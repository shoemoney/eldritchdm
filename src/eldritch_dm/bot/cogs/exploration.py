"""
ExplorationCog — EXPLORATION state UI: room embed lifecycle, declare-action
modal, and batch coordinator wiring.

Implements EXPLORE-01..07 for Phase 4 Plan 01.

Design:
  - DeclareActionModal: single 500-char TextInput; submission sanitizes and
    queues via BatchCoordinator.
  - DeclareActionButton.callback promoted from Phase 2 stub: checks session
    state, refuses if not EXPLORATION, opens DeclareActionModal via the
    _ModalLaunchView 2-step pattern (Phase 3 precedent from ingest.py).
  - ExplorationCog:
      - render_room_for_channel: posts a new room_embed message with
        DeclareActionButton; registers an EmbedCoalescer.
      - update_room_for_channel: calls existing coalescer.update().
      - Registers resolution + state-change callbacks on the orchestrator.
  - on_state_change(EXPLORATION→COMBAT): closes the exploration coalescer
    for that channel; CombatCog (Plan 02) registers its own.

  EDM001 waiver on _ModalLaunchButton: button opens modal; first response
  is send_modal (same precedent as ingest.py line 609).

Threat mitigations:
  T-04-01: sanitizer wraps with user_id from interaction.user.id directly.
  T-04-02: serializer builds batch from already-wrapped sanitized strings.
  T-04-03: structlog declare_action_submitted log binds channel_id, user_id.
  T-04-05: BatchCoordinator dedupes within 30s window; ChannelRateLimiter
           throttles mutating MCP calls (wired in orchestrator).
  T-04-06: Sanitizer enforces 500-char cap; modal has max_length=500.
  T-04-08: Callbacks wrapped in asyncio.shield in the orchestrator.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from eldritch_dm.bot.coalescer import EmbedCoalescer
from eldritch_dm.bot.embeds import room_embed
from eldritch_dm.gameplay.exploration_batch import PlayerIntent
from eldritch_dm.logging import get_logger
from eldritch_dm.persistence.models import ChannelState
from eldritch_dm.safety.sanitizer import sanitize_player_input

if TYPE_CHECKING:
    from eldritch_dm.bot.bot import EldritchBot

log = get_logger(__name__)


# ── DeclareActionModal ────────────────────────────────────────────────────────


class DeclareActionModal(discord.ui.Modal, title="Declare Your Action"):
    """Modal that collects a player's declared action intent.

    Single TextInput component (max_length=500 enforced client-side per T-04-06).
    on_submit: sanitizes input → creates PlayerIntent → submits to BatchCoordinator.

    Phase 4 Plan 01, EXPLORE-01/02.
    """

    action_text = discord.ui.TextInput(
        label="What do you do?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        placeholder="Describe your action in up to 500 characters...",
        required=True,
    )

    def __init__(self, *, channel_id: int, bot: EldritchBot) -> None:
        super().__init__()
        self._channel_id = channel_id
        self._bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission: sanitize → enqueue → followup with status.

        EDM001: Modal on_submit uses defer(thinking=True, ephemeral=True) first.

        Submission flow (D-08 step 2-5):
          1. Defer ephemeral (EDM001).
          2. Sanitize via sanitize_player_input (T-04-01, T-04-06).
          3. Create PlayerIntent.
          4. Submit to BatchCoordinator.
          5. Followup with status (flushed vs pending).
        """
        # Step 1: EDM001 defer first
        await interaction.response.defer(thinking=True, ephemeral=True)

        channel_id_str = str(self._channel_id)
        user_id = str(getattr(interaction.user, "id", "unknown"))
        display_name = getattr(interaction.user, "display_name", "Player")

        bound_log = log.bind(
            channel_id=channel_id_str,
            user_id=user_id,
        )

        raw = self.action_text.value or ""

        # SAFETY-01 (Phase 7 refactor): read the memoized audit callback
        # from the bot instead of constructing one per-submit. Same wiring
        # as the 3 ingest modals — single source of truth for the bridge
        # from sync sanitize_player_input to the async repo. Pre-Phase-7
        # this constructed make_async_audit_callback(repo) per click (G-2
        # closure pattern); the memoization in bot.setup_hook makes that
        # redundant.
        audit_cb = getattr(self._bot, "sanitizer_audit_callback", None)

        # Step 2: Sanitize (T-04-01, T-04-06, SAN-05)
        sanitized = sanitize_player_input(
            raw,
            speaker=display_name,
            user_id=user_id,
            channel_id=channel_id_str,
            audit_callback=audit_cb,
        )

        bound_log.info(
            "declare_action_submitted",
            len_raw=len(raw),
            audit_stripped_tokens=sanitized.stripped_tokens,
            truncated=sanitized.truncated,
        )

        # Step 3: Create PlayerIntent
        intent = PlayerIntent(
            user_id=user_id,
            sanitized_wrapped=sanitized.wrapped,
            character_id=None,
            ts=datetime.now(UTC),
        )

        # Step 4: Submit to BatchCoordinator
        try:
            result = await self._bot.batch_coordinator.submit(channel_id_str, intent)
        except Exception:
            bound_log.exception("declare_action_batch_submit_error")
            await interaction.followup.send(
                content="Failed to record your action. Please try again.",
                ephemeral=True,
            )
            return

        # Step 5: Status followup
        if result.flushed:
            await interaction.followup.send(
                content="Action submitted. Resolving the party's turn...",
                ephemeral=True,
            )
        else:
            remaining = self._bot.batch_coordinator.get_deadline_seconds_remaining(
                channel_id_str
            )
            remaining_str = f"{int(remaining or 30)}s" if remaining is not None else "30s"
            await interaction.followup.send(
                content=f"Action submitted. Waiting for the party (deadline: {remaining_str}).",
                ephemeral=True,
            )


