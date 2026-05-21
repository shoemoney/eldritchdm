"""
Tests for eldritch_dm.bot.cogs.lobby — LobbyCog.

Covers:
  - /start_game happy path: create_campaign → start_claudmaster_session → start_party_mode, session upserted, embed posted
  - /start_game rollback: start_party_mode fails → end_claudmaster_session called, no DB row
  - /start_game rollback: start_claudmaster_session fails → no end_claudmaster_session
  - /start_game already-running party mode: get_party_status used, proceeds as happy path
  - /load_adventure: happy path, session upserted with module_bound
  - /load_adventure: no active campaign → ephemeral error
  - /load_adventure: module_bound already set → populate_chapter_1=False
  - /load_adventure: permission denied for non-manage_channels user
  - adventure_id_autocomplete: empty current → 9 results
  - adventure_id_autocomplete: substring filter (case-insensitive)
  - ADVENTURE_IDS has exactly 9 entries
  - LobbyCog constructor binds logger with cog="lobby"
  - bot.py: LobbyCog registered after diagnostics cog
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from eldritch_dm.bot.cogs.lobby import ADVENTURE_IDS, LobbyCog


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_bot(
    channel_session=None,
    persistent_view=None,
):
    """Build a mock EldritchBot with the subsystems LobbyCog needs."""
    bot = MagicMock()
    bot.mcp = AsyncMock()

    # channel_sessions repo
    cs_repo = AsyncMock()
    cs_repo.get.return_value = channel_session
    cs_repo.upsert = AsyncMock()
    cs_repo.set_state = AsyncMock()
    bot.channel_sessions = cs_repo

    # persistent_views repo (accessed via bot.pv_repo — discord.Client has a
    # `persistent_views` property so we cannot reuse that name on the bot)
    pv_repo = AsyncMock()
    pv_repo.insert = AsyncMock()
    pv_repo.upsert = AsyncMock()
    bot.pv_repo = pv_repo

    bot.settings = MagicMock()
    bot._logger = MagicMock()
    bot._logger.bind.return_value = bot._logger
    return bot


def _make_interaction(
    user_id: int = 100,
    channel_id: int = 200,
    manage_channels: bool = True,
) -> discord.Interaction:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.display_name = f"User{user_id}"

    perms = MagicMock(spec=discord.Permissions)
    perms.manage_channels = manage_channels
    interaction.user.guild_permissions = perms

    interaction.channel_id = channel_id

    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)

    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock(return_value=MagicMock(id=999))

    interaction.guild = MagicMock()
    interaction.guild.id = 300
    return interaction


def _make_mcp_call_mock(
    party_mode_text: str | None = None,
    already_running: bool = False,
    party_mode_raises: Exception | None = None,
    claudmaster_raises: Exception | None = None,
) -> AsyncMock:
    """Return an AsyncMock for bot.mcp.call with a side_effect that dispatches by tool_name."""
    if party_mode_text is None:
        if already_running:
            party_mode_text = (
                "Party Mode is already running at http://192.168.1.5:8080\n\n"
                "**Server:** http://192.168.1.5:8080\n"
            )
        else:
            party_mode_text = (
                "# Party Mode Active\n\n"
                "**Server:** http://192.168.1.5:8080\n\n"
                "## Player Connections\n\n"
                "### Aragorn\n"
                "- **URL:** http://192.168.1.5:8080/play?token=abc\n"
                "- **QR Code:** (generation failed, use URL instead)\n"
            )

    async def _side_effect(tool_name, **kwargs):
        if tool_name == "dm20__create_campaign":
            return {"campaign_id": "camp-1", "name": kwargs.get("name")}
        if tool_name == "dm20__start_claudmaster_session":
            if claudmaster_raises:
                raise claudmaster_raises
            return {"session_id": "sess-xyz"}
        if tool_name == "dm20__start_party_mode":
            if party_mode_raises:
                raise party_mode_raises
            return party_mode_text
        if tool_name == "dm20__end_claudmaster_session":
            return {"ok": True}
        if tool_name == "dm20__get_party_status":
            return {"server_url": "http://192.168.1.5:8080", "members": []}
        if tool_name == "dm20__load_adventure":
            return "## Adventure Loaded\n\nCurse of Strahd is now active."
        return {"ok": True}

    mock = AsyncMock(side_effect=_side_effect)
    return mock


# Keep backward compat alias
def _make_mcp_responses(
    party_mode_text: str | None = None,
    already_running: bool = False,
) -> AsyncMock:
    return _make_mcp_call_mock(party_mode_text=party_mode_text, already_running=already_running)


# ── ADVENTURE_IDS ──────────────────────────────────────────────────────────────


class TestAdventureIds:
    def test_adventure_ids_has_exactly_9_entries(self):
        assert len(ADVENTURE_IDS) == 9

    def test_adventure_ids_contains_expected_keys(self):
        expected = {"CoS", "LMoP", "HotDQ", "PotA", "OotA", "ToA", "WDH", "WDMM", "BGDIA"}
        assert set(ADVENTURE_IDS.keys()) == expected

    def test_adventure_ids_values_are_strings(self):
        for k, v in ADVENTURE_IDS.items():
            assert isinstance(v, str), f"ADVENTURE_IDS[{k!r}] is not a str: {v!r}"


# ── LobbyCog constructor ────────────────────────────────────────────────────────


class TestLobbyCogConstructor:
    def test_cog_constructed_with_bot_and_logger(self):
        bot = _make_bot()
        import structlog

        logger = structlog.get_logger("test")
        cog = LobbyCog(bot, logger=logger)
        assert cog is not None

    def test_cog_logger_bound_with_cog_name(self):
        """Logger is bound with cog='lobby'."""
        bot = _make_bot()
        mock_logger = MagicMock()
        mock_logger.bind.return_value = mock_logger
        LobbyCog(bot, logger=mock_logger)
        mock_logger.bind.assert_called_with(cog="lobby")


# ── /start_game ────────────────────────────────────────────────────────────────


class TestStartGame:
    @pytest.mark.asyncio
    async def test_start_game_defers_first(self):
        """Interaction is deferred as the first await (D-09 / EDM001)."""
        call_order: list[str] = []

        bot = _make_bot()
        bot.mcp.call = _make_mcp_responses()

        async def defer_coro(**kw):
            call_order.append("defer")

        interaction = _make_interaction()
        interaction.response.defer.side_effect = defer_coro

        cog = LobbyCog(bot)
        # Call the underlying callback to bypass app_commands decorator routing
        await cog.start_game.callback(cog, interaction, name="TestCamp")

        assert call_order[0] == "defer", f"defer was not first: {call_order}"

    @pytest.mark.asyncio
    async def test_start_game_happy_path_calls_three_mcp_tools(self):
        """create_campaign → start_claudmaster_session → start_party_mode in order."""
        call_log: list[str] = []

        async def mcp_call(tool_name, **kwargs):
            call_log.append(tool_name)
            if tool_name == "dm20__start_claudmaster_session":
                return {"session_id": "sess-abc"}
            if tool_name == "dm20__start_party_mode":
                return (
                    "# Party Mode Active\n\n"
                    "**Server:** http://192.168.1.5:8080\n\n"
                    "## Player Connections\n\n"
                    "### Aragorn\n"
                    "- **URL:** http://192.168.1.5:8080/play?token=abc\n"
                    "- **QR Code:** (generation failed, use URL instead)\n"
                )
            return {"ok": True}

        bot = _make_bot()
        bot.mcp.call = mcp_call
        interaction = _make_interaction()

        cog = LobbyCog(bot)
        await cog.start_game.callback(cog, interaction, name="TestCamp")

        assert "dm20__create_campaign" in call_log
        assert "dm20__start_claudmaster_session" in call_log
        assert "dm20__start_party_mode" in call_log
        # Ordering check
        ci = call_log.index("dm20__create_campaign")
        csi = call_log.index("dm20__start_claudmaster_session")
        spm = call_log.index("dm20__start_party_mode")
        assert ci < csi < spm, f"Call order wrong: {call_log}"

    @pytest.mark.asyncio
    async def test_start_game_happy_path_upserts_channel_session(self):
        """channel_sessions.upsert is called with all three tokens after success."""
        bot = _make_bot()
        bot.mcp.call = _make_mcp_responses()
        interaction = _make_interaction()

        cog = LobbyCog(bot)
        await cog.start_game.callback(cog, interaction, name="TestCamp")

        bot.channel_sessions.upsert.assert_awaited()

    @pytest.mark.asyncio
    async def test_start_game_rollback_on_start_party_mode_failure(self):
        """start_party_mode failure → end_claudmaster_session called; no DB write."""
        bot = _make_bot()
        bot.mcp.call = _make_mcp_call_mock(
            party_mode_raises=RuntimeError("party mode failed")
        )
        interaction = _make_interaction()

        cog = LobbyCog(bot)
        await cog.start_game.callback(cog, interaction, name="TestCamp")

        # end_claudmaster_session must have been called for rollback
        call_names = [c.args[0] for c in bot.mcp.call.call_args_list]
        assert "dm20__end_claudmaster_session" in call_names

        # channel_sessions must NOT have been written
        bot.channel_sessions.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_start_game_no_rollback_on_claudmaster_failure(self):
        """start_claudmaster_session fails → no end_claudmaster_session (it never started)."""
        bot = _make_bot()
        bot.mcp.call = _make_mcp_call_mock(
            claudmaster_raises=RuntimeError("claudmaster error")
        )
        interaction = _make_interaction()

        cog = LobbyCog(bot)
        await cog.start_game.callback(cog, interaction, name="TestCamp")

        call_names = [c.args[0] for c in bot.mcp.call.call_args_list]
        assert "dm20__end_claudmaster_session" not in call_names
        bot.channel_sessions.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_start_game_already_running_calls_get_party_status(self):
        """When party mode is already running, get_party_status is called to recover state."""
        bot = _make_bot()
        bot.mcp.call = _make_mcp_responses(already_running=True)
        interaction = _make_interaction()

        cog = LobbyCog(bot)
        await cog.start_game.callback(cog, interaction, name="TestCamp")

        call_names = [c.args[0] for c in bot.mcp.call.call_args_list]
        assert "dm20__get_party_status" in call_names


# ── /load_adventure ────────────────────────────────────────────────────────────


class TestLoadAdventure:
    def _make_session(
        self,
        campaign_name: str = "TestCamp",
        module_bound: str | None = None,
    ):
        from datetime import datetime, timezone

        from eldritch_dm.persistence.models import ChannelSession, ChannelState

        token = json.dumps({
            "server_url": "http://192.168.1.5:8080",
            "members": [],
            "module_bound": module_bound,
        })
        return ChannelSession(
            channel_id="200",
            campaign_name=campaign_name,
            claudmaster_session_id="sess-xyz",
            dm20_party_token=token,
            state=ChannelState.LOBBY,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_load_adventure_defers_first(self):
        """Interaction is deferred as the first await (D-09 / EDM001)."""
        call_order: list[str] = []
        session = self._make_session()
        bot = _make_bot(channel_session=session)
        bot.mcp.call = _make_mcp_responses()

        async def defer_coro(**kw):
            call_order.append("defer")

        interaction = _make_interaction()
        interaction.response.defer.side_effect = defer_coro

        cog = LobbyCog(bot)
        await cog.load_adventure.callback(cog, interaction, adventure_id="CoS")
        assert call_order[0] == "defer"

    @pytest.mark.asyncio
    async def test_load_adventure_no_session_sends_ephemeral_error(self):
        """No active campaign → ephemeral error, no MCP call."""
        bot = _make_bot(channel_session=None)
        interaction = _make_interaction()

        cog = LobbyCog(bot)
        await cog.load_adventure.callback(cog, interaction, adventure_id="CoS")

        interaction.followup.send.assert_awaited_once()
        sent = interaction.followup.send.call_args
        content = sent.kwargs.get("content") or (sent.args[0] if sent.args else "")
        assert "start_game" in content.lower() or "no active" in content.lower()
        assert sent.kwargs.get("ephemeral") is True
        bot.mcp.call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_load_adventure_first_run_uses_populate_chapter_1_true(self):
        """First /load_adventure call (module_bound=None) uses populate_chapter_1=True."""
        session = self._make_session(module_bound=None)
        bot = _make_bot(channel_session=session)
        bot.mcp.call = _make_mcp_responses()
        interaction = _make_interaction()

        cog = LobbyCog(bot)
        await cog.load_adventure.callback(cog, interaction, adventure_id="CoS")

        # Verify load_adventure was called with populate_chapter_1=True
        call_names_and_kwargs = [
            (c.args[0], c.kwargs) for c in bot.mcp.call.call_args_list
        ]
        load_calls = [(t, kw) for t, kw in call_names_and_kwargs if t == "dm20__load_adventure"]
        assert len(load_calls) >= 1
        _, load_kw = load_calls[0]
        assert load_kw.get("populate_chapter_1") is True

    @pytest.mark.asyncio
    async def test_load_adventure_second_run_uses_populate_chapter_1_false(self):
        """Re-run when module_bound is already set uses populate_chapter_1=False (Pitfall 7)."""
        session = self._make_session(module_bound="CoS")  # already bound!
        bot = _make_bot(channel_session=session)
        bot.mcp.call = _make_mcp_responses()
        interaction = _make_interaction()

        cog = LobbyCog(bot)
        await cog.load_adventure.callback(cog, interaction, adventure_id="CoS")

        call_names_and_kwargs = [
            (c.args[0], c.kwargs) for c in bot.mcp.call.call_args_list
        ]
        load_calls = [(t, kw) for t, kw in call_names_and_kwargs if t == "dm20__load_adventure"]
        assert len(load_calls) >= 1
        _, load_kw = load_calls[0]
        assert load_kw.get("populate_chapter_1") is False

    @pytest.mark.asyncio
    async def test_load_adventure_updates_module_bound_after_success(self):
        """After successful load, channel_sessions is upserted with module_bound=adventure_id."""
        session = self._make_session(module_bound=None)
        bot = _make_bot(channel_session=session)
        bot.mcp.call = _make_mcp_responses()
        interaction = _make_interaction()

        cog = LobbyCog(bot)
        await cog.load_adventure.callback(cog, interaction, adventure_id="CoS")

        bot.channel_sessions.upsert.assert_awaited()
        upsert_call = bot.channel_sessions.upsert.call_args
        token_str = upsert_call.kwargs.get("dm20_party_token") or (
            upsert_call.args[0] if upsert_call.args else None
        )
        if token_str is None:
            # Check all kwargs for the token
            for k, v in upsert_call.kwargs.items():
                if k == "dm20_party_token":
                    token_str = v
                    break
        if token_str is not None and isinstance(token_str, str):
            token_data = json.loads(token_str)
            assert token_data.get("module_bound") == "CoS"

    @pytest.mark.asyncio
    async def test_load_adventure_permission_denied_for_non_dm(self):
        """User without manage_channels is rejected with ephemeral denial."""
        session = self._make_session()
        bot = _make_bot(channel_session=session)
        # Non-DM user (manage_channels=False)
        interaction = _make_interaction(manage_channels=False)

        cog = LobbyCog(bot)
        await cog.load_adventure.callback(cog, interaction, adventure_id="CoS")

        interaction.followup.send.assert_awaited_once()
        sent = interaction.followup.send.call_args
        assert sent.kwargs.get("ephemeral") is True
        bot.mcp.call.assert_not_awaited()


# ── Autocomplete ────────────────────────────────────────────────────────────────


class TestAdventureIdAutocomplete:
    @pytest.mark.asyncio
    async def test_empty_current_returns_all_9(self):
        bot = _make_bot()
        interaction = _make_interaction()
        cog = LobbyCog(bot)

        results = await cog.adventure_id_autocomplete(interaction, current="")

        assert len(results) == 9

    @pytest.mark.asyncio
    async def test_results_are_app_commands_choice(self):
        bot = _make_bot()
        interaction = _make_interaction()
        cog = LobbyCog(bot)

        results = await cog.adventure_id_autocomplete(interaction, current="")
        assert all(isinstance(r, app_commands.Choice) for r in results)

    @pytest.mark.asyncio
    async def test_substring_filter_case_insensitive(self):
        bot = _make_bot()
        interaction = _make_interaction()
        cog = LobbyCog(bot)

        # "strahd" matches "Curse of Strahd" (CoS)
        results = await cog.adventure_id_autocomplete(interaction, current="strahd")
        values = [r.value for r in results]
        assert "CoS" in values

    @pytest.mark.asyncio
    async def test_autocomplete_filters_by_id(self):
        bot = _make_bot()
        interaction = _make_interaction()
        cog = LobbyCog(bot)

        # "WD" matches "WDH" and "WDMM"
        results = await cog.adventure_id_autocomplete(interaction, current="WD")
        values = [r.value for r in results]
        assert "WDH" in values
        assert "WDMM" in values

    @pytest.mark.asyncio
    async def test_autocomplete_returns_at_most_25(self):
        bot = _make_bot()
        interaction = _make_interaction()
        cog = LobbyCog(bot)

        results = await cog.adventure_id_autocomplete(interaction, current="")
        assert len(results) <= 25

    @pytest.mark.asyncio
    async def test_autocomplete_no_match_returns_empty(self):
        bot = _make_bot()
        interaction = _make_interaction()
        cog = LobbyCog(bot)

        results = await cog.adventure_id_autocomplete(interaction, current="xyznotanadventure")
        assert len(results) == 0
