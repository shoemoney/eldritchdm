"""
MonsterDriver — drives monster-actor combat turns.

Phase 5 Plan 01 ships the MINIMAL random-target driver per user decision D-B:
when the current actor in combat is a monster (player_id is None), this driver
picks a uniformly-random eligible PC target from the initiative list, calls
dm20__combat_action(action='attack', attacker=monster, target=pc), parses the
text outcome via `combat_outcome_parser.parse_combat_outcome`, and on
MISS / NATURAL_ONE awaits `reactions.check_riposte_eligibility` and (if
non-None) `reactions.surface_riposte_button`. Regardless of outcome, the
driver calls `next_turn` to advance the initiative pointer.

# Phase 5 v1: random PC targeting (user decision D-B). v2 may add
# Claudmaster-driven smart targeting; see REQUIREMENTS REACT-* family.

Phase 4 left the monster-turn driver path unimplemented (Phase 4 SUMMARY +
Phase 5 RESEARCH finding #6). Plan 01 closes that gap with the minimum needed
to ship Riposte. Smarter behaviors (target prioritization, ability use,
multi-attack) are explicitly out of scope.

The driver does NOT post to Discord directly — it calls into
`reactions.surface_riposte_button` which takes a `channel` argument the
caller provides. The driver receives `channel_resolver` so the caller (bot
setup_hook) can pass `bot.get_channel(int(channel_id))`.

PartyModeOrchestrator wiring: the COMBAT-tick branch detects monster turns
and delegates here. The orchestrator tracks the last-driven (channel_id,
round, monster_id) tuple to prevent double-fires on consecutive ticks.

Import-linter discipline: this module lives under `gameplay/`, so it CANNOT
import from `bot/`. The button factory and warning sender used by
`reactions.surface_riposte_button` must be plumbed from the caller.

Phase 5 Plan 01.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

import discord

from eldritch_dm.gameplay.combat_outcome_parser import (
    AttackOutcome,
    parse_combat_outcome,
)
from eldritch_dm.gameplay.reactions import (
    check_riposte_eligibility,
    surface_riposte_button,
)
from eldritch_dm.logging import get_logger
from eldritch_dm.mcp import tools as mcp_tools

if TYPE_CHECKING:
    from eldritch_dm.persistence.pc_classes_repo import PCClassesRepo
    from eldritch_dm.persistence.riposte_timers_repo import RiposteTimerRepo


log = get_logger(__name__)


class MonsterDriver:
    """Minimal random-target driver for monster-actor combat turns.

    The driver consumes a `state_provider` callable that returns an enriched
    game-state dict shaped:

        {
          "round_number": int,
          "current_actor": {"character_id": str, "player_id": str|None, "name": str, ...},
          "pcs": [
              {"character_id": str, "user_id": int, "player_id": str, "name": str, ...},
              ...
          ],
        }

    This decouples the driver from the markdown-text parser. The caller is
    responsible for assembling this dict from `get_game_state` plus its own
    channel/player mapping (CombatCog already does similar enrichment).

    Args:
        mcp: MCPClient instance.
        rate_limiter: ChannelRateLimiter for mutating MCP call throttling.
        pc_classes_repo: PCClassesRepo for Riposte eligibility lookup.
        riposte_timers_repo: RiposteTimerRepo for the timer-row INSERT.
        button_factory: Callable(timer_id: int, user_id: int) → discord.ui.Item
            produces the RiposteButton instance. Passed in so this module
            stays free of `bot/` imports (import-linter contract).
        state_provider: async Callable(channel_id, campaign_name) → enriched
            state dict (as above). Caller injects from CombatCog / orchestrator.
        channel_resolver: Callable(channel_id_str) → discord.TextChannel | None.
            Caller wires this to `bot.get_channel(int(channel_id))`.
        ttl_seconds: Riposte window in seconds (default 8, settings driven).
        random_choice: Callable for picking the target (injectable for tests).
    """

    def __init__(
        self,
        *,
        mcp: Any,
        rate_limiter: Any,
        pc_classes_repo: PCClassesRepo,
        riposte_timers_repo: RiposteTimerRepo,
        button_factory: Callable[[int, int], discord.ui.Item],
        state_provider: Callable[[str, str], Awaitable[dict[str, Any]]],
        channel_resolver: Callable[[str], Any],
        ttl_seconds: int = 8,
        random_choice: Callable[[Sequence[Any]], Any] = random.choice,
        eligibility_set: frozenset[tuple[str, str]] | None = None,
    ) -> None:
        self._mcp = mcp
        self._rate_limiter = rate_limiter
        self._pc_classes_repo = pc_classes_repo
        self._riposte_timers_repo = riposte_timers_repo
        self._button_factory = button_factory
        self._state_provider = state_provider
        self._channel_resolver = channel_resolver
        self._ttl_seconds = ttl_seconds
        self._random_choice = random_choice
        # Phase 8 D-38: loader-resolved frozenset. None → reactions falls back
        # to the in-module ELIGIBLE_CLASS_SUBCLASSES constant (v1.0 behavior).
        self._eligibility_set = eligibility_set
        self._log = log.bind(component="MonsterDriver")

    async def drive(
        self,
        *,
        channel_id: str,
        campaign_name: str,
        current_actor: dict[str, Any],
    ) -> None:
        """Drive one monster-actor combat turn.

        Args:
            channel_id: Discord channel snowflake string.
            campaign_name: dm20 campaign name (for state_provider).
            current_actor: Enriched actor dict — must have `character_id` and
                `player_id`. If `player_id is not None`, this is a PC turn and
                the driver no-ops (defense-in-depth — caller should never
                invoke for a PC turn).
        """
        bound_log = self._log.bind(
            channel_id=channel_id,
            monster_id=current_actor.get("character_id"),
            action_kind="monster_attack",
        )

        # Defense-in-depth: PC turns are not the driver's job
        if current_actor.get("player_id") is not None:
            bound_log.debug("monster_driver_skipped_pc_turn")
            return

        # Fetch enriched state from caller-provided provider
        state = await self._state_provider(channel_id, campaign_name)
        round_number = state.get("round_number", 0)
        bound_log = bound_log.bind(round_number=round_number)

        monster_id = current_actor.get("character_id", "")
        pcs: list[dict[str, Any]] = list(state.get("pcs", []))
        # Exclude the monster itself (defensive — provider should already exclude)
        targets = [p for p in pcs if p.get("character_id") != monster_id]

        if not targets:
            bound_log.warning("monster_driver_no_eligible_target")
            # Still advance the turn so combat doesn't deadlock
            await self._advance_turn(channel_id, bound_log)
            return

        # D-B: uniformly-random target
        chosen: dict[str, Any] = self._random_choice(targets)
        chosen_id = chosen.get("character_id", "")
        bound_log = bound_log.bind(target_id=chosen_id)
        bound_log.info("monster_driver_target_chosen")

        # Acquire rate-limit slot for the mutating MCP call
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire(channel_id)

        try:
            result = await mcp_tools.combat_action(
                self._mcp,
                action="attack",
                attacker=monster_id,
                target=chosen_id,
            )
        except Exception:  # noqa: BLE001
            bound_log.exception("monster_driver_combat_action_error")
            # Try to advance the turn anyway to avoid deadlock
            await self._advance_turn(channel_id, bound_log)
            return

        # Parse outcome — result may be dict-with-text or plain str
        text = self._extract_text(result)
        outcome = parse_combat_outcome(text)
        bound_log.info(
            "monster_driver_attack_resolved",
            outcome=str(outcome) if outcome else None,
        )

        # On MISS / NATURAL_ONE — surface a Riposte button if PC is eligible
        if outcome in (AttackOutcome.MISS, AttackOutcome.NATURAL_ONE):
            await self._maybe_surface_riposte(
                channel_id=channel_id,
                round_number=round_number,
                monster_id=monster_id,
                target=chosen,
                bound_log=bound_log,
            )

        # Always advance the turn
        await self._advance_turn(channel_id, bound_log)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_text(result: Any) -> str:
        """Normalize dm20 result to a string — sometimes dict, sometimes str."""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for key in ("text", "narration", "result", "message", "output"):
                v = result.get(key)
                if isinstance(v, str):
                    return v
            return str(result)
        return str(result) if result is not None else ""

    async def _maybe_surface_riposte(
        self,
        *,
        channel_id: str,
        round_number: int,
        monster_id: str,
        target: dict[str, Any],
        bound_log: Any,
    ) -> None:
        """Check eligibility and surface the Riposte button if eligible."""
        target_character_id = target.get("character_id", "")
        target_user_id = target.get("user_id")
        if target_user_id is None:
            bound_log.debug("riposte_skipped_no_user_id")
            return
        try:
            target_user_id_int = int(target_user_id)
        except (TypeError, ValueError):
            bound_log.warning("riposte_skipped_bad_user_id", user_id=target_user_id)
            return

        eligibility = await check_riposte_eligibility(
            channel_id=channel_id,
            character_id=target_character_id,
            user_id=target_user_id_int,
            primary_weapon=target.get("primary_weapon"),
            current_round=round_number,
            pc_classes_repo=self._pc_classes_repo,
            riposte_timers_repo=self._riposte_timers_repo,
            eligibility_set=self._eligibility_set,
        )
        if eligibility is None:
            bound_log.debug("riposte_not_eligible")
            return

        channel = self._channel_resolver(channel_id)
        if channel is None:
            bound_log.warning("riposte_channel_resolve_failed")
            return

        try:
            timer_id = await surface_riposte_button(
                channel=channel,
                eligibility=eligibility,
                monster_uuid=monster_id,
                round_number=round_number,
                channel_id=channel_id,
                repo=self._riposte_timers_repo,
                button_factory=self._button_factory,
                ttl_seconds=self._ttl_seconds,
                log=bound_log,
            )
            bound_log.info("riposte_surfaced_ok", timer_id=timer_id)
        except Exception:  # noqa: BLE001
            bound_log.exception("riposte_surface_failed")

    async def _advance_turn(self, channel_id: str, bound_log: Any) -> None:
        """Best-effort `next_turn` call to keep combat moving."""
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire(channel_id)
        try:
            await mcp_tools.next_turn(self._mcp)
            bound_log.info("monster_driver_next_turn_ok")
        except Exception:  # noqa: BLE001
            bound_log.exception("monster_driver_next_turn_error")
