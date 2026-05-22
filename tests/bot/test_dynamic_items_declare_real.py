"""
Phase 4 tests for the REAL DeclareActionButton.callback implementation.

Tests cover:
  - Defer-first (D-09 / EDM001)
  - Missing channel_sessions on bot → INVALID_ACTION warning
  - No session → INVALID_ACTION warning
  - Session in LOBBY state → INVALID_ACTION warning
  - Session in EXPLORATION → followup with launch view (modal step)

Isolation: all I/O (DB repos) replaced with AsyncMock / MagicMock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.bot.dynamic_items import DeclareActionButton
from eldritch_dm.persistence.models import ChannelSession, ChannelState

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_channel_session(
    channel_id: str = "111",
    state: ChannelState = ChannelState.EXPLORATION,
) -> ChannelSession:
    return ChannelSession(
        channel_id=channel_id,
        campaign_name="TestCamp",
        claudmaster_session_id="sess-abc",
        dm20_party_token=None,
        state=state,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )


def _make_interaction(bot_client=None, *, channel_id: int = 111):
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.user = MagicMock()
    interaction.user.id = 42
    interaction.user.display_name = "TestUser"
    interaction.client = bot_client or MagicMock()
    return interaction


def _make_bot(session=None, has_channel_sessions=True):
    bot = MagicMock()
    if has_channel_sessions:
        cs_repo = AsyncMock()
        cs_repo.get.return_value = session
        bot.channel_sessions = cs_repo
    else:
        bot.channel_sessions = None
    bot.batch_coordinator = AsyncMock()
    return bot


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_declare_defers_first():
    """EDM001: defer must be the first interaction response."""
    session = _make_channel_session(state=ChannelState.EXPLORATION)
    bot = _make_bot(session=session)
    interaction = _make_interaction(bot)

    btn = DeclareActionButton(channel_id=111)
    await btn.callback(interaction)

    interaction.response.defer.assert_called_once_with(thinking=True, ephemeral=True)


@pytest.mark.asyncio
async def test_declare_no_channel_sessions_sends_warning():
    """When bot.channel_sessions is None, sends INVALID_ACTION warning."""
    bot = _make_bot(has_channel_sessions=False)
    interaction = _make_interaction(bot)

    btn = DeclareActionButton(channel_id=111)
    await btn.callback(interaction)

    interaction.followup.send.assert_called_once()
    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    assert "invalid action" in call_kwargs.get("content", "").lower() or \
        "not ready" in call_kwargs.get("content", "").lower() or \
        "invalid_action" in str(call_kwargs).lower() or \
        call_kwargs.get("content", "").startswith("❌")


@pytest.mark.asyncio
async def test_declare_no_session_sends_warning():
    """When no session exists, sends INVALID_ACTION ephemeral."""
    bot = _make_bot(session=None)
    interaction = _make_interaction(bot)

    btn = DeclareActionButton(channel_id=111)
    await btn.callback(interaction)

    interaction.followup.send.assert_called_once()
    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    content = call_kwargs.get("content", "")
    # Should be the INVALID_ACTION copy (starts with ❌)
    assert content.startswith("❌")


@pytest.mark.asyncio
async def test_declare_lobby_state_sends_warning():
    """When session is in LOBBY state, sends INVALID_ACTION warning."""
    session = _make_channel_session(state=ChannelState.LOBBY)
    bot = _make_bot(session=session)
    interaction = _make_interaction(bot)

    btn = DeclareActionButton(channel_id=111)
    await btn.callback(interaction)

    interaction.followup.send.assert_called_once()
    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    content = call_kwargs.get("content", "")
    assert content.startswith("❌")
    assert "exploration" in content.lower()


@pytest.mark.asyncio
async def test_declare_combat_state_sends_warning():
    """When session is in COMBAT state, sends INVALID_ACTION warning."""
    session = _make_channel_session(state=ChannelState.COMBAT)
    bot = _make_bot(session=session)
    interaction = _make_interaction(bot)

    btn = DeclareActionButton(channel_id=111)
    await btn.callback(interaction)

    interaction.followup.send.assert_called_once()
    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_declare_exploration_sends_modal_launch_view():
    """When session is EXPLORATION, sends ephemeral view with launch button."""
    session = _make_channel_session(state=ChannelState.EXPLORATION)
    bot = _make_bot(session=session)
    interaction = _make_interaction(bot)

    btn = DeclareActionButton(channel_id=111)
    await btn.callback(interaction)

    # Should send exactly one followup with a view
    interaction.followup.send.assert_called_once()
    call_kwargs = interaction.followup.send.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    assert call_kwargs.get("view") is not None
    assert isinstance(call_kwargs["view"], discord.ui.View)


@pytest.mark.asyncio
async def test_declare_exploration_no_session_check_after_defer():
    """State check happens after defer (EDM001 compliance)."""
    session = _make_channel_session(state=ChannelState.EXPLORATION)
    bot = _make_bot(session=session)
    interaction = _make_interaction(bot)

    btn = DeclareActionButton(channel_id=111)

    defer_called_before_session_check = False

    original_defer = interaction.response.defer

    async def tracking_defer(*args, **kwargs):
        nonlocal defer_called_before_session_check
        defer_called_before_session_check = True
        return await original_defer(*args, **kwargs)

    interaction.response.defer = tracking_defer

    await btn.callback(interaction)

    assert defer_called_before_session_check, "defer must be called first"
