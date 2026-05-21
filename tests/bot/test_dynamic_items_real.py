"""
Phase 3 tests for the REAL ReadyButton.callback implementation.

Tests cover the state machine wired via interaction.client:
  - Defer-first (D-09 / EDM001)
  - No active session → ephemeral "No active session"
  - Non-roster user → ephemeral "Only seated players can ready up"
  - Partial ready (3/5) → ephemeral "Marked ready (3/5)"
  - All-ready transition → set_state EXPLORATION + player_action called + embed edit
  - persistent_views payload upsert called with correct args
  - ready_user_ids are deduped (same user clicking twice doesn't double-count)

Isolation: all I/O (MCP, DB repos) is replaced with AsyncMock / MagicMock.
The bot is a MagicMock with .mcp, .channel_sessions, and .pv_repo attributes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from eldritch_dm.bot.dynamic_items import ReadyButton
from eldritch_dm.persistence.models import ChannelSession, ChannelState


# ── Fixtures ────────────────────────────────────────────────────────────────────


def _make_channel_session(
    channel_id: str = "200",
    campaign_name: str = "TestCamp",
    claudmaster_session_id: str | None = "sess-abc",
    state: ChannelState = ChannelState.LOBBY,
) -> ChannelSession:
    from datetime import datetime, timezone
    return ChannelSession(
        channel_id=channel_id,
        campaign_name=campaign_name,
        claudmaster_session_id=claudmaster_session_id,
        dm20_party_token=None,
        state=state,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )


def _make_mock_client(
    channel_session=None,
    characters=None,
    persistent_view_payload=None,
):
    """Build a mock bot client with the three attributes ReadyButton.callback reads."""
    client = MagicMock()

    # channel_sessions repo
    cs_repo = AsyncMock()
    cs_repo.get.return_value = channel_session
    cs_repo.set_state = AsyncMock()
    client.channel_sessions = cs_repo

    # persistent_views repo (accessed via bot.pv_repo — discord.Client has a
    # `persistent_views` property so we cannot reuse that name on the bot)
    pv_repo = AsyncMock()
    if persistent_view_payload is not None:
        pv_view = MagicMock()
        pv_view.payload = persistent_view_payload
        pv_repo.get.return_value = pv_view
    else:
        pv_repo.get.return_value = None
    pv_repo.insert = AsyncMock()
    client.pv_repo = pv_repo

    # mcp client
    mcp = AsyncMock()
    char_list = characters or []
    mcp.call = AsyncMock(return_value={"characters": char_list})
    client.mcp = mcp

    return client


def _make_interaction(user_id: int = 100, channel_id: int = 200) -> discord.Interaction:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.user.display_name = f"User{user_id}"
    interaction.channel_id = channel_id

    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)

    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()

    msg = AsyncMock()
    msg.edit = AsyncMock()
    interaction.message = msg

    return interaction


# ── Test class ─────────────────────────────────────────────────────────────────


class TestReadyButtonReal:
    """Phase 3 real callback state machine tests."""

    @pytest.mark.asyncio
    async def test_defer_is_first_await(self):
        """callback defers ephemeral before any other I/O (D-09 / EDM001)."""
        call_order: list[str] = []

        session = _make_channel_session()
        client = _make_mock_client(
            channel_session=session,
            characters=[{"player_id": "100", "name": "Aragorn"}],
        )

        async def defer_side(**kwargs):
            call_order.append("defer")

        async def repo_get_side(*args, **kwargs):
            call_order.append("repo_get")
            return session

        interaction = _make_interaction(user_id=100, channel_id=200)
        interaction.response.defer.side_effect = defer_side
        client.channel_sessions.get.side_effect = repo_get_side
        interaction.client = client

        button = ReadyButton(channel_id=200)
        await button.callback(interaction)

        assert call_order[0] == "defer", f"defer was not first; order={call_order}"

    @pytest.mark.asyncio
    async def test_no_active_session_returns_early(self):
        """When no channel session exists, sends ephemeral 'No active session'."""
        client = _make_mock_client(channel_session=None)
        interaction = _make_interaction(user_id=100, channel_id=200)
        interaction.client = client

        button = ReadyButton(channel_id=200)
        await button.callback(interaction)

        interaction.followup.send.assert_awaited_once()
        sent_kwargs = interaction.followup.send.call_args
        content = sent_kwargs.kwargs.get("content") or (sent_kwargs.args[0] if sent_kwargs.args else "")
        assert "No active session" in content
        assert sent_kwargs.kwargs.get("ephemeral") is True
        # Must NOT write any state
        client.channel_sessions.set_state.assert_not_awaited()
        client.pv_repo.insert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_roster_user_rejected(self):
        """A user whose discord ID is not in the character roster is rejected."""
        session = _make_channel_session()
        client = _make_mock_client(
            channel_session=session,
            # Only player_id "999" is on the roster
            characters=[{"player_id": "999", "name": "Aragorn"}],
        )
        # User ID 100 (not 999) tries to ready up
        interaction = _make_interaction(user_id=100, channel_id=200)
        interaction.client = client

        button = ReadyButton(channel_id=200)
        await button.callback(interaction)

        interaction.followup.send.assert_awaited_once()
        sent_kwargs = interaction.followup.send.call_args
        content = sent_kwargs.kwargs.get("content") or (sent_kwargs.args[0] if sent_kwargs.args else "")
        assert "seated players" in content.lower() or "roster" in content.lower()
        assert sent_kwargs.kwargs.get("ephemeral") is True
        client.channel_sessions.set_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_partial_ready_sends_progress_message(self):
        """Partial ready: user added to list, no transition, returns count message."""
        session = _make_channel_session()
        # 5-person roster, user 100 is one of them
        characters = [
            {"player_id": str(i), "name": f"Char{i}"} for i in range(100, 105)
        ]
        client = _make_mock_client(
            channel_session=session,
            characters=characters,
            persistent_view_payload={"ready_user_ids": ["101", "102"]},  # 2 already ready
        )
        interaction = _make_interaction(user_id=100, channel_id=200)
        interaction.client = client

        button = ReadyButton(channel_id=200)
        await button.callback(interaction)

        # Should NOT transition
        client.channel_sessions.set_state.assert_not_awaited()
        # Should update persistent_views
        client.pv_repo.insert.assert_awaited_once()
        # Should send progress message
        interaction.followup.send.assert_awaited_once()
        sent_kwargs = interaction.followup.send.call_args
        content = sent_kwargs.kwargs.get("content") or (sent_kwargs.args[0] if sent_kwargs.args else "")
        assert "ready" in content.lower()
        assert sent_kwargs.kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_all_ready_transitions_to_exploration(self):
        """When all roster players are ready, state transitions to EXPLORATION."""
        session = _make_channel_session()
        # 2-person roster
        characters = [
            {"player_id": "100", "name": "Aragorn"},
            {"player_id": "101", "name": "Legolas"},
        ]
        # 101 already ready; user 100 is the last one
        client = _make_mock_client(
            channel_session=session,
            characters=characters,
            persistent_view_payload={"ready_user_ids": ["101"]},
        )
        interaction = _make_interaction(user_id=100, channel_id=200)
        interaction.client = client

        button = ReadyButton(channel_id=200)
        await button.callback(interaction)

        # Must transition
        client.channel_sessions.set_state.assert_awaited_once()
        call_args = client.channel_sessions.set_state.call_args
        assert call_args.args[1] == ChannelState.EXPLORATION or (
            call_args.kwargs.get("state") == ChannelState.EXPLORATION
        )

    @pytest.mark.asyncio
    async def test_all_ready_calls_player_action(self):
        """On all-ready transition, player_action is signalled with party_ready."""
        session = _make_channel_session(claudmaster_session_id="sess-xyz")
        characters = [
            {"player_id": "100", "name": "Aragorn"},
        ]
        client = _make_mock_client(
            channel_session=session,
            characters=characters,
            persistent_view_payload={"ready_user_ids": []},
        )
        interaction = _make_interaction(user_id=100, channel_id=200)
        interaction.client = client

        button = ReadyButton(channel_id=200)
        await button.callback(interaction)

        # player_action must have been called
        mcp_calls = client.mcp.call.call_args_list
        player_action_calls = [
            c for c in mcp_calls
            if c.args and c.args[0] == "dm20__player_action"
        ]
        assert len(player_action_calls) >= 1, "dm20__player_action was not called"
        call_kwargs = player_action_calls[0].kwargs
        assert call_kwargs.get("action") == "party_ready"
        assert call_kwargs.get("context") == "lobby_complete"

    @pytest.mark.asyncio
    async def test_persistent_views_upserted_with_correct_payload(self):
        """After ready, persistent_views is updated with the new ready_user_ids."""
        session = _make_channel_session()
        characters = [
            {"player_id": "100", "name": "Aragorn"},
            {"player_id": "101", "name": "Legolas"},
        ]
        client = _make_mock_client(
            channel_session=session,
            characters=characters,
            persistent_view_payload={"ready_user_ids": []},
        )
        interaction = _make_interaction(user_id=100, channel_id=200)
        interaction.client = client

        button = ReadyButton(channel_id=200)
        await button.callback(interaction)

        # pv_repo.insert should have been called
        client.pv_repo.insert.assert_awaited()
        insert_call = client.pv_repo.insert.call_args
        inserted_view = insert_call.args[0] if insert_call.args else insert_call.kwargs.get("view")
        assert inserted_view is not None
        assert "100" in inserted_view.payload.get("ready_user_ids", [])

    @pytest.mark.asyncio
    async def test_duplicate_ready_click_deduped(self):
        """Same user clicking ready twice only counts once."""
        session = _make_channel_session()
        characters = [
            {"player_id": "100", "name": "Aragorn"},
            {"player_id": "101", "name": "Legolas"},
        ]
        # User 100 already in ready list
        client = _make_mock_client(
            channel_session=session,
            characters=characters,
            persistent_view_payload={"ready_user_ids": ["100"]},
        )
        interaction = _make_interaction(user_id=100, channel_id=200)
        interaction.client = client

        button = ReadyButton(channel_id=200)
        await button.callback(interaction)

        # Should insert with deduped list (100 appears only once)
        insert_call = client.pv_repo.insert.call_args
        inserted_view = insert_call.args[0] if insert_call.args else insert_call.kwargs.get("view")
        if inserted_view:
            ready_ids = inserted_view.payload.get("ready_user_ids", [])
            assert ready_ids.count("100") == 1

    @pytest.mark.asyncio
    async def test_missing_persistent_view_treated_as_empty(self):
        """When no persistent_view row exists, payload defaults to {ready_user_ids: []}."""
        session = _make_channel_session()
        characters = [{"player_id": "100", "name": "Aragorn"}]
        # persistent_view not found
        client = _make_mock_client(
            channel_session=session,
            characters=characters,
            persistent_view_payload=None,  # repo.get returns None
        )
        interaction = _make_interaction(user_id=100, channel_id=200)
        interaction.client = client

        button = ReadyButton(channel_id=200)
        # Should not raise
        await button.callback(interaction)
        # Should eventually transition (single-player roster, user is on it)
        client.channel_sessions.set_state.assert_awaited_once()
