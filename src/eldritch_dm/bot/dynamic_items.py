"""
EldritchDM persistent button DynamicItem subclasses.

Each class subclasses ``discord.ui.DynamicItem[discord.ui.Button]`` with a
class-level ``template`` regex. Discord routes any incoming button click whose
``custom_id`` fullmatches the template to the appropriate class's
``from_custom_id`` classmethod, then invokes ``callback``.

IMPORTANT -- rehydration note (from 02-RESEARCH.md):
    ``add_dynamic_items(Cls)`` registers a regex listener globally. Any
    ``custom_id`` matching the template is routed to the correct handler
    regardless of which message/channel the button lives on. This means
    ``bot.add_view(view, message_id=...)`` is NOT needed for DynamicItem-based
    buttons. The ``persistent_views`` table is bookkeeping / audit metadata --
    not a rehydration source. (Old tutorials that say ``add_view`` is required
    pre-date discord.py 2.4's DynamicItem API.)

``DYNAMIC_ITEM_CLASSES`` is the canonical tuple for Plan 03's ``setup_hook``::

    bot.add_dynamic_items(*DYNAMIC_ITEM_CLASSES)

Phase 2 callbacks are STUBS (D-23): they defer first (D-09), bind structlog
context (D-38), log the dispatch, and reply with an ephemeral "Phase N stub"
message. Real handlers land in:
    - Phase 3: ReadyButton
    - Phase 4: DeclareActionButton, EndTurnButton, AttackButton, DodgeButton,
               CastSpellButton (stub)
    - Phase 5: RiposteButton

custom_id 100-char limit (D-22, T-02-10): encodings are compact digit-only
strings. For 19-digit Discord snowflakes (the realistic worst case):
    - ``endturn:9999999999999999999:9999999999999999999`` = 48 chars  ok
    - ``riposte:9999999999999999999:9999999999999999999`` = 48 chars  ok

Phase 4 Plan 02: combat buttons with turn-gatekeeper pattern.
    All combat button callbacks:
      1. defer(thinking=True, ephemeral=True)  (EDM001)
      2. Load session, get enriched game_state
      3. Check stale-round (match["round"] vs game_state["round_number"])
      4. is_actor gate (T-04-09)
      5. rate_limiter.acquire() -- ONLY on accepted mutating calls (T-04-13)
      6. MCP call
      7. Ephemeral followup

Phase 5 Plan 01 — Riposte trigger relocation (D-A):
    The Phase 4 stub seam `AttackButton._maybe_surface_riposte` has been
    DELETED. It fired on the wrong RAW path (PC-misses-monster). Battle
    Master Riposte triggers when a MONSTER misses a PC. The correct trigger
    now lives in `gameplay/monster_driver.MonsterDriver` which detects
    monster-actor turns, calls dm20__combat_action, parses the text outcome
    via `gameplay/combat_outcome_parser`, and on MISS / NATURAL_ONE awaits
    `gameplay/reactions.surface_riposte_button`.

Dodge v1 narrative-only note (04-RESEARCH.md Q2, D-22):
    dm20 has no built-in "dodging" SRD condition. DodgeButton:
      1. Writes a row to combat_conditions (local shim).
      2. Calls apply_effect(target=actor_id, effect="dodging") so ShoeGPT
         gets narrative context ("Thorin is dodging").
      3. The mechanical disadvantage on incoming attacks is v1-narrative-only --
         combat_action has no advantage/disadvantage arg. Phase 5 will add the
         mechanical enforcement when dm20 supports it.
"""

from __future__ import annotations

import re
from typing import Any

import discord

from eldritch_dm.bot.warnings import WarningKind, send_warning
from eldritch_dm.gameplay.turn_gatekeeper import current_actor_from_game_state, is_actor
from eldritch_dm.logging import get_logger
from eldritch_dm.mcp import tools as mcp_tools
from eldritch_dm.persistence.combat_conditions_repo import CombatConditionsRepo
from eldritch_dm.persistence.models import ChannelState, PersistentView

log = get_logger(__name__)


# ── Shared combat-button prelude helpers ─────────────────────────────────────

