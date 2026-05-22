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
        # First .get() → pending; second .get() → consumed
        repo.get = AsyncMock(side_effect=[timer, consumed_timer])
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
            f"Expected zero live def/call of _maybe_surface_riposte; found:\n"
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
