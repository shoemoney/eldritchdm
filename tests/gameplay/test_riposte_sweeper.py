"""
Tests for gameplay/riposte_sweeper.py (Phase 5 Plan 02 Task 1).

RiposteSweeper is the background asyncio.Task that wakes on the earliest
pending ``deadline_ts``, marks expired any past-deadline rows, and
best-effort deletes the corresponding public Discord message. Sweeper
shares ``SessionLocks`` with ``handle_riposte_click`` so click-at-deadline
races are deterministic (RESEARCH Pitfall 3).

Per plan behavior section (Tests 7-14):
  7.  start() creates Task; stop() cancels + awaits clean shutdown.
  8.  Empty queue → sleeps default_sleep_s (30.0).
  9.  Single future-deadline row → sleeps until (deadline - now), capped.
  10. Past-deadline row → mark_expired + fetch_message + delete.
  11. Discord HTTP errors (NotFound/Forbidden/HTTPException) → caught.
  12. Sweeper acquires SessionLocks lock BEFORE calling mark_expired.
  13. Cooperative cancellation: CancelledError re-raised.
  14. Unexpected exception → caught, logged, defensive 1.0s sleep, continue.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.gameplay.riposte_sweeper import RiposteSweeper
from eldritch_dm.gameplay.session_locks import SessionLocks
from eldritch_dm.persistence.models import RiposteStatus, RiposteTimer

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_timer(
    *,
    id_: int = 1,
    deadline_seconds_from_now: float = 8.0,
    channel_id: str = "ch-1",
    message_id: str = "msg-1",
) -> RiposteTimer:
    now = datetime.now(UTC)
    return RiposteTimer(
        id=id_,
        channel_id=channel_id,
        character_id="hero-001",
        user_id="999",
        monster_uuid="goblin-001",
        weapon_used="longsword",
        message_id=message_id,
        custom_id=f"riposte:{id_}:999",
        deadline_ts=now + timedelta(seconds=deadline_seconds_from_now),
        status=RiposteStatus.PENDING,
        created_at=now,
    )


def _make_bot_with_channel(message_mock: MagicMock | None = None) -> MagicMock:
    """Build a mocked bot whose get_channel returns a channel mock chain."""
    bot = MagicMock()
    if message_mock is None:
        message_mock = MagicMock()
        message_mock.delete = AsyncMock()
    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=message_mock)
    bot.get_channel = MagicMock(return_value=channel)
    return bot


# ── Test 7: start()/stop() lifecycle ─────────────────────────────────────────


class TestStartStopLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_task_stop_cancels_cleanly(self) -> None:
        repo = MagicMock()
        repo.list_pending = AsyncMock(return_value=[])
        repo.mark_expired = AsyncMock()

        bot = MagicMock()
        locks = SessionLocks()

        # Use a long default_sleep so the loop parks; we cancel before it fires.
        sweeper = RiposteSweeper(
            repo=repo,
            bot=bot,
            session_locks=locks,
            default_sleep_s=60.0,
            min_sleep_s=0.1,
        )
        await sweeper.start()
        assert sweeper.is_running() is True

        await sweeper.stop()
        assert sweeper.is_running() is False


# ── Test 8: empty queue → default sleep ──────────────────────────────────────


class TestEmptyQueueSleep:
    @pytest.mark.asyncio
    async def test_no_pending_rows_sleeps_default(self) -> None:
        repo = MagicMock()
        repo.list_pending = AsyncMock(return_value=[])
        repo.mark_expired = AsyncMock()

        bot = MagicMock()
        locks = SessionLocks()

        sleep_calls: list[float] = []

        async def fake_sleep(s: float) -> None:
            sleep_calls.append(s)
            # Trip an exception to break the loop after one iteration
            raise asyncio.CancelledError

        sweeper = RiposteSweeper(
            repo=repo,
            bot=bot,
            session_locks=locks,
            default_sleep_s=30.0,
            min_sleep_s=0.1,
            sleep=fake_sleep,
        )

        with pytest.raises(asyncio.CancelledError):
            await sweeper._iterate_once()
        assert sleep_calls == [30.0]


# ── Test 9: single future-deadline row → sleeps to deadline ──────────────────


class TestFutureDeadlineSleep:
    @pytest.mark.asyncio
    async def test_future_deadline_sleeps_until_deadline(self) -> None:
        # deadline 5s in future → sleep ≈ 5s
        timer = _make_timer(deadline_seconds_from_now=5.0)

        repo = MagicMock()
        repo.list_pending = AsyncMock(return_value=[timer])
        repo.mark_expired = AsyncMock()

        bot = MagicMock()
        locks = SessionLocks()

        sleep_calls: list[float] = []

        async def fake_sleep(s: float) -> None:
            sleep_calls.append(s)
            raise asyncio.CancelledError

        sweeper = RiposteSweeper(
            repo=repo,
            bot=bot,
            session_locks=locks,
            default_sleep_s=30.0,
            min_sleep_s=0.1,
            sleep=fake_sleep,
        )

        with pytest.raises(asyncio.CancelledError):
            await sweeper._iterate_once()
        assert sleep_calls, "Expected at least one sleep call"
        slept = sleep_calls[0]
        # Allow some slack: the value is bounded between min_sleep_s and default_sleep_s,
        # but the time-to-deadline is approximately 5s.
        assert 4.5 <= slept <= 5.1, f"Expected ~5s sleep, got {slept}"

    @pytest.mark.asyncio
    async def test_sleep_cap_uses_min_sleep_floor(self) -> None:
        """deadline already passed (or very close) → at least min_sleep_s."""
        # Use a deadline that's basically now
        timer = _make_timer(deadline_seconds_from_now=-0.5)  # already past
        repo = MagicMock()
        repo.list_pending = AsyncMock(return_value=[timer])
        repo.mark_expired = AsyncMock()

        bot = _make_bot_with_channel()
        locks = SessionLocks()

        sleep_calls: list[float] = []

        async def fake_sleep(s: float) -> None:
            sleep_calls.append(s)
            raise asyncio.CancelledError

        sweeper = RiposteSweeper(
            repo=repo,
            bot=bot,
            session_locks=locks,
            default_sleep_s=30.0,
            min_sleep_s=0.1,
            sleep=fake_sleep,
        )

        with pytest.raises(asyncio.CancelledError):
            await sweeper._iterate_once()
        # past-deadline row gets expired AND list_pending re-runs returning empty;
        # then sleep is default_sleep_s. The point is: no negative sleep value.
        assert all(s >= 0.0 for s in sleep_calls), (
            f"All sleep values must be non-negative, got {sleep_calls}"
        )


# ── Test 10: past-deadline → mark_expired + delete ───────────────────────────


class TestPastDeadlineExpiry:
    @pytest.mark.asyncio
    async def test_past_deadline_marks_expired_and_deletes_message(self) -> None:
        timer = _make_timer(
            id_=42,
            deadline_seconds_from_now=-1.0,
            channel_id="999",
            message_id="111",
        )
        # First call returns the past-deadline row; second returns empty
        repo = MagicMock()
        repo.list_pending = AsyncMock(side_effect=[[timer], []])
        repo.mark_expired = AsyncMock()

        msg = MagicMock()
        msg.delete = AsyncMock()
        bot = _make_bot_with_channel(msg)
        locks = SessionLocks()

        async def fake_sleep(_s: float) -> None:
            raise asyncio.CancelledError

        sweeper = RiposteSweeper(
            repo=repo,
            bot=bot,
            session_locks=locks,
            sleep=fake_sleep,
        )

        with pytest.raises(asyncio.CancelledError):
            await sweeper._iterate_once()

        repo.mark_expired.assert_awaited_once_with(42)
        bot.get_channel.assert_called_once_with(999)
        bot.get_channel.return_value.fetch_message.assert_awaited_once_with(111)
        msg.delete.assert_awaited_once()


# ── Test 11: Discord HTTP failures are caught ────────────────────────────────


class TestDiscordHTTPErrorHandling:
    @pytest.mark.asyncio
    async def test_not_found_during_delete_is_caught(self) -> None:
        timer = _make_timer(
            id_=1, deadline_seconds_from_now=-1.0, channel_id="1", message_id="2"
        )
        repo = MagicMock()
        repo.list_pending = AsyncMock(side_effect=[[timer], []])
        repo.mark_expired = AsyncMock()

        bot = MagicMock()
        channel = MagicMock()
        # NotFound is a real discord exception that takes (response, message)
        channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(
                response=MagicMock(status=404, reason="Not Found"),
                message="message gone",
            )
        )
        bot.get_channel = MagicMock(return_value=channel)
        locks = SessionLocks()

        async def fake_sleep(_s: float) -> None:
            raise asyncio.CancelledError

        sweeper = RiposteSweeper(
            repo=repo,
            bot=bot,
            session_locks=locks,
            sleep=fake_sleep,
        )

        # Should NOT raise — error is caught and logged.
        with pytest.raises(asyncio.CancelledError):
            await sweeper._iterate_once()

        # mark_expired still called (row gets cleaned up even if Discord 404s)
        repo.mark_expired.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_forbidden_during_delete_is_caught(self) -> None:
        timer = _make_timer(
            id_=2, deadline_seconds_from_now=-1.0, channel_id="3", message_id="4"
        )
        repo = MagicMock()
        repo.list_pending = AsyncMock(side_effect=[[timer], []])
        repo.mark_expired = AsyncMock()

        bot = MagicMock()
        channel = MagicMock()
        channel.fetch_message = AsyncMock(
            side_effect=discord.Forbidden(
                response=MagicMock(status=403, reason="Forbidden"),
                message="no perms",
            )
        )
        bot.get_channel = MagicMock(return_value=channel)
        locks = SessionLocks()

        async def fake_sleep(_s: float) -> None:
            raise asyncio.CancelledError

        sweeper = RiposteSweeper(
            repo=repo,
            bot=bot,
            session_locks=locks,
            sleep=fake_sleep,
        )

        with pytest.raises(asyncio.CancelledError):
            await sweeper._iterate_once()

        # Even with Forbidden on delete, row still marked expired so it
        # doesn't loop forever.
        repo.mark_expired.assert_awaited_once_with(2)


# ── Test 12: SessionLocks acquired BEFORE mark_expired ───────────────────────


class TestSessionLockOrdering:
    @pytest.mark.asyncio
    async def test_lock_acquired_before_mark_expired(self) -> None:
        """The sweeper must acquire the session lock BEFORE calling mark_expired.

        Without this, a sweeper-vs-click race could double-handle a row.
        """
        timer = _make_timer(
            id_=7, deadline_seconds_from_now=-0.5, channel_id="abc", message_id="xyz"
        )
        repo = MagicMock()
        repo.list_pending = AsyncMock(side_effect=[[timer], []])

        ordering: list[str] = []

        # The shared lock — the same instance must be acquired by sweeper
        locks = SessionLocks()
        shared_lock = await locks.acquire("riposte", "abc")
        original_acquire = shared_lock.acquire

        async def trace_acquire(*args, **kwargs):
            ordering.append("lock_acquired")
            return await original_acquire(*args, **kwargs)

        shared_lock.acquire = trace_acquire  # type: ignore[method-assign]

        async def trace_mark_expired(_id: int) -> None:
            ordering.append("mark_expired_called")

        repo.mark_expired = trace_mark_expired

        bot = _make_bot_with_channel()

        async def fake_sleep(_s: float) -> None:
            raise asyncio.CancelledError

        sweeper = RiposteSweeper(
            repo=repo,
            bot=bot,
            session_locks=locks,
            sleep=fake_sleep,
        )

        with pytest.raises(asyncio.CancelledError):
            await sweeper._iterate_once()

        # lock acquired BEFORE mark_expired called
        assert "lock_acquired" in ordering, f"lock was never acquired: {ordering}"
        assert "mark_expired_called" in ordering, f"mark_expired never called: {ordering}"
        assert ordering.index("lock_acquired") < ordering.index("mark_expired_called"), (
            f"Lock must be acquired BEFORE mark_expired; ordering: {ordering}"
        )


# ── Test 13: Cooperative cancellation re-raises CancelledError ───────────────


class TestCancellation:
    @pytest.mark.asyncio
    async def test_cancellation_re_raises_cleanly(self) -> None:
        repo = MagicMock()
        # list_pending raises CancelledError
        repo.list_pending = AsyncMock(side_effect=asyncio.CancelledError)
        repo.mark_expired = AsyncMock()

        bot = MagicMock()
        locks = SessionLocks()
        sweeper = RiposteSweeper(repo=repo, bot=bot, session_locks=locks)

        with pytest.raises(asyncio.CancelledError):
            await sweeper._iterate_once()


# ── Test 14: Unexpected exception caught with defensive sleep ────────────────


class TestUnexpectedExceptionResilience:
    @pytest.mark.asyncio
    async def test_repo_exception_caught_and_defensive_sleep(self) -> None:
        repo = MagicMock()
        # First call raises; loop must catch and continue (via defensive sleep)
        repo.list_pending = AsyncMock(side_effect=RuntimeError("oh no"))
        repo.mark_expired = AsyncMock()

        bot = MagicMock()
        locks = SessionLocks()

        sleep_calls: list[float] = []

        async def fake_sleep(s: float) -> None:
            sleep_calls.append(s)
            raise asyncio.CancelledError

        sweeper = RiposteSweeper(
            repo=repo,
            bot=bot,
            session_locks=locks,
            default_sleep_s=30.0,
            sleep=fake_sleep,
        )

        with pytest.raises(asyncio.CancelledError):
            await sweeper._iterate_once()

        # The defensive sleep is 1.0s (per plan), not the default 30.0s.
        assert sleep_calls == [1.0], (
            f"Expected defensive 1.0s sleep after repo exception, got {sleep_calls}"
        )


# ── Test 15: full background-task run+stop drains cleanly ────────────────────


class TestBackgroundTaskDrains:
    @pytest.mark.asyncio
    async def test_start_then_stop_completes_within_1s(self) -> None:
        """End-to-end: actual start() + actual stop() (no _iterate_once mock)."""
        repo = MagicMock()
        repo.list_pending = AsyncMock(return_value=[])
        repo.mark_expired = AsyncMock()

        bot = MagicMock()
        locks = SessionLocks()

        # Use a real (short) default sleep so the loop parks briefly and we
        # can stop quickly.
        sweeper = RiposteSweeper(
            repo=repo,
            bot=bot,
            session_locks=locks,
            default_sleep_s=10.0,
            min_sleep_s=0.05,
        )
        await sweeper.start()
        # Let the loop hit list_pending at least once
        await asyncio.sleep(0.05)
        # Stop and verify it drains under 1s
        await asyncio.wait_for(sweeper.stop(), timeout=1.0)
        assert sweeper.is_running() is False
