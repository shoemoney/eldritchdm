"""
Tests for PartyModeOrchestrator.

TDD tests for Task 2 of Phase 4 Plan 01.
Covers: task lifecycle, pop/thinking/resolve loop, empty-queue sleep, prefetch,
rate-limiter gating, combat-transition watcher, error resilience, cancellation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


import eldritch_dm.mcp.tools as mcp_tools_module
from eldritch_dm.gameplay.exploration_batch import BatchCoordinator
from eldritch_dm.gameplay.party_mode import PartyModeOrchestrator
from eldritch_dm.mcp.rate_limit import ChannelRateLimiter
from eldritch_dm.persistence.models import ChannelState


def _make_stopped_orchestrator():
    """Build a PartyModeOrchestrator whose sleep immediately raises CancelledError."""
    mock_mcp = MagicMock()
    mock_sessions = AsyncMock()
    mock_sessions.set_state = AsyncMock()

    async def instant_cancel(s: float) -> None:
        raise asyncio.CancelledError()

    mock_limiter = ChannelRateLimiter(min_interval_ms=0)
    mock_coordinator = BatchCoordinator(window_seconds=30)

    orchestrator = PartyModeOrchestrator(
        mcp=mock_mcp,
        rate_limiter=mock_limiter,
        batch_coordinator=mock_coordinator,
        channel_sessions=mock_sessions,
        poll_interval_ms=250,
        combat_check_every_n_polls=4,
        sleep=instant_cancel,
    )
    return orchestrator, mock_sessions


async def _run_orchestrator_briefly(orchestrator, channel_id="ch-1", n_loops=2):
    """Run the orchestrator loop for at most n_loops sleep calls, then stop."""
    count = [0]
    original_sleep = orchestrator._sleep

    async def counting_sleep(s: float) -> None:
        count[0] += 1
        if count[0] >= n_loops:
            raise asyncio.CancelledError()
        # Don't actually sleep

    orchestrator._sleep = counting_sleep
    task = await orchestrator.start_orchestrator_for_channel(channel_id, "Camp", "sess-1")
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
    except (TimeoutError, asyncio.CancelledError):
        pass
    finally:
        await orchestrator.stop_orchestrator_for_channel(channel_id)

    orchestrator._sleep = original_sleep


# ── Test 8: start_orchestrator creates exactly one task ──────────────────────


async def test_start_orchestrator_creates_one_task():
    """start_orchestrator_for_channel creates exactly one task; calling again is a no-op."""
    orchestrator, _ = _make_stopped_orchestrator()

    async def fake_loop(ch, camp, sess):
        await asyncio.sleep(1000)

    orchestrator._loop = fake_loop

    task1 = await orchestrator.start_orchestrator_for_channel("ch-1", "TestCamp", "sess-1")
    task2 = await orchestrator.start_orchestrator_for_channel("ch-1", "TestCamp", "sess-1")

    assert task1 is task2, "Second start should return the existing task"

    await orchestrator.stop_orchestrator_for_channel("ch-1")
    assert "ch-1" not in orchestrator._tasks


# ── Test 9: stop_orchestrator cancels and removes task ───────────────────────


async def test_stop_orchestrator_cancels_task():
    """stop_orchestrator_for_channel cancels the task and removes it from registry."""
    orchestrator, _ = _make_stopped_orchestrator()

    async def fake_loop(ch, camp, sess):
        await asyncio.sleep(1000)

    orchestrator._loop = fake_loop

    await orchestrator.start_orchestrator_for_channel("ch-1", "TestCamp", "sess-1")
    assert "ch-1" in orchestrator._tasks

    await orchestrator.stop_orchestrator_for_channel("ch-1")
    assert "ch-1" not in orchestrator._tasks

    # Idempotent — calling again is safe
    await orchestrator.stop_orchestrator_for_channel("ch-1")


# ── Test 11: Empty pop → sleep poll_interval ──────────────────────────────────


async def test_empty_pop_sleeps_poll_interval():
    """An empty pop causes the orchestrator to sleep poll_interval_s."""
    orchestrator, _ = _make_stopped_orchestrator()
    sleep_values: list[float] = []

    async def track_sleep(s: float) -> None:
        sleep_values.append(s)
        raise asyncio.CancelledError()

    orchestrator._sleep = track_sleep

    with patch.object(mcp_tools_module, "party_pop_action", new=AsyncMock(return_value={"empty": True})):
        with patch.object(mcp_tools_module, "get_game_state", new=AsyncMock(return_value="**In Combat:** No\n**Round:** 0")):
            task = await orchestrator.start_orchestrator_for_channel("ch-1", "C", "s1")
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
            except (TimeoutError, asyncio.CancelledError):
                pass

    # Should have slept the poll interval (0.250)
    assert len(sleep_values) >= 1
    assert abs(sleep_values[0] - 0.250) < 0.001, (
        f"Expected poll sleep of 0.250s, got {sleep_values[0]}"
    )


# ── Test 12a: party_get_prefetch called when turn_id present ──────────────────


async def test_prefetch_called_when_turn_id_present():
    """party_get_prefetch is called when the popped action has turn_id."""
    prefetch_calls: list[str] = []

    async def fake_prefetch(client, *, turn_id, **kwargs):
        prefetch_calls.append(turn_id)
        return {}

    action_with_turn_id = {
        "empty": False,
        "action": {"id": "action-1", "turn_id": "turn-abc", "player_id": "u1", "text": "I attack"},
    }

    # pop returns the action once, then always empty (so the loop polls then cancels)
    pop_responses = iter([action_with_turn_id])

    async def pop_once(client):
        try:
            return next(pop_responses)
        except StopIteration:
            raise asyncio.CancelledError()

    orchestrator, _ = _make_stopped_orchestrator()

    # Override sleep to just raise CancelledError so we don't loop
    async def cancel_on_sleep(s: float) -> None:
        raise asyncio.CancelledError()

    orchestrator._sleep = cancel_on_sleep

    with (
        patch.object(mcp_tools_module, "party_pop_action", new=pop_once),
        patch.object(mcp_tools_module, "party_thinking", new=AsyncMock(return_value={})),
        patch.object(mcp_tools_module, "party_resolve_action", new=AsyncMock(return_value={})),
        patch.object(mcp_tools_module, "party_get_prefetch", new=fake_prefetch),
        patch.object(mcp_tools_module, "get_game_state", new=AsyncMock(return_value="**In Combat:** No\n**Round:** 0")),
    ):
        task = await orchestrator.start_orchestrator_for_channel("ch-a", "C", "s1")
        try:
            await asyncio.wait_for(task, timeout=3.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
        # Task is already cancelled/done here

    assert len(prefetch_calls) >= 1, "party_get_prefetch should be called when turn_id present"
    assert "turn-abc" in prefetch_calls


# ── Test 12b: party_get_prefetch NOT called without turn_id ──────────────────


async def test_prefetch_not_called_without_turn_id():
    """party_get_prefetch is NOT called when action has no turn_id."""
    prefetch_calls: list[str] = []

    async def fake_prefetch(client, *, turn_id, **kwargs):
        prefetch_calls.append(turn_id)
        return {}

    action_no_turn = {
        "empty": False,
        "action": {"id": "action-2", "player_id": "u1", "text": "I explore"},
    }

    pop_responses = iter([action_no_turn])

    async def pop_once(client):
        try:
            return next(pop_responses)
        except StopIteration:
            raise asyncio.CancelledError()

    orchestrator, _ = _make_stopped_orchestrator()

    async def cancel_on_sleep(s: float) -> None:
        raise asyncio.CancelledError()

    orchestrator._sleep = cancel_on_sleep

    with (
        patch.object(mcp_tools_module, "party_pop_action", new=pop_once),
        patch.object(mcp_tools_module, "party_thinking", new=AsyncMock(return_value={})),
        patch.object(mcp_tools_module, "party_resolve_action", new=AsyncMock(return_value={})),
        patch.object(mcp_tools_module, "party_get_prefetch", new=fake_prefetch),
        patch.object(mcp_tools_module, "get_game_state", new=AsyncMock(return_value="**In Combat:** No\n**Round:** 0")),
    ):
        task = await orchestrator.start_orchestrator_for_channel("ch-b", "C", "s1")
        try:
            await asyncio.wait_for(task, timeout=3.0)
        except (TimeoutError, asyncio.CancelledError):
            pass

    assert len(prefetch_calls) == 0, "party_get_prefetch should NOT be called without turn_id"


# ── Test 13: Mutating calls go through rate limiter ──────────────────────────


async def test_mutating_calls_gated_by_rate_limiter():
    """party_thinking and party_resolve_action go through ChannelRateLimiter.acquire."""
    acquired_channels: list[str] = []

    class TrackingLimiter(ChannelRateLimiter):
        async def acquire(self, channel_id: str) -> None:
            acquired_channels.append(channel_id)

    orchestrator, _ = _make_stopped_orchestrator()
    orchestrator._rate_limiter = TrackingLimiter(min_interval_ms=0)

    async def one_shot_sleep(s: float) -> None:
        raise asyncio.CancelledError()

    orchestrator._sleep = one_shot_sleep

    action = {
        "empty": False,
        "action": {"id": "action-1", "turn_id": "turn-1", "player_id": "u1", "text": "I attack"},
    }

    action_pop_responses = iter([action])

    async def pop_once_then_cancel(client):
        try:
            return next(action_pop_responses)
        except StopIteration:
            raise asyncio.CancelledError()

    async def cancel_on_sleep(s: float) -> None:
        raise asyncio.CancelledError()

    orchestrator._sleep = cancel_on_sleep

    with (
        patch.object(mcp_tools_module, "party_pop_action", new=pop_once_then_cancel),
        patch.object(mcp_tools_module, "party_thinking", new=AsyncMock(return_value={})),
        patch.object(mcp_tools_module, "party_get_prefetch", new=AsyncMock(return_value={})),
        patch.object(mcp_tools_module, "party_resolve_action", new=AsyncMock(return_value={})),
        patch.object(mcp_tools_module, "get_game_state", new=AsyncMock(return_value="**In Combat:** No\n**Round:** 0")),
    ):
        task = await orchestrator.start_orchestrator_for_channel("ch-1", "C", "s1")
        try:
            await asyncio.wait_for(task, timeout=3.0)
        except (TimeoutError, asyncio.CancelledError):
            pass

    # party_thinking and party_resolve_action are mutating; both should gate
    assert len(acquired_channels) >= 2, (
        f"Expected >=2 rate-limiter acquires (thinking + resolve), got {acquired_channels}"
    )
    for ch in acquired_channels:
        assert ch == "ch-1"


# ── Test 14: Combat-transition callback fires exactly once ────────────────────


async def test_combat_transition_callback_fires_once():
    """Combat-transition callback fires exactly once on EXPLORATION->COMBAT."""
    state_changes: list[tuple[str, ChannelState, ChannelState]] = []
    sleep_call_count = [0]

    async def on_state_change(ch_id, old, new):
        state_changes.append((ch_id, old, new))

    # game_state: first not-in-combat (init), then combat twice
    game_state_responses = [
        "**In Combat:** No\n**Round:** 0",   # tick 4: initialize
        "**In Combat:** Yes\n**Round:** 1",  # tick 8: COMBAT START
        "**In Combat:** Yes\n**Round:** 1",  # tick 12: same, no second callback
    ]
    gs_idx = [0]

    async def cycle_game_state(client):
        val = game_state_responses[min(gs_idx[0], len(game_state_responses) - 1)]
        gs_idx[0] += 1
        return val

    async def counting_sleep(s: float) -> None:
        sleep_call_count[0] += 1
        if sleep_call_count[0] >= 15:
            raise asyncio.CancelledError()

    mock_sessions = AsyncMock()
    mock_sessions.set_state = AsyncMock()

    orchestrator = PartyModeOrchestrator(
        mcp=MagicMock(),
        rate_limiter=ChannelRateLimiter(min_interval_ms=0),
        batch_coordinator=BatchCoordinator(window_seconds=30),
        channel_sessions=mock_sessions,
        poll_interval_ms=250,
        combat_check_every_n_polls=4,
        sleep=counting_sleep,
    )
    orchestrator.register_state_change_callback(on_state_change)

    with (
        patch.object(mcp_tools_module, "party_pop_action", new=AsyncMock(return_value={"empty": True})),
        patch.object(mcp_tools_module, "get_game_state", new=cycle_game_state),
    ):
        task = await orchestrator.start_orchestrator_for_channel("ch-1", "C", "s1")
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass

    # Should fire exactly once for EXPLORATION->COMBAT transition
    combat_transitions = [
        t for t in state_changes
        if t[1] == ChannelState.EXPLORATION and t[2] == ChannelState.COMBAT
    ]
    assert len(combat_transitions) == 1, (
        f"Expected exactly 1 EXPLORATION->COMBAT transition, got {len(combat_transitions)}. "
        f"All transitions: {state_changes}"
    )


# ── Test 15: pop error does not crash loop ────────────────────────────────────


async def test_pop_error_does_not_crash_loop():
    """party_pop_action raising an exception does not crash the loop; retries."""
    error_count = [0]
    sleep_count = [0]

    async def limited_sleep(s: float) -> None:
        sleep_count[0] += 1
        if sleep_count[0] >= 3:
            raise asyncio.CancelledError()

    async def flaky_pop(client):
        error_count[0] += 1
        if error_count[0] <= 2:
            raise RuntimeError("dm20 offline")
        return {"empty": True}

    orchestrator = PartyModeOrchestrator(
        mcp=MagicMock(),
        rate_limiter=ChannelRateLimiter(min_interval_ms=0),
        batch_coordinator=BatchCoordinator(window_seconds=30),
        channel_sessions=AsyncMock(),
        poll_interval_ms=250,
        sleep=limited_sleep,
    )

    with (
        patch.object(mcp_tools_module, "party_pop_action", new=flaky_pop),
        patch.object(mcp_tools_module, "get_game_state", new=AsyncMock(return_value="**In Combat:** No\n**Round:** 0")),
    ):
        task = await orchestrator.start_orchestrator_for_channel("ch-1", "C", "s1")
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass

    assert error_count[0] >= 2, "Loop should have retried after pop errors"
    assert sleep_count[0] >= 1, "Loop should have slept after errors"


# ── Test 16: Cancellation — clean cancel on CancelledError ────────────────────


async def test_orchestrator_cancellation_is_clean():
    """Orchestrator task awaits CancelledError cleanly; no orphaned tasks."""
    orchestrator, _ = _make_stopped_orchestrator()

    # Use the stopped orchestrator (sleep immediately cancels)
    orchestrator2, _ = _make_stopped_orchestrator()

    with (
        patch.object(mcp_tools_module, "party_pop_action", new=AsyncMock(return_value={"empty": True})),
        patch.object(mcp_tools_module, "get_game_state", new=AsyncMock(return_value="**In Combat:** No\n**Round:** 0")),
    ):
        task = await orchestrator2.start_orchestrator_for_channel("ch-cancel", "C", "s")

        # Allow the task to start and run
        await asyncio.sleep(0)

        # Cancel via stop
        await orchestrator2.stop_orchestrator_for_channel("ch-cancel")

        # Task should be done
        assert task.done()
        assert "ch-cancel" not in orchestrator2._tasks
