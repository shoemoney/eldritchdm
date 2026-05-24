"""
Tests for the RiposteButton.callback flow + handle_riposte_click branching
(Phase 5 Plan 01 Task 2).

Covers (per plan):
  - Wrong-user click → INVALID_ACTION warning, no state mutation.
  - Click on expired row → RIPOSTE_EXPIRED, no combat_action.
  - Click on deadline-passed pending row → self-expire + RIPOSTE_EXPIRED.
  - Successful click → combat_action + mark_consumed_with_round + delete + ✅.
  - Concurrent clicks → only one mark_consumed_with_round (status-check
    correctness; Plan 02 hardens via lock).
  - AttackButton._maybe_surface_riposte deletion gate.
  - WarningKind.RIPOSTE_EXPIRED exists and dispatches.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from eldritch_dm.bot.warnings import WarningKind
from eldritch_dm.gameplay.reactions import handle_riposte_click
from eldritch_dm.gameplay.session_locks import SessionLocks
from eldritch_dm.persistence.models import RiposteStatus, RiposteTimer

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_timer(
    *,
    id_: int = 1,
    status: RiposteStatus = RiposteStatus.PENDING,
    deadline_ts: datetime | None = None,
    user_id: str = "999",
    weapon_used: str | None = "longsword",
    monster_uuid: str | None = "goblin-001",
) -> RiposteTimer:
    if deadline_ts is None:
        deadline_ts = datetime.now(UTC) + timedelta(seconds=8)
    return RiposteTimer(
        id=id_,
        channel_id="ch-1",
        character_id="hero-001",
        user_id=user_id,
        message_id="msg-1",
        custom_id=f"riposte:{id_}:{user_id}",
        deadline_ts=deadline_ts,
        status=status,
        created_at=datetime.now(UTC),
        monster_uuid=monster_uuid,
        weapon_used=weapon_used,
    )


def _make_interaction(user_id: int = 999) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = user_id

    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.channel = AsyncMock()
    interaction.channel.fetch_message = AsyncMock(side_effect=Exception("no msg"))
    return interaction


async def _round_provider(_channel_id: str) -> int:
    return 1


# ── Test 26: Wrong-user click ────────────────────────────────────────────────


class TestWrongUserRejected:
    @pytest.mark.asyncio
    async def test_wrong_user_warning_and_no_mutation(self) -> None:
        repo = MagicMock()
        repo.get = AsyncMock(return_value=_make_timer())
        repo.mark_consumed_with_round = AsyncMock()
        repo.mark_expired = AsyncMock()
        repo.mark_cancelled = AsyncMock()

        interaction = _make_interaction(user_id=42)  # NOT 999

        warning_sender = AsyncMock()

        with patch(
            "eldritch_dm.gameplay.reactions.mcp_tools.combat_action",
            new=AsyncMock(),
        ) as mock_ca:
            await handle_riposte_click(
                interaction=interaction,
                timer_id=1,
                expected_user_id=999,
                repo=repo,
                mcp=MagicMock(),
                rate_limiter=None,
                session_locks=SessionLocks(),
                current_round_provider=_round_provider,
                warning_sender=warning_sender,
                invalid_action_kind=WarningKind.INVALID_ACTION,
                riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
            )

        warning_sender.assert_awaited_once()
        kind = warning_sender.call_args.args[1]
        assert kind == WarningKind.INVALID_ACTION
        mock_ca.assert_not_called()
        repo.mark_consumed_with_round.assert_not_called()


# ── Test 27: Click on expired row ────────────────────────────────────────────


class TestExpiredRowClick:
    @pytest.mark.asyncio
    async def test_expired_status_emits_riposte_expired(self) -> None:
        repo = MagicMock()
        repo.get = AsyncMock(return_value=_make_timer(status=RiposteStatus.EXPIRED))
        repo.mark_consumed_with_round = AsyncMock()

        interaction = _make_interaction()
        warning_sender = AsyncMock()

        with patch(
            "eldritch_dm.gameplay.reactions.mcp_tools.combat_action",
            new=AsyncMock(),
        ) as mock_ca:
            await handle_riposte_click(
                interaction=interaction,
                timer_id=1,
                expected_user_id=999,
                repo=repo,
                mcp=MagicMock(),
                rate_limiter=None,
                session_locks=SessionLocks(),
                current_round_provider=_round_provider,
                warning_sender=warning_sender,
                invalid_action_kind=WarningKind.INVALID_ACTION,
                riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
            )

        warning_sender.assert_awaited_once()
        assert warning_sender.call_args.args[1] == WarningKind.RIPOSTE_EXPIRED
        mock_ca.assert_not_called()


# ── Test 28: Late click on pending row → self-expire ─────────────────────────


class TestLatePendingClick:
    @pytest.mark.asyncio
    async def test_deadline_passed_self_expires(self) -> None:
        # Pending but deadline already in the past
        late_deadline = datetime.now(UTC) - timedelta(seconds=1)
        timer = _make_timer(deadline_ts=late_deadline)

        repo = MagicMock()
        repo.get = AsyncMock(return_value=timer)
        repo.mark_expired = AsyncMock()
        repo.mark_consumed_with_round = AsyncMock()

        interaction = _make_interaction()
        warning_sender = AsyncMock()

        with patch(
            "eldritch_dm.gameplay.reactions.mcp_tools.combat_action",
            new=AsyncMock(),
        ) as mock_ca:
            await handle_riposte_click(
                interaction=interaction,
                timer_id=1,
                expected_user_id=999,
                repo=repo,
                mcp=MagicMock(),
                rate_limiter=None,
                session_locks=SessionLocks(),
                current_round_provider=_round_provider,
                warning_sender=warning_sender,
                invalid_action_kind=WarningKind.INVALID_ACTION,
                riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
            )

        repo.mark_expired.assert_awaited_once_with(1)
        mock_ca.assert_not_called()
        warning_sender.assert_awaited_once()
        assert warning_sender.call_args.args[1] == WarningKind.RIPOSTE_EXPIRED


# ── Test 29: Successful click ─────────────────────────────────────────────────


class TestSuccessfulClick:
    @pytest.mark.asyncio
    async def test_combat_action_then_mark_consumed_then_followup(self) -> None:
        timer = _make_timer()

        repo = MagicMock()
        repo.get = AsyncMock(return_value=timer)
        repo.mark_consumed_with_round = AsyncMock()
        repo.mark_expired = AsyncMock()

        rate_limiter = MagicMock()
        rate_limiter.acquire = AsyncMock()

        interaction = _make_interaction()
        warning_sender = AsyncMock()

        async def round_5(_ch_id: str) -> int:
            return 5

        with patch(
            "eldritch_dm.gameplay.reactions.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Hit!** Thorin hits Goblin."),
        ) as mock_ca:
            await handle_riposte_click(
                interaction=interaction,
                timer_id=1,
                expected_user_id=999,
                repo=repo,
                mcp=MagicMock(),
                rate_limiter=rate_limiter,
                session_locks=SessionLocks(),
                current_round_provider=round_5,
                warning_sender=warning_sender,
                invalid_action_kind=WarningKind.INVALID_ACTION,
                riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
            )

        rate_limiter.acquire.assert_awaited_once_with("ch-1")
        mock_ca.assert_awaited_once()
        ca_kwargs = mock_ca.call_args.kwargs
        assert ca_kwargs["action"] == "attack"
        assert ca_kwargs["attacker"] == "hero-001"
        assert ca_kwargs["target"] == "goblin-001"
        assert ca_kwargs["weapon_or_spell"] == "longsword"

        repo.mark_consumed_with_round.assert_awaited_once_with(1, 5)
        # No warning sent on success
        warning_sender.assert_not_called()
        # ephemeral followup with ✅ emoji
        interaction.followup.send.assert_awaited()
        followup_content = interaction.followup.send.call_args.kwargs.get("content", "")
        assert "Riposte" in followup_content


# ── Test 30: Concurrent clicks → only one mark_consumed_with_round ────────────


class TestConcurrentClicks:
    @pytest.mark.asyncio
    async def test_second_concurrent_click_sees_consumed_status(self) -> None:
        """Status-check correctness path; Plan 02 hardens this via per-channel lock."""
        # We simulate sequential rather than truly racing for determinism — the
        # second call sees status='consumed' on the second .get() and emits
        # RIPOSTE_EXPIRED.
        timer = _make_timer()
        consumed_timer = _make_timer(status=RiposteStatus.CONSUMED)

        repo = MagicMock()
        # Plan 02: handle_riposte_click does TWO .get() calls per click —
        # one pre-lock (to discover channel_id) and one under-lock (the
        # authoritative status read). So we need 4 .get() returns total:
        #   click 1: pre-lock pending, under-lock pending → consumes
        #   click 2: pre-lock consumed,  under-lock consumed → RIPOSTE_EXPIRED
        repo.get = AsyncMock(
            side_effect=[timer, timer, consumed_timer, consumed_timer]
        )
        repo.mark_consumed_with_round = AsyncMock()
        repo.mark_expired = AsyncMock()

        rate_limiter = MagicMock()
        rate_limiter.acquire = AsyncMock()

        warning_sender = AsyncMock()

        with patch(
            "eldritch_dm.gameplay.reactions.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Hit!**"),
        ):
            # First click — happy path
            interaction_1 = _make_interaction()
            await handle_riposte_click(
                interaction=interaction_1,
                timer_id=1,
                expected_user_id=999,
                repo=repo,
                mcp=MagicMock(),
                rate_limiter=rate_limiter,
                session_locks=SessionLocks(),
                current_round_provider=_round_provider,
                warning_sender=warning_sender,
                invalid_action_kind=WarningKind.INVALID_ACTION,
                riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
            )

            # Second click — sees consumed status
            interaction_2 = _make_interaction()
            await handle_riposte_click(
                interaction=interaction_2,
                timer_id=1,
                expected_user_id=999,
                repo=repo,
                mcp=MagicMock(),
                rate_limiter=rate_limiter,
                session_locks=SessionLocks(),
                current_round_provider=_round_provider,
                warning_sender=warning_sender,
                invalid_action_kind=WarningKind.INVALID_ACTION,
                riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
            )

        # Exactly one mark_consumed
        assert repo.mark_consumed_with_round.await_count == 1
        # Second click emitted a warning
        assert warning_sender.await_count == 1
        assert warning_sender.call_args.args[1] == WarningKind.RIPOSTE_EXPIRED


# ── Tests 31, 32: AttackButton._maybe_surface_riposte deletion ───────────────


class TestSeamDeletion:
    def test_grep_dynamic_items_zero_non_comment_hits(self) -> None:
        """The deletion gate per D-A."""
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "src" / "eldritch_dm" / "bot" / "dynamic_items.py"
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        # Count any line that contains the symbol AND is not a comment/docstring line
        live_hits = []
        for ln in lines:
            stripped = ln.strip()
            if "_maybe_surface_riposte" not in stripped:
                continue
            # Skip docstring-like comments / standalone bare comments
            if (
                stripped.startswith("#")
                or stripped.startswith('"""')
                or stripped.startswith("'''")
                or stripped.startswith("The Phase 4 stub seam")
                or stripped.startswith("Phase 5 Plan 01")
            ):
                continue
            # Heuristic: live code line (def, await, .) — if it has any of those tokens it's live
            if any(tok in ln for tok in ("def ", "await ", ".", "(", ")")):
                # But also ignore lines inside docstrings — the file uses triple-quoted strings
                # for class/module docstrings. We approximate by checking whether the line text
                # appears WITHIN the closest enclosing docstring boundaries; the simplest
                # heuristic: if the line is indented and does not start with `await`/`def`/`async`
                # and does not have leading code keywords, treat as documentation.
                # Simpler: explicitly exclude doc lines we know about.
                if "DELETED" in ln or "Phase 4 stub seam" in ln:
                    continue
                live_hits.append(ln)
        assert not live_hits, (
            f"Expected 0 non-comment hits for _maybe_surface_riposte; "
            f"found {len(live_hits)}:\n" + "\n".join(live_hits)
        )

    def test_grep_bot_dir_no_executable_callsites(self) -> None:
        """No actual call/def of _maybe_surface_riposte anywhere in src/eldritch_dm/bot/."""
        from pathlib import Path

        bot_dir = Path(__file__).resolve().parents[2] / "src" / "eldritch_dm" / "bot"
        live = []
        for path in bot_dir.rglob("*.py"):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if "_maybe_surface_riposte" not in line:
                    continue
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if (
                    "def _maybe_surface_riposte" in line
                    or "await self._maybe_surface_riposte" in line
                    or "self._maybe_surface_riposte(" in line
                ):
                    live.append(f"{path}:{i}:{line}")
        assert not live, (
            "Expected zero live def/call of _maybe_surface_riposte; found:\n"
            + "\n".join(live)
        )


