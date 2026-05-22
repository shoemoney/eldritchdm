"""
SessionLocks — namespaced per-channel asyncio.Lock registry.

Phase 5 Plan 02. Resolves RESEARCH Pitfall 3 (click-vs-sweeper race).

Two code paths must serialize at the click-at-deadline boundary:

  - ``gameplay/reactions.handle_riposte_click`` (read row → check status →
    mark_consumed_with_round)
  - ``gameplay/riposte_sweeper.RiposteSweeper._iterate`` (list pending rows
    past deadline → mark_expired)

Without a shared lock, a click at T=7.999s and a sweeper sweep at T=8.000s
can both write — producing either a consumed-but-also-expired race (UI
shows the wrong final state) or a double UI-action (button "fired twice").

The fix is a tiny per-channel-and-namespace registry of ``asyncio.Lock``
instances. Same ``(namespace, channel_id)`` always returns the same Lock,
so two coroutines that both ``acquire("riposte", "abc")`` will serialize.

Namespace isolation: the sweeper's lock is keyed ``riposte:{channel_id}``;
the Phase 4 ``ChannelRateLimiter`` uses its own per-channel asyncio.Lock
(different concern, different Lock — we do NOT reuse the rate_limiter's
locks because that would serialize completely unrelated work).

Import-linter discipline:
  This module lives under ``gameplay/`` (not ``bot/``) because the
  ``"gameplay must not import bot"`` contract would forbid the reverse
  path that any bot-located primitive would require here. SessionLocks
  is semantically a gameplay synchronization primitive; the plan's
  verification.risks section recommended this location and we adopt it.

Concurrency model:
  ``acquire(...)`` itself is awaited (briefly) under an internal
  ``_guard`` lock that serializes the dict mutation. The lock returned
  is the per-key ``asyncio.Lock`` — callers ``async with`` it for the
  critical section.

Usage:
  ```python
  lock = await session_locks.acquire("riposte", channel_id)
  async with lock:
      ...

  # Or via the helper:
  async with session_locks.lock_for("riposte", channel_id):
      ...
  ```
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class SessionLocks:
    """Namespaced per-channel asyncio.Lock registry.

    Phase 5 Plan 02. Same (namespace, channel_id) yields the same Lock
    instance; concurrent creation is safe.

    Args:
        (none) — locks are created on first acquire.
    """

    def __init__(self) -> None:
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        # _guard serializes dict mutation under concurrent acquire().
        self._guard = asyncio.Lock()

    @staticmethod
    def _key(namespace: str, channel_id: str) -> tuple[str, str]:
        return (namespace, str(channel_id))

    async def acquire(self, namespace: str, channel_id: str) -> asyncio.Lock:
        """Return the asyncio.Lock for (namespace, channel_id).

        Caller is responsible for ``async with`` on the returned Lock.
        Creation is safe under concurrency: 100 concurrent acquire()
        calls for the same key return ONE Lock instance.
        """
        key = self._key(namespace, channel_id)
        # Fast path: lock already exists. No need to await _guard.
        lock = self._locks.get(key)
        if lock is not None:
            return lock
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
        return lock

    @asynccontextmanager
    async def lock_for(
        self, namespace: str, channel_id: str
    ) -> AsyncIterator[None]:
        """Context-manager helper: acquire + ``async with`` in one shot.

        Equivalent to::

            lock = await locks.acquire(namespace, channel_id)
            async with lock:
                ...
        """
        lock = await self.acquire(namespace, channel_id)
        async with lock:
            yield