# ── ExplorationCog ────────────────────────────────────────────────────────────


class ExplorationCog(commands.Cog):
    """Exploration state handler: room embed lifecycle and declare-action UI.

    Holds per-channel EmbedCoalescer instances. When the orchestrator resolves
    a narrative, ExplorationCog.on_resolved is called to update the room embed.
    When state transitions to COMBAT, on_state_change closes the coalescer
    so CombatCog (Plan 02) can register a fresh one.

    Registered on the orchestrator in cog_load.
    """

    def __init__(self, bot: EldritchBot) -> None:
        self.bot = bot
        # channel_id → EmbedCoalescer for the current room message
        self._coalescers: dict[str, EmbedCoalescer] = {}
        # channel_id → room message (for reference)
        self._room_messages: dict[str, discord.Message] = {}
        self._logger = log.bind(cog="exploration")

    async def cog_load(self) -> None:
        """Register callbacks on the orchestrator when cog is loaded."""
        if hasattr(self.bot, "orchestrator") and self.bot.orchestrator is not None:
            self.bot.orchestrator.register_resolution_callback(self.on_resolved)
            self.bot.orchestrator.register_state_change_callback(self.on_state_change)
            self._logger.info("exploration_cog_callbacks_registered")

    # ── Room embed lifecycle ──────────────────────────────────────────────────

    async def render_room_for_channel(
        self,
        channel_id: str,
        room_title: str,
        narration: str,
        party_hp: list[tuple[str, int, int]],
    ) -> discord.Message:
        """Post a fresh room_embed message with DeclareActionButton.

        Also registers an EmbedCoalescer for the posted message.

        Args:
            channel_id: Discord channel snowflake string.
            room_title: Short room/location name.
            narration: DM narration text.
            party_hp: List of (char_name, current_hp, max_hp) for Party field.

        Returns:
            The sent discord.Message.
        """
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            raise ValueError(f"Channel {channel_id} not found or not cached")

        embed = room_embed(
            room_title=room_title,
            narration=narration,
            party_hp=party_hp,
        )

        from eldritch_dm.bot.dynamic_items import DeclareActionButton  # noqa: PLC0415

        view = discord.ui.View(timeout=None)
        view.add_item(DeclareActionButton(channel_id=int(channel_id)))

        msg = await channel.send(embed=embed, view=view)  # type: ignore[union-attr]

        # Get or create per-channel ChannelEditBudget
        budget = self.bot.get_channel_edit_budget(channel_id)

        # Register EmbedCoalescer for this message
        coalescer = EmbedCoalescer(
            msg,
            rate_limit_seconds=self.bot.settings.embed_edit_rate_limit,
            channel_budget=budget,
        )
        # Close any existing coalescer first
        if channel_id in self._coalescers:
            await self._coalescers[channel_id].close()

        self._coalescers[channel_id] = coalescer
        self._room_messages[channel_id] = msg

        self._logger.info(
            "room_rendered",
            channel_id=channel_id,
            room_title=room_title,
            message_id=msg.id,
        )
        return msg

    async def update_room_for_channel(
        self,
        channel_id: str,
        room_title: str,
        narration: str,
        party_hp: list[tuple[str, int, int]],
    ) -> None:
        """Update the current room embed via the registered coalescer.

        Never posts a new message — only edits the existing one.

        Args:
            channel_id: Discord channel snowflake string.
            room_title: Short room/location name (may have changed).
            narration: Updated narration text.
            party_hp: Updated party HP snapshot.
        """
        coalescer = self._coalescers.get(channel_id)
        if coalescer is None:
            self._logger.warning(
                "update_room_no_coalescer",
                channel_id=channel_id,
            )
            return

        embed = room_embed(
            room_title=room_title,
            narration=narration,
            party_hp=party_hp,
        )
        await coalescer.update(embed)

    # ── Orchestrator callbacks ────────────────────────────────────────────────

    async def on_resolved(self, channel_id: str, action: dict[str, Any]) -> None:
        """Called by the orchestrator when a narrative is resolved.

        Updates the room embed with the narrative from the action dict.
        Only acts on EXPLORATION-state resolutions.

        Args:
            channel_id: Discord channel snowflake string.
            action: Popped action dict from dm20 (contains id, text, etc.).
        """
        # Check session state — only update if EXPLORATION
        session = await self.bot.channel_sessions.get(channel_id)
        if session is None or session.state != ChannelState.EXPLORATION:
            return

        narration = action.get("text") or action.get("narration") or "The party's action is noted."

        await self.update_room_for_channel(
            channel_id=channel_id,
            room_title=action.get("location", "Current Room"),
            narration=narration,
            party_hp=[],  # HP snapshot from get_game_state (orchestrator can inject)
        )

    async def on_state_change(
        self,
        channel_id: str,
        old_state: ChannelState,
        new_state: ChannelState,
    ) -> None:
        """Called by the orchestrator on EXPLORATION↔COMBAT transitions.

        On EXPLORATION→COMBAT: closes the exploration coalescer for this channel.
        CombatCog (Plan 02) will register its own coalescer for the combat embed.

        Args:
            channel_id: Discord channel snowflake string.
            old_state: Previous ChannelState.
            new_state: New ChannelState.
        """
        if old_state == ChannelState.EXPLORATION and new_state == ChannelState.COMBAT:
            coalescer = self._coalescers.pop(channel_id, None)
            if coalescer is not None:
                await coalescer.close()
                self._logger.info(
                    "exploration_coalescer_closed_for_combat",
                    channel_id=channel_id,
                )

    # ── Cog unload ────────────────────────────────────────────────────────────

    async def cog_unload(self) -> None:
        """Close all coalescers on cog unload."""
        for coalescer in list(self._coalescers.values()):
            await coalescer.close()
        self._coalescers.clear()


async def setup(bot: EldritchBot) -> None:
    """discord.py extension entry point — called by bot.load_extension(...)."""
    await bot.add_cog(ExplorationCog(bot))
