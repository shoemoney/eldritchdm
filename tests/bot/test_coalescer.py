"""
tests/bot/test_coalescer.py — EmbedCoalescer TDD tests.

Tests cover:
  1. First update fires immediately (no sleep when last_edit_t == -inf)
  2. Rate-limiting: two updates produce second edit delayed by ~rate_limit_seconds
  3. Latest-value semantics: 5 rapid updates → 2 edits total (1st + final)
  4. Abandoned on NotFound
  5. Abandoned on Forbidden
  6. Transient HTTPException — no abandon, next update retries
  7. close() cancels render task
  8. env-driven rate: default Settings rate_limit=1.0 respected

All tests use fake clock + fake sleep for determinism (<1s total runtime).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import discord
import pytest

# EmbedCoalescer is the SUT (System Under Test)
from eldritch_dm.bot.coalescer import EmbedCoalescer


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_fake_message(message_id: int = 12345) -> MagicMock:
    """Build a fake discord.Message with AsyncMock .edit and an .id."""
    msg = MagicMock(spec=discord.Message)
    msg.id = message_id
    msg.edit = AsyncMock()
    return msg


def make_embed(title: str = "test") -> discord.Embed:
    return discord.Embed(title=title)


def make_view() -> discord.ui.View:
    return discord.ui.View(timeout=None)


# ── Test 1: First update fires immediately ────────────────────────────────────


@pytest.mark.asyncio
async def test_first_update_fires_immediately():
    """With _last_edit_t == -inf, first update triggers edit without sleep."""
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    clock_val = 100.0

    def fake_clock() -> float:
        return clock_val

    msg = make_fake_message()
    coalescer = EmbedCoalescer(
        msg,
        rate_limit_seconds=1.0,
        clock=fake_clock,
        sleep=fake_sleep,
    )

    embed = make_embed("first")
    await coalescer.update(embed)

    # Give the event loop a few ticks to run the render task
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Edit should have been called once, with no sleep
    assert msg.edit.await_count >= 1
    assert sleep_calls == [], f"Expected no sleep calls, got: {sleep_calls}"

    await coalescer.close()


# ── Test 2: Rate-limit applied on second rapid update ────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_applied_on_second_update():
    """Two rapid updates produce 2 edits; second is delayed by sleep(~rate_limit - elapsed)."""
    sleep_calls: list[float] = []
    event_loop = asyncio.get_event_loop()

    # Use a real asyncio.Event to coordinate the test
    sleep_started = asyncio.Event()
    sleep_done = asyncio.Event()

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        sleep_started.set()
        await sleep_done.wait()

    clock_val = 0.5  # 0.5s elapsed since last edit
    rate_limit = 1.0

    def fake_clock() -> float:
        return clock_val

    msg = make_fake_message()
    coalescer = EmbedCoalescer(
        msg,
        rate_limit_seconds=rate_limit,
        clock=fake_clock,
        sleep=fake_sleep,
    )

    # First update fires immediately (last_edit_t starts at -inf)
    embed1 = make_embed("first")
    await coalescer.update(embed1)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Now simulate that 0.5s have elapsed since last edit
    # Second update: clock says 0.5s elapsed; need sleep(0.5s more)
    embed2 = make_embed("second")
    await coalescer.update(embed2)

    # Wait for sleep to be called
    try:
        await asyncio.wait_for(sleep_started.wait(), timeout=1.0)
    except TimeoutError:
        pass

    assert len(sleep_calls) >= 1, "Expected sleep to be called for rate-limiting"
    # Sleep should be ~0.5s (rate_limit - elapsed = 1.0 - 0.5)
    assert abs(sleep_calls[0] - 0.5) < 0.1, f"Expected sleep(~0.5), got sleep({sleep_calls[0]})"

    sleep_done.set()
    await asyncio.sleep(0)

    await coalescer.close()


# ── Test 3: Latest-value semantics ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_latest_value_semantics():
    """5 rapid updates in rate-limit window → 2 edits total; only 1st + 5th payload sent."""
    sleep_calls: list[float] = []
    sleep_release = asyncio.Event()

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        await sleep_release.wait()

    call_count = 0

    def fake_clock() -> float:
        return float(call_count)

    msg = make_fake_message()
    coalescer = EmbedCoalescer(
        msg,
        rate_limit_seconds=1.0,
        clock=fake_clock,
        sleep=fake_sleep,
    )

    # First update fires immediately
    embed1 = make_embed("payload-1")
    await coalescer.update(embed1)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Wait for first edit to complete
    for _ in range(5):
        await asyncio.sleep(0)

    # Now send 4 more rapid updates — all arrive while rate-limiter is sleeping
    for i in range(2, 6):
        await coalescer.update(make_embed(f"payload-{i}"))

    # Release the sleep so second edit fires
    sleep_release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Should have exactly 2 edits; first with payload-1, second with payload-5
    assert msg.edit.await_count == 2, f"Expected 2 edits, got {msg.edit.await_count}"

    # The 5th payload should be the one in the second edit
    second_call_kwargs = msg.edit.call_args_list[1].kwargs
    embed_sent = second_call_kwargs.get("embed")
    assert embed_sent is not None
    assert embed_sent.title == "payload-5", (
        f"Expected 'payload-5' in second edit, got: {embed_sent.title!r}"
    )

    await coalescer.close()


# ── Test 4: Abandoned on NotFound ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_abandoned_on_not_found():
    """If message.edit raises discord.NotFound, coalescer marks _abandoned=True; subsequent updates no-op."""

    async def fake_sleep(s: float) -> None:
        pass

    def fake_clock() -> float:
        return 0.0

    msg = make_fake_message()
    # Raise NotFound on first call
    not_found = discord.NotFound(MagicMock(status=404), "Unknown Message")
    msg.edit.side_effect = not_found

    coalescer = EmbedCoalescer(
        msg,
        rate_limit_seconds=0.0,
        clock=fake_clock,
        sleep=fake_sleep,
    )

    await coalescer.update(make_embed("gone"))
    # Let the render task process the update
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert coalescer._abandoned is True

    # Subsequent updates should be no-ops (no new edits)
    msg.edit.reset_mock()
    msg.edit.side_effect = None
    await coalescer.update(make_embed("nope"))
    await asyncio.sleep(0)
    msg.edit.assert_not_awaited()

    await coalescer.close()


# ── Test 5: Abandoned on Forbidden ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_abandoned_on_forbidden():
    """If message.edit raises discord.Forbidden, coalescer marks _abandoned=True."""

    async def fake_sleep(s: float) -> None:
        pass

    def fake_clock() -> float:
        return 0.0

    msg = make_fake_message()
    forbidden = discord.Forbidden(MagicMock(status=403), "Missing Permissions")
    msg.edit.side_effect = forbidden

    coalescer = EmbedCoalescer(
        msg,
        rate_limit_seconds=0.0,
        clock=fake_clock,
        sleep=fake_sleep,
    )

    await coalescer.update(make_embed("forbidden"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert coalescer._abandoned is True

    msg.edit.reset_mock()
    msg.edit.side_effect = None
    await coalescer.update(make_embed("still nope"))
    await asyncio.sleep(0)
    msg.edit.assert_not_awaited()

    await coalescer.close()


# ── Test 6: Transient HTTPException — no abandon ──────────────────────────────


@pytest.mark.asyncio
async def test_transient_http_error_no_abandon():
    """discord.HTTPException (non-NotFound/Forbidden) doesn't abandon; next update retries."""

    async def fake_sleep(s: float) -> None:
        pass

    def fake_clock() -> float:
        return 0.0

    msg = make_fake_message()

    call_count = 0

    async def mock_edit(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            http_err = discord.HTTPException(MagicMock(status=503), "Service Unavailable")
            raise http_err
        # Second call succeeds

    msg.edit.side_effect = mock_edit

    coalescer = EmbedCoalescer(
        msg,
        rate_limit_seconds=0.0,
        clock=fake_clock,
        sleep=fake_sleep,
    )

    # First update — raises HTTPException(503), does NOT abandon
    await coalescer.update(make_embed("try-1"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert coalescer._abandoned is False

    # Second update — should succeed
    await coalescer.update(make_embed("try-2"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Not abandoned; second edit attempted
    assert call_count >= 2
    assert coalescer._abandoned is False

    await coalescer.close()


# ── Test 7: close() cancels render task ──────────────────────────────────────


@pytest.mark.asyncio
async def test_close_cancels_render_task():
    """close() should cancel the render task; no further edits happen after close."""
    released = asyncio.Event()

    async def fake_sleep(s: float) -> None:
        await released.wait()

    def fake_clock() -> float:
        return 0.0

    msg = make_fake_message()
    coalescer = EmbedCoalescer(
        msg,
        rate_limit_seconds=1.0,
        clock=fake_clock,
        sleep=fake_sleep,
    )

    # Update and trigger sleep inside render loop
    await coalescer.update(make_embed("first"))
    # Let first edit process
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Schedule second update (will be pending in sleep)
    await coalescer.update(make_embed("second"))

    # Close should cancel and return quickly
    await coalescer.close()

    # Render task must be done (cancelled)
    assert coalescer._render_task is None or coalescer._render_task.done()

    # Released so the sleep (if still active) doesn't hang
    released.set()

    # Give loop a moment
    await asyncio.sleep(0)


# ── Test 8: env-driven rate respects default Settings ─────────────────────────


@pytest.mark.asyncio
async def test_env_driven_rate_limit():
    """EmbedCoalescer(message, rate_limit_seconds=settings.embed_edit_rate_limit) uses 1.0."""
    from eldritch_dm.config import Settings

    settings = Settings(
        discord_token="test-token",
        discord_guild_ids="",
        eldritch_db_path="/tmp/test.sqlite3",
        omlx_health_interval=3600,
    )

    async def fake_sleep(s: float) -> None:
        pass

    def fake_clock() -> float:
        return 0.0

    msg = make_fake_message()
    coalescer = EmbedCoalescer(
        msg,
        rate_limit_seconds=settings.embed_edit_rate_limit,
        clock=fake_clock,
        sleep=fake_sleep,
    )

    # Default embed_edit_rate_limit should be 1.0
    assert coalescer._rate_limit_seconds == 1.0, (
        f"Expected rate_limit_seconds=1.0, got {coalescer._rate_limit_seconds}"
    )

    await coalescer.close()