async def _combat_button_prelude(
    btn: discord.ui.DynamicItem,
    interaction: discord.Interaction,
    round_n: int,
    actor_id: str,
) -> tuple[dict[str, Any] | None, Any | None, str | None]:
    """Shared prelude for all combat action buttons.

    Performs:
      1. Load session from channel_sessions.
      2. Call _get_enriched_game_state (override in tests via patching).
      3. Stale-round check: match["round"] vs game_state["round_number"].
      4. is_actor gate.

    Returns:
        (enriched_game_state, current_actor, channel_id_str)
        OR (None, None, None) if the prelude rejected the click (warning already sent).

    The caller MUST check if enriched_game_state is None before proceeding.
    """
    channel_id_str = str(btn.channel_id)  # type: ignore[attr-defined]
    user_id = str(getattr(interaction.user, "id", "0"))
    bot = interaction.client
    bound_log = log.bind(
        channel_id=channel_id_str,
        actor_id=actor_id,
        round=round_n,
        user_id=user_id,
        action_kind=type(btn).__name__,
    )
    bound_log.info("combat_button_invoked")

    # Load session
    channel_sessions = getattr(bot, "channel_sessions", None)
    if channel_sessions is None:
        await send_warning(interaction, WarningKind.INVALID_ACTION, reason="Bot not ready.")
        return None, None, None

    session = await channel_sessions.get(channel_id_str)
    if session is None or session.state != ChannelState.COMBAT:
        sess_state = getattr(session, "state", "no_session")
        await send_warning(
            interaction,
            WarningKind.INVALID_ACTION,
            reason=f"No active combat in this channel (state: {sess_state}).",
        )
        return None, None, None

    # Get enriched game state (allow override in tests via _get_enriched_game_state)
    enriched_state = await btn._get_enriched_game_state(bot, channel_id_str)  # type: ignore[attr-defined]
    if enriched_state is None:
        await send_warning(
            interaction,
            WarningKind.INVALID_ACTION,
            reason="Could not fetch game state.",
        )
        return None, None, None

    # Stale-round check (T-04-10)
    current_round = enriched_state.get("round_number", 0)
    if round_n != current_round:
        bound_log.warning(
            "combat_button_stale_round",
            button_round=round_n,
            current_round=current_round,
        )
        await send_warning(
            interaction,
            WarningKind.INVALID_ACTION,
            reason="This is an old turn. The round has advanced.",
        )
        return None, None, None

    # is_actor gate (T-04-09)
    current_actor = current_actor_from_game_state(enriched_state)
    if current_actor is None or not is_actor(user_id, current_actor):
        actor_name = current_actor["name"] if current_actor else "another character"
        bound_log.warning("combat_button_not_your_turn", current_actor=actor_name)
        await send_warning(interaction, WarningKind.NOT_YOUR_TURN, actor_name=actor_name)
        return None, None, None

    return enriched_state, current_actor, channel_id_str


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
    ) -> ReadyButton:
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
        player_ids: set[str] = {  # noqa: E501
            str(c.get("player_id", "")) for c in characters if c.get("player_id")
        }

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
        from datetime import UTC  # noqa: PLC0415
        from datetime import datetime as _datetime

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
    ) -> DeclareActionButton:
        return cls(channel_id=int(match["channel_id"]))

    def _custom_id_str(self) -> str:
        return f"declare:{self.channel_id}"

    async def callback(self, interaction: discord.Interaction) -> None:
        """Phase 4 DeclareActionButton callback.

        State guard: refuses to open modal if session is not EXPLORATION.
        Uses the 2-step _ModalLaunchView pattern (defer + ephemeral button →
        button click sends modal on a fresh interaction).

        EDM001 waiver granted on the inner _launch_button: it opens a modal;
        first response is send_modal (same precedent as ingest.py line 609).
        """
        # Step 1: D-09 defer first (EDM001 lint gate)
        await interaction.response.defer(thinking=True, ephemeral=True)

        channel_id_str = str(self.channel_id)
        bound_log = log.bind(
            channel_id=channel_id_str,
            custom_id=self._custom_id_str(),
            view_class=type(self).__name__,
            user_id=getattr(interaction.user, "id", None),
        )
        bound_log.info("declare_action_button_invoked")

        # Resolve bot subsystems via interaction.client (DynamicItem cannot use
        # constructor injection — discord.py routes dispatch via class).
        bot = interaction.client

        # Step 2: Check session state — only open modal if EXPLORATION
        from eldritch_dm.persistence.models import ChannelState  # noqa: PLC0415

        channel_sessions = getattr(bot, "channel_sessions", None)
        if channel_sessions is None:
            bound_log.warning("declare_action_no_channel_sessions")
            from eldritch_dm.bot.warnings import WarningKind, send_warning  # noqa: PLC0415

            await send_warning(
                interaction,
                WarningKind.INVALID_ACTION,
                reason="Bot not ready yet. Try again in a moment.",
            )
            return

        session = await channel_sessions.get(channel_id_str)
        if session is None or session.state != ChannelState.EXPLORATION:
            bound_log.warning(
                "declare_action_wrong_state",
                state=session.state if session else "no_session",
            )
            from eldritch_dm.bot.warnings import WarningKind, send_warning  # noqa: PLC0415

            if session is None:
                reason = "No active session in this channel."
            else:
                reason = (
                    f"Actions can only be declared during exploration"
                    f" (state: {session.state})."
                )
            await send_warning(
                interaction,
                WarningKind.INVALID_ACTION,
                reason=reason,
            )
            return

        # Step 3: Open modal via 2-step pattern (defer + send_modal conflict workaround).
        # Import here to avoid circular import (dynamic_items → cogs/exploration).
        from eldritch_dm.bot.cogs.exploration import DeclareActionModal  # noqa: PLC0415

        def _modal_factory() -> DeclareActionModal:
            return DeclareActionModal(channel_id=self.channel_id, bot=bot)  # type: ignore[arg-type]

        # Inline _ModalLaunchView — same pattern as ingest.py but private to this callback.
        launch_view = discord.ui.View(timeout=300)
        launch_button = discord.ui.Button(
            label="Open Action Form",
            style=discord.ButtonStyle.primary,
        )

        async def _on_launch_click(btn_interaction: discord.Interaction) -> None:  # noqa: EDM001 — button opens modal; first response is send_modal
            await btn_interaction.response.send_modal(_modal_factory())

        launch_button.callback = _on_launch_click
        launch_view.add_item(launch_button)

        await interaction.followup.send(
            content="Click below to declare your action:",
            view=launch_view,
            ephemeral=True,
        )


