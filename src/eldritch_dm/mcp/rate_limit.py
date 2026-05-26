"""
Per-channel token-bucket rate limiter for mutating MCP calls.

Design (D-28, D-29, D-30, OPS-03):
  - One token per min_interval_ms per channel_id.
  - acquire() NEVER raises — it awaits the bucket drain.
  - Per-channel asyncio.Lock serializes concurrent acquires on the same channel.
  - Clock and sleep are injectable for deterministic testing.
  - Classification of mutating vs read-only is the CALLER's responsibility;
    this module does not introspect tool names.

Usage::

    limiter = ChannelRateLimiter(min_interval_ms=200)
    await limiter.acquire("channel-123")
    # now safe to call mutating MCP tool
    await mcp_tools.party_resolve_action(client, ...)

Phase 4 Plan 01 implementation. OPS-03 requirement.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from eldritch_dm.logging import get_logger

log = get_logger(__name__)


class ChannelRateLimiter:
    """Per-channel token-bucket rate limiter for mutating MCP calls.

    Enforces at most one mutating call per `min_interval_ms` milliseconds per
    channel_id. Concurrent calls to the same channel are serialized and each
    waits its turn in FIFO order.

    Args:
        min_interval_ms: Minimum milliseconds between calls per channel (default 200).
        clock: Monotonic clock callable (injectable for testing).
        sleep: Async sleep callable (injectable for testing).

    Example::

        limiter = ChannelRateLimiter(min_interval_ms=200)
        await limiter.acquire("ch-123")  # returns immediately or awaits
    """

    def __init__(
        self,
        min_interval_ms: int = 200,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._min_interval_s: float = min_interval_ms / 1000.0
        self._clock = clock
        self._sleep = sleep
        # channel_id → next allowed monotonic time
        self._next_allowed: dict[str, float] = {}
        # channel_id → per-channel lock (read-modify-write under contention)
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, channel_id: str) -> asyncio.Lock:
        """Lazily create and return the asyncio.Lock for a channel."""
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()
        return self._locks[channel_id]

    async def acquire(self, channel_id: str) -> None:
        """Acquire a token for the given channel, awaiting if needed.

        Never raises. Blocks until the token is available (≥200ms since the
        last acquire for this channel). Per-channel locks ensure correct
        serialization under concurrent task pressure.

        Args:
            channel_id: The Discord channel snowflake string to rate-limit.
        """
        lock = self._get_lock(channel_id)
        async with lock:
            now = self._clock()
            next_allowed = self._next_allowed.get(channel_id, 0.0)
            wait = max(0.0, next_allowed - now)

            if wait > 0.0:
                log.debug(
                    "rate_limit_acquire_wait",
                    channel_id=channel_id,
                    wait_ms=round(wait * 1000, 1),
                )
                await self._sleep(wait)

            # Re-read clock after potential sleep
            now = self._clock()
            self._next_allowed[channel_id] = now + self._min_interval_s

            log.debug(
                "rate_limit_acquire_ok",
                channel_id=channel_id,
                wait_ms=round(wait * 1000, 1),
            )
