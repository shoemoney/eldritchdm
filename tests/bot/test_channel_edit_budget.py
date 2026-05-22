"""
Tests for ChannelEditBudget — per-channel Discord edit rate budget.

TDD tests for Task 1 of Phase 4 Plan 01.
Discord's per-channel limit: 5 edits / 5 seconds.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from eldritch_dm.bot.coalescer import ChannelEditBudget, EmbedCoalescer


# ── Test 7: acquire is non-blocking when budget has capacity ──────────────────


async def test_acquire_nonblocking_with_capacity():
    """acquire() is non-blocking when the per-channel edit budget has capacity."""
    slept: list[float] = []

    async def capture_sleep(s: float) -> None:
        slept.append(s)

    clock = MagicMock(return_value=100.0)
    budget = ChannelEditBudget(
        channel_id="ch-1",
        limit=5,
        window_seconds=5.0,
        clock=clock,
        sleep=capture_sleep,
    )

    # First 5 acquires should all be immediate
    for i in range(5):
        await budget.acquire(f"msg-{i}")

    assert not slept, f"Expected no sleeps but got {slept}"


# ── Test 8: 6th acquire when 5 edits in window awaits ─────────────────────────


async def test_acquire_waits_when_budget_exhausted():
    """6th acquire waits until the oldest edit falls outside the 5s window."""
    slept: list[float] = []
    time_val = [0.0]

    def clock() -> float:
        return time_val[0]

    async def capture_sleep(s: float) -> None:
        slept.append(s)
        time_val[0] += s  # Advance the clock to simulate time passing

    budget = ChannelEditBudget(
        channel_id="ch-1",
        limit=5,
        window_seconds=5.0,
        clock=clock,
        sleep=capture_sleep,
    )

    # Fill the budget: 5 edits all at t=0.0
    for i in range(5):
        await budget.acquire(f"msg-{i}")

    # Now the budget is full; t=0.0, oldest edit at 0.0, window expires at 5.0
    await budget.acquire("msg-5")

    # Should have slept 5.0 seconds (oldest=0.0, window=5.0, now=0.0, wait=5.0)
    assert len(slept) >= 1
    assert abs(sum(slept) - 5.0) < 0.01, (
        f"Expected total sleep ~5.0s, got {sum(slept):.3f}s"
    )


# ── Test 9: EmbedCoalescer calls budget.acquire before message.edit ────────────


async def test_coalescer_calls_channel_budget_before_edit():
    """EmbedCoalescer calls channel_budget.acquire() BEFORE message.edit()."""
    import discord

    call_order: list[str] = []

    # Mock budget with call tracking
    mock_budget = MagicMock(spec=ChannelEditBudget)

    async def budget_acquire(message_id):
        call_order.append("budget_acquire")

    mock_budget.acquire = budget_acquire

    # Mock message
    mock_message = MagicMock(spec=discord.Message)
    mock_message.id = 999

    async def message_edit(**kwargs):
        call_order.append("message_edit")

    mock_message.edit = message_edit

    # Build coalescer with our mock budget and no real rate-limit sleep
    coalescer = EmbedCoalescer(
        mock_message,
        rate_limit_seconds=0.0,  # no per-message sleep
        channel_budget=mock_budget,
        clock=lambda: 0.0,
        sleep=AsyncMock(),
    )

    mock_embed = MagicMock(spec=discord.Embed)
    await coalescer.update(mock_embed)

    # Allow the render task to run
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    await coalescer.close()

    assert "budget_acquire" in call_order, "budget.acquire() was not called"
    assert "message_edit" in call_order, "message.edit() was not called"

    budget_idx = call_order.index("budget_acquire")
    edit_idx = call_order.index("message_edit")
    assert budget_idx < edit_idx, (
        f"budget_acquire ({budget_idx}) must come before message_edit ({edit_idx})"
    )


# ── Test 10: Coalescer with channel_budget=None remains unchanged ─────────────


async def test_coalescer_no_budget_unchanged():
    """EmbedCoalescer with channel_budget=None works as before (no regression)."""
    import discord

    edited: list[bool] = []

    mock_message = MagicMock(spec=discord.Message)
    mock_message.id = 42

    async def message_edit(**kwargs):
        edited.append(True)

    mock_message.edit = message_edit

    coalescer = EmbedCoalescer(
        mock_message,
        rate_limit_seconds=0.0,
        channel_budget=None,  # Phase 2 behavior
        clock=lambda: 0.0,
        sleep=AsyncMock(),
    )

    mock_embed = MagicMock(spec=discord.Embed)
    await coalescer.update(mock_embed)

    # Allow render task
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    await coalescer.close()

    assert edited, "message.edit() should have been called even without channel_budget"
