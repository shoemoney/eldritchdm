"""
Tests for eldritch_dm.bot.warnings — ephemeral warning helper.

Covers:
  - send_warning formats correctly for specific WarningKind
  - parametric: all 5 kinds call followup.send exactly once with ephemeral=True
  - missing ctx key raises ValueError mentioning the key
  - WarningKind has exactly 5 members with _COPY entry for each
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.bot.warnings import WarningKind, _COPY, send_warning


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_interaction() -> discord.Interaction:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=True)
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


# ── Test 1: NOT_YOUR_TURN with actor_name ──────────────────────────────────────


class TestNotYourTurn:
    @pytest.mark.asyncio
    async def test_not_your_turn_formats_actor_name(self) -> None:
        interaction = _make_interaction()
        await send_warning(interaction, WarningKind.NOT_YOUR_TURN, actor_name="Thorin")

        interaction.followup.send.assert_awaited_once()
        call_kwargs = interaction.followup.send.call_args
        content = call_kwargs.kwargs.get("content") or (
            call_kwargs.args[0] if call_kwargs.args else ""
        )
        assert "Thorin" in content
        assert "not your turn" in content.lower()
        assert call_kwargs.kwargs.get("ephemeral") is True


# ── Test 2: all 5 kinds call followup.send once with ephemeral=True ───────────


class TestAllKindsCallFollowup:
    @pytest.mark.parametrize(
        "kind, ctx",
        [
            (WarningKind.NOT_YOUR_TURN, {"actor_name": "Alice"}),
            (WarningKind.RIPOSTE_EXPIRED, {}),
            (WarningKind.DM_OFFLINE, {"failure_count": 3}),
            (WarningKind.INVALID_ACTION, {"reason": "out of range"}),
            (WarningKind.RATE_LIMITED, {"retry_after": 5}),
        ],
    )
    @pytest.mark.asyncio
    async def test_each_kind_calls_followup_once(self, kind, ctx) -> None:
        interaction = _make_interaction()
        await send_warning(interaction, kind, **ctx)

        interaction.followup.send.assert_awaited_once()
        call_kwargs = interaction.followup.send.call_args
        assert call_kwargs.kwargs.get("ephemeral") is True

    @pytest.mark.parametrize(
        "kind, ctx",
        [
            (WarningKind.NOT_YOUR_TURN, {"actor_name": "Alice"}),
            (WarningKind.RIPOSTE_EXPIRED, {}),
            (WarningKind.DM_OFFLINE, {"failure_count": 3}),
            (WarningKind.INVALID_ACTION, {"reason": "out of range"}),
            (WarningKind.RATE_LIMITED, {"retry_after": 5}),
        ],
    )
    @pytest.mark.asyncio
    async def test_each_kind_content_is_string(self, kind, ctx) -> None:
        interaction = _make_interaction()
        await send_warning(interaction, kind, **ctx)

        call_kwargs = interaction.followup.send.call_args
        content = call_kwargs.kwargs.get("content") or (
            call_kwargs.args[0] if call_kwargs.args else None
        )
        assert isinstance(content, str)
        assert len(content) > 0


# ── Test 3: missing ctx key raises ValueError ──────────────────────────────────


class TestMissingCtxRaisesValueError:
    @pytest.mark.asyncio
    async def test_missing_actor_name_raises(self) -> None:
        interaction = _make_interaction()
        with pytest.raises(ValueError, match="actor_name"):
            await send_warning(interaction, WarningKind.NOT_YOUR_TURN)
        # followup.send must NOT have been called
        interaction.followup.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_failure_count_raises(self) -> None:
        interaction = _make_interaction()
        with pytest.raises(ValueError):
            await send_warning(interaction, WarningKind.DM_OFFLINE)

    @pytest.mark.asyncio
    async def test_missing_reason_raises(self) -> None:
        interaction = _make_interaction()
        with pytest.raises(ValueError):
            await send_warning(interaction, WarningKind.INVALID_ACTION)

    @pytest.mark.asyncio
    async def test_missing_retry_after_raises(self) -> None:
        interaction = _make_interaction()
        with pytest.raises(ValueError):
            await send_warning(interaction, WarningKind.RATE_LIMITED)


# ── Test 4: enum completeness ─────────────────────────────────────────────────


class TestWarningKindEnum:
    def test_exactly_five_members(self) -> None:
        assert len(WarningKind) == 5

    def test_all_members_in_copy_dict(self) -> None:
        for kind in WarningKind:
            assert kind in _COPY, f"WarningKind.{kind.name} missing from _COPY dict"

    def test_expected_member_names(self) -> None:
        names = {m.name for m in WarningKind}
        assert names == {
            "NOT_YOUR_TURN",
            "RIPOSTE_EXPIRED",
            "DM_OFFLINE",
            "INVALID_ACTION",
            "RATE_LIMITED",
        }
