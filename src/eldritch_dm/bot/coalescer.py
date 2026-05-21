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

Phase 2 note: ChannelEditBudget is stubbed as None for per-message limiting.
Phase 4 will pass a shared budget to prevent per-channel rate-limit collisions
(see RESEARCH.md Pitfall 4).
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


class ChannelEditBudget:
    """Stub for Phase 4 per-channel rate-limit budget.

    Phase 2 leaves this unused (None). Phase 4 will implement a token-bucket
    semaphore and pass it to each EmbedCoalescer for a given channel to prevent
    the 5-edits/5s per-channel limit from being hit by multiple coalescers.
    """


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