# ── Test 34: WarningKind.RIPOSTE_EXPIRED dispatch ─────────────────────────────


class TestRiposteExpiredWarningKind:
    def test_warning_kind_value(self) -> None:
        assert WarningKind.RIPOSTE_EXPIRED == "riposte_expired"

    @pytest.mark.asyncio
    async def test_send_warning_dispatches_ephemeral(self) -> None:
        from eldritch_dm.bot.warnings import send_warning

        interaction = MagicMock()
        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()

        await send_warning(interaction, WarningKind.RIPOSTE_EXPIRED)

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        # message text contains a riposte hint
        assert "riposte" in kwargs.get("content", "").lower()


# ── Test 16 (Plan 02): Concurrent clicks — deterministic under shared lock ──


class TestPlan02ConcurrentClicksDeterministic:
    """Plan 02: with the shared SessionLocks lock, two concurrent clicks for
    the same timer_id (fired via asyncio.gather) are deterministic — exactly
    ONE completes mark_consumed_with_round, the other observes status='consumed'
    inside the lock and emits RIPOSTE_EXPIRED.

    Plan 01 shipped a status-check correctness path; Plan 02 hardens it so
    the test outcome is deterministic (not race-lucky).
    """

    @pytest.mark.asyncio
    async def test_concurrent_clicks_one_winner(self) -> None:
        timer = _make_timer()
        consumed_timer = _make_timer(status=RiposteStatus.CONSUMED)

        # First .get (initial pre-lock) for both clicks returns pending.
        # Once one click enters the lock and calls mark_consumed, the OTHER
        # click's second .get (under the lock) sees consumed_timer.
        repo = MagicMock()
        get_call_count = {"n": 0}
        mark_consumed_done = asyncio.Event()

        async def get_side_effect(_id: int):
            get_call_count["n"] += 1
            # 1st + 2nd get calls (pre-lock for both clicks) → pending
            # 3rd get (the FIRST under-lock re-read for the winner) → pending
            # 4th get (the SECOND under-lock re-read for the loser) → consumed
            if mark_consumed_done.is_set():
                return consumed_timer
            return timer

        repo.get = AsyncMock(side_effect=get_side_effect)
        repo.mark_expired = AsyncMock()

        async def mark_consumed_impl(_id: int, _round: int) -> None:
            mark_consumed_done.set()

        repo.mark_consumed_with_round = AsyncMock(side_effect=mark_consumed_impl)

        rate_limiter = MagicMock()
        rate_limiter.acquire = AsyncMock()

        warning_sender = AsyncMock()
        # Shared SessionLocks across both clicks (THIS is the critical wiring)
        shared_locks = SessionLocks()

        with patch(
            "eldritch_dm.gameplay.reactions.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Hit!**"),
        ):
            async def one_click():
                interaction = _make_interaction()
                await handle_riposte_click(
                    interaction=interaction,
                    timer_id=1,
                    expected_user_id=999,
                    repo=repo,
                    mcp=MagicMock(),
                    rate_limiter=rate_limiter,
                    session_locks=shared_locks,
                    current_round_provider=_round_provider,
                    warning_sender=warning_sender,
                    invalid_action_kind=WarningKind.INVALID_ACTION,
                    riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
                )

            await asyncio.gather(one_click(), one_click())

        # Exactly ONE mark_consumed_with_round under deterministic lock
        assert repo.mark_consumed_with_round.await_count == 1
        # The other click sent a RIPOSTE_EXPIRED warning
        assert warning_sender.await_count == 1
        assert warning_sender.call_args.args[1] == WarningKind.RIPOSTE_EXPIRED


