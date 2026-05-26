"""
EmbedCoalescer — per-message rate-limited embed update queue.

Design: asyncio.Event + latest-value slot (D-28, RESEARCH.md Pattern 4).

Semantics:
  - Stores latest (embed, view) payload (overwrites older pending updates).
  - A render task wakes on the Event, respects the rate-limit window, applies
    the latest payload via message.edit(...), then loops.
  - If a new update arrives during the sleep window, it overwrites _pending;
    the next loop iteration picks up the newer payload — never lost.

Race-free ordering (RESEARCH.md Pattern 4):
  - Snapshot _pending + clear BEFORE awaiting message.edit
  - Any update arriving during the edit sets _dirty again → next iteration picks it up

Abandoned states:
  - discord.NotFound (message deleted) → abandon silently
  - discord.Forbidden (lost permissions) → abandon silently
  - discord.HTTPException (transient errors, 429, 5xx) → log, continue (loop retries)

Phase 4 note: ChannelEditBudget is now fully implemented (replacing Phase 2 stub).
Pass a shared budget instance to each EmbedCoalescer for a given Discord channel to
prevent the 5-edits/5s per-channel limit from being hit by multiple coalescers
(see RESEARCH.md Pitfall 4, Phase 4 Plan 01).
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

# Discord's per-channel rate limit: 5 edits per 5 seconds (verified Phase 2 RESEARCH)
_CHANNEL_EDIT_LIMIT = 5
_CHANNEL_WINDOW_SECONDS = 5.0


class ChannelEditBudget:
    """Per-channel Discord edit-rate budget (5 edits / 5 seconds per channel).

    Shared across all EmbedCoalescer instances for the same Discord channel.
    When 5 edits have already occurred within the last 5 seconds, the 6th
    acquire() call awaits until the oldest edit falls outside the window.

    Clock and sleep are injectable for deterministic testing.

    Args:
        channel_id: Discord channel snowflake string (for logging).
        limit: Maximum edits in the window (default 5, matching Discord's limit).
        window_seconds: Rolling window in seconds (default 5.0, matching Discord's limit).
        clock: Monotonic clock callable (injectable for testing).
        sleep: Async sleep callable (injectable for testing).

    Usage::

        budget = ChannelEditBudget(channel_id="123456789")
        await budget.acquire(message_id="987654321")  # may await if budget exhausted
        await message.edit(embed=embed)
    """

    def __init__(
        self,
        channel_id: str = "",
        *,
        limit: int = _CHANNEL_EDIT_LIMIT,
        window_seconds: float = _CHANNEL_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._channel_id = channel_id
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._sleep = sleep
        # Timestamps of recent edits (oldest first)
        self._edit_times: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._logger = log.bind(channel_id=channel_id, component="ChannelEditBudget")

    def _evict_stale(self, now: float) -> None:
        """Remove timestamps older than the window from the deque."""
        cutoff = now - self._window_seconds
        while self._edit_times and self._edit_times[0] <= cutoff:
            self._edit_times.popleft()

    async def acquire(self, message_id: str | int = "") -> None:
        """Acquire a budget token for one Discord message edit.

        Awaits until a token is available within the per-channel rolling window.
        Never raises; blocks if the budget is exhausted.

        Args:
            message_id: The Discord message snowflake (for logging only).
        """
        async with self._lock:
            while True:
                now = self._clock()
                self._evict_stale(now)

                if len(self._edit_times) < self._limit:
                    # Budget available — record this edit and proceed
                    self._edit_times.append(now)
                    self._logger.debug(
                        "channel_edit_budget_acquired",
                        message_id=str(message_id),
                        edits_in_window=len(self._edit_times),
                    )
                    return

                # Budget exhausted — compute wait until oldest edit falls out
                oldest = self._edit_times[0]
                wait = (oldest + self._window_seconds) - now
                if wait > 0.0:
                    self._logger.debug(
                        "channel_edit_budget_waiting",
                        message_id=str(message_id),
                        wait_ms=round(wait * 1000, 1),
                        edits_in_window=len(self._edit_times),
                    )
                    await self._sleep(wait)
                # Re-evaluate after sleep (lock held throughout)


class EmbedCoalescer:
    """Per-message coalescer: buffers rapid embed updates to ≤1 edit/rate_limit_seconds.

    Args:
        message: The Discord message to edit.
        rate_limit_seconds: Minimum seconds between edits (default 1.0).
        clock: Callable returning current monotonic time (injectable for testing).
        sleep: Async callable for rate-limit sleeping (injectable for testing).
        channel_budget: Optional shared channel-level rate-limiter (Phase 4).

    Usage::

        coalescer = EmbedCoalescer(message, rate_limit_seconds=settings.embed_edit_rate_limit)
        await coalescer.update(embed, view=my_view)
        # ... later, on teardown:
        await coalescer.close()
    """

    def __init__(
        self,
        message: discord.Message,
        *,
        rate_limit_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        channel_budget: ChannelEditBudget | None = None,
    ) -> None:
        self._message = message
        self._rate_limit_seconds = rate_limit_seconds
        self._clock = clock
        self._sleep = sleep
        self._channel_budget = channel_budget  # Phase 4 hook

        self._pending: tuple[discord.Embed, discord.ui.View | None] | None = None
        self._dirty: asyncio.Event = asyncio.Event()
        self._render_task: asyncio.Task | None = None
        self._abandoned: bool = False
        self._last_edit_t: float = -math.inf

        self._logger = log.bind(message_id=message.id)

    async def update(
        self,
        embed: discord.Embed,
        *,
        view: discord.ui.View | None = None,
    ) -> None:
        """Queue a new (embed, view) payload for the next render cycle.

        Latest-value semantics: overwrites any pending but unsent payload.
        No-op if the coalescer has been abandoned (message gone/forbidden).
        Lazily starts the render task on first call.

        Args:
            embed: The new Embed to send.
            view: Optional View to attach (pass None to remove existing view).
        """
        if self._abandoned:
            return

        # Overwrite pending payload (latest-value)
        self._pending = (embed, view)
        self._dirty.set()

        # Lazily start render task
        if self._render_task is None or self._render_task.done():
            self._render_task = asyncio.create_task(
                self._render_loop(),
                name=f"coalescer:{self._message.id}",
            )

    async def close(self) -> None:
        """Stop the coalescer and cancel the render task.

        Does NOT issue any final edit. Just cancels the background task cleanly.
        """
        if self._render_task is not None and not self._render_task.done():
            self._render_task.cancel()
            try:
                await self._render_task
            except asyncio.CancelledError:
                pass
        self._render_task = None

    async def _render_loop(self) -> None:
        """Background render loop: wakes on _dirty, respects rate limit, edits message."""
        while not self._abandoned:
            await self._dirty.wait()
            self._dirty.clear()

            # Check if we have a payload to send
            payload = self._pending
            if payload is None:
                continue

            # Respect rate limit: sleep only what's needed
            elapsed = self._clock() - self._last_edit_t
            if elapsed < self._rate_limit_seconds:
                remaining = self._rate_limit_seconds - elapsed
                await self._sleep(remaining)

            # Re-read _pending after sleep (newer overwrite may have arrived)
            payload = self._pending
            if payload is None:
                continue

            embed, view = payload
            # Clear pending BEFORE the await to avoid losing concurrent updates
            # (any update during edit will re-set _dirty, next loop picks it up)
            self._pending = None

            # Phase 4: per-channel budget check (5 edits/5s Discord limit).
            # Must acquire BEFORE the message.edit call.
            if self._channel_budget is not None:
                await self._channel_budget.acquire(self._message.id)

            try:
                await self._message.edit(embed=embed, view=view)
                self._last_edit_t = self._clock()
            except discord.NotFound:
                self._abandoned = True
                self._logger.warning("coalescer_message_gone", message_id=self._message.id)
                return
            except discord.Forbidden:
                self._abandoned = True
                self._logger.warning(
                    "coalescer_message_forbidden", message_id=self._message.id
                )
                return
            except discord.HTTPException as exc:
                self._logger.warning(
                    "coalescer_http_error",
                    status=getattr(exc, "status", None),
                    error=str(exc),
                )
                # Transient error — do NOT abandon; loop will retry on next dirty signal
                continue
