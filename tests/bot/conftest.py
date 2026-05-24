"""
tests/bot/conftest.py — shared fixtures for all bot tests.

Provides:
  - tmp_db_path: isolated SQLite path under tmp_path
  - bot_settings: Settings with test-safe values (no real Discord token, no .env)
  - bot_factory: constructs EldritchBot and runs setup_hook against a real tmp DB
  - running_bot: async fixture that yields a bot and calls close() in teardown
  - interaction_factory: builds a mock discord.Interaction with the correct shape

All fixtures avoid real Discord API calls — bot.start / bot.run are never called.
Pattern from RESEARCH.md Q2 / Q6.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio

# ── DB path ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db_path(tmp_path: pytest.TempPathFactory) -> str:
    """Return an isolated SQLite path for one test."""
    return str(tmp_path / "test_eldritch.sqlite3")


# ── Settings with test-safe values ───────────────────────────────────────────


@pytest.fixture
def bot_settings(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch):
    """Build Settings with safe test values; monkeypatch env to avoid .env interference."""
    # Patch env vars before importing Settings (pydantic-settings reads at construction)
    monkeypatch.setenv("DISCORD_TOKEN", "test-token-not-real")
    monkeypatch.setenv("DISCORD_GUILD_IDS", "")
    monkeypatch.setenv("ELDRITCH_DB_PATH", tmp_db_path)
    monkeypatch.setenv("OMLX_HEALTH_INTERVAL", "3600")  # effectively disable in unit tests
    monkeypatch.setenv("OMLX_CIRCUIT_BREAKER_THRESHOLD", "3")
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")  # quiet test output

    from eldritch_dm.config import Settings

    return Settings(
        discord_token="test-token-not-real",
        discord_guild_ids="",
        eldritch_db_path=tmp_db_path,
        omlx_health_interval=3600,
        omlx_circuit_breaker_threshold=3,
    )


# ── Bot factory ───────────────────────────────────────────────────────────────


@pytest.fixture
def bot_factory(bot_settings):
    """Return an async factory that builds EldritchBot and runs setup_hook.

    setup_hook is run against a real tmp DB. The caller is responsible for
    calling `await bot.close()` (or use the `running_bot` fixture instead).

    tree.sync is replaced with AsyncMock so no real Discord API calls happen.
    health.start is called with a high interval (3600s) so no ping fires in tests.

    Args (for the returned async callable):
        eldritch_db_path: Override the DB path (used by restart-drill tests
                          that want two bot instances sharing a tmp DB).
    """
    from eldritch_dm.bot.bot import EldritchBot
    from eldritch_dm.config import Settings

    async def _make(eldritch_db_path: str | None = None) -> EldritchBot:
        if eldritch_db_path is not None:
            # Build a Settings copy with the overridden DB path
            settings = Settings(
                discord_token=bot_settings.discord_token,
                discord_guild_ids=bot_settings.discord_guild_ids or "",
                eldritch_db_path=eldritch_db_path,
                omlx_health_interval=bot_settings.omlx_health_interval,
                omlx_circuit_breaker_threshold=bot_settings.omlx_circuit_breaker_threshold,
            )
        else:
            settings = bot_settings

        bot = EldritchBot(settings)
        # Prevent real Discord API calls during tree sync
        bot.tree.sync = AsyncMock(return_value=[])
        await bot.setup_hook()
        return bot

    return _make


# ── Running bot (with teardown) ───────────────────────────────────────────────


@pytest_asyncio.fixture
async def running_bot(bot_factory) -> AsyncIterator:
    """Async fixture: yields a started bot, closes it in teardown."""
    bot = await bot_factory()
    try:
        yield bot
    finally:
        await bot.close()


# ── Interaction factory ───────────────────────────────────────────────────────


@pytest.fixture
def interaction_factory():
    """Build a mock discord.Interaction with the correct shape.

    Each call returns a fresh mock. Arguments are keyword-only for clarity.

    Pattern: RESEARCH.md Q2 recipe — explicit AsyncMock for nested attrs.

    Args:
        user_id:    Snowflake int for interaction.user.id
        channel_id: Snowflake int for interaction.channel_id
        guild_id:   Optional guild snowflake (None for DM)
        custom_id:  Optional custom_id string (for button interactions)
    """

    def _make(
        *,
        user_id: int = 100,
        channel_id: int = 200,
        guild_id: int | None = 300,
        custom_id: str | None = None,
    ) -> discord.Interaction:
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = user_id
        interaction.channel_id = channel_id
        interaction.guild_id = guild_id
        interaction.data = {"custom_id": custom_id} if custom_id else {}

        # Explicit AsyncMock — spec doesn't reach nested attrs cleanly (RESEARCH Pitfall 6)
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.is_done = MagicMock(return_value=False)

        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        return interaction

    return _make
