"""BudgetOwnerNotifier — Discord DM-to-owner on budget / degraded-mode events.

Phase 22 / OPQOL-02 / D-169 / D-170.

Consumes three event types:
  - `budget_breached`         — Phase 13 BudgetEvaluator daily cap exceeded
  - `degraded_mode_entered`   — DegradedModeState.trip() first transition
  - `degraded_mode_exited`    — DegradedModeState.recover()

Sends a single Discord DM to ``Settings.discord_owner_id`` per event type,
rate-limited to 1 DM per event type per ``rate_limit_window_s`` (default
3600s = 1 hour). When ``owner_id is None`` (the default), every method is
a no-op — zero behavior change for self-hosters who do not opt in (D-170).

Fail-soft (D-174): ``discord.Forbidden`` (owner DMs disabled), ``NotFound``
(invalid owner ID), ``HTTPException`` (Discord transient), and any generic
``Exception`` are caught, logged ``eldritch.budget_dm.send_failed``, and
swallowed. The notifier NEVER raises into the bot event loop.

The notifier is decoupled from both BudgetEvaluator and DegradedModeState
— callers wire ``attach_to_degraded_mode()`` for the latter, and call
``notify(...)`` directly from BudgetEvaluator.tick() callbacks. This
matches the v1.x pattern where observability surfaces are composable
without tight coupling to triggers.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from eldritch_dm.logging import get_logger
from eldritch_dm.observability.degraded_mode import (
    DegradedModeState,
    NotifyEvent,
    get_degraded_mode,
)

# Defensive discord-symbol import: project pins discord.py 2.7.1, but a
# stripped-down test environment (or future fork) might run without it.
try:
    from discord import Forbidden, HTTPException, NotFound  # type: ignore[assignment]
except ImportError:  # pragma: no cover

    class Forbidden(Exception):  # type: ignore[no-redef]
        ...

    class NotFound(Exception):  # type: ignore[no-redef]
        ...

    class HTTPException(Exception):  # type: ignore[no-redef]
        ...


if TYPE_CHECKING:
    pass

log = get_logger(__name__)


EventType = Literal[
    "budget_breached",
    "degraded_mode_entered",
    "degraded_mode_exited",
]


_MESSAGES: dict[EventType, str] = {
    "budget_breached": "⚠️ EldritchDM: daily LLM budget breached. Reason: {reason}",
    "degraded_mode_entered": "🛡️ EldritchDM entered degraded mode. Reason: {reason}",
    "degraded_mode_exited": "✅ EldritchDM exited degraded mode.",
}


class BudgetOwnerNotifier:
    """Sends Discord DMs to the bot owner on budget / degraded-mode events.

    Args:
        bot: discord.Client-like object with ``async fetch_user(int) -> User``.
            The returned User must have ``async send(content: str)``.
        owner_id: Discord user ID of the owner. When None, every method is a
            no-op (D-170).
        loop: Event loop for `notify()` cross-thread scheduling. Optional;
            falls back to ``asyncio.get_running_loop()`` at call time.
        rate_limit_window_s: Per-event-type minimum interval between DMs.
            Defaults to 3600s (1 hour) per D-170.
        clock: Injectable monotonic-equivalent clock (``time.monotonic`` by
            default). Tests inject a controllable callable.
    """

    def __init__(
        self,
        *,
        bot: Any,
        owner_id: int | None,
        loop: asyncio.AbstractEventLoop | None = None,
        rate_limit_window_s: float = 3600.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._bot = bot
        self._owner_id = owner_id
        self._loop = loop
        self._rate_limit_window_s = rate_limit_window_s
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._last_sent_ts: dict[EventType, float] = {}
        # Bound callback held by reference so detach_from_degraded_mode can
        # remove it. None until attach_to_degraded_mode() is called.
        self._dm_callback: Callable[[NotifyEvent, str | None], None] | None = None

    # ── Sync entrypoint (thread-safe) ────────────────────────────────────────

    def notify(self, event: EventType, reason: str | None = None) -> None:
        """Schedule a DM for `event`. Safe to call from any thread.

        Fail-soft: never raises. If no event loop can be acquired, logs and
        returns. If the loop is supplied at construction (or inferable from
        the current context), schedules `notify_async` via
        `call_soon_threadsafe`.
        """
        if self._owner_id is None:
            return

        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop in this thread; fall back to the policy's
                # current loop. If that also fails, log + no-op.
                try:
                    loop = asyncio.get_event_loop_policy().get_event_loop()
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "eldritch.budget_dm.no_loop",
                        event_type=event,
                        error_type=type(exc).__name__,
                    )
                    return

        try:
            loop.call_soon_threadsafe(
                lambda: loop.create_task(self.notify_async(event, reason))
            )
        except RuntimeError as exc:
            # Loop closed mid-shutdown — fail-soft.
            log.warning(
                "eldritch.budget_dm.schedule_failed",
                event_type=event,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )

    # ── Async entrypoint ─────────────────────────────────────────────────────

    async def notify_async(
        self, event: EventType, reason: str | None = None
    ) -> None:
        """Send the DM directly. Fail-soft on every error path."""
        if self._owner_id is None:
            return

        # Rate-limit check — per-event-type bucket.
        now = self._clock()
        last = self._last_sent_ts.get(event)
        if last is not None and (now - last) < self._rate_limit_window_s:
            log.info(
                "eldritch.budget_dm.rate_limited",
                event_type=event,
                window_s=self._rate_limit_window_s,
                elapsed_s=now - last,
            )
            return

        template = _MESSAGES[event]
        msg = template.format(reason=reason) if "{reason}" in template else template

        try:
            user = await self._bot.fetch_user(self._owner_id)
            await user.send(msg)
        except Forbidden as exc:
            log.warning(
                "eldritch.budget_dm.send_failed",
                event_type=event,
                error_type="Forbidden",
                error=str(exc)[:200],
            )
            return
        except NotFound as exc:
            log.warning(
                "eldritch.budget_dm.send_failed",
                event_type=event,
                error_type="NotFound",
                error=str(exc)[:200],
            )
            return
        except HTTPException as exc:
            log.warning(
                "eldritch.budget_dm.send_failed",
                event_type=event,
                error_type="HTTPException",
                error=str(exc)[:200],
            )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "eldritch.budget_dm.send_failed",
                event_type=event,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return

        # Successful send → record timestamp so rate-limit bucket holds.
        self._last_sent_ts[event] = now
        log.info(
            "eldritch.budget_dm.sent", event_type=event, owner_id=self._owner_id
        )

    # ── DegradedModeState wiring ─────────────────────────────────────────────

    def attach_to_degraded_mode(
        self, state: DegradedModeState | None = None
    ) -> None:
        """Register self as a notify callback on the singleton (or supplied) state."""
        target = state if state is not None else get_degraded_mode()

        def _on_event(event: NotifyEvent, reason: str | None) -> None:
            # NotifyEvent is a strict subset of EventType — type narrows safely.
            self.notify(event, reason)

        self._dm_callback = _on_event
        target.add_notify_callback(_on_event)

    def detach_from_degraded_mode(
        self, state: DegradedModeState | None = None
    ) -> None:
        """Unregister the previously-attached callback. Idempotent."""
        if self._dm_callback is None:
            return
        target = state if state is not None else get_degraded_mode()
        target.remove_notify_callback(self._dm_callback)
        self._dm_callback = None
