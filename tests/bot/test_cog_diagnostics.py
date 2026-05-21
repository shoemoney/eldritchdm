"""
Tests for the Diagnostics cog (/ping and /status slash commands).

All Discord API calls are mocked — no real gateway connection.
Pattern from RESEARCH.md Q2: MagicMock(spec=discord.Interaction) with
explicit AsyncMock for .response.defer and .followup.send.

TDD RED phase: these tests are written BEFORE the implementation.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, call

import discord


@pytest.fixture
def interaction_factory():
    """Build a mock discord.Interaction with the correct shape.

    Follows the recipe from 02-RESEARCH.md Q2.
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

        # Explicit AsyncMock — spec doesn't reach nested attrs cleanly
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.is_done = MagicMock(return_value=False)

        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        return interaction

    return _make


@pytest.fixture
def mock_bot(tmp_path):
    """Build a minimal mock EldritchBot for cog tests (no real DB, no real Discord)."""
    from eldritch_dm.mcp.health import CircuitBreaker, CircuitState
    from eldritch_dm.config import Settings
    from unittest.mock import MagicMock, AsyncMock

    bot = MagicMock()
    bot.circuit_breaker = CircuitBreaker(threshold=3)

    # Settings with a recognizable endpoint URL
    bot.settings = MagicMock(spec=Settings)
    bot.settings.omlx_endpoint = "http://localhost:8765/v1"

    # Stub channel_sessions_repo
    bot.channel_sessions_repo = MagicMock()
    bot.channel_sessions_repo.get = AsyncMock(return_value=None)

    # Stub MCP client
    bot.mcp = MagicMock()

    return bot


@pytest.fixture
def diagnostics_cog(mock_bot):
    """Instantiate the Diagnostics cog bound to mock_bot."""
    from eldritch_dm.bot.cogs.diagnostics import Diagnostics

    return Diagnostics(mock_bot)


# ─── Test 1: /ping with CLOSED circuit ──────────────────────────────────────

@pytest.mark.asyncio
async def test_ping_closed_circuit(diagnostics_cog, interaction_factory):
    """When circuit breaker is CLOSED, /ping followup contains 'CLOSED' and endpoint."""
    interaction = interaction_factory(user_id=42, channel_id=999)

    # Call the underlying callback method (bypass decorator routing)
    await diagnostics_cog.ping.callback(diagnostics_cog, interaction)

    interaction.followup.send.assert_awaited_once()
    call_kwargs = interaction.followup.send.call_args
    content = call_kwargs.kwargs.get("content", "") or (
        call_kwargs.args[0] if call_kwargs.args else ""
    )
    assert "CLOSED" in content
    assert "8765" in content or "localhost" in content


# ─── Test 2: /ping with OPEN circuit ────────────────────────────────────────

@pytest.mark.asyncio
async def test_ping_open_circuit(diagnostics_cog, interaction_factory):
    """After forcing the circuit breaker OPEN, /ping followup contains 'OPEN'."""
    # Trip the breaker (threshold=3 failures)
    for _ in range(3):
        diagnostics_cog.bot.circuit_breaker.record_failure()

    interaction = interaction_factory(user_id=42, channel_id=999)
    await diagnostics_cog.ping.callback(diagnostics_cog, interaction)

    interaction.followup.send.assert_awaited_once()
    call_kwargs = interaction.followup.send.call_args
    content = call_kwargs.kwargs.get("content", "") or (
        call_kwargs.args[0] if call_kwargs.args else ""
    )
    assert "OPEN" in content


# ─── Test 3: /status with no session ────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_no_session(diagnostics_cog, interaction_factory):
    """/status returns 'No active session' when no row exists in the DB."""
    diagnostics_cog.bot.channel_sessions_repo.get = AsyncMock(return_value=None)
    interaction = interaction_factory(channel_id=999)

    await diagnostics_cog.status.callback(diagnostics_cog, interaction)

    interaction.followup.send.assert_awaited_once()
    call_kwargs = interaction.followup.send.call_args
    content = call_kwargs.kwargs.get("content", "") or (
        call_kwargs.args[0] if call_kwargs.args else ""
    )
    assert "No active session" in content


# ─── Test 4: /status with an active session ──────────────────────────────────

@pytest.mark.asyncio
async def test_status_with_session(diagnostics_cog, interaction_factory):
    """/status returns state and campaign name when a session row exists."""
    from eldritch_dm.persistence.models import ChannelSession, ChannelState
    from datetime import datetime

    session = ChannelSession(
        channel_id="999",
        campaign_name="Curse of Strahd",
        state=ChannelState.EXPLORATION,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    diagnostics_cog.bot.channel_sessions_repo.get = AsyncMock(return_value=session)
    interaction = interaction_factory(channel_id=999)

    await diagnostics_cog.status.callback(diagnostics_cog, interaction)

    interaction.followup.send.assert_awaited_once()
    call_kwargs = interaction.followup.send.call_args
    content = call_kwargs.kwargs.get("content", "") or (
        call_kwargs.args[0] if call_kwargs.args else ""
    )
    assert "EXPLORATION" in content or "Exploration" in content
    assert "Curse of Strahd" in content


# ─── Test 5: defer is called BEFORE followup ─────────────────────────────────

@pytest.mark.asyncio
async def test_ping_defer_before_followup(diagnostics_cog, interaction_factory):
    """The /ping callback's first observable await must be interaction.response.defer.

    Verifies D-09: defer-first discipline.
    """
    call_order: list[str] = []

    interaction = interaction_factory(user_id=42, channel_id=999)

    # Replace with order-tracking mocks
    async def tracking_defer(*args, **kwargs):
        call_order.append("defer")

    async def tracking_send(*args, **kwargs):
        call_order.append("send")

    interaction.response.defer = AsyncMock(side_effect=tracking_defer)
    interaction.followup.send = AsyncMock(side_effect=tracking_send)

    await diagnostics_cog.ping.callback(diagnostics_cog, interaction)

    assert call_order[0] == "defer", f"Expected defer first, got: {call_order}"
    assert "send" in call_order
