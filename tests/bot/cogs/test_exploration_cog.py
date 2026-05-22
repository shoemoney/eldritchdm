"""
Phase 4 tests for ExplorationCog + DeclareActionModal.

Tests cover:
  - ExplorationCog.render_room_for_channel: posts embed + registers coalescer
  - ExplorationCog.update_room_for_channel: calls coalescer.update
  - ExplorationCog.on_resolved: only updates when EXPLORATION state
  - ExplorationCog.on_state_change: EXPLORATION→COMBAT closes coalescer
  - DeclareActionModal.on_submit: sanitize → PlayerIntent → BatchCoordinator
  - DeclareActionModal.on_submit: flushed vs pending followup

Isolation: I/O replaced with AsyncMock / MagicMock; no Discord gateway.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from eldritch_dm.bot.cogs.exploration import DeclareActionModal, ExplorationCog
from eldritch_dm.gameplay.exploration_batch import SubmitResult
from eldritch_dm.persistence.models import ChannelSession, ChannelState

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_channel_session(
    channel_id: str = "100",
    state: ChannelState = ChannelState.EXPLORATION,
) -> ChannelSession:
    return ChannelSession(
        channel_id=channel_id,
        campaign_name="TestCamp",
        claudmaster_session_id="sess-xyz",
        dm20_party_token=None,
        state=state,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )


def _make_bot(session=None):
    bot = MagicMock()
    bot.settings = MagicMock()
    bot.settings.embed_edit_rate_limit = 1.0
    cs_repo = AsyncMock()
    cs_repo.get.return_value = session
    bot.channel_sessions = cs_repo

    budget = MagicMock()
    budget.acquire = AsyncMock()
    bot.get_channel_edit_budget = MagicMock(return_value=budget)

    batch_coord = AsyncMock()
    bot.batch_coordinator = batch_coord

    orchestrator = MagicMock()
    orchestrator.register_resolution_callback = MagicMock()
    orchestrator.register_state_change_callback = MagicMock()
    bot.orchestrator = orchestrator

    return bot


def _make_channel(channel_id: int = 100):
    channel = AsyncMock()
    channel.id = channel_id
    msg = MagicMock(spec=discord.Message)
    msg.id = 9999
    channel.send = AsyncMock(return_value=msg)
    return channel


# ── ExplorationCog tests ──────────────────────────────────────────────────────


class TestExplorationCogRenderRoom:
    @pytest.mark.asyncio
    async def test_render_posts_embed_and_registers_coalescer(self):
        bot = _make_bot()
        cog = ExplorationCog(bot)
        channel = _make_channel()
        bot.get_channel = MagicMock(return_value=channel)

        with patch("eldritch_dm.bot.cogs.exploration.EmbedCoalescer") as mock_coalescer_cls:
            mock_coalescer = AsyncMock()
            mock_coalescer_cls.return_value = mock_coalescer

            await cog.render_room_for_channel(
                channel_id="100",
                room_title="Dark Hallway",
                narration="You see a flickering torch.",
                party_hp=[("Thorin", 20, 30)],
            )

        channel.send.assert_called_once()
        # Embed + view sent
        call_kwargs = channel.send.call_args[1]
        assert isinstance(call_kwargs["embed"], discord.Embed)
        assert isinstance(call_kwargs["view"], discord.ui.View)
        # Coalescer registered
        assert "100" in cog._coalescers

    @pytest.mark.asyncio
    async def test_render_closes_existing_coalescer(self):
        bot = _make_bot()
        cog = ExplorationCog(bot)
        channel = _make_channel()
        bot.get_channel = MagicMock(return_value=channel)

        old_coalescer = AsyncMock()
        old_coalescer.close = AsyncMock()
        cog._coalescers["100"] = old_coalescer

        with patch("eldritch_dm.bot.cogs.exploration.EmbedCoalescer"):
            await cog.render_room_for_channel(
                channel_id="100",
                room_title="New Room",
                narration="A fresh start.",
                party_hp=[],
            )

        old_coalescer.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_render_raises_on_missing_channel(self):
        bot = _make_bot()
        cog = ExplorationCog(bot)
        bot.get_channel = MagicMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await cog.render_room_for_channel(
                channel_id="999",
                room_title="Ghost Room",
                narration="...",
                party_hp=[],
            )


class TestExplorationCogUpdateRoom:
    @pytest.mark.asyncio
    async def test_update_calls_coalescer(self):
        bot = _make_bot()
        cog = ExplorationCog(bot)

        mock_coalescer = AsyncMock()
        mock_coalescer.update = AsyncMock()
        cog._coalescers["100"] = mock_coalescer

        await cog.update_room_for_channel(
            channel_id="100",
            room_title="Updated Room",
            narration="The scene shifts.",
            party_hp=[("Gimli", 18, 25)],
        )

        mock_coalescer.update.assert_called_once()
        embed = mock_coalescer.update.call_args[0][0]
        assert isinstance(embed, discord.Embed)

    @pytest.mark.asyncio
    async def test_update_no_coalescer_logs_warning(self):
        bot = _make_bot()
        cog = ExplorationCog(bot)
        # No coalescer registered — should log warning and return gracefully
        await cog.update_room_for_channel(
            channel_id="999",
            room_title="Ghost",
            narration="...",
            party_hp=[],
        )
        # Reaches here without exception


class TestExplorationCogCallbacks:
    @pytest.mark.asyncio
    async def test_on_resolved_updates_exploration_session(self):
        session = _make_channel_session(state=ChannelState.EXPLORATION)
        bot = _make_bot(session=session)
        cog = ExplorationCog(bot)

        mock_coalescer = AsyncMock()
        mock_coalescer.update = AsyncMock()
        cog._coalescers["100"] = mock_coalescer

        action = {"text": "You enter the crypt.", "location": "Ancient Crypt"}
        await cog.on_resolved(channel_id="100", action=action)

        mock_coalescer.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_resolved_ignores_non_exploration(self):
        session = _make_channel_session(state=ChannelState.COMBAT)
        bot = _make_bot(session=session)
        cog = ExplorationCog(bot)

        mock_coalescer = AsyncMock()
        mock_coalescer.update = AsyncMock()
        cog._coalescers["100"] = mock_coalescer

        await cog.on_resolved(channel_id="100", action={"text": "..."})

        mock_coalescer.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_resolved_ignores_no_session(self):
        bot = _make_bot(session=None)
        cog = ExplorationCog(bot)
        mock_coalescer = AsyncMock()
        cog._coalescers["100"] = mock_coalescer

        await cog.on_resolved(channel_id="100", action={"text": "..."})

        mock_coalescer.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_state_change_exploration_to_combat_closes_coalescer(self):
        bot = _make_bot()
        cog = ExplorationCog(bot)

        mock_coalescer = AsyncMock()
        mock_coalescer.close = AsyncMock()
        cog._coalescers["100"] = mock_coalescer

        await cog.on_state_change(
            channel_id="100",
            old_state=ChannelState.EXPLORATION,
            new_state=ChannelState.COMBAT,
        )

        mock_coalescer.close.assert_called_once()
        assert "100" not in cog._coalescers

    @pytest.mark.asyncio
    async def test_on_state_change_other_transition_no_close(self):
        bot = _make_bot()
        cog = ExplorationCog(bot)

        mock_coalescer = AsyncMock()
        mock_coalescer.close = AsyncMock()
        cog._coalescers["100"] = mock_coalescer

        # COMBAT→EXPLORATION should not close the exploration coalescer
        await cog.on_state_change(
            channel_id="100",
            old_state=ChannelState.COMBAT,
            new_state=ChannelState.EXPLORATION,
        )

        mock_coalescer.close.assert_not_called()


class TestExplorationCogLoad:
    @pytest.mark.asyncio
    async def test_cog_load_registers_callbacks(self):
        bot = _make_bot()
        cog = ExplorationCog(bot)
        await cog.cog_load()

        bot.orchestrator.register_resolution_callback.assert_called_once_with(cog.on_resolved)
        bot.orchestrator.register_state_change_callback.assert_called_once_with(cog.on_state_change)


# ── DeclareActionModal tests ──────────────────────────────────────────────────


def _make_modal_interaction(batch_coord=None):
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.user = MagicMock()
    interaction.user.id = 77
    interaction.user.display_name = "Legolas"
    return interaction


class TestDeclareActionModal:
    @pytest.mark.asyncio
    async def test_modal_defers_first(self):
        bot = MagicMock()
        batch_coord = AsyncMock()
        flush_result = SubmitResult(flushed=True, batch=None)
        batch_coord.submit = AsyncMock(return_value=flush_result)
        bot.batch_coordinator = batch_coord

        modal = DeclareActionModal(channel_id=100, bot=bot)
        modal.action_text._value = "I cast Fireball!"

        interaction = _make_modal_interaction()
        await modal.on_submit(interaction)

        interaction.response.defer.assert_called_once_with(thinking=True, ephemeral=True)

    @pytest.mark.asyncio
    async def test_modal_submits_sanitized_intent(self):
        bot = MagicMock()
        batch_coord = AsyncMock()
        flush_result = SubmitResult(flushed=False, batch=None)
        batch_coord.submit = AsyncMock(return_value=flush_result)
        batch_coord.get_deadline_seconds_remaining = MagicMock(return_value=25.0)
        bot.batch_coordinator = batch_coord

        modal = DeclareActionModal(channel_id=100, bot=bot)
        modal.action_text._value = "I search the room."

        interaction = _make_modal_interaction()
        await modal.on_submit(interaction)

        batch_coord.submit.assert_called_once()
        channel_id_arg, intent_arg = batch_coord.submit.call_args[0]
        assert channel_id_arg == "100"
        assert intent_arg.user_id == "77"
        assert "search the room" in intent_arg.sanitized_wrapped.lower()

    @pytest.mark.asyncio
    async def test_modal_flushed_followup(self):
        bot = MagicMock()
        batch_coord = AsyncMock()
        flush_result = SubmitResult(flushed=True, batch=None)
        batch_coord.submit = AsyncMock(return_value=flush_result)
        bot.batch_coordinator = batch_coord

        modal = DeclareActionModal(channel_id=100, bot=bot)
        modal.action_text._value = "Attack the goblin!"

        interaction = _make_modal_interaction()
        await modal.on_submit(interaction)

        interaction.followup.send.assert_called_once()
        content = interaction.followup.send.call_args[1].get("content", "")
        assert "resolving" in content.lower() or "action submitted" in content.lower()

    @pytest.mark.asyncio
    async def test_modal_pending_followup_with_deadline(self):
        bot = MagicMock()
        batch_coord = AsyncMock()
        flush_result = SubmitResult(flushed=False, batch=None)
        batch_coord.submit = AsyncMock(return_value=flush_result)
        batch_coord.get_deadline_seconds_remaining = MagicMock(return_value=20.0)
        bot.batch_coordinator = batch_coord

        modal = DeclareActionModal(channel_id=100, bot=bot)
        modal.action_text._value = "I help Thorin."

        interaction = _make_modal_interaction()
        await modal.on_submit(interaction)

        interaction.followup.send.assert_called_once()
        content = interaction.followup.send.call_args[1].get("content", "")
        assert "waiting" in content.lower() or "party" in content.lower()
        assert "20s" in content

    @pytest.mark.asyncio
    async def test_modal_submit_error_sends_ephemeral_error(self):
        bot = MagicMock()
        batch_coord = AsyncMock()
        batch_coord.submit = AsyncMock(side_effect=RuntimeError("boom"))
        bot.batch_coordinator = batch_coord

        modal = DeclareActionModal(channel_id=100, bot=bot)
        modal.action_text._value = "I hide."

        interaction = _make_modal_interaction()
        await modal.on_submit(interaction)

        interaction.followup.send.assert_called_once()
        call_kwargs = interaction.followup.send.call_args[1]
        assert call_kwargs.get("ephemeral") is True
        assert "failed" in call_kwargs.get("content", "").lower()
