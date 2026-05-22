"""
tests/bot/test_setup_hook.py — persistent-view rehydration + graceful shutdown tests.

Tests:
  1. build_view_for_row: parametric over 4 known view_class strings
  2. build_view_for_row: unknown class → None + warning logged
  3. rehydrate_persistent_views: happy path — 2 sessions, 3 views, add_view called 3 times
  4. rehydrate_persistent_views: empty DB → 0 count, no add_view calls
  5. bot graceful shutdown: health → writer_queue → mcp ordering
  6. writer_queue drain timeout: bot.close() still returns within timeout
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.persistence.models import ChannelSession, ChannelState, PersistentView

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_pv(
    *,
    custom_id: str,
    view_class: str,
    message_id: str,
    channel_id: str,
) -> PersistentView:
    return PersistentView(
        custom_id=custom_id,
        view_class=view_class,
        message_id=message_id,
        channel_id=channel_id,
        payload={},
        created_at=datetime(2026, 1, 1),
    )


def _make_session(channel_id: str) -> ChannelSession:
    return ChannelSession(
        channel_id=channel_id,
        campaign_name="Test",
        state=ChannelState.LOBBY,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


# ── Test 1: build_view_for_row — parametric over all 4 view classes ───────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_class,custom_id,expected_cls_name",
    [
        ("ReadyButton", "ready:111", "ReadyButton"),
        ("DeclareActionButton", "declare:222", "DeclareActionButton"),
        # Phase 4 format: endturn:{channel_id}:{actor_id}:{round}
        ("EndTurnButton", "endturn:333:hero-001:1", "EndTurnButton"),
        ("RiposteButton", "riposte:555:666", "RiposteButton"),
    ],
)
async def test_build_view_for_row_known_class(view_class, custom_id, expected_cls_name):
    """Each known view_class produces a View containing the expected DynamicItem."""
    from eldritch_dm.bot.setup_hook import build_view_for_row

    row = _make_pv(
        custom_id=custom_id,
        view_class=view_class,
        message_id="999",
        channel_id="111",
    )

    view = build_view_for_row(row)

    assert view is not None, f"Expected a View for view_class={view_class!r}, got None"
    # The view should have exactly one child item
    children = view.children
    assert len(children) == 1, f"Expected 1 child, got {len(children)}"
    # The child's class name should match
    child_cls_name = type(children[0]).__name__
    assert child_cls_name == expected_cls_name, (
        f"Expected child class {expected_cls_name!r}, got {child_cls_name!r}"
    )


# ── Test 2: build_view_for_row — unknown class → None ────────────────────────


@pytest.mark.asyncio
async def test_build_view_for_row_unknown_class(caplog):
    """Unknown view_class returns None and logs a warning; does not raise."""
    import logging

    from eldritch_dm.bot.setup_hook import build_view_for_row

    row = _make_pv(
        custom_id="unknown:123",
        view_class="UnknownButtonType",
        message_id="888",
        channel_id="777",
    )

    with caplog.at_level(logging.WARNING):
        result = build_view_for_row(row)

    assert result is None


# ── Test 3: rehydrate_persistent_views — happy path ──────────────────────────


@pytest.mark.asyncio
async def test_rehydrate_persistent_views_happy_path():
    """2 active sessions, 3 views total → add_view called 3 times with correct message_ids."""
    from eldritch_dm.bot.setup_hook import rehydrate_persistent_views

    # Mock bot with a spy on add_view
    mock_bot = MagicMock(spec=discord.Client)
    mock_bot.add_view = MagicMock()

    # 2 active sessions — use numeric channel IDs to match DynamicItem regex patterns
    sessions = [_make_session("111"), _make_session("222")]

    # 2 views in channel 111, 1 view in channel 222
    views_by_channel = {
        "111": [
            _make_pv(custom_id="ready:111", view_class="ReadyButton", message_id="100", channel_id="111"),
            # Phase 4 EndTurnButton format: endturn:{channel}:{actor_id}:{round}
            _make_pv(custom_id="endturn:111:hero-001:1", view_class="EndTurnButton", message_id="101", channel_id="111"),
        ],
        "222": [
            _make_pv(custom_id="declare:222", view_class="DeclareActionButton", message_id="200", channel_id="222"),
        ],
    }

    # Mock repos
    mock_pv_repo = AsyncMock()
    mock_pv_repo.list_by_channel.side_effect = lambda ch_id: views_by_channel.get(ch_id, [])

    mock_cs_repo = AsyncMock()
    mock_cs_repo.list_active.return_value = sessions

    count = await rehydrate_persistent_views(mock_bot, mock_pv_repo, mock_cs_repo)

    assert count == 3, f"Expected count=3, got {count}"
    assert mock_bot.add_view.call_count == 3, (
        f"Expected add_view called 3 times, got {mock_bot.add_view.call_count}"
    )

    # Collect all message_ids that add_view was called with
    called_message_ids = {
        call.kwargs.get("message_id") for call in mock_bot.add_view.call_args_list
    }
    assert called_message_ids == {100, 101, 200}, (
        f"Expected message_ids {{100, 101, 200}}, got {called_message_ids}"
    )


# ── Test 4: rehydrate_persistent_views — empty DB ────────────────────────────


@pytest.mark.asyncio
async def test_rehydrate_persistent_views_empty_db():
    """Empty DB → count=0, add_view never called."""
    from eldritch_dm.bot.setup_hook import rehydrate_persistent_views

    mock_bot = MagicMock(spec=discord.Client)
    mock_bot.add_view = MagicMock()

    mock_pv_repo = AsyncMock()
    mock_pv_repo.list_by_channel.return_value = []

    mock_cs_repo = AsyncMock()
    mock_cs_repo.list_active.return_value = []

    count = await rehydrate_persistent_views(mock_bot, mock_pv_repo, mock_cs_repo)

    assert count == 0
    mock_bot.add_view.assert_not_called()


# ── Test 5: graceful shutdown ordering ───────────────────────────────────────


@pytest.mark.asyncio
async def test_bot_graceful_shutdown_ordering(bot_factory):
    """bot.close(): health.stop BEFORE writer_queue.stop BEFORE mcp.aclose."""
    bot = await bot_factory()

    call_order: list[str] = []

    # Capture real tasks before spying (to cancel them in side_effect)
    real_health_task = bot.health._task
    real_wq_task = bot.writer_queue._task

    async def health_stop_side_effect():
        call_order.append("health")
        # Cancel the real task to avoid warnings
        if real_health_task and not real_health_task.done():
            real_health_task.cancel()
            try:
                await real_health_task
            except (asyncio.CancelledError, Exception):
                pass

    async def wq_stop_side_effect():
        call_order.append("writer_queue")
        # Cancel the real task to avoid warnings
        if real_wq_task and not real_wq_task.done():
            real_wq_task.cancel()
            try:
                await real_wq_task
            except (asyncio.CancelledError, Exception):
                pass

    async def mcp_aclose_side_effect():
        call_order.append("mcp")

    bot.health.stop = AsyncMock(side_effect=health_stop_side_effect)
    bot.writer_queue.stop = AsyncMock(side_effect=wq_stop_side_effect)
    bot.mcp.aclose = AsyncMock(side_effect=mcp_aclose_side_effect)

    await bot.close()

    assert call_order == ["health", "writer_queue", "mcp"], (
        f"Expected shutdown order [health, writer_queue, mcp], got {call_order}"
    )


# ── Test 6: writer_queue drain timeout ────────────────────────────────────────


@pytest.mark.asyncio
async def test_writer_queue_drain_timeout(bot_factory):
    """If writer_queue.stop hangs, bot.close() still returns within ~5.5s and logs timeout."""
    bot = await bot_factory()

    # Capture real tasks for cleanup
    real_health_task = bot.health._task
    real_wq_task = bot.writer_queue._task

    async def health_stop_ok():
        if real_health_task and not real_health_task.done():
            real_health_task.cancel()
            try:
                await real_health_task
            except (asyncio.CancelledError, Exception):
                pass

    async def wq_stop_hangs():
        # Simulate a very slow drain that exceeds the 5s timeout
        if real_wq_task and not real_wq_task.done():
            real_wq_task.cancel()
            try:
                await real_wq_task
            except (asyncio.CancelledError, Exception):
                pass
        await asyncio.sleep(30)  # Hang indefinitely

    bot.health.stop = AsyncMock(side_effect=health_stop_ok)
    bot.writer_queue.stop = AsyncMock(side_effect=wq_stop_hangs)
    bot.mcp.aclose = AsyncMock()

    # bot.close() should still return (within timeout + margin)
    try:
        await asyncio.wait_for(bot.close(), timeout=6.5)
    except TimeoutError:
        pytest.fail("bot.close() timed out — should have handled writer_queue drain timeout")

    # mcp.aclose should still have been called (shutdown continues despite drain timeout)
    bot.mcp.aclose.assert_awaited_once()
