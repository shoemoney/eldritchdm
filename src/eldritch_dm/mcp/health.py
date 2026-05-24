"""
Circuit breaker state machine and health check loop.

CircuitBreaker:
- CLOSED: normal operation
- OPEN: trips after `threshold` consecutive failures; blocks MCP calls
- No HALF_OPEN state in v1 — recovery is immediate on the first success (D-08)

HealthCheck:
- Pings {endpoint}/models on a configurable interval
- Updates the CircuitBreaker on each ping result
- Used by the Discord layer to render "DM is offline" status
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import suppress
from enum import StrEnum
from typing import TYPE_CHECKING

import httpx

from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


class CircuitState(StrEnum):
    """The two states of the v1 circuit breaker."""

    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"  # Tripped; all calls rejected


class CircuitBreaker:
    """Simple threshold-based circuit breaker.

    Args:
        threshold: Number of consecutive failures required to trip OPEN.
            Default 3, matching omlx_circuit_breaker_threshold (D-08).
    """

    def __init__(
        self,
        threshold: int = 3,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = threshold
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._clock = clock
        # SAFETY-02 (Phase 7): monotonic timestamp of the most recent
        # CLOSED→OPEN transition. None when CLOSED. Consumed by
        # DMOfflineDebouncer's 5s min-open gate so transient circuit blips
        # do not surface a "DM offline" warning to players (OPS-02-2 / D-34).
        # Wall-clock would be wrong here — NTP slew could falsify the gate.
        self.opened_at: float | None = None
        self._logger = log.bind(component="circuit_breaker")

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        """Public read of the consecutive-failures counter (SAFETY-02 consumer).

        Used by the DM_OFFLINE warning template — players see ``Health check
        failed N times in a row`` where N is this counter.
        """
        return self._failures

    def record_success(self) -> None:
        """Record a successful call; reset failure counter and close the circuit."""
        prev = self._state
        self._failures = 0
        self._state = CircuitState.CLOSED
        # SAFETY-02: clear the open-timestamp on close so a future open
        # transition starts a fresh min-open clock.
        self.opened_at = None
        if prev != CircuitState.CLOSED:
            self._logger.info("circuit_closed", after_failures=self._failures)

    def record_failure(self) -> None:
        """Record a failed call; trip OPEN after threshold consecutive failures."""
        self._failures += 1
        if self._failures >= self._threshold and self._state == CircuitState.CLOSED:
            self._state = CircuitState.OPEN
            # SAFETY-02: stamp the open-transition time so DMOfflineDebouncer
            # can compute (now - opened_at) >= min_open_seconds before
            # surfacing the warning.
            self.opened_at = self._clock()
            self._logger.warning("circuit_opened", failures=self._failures)
        else:
            self._logger.debug(
                "circuit_failure_recorded",
                failures=self._failures,
                threshold=self._threshold,
                state=str(self._state),
            )

    def reset(self) -> None:
        """Reset to CLOSED with zero failures (used in tests)."""
        self._failures = 0
        self._state = CircuitState.CLOSED
        self.opened_at = None


def get_circuit_state(breaker: CircuitBreaker) -> CircuitState:
    """Return the current state of the circuit breaker.

    Used by the Discord layer in later phases to render "DM is offline" status.
    """
    return breaker.state


class HealthCheck:
    """Periodic health check loop that pings {endpoint}/models.

    Integrates with CircuitBreaker: success → record_success(), failure → record_failure().

    Args:
        endpoint: Base URL to ping; appends "/models" for the GET request.
        interval: Seconds between pings.
        breaker: The CircuitBreaker to update.
        http_client: Optional httpx.AsyncClient; creates its own if not provided.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        interval: float = 60.0,
        breaker: CircuitBreaker,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._interval = interval
        self._breaker = breaker
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=2.0)
        )
        self._task: asyncio.Task[None] | None = None
        self._logger = log.bind(component="health_check", endpoint=self._endpoint)

    async def start(self) -> None:
        """Start the background health check loop."""
        self._task = asyncio.get_event_loop().create_task(
            self._run(), name="HealthCheck._run"
        )
        self._logger.debug("health_check_started", interval=self._interval)

    async def _run(self) -> None:
        """Main loop: sleep → ping → update breaker → repeat."""
        while True:
            try:
                await asyncio.sleep(self._interval)
                r = await self._client.get(
                    f"{self._endpoint}/models",
                    timeout=httpx.Timeout(5.0, connect=2.0),
                )
                r.raise_for_status()
                self._breaker.record_success()
                self._logger.info(
                    "health_ping_ok",
                    status_code=r.status_code,
                    circuit_state=str(self._breaker.state),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._breaker.record_failure()
                self._logger.warning(
                    "health_ping_failed",
                    error=str(exc),
                    circuit_state=str(self._breaker.state),
                )

    async def stop(self) -> None:
        """Cancel the health check loop cleanly."""
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
            self._logger.debug("health_check_stopped")

        if self._owns_client:
            await self._client.aclose()
