"""Tests for BudgetOwnerNotifier (Phase 22 / OPQOL-02).

Cover all 10 behaviors:
  1. owner_id=None → no-op
  2-4. DM sent for each of the 3 event types
  5. rate limit blocks second-within-window
  6. rate-limit buckets are per-event-type
  7. clock advance unblocks
  8. discord.Forbidden swallowed; bucket NOT burned
  9. generic Exception swallowed
  10. attach/detach degraded_mode wiring
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from eldritch_dm.observability import budget_dm as bdm_mod
from eldritch_dm.observability.budget_dm import BudgetOwnerNotifier
from eldritch_dm.observability.degraded_mode import DegradedModeState


def _make_bot() -> MagicMock:
    """Build a Discord-bot-shaped mock: bot.fetch_user → user → user.send."""
    bot = MagicMock()
    user = MagicMock()
    user.send = AsyncMock(return_value=None)
    bot.fetch_user = AsyncMock(return_value=user)
    return bot


def _clock_factory(start: float = 0.0):
    """Return (clock_callable, advance_fn) sharing a mutable ref."""
    state = {"t": start}

    def clock() -> float:
        return state["t"]

    def advance(dt: float) -> None:
        state["t"] += dt

    return clock, advance


# ── 1: owner_id None → noop ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_owner_id_none_is_noop() -> None:
    bot = _make_bot()
    n = BudgetOwnerNotifier(bot=bot, owner_id=None)
    await n.notify_async("budget_breached", "any reason")
    await n.notify_async("degraded_mode_entered", "any reason")
    await n.notify_async("degraded_mode_exited", None)
    bot.fetch_user.assert_not_called()


# ── 2-4: DM sent for each event type ────────────────────────────────────────


@pytest.mark.asyncio
async def test_dm_sent_on_budget_breached() -> None:
    bot = _make_bot()
    n = BudgetOwnerNotifier(bot=bot, owner_id=12345)
    await n.notify_async("budget_breached", "spend $3.01 > cap $2.00")
    bot.fetch_user.assert_awaited_once_with(12345)
    user = await bot.fetch_user(12345)  # same mock instance
    sent_msg = user.send.await_args.args[0]
    assert "daily LLM budget breached" in sent_msg
    assert "spend $3.01 > cap $2.00" in sent_msg


@pytest.mark.asyncio
async def test_dm_sent_on_degraded_mode_entered() -> None:
    bot = _make_bot()
    n = BudgetOwnerNotifier(bot=bot, owner_id=12345)
    await n.notify_async("degraded_mode_entered", "mcp_circuit_open")
    user = await bot.fetch_user(12345)
    sent_msg = user.send.await_args.args[0]
    assert "entered degraded mode" in sent_msg
    assert "mcp_circuit_open" in sent_msg


@pytest.mark.asyncio
async def test_dm_sent_on_degraded_mode_exited() -> None:
    bot = _make_bot()
    n = BudgetOwnerNotifier(bot=bot, owner_id=12345)
    await n.notify_async("degraded_mode_exited", None)
    user = await bot.fetch_user(12345)
    sent_msg = user.send.await_args.args[0]
    assert "exited degraded mode" in sent_msg


# ── 5: rate limit blocks second within window ───────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_blocks_second_within_hour() -> None:
    bot = _make_bot()
    clock, _advance = _clock_factory()
    n = BudgetOwnerNotifier(
        bot=bot, owner_id=42, rate_limit_window_s=3600.0, clock=clock
    )
    await n.notify_async("budget_breached", "first")
    await n.notify_async("budget_breached", "second")
    # fetch_user should have been awaited exactly ONCE
    assert bot.fetch_user.await_count == 1


# ── 6: rate-limit buckets are per-event-type ────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_per_event_type_isolated() -> None:
    bot = _make_bot()
    clock, _advance = _clock_factory()
    n = BudgetOwnerNotifier(bot=bot, owner_id=42, clock=clock)
    await n.notify_async("budget_breached", "x")
    await n.notify_async("degraded_mode_entered", "y")
    await n.notify_async("degraded_mode_exited", None)
    # All three should have sent — separate buckets.
    assert bot.fetch_user.await_count == 3


# ── 7: clock advance unblocks ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_clock_advance_unblocks() -> None:
    bot = _make_bot()
    clock, advance = _clock_factory()
    n = BudgetOwnerNotifier(
        bot=bot, owner_id=42, rate_limit_window_s=100.0, clock=clock
    )
    await n.notify_async("budget_breached", "first")
    advance(101.0)
    await n.notify_async("budget_breached", "second")
    assert bot.fetch_user.await_count == 2


# ── 8: discord.Forbidden swallowed; bucket NOT burned ───────────────────────


@pytest.mark.asyncio
async def test_discord_forbidden_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeForbidden(Exception):
        pass

    monkeypatch.setattr(bdm_mod, "Forbidden", FakeForbidden)

    bot = _make_bot()
    user = await bot.fetch_user(99)  # prime the mock chain
    # Patch the SAME mock that fetch_user returns so user.send raises.
    # Reset the call count after the priming call above.
    bot.fetch_user.reset_mock()
    user.send = AsyncMock(side_effect=FakeForbidden("DMs disabled"))

    clock, _advance = _clock_factory()
    n = BudgetOwnerNotifier(bot=bot, owner_id=99, clock=clock)
    # No raise.
    await n.notify_async("budget_breached", "spend over cap")
    assert bot.fetch_user.await_count == 1

    # Bucket NOT burned: a SECOND attempt should still go through (and also
    # be swallowed). We assert by checking fetch_user is awaited again.
    await n.notify_async("budget_breached", "spend over cap again")
    assert bot.fetch_user.await_count == 2


# ── 9: generic Exception swallowed ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_generic_exception_swallowed() -> None:
    bot = _make_bot()
    user = await bot.fetch_user(7)
    bot.fetch_user.reset_mock()
    user.send = AsyncMock(side_effect=RuntimeError("network blew up"))

    n = BudgetOwnerNotifier(bot=bot, owner_id=7)
    # No raise.
    await n.notify_async("degraded_mode_entered", "boom")
    assert bot.fetch_user.await_count == 1


# ── 10: attach / detach degraded-mode wiring ────────────────────────────────


@pytest.mark.asyncio
async def test_attach_detach_degraded_mode_callbacks() -> None:
    bot = _make_bot()
    state = DegradedModeState()
    # Avoid scheduling onto a non-existent loop — capture events synchronously
    # via a notify-monkeypatch instead of relying on call_soon_threadsafe.
    events: list[tuple[str, str | None]] = []
    n = BudgetOwnerNotifier(bot=bot, owner_id=42)
    n.notify = lambda event, reason=None: events.append((event, reason))  # type: ignore[method-assign]

    n.attach_to_degraded_mode(state)
    state.trip("oracle_timeout")
    assert events == [("degraded_mode_entered", "oracle_timeout")]

    state.recover()
    assert events == [
        ("degraded_mode_entered", "oracle_timeout"),
        ("degraded_mode_exited", None),
    ]

    # detach → no further events.
    n.detach_from_degraded_mode(state)
    state.trip("another_reason")
    assert len(events) == 2  # unchanged
