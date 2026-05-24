"""
Tests for ChannelRateLimiter — per-channel token-bucket rate limiter.

TDD RED tests for Task 1 of Phase 4 Plan 01.
Covers: basic acquire, rate-limit enforcement, per-channel isolation,
configurability, await-not-raise semantics, and concurrency safety.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from eldritch_dm.mcp.rate_limit import ChannelRateLimiter

# ── Test 1: Single acquire returns immediately ────────────────────────────────


async def test_single_acquire_returns_immediately():
    """A single acquire() returns immediately when the bucket has tokens."""
    sleep_mock = AsyncMock()
    clock_mock = MagicMock(side_effect=[100.0, 100.0])  # called twice in acquire

    limiter = ChannelRateLimiter(min_interval_ms=200, clock=clock_mock, sleep=sleep_mock)
    await limiter.acquire("channel-A")

    sleep_mock.assert_not_called()


# ── Test 2: Second acquire within window awaits ~200ms ────────────────────────


async def test_second_acquire_within_window_awaits():
    """Two acquires within min_interval_ms cause the second to await the remainder."""
    waited: list[float] = []

    async def capture_sleep(s: float) -> None:
        waited.append(s)

    # Clock: first acquire: now=0.0, then 0.0 again; second acquire: now=0.05 (50ms elapsed)
    clock_values = [0.0, 0.0, 0.05, 0.25]
    clock_mock = MagicMock(side_effect=clock_values)

    limiter = ChannelRateLimiter(
        min_interval_ms=200, clock=clock_mock, sleep=capture_sleep
    )
    await limiter.acquire("channel-A")  # sets next_allowed = 0.0 + 0.2 = 0.2
    await limiter.acquire("channel-A")  # now=0.05, wait=0.2-0.05=0.15

    assert len(waited) == 1
    assert abs(waited[0] - 0.15) < 0.001, f"Expected wait ~0.15s, got {waited[0]}"


# ── Test 3: Per-channel isolation ─────────────────────────────────────────────


async def test_per_channel_isolation():
    """Channel A being rate-limited does NOT block channel B."""
    # Channel A is fully rate-limited (next_allowed far in the future)
    # Channel B should still acquire immediately

    clock_calls_A = [0.0, 0.0, 0.05, 1.0]  # A: first ok, second waits
    clock_calls_B = [2.0, 2.0]  # B: immediate, no wait

    call_sequence: list[float] = clock_calls_A + clock_calls_B
    clock_mock = MagicMock(side_effect=call_sequence)

    waited_channels: list[str] = []

    async def capture_sleep(s: float) -> None:
        waited_channels.append("A")

    limiter = ChannelRateLimiter(
        min_interval_ms=200, clock=clock_mock, sleep=capture_sleep
    )

    # Exhaust channel A's budget
    await limiter.acquire("channel-A")
    # now channel A is at next_allowed=0.2; second acquire at t=0.05 waits
    await limiter.acquire("channel-A")

    # Channel B should not be blocked
    b_slept = False

    async def b_sleep(s: float) -> None:
        nonlocal b_slept
        b_slept = True

    limiter._sleep = b_sleep
    await limiter.acquire("channel-B")

    assert not b_slept, "Channel B should not be rate-limited by Channel A"


# ── Test 4: min_interval_ms is constructor-configurable ──────────────────────


async def test_min_interval_ms_configurable():
    """min_interval_ms is constructor-configurable; default is 200."""
    # Default
    default_limiter = ChannelRateLimiter()
    assert default_limiter._min_interval_s == pytest.approx(0.200)

    # Custom: 500ms
    custom_limiter = ChannelRateLimiter(min_interval_ms=500)
    assert custom_limiter._min_interval_s == pytest.approx(0.500)

    # Custom: 50ms
    fast_limiter = ChannelRateLimiter(min_interval_ms=50)
    assert fast_limiter._min_interval_s == pytest.approx(0.050)


# ── Test 5: acquire never raises — awaits instead ─────────────────────────────


async def test_acquire_never_raises():
    """acquire() never raises; it awaits. Even with a sleep that takes time."""
    calls = 0

    async def counting_sleep(s: float) -> None:
        nonlocal calls
        calls += 1

    # Clock that first returns 0.0, then 0.05 (within window)
    clock = MagicMock(side_effect=[0.0, 0.0, 0.05, 0.25])
    limiter = ChannelRateLimiter(min_interval_ms=200, clock=clock, sleep=counting_sleep)

    # Should not raise
    await limiter.acquire("ch")
    await limiter.acquire("ch")

    # sleep was called (rate limit was hit), but no exception
    assert calls == 1


# ── Test 6: Concurrent safety — 4 tasks, timestamps ≥ 200ms apart ─────────────


async def test_concurrent_acquire_monotonic_timestamps():
    """4 concurrent tasks on the same channel produce ≥200ms gaps."""
    results: list[float] = []
    real_time_base = 0.0
    time_counter = 0.0

    def advancing_clock() -> float:
        nonlocal time_counter
        val = time_counter
        return val

    async def advancing_sleep(s: float) -> None:
        nonlocal time_counter
        time_counter += s

    limiter = ChannelRateLimiter(
        min_interval_ms=200, clock=advancing_clock, sleep=advancing_sleep
    )

    async def worker() -> None:
        await limiter.acquire("shared-channel")
        results.append(advancing_clock())

    await asyncio.gather(*[worker() for _ in range(4)])

    # Verify all 4 got their timestamps, and each is ≥200ms apart from the previous
    assert len(results) == 4
    results.sort()
    for i in range(1, len(results)):
        gap = results[i] - results[i - 1]
        assert gap >= 0.199, (  # 1ms tolerance for float arithmetic
            f"Gap between call {i-1} and {i} was {gap*1000:.1f}ms, expected ≥200ms"
        )