# ── EndTurnButton ──────────────────────────────────────────────────────────────


class EndTurnButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^endturn:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)$",
):
    """Combat turn-yield button.

    Encodes: ``channel_id``, ``actor_id`` (dm20 character UUID), ``round`` (cache-buster).

    Phase 4 handler (Phase 2 stub promoted):
      - Validates that interaction.user.id matches current_actor.player_id (T-04-09).
      - Stale-round guard: match["round"] vs game_state["round_number"] (T-04-10).
      - Calls dm20__next_turn via ChannelRateLimiter (OPS-03, D-29).

    Phase 2 Note: The old Phase 2 stub used actor_id as a Discord user snowflake
    (digit-only). Phase 4 changes actor_id to a dm20 character UUID (lowercase
    alphanumeric+dash). This is a BREAKING CHANGE to the custom_id regex, but
    Phase 2 only emitted stubs, so no live persistent buttons exist with the old format.
    """

    template = re.compile(r"^endturn:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)$")

    def __init__(self, channel_id: int, actor_id: str, round_n: int) -> None:
        # Set attrs BEFORE super().__init__() -- discord.py accesses self.custom_id
        # during DynamicItem.__init__() to validate the template match.
        self.channel_id = channel_id
        self.actor_id = actor_id
        self.round_n = round_n
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="⏭️ End Turn",
                custom_id=f"endturn:{channel_id}:{actor_id}:{round_n}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> EndTurnButton:
        return cls(
            channel_id=int(match["channel_id"]),
            actor_id=match["actor_id"],
            round_n=int(match["round"]),
        )

    @property
    def custom_id(self) -> str:
        return f"endturn:{self.channel_id}:{self.actor_id}:{self.round_n}"

    def _custom_id_str(self) -> str:
        return self.custom_id

    async def _get_enriched_game_state(  # noqa: E501
        self, bot: Any, channel_id_str: str
    ) -> dict[str, Any] | None:
        """Fetch and return an enriched game_state dict for the given channel.

        Separated for testability — tests can patch this method on the instance.
        The real implementation fetches from dm20 via mcp_tools.get_game_state.

        Returns None on error.
        """
        try:
            raw = await mcp_tools.get_game_state(bot.mcp)
            if not isinstance(raw, str):
                raw = str(raw) if raw is not None else ""
            from eldritch_dm.gameplay.game_state_parser import parse_game_state  # noqa: PLC0415
            parsed = parse_game_state(raw)
            # Build minimal enriched state from parsed data
            # Real CombatCog builds a richer version with per-actor HP/AC from get_character
            # Here we use ParsedGameState fields and synthesize actor dicts from initiative
            combatants = []
            for name, init_score in parsed.initiative_order:
                actor_id_guess = name.lower().replace(" ", "-")
                combatants.append({
                    "id": actor_id_guess,
                    "name": name,
                    "player_id": None,  # unknown without get_character; gatekeeper will reject all
                    "hp_current": 0,
                    "hp_max": 0,
                    "ac": 10,
                    "conditions": [],
                    "_initiative": init_score,
                })
            # Override player_id for current actor if we know the channel's character map
            # (CombatCog injects this via a richer path; button callbacks use the lightweight path)
            return {
                "current_actor_id": (
                    parsed.current_turn.lower().replace(" ", "-")
                    if parsed.current_turn else None
                ),
                "combatants": combatants,
                "round_number": parsed.round_number,
                "in_combat": parsed.in_combat,
            }
        except Exception:  # noqa: BLE001
            log.warning("endturn_button_game_state_error", channel_id=channel_id_str)
            return None

    async def callback(self, interaction: discord.Interaction) -> None:
        """End the current actor's turn.

        Prelude: defer, load session, stale-round check, is_actor gate.
        Then: rate_limiter.acquire -> next_turn.
        """
        # EDM001: defer first
        await interaction.response.defer(thinking=True, ephemeral=True)

        enriched_state, current_actor, channel_id_str = await _combat_button_prelude(
            self, interaction, self.round_n, self.actor_id
        )
        if enriched_state is None:
            return

        bot = interaction.client
        rate_limiter = getattr(bot, "rate_limiter", None)

        # Acquire rate limiter for mutating call (D-29, OPS-03)
        if rate_limiter is not None:
            await rate_limiter.acquire(channel_id_str)

        try:
            await mcp_tools.next_turn(bot.mcp)
            log.bind(
                channel_id=channel_id_str,
                actor_id=self.actor_id,
                action_kind="end_turn",
                round_number=self.round_n,
            ).info("end_turn_dispatched")
        except Exception:  # noqa: BLE001
            log.warning("end_turn_mcp_error", channel_id=channel_id_str, actor_id=self.actor_id)
            await interaction.followup.send(
                content="Failed to advance turn. Please try again.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(content="⏭ Turn ended.", ephemeral=True)


# ── AttackButton ──────────────────────────────────────────────────────────────


class AttackButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^attack:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)$",
):
    """Combat attack button.

    Encodes: channel_id, actor_id (dm20 character UUID), round (cache-buster).
    Phase 4 Plan 02: real callback with is_actor + stale-round gate + rate limit.

    Attack flow (D-18, D-19, D-20):
      1. Prelude checks (defer, session, round guard, is_actor).
      2. Open WeaponSelectModal via 2-step launch pattern.
      3. on_submit_cb: rate_limiter.acquire -> combat_action(action="attack").
      4. Enqueue narrative context for ShoeGPT.

    Phase 5 Plan 01 D-A: the prior `_maybe_surface_riposte` seam was DELETED.
    Riposte fires on the monster-attack path in MonsterDriver, not here.
    """

    template = re.compile(r"^attack:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)$")

    def __init__(self, channel_id: int, actor_id: str, round_n: int) -> None:
        # Set attrs BEFORE super().__init__() — discord.py calls self.custom_id
        # during DynamicItem.__init__() to validate the template match.
        self.channel_id = channel_id
        self.actor_id = actor_id
        self.round_n = round_n
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="⚔️ Attack",
                custom_id=f"attack:{channel_id}:{actor_id}:{round_n}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> AttackButton:
        return cls(
            channel_id=int(match["channel_id"]),
            actor_id=match["actor_id"],
            round_n=int(match["round"]),
        )

    @property
    def custom_id(self) -> str:
        return f"attack:{self.channel_id}:{self.actor_id}:{self.round_n}"

    def _custom_id_str(self) -> str:
        return self.custom_id

    async def _get_enriched_game_state(  # noqa: E501
        self, bot: Any, channel_id_str: str
    ) -> dict[str, Any] | None:
        """Lightweight game state fetch -- see EndTurnButton for full doc."""
        try:
            raw = await mcp_tools.get_game_state(bot.mcp)
            if not isinstance(raw, str):
                raw = str(raw) if raw is not None else ""
            from eldritch_dm.gameplay.game_state_parser import parse_game_state  # noqa: PLC0415
            parsed = parse_game_state(raw)
            combatants = [
                {
                    "id": name.lower().replace(" ", "-"),
                    "name": name,
                    "player_id": None,
                    "hp_current": 0,
                    "hp_max": 0,
                    "ac": 10,
                    "conditions": [],
                }
                for name, _ in parsed.initiative_order
            ]
            return {
                "current_actor_id": (
                    parsed.current_turn.lower().replace(" ", "-")
                    if parsed.current_turn else None
                ),
                "combatants": combatants,
                "round_number": parsed.round_number,
                "in_combat": parsed.in_combat,
            }
        except Exception:  # noqa: BLE001
            log.warning("attack_button_game_state_error", channel_id=channel_id_str)
            return None

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle Attack button click.

        2-step modal flow: defer -> prelude checks -> open WeaponSelectModal.
        The on_submit_cb completes the attack flow.
        """
        # EDM001: defer first
        await interaction.response.defer(thinking=True, ephemeral=True)

        enriched_state, current_actor, channel_id_str = await _combat_button_prelude(
            self, interaction, self.round_n, self.actor_id
        )
        if enriched_state is None:
            return

        bot = interaction.client

        # Open WeaponSelectModal via 2-step launch pattern (D-18, Phase 3 precedent).
        from eldritch_dm.bot.modals import WeaponSelectModal  # noqa: PLC0415

        actor_id = self.actor_id
        round_n = self.round_n

        async def _on_weapon_submit(payload: dict[str, Any]) -> None:
            """Called after WeaponSelectModal submit. Dispatches combat_action."""
            weapon = payload.get("weapon", "")
            target_id = payload.get("target_id", "")

            rate_limiter = getattr(bot, "rate_limiter", None)
            if rate_limiter is not None:
                await rate_limiter.acquire(channel_id_str)

            try:
                await mcp_tools.combat_action(
                    bot.mcp,
                    action="attack",
                    attacker=actor_id,
                    target=target_id,
                    weapon_or_spell=weapon,
                )
            except Exception:  # noqa: BLE001
                log.warning(
                    "attack_combat_action_error",
                    channel_id=channel_id_str,
                    actor_id=actor_id,
                )
                return

            log.bind(
                channel_id=channel_id_str,
                actor_id=actor_id,
                action_kind="attack",
                round_number=round_n,
                weapon=weapon,
                target=target_id,
            ).info("attack_dispatched")

        modal = WeaponSelectModal(on_submit_cb=_on_weapon_submit)

        # 2-step launch: send ephemeral button that opens the modal
        launch_view = discord.ui.View(timeout=300)
        launch_button = discord.ui.Button(
            label="Select Weapon & Target",
            style=discord.ButtonStyle.primary,
        )

        async def _on_launch_click(btn_interaction: discord.Interaction) -> None:  # noqa: EDM001 -- button opens modal; first response is send_modal
            await btn_interaction.response.send_modal(modal)

        launch_button.callback = _on_launch_click
        launch_view.add_item(launch_button)

        await interaction.followup.send(
            content="Choose your weapon and target:",
            view=launch_view,
            ephemeral=True,
        )


# ── DodgeButton ────────────────────────────────────────────────────────────────


class DodgeButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^dodge:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)$",
):
    """Combat dodge button.

    Encodes: channel_id, actor_id (dm20 character UUID), round (cache-buster).
    Phase 4 Plan 02: real callback with is_actor + stale-round gate.

    Dodge flow (D-22, D-23):
      1. Prelude checks (defer, session, round guard, is_actor).
      2. Insert combat_conditions row (shim for dm20 missing "dodging" condition).
      3. Call apply_effect(target=actor_id, effect="dodging") for ShoeGPT narrative.
         NOTE: v1 mechanical disadvantage is narrative-only.
      4. Call next_turn (D-23: dodge ends turn immediately).

    v1 dodge is narrative-only per 04-RESEARCH.md Q2:
        dm20 has no built-in "dodging" SRD condition. The mechanical disadvantage
        on incoming attacks is enforced narratively -- ShoeGPT sees "Thorin is dodging"
        in the narrative context. Phase 5 will wire actual to-hit math when dm20 adds
        advantage/disadvantage support to combat_action.
    """

    template = re.compile(r"^dodge:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)$")

    def __init__(self, channel_id: int, actor_id: str, round_n: int) -> None:
        # Set attrs BEFORE super().__init__() -- discord.py accesses self.custom_id
        # during DynamicItem.__init__() to validate the template match.
        self.channel_id = channel_id
        self.actor_id = actor_id
        self.round_n = round_n
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="🛡️ Dodge",
                custom_id=f"dodge:{channel_id}:{actor_id}:{round_n}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> DodgeButton:
        return cls(
            channel_id=int(match["channel_id"]),
            actor_id=match["actor_id"],
            round_n=int(match["round"]),
        )

    @property
    def custom_id(self) -> str:
        return f"dodge:{self.channel_id}:{self.actor_id}:{self.round_n}"

    def _custom_id_str(self) -> str:
        return self.custom_id

    async def _get_enriched_game_state(  # noqa: E501
        self, bot: Any, channel_id_str: str
    ) -> dict[str, Any] | None:
        """Lightweight game state fetch -- see EndTurnButton for full doc."""
        try:
            raw = await mcp_tools.get_game_state(bot.mcp)
            if not isinstance(raw, str):
                raw = str(raw) if raw is not None else ""
            from eldritch_dm.gameplay.game_state_parser import parse_game_state  # noqa: PLC0415
            parsed = parse_game_state(raw)
            combatants = [
                {
                    "id": name.lower().replace(" ", "-"),
                    "name": name,
                    "player_id": None,
                    "hp_current": 0,
                    "hp_max": 0,
                    "ac": 10,
                    "conditions": [],
                }
                for name, _ in parsed.initiative_order
            ]
            return {
                "current_actor_id": (
                    parsed.current_turn.lower().replace(" ", "-")
                    if parsed.current_turn else None
                ),
                "combatants": combatants,
                "round_number": parsed.round_number,
                "in_combat": parsed.in_combat,
            }
        except Exception:  # noqa: BLE001
            log.warning("dodge_button_game_state_error", channel_id=channel_id_str)
            return None

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle Dodge button click.

        D-22 shim path: combat_conditions row + apply_effect narrative hint + next_turn.
        """
        # EDM001: defer first
        await interaction.response.defer(thinking=True, ephemeral=True)

        enriched_state, current_actor, channel_id_str = await _combat_button_prelude(
            self, interaction, self.round_n, self.actor_id
        )
        if enriched_state is None:
            return

        bot = interaction.client
        rate_limiter = getattr(bot, "rate_limiter", None)

        # Step 1: Write dodge shim row to combat_conditions (T-04-16: at most 1 per dodge)
        # expires_round = current_round + 1 (cleared at start of dodger next turn)
        current_round = enriched_state.get("round_number", 0)
        db_path = getattr(getattr(bot, "settings", None), "eldritch_db_path", ":memory:")
        conditions_repo = CombatConditionsRepo(db_path)
        try:
            await conditions_repo.insert(
                channel_id=channel_id_str,
                character_id=self.actor_id,
                condition_kind="dodging",
                applied_round=current_round,
                expires_round=current_round + 1,
            )
        except Exception:  # noqa: BLE001
            log.warning(
                "dodge_conditions_repo_error",
                channel_id=channel_id_str,
                actor_id=self.actor_id,
            )

        # Step 2: apply_effect for ShoeGPT narrative context (D-22 shim)
        # v1: narrative-only -- dm20 has no "dodging" SRD condition (04-RESEARCH.md Q2)
        if rate_limiter is not None:
            await rate_limiter.acquire(channel_id_str)
        try:
            await mcp_tools.apply_effect(
                bot.mcp,
                target=self.actor_id,
                effect="dodging",
            )
        except Exception:  # noqa: BLE001
            # Non-fatal: narrative hint failed; mechanical shim row is still written
            log.warning(
                "dodge_apply_effect_error",
                channel_id=channel_id_str,
                actor_id=self.actor_id,
            )

        # Step 3: next_turn (D-23: dodge ends turn immediately)
        if rate_limiter is not None:
            await rate_limiter.acquire(channel_id_str)
        try:
            await mcp_tools.next_turn(bot.mcp)
            log.bind(
                channel_id=channel_id_str,
                actor_id=self.actor_id,
                action_kind="dodge",
                round_number=self.round_n,
            ).info("dodge_dispatched")
        except Exception:  # noqa: BLE001
            log.warning(
                "dodge_next_turn_error",
                channel_id=channel_id_str,
                actor_id=self.actor_id,
            )
            await interaction.followup.send(
                content="Dodge recorded, but failed to advance turn.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            content="🛡 Dodge stance. Turn ended.",
            ephemeral=True,
        )


