"""
EldritchDM per-channel asyncio.Lock registry.

SessionLocks provides one asyncio.Lock per Discord channel_id.
Locks are created lazily and never garbage-collected during process lifetime
(D-10, D-11) — cardinality is bounded by the number of Discord channels
the bot is active in, which is a small finite set for a single guild.

Usage::

    locks = SessionLocks()

    async with locks.get(channel_id):
        # Only one coroutine at a time per channel
        await mcp_client.call("combat_action", ...)
"""

from __future__ import annotations

import asyncio


class SessionLocks:
    """Registry of per-channel asyncio.Lock objects.

    Thread-safe within a single event loop.  One instance should be created
    at process startup and shared across all subsystems that need per-channel
    serialization (MCP mutating calls, riposte sweeper, session writes).
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, channel_id: str) -> asyncio.Lock:
        """Return the asyncio.Lock for the given channel_id.

        Creates the lock on first access; never evicts it (D-11).
        """
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()
        return self._locks[channel_id]

    def __len__(self) -> int:
        """Return the number of channels currently tracked."""
        return len(self._locks)