# ── Test 17 (Plan 02): Race with sweeper — click wins, sweeper no-ops ────────


class TestPlan02SweeperRaceLockOrdering:
    """Plan 02: with the shared SessionLocks, a sweeper that tries to
    mark_expired while a click is in-flight will WAIT for the click's lock
    release. Then the sweeper's mark_expired SQL (WHERE status='pending')
    becomes a 0-row no-op since the click already flipped status to consumed.
    """

    @pytest.mark.asyncio
    async def test_sweeper_waits_then_observes_consumed(self) -> None:
        # The click writes mark_consumed first; then a "sweeper" coroutine
        # acquires the same lock and calls mark_expired (which is conditional
        # on still-pending, so it's a 0-row UPDATE — semantic no-op).
        timer = _make_timer()
        consumed_timer = _make_timer(status=RiposteStatus.CONSUMED)

        click_done = asyncio.Event()
        sweeper_waited = {"flag": False}

        repo = MagicMock()
        get_calls = {"n": 0}

        async def get_side_effect(_id: int):
            get_calls["n"] += 1
            # Click's initial pre-lock get → pending
            # Click's under-lock re-read get → pending
            # (sweeper doesn't call .get; it acts on list_pending elsewhere)
            return timer if not click_done.is_set() else consumed_timer

        repo.get = AsyncMock(side_effect=get_side_effect)

        async def mark_consumed_impl(_id: int, _round: int) -> None:
            # Hold the click in the critical section briefly so the sweeper
            # has time to enqueue waiting on the lock.
            await asyncio.sleep(0.02)
            click_done.set()

        repo.mark_consumed_with_round = AsyncMock(side_effect=mark_consumed_impl)
        repo.mark_expired = AsyncMock()

        rate_limiter = MagicMock()
        rate_limiter.acquire = AsyncMock()

        warning_sender = AsyncMock()
        shared_locks = SessionLocks()

        async def fake_sweeper_run() -> None:
            # Wait a bit so the click acquires the lock first
            await asyncio.sleep(0.005)
            async with shared_locks.lock_for("riposte", "ch-1"):
                # If we get here AFTER the click has flipped status, the
                # mark_expired UPDATE is a 0-row no-op (status no longer
                # 'pending'). This is the belt-and-suspenders correctness.
                sweeper_waited["flag"] = click_done.is_set()
                await repo.mark_expired(1)

        with patch(
            "eldritch_dm.gameplay.reactions.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Hit!**"),
        ):
            interaction = _make_interaction()
            await asyncio.gather(
                handle_riposte_click(
                    interaction=interaction,
                    timer_id=1,
                    expected_user_id=999,
                    repo=repo,
                    mcp=MagicMock(),
                    rate_limiter=rate_limiter,
                    session_locks=shared_locks,
                    current_round_provider=_round_provider,
                    warning_sender=warning_sender,
                    invalid_action_kind=WarningKind.INVALID_ACTION,
                    riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
                ),
                fake_sweeper_run(),
            )

        # Click completed first (mark_consumed called)
        assert repo.mark_consumed_with_round.await_count == 1
        # Sweeper waited for the click's lock release THEN called mark_expired
        # (which is a 0-row no-op under the conditional SQL).
        assert sweeper_waited["flag"] is True, (
            "Sweeper must have waited for the click's lock release "
            "(observed click_done before entering its critical section)."
        )
        repo.mark_expired.assert_awaited_once()
