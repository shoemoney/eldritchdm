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

from __future__ import annotations

import threading
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from eldritch_dm.logging import get_logger

log = get_logger(__name__)


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

    def is_active(self) -> bool:
        # Fast path — no lock needed for a single bool read (GIL provides
        # atomicity for primitive assignments).
        return self._active

    def trip(self, reason: str, *, now: datetime | None = None) -> None:
        """Enter degraded mode. Idempotent — re-trips update reason only."""
        when = now or datetime.now(UTC)
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

    def recover(self, *, now: datetime | None = None) -> None:
        """Exit degraded mode. Idempotent — no-op when already recovered."""
        when = now or datetime.now(UTC)
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

    def snapshot(self) -> DegradedModeSnapshot:
        with self._lock:
            return DegradedModeSnapshot(
                active=self._active,
                reason=self._reason,
                entered_at_utc=self._entered_at,
                recovered_at_utc=self._recovered_at,
            )

    def reset_for_tests(self) -> None:
        """Drop state. Test-only."""
        with self._lock:
            self._active = False
            self._reason = None
            self._entered_at = None
            self._recovered_at = None


# ── Module-level singleton ──────────────────────────────────────────────────

_INSTANCE = DegradedModeState()


def get_degraded_mode() -> DegradedModeState:
    """Return the process-wide degraded-mode state singleton."""
    return _INSTANCE
