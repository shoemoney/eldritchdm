"""Process-wide runtime override for ``NarrCache`` (Phase 18 / NARRCACHE-03 / D-134).

Mirrors ``degraded_mode.py``'s singleton-with-``RLock`` pattern. Operators
can flip the narration cache off without restarting the bot via
``eldritch-dm-cache-disable --narration`` (Plan 18-02 Task 4), and back on
via ``eldritch-dm-cache-disable --narration --enable``. State is
process-local and resets to "enabled" on bot restart — orchestration that
survives restart belongs in ``.env`` (``NARRCACHE_ENABLED=false``).

``NarrCache.acompletion`` consults ``get_narrcache_override().is_disabled()``
at every call; a disabled override forces the bypass path.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import threading
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from eldritch_dm.logging import get_logger

log = get_logger(__name__)


class NarrCacheOverrideSnapshot(BaseModel):
    """Read-only view of the runtime override. Used by tests + the stats CLI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    disabled: bool
    last_change_utc: datetime | None
    reason: str | None


class NarrCacheRuntimeOverride:
    """Singleton runtime override for NarrCache. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._disabled = False
        self._last_change: datetime | None = None
        self._reason: str | None = None

    def is_disabled(self) -> bool:
        # Fast path — single bool read; GIL provides atomicity.
        return self._disabled

    def disable(self, reason: str | None = None, *, now: datetime | None = None) -> None:
        """Flip the override to DISABLED. Idempotent."""
        when = now or datetime.now(UTC)
        with self._lock:
            already = self._disabled
            self._disabled = True
            self._last_change = when
            self._reason = reason
            if not already:
                log.warning(
                    "narrcache.runtime_disabled",
                    reason=reason,
                    at_utc=when.isoformat(),
                )

    def enable(self, *, now: datetime | None = None) -> None:
        """Flip the override to ENABLED. Idempotent."""
        when = now or datetime.now(UTC)
        with self._lock:
            already = not self._disabled
            self._disabled = False
            self._last_change = when
            self._reason = None
            if not already:
                log.info(
                    "narrcache.runtime_enabled",
                    at_utc=when.isoformat(),
                )

    def snapshot(self) -> NarrCacheOverrideSnapshot:
        with self._lock:
            return NarrCacheOverrideSnapshot(
                disabled=self._disabled,
                last_change_utc=self._last_change,
                reason=self._reason,
            )

    def reset_for_tests(self) -> None:
        with self._lock:
            self._disabled = False
            self._last_change = None
            self._reason = None


# ── Module-level singleton ──────────────────────────────────────────────────

_INSTANCE = NarrCacheRuntimeOverride()


def get_narrcache_override() -> NarrCacheRuntimeOverride:
    """Return the process-wide narration-cache runtime override singleton."""
    return _INSTANCE
