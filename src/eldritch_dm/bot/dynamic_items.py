"""
EldritchDM persistent button DynamicItem subclasses.

Each class subclasses ``discord.ui.DynamicItem[discord.ui.Button]`` with a
class-level ``template`` regex. Discord routes any incoming button click whose
``custom_id`` fullmatches the template to the appropriate class's
``from_custom_id`` classmethod, then invokes ``callback``.

IMPORTANT — rehydration note (from 02-RESEARCH.md):
    ``add_dynamic_items(Cls)`` registers a regex listener globally. Any
    ``custom_id`` matching the template is routed to the correct handler
    regardless of which message/channel the button lives on. This means
    ``bot.add_view(view, message_id=...)`` is NOT needed for DynamicItem-based
    buttons. The ``persistent_views`` table is bookkeeping / audit metadata —
    not a rehydration source. (Old tutorials that say ``add_view`` is required
    pre-date discord.py 2.4's DynamicItem API.)

``DYNAMIC_ITEM_CLASSES`` is the canonical tuple for Plan 03's ``setup_hook``::

    bot.add_dynamic_items(*DYNAMIC_ITEM_CLASSES)

Phase 2 callbacks are STUBS (D-23): they defer first (D-09), bind structlog
context (D-38), log the dispatch, and reply with an ephemeral "Phase N stub"
message. Real handlers land in:
    - Phase 3: ReadyButton
    - Phase 4: DeclareActionButton, EndTurnButton
    - Phase 5: RiposteButton

custom_id 100-char limit (D-22, T-02-10): encodings are compact digit-only
strings. For 19-digit Discord snowflakes (the realistic worst case):
    - ``endturn:9999999999999999999:9999999999999999999`` = 48 chars  ✓
    - ``riposte:9999999999999999999:9999999999999999999`` = 48 chars  ✓
"""

from __future__ import annotations

import json
import re

import discord
import structlog

from eldritch_dm.logging import get_logger
from eldritch_dm.mcp import tools as mcp_tools
from eldritch_dm.persistence.models import ChannelState, PersistentView

log = get_logger(__name__)


# ── ReadyButton ────────────────────────────────────────────────────────────────


class ReadyButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^ready:(?P<channel_id>\d+)$",
):
    """Lobby ready-up button.

    Encodes: ``channel_id`` (Discord channel snowflake).
    Phase 3 handler: marks the player as ready in channel session; triggers
    transition to exploration when all players are ready.
    """

    template = re.compile(r"^ready:(?P<channel_id>\d+)$")

    def __init__(self, channel_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="✅ Ready",
                custom_id=f"ready:{channel_id}",
            )
        )
        self.channel_id = channel_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> "ReadyButton":
        return cls(channel_id=int(match["channel_id"]))

    def _custom_id_str(self) -> str:
        return f"ready:{self.channel_id}"

    async def callback(self, interaction: discord.Interaction) -> None:
        """Real Phase 3 ReadyButton callback — state machine implementation.

        Resolves dependencies from ``interaction.client`` (the bot), which
        exposes ``.mcp``, ``.channel_sessions``, and ``.persistent_views``
        (set in EldritchBot.__init__ and setup_hook, Task 4).

        State machine (D-11, D-12, D-13):
          1. Defer ephemeral (D-09 / EDM001).
          2. Load ChannelSession; error if missing.
          3. Fetch roster via list_characters; reject non-roster users.
          4. Load per-channel ready dict from persistent_views.payload_json;
             default to empty if row missing.
          5. Add user ID (deduped); upsert the row (survives restart — D-12).
          6. If all roster players are ready → transition to EXPLORATION and
             signal Claudmaster via player_action(action='party_ready').
             Otherwise → ephemeral progress reply.

        Threat mitigations:
          T-03-02: roster check via list_characters player_id set.
          D-13: player_id mapping is the gate (not Discord role).

        CONTEXT ref: D-11, D-12, D-13, D-37 (structlog binding)
        """
        # Step 1: D-09 defer first (EDM001 lint gate)
        await interaction.response.defer(thinking=True, ephemeral=True)

        # D-37: bind structlog context early
        user_id = getattr(interaction.user, "id", None)
        bound_log = log.bind(
            channel_id=self.channel_id,
            custom_id=self._custom_id_str(),
            view_class=type(self).__name__,
            user_id=user_id,
        )
        bound_log.info("ready_button_invoked")

        # Resolve bot subsystems via interaction.client (cannot use constructor injection
        # with DynamicItem — discord.py routes dispatch via class; cog can't inject deps).
        bot = interaction.client
        channel_sessions_repo = bot.channel_sessions
        persistent_views_repo = bot.pv_repo
        mcp_client = bot.mcp

        # Step 2: Load channel session
        session = await channel_sessions_repo.get(str(self.channel_id))
        if session is None:
            bound_log.warning("ready_button_no_session")
            await interaction.followup.send(
                content="No active session in this channel. Run /start_game first.",
                ephemeral=True,
            )
            return

        # Bind campaign_name after session lookup (D-37)
        bound_log = bound_log.bind(campaign_name=session.campaign_name)

        # Step 3: Fetch roster from dm20; verify user is on it (T-03-02, D-13)
        try:
            roster_result = await mcp_tools.list_characters(
                mcp_client,
                campaign_name=session.campaign_name,
            )
        except Exception:  # noqa: BLE001
            bound_log.exception("ready_button_list_characters_error")
            await interaction.followup.send(
                content="Could not fetch character roster — please try again.",
                ephemeral=True,
            )
            return

        characters = roster_result.get("characters", []) if isinstance(roster_result, dict) else []
        player_ids: set[str] = {str(c.get("player_id", "")) for c in characters if c.get("player_id")}

        if str(user_id) not in player_ids:
            bound_log.warning("ready_button_non_roster_user")
            await interaction.followup.send(
                content="Only seated players can ready up. Add a character first.",
                ephemeral=True,
            )
            return

        # Step 4: Load per-channel ready dict from persistent_views
        ready_custom_id = f"ready:{self.channel_id}"
        pv_row = await persistent_views_repo.get(ready_custom_id)
        if pv_row is not None:
            ready_user_ids: list[str] = list(pv_row.payload.get("ready_user_ids", []))
        else:
            ready_user_ids = []

        # Step 5: Add user (deduped) and upsert persistent_views row
        if str(user_id) not in ready_user_ids:
            ready_user_ids.append(str(user_id))

        # Build the PersistentView for the ready-state row.
        # created_at is set by the DB (datetime('now')); provide a dummy datetime
        # for model construction since it's required by Pydantic but overridden in SQL.
        # message_id is "" since we track the lobby message separately.
        from datetime import UTC, datetime as _datetime  # noqa: PLC0415

        updated_view = PersistentView(
            custom_id=ready_custom_id,
            view_class="ReadyButton",
            message_id="",
            channel_id=str(self.channel_id),
            payload={"ready_user_ids": ready_user_ids},
            created_at=_datetime.now(tz=UTC),
        )
        await persistent_views_repo.insert(updated_view)
        bound_log.info(
            "ready_button_state_saved",
            ready_count=len(ready_user_ids),
            total=len(player_ids),
        )

        # Step 6: Check if all-ready transition applies
        if set(ready_user_ids) >= player_ids and player_ids:
            # All roster players have readied up → EXPLORATION transition
            bound_log.info("ready_button_all_ready_transition")

            await channel_sessions_repo.set_state(
                str(self.channel_id), ChannelState.EXPLORATION
            )

            # Signal Claudmaster (best-effort; suppress errors to not block the transition)
            try:
                await mcp_tools.player_action(
                    mcp_client,
                    session_id=session.claudmaster_session_id or "",
                    action="party_ready",
                    context="lobby_complete",
                )
            except Exception:  # noqa: BLE001
                bound_log.warning("ready_button_player_action_failed")

            # Update the lobby embed on the original message
            from eldritch_dm.bot.embeds import PlayerStatus, lobby_embed  # noqa: PLC0415

            player_statuses = [
                PlayerStatus(
                    display_name=c.get("name", "Unknown"),
                    ready=True,
                    character_name=c.get("name"),
                )
                for c in characters
            ]
            transition_embed = lobby_embed(
                campaign_name=session.campaign_name,
                players=player_statuses,
                transition_state="transitioning",
            )
            try:
                await interaction.message.edit(embed=transition_embed)
            except Exception:  # noqa: BLE001
                bound_log.warning("ready_button_embed_edit_failed")

            await interaction.followup.send(
                content="All players ready! Transitioning to EXPLORATION…",
                ephemeral=True,
            )
        else:
            # Partial ready — report progress
            n = len(ready_user_ids)
            total = len(player_ids)
            await interaction.followup.send(
                content=f"Marked ready ({n}/{total}). Waiting for other players…",
                ephemeral=True,
            )


# ── DeclareActionButton ────────────────────────────────────────────────────────


class DeclareActionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^declare:(?P<channel_id>\d+)$",
):
    """Exploration intent-collection button.

    Encodes: ``channel_id``.
    Phase 4 handler: opens a modal for the player to declare their action
    intent before the DM narrates the scene.
    """

    template = re.compile(r"^declare:(?P<channel_id>\d+)$")

    def __init__(self, channel_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="💬 Declare Action",
                custom_id=f"declare:{channel_id}",
            )
        )
        self.channel_id = channel_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> "DeclareActionButton":
        return cls(channel_id=int(match["channel_id"]))

    def _custom_id_str(self) -> str:
        return f"declare:{self.channel_id}"

    async def callback(self, interaction: discord.Interaction) -> None:
        # D-09: defer first — always
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = log.bind(
            channel_id=self.channel_id,
            custom_id=self._custom_id_str(),
            view_class=type(self).__name__,
            user_id=getattr(interaction.user, "id", None),
        )
        bound_log.info("phase2_stub_callback_invoked")

        await interaction.followup.send(
            content=f"⏳ Phase 2 stub — {type(self).__name__} will be wired up in a later phase.",
            ephemeral=True,
        )


# ── EndTurnButton ──────────────────────────────────────────────────────────────


class EndTurnButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^endturn:(?P<channel_id>\d+):(?P<actor_id>\d+)$",
):
    """Combat turn-yield button.

    Encodes: ``channel_id``, ``actor_id`` (Discord user snowflake).
    Phase 4 handler: validates that ``interaction.user.id == actor_id``
    (T-02-09 elevation-of-privilege mitigation), then advances turn order.
    """

    template = re.compile(r"^endturn:(?P<channel_id>\d+):(?P<actor_id>\d+)$")

    def __init__(self, channel_id: int, actor_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="⏭️ End Turn",
                custom_id=f"endturn:{channel_id}:{actor_id}",
            )
        )
        self.channel_id = channel_id
        self.actor_id = actor_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> "EndTurnButton":
        return cls(
            channel_id=int(match["channel_id"]),
            actor_id=int(match["actor_id"]),
        )

    def _custom_id_str(self) -> str:
        return f"endturn:{self.channel_id}:{self.actor_id}"

    async def callback(self, interaction: discord.Interaction) -> None:
        # D-09: defer first — always
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = log.bind(
            channel_id=self.channel_id,
            actor_id=self.actor_id,
            custom_id=self._custom_id_str(),
            view_class=type(self).__name__,
            user_id=getattr(interaction.user, "id", None),
        )
        bound_log.info("phase2_stub_callback_invoked")

        await interaction.followup.send(
            content=f"⏳ Phase 2 stub — {type(self).__name__} will be wired up in a later phase.",
            ephemeral=True,
        )


# ── RiposteButton ──────────────────────────────────────────────────────────────


class RiposteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^riposte:(?P<timer_id>\d+):(?P<user_id>\d+)$",
):
    """Timed riposte reaction button.

    Encodes: ``timer_id`` (keys into ``riposte_timers`` table), ``user_id``.
    Phase 5 handler: validates the timer has not expired, then processes the
    riposte counter-attack.
    """

    template = re.compile(r"^riposte:(?P<timer_id>\d+):(?P<user_id>\d+)$")

    def __init__(self, timer_id: int, user_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="⚔️ Riposte!",
                custom_id=f"riposte:{timer_id}:{user_id}",
            )
        )
        self.timer_id = timer_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> "RiposteButton":
        return cls(
            timer_id=int(match["timer_id"]),
            user_id=int(match["user_id"]),
        )

    def _custom_id_str(self) -> str:
        return f"riposte:{self.timer_id}:{self.user_id}"

    async def callback(self, interaction: discord.Interaction) -> None:
        # D-09: defer first — always
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = log.bind(
            timer_id=self.timer_id,
            user_id=self.user_id,
            custom_id=self._custom_id_str(),
            view_class=type(self).__name__,
        )
        bound_log.info("phase2_stub_callback_invoked")

        await interaction.followup.send(
            content=f"⏳ Phase 2 stub — {type(self).__name__} will be wired up in a later phase.",
            ephemeral=True,
        )


# ── Registration tuple ─────────────────────────────────────────────────────────

DYNAMIC_ITEM_CLASSES: tuple[type[discord.ui.DynamicItem], ...] = (
    ReadyButton,
    DeclareActionButton,
    EndTurnButton,
    RiposteButton,
)
"""Canonical tuple for ``setup_hook`` registration.

Usage in Plan 03's setup_hook::

    bot.add_dynamic_items(*DYNAMIC_ITEM_CLASSES)

Note: ``add_dynamic_items`` alone is sufficient for persistent buttons.
Do NOT also call ``bot.add_view(view, message_id=...)`` for these classes
(see module docstring and 02-RESEARCH.md Pitfall 1).
"""
