"""
CombatCog — COMBAT state UI: combat embed lifecycle, turn-gated action buttons,
EXPLORATION<->COMBAT state-transition wiring.

Implements COMBAT-01..07, COMBAT-12 for Phase 4 Plan 02.

Design:
  - CombatCog holds per-channel EmbedCoalescer + combat Message instances.
  - On EXPLORATION->COMBAT (via orchestrator on_state_change callback):
      _enter_combat: fetch game_state, post combat_embed, create buttons view
      for the current PC actor (or no buttons for monster turns), register
      EmbedCoalescer sharing the per-channel ChannelEditBudget, close
      ExplorationCog's coalescer via bot.close_exploration_coalescer_for().
  - On COMBAT->EXPLORATION (COMBAT-12):
      _exit_combat: edit combat message with view=None (removes buttons),
      close EmbedCoalescer, clear internal state.
  - on_resolved_combat: re-fetch game_state, rebuild embed + view for new
      current actor, call coalescer.update(embed, view=view).
  - Monster turns (D-17, per 04-RESEARCH.md Q3): player_id=None means the
      orchestrator's narrative loop handles the turn. CombatCog posts NO player
      buttons for monster turns — only the embed updates.

Thread safety:
  - All state mutations use the asyncio event loop (no threads).
  - Callbacks wrapped in asyncio.shield in the orchestrator (T-04-08).

Phase 5 Plan 01 update (D-A): the Riposte trigger does NOT live in CombatCog.
It runs in `gameplay/monster_driver.MonsterDriver` on the monster-attack
resolution path (RESEARCH finding #6 corrected the Phase 4 placement).
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from eldritch_dm.bot.coalescer import EmbedCoalescer
from eldritch_dm.bot.embeds import combat_embed
from eldritch_dm.gameplay.turn_gatekeeper import current_actor_from_game_state
from eldritch_dm.logging import get_logger
from eldritch_dm.mcp import tools as mcp_tools
from eldritch_dm.persistence.models import ChannelState

if TYPE_CHECKING:
    from eldritch_dm.bot.bot import EldritchBot

log = get_logger(__name__)


class CombatCog(commands.Cog):
    """Combat state handler: combat embed lifecycle and turn-gated action buttons.

    Registered on the orchestrator in cog_load. Manages one EmbedCoalescer per
    active combat channel, cleaned up on COMBAT->EXPLORATION or cog unload.

    Bot-level helpers used (to avoid cog->cog imports):
        bot.close_exploration_coalescer_for(channel_id) -- async
        bot.close_combat_coalescer_for(channel_id) -- async (for bot wiring tests)
    """

    def __init__(self, bot: EldritchBot) -> None:
        self.bot = bot
        # channel_id -> EmbedCoalescer for the current combat message
        self._coalescers: dict[str, EmbedCoalescer] = {}
        # channel_id -> the combat message (for button removal on exit)
        self._combat_messages: dict[str, discord.Message] = {}
        self._logger = log.bind(cog="combat")

    async def cog_load(self) -> None:
        """Register callbacks on the orchestrator when cog is loaded."""
        if hasattr(self.bot, "orchestrator") and self.bot.orchestrator is not None:
            self.bot.orchestrator.register_state_change_callback(self.on_state_change)
            self.bot.orchestrator.register_resolution_callback(self.on_resolved_combat)
            self._logger.info("combat_cog_callbacks_registered")

    # ── Game state fetcher ────────────────────────────────────────────────────

    async def _fetch_game_state(
        self, channel_id: str  # noqa: ARG002
    ) -> dict[str, Any] | None:
        """Fetch and parse game_state from dm20. Separated for testability.

        Tests patch this method with AsyncMock to avoid real MCP calls.
        """
        try:
            raw = await mcp_tools.get_game_state(self.bot.mcp)
            if not isinstance(raw, str):
                raw = str(raw) if raw is not None else ""
            from eldritch_dm.gameplay.game_state_parser import parse_game_state  # noqa: PLC0415

            parsed = parse_game_state(raw)
            # Build enriched state from parsed data.
            # NOTE: The lightweight parse does not include per-actor HP/AC/conditions
            # (dm20's get_game_state returns markdown, not JSON). CombatCog synthesizes
            # combatant dicts from the initiative_order list with default HP/AC.
            # A future phase can enrich with get_character calls per actor.
            combatants: list[dict[str, Any]] = []
            for name, init_score in parsed.initiative_order:
                actor_id = name.lower().replace(" ", "-")
                combatants.append({
                    "id": actor_id,
                    "name": name,
                    "player_id": None,  # unknown from parse; real path uses get_character
                    "hp_current": 0,  # unknown without per-actor enrichment
                    "hp_max": 0,
                    "ac": 10,  # default AC
                    "conditions": [],
                    "_initiative": init_score,
                })

            current_actor_id = (
                parsed.current_turn.lower().replace(" ", "-")
                if parsed.current_turn else None
            )

            return {
                "current_actor_id": current_actor_id,
                "combatants": combatants,
                "round_number": parsed.round_number,
                "in_combat": parsed.in_combat,
            }
        except Exception:  # noqa: BLE001
            self._logger.exception("combat_cog_fetch_game_state_error")
            return None

    # ── View builder ──────────────────────────────────────────────────────────

    def _build_combat_view(
        self,
        channel_id: str,
        actor_id: str,
        round_n: int,
        current_actor: dict[str, Any] | None,
    ) -> discord.ui.View | None:
        """Build a View with combat action buttons for the current PC actor.

        Returns None (no buttons) for monster turns (player_id is None).
        """
        if current_actor is None or current_actor.get("player_id") is None:
            # Monster turn — no player UI (D-17)
            return None

        from eldritch_dm.bot.dynamic_items import (  # noqa: PLC0415
            AttackButton,
            CastSpellButton,
            DodgeButton,
            EndTurnButton,
        )

        channel_int = int(channel_id)
        view = discord.ui.View(timeout=None)
        view.add_item(AttackButton(channel_id=channel_int, actor_id=actor_id, round_n=round_n))
        view.add_item(DodgeButton(channel_id=channel_int, actor_id=actor_id, round_n=round_n))
        view.add_item(EndTurnButton(channel_id=channel_int, actor_id=actor_id, round_n=round_n))
        view.add_item(CastSpellButton(channel_id=channel_int, actor_id=actor_id, round_n=round_n))
        return view

    # ── State change callbacks ────────────────────────────────────────────────

    async def on_state_change(
        self,
        channel_id: str,
        old_state: ChannelState,
        new_state: ChannelState,
    ) -> None:
        """Dispatched by the orchestrator on EXPLORATION<->COMBAT transitions.

        Routes to _enter_combat (EXPLORATION->COMBAT) or _exit_combat (COMBAT->EXPLORATION).
        """
        if old_state == ChannelState.EXPLORATION and new_state == ChannelState.COMBAT:
            await self._enter_combat(channel_id)
        elif old_state == ChannelState.COMBAT and new_state == ChannelState.EXPLORATION:
            await self._exit_combat(channel_id)

    async def _enter_combat(self, channel_id: str) -> None:
        """Post fresh combat_embed + register coalescer on EXPLORATION->COMBAT.

        Steps:
          1. Fetch game_state from dm20.
          2. Build combat_embed with all combatants.
          3. Build View for current PC actor (or None for monster turn).
          4. Post message to channel.
          5. Close ExplorationCog's coalescer for this channel.
          6. Register EmbedCoalescer for the combat message.
        """
        self._logger.info("combat_enter", channel_id=channel_id)

        # Step 1: Fetch game_state
        game_state = await self._fetch_game_state(channel_id)
        if game_state is None:
            self._logger.warning("combat_enter_no_game_state", channel_id=channel_id)
            return

        # Step 2: Build combat_embed
        combatants = game_state.get("combatants", [])
        round_n = game_state.get("round_number", 1)
        current_actor_id = game_state.get("current_actor_id") or ""
        current_actor = current_actor_from_game_state(game_state)

        # Build initiative rows as 6-tuples (v2 format)
        current_actor_name = current_actor["name"] if current_actor else ""
        initiative_rows = []
        for c in combatants:
            initiative_rows.append((
                c["name"],
                c.get("_initiative", 0),
                c.get("hp_current", 0),
                c.get("hp_max", 0),
                c.get("ac", 10),
                c.get("conditions", []),
            ))

        embed = combat_embed(
            round_n=round_n,
            current_actor=current_actor_name,
            initiative=initiative_rows,
        )

        # Step 3: Build view
        view = self._build_combat_view(
            channel_id=channel_id,
            actor_id=current_actor_id,
            round_n=round_n,
            current_actor=current_actor,
        )

        # Step 4: Post to channel
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            self._logger.warning("combat_enter_channel_not_found", channel_id=channel_id)
            return

        send_kwargs: dict[str, Any] = {"embed": embed}
        if view is not None:
            send_kwargs["view"] = view
        else:
            send_kwargs["view"] = None

        msg = await channel.send(**send_kwargs)  # type: ignore[union-attr]
        self._combat_messages[channel_id] = msg

        # Step 5: Close ExplorationCog's coalescer
        close_fn = getattr(self.bot, "close_exploration_coalescer_for", None)
        if close_fn is not None:
            await close_fn(channel_id)

        # Step 6: Register EmbedCoalescer
        budget = self.bot.get_channel_edit_budget(channel_id)
        coalescer = EmbedCoalescer(
            msg,
            rate_limit_seconds=self.bot.settings.embed_edit_rate_limit,
            channel_budget=budget,
        )

        # Close any existing combat coalescer for this channel
        if channel_id in self._coalescers:
            await self._coalescers[channel_id].close()

        self._coalescers[channel_id] = coalescer

        self._logger.info(
            "combat_embed_posted",
            channel_id=channel_id,
            round_n=round_n,
            current_actor=current_actor_name,
            message_id=msg.id,
        )

    async def _exit_combat(self, channel_id: str) -> None:
        """Close coalescer + remove buttons from combat message on COMBAT->EXPLORATION.

        COMBAT-12: combat end is fully handled here.

        Steps:
          1. Edit combat message with view=None (removes buttons).
          2. Close EmbedCoalescer.
          3. Clear internal state for this channel.
        """
        self._logger.info("combat_exit", channel_id=channel_id)

        # Step 1: Remove buttons from combat message
        msg = self._combat_messages.pop(channel_id, None)
        if msg is not None:
            try:
                await msg.edit(view=None)
            except Exception:  # noqa: BLE001
                self._logger.warning(
                    "combat_exit_message_edit_failed",
                    channel_id=channel_id,
                )

        # Step 2: Close EmbedCoalescer
        coalescer = self._coalescers.pop(channel_id, None)
        if coalescer is not None:
            try:
                await coalescer.close()
            except Exception:  # noqa: BLE001
                self._logger.warning(
                    "combat_exit_coalescer_close_failed",
                    channel_id=channel_id,
                )

        self._logger.info("combat_exited", channel_id=channel_id)

    # ── Resolution callback ───────────────────────────────────────────────────

    async def on_resolved_combat(
        self,
        channel_id: str,
        action_payload: dict[str, Any],
    ) -> None:
        """Called by the orchestrator when a narrative resolves during COMBAT.

        Re-fetches game_state, re-renders embed with new current actor + HP/conditions,
        and calls coalescer.update(embed, view=view).

        Only acts when session state is COMBAT (guards against stale callbacks
        during transition windows).
        """
        # Guard: only update if session is COMBAT
        session = await self.bot.channel_sessions.get(channel_id)
        if session is None or session.state != ChannelState.COMBAT:
            return

        coalescer = self._coalescers.get(channel_id)
        if coalescer is None:
            self._logger.debug(
                "on_resolved_combat_no_coalescer",
                channel_id=channel_id,
            )
            return

        # Re-fetch game_state (read-only — no rate limiter)
        game_state = await self._fetch_game_state(channel_id)
        if game_state is None:
            return

        # Rebuild embed + view for new current actor
        combatants = game_state.get("combatants", [])
        round_n = game_state.get("round_number", 1)
        current_actor_id = game_state.get("current_actor_id") or ""
        current_actor = current_actor_from_game_state(game_state)

        current_actor_name = current_actor["name"] if current_actor else ""

        initiative_rows = []
        for c in combatants:
            initiative_rows.append((
                c["name"],
                c.get("_initiative", 0),
                c.get("hp_current", 0),
                c.get("hp_max", 0),
                c.get("ac", 10),
                c.get("conditions", []),
            ))

        embed = combat_embed(
            round_n=round_n,
            current_actor=current_actor_name,
            initiative=initiative_rows,
        )

        view = self._build_combat_view(
            channel_id=channel_id,
            actor_id=current_actor_id,
            round_n=round_n,
            current_actor=current_actor,
        )

        await coalescer.update(embed, view=view)

        self._logger.info(
            "combat_embed_refreshed",
            channel_id=channel_id,
            round_n=round_n,
            current_actor=current_actor_name,
            action_type=action_payload.get("type") or action_payload.get("action_type", "?"),
        )

    # ── Cog unload ────────────────────────────────────────────────────────────

    async def cog_unload(self) -> None:
        """Close all coalescers on cog unload."""
        for coalescer in list(self._coalescers.values()):
            try:
                await coalescer.close()
            except Exception:  # noqa: BLE001
                pass
        self._coalescers.clear()


async def setup(bot: EldritchBot) -> None:
    """discord.py extension entry point — called by bot.load_extension(...)."""
    await bot.add_cog(CombatCog(bot))
