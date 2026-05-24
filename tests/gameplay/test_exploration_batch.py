"""
Tests for ExplorationBatch + BatchCoordinator.

TDD tests for Task 2 of Phase 4 Plan 01.
Covers: batch lifecycle, deadline flush, party-size flush, concurrency safety,
post-flush submission, degraded-mode (unknown party size), serialization.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from eldritch_dm.gameplay.exploration_batch import (
    BatchCoordinator,
    ExplorationBatch,
    PlayerIntent,
    serialize_batch_payload,
)


def _make_intent(user_id: str = "u1", text: str = "I search the chest") -> PlayerIntent:
    """Create a test PlayerIntent with sensible defaults."""
    return PlayerIntent(
        user_id=user_id,
        sanitized_wrapped=f'<player_action speaker="Aria" user_id="{user_id}">{text}</player_action>',
        character_id=None,
        ts=datetime.now(UTC),
    )


# ── Test 1: First submit starts a new batch ───────────────────────────────────


async def test_first_submit_starts_batch_with_30s_deadline():
    """First submit() starts a new ExplorationBatch; deadline = now + 30s."""
    base_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    coordinator = BatchCoordinator(window_seconds=30, clock=lambda: base_time)

    result = await coordinator.submit("ch-1", _make_intent("u1"))

    assert result.flushed is False
    assert result.batch is None
    assert coordinator.has_batch("ch-1")

    remaining = coordinator.get_deadline_seconds_remaining("ch-1")
    assert remaining is not None
    assert abs(remaining - 30.0) < 0.5


# ── Test 2: Subsequent submits append to the same batch ──────────────────────


async def test_subsequent_submits_append_within_window():
    """Subsequent submits within the window append; flushed=False returned."""
    base_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    coordinator = BatchCoordinator(window_seconds=30, clock=lambda: base_time)
    coordinator.set_active_party_size("ch-1", 4)  # party of 4; won't flush at 2

    await coordinator.submit("ch-1", _make_intent("u1", "I search the chest"))
    result = await coordinator.submit("ch-1", _make_intent("u2", "I guard the door"))

    assert result.flushed is False
    # Batch still open with 2 submissions
    remaining = coordinator.get_deadline_seconds_remaining("ch-1")
    assert remaining is not None  # still open


# ── Test 3: Party-size flush ──────────────────────────────────────────────────


async def test_party_size_flush_when_all_players_submit():
    """When len(submissions) == active_party_size, submit returns flushed=True."""
    base_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    coordinator = BatchCoordinator(window_seconds=30, clock=lambda: base_time)
    coordinator.set_active_party_size("ch-1", 3)

    await coordinator.submit("ch-1", _make_intent("u1"))
    await coordinator.submit("ch-1", _make_intent("u2"))
    result = await coordinator.submit("ch-1", _make_intent("u3"))  # 3rd = flush

    assert result.flushed is True
    assert result.batch is not None
    assert len(result.batch.submissions) == 3
    # Batch removed from coordinator
    assert not coordinator.has_batch("ch-1")


# ── Test 4: Deadline-driven flush via tick() ──────────────────────────────────


async def test_tick_flushes_expired_batches():
    """tick(now) returns channel_ids whose batches have expired; coordinator removes them."""
    base_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    coordinator = BatchCoordinator(window_seconds=30, clock=lambda: base_time)
    coordinator.set_active_party_size("ch-1", 4)  # won't fill naturally

    await coordinator.submit("ch-1", _make_intent("u1"))

    # Tick before deadline — no flush
    expired_early = coordinator.tick(base_time + timedelta(seconds=25))
    assert expired_early == []
    assert coordinator.has_batch("ch-1")

    # Tick at/after deadline — flush
    expired_at = coordinator.tick(base_time + timedelta(seconds=30))
    assert len(expired_at) == 1
    ch_id, batch = expired_at[0]
    assert ch_id == "ch-1"
    assert len(batch.submissions) == 1
    assert not coordinator.has_batch("ch-1")


# ── Test 5: Post-flush submission starts new batch ────────────────────────────


async def test_submit_after_flush_starts_new_batch():
    """A submission after batch flush starts a new batch (D-10)."""
    base_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    coordinator = BatchCoordinator(window_seconds=30, clock=lambda: base_time)
    coordinator.set_active_party_size("ch-1", 1)

    # Flush the first batch
    result1 = await coordinator.submit("ch-1", _make_intent("u1"))
    assert result1.flushed is True

    # Now submit again — should start a new batch
    result2 = await coordinator.submit("ch-1", _make_intent("u1", "I attack the goblin"))
    assert result2.flushed is True  # party of 1 → immediate flush again
    assert result2.batch is not None


# ── Test 6: Unknown party size — deadline-only flush ─────────────────────────


async def test_unknown_party_size_deadline_only():
    """Without set_active_party_size, only deadline flushes (degraded but safe)."""
    base_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    coordinator = BatchCoordinator(window_seconds=30, clock=lambda: base_time)
    # No set_active_party_size call

    for i in range(10):
        result = await coordinator.submit("ch-1", _make_intent(f"u{i}"))
        assert result.flushed is False, f"Should not flush on submit {i} without party size"

    # Only tick after deadline flushes
    expired = coordinator.tick(base_time + timedelta(seconds=31))
    assert len(expired) == 1


# ── Test 7: Concurrent submit — exactly one double-flush ────────────────────────


async def test_concurrent_submit_no_double_flush():
    """Concurrent submit calls from 4 tasks produce exactly one flushed=True."""
    base_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    coordinator = BatchCoordinator(window_seconds=30, clock=lambda: base_time)
    coordinator.set_active_party_size("ch-1", 4)

    intents = [_make_intent(f"u{i}") for i in range(4)]

    results = await asyncio.gather(
        *[coordinator.submit("ch-1", intent) for intent in intents]
    )

    flushed_count = sum(1 for r in results if r.flushed)
    assert flushed_count == 1, (
        f"Expected exactly 1 flush, got {flushed_count}. "
        f"Results: {[(r.flushed, len(r.batch.submissions) if r.batch else 0) for r in results]}"
    )


# ── Serialization test ────────────────────────────────────────────────────────


def test_serialize_batch_payload():
    """serialize_batch_payload wraps all submissions in <batch>...</batch>."""
    intent1 = PlayerIntent(
        user_id="u1",
        sanitized_wrapped='<player_action speaker="Aria" user_id="u1">I search the chest</player_action>',
        character_id=None,
        ts=datetime.now(UTC),
    )
    intent2 = PlayerIntent(
        user_id="u2",
        sanitized_wrapped='<player_action speaker="Thorin" user_id="u2">I guard the door</player_action>',
        character_id=None,
        ts=datetime.now(UTC),
    )
    batch = ExplorationBatch(
        first_submission_ts=datetime.now(UTC),
        deadline_ts=datetime.now(UTC),
        submissions=[intent1, intent2],
    )

    payload = serialize_batch_payload(batch)
    assert payload.startswith("<batch>")
    assert payload.endswith("</batch>")
    assert "Aria" in payload
    assert "Thorin" in payload
    assert "I search the chest" in payload
    assert "I guard the door" in payload
