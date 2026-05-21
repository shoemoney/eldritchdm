"""
Bot lifecycle tests — startup, shutdown, intents, tree sync.

TDD RED: written before testing; implementation is in bot.py (already GREEN
from Task 2, so these will go directly GREEN on first run — still using TDD
discipline to document the expected behaviors).

All tests avoid real Discord API calls:
- bot.start / bot.run are never called
- bot.tree.sync is replaced with AsyncMock(return_value=[]) in bot_factory
- HealthCheck interval is 3600s → first ping never fires during test window
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

from eldritch_dm.mcp.health import CircuitState


# ── Test 1: setup_hook initializes all subsystems ────────────────────────────


@pytest.mark.asyncio
async def test_setup_hook_initializes_subsystems(bot_factory, tmp_db_path):
    """After setup_hook: writer_queue started, circuit_breaker CLOSED,
    mcp exists, health exists, schema tables present, Diagnostics cog loaded.
    """
    bot = await bot_factory()
    try:
        # WriterQueue is started (has a running background task)
        assert bot.writer_queue is not None
        assert bot.writer_queue._task is not None
        assert not bot.writer_queue._task.done()

        # CircuitBreaker starts CLOSED
        assert bot.circuit_breaker is not None
        assert bot.circuit_breaker.state == CircuitState.CLOSED

        # MCP client is constructed
        assert bot.mcp is not None

        # HealthCheck is running
        assert bot.health is not None
        assert bot.health._task is not None

        # ChannelSessionRepo is attached
        assert bot.channel_sessions_repo is not None

        # Schema was applied: verify the four tables exist
        expected_tables = {"channel_sessions", "persistent_views", "riposte_timers", "sanitizer_audit"}
        async with aiosqlite.connect(tmp_db_path) as conn:
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cur:
                rows = await cur.fetchall()
        actual_tables = {row[0] for row in rows}
        assert expected_tables <= actual_tables, (
            f"Missing tables: {expected_tables - actual_tables}"
        )

        # Diagnostics cog is loaded
        assert bot.get_cog("Diagnostics") is not None

    finally:
        await bot.close()


# ── Test 2: close cleanly shuts down all subsystems ──────────────────────────


@pytest.mark.asyncio
async def test_close_cleanly_shuts_down(bot_factory, mocker):
    """After bot.close(): health.stop, mcp.aclose, writer_queue.stop all awaited."""
    bot = await bot_factory()

    # Grab the real tasks so we can cancel them manually after asserting
    real_health_task = bot.health._task
    real_wq_task = bot.writer_queue._task

    async def fake_health_stop():
        """Cancel the real HealthCheck task to avoid 'Task destroyed' warnings."""
        import asyncio as _asyncio
        if real_health_task and not real_health_task.done():
            real_health_task.cancel()
            try:
                await real_health_task
            except (_asyncio.CancelledError, Exception):
                pass

    async def fake_wq_stop():
        """Cancel the real WriterQueue task to avoid 'Task destroyed' warnings."""
        import asyncio as _asyncio
        if real_wq_task and not real_wq_task.done():
            real_wq_task.cancel()
            try:
                await real_wq_task
            except (_asyncio.CancelledError, Exception):
                pass

    # Spy on the three shutdown methods (with side effects that do real cleanup)
    health_stop_spy = mocker.patch.object(bot.health, "stop", new=AsyncMock(side_effect=fake_health_stop))
    mcp_close_spy = mocker.patch.object(bot.mcp, "aclose", new=AsyncMock())
    wq_stop_spy = mocker.patch.object(bot.writer_queue, "stop", new=AsyncMock(side_effect=fake_wq_stop))

    await bot.close()

    health_stop_spy.assert_awaited_once()
    mcp_close_spy.assert_awaited_once()
    wq_stop_spy.assert_awaited_once()


# ── Test 3: setup_hook failure propagates (does not swallow) ──────────────────


@pytest.mark.asyncio
async def test_setup_hook_failure_is_fatal(bot_settings, mocker):
    """A failure in setup_hook must propagate as an exception (D-25)."""
    from eldritch_dm.bot.bot import EldritchBot

    bot = EldritchBot(bot_settings)
    # Prevent real Discord API calls during tree sync
    bot.tree.sync = AsyncMock(return_value=[])

    # Patch 'bootstrap' in the bot module's namespace (where it was imported to)
    mocker.patch(
        "eldritch_dm.bot.bot.bootstrap",
        new=AsyncMock(side_effect=RuntimeError("schema failed")),
    )

    with pytest.raises(RuntimeError, match="schema failed"):
        await bot.setup_hook()


# ── Test 4: intents are minimal (message_content is False) ───────────────────


@pytest.mark.asyncio
async def test_intents_are_minimal(bot_settings):
    """Bot intents must have message_content=False (D-04 security choice)."""
    from eldritch_dm.bot.bot import EldritchBot

    bot = EldritchBot(bot_settings)
    assert bot.intents.message_content is False, (
        "message_content must be False: bot cannot read raw messages (D-04)"
    )


# ── Test 5: global sync when guild_ids is empty ───────────────────────────────


@pytest.mark.asyncio
async def test_no_guild_sync_when_empty(bot_settings, mocker):
    """When discord_guild_ids='', tree.sync() is called WITHOUT a guild= kwarg."""
    from eldritch_dm.bot.bot import EldritchBot

    bot = EldritchBot(bot_settings)  # guild_ids="" in bot_settings

    sync_mock = AsyncMock(return_value=[])
    bot.tree.sync = sync_mock

    try:
        await bot.setup_hook()

        # Should be called once with no guild= kwarg (global sync)
        sync_mock.assert_awaited_once()
        call_kwargs = sync_mock.call_args
        assert "guild" not in (call_kwargs.kwargs or {}), (
            "Global sync must NOT pass guild= argument"
        )
    finally:
        await bot.close()


# ── Test 6: per-guild sync when guild_ids configured ─────────────────────────


@pytest.mark.asyncio
async def test_per_guild_sync_when_configured(tmp_db_path, monkeypatch, mocker):
    """When discord_guild_ids='123,456', tree.sync is called once per guild."""
    from eldritch_dm.config import Settings
    from eldritch_dm.bot.bot import EldritchBot
    import discord

    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    settings = Settings(
        discord_token="test-token",
        discord_guild_ids="123,456",
        eldritch_db_path=tmp_db_path,
        omlx_health_interval=3600,
    )

    bot = EldritchBot(settings)
    sync_mock = AsyncMock(return_value=[])
    bot.tree.sync = sync_mock

    try:
        await bot.setup_hook()

        # Should be called twice — once per guild
        assert sync_mock.await_count == 2, (
            f"Expected 2 sync calls (one per guild), got {sync_mock.await_count}"
        )

        # Each call should pass guild= with the correct IDs
        call_args_list = sync_mock.call_args_list
        guild_ids_passed = {
            call.kwargs["guild"].id for call in call_args_list if "guild" in (call.kwargs or {})
        }
        assert guild_ids_passed == {123, 456}, (
            f"Expected guild IDs {{123, 456}}, got {guild_ids_passed}"
        )
    finally:
        await bot.close()
