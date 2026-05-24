"""
Tests for gameplay/session_locks.py (Phase 5 Plan 02 Task 1).

SessionLocks is a namespaced per-channel asyncio.Lock registry. Two code
paths must serialize against each other at the click-vs-sweeper boundary
(RESEARCH Pitfall 3): RiposteButton.callback's read-then-mark sequence and
RiposteSweeper's deadline-driven mark_expired. Both acquire
``acquire("riposte", channel_id)`` and Plan 02 makes this deterministic.

Tests (per plan behavior section):
  1. acquire returns asyncio.Lock instance.
  2. Same key → same Lock identity.
  3. Different channel_id → different Lock.
  4. Different namespace → different Lock (sweeper ≠ rate_limiter).
  5. Lock acquisition order is deterministic (second awaits while first holds).
  6. 100 concurrent acquire() calls for same key return ONE Lock instance.
  7. lock_for context-manager helper acquires + releases the same Lock.

DECISION (deviation from frontmatter): SessionLocks lives under
``src/eldritch_dm/gameplay/`` (not ``src/eldritch_dm/bot/``) because the
import-linter ``"gameplay must not import bot"`` contract forbids the
reverse path that bot/session_locks would require. SessionLocks is
semantically a gameplay synchronization primitive — see plan's
verification.risks for the recommendation.
"""

from __future__ import annotations

import asyncio

import pytest

from eldritch_dm.gameplay.session_locks import SessionLocks

# ── Test 1: acquire returns asyncio.Lock ─────────────────────────────────────


class TestAcquireReturnsLock:
    @pytest.mark.asyncio
    async def test_acquire_returns_asyncio_lock(self) -> None:
        locks = SessionLocks()
        lock = await locks.acquire("riposte", "channel123")
        assert isinstance(lock, asyncio.Lock)


# ── Test 2: Same key → same Lock identity ─────────────────────────────────────


class TestAcquireIsIdempotent:
    @pytest.mark.asyncio
    async def test_same_key_returns_same_lock(self) -> None:
        locks = SessionLocks()
        a = await locks.acquire("riposte", "channel123")
        b = await locks.acquire("riposte", "channel123")
        assert a is b, "Same (namespace, channel_id) must yield the same Lock instance"


# ── Test 3: Different channel_id → different Lock ────────────────────────────


class TestAcquirePerChannelIsolation:
    @pytest.mark.asyncio
    async def test_different_channels_distinct_locks(self) -> None:
        locks = SessionLocks()
        a = await locks.acquire("riposte", "channelA")
        b = await locks.acquire("riposte", "channelB")
        assert a is not b


# ── Test 4: Different namespace → different Lock ─────────────────────────────


class TestAcquireNamespaceIsolation:
    @pytest.mark.asyncio
    async def test_different_namespaces_distinct_locks(self) -> None:
        locks = SessionLocks()
        a = await locks.acquire("riposte", "channelA")
        b = await locks.acquire("rate_limit", "channelA")
        assert a is not b


# ── Test 5: Lock acquisition serializes ──────────────────────────────────────


class TestLockSerializesContenders:
    @pytest.mark.asyncio
    async def test_second_acquire_waits_for_first(self) -> None:
        locks = SessionLocks()
        order: list[str] = []
        lock = await locks.acquire("riposte", "X")

        async def first() -> None:
            async with lock:
                order.append("first_in")
                await asyncio.sleep(0.05)
                order.append("first_out")

        async def second() -> None:
            # Tiny delay so first wins the race deterministically
            await asyncio.sleep(0.01)
            same_lock = await locks.acquire("riposte", "X")
            async with same_lock:
                order.append("second_in")
                order.append("second_out")

        await asyncio.gather(first(), second())
        assert order == ["first_in", "first_out", "second_in", "second_out"]


# ── Test 6: 100 concurrent acquire() for same key → ONE Lock ─────────────────


class TestAcquireConcurrentCreationIsSafe:
    @pytest.mark.asyncio
    async def test_100_concurrent_acquires_same_key(self) -> None:
        locks = SessionLocks()

        async def grab() -> asyncio.Lock:
            return await locks.acquire("riposte", "race-key")

        results = await asyncio.gather(*(grab() for _ in range(100)))
        ids = {id(lock) for lock in results}
        assert len(ids) == 1, (
            f"Expected ONE Lock id under 100 concurrent acquires, got {len(ids)}"
        )


# ── Test 7: lock_for context manager helper ──────────────────────────────────


class TestLockForContextManager:
    @pytest.mark.asyncio
    async def test_lock_for_acquires_and_releases(self) -> None:
        locks = SessionLocks()

        async with locks.lock_for("riposte", "X"):
            inner_lock = await locks.acquire("riposte", "X")
            assert inner_lock.locked() is True

        # After context manager exits, lock must be released
        lock = await locks.acquire("riposte", "X")
        assert lock.locked() is False