# ── CastSpellButton ────────────────────────────────────────────────────────────


class CastSpellButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^cast:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)$",
):
    """Cast Spell button -- v1 stub.

    Encodes: channel_id, actor_id (dm20 character UUID), round (cache-buster).

    v1 behavior: returns an ephemeral message directing players to use Attack
    with weapon='spell' instead. Full spell flow (slots, concentration, AoE)
    is deferred to v2. Still gated by is_actor for defense-in-depth (D-15 note).

    Per CONTEXT Claude Discretion: rendered-and-stubbed (not hidden) to signal
    that v2 spellcasting is coming.
    """

    template = re.compile(r"^cast:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)$")

    def __init__(self, channel_id: int, actor_id: str, round_n: int) -> None:
        # Set attrs BEFORE super().__init__() -- discord.py accesses self.custom_id
        # during DynamicItem.__init__() to validate the template match.
        self.channel_id = channel_id
        self.actor_id = actor_id
        self.round_n = round_n
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="⚗️ Cast Spell",
                custom_id=f"cast:{channel_id}:{actor_id}:{round_n}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> CastSpellButton:
        return cls(
            channel_id=int(match["channel_id"]),
            actor_id=match["actor_id"],
            round_n=int(match["round"]),
        )

    @property
    def custom_id(self) -> str:
        return f"cast:{self.channel_id}:{self.actor_id}:{self.round_n}"

    def _custom_id_str(self) -> str:
        return self.custom_id

    async def _get_enriched_game_state(  # noqa: E501
        self, bot: Any, channel_id_str: str
    ) -> dict[str, Any] | None:
        """Lightweight game state fetch -- see EndTurnButton for full doc."""
        try:
            raw = await mcp_tools.get_game_state(bot.mcp)
            if not isinstance(raw, str):
                raw = str(raw) if raw is not None else ""
            from eldritch_dm.gameplay.game_state_parser import parse_game_state  # noqa: PLC0415
            parsed = parse_game_state(raw)
            combatants = [
                {
                    "id": name.lower().replace(" ", "-"),
                    "name": name,
                    "player_id": None,
                    "hp_current": 0,
                    "hp_max": 0,
                    "ac": 10,
                    "conditions": [],
                }
                for name, _ in parsed.initiative_order
            ]
            return {
                "current_actor_id": (
                    parsed.current_turn.lower().replace(" ", "-")
                    if parsed.current_turn else None
                ),
                "combatants": combatants,
                "round_number": parsed.round_number,
                "in_combat": parsed.in_combat,
            }
        except Exception:  # noqa: BLE001
            log.warning("cast_button_game_state_error", channel_id=channel_id_str)
            return None

    async def callback(self, interaction: discord.Interaction) -> None:
        """v1 stub: gates on is_actor then returns v2 message."""
        # EDM001: defer first
        await interaction.response.defer(thinking=True, ephemeral=True)

        enriched_state, current_actor, channel_id_str = await _combat_button_prelude(
            self, interaction, self.round_n, self.actor_id
        )
        if enriched_state is None:
            return

        # v1 stub: spellcasting in v2
        log.bind(
            channel_id=channel_id_str,
            actor_id=self.actor_id,
            action_kind="cast_spell_stub",
            round_number=self.round_n,
        ).info("cast_spell_stub_invoked")

        await interaction.followup.send(
            content=(
                "⚗️ Spellcasting arrives in v2. "
                "For now, use Attack with weapon='spell' to cast."
            ),
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
    ) -> RiposteButton:
        return cls(
            timer_id=int(match["timer_id"]),
            user_id=int(match["user_id"]),
        )

    def _custom_id_str(self) -> str:
        return f"riposte:{self.timer_id}:{self.user_id}"

    async def callback(self, interaction: discord.Interaction) -> None:
        """Phase 5 Plan 01 — promoted from Phase 2 stub.

        Defers ephemerally, then delegates the gate-and-dispatch sequence to
        `gameplay/reactions.handle_riposte_click`. Plan 02 will wrap that
        handler in a per-channel asyncio.Lock — see the PLAN-02-LOCK-SEAM
        marker in reactions.py for the exact wrap point.

        Dependency injection note: we pass `send_warning` + `WarningKind`
        values into the gameplay-layer helper so that module stays free of
        any `bot/` imports (import-linter contract).
        """
        # D-09: defer first — always
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = log.bind(
            timer_id=self.timer_id,
            user_id=self.user_id,
            custom_id=self._custom_id_str(),
            view_class=type(self).__name__,
        )
        bound_log.info("riposte_button_callback")

        # Lazy imports to avoid cycles (bot ↔ gameplay).
        from eldritch_dm.gameplay.reactions import handle_riposte_click  # noqa: PLC0415

        bot = interaction.client
        repo = getattr(bot, "riposte_timers_repo", None) or getattr(bot, "riposte_timers", None)
        if repo is None:
            bound_log.warning("riposte_callback_no_repo")
            await send_warning(
                interaction,
                WarningKind.INVALID_ACTION,
                reason="Bot not ready.",
            )
            return

        async def _current_round_provider(channel_id: str) -> int:
            """Re-fetch current round from dm20 on each click.

            v1: no caching. Riposte clicks are rare; Plan 02 may add a tiny
            LRU/TTL cache if profiling shows a hotspot. See bot.bot
            current_round_for_channel for the helper.
            """
            getter = getattr(bot, "current_round_for_channel", None)
            if getter is not None:
                return await getter(channel_id)
            # Fallback: parse fresh get_game_state
            from eldritch_dm.gameplay.game_state_parser import parse_game_state  # noqa: PLC0415
            raw = await mcp_tools.get_game_state(bot.mcp)
            text = raw if isinstance(raw, str) else str(raw)
            parsed = parse_game_state(text)
            return parsed.round_number

        await handle_riposte_click(
            interaction=interaction,
            timer_id=self.timer_id,
            expected_user_id=self.user_id,
            repo=repo,
            mcp=bot.mcp,
            rate_limiter=getattr(bot, "rate_limiter", None),
            current_round_provider=_current_round_provider,
            warning_sender=send_warning,
            invalid_action_kind=WarningKind.INVALID_ACTION,
            riposte_expired_kind=WarningKind.RIPOSTE_EXPIRED,
            log=log,
        )


# ── Registration tuple ─────────────────────────────────────────────────────────

DYNAMIC_ITEM_CLASSES: tuple[type[discord.ui.DynamicItem], ...] = (
    ReadyButton,
    DeclareActionButton,
    EndTurnButton,
    AttackButton,
    DodgeButton,
    CastSpellButton,
    RiposteButton,
)
"""Canonical tuple for ``setup_hook`` registration.

Usage in Plan 03's setup_hook::

    bot.add_dynamic_items(*DYNAMIC_ITEM_CLASSES)

Note: ``add_dynamic_items`` alone is sufficient for persistent buttons.
Do NOT also call ``bot.add_view(view, message_id=...)`` for these classes
(see module docstring and 02-RESEARCH.md Pitfall 1).
"""
