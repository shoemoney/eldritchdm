"""Per-channel debouncer for the DM_OFFLINE warning (SAFETY-02 / Phase 7 / D-34).

When the MCP circuit breaker trips OPEN, players who keep clicking buttons would
otherwise see one ``WarningKind.DM_OFFLINE`` ephemeral per click. The debouncer
caps that to **one warning per channel per 30 seconds** (OPS-02-1) AND
suppresses warnings while the circuit has been OPEN for less than 5 seconds
(OPS-02-2 — transient blips during oMLX restart shouldn't bother players).

The clock is injectable for deterministic tests. In production the default
``time.monotonic`` is correct — wall-clock would be wrong because NTP slew
could falsify the elapsed-time gates.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from eldritch_dm.mcp.health import CircuitBreaker

_log = get_logger(__name__)


class DMOfflineDebouncer:
    """Per-channel debounce + min-open-duration gate for DM_OFFLINE warnings.

    Args:
        debounce_seconds: Suppress repeat warnings on the same channel within
            this window (D-34: 30s default).
        min_open_seconds: Require the circuit to have been OPEN for at least
            this long before emitting a warning (D-34: 5s default — protects
            against transient blips during oMLX restart).
        clock: Injectable monotonic clock. Defaults to ``time.monotonic``.
    """

    def __init__(
        self,
        *,
        debounce_seconds: float = 30.0,
        min_open_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._debounce_seconds = debounce_seconds
        self._min_open_seconds = min_open_seconds
        self._clock = clock
        # channel_id (str) → last-warned monotonic timestamp.
        self._last_warned: dict[str, float] = {}

    def maybe_warn(self, channel_id: str, circuit: CircuitBreaker) -> bool:
        """Return True iff a DM_OFFLINE warning should be dispatched now.

        Records the warning timestamp on return-True so the next call within
        ``debounce_seconds`` returns False (per-channel keyed).

        Two gates:
          1. **min-open gate (OPS-02-2):** circuit must have been OPEN for
             at least ``min_open_seconds`` (transient blips suppressed).
          2. **debounce gate (OPS-02-1):** no warning was emitted on this
             channel within the last ``debounce_seconds``.
        """
        now = self._clock()
        opened_at = getattr(circuit, "opened_at", None)

        # Gate 1: min-open duration
        if opened_at is None or (now - opened_at) < self._min_open_seconds:
            open_for = None if opened_at is None else (now - opened_at)
            _log.debug(
                "dm_offline_warning_suppressed_min_open",
                channel_id=channel_id,
                circuit_open_duration_s=open_for,
                min_open_seconds=self._min_open_seconds,
            )
            return False

        # Gate 2: per-channel debounce
        last = self._last_warned.get(channel_id)
        if last is not None and (now - last) < self._debounce_seconds:
            _log.debug(
                "dm_offline_warning_suppressed_debounce",
                channel_id=channel_id,
                last_warned_s_ago=now - last,
                debounce_seconds=self._debounce_seconds,
            )
            return False

        # Both gates passed — emit the warning and record the timestamp.
        self._last_warned[channel_id] = now
        _log.info(
            "dm_offline_warning_emitted",
            channel_id=channel_id,
            circuit_open_duration_s=now - opened_at,
            failure_count=getattr(circuit, "failure_count", -1),
        )
        return True

    def force_warn(self, channel_id: str) -> None:
        """Test helper: bypass both gates and record a warning now.

        Used in integration tests to assert the 30s window fires correctly
        without having to manipulate the circuit breaker's ``opened_at``.
        """
        self._last_warned[channel_id] = self._clock()
