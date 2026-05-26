"""Process-wide degraded-mode state (Phase 13 / MON-02 / R-13-02-a).

The monster driver factory consults this singleton BEFORE the env to decide
whether to return ``MonsterDriver`` (random — safety override) or
``SmartMonsterDriver``. Settings is ``frozen=True`` (immutable per
project-wide invariant) so we cannot store the override there — module-level
state with a ``threading.RLock`` is the standard pattern for cross-async-task
mutability.

State machine:

  - Initial: active=False
  - trip(reason)    → active=True, entered_at=now (idempotent; reason updates)
  - recover()       → active=False, recovered_at=now (idempotent)

Logging:

  - On first trip:    eldritch.degraded_mode.entered (WARNING) with reason
  - On reason change: eldritch.degraded_mode.reason_changed (INFO)
  - On recover:       eldritch.degraded_mode.exited (INFO) with dwell_seconds
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from eldritch_dm.logging import get_logger

log = get_logger(__name__)


# ── Notify-callback typing (Phase 22 / OPQOL-02) ─────────────────────────────

NotifyEvent = Literal["degraded_mode_entered", "degraded_mode_exited"]
NotifyCallback = Callable[[NotifyEvent, "str | None"], None]


class DegradedModeSnapshot(BaseModel):
    """Read-only view of degraded-mode state. Used by tests + reports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    active: bool
    reason: str | None
    entered_at_utc: datetime | None
    recovered_at_utc: datetime | None


class DegradedModeState:
    """Singleton degraded-mode state machine. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active = False
        self._reason: str | None = None
        self._entered_at: datetime | None = None
        self._recovered_at: datetime | None = None
        # Phase 22 / OPQOL-02: notify-callbacks fire on FIRST trip and on
        # recover. Reason-change re-trips do NOT fire (avoid spam).
        self._notify_callbacks: list[NotifyCallback] = []

    def is_active(self) -> bool:
        # Fast path — no lock needed for a single bool read (GIL provides
        # atomicity for primitive assignments).
        return self._active

    def trip(self, reason: str, *, now: datetime | None = None) -> None:
        """Enter degraded mode. Idempotent — re-trips update reason only.

        Fires `degraded_mode_entered` notify callbacks ONLY on the
        first-time transition (not on reason-change re-trips — D-170).
        Callback exceptions are logged and swallowed.
        """
        when = now or datetime.now(UTC)
        fire_callbacks: list[NotifyCallback] = []
        with self._lock:
            if self._active:
                if reason != self._reason:
                    log.info(
                        "eldritch.degraded_mode.reason_changed",
                        old_reason=self._reason,
                        new_reason=reason,
                    )
                    self._reason = reason
                return
            self._active = True
            self._reason = reason
            self._entered_at = when
            self._recovered_at = None
            log.warning(
                "eldritch.degraded_mode.entered",
                reason=reason,
                entered_at_utc=when.isoformat(),
            )
            # Snapshot callbacks under lock so registrations during dispatch
            # do not mutate the list we're iterating.
            fire_callbacks = list(self._notify_callbacks)

        # Fire callbacks OUTSIDE the lock to avoid holding it across IO.
        for cb in fire_callbacks:
            try:
                cb("degraded_mode_entered", reason)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "eldritch.degraded_mode.notify_error",
                    event_type="degraded_mode_entered",
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )

    def recover(self, *, now: datetime | None = None) -> None:
        """Exit degraded mode. Idempotent — no-op when already recovered.

        Fires `degraded_mode_exited` notify callbacks on the actual exit.
        Callback exceptions logged + swallowed.
        """
        when = now or datetime.now(UTC)
        fire_callbacks: list[NotifyCallback] = []
        with self._lock:
            if not self._active:
                return
            dwell = (when - self._entered_at).total_seconds() if self._entered_at else None
            self._active = False
            self._recovered_at = when
            old_reason = self._reason
            self._reason = None
            log.info(
                "eldritch.degraded_mode.exited",
                previous_reason=old_reason,
                dwell_seconds=dwell,
                recovered_at_utc=when.isoformat(),
            )
            fire_callbacks = list(self._notify_callbacks)

        for cb in fire_callbacks:
            try:
                cb("degraded_mode_exited", None)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "eldritch.degraded_mode.notify_error",
                    event_type="degraded_mode_exited",
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )

    def snapshot(self) -> DegradedModeSnapshot:
        with self._lock:
            return DegradedModeSnapshot(
                active=self._active,
                reason=self._reason,
                entered_at_utc=self._entered_at,
                recovered_at_utc=self._recovered_at,
            )

    def add_notify_callback(self, cb: NotifyCallback) -> None:
        """Register a callback fired on first-trip and on recover (D-169)."""
        with self._lock:
            if cb not in self._notify_callbacks:
                self._notify_callbacks.append(cb)

    def remove_notify_callback(self, cb: NotifyCallback) -> None:
        """Unregister a previously-added notify callback. Idempotent."""
        with self._lock:
            try:
                self._notify_callbacks.remove(cb)
            except ValueError:
                pass

    def reset_for_tests(self) -> None:
        """Drop state + callbacks. Test-only."""
        with self._lock:
            self._active = False
            self._reason = None
            self._entered_at = None
            self._recovered_at = None
            self._notify_callbacks.clear()


# ── Module-level singleton ──────────────────────────────────────────────────

_INSTANCE = DegradedModeState()


def get_degraded_mode() -> DegradedModeState:
    """Return the process-wide degraded-mode state singleton."""
    return _INSTANCE
