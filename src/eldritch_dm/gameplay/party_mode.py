"""
PartyModeOrchestrator — per-channel asyncio.Task that drives the dm20 pop/resolve loop.

Implements the EXPLORATION/COMBAT game loop (D-02, D-03, D-05, D-06) per Phase 4 Plan 01.

Loop behavior (D-03 pseudocode):
  while not stopping:
      action = await party_pop_action(mcp)  # returns immediately if empty
      if action.empty:
          await sleep(poll_interval_s)
          continue
      await rate_limiter.acquire(channel_id)  # mutating — gate it
      await party_thinking(mcp, message="ShoeGPT consults the ancient scrolls…")
      if action.has turn_id (combat-relevant):
          prefetch = await party_get_prefetch(turn_id, ...)  # best-effort
      narrative = on_resolved callback (Discord-side generates narration)
      await rate_limiter.acquire(channel_id)
      await party_resolve_action(mcp, turn_id=action.id, narration=narrative)
      for expired_batch in batch_coordinator.tick(now):
          await player_action(...)  # send batch to claudmaster

  Every K-th tick (~1s): call get_game_state and compare in_combat flag;
  fire on_state_change callback when transition detected.

Architecture (D-05):
  - One asyncio.Task per active EXPLORATION/COMBAT channel.
  - Started by setup_hook for all EXPLORATION/COMBAT rows on boot.
  - Started by on_session_state_change bus when state transitions to EXPLORATION.
  - Stopped by stop_orchestrator_for_channel when state returns to LOBBY.

Rate limiting (D-28, OPS-03):
  - Mutating calls (party_thinking, party_resolve_action, player_action for
    batch flush) go through ChannelRateLimiter.acquire(channel_id).
  - Read calls (party_pop_action, get_game_state) bypass the limiter.

Phase 4 Plan 01.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from eldritch_dm.gameplay.exploration_batch import (
    BatchCoordinator,
    serialize_batch_payload,
)
from eldritch_dm.gameplay.game_state_parser import parse_game_state
from eldritch_dm.logging import get_logger
from eldritch_dm.mcp import tools as mcp_tools
from eldritch_dm.mcp.rate_limit import ChannelRateLimiter
from eldritch_dm.persistence.models import ChannelState

log = get_logger(__name__)

# Number of pop_action ticks between get_game_state calls (every K ticks ≈ 1Hz at 250ms)
_COMBAT_CHECK_EVERY_N_POLLS = 4


class PartyModeOrchestrator:
    """Per-channel orchestrator driving the dm20 party-mode pop/resolve loop.

    One instance is shared by all channels. Internally manages one asyncio.Task
    per active channel. Call start_orchestrator_for_channel / stop_orchestrator_for_channel
    to control per-channel lifecycle.

    Args:
        mcp: MCPClient instance (shared with the rest of the bot).
        rate_limiter: ChannelRateLimiter for OPS-03 mutating-call throttling.
        batch_coordinator: BatchCoordinator for EXPLORE-06 action batching.
        channel_sessions: ChannelSessionRepo for reading/writing session state.
        poll_interval_ms: ms between party_pop_action calls (default 250, D-04).
        combat_check_every_n_polls: Number of pop ticks between game_state checks.
        clock: Monotonic clock (injectable for testing).
        sleep: Async sleep (injectable for testing).
    """

    def __init__(
        self,
        mcp: Any,  # MCPClient — typed as Any to avoid circular import
        rate_limiter: ChannelRateLimiter,
        batch_coordinator: BatchCoordinator,
        channel_sessions: Any,  # ChannelSessionRepo
        *,
        monster_driver: Any = None,  # Phase 5 Plan 01: MonsterDriver (optional)
        poll_interval_ms: int = 250,
        combat_check_every_n_polls: int = _COMBAT_CHECK_EVERY_N_POLLS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._mcp = mcp
        self._rate_limiter = rate_limiter
        self._batch_coordinator = batch_coordinator
        self._channel_sessions = channel_sessions
        self._monster_driver = monster_driver
        self._poll_interval_s = poll_interval_ms / 1000.0
        self._combat_check_every_n = combat_check_every_n_polls
        self._clock = clock
        self._sleep = sleep

        # channel_id → asyncio.Task
        self._tasks: dict[str, asyncio.Task] = {}
        # channel_id → (campaign_name, session_id)
        self._channel_meta: dict[str, tuple[str, str]] = {}
        # channel_id → last known in_combat state (None = unknown)
        self._last_combat_state: dict[str, bool | None] = {}
        # channel_id → last known ChannelState (for cadence acceleration)
        self._last_channel_state: dict[str, ChannelState] = {}
        # Phase 5 Plan 01: idempotency key per channel for monster-turn dispatch
        # (round_number, monster_character_id) — prevents double-fires when the
        # same monster turn appears on two consecutive COMBAT ticks.
        self._last_monster_drive: dict[str, tuple[int, str]] = {}

        # Registered callbacks (list allows multiple cogs to register)
        self._resolution_callbacks: list[
            Callable[[str, dict[str, Any]], Awaitable[None]]
        ] = []
        self._state_change_callbacks: list[
            Callable[[str, ChannelState, ChannelState], Awaitable[None]]
        ] = []

    # ── Poll cadence ─────────────────────────────────────────────────────────

    def _get_poll_cadence(self, state: ChannelState) -> int:
        """Return number of pop_action ticks between game_state checks.

        COMBAT state accelerates to every tick (cadence=1) so the orchestrator
        catches COMBAT->EXPLORATION transitions within one 250ms cycle.

        EXPLORATION state uses the default _combat_check_every_n (4 ticks).
        """
        if state == ChannelState.COMBAT:
            return 1  # Check every tick in COMBAT (D-17, COMBAT-12 fast detection)
        return self._combat_check_every_n

    # ── Callback registration ─────────────────────────────────────────────────

    def register_resolution_callback(
        self,
        cb: Callable[[str, dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Register a callback invoked when a narrative is resolved.

        Args:
            cb: Async callable(channel_id: str, action: dict) → None.
                Called with the popped action dict after party_resolve_action.
        """
        self._resolution_callbacks.append(cb)

    def register_state_change_callback(
        self,
        cb: Callable[[str, ChannelState, ChannelState], Awaitable[None]],
    ) -> None:
        """Register a callback invoked when EXPLORATION↔COMBAT state changes.

        Args:
            cb: Async callable(channel_id: str, old_state: ChannelState,
                               new_state: ChannelState) → None.
        """
        self._state_change_callbacks.append(cb)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start_orchestrator_for_channel(
        self,
        channel_id: str,
        campaign_name: str,
        session_id: str,
    ) -> asyncio.Task:
        """Start the pop/resolve loop for a channel.

        Idempotent: returns the existing task if one is already running.

        Args:
            channel_id: Discord channel snowflake string.
            campaign_name: dm20 campaign name (for logging and batch payloads).
            session_id: Claudmaster session ID (for player_action calls).

        Returns:
            The asyncio.Task driving the loop for this channel.
        """
        if channel_id in self._tasks and not self._tasks[channel_id].done():
            log.info(
                "orchestrator_already_running",
                channel_id=channel_id,
                campaign_name=campaign_name,
            )
            return self._tasks[channel_id]

        self._channel_meta[channel_id] = (campaign_name, session_id)
        self._last_combat_state[channel_id] = None
        self._last_channel_state[channel_id] = ChannelState.EXPLORATION

        task = asyncio.create_task(
            self._loop(channel_id, campaign_name, session_id),
            name=f"orchestrator:{channel_id}",
        )
        self._tasks[channel_id] = task
        log.info(
            "orchestrator_started",
            channel_id=channel_id,
            campaign_name=campaign_name,
            session_id=session_id,
        )
        return task

    async def stop_orchestrator_for_channel(self, channel_id: str) -> None:
        """Cancel the loop task for a channel and clean up.

        Idempotent: no-op if no task is running for this channel.

        Args:
            channel_id: Discord channel snowflake string.
        """
        task = self._tasks.pop(channel_id, None)
        self._channel_meta.pop(channel_id, None)
        self._last_combat_state.pop(channel_id, None)
        self._last_channel_state.pop(channel_id, None)

        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            log.info("orchestrator_stopped", channel_id=channel_id)

    async def stop_all(self) -> None:
        """Cancel all per-channel orchestrator tasks (called on bot.close())."""
        channel_ids = list(self._tasks.keys())
        for channel_id in channel_ids:
            await self.stop_orchestrator_for_channel(channel_id)
        log.info("orchestrator_all_stopped", count=len(channel_ids))

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def _loop(
        self,
        channel_id: str,
        campaign_name: str,
        session_id: str,
    ) -> None:
        """The pop/thinking/resolve loop for a single channel.

        Runs until cancelled. Handles:
          - party_pop_action polling (250ms when empty)
          - party_thinking → party_resolve_action on non-empty actions
          - party_get_prefetch for combat-relevant actions (turn_id present)
          - Combat-trigger watcher (every K ticks, ~1Hz)
          - Deadline-based batch flushing via batch_coordinator.tick()

        All mutating dm20 calls go through rate_limiter.acquire().
        Reads (party_pop_action, get_game_state) bypass the limiter.
        """
        bound_log = log.bind(
            channel_id=channel_id,
            campaign_name=campaign_name,
            session_id=session_id,
        )
        bound_log.info("orchestrator_loop_started")

        poll_counter = 0

        try:
            while True:
                # ── Deadline-driven batch flush ──────────────────────────────
                await self._flush_expired_batches(channel_id, session_id, bound_log)

                # ── Pop an action ─────────────────────────────────────────────
                try:
                    # party_pop_action is a READ — no rate limit
                    pop_result = await mcp_tools.party_pop_action(self._mcp)
                except Exception:
                    bound_log.exception("orchestrator_pop_error")
                    await self._sleep(1.0)
                    continue

                poll_counter += 1

                # ── Combat-state watcher ──────────────────────────────────────
                # Cadence accelerates to 1 (every tick) when in COMBAT state
                # so we catch COMBAT->EXPLORATION transitions within 250ms.
                last_state = self._last_channel_state.get(channel_id, ChannelState.EXPLORATION)
                cadence = self._get_poll_cadence(last_state)
                if poll_counter % cadence == 0:
                    await self._check_state_transition(
                        channel_id, campaign_name, session_id, bound_log
                    )

                # ── Empty queue → sleep and retry ─────────────────────────────
                if pop_result.get("empty", True):
                    await self._sleep(self._poll_interval_s)
                    continue

                # ── Non-empty action — process it ─────────────────────────────
                action = pop_result.get("action", pop_result)
                action_id = action.get("id") or action.get("turn_id")
                action_kind = action.get("action_type", "player_intent")

                bound_log.info(
                    "orchestrator_action_popped",
                    action_id=action_id,
                    action_kind=action_kind,
                )

                # party_thinking is MUTATING — rate-limit it
                try:
                    await self._rate_limiter.acquire(channel_id)
                    await mcp_tools.party_thinking(
                        self._mcp,
                        message="ShoeGPT consults the ancient scrolls…",
                    )
                except Exception:
                    bound_log.warning("orchestrator_party_thinking_error")

                # party_get_prefetch for combat-relevant actions (turn_id present)
                if (
                    "turn_id" in action
                    or "combat_turn_id" in action
                    or "encounter_action" in action
                ):
                    turn_id = (
                        action.get("turn_id")
                        or action.get("combat_turn_id")
                        or action.get("id")
                        or ""
                    )
                    try:
                        # party_get_prefetch is READ (fetches prefetch cache) — no rate limit
                        await mcp_tools.party_get_prefetch(
                            self._mcp,
                            turn_id=turn_id,
                        )
                        bound_log.info("orchestrator_prefetch_ok", turn_id=turn_id)
                    except Exception:
                        bound_log.warning("orchestrator_prefetch_miss", turn_id=turn_id)

                # Invoke resolution callbacks (ExplorationCog / CombatCog render)
                narrative = ""
                for cb in self._resolution_callbacks:
                    try:
                        # Wrap callback in asyncio.shield so cancellation doesn't
                        # tear down a rendering callback mid-execution (T-04-08)
                        await asyncio.shield(cb(channel_id, action))
                    except asyncio.CancelledError:
                        raise  # re-raise CancelledError — we're stopping
                    except Exception:
                        bound_log.warning("orchestrator_resolution_callback_error")

                # party_resolve_action is MUTATING — rate-limit it
                turn_id_for_resolve = (
                    action.get("turn_id")
                    or action.get("id")
                    or ""
                )
                if turn_id_for_resolve:
                    try:
                        await self._rate_limiter.acquire(channel_id)
                        await mcp_tools.party_resolve_action(
                            self._mcp,
                            turn_id=turn_id_for_resolve,
                            narration=narrative or "The party's action is noted.",
                        )
                        bound_log.info(
                            "orchestrator_resolved",
                            turn_id=turn_id_for_resolve,
                        )
                    except Exception:
                        bound_log.exception("orchestrator_resolve_error")

        except asyncio.CancelledError:
            bound_log.info("orchestrator_loop_cancelled")
            raise
        except Exception:
            bound_log.exception("orchestrator_loop_crashed")
            raise

    async def _flush_expired_batches(
        self,
        channel_id: str,
        session_id: str,
        bound_log: Any,
    ) -> None:
        """Flush any expired batches for the given channel via player_action."""
        now = datetime.now(UTC)
        expired = self._batch_coordinator.tick(now)

        for ch_id, batch in expired:
            if ch_id != channel_id:
                continue  # different channel's batch (should not happen but be safe)
            if not batch.submissions:
                continue

            payload = serialize_batch_payload(batch)
            bound_log.info(
                "orchestrator_batch_flush",
                n_intents=len(batch.submissions),
            )
            try:
                # player_action is MUTATING — rate-limit it
                await self._rate_limiter.acquire(channel_id)
                await mcp_tools.player_action(
                    self._mcp,
                    session_id=session_id,
                    action="batch_intents",
                    context=payload,
                )
            except Exception:
                bound_log.exception("orchestrator_batch_send_error")

    async def _check_state_transition(
        self,
        channel_id: str,
        campaign_name: str,
        session_id: str,
        bound_log: Any,
    ) -> None:
        """Check get_game_state and fire callbacks on EXPLORATION↔COMBAT transitions."""
        try:
            # get_game_state is READ — no rate limit
            raw = await mcp_tools.get_game_state(self._mcp)
            if not isinstance(raw, str):
                raw = str(raw) if raw is not None else ""
            state = parse_game_state(raw)
        except Exception:
            bound_log.warning("orchestrator_game_state_error")
            return

        last_combat = self._last_combat_state.get(channel_id)

        if last_combat is None:
            # First check — initialize without firing callbacks
            self._last_combat_state[channel_id] = state.in_combat
            return

        if state.in_combat == last_combat:
            return  # No change

        # State transition detected
        # last_combat was the PREVIOUS state; state.in_combat is the NEW state
        # old_state = the state we just LEFT (based on last_combat value before update)
        self._last_combat_state[channel_id] = state.in_combat

        old_state = ChannelState.COMBAT if last_combat else ChannelState.EXPLORATION
        new_state = ChannelState.COMBAT if state.in_combat else ChannelState.EXPLORATION

        # Update cadence tracker so loop uses correct poll cadence next tick
        self._last_channel_state[channel_id] = new_state

        bound_log.info(
            "orchestrator_state_transition",
            old_state=old_state,
            new_state=new_state,
            round_number=state.round_number,
        )

        # Update channel_sessions DB
        try:
            await self._channel_sessions.set_state(channel_id, new_state)
        except Exception:
            bound_log.warning("orchestrator_state_db_update_error")

        # Fire all registered callbacks concurrently via asyncio.gather so one
        # cog raising does not prevent others from running (T-04-08, COMBAT-11).
        if self._state_change_callbacks:
            results = await asyncio.gather(
                *[
                    asyncio.shield(cb(channel_id, old_state, new_state))
                    for cb in self._state_change_callbacks
                ],
                return_exceptions=True,
            )
            for i, result in enumerate(results):
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    bound_log.warning(
                        "orchestrator_state_change_callback_error",
                        callback_index=i,
                        error=str(result),
                    )


    # ── Phase 5 Plan 01: monster-turn dispatch ────────────────────────────────

    async def maybe_drive_monster_turn(
        self,
        *,
        channel_id: str,
        campaign_name: str,
        current_actor: dict[str, Any],
        round_number: int,
    ) -> bool:
        """Delegate the current turn to MonsterDriver if it's a monster's turn.

        Idempotent per `(channel_id, round_number, current_actor.character_id)`:
        calling twice for the same key is a no-op so consecutive COMBAT ticks
        don't double-fire the driver.

        Returns:
            True if the driver was invoked; False if skipped (PC turn, no
            driver wired, or duplicate dispatch).
        """
        if self._monster_driver is None:
            return False
        if current_actor.get("player_id") is not None:
            return False  # PC turn — not driver's job

        monster_id = current_actor.get("character_id", "")
        key = (round_number, monster_id)
        last = self._last_monster_drive.get(channel_id)
        if last == key:
            return False  # already dispatched for this (round, monster)

        self._last_monster_drive[channel_id] = key
        try:
            await self._monster_driver.drive(
                channel_id=channel_id,
                campaign_name=campaign_name,
                current_actor=current_actor,
            )
            return True
        except Exception:  # noqa: BLE001
            log.exception(
                "orchestrator_monster_driver_error",
                channel_id=channel_id,
                monster_id=monster_id,
                round_number=round_number,
            )
            return False


def start_orchestrator_for_channel(
    orchestrator: PartyModeOrchestrator,
    channel_id: str,
    campaign_name: str,
    session_id: str,
) -> Awaitable[asyncio.Task]:
    """Module-level helper for starting an orchestrator task.

    Thin wrapper for convenience import. Prefer calling orchestrator.start_orchestrator_for_channel
    directly.
    """
    return orchestrator.start_orchestrator_for_channel(channel_id, campaign_name, session_id)


def stop_orchestrator_for_channel(
    orchestrator: PartyModeOrchestrator,
    channel_id: str,
) -> Awaitable[None]:
    """Module-level helper for stopping an orchestrator task."""
    return orchestrator.stop_orchestrator_for_channel(channel_id)
