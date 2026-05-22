"""
Tests for eldritch_dm.bot.cogs.ingest — IngestCog.

Covers:
  - /upload_character_url happy path (dm20 call order: import → update_character)
  - /upload_character_url no-active-campaign
  - /upload_character_url dm20 error path
  - /upload_character_file oversize rejection (NO .read() called)
  - /upload_character_file wrong format (sniff fails)
  - /upload_character_file confidence >= 0.6 → CharacterReviewModal flow
  - /upload_character_file confidence < 0.6 → CharacterEntryModal flow
  - /upload_character_file modal-submit invalid ability string → ephemeral error
  - /upload_character_file modal-submit valid → dm20__create_character called with player_id
  - /upload_character_file permission denied
  - /upload_character_manual happy path (no OCR)
  - lobby embed update: edit() called with recently_joined member
  - INGEST-10: all cog replies use ephemeral=True
  - INGEST-11: ingest() called once, no extra MCP calls in hot path
  - Timing test: cog completes ingest call quickly (mocked fast)
  - embeds.py: lobby_embed_with_joined_member backward-compat
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import discord
import pytest

from eldritch_dm.bot.embeds import lobby_embed_with_joined_member, lobby_embed, PlayerStatus
from eldritch_dm.ingest.schema import AbilityScores, CharacterSheet, IngestResult

# ── Helpers ────────────────────────────────────────────────────────────────────

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal PNG magic
PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 100          # minimal PDF magic
TXT_BYTES = b"This is not an image or PDF"

_FAKE_PLAYER_ID = 12345
_FAKE_CHANNEL_ID = 67890
_FAKE_CAMPAIGN = "Test Campaign"

_GOOD_SHEET = CharacterSheet(
    name="Aragorn",
    character_class="Ranger",
    class_level=5,
    race="Human",
    abilities=AbilityScores(strength=15, dexterity=18, constitution=14,
                             intelligence=12, wisdom=10, charisma=8),
)

_GOOD_INGEST_RESULT = IngestResult(
    raw_text="Aragorn / Ranger / 5 / Human",
    parsed_sheet=_GOOD_SHEET,
    confidence_score=0.9,
    validation_warnings=[],
    ocr_backend="ocrmac",
    pdf_backend=None,
)

_LOW_CONFIDENCE_RESULT = IngestResult(
    raw_text="garbled ocr text",
    parsed_sheet=None,
    confidence_score=0.3,
    validation_warnings=["OCR quality low"],
    ocr_backend="ocrmac",
    pdf_backend=None,
)


def _make_session(
    campaign_name: str = _FAKE_CAMPAIGN,
    channel_id: str = str(_FAKE_CHANNEL_ID),
    state: str = "LOBBY",
    dm20_party_token: str | None = None,
) -> MagicMock:
    session = MagicMock()
    session.campaign_name = campaign_name
    session.channel_id = channel_id
    session.state = state
    session.claudmaster_session_id = "cm-session-123"
    session.dm20_party_token = dm20_party_token or json.dumps({
        "server_url": "http://party.local:8080",
        "members": [],
        "module_bound": None,
        "lobby_message_id": "msg-lobby-999",
    })
    return session


def _make_bot(session: MagicMock | None = None) -> MagicMock:
    """Build a mock EldritchBot with the subsystems IngestCog needs."""
    bot = MagicMock()
    bot.mcp = AsyncMock()

    cs_repo = AsyncMock()
    cs_repo.get = AsyncMock(return_value=session)
    cs_repo.upsert = AsyncMock()
    bot.channel_sessions = cs_repo

    pv_repo = AsyncMock()
    pv_repo.insert = AsyncMock()
    pv_repo.get = AsyncMock(return_value=None)
    bot.pv_repo = pv_repo

    bot.settings = MagicMock()
    bot.settings.omlx_endpoint = "http://localhost:8765/v1"
    bot._logger = MagicMock()
    bot._logger.bind.return_value = bot._logger

    # Provide a fake openai client
    bot.openai_client = AsyncMock()

    return bot


def _make_interaction(
    user_id: int = _FAKE_PLAYER_ID,
    channel_id: int = _FAKE_CHANNEL_ID,
    manage_channels: bool = False,
) -> MagicMock:
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
    interaction.response.send_modal = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock(return_value=MagicMock(id=111))
    interaction.client = MagicMock()
    return interaction


def _make_attachment(
    size: int = 1000,
    content_type: str = "image/png",
    filename: str = "sheet.png",
    data: bytes = PNG_BYTES,
) -> AsyncMock:
    att = AsyncMock(spec=discord.Attachment)
    att.size = size
    att.content_type = content_type
    att.filename = filename
    att.read = AsyncMock(return_value=data)
    return att


def _make_cog(bot: MagicMock | None = None) -> "IngestCog":
    from eldritch_dm.bot.cogs.ingest import IngestCog
    b = bot or _make_bot(_make_session())
    return IngestCog(b)


# ── lobby_embed_with_joined_member ─────────────────────────────────────────────


def test_lobby_embed_with_joined_member_has_recently_joined_field():
    """lobby_embed_with_joined_member adds a 'Recently joined' field."""
    embed = lobby_embed_with_joined_member(
        campaign_name="Test",
        players=[],
        recently_joined=["✅ Aragorn (Ranger, lvl 5) joined"],
    )
    field_names = [f.name for f in embed.fields]
    assert any("recently" in name.lower() or "joined" in name.lower() for name in field_names)


def test_lobby_embed_with_joined_member_backward_compat():
    """Calling lobby_embed_with_joined_member without recently_joined works like lobby_embed."""
    embed1 = lobby_embed(campaign_name="C", players=[])
    embed2 = lobby_embed_with_joined_member(campaign_name="C", players=[])
    # Same title, color, no recently_joined field
    assert embed1.title == embed2.title
    assert embed1.color == embed2.color
    field_names = [f.name for f in embed2.fields]
    assert not any("recently" in n.lower() or "joined" in n.lower() for n in field_names)


def test_lobby_embed_with_joined_member_none_recently_joined():
    """recently_joined=None is treated same as empty/omitted."""
    embed = lobby_embed_with_joined_member(campaign_name="C", players=[], recently_joined=None)
    field_names = [f.name for f in embed.fields]
    assert not any("recently" in n.lower() or "joined" in n.lower() for n in field_names)


# ── /upload_character_url ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_url_defers_first():
    """First await in /upload_character_url must be defer (EDM001 + INGEST-10)."""
    bot = _make_bot(_make_session())
    bot.mcp.call = AsyncMock(side_effect=[
        {"character_id": "char-42", "name": "Aragorn"},  # import
        {"ok": True},                                     # update
    ])
    # Mock the lobby message edit
    lobby_msg = AsyncMock()
    lobby_msg.edit = AsyncMock()
    with patch("eldritch_dm.bot.cogs.ingest.lobby_embed_with_joined_member"):
        cog = _make_cog(bot)
        interaction = _make_interaction()

        defer_called = False
        mcp_called = False

        original_defer = interaction.response.defer

        async def track_defer(*args, **kwargs):
            nonlocal defer_called
            defer_called = True
            await original_defer(*args, **kwargs)

        interaction.response.defer = track_defer

        original_call = bot.mcp.call

        async def track_call(*args, **kwargs):
            nonlocal mcp_called
            assert defer_called, "defer must be called before any MCP call"
            mcp_called = True
            return await original_call(*args, **kwargs)

        bot.mcp.call = track_call

        await cog.upload_character_url.callback(cog, interaction, url="https://ddb.ac/123")
        assert defer_called


@pytest.mark.asyncio
async def test_upload_url_no_active_campaign():
    """Ephemeral error when no active campaign in channel."""
    bot = _make_bot(session=None)
    cog = _make_cog(bot)
    interaction = _make_interaction()

    await cog.upload_character_url.callback(cog, interaction, url="https://ddb.ac/123")

    # Should have sent ephemeral error
    interaction.followup.send.assert_awaited()
    call_args = interaction.followup.send.call_args
    assert call_args.kwargs.get("ephemeral") is True
    assert "campaign" in call_args.kwargs.get("content", "").lower()


@pytest.mark.asyncio
async def test_upload_url_dm20_error():
    """Ephemeral error sent on dm20 import failure."""
    bot = _make_bot(_make_session())
    bot.mcp.call = AsyncMock(side_effect=Exception("DDB 404 not found"))
    cog = _make_cog(bot)
    interaction = _make_interaction()

    await cog.upload_character_url.callback(cog, interaction, url="https://bad-url/x")

    interaction.followup.send.assert_awaited()
    content = interaction.followup.send.call_args.kwargs.get("content", "")
    assert "❌" in content or "error" in content.lower() or "could not" in content.lower()


@pytest.mark.asyncio
async def test_upload_url_calls_import_then_update():
    """Happy path: import_from_dndbeyond → update_character with player_id."""
    calls_made: list[tuple] = []
    import_result = {"character_id": "char-99", "name": "Legolas", "class": "Fighter", "level": 3}
    update_result = {"ok": True}

    async def mock_call(tool_name, **kwargs):
        calls_made.append((tool_name, kwargs))
        if "import" in tool_name:
            return import_result
        return update_result

    bot = _make_bot(_make_session())
    bot.mcp.call = mock_call

    # Mock lobby message lookup
    mock_lobby_msg = AsyncMock()
    mock_lobby_msg.edit = AsyncMock()

    with patch("eldritch_dm.bot.cogs.ingest.lobby_embed_with_joined_member", return_value=MagicMock()):
        cog = _make_cog(bot)
        # Patch the _get_lobby_message helper to return our mock
        with patch.object(cog, "_get_lobby_message", new=AsyncMock(return_value=mock_lobby_msg)):
            interaction = _make_interaction(user_id=_FAKE_PLAYER_ID)
            await cog.upload_character_url.callback(cog, interaction, url="https://ddb.ac/legolas")

    # First call should be import
    assert calls_made[0][0] == "dm20__import_from_dndbeyond"
    # Second call should be update with player_id
    update_calls = [(t, k) for t, k in calls_made if "update" in t]
    assert len(update_calls) >= 1
    _, update_kwargs = update_calls[0]
    assert str(_FAKE_PLAYER_ID) in str(update_kwargs)


# ── /upload_character_file ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_file_oversize_no_read():
    """Files > 10 MB are rejected with ephemeral error; attachment.read() NOT called."""
    cog = _make_cog()
    interaction = _make_interaction()
    attachment = _make_attachment(size=11 * 1024 * 1024)

    await cog.upload_character_file.callback(cog, interaction, attachment=attachment)

    # .read() must NOT have been called
    attachment.read.assert_not_awaited()
    interaction.followup.send.assert_awaited()
    content = interaction.followup.send.call_args.kwargs.get("content", "")
    assert "10" in content or "MB" in content


@pytest.mark.asyncio
async def test_upload_file_wrong_format_rejected():
    """Non-image/non-PDF magic bytes → ephemeral error, no ingest call."""
    cog = _make_cog()
    interaction = _make_interaction()
    attachment = _make_attachment(data=TXT_BYTES, content_type="text/plain")

    with patch("eldritch_dm.bot.cogs.ingest.ingest", new=AsyncMock()) as mock_ingest:
        await cog.upload_character_file.callback(cog, interaction, attachment=attachment)
        mock_ingest.assert_not_awaited()

    interaction.followup.send.assert_awaited()
    content = interaction.followup.send.call_args.kwargs.get("content", "")
    assert "unsupported" in content.lower() or "format" in content.lower() or "PNG" in content


@pytest.mark.asyncio
async def test_upload_file_high_confidence_sends_review_button():
    """High confidence result → followup with a 'Review & Confirm' button."""
    cog = _make_cog()
    interaction = _make_interaction()
    attachment = _make_attachment()

    with patch("eldritch_dm.bot.cogs.ingest.ingest", return_value=AsyncMock(return_value=_GOOD_INGEST_RESULT)()) as mock_ingest, \
         patch.object(mock_ingest, "__call__", new=AsyncMock(return_value=_GOOD_INGEST_RESULT)):
        with patch("eldritch_dm.bot.cogs.ingest.ingest", new=AsyncMock(return_value=_GOOD_INGEST_RESULT)):
            await cog.upload_character_file.callback(cog, interaction, attachment=attachment)

    # Should have sent followup with a view (button)
    interaction.followup.send.assert_awaited()
    send_kwargs = interaction.followup.send.call_args.kwargs
    assert send_kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_upload_file_low_confidence_sends_entry_button():
    """Low confidence result → followup with an 'Enter Character Manually' button."""
    cog = _make_cog()
    interaction = _make_interaction()
    attachment = _make_attachment()

    with patch("eldritch_dm.bot.cogs.ingest.ingest", new=AsyncMock(return_value=_LOW_CONFIDENCE_RESULT)):
        await cog.upload_character_file.callback(cog, interaction, attachment=attachment)

    interaction.followup.send.assert_awaited()
    send_kwargs = interaction.followup.send.call_args.kwargs
    assert send_kwargs.get("ephemeral") is True
    # View should be present (button to open modal)
    view = send_kwargs.get("view")
    assert view is not None


@pytest.mark.asyncio
async def test_upload_file_permission_denied():
    """Non-owner player uploading for another user (manage_channels=False) → denied."""
    cog = _make_cog()
    # User 99999 is uploading for player_name="OtherPlayer" but lacks manage_channels
    interaction = _make_interaction(user_id=99999, manage_channels=False)
    attachment = _make_attachment()

    # The permission check happens at the start; since this is own upload it passes.
    # For DM-only overrides, the gate applies when uploading "on behalf of" another player.
    # We test that the gate is wired correctly by mocking can_act_on_character to False.
    with patch("eldritch_dm.bot.cogs.ingest.can_act_on_character", return_value=False):
        with patch("eldritch_dm.bot.cogs.ingest.ingest", new=AsyncMock()) as mock_ingest:
            await cog.upload_character_file.callback(cog, interaction, attachment=attachment)
            mock_ingest.assert_not_awaited()

    interaction.followup.send.assert_awaited()
    content = interaction.followup.send.call_args.kwargs.get("content", "")
    assert "only" in content.lower() or "permission" in content.lower() or "DM" in content


@pytest.mark.asyncio
async def test_modal_submit_invalid_abilities_sends_error():
    """on_submit with 5-score ability string sends ephemeral error, no dm20 create."""
    cog = _make_cog()
    interaction = _make_interaction()

    raw_dict = {
        "name": "Aragorn",
        "character_class": "Ranger",
        "class_level": "5",
        "race": "Human",
        "abilities_str": "10 12 14 8 16",  # only 5 scores — invalid
    }

    with patch.object(cog.bot.mcp, "call", new=AsyncMock()) as mock_call:
        await cog._on_character_submit(interaction, raw_dict, campaign_name=_FAKE_CAMPAIGN)
        mock_call.assert_not_awaited()

    interaction.followup.send.assert_awaited()
    content = interaction.followup.send.call_args.kwargs.get("content", "")
    assert "❌" in content or "ability" in content.lower() or "error" in content.lower()
    assert call_kwargs_has_ephemeral(interaction.followup.send)


def call_kwargs_has_ephemeral(mock_send) -> bool:
    """Check if any followup.send call had ephemeral=True."""
    for c in mock_send.call_args_list:
        if c.kwargs.get("ephemeral") is True:
            return True
    return False


@pytest.mark.asyncio
async def test_modal_submit_valid_calls_create_character():
    """Valid modal submit calls dm20__create_character with player_id."""
    calls: list[tuple] = []

    async def mock_call(tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        return {"character_id": "char-created", "name": "Aragorn"}

    bot = _make_bot(_make_session())
    bot.mcp.call = mock_call
    cog = _make_cog(bot)

    mock_lobby_msg = AsyncMock()
    mock_lobby_msg.edit = AsyncMock()

    interaction = _make_interaction(user_id=_FAKE_PLAYER_ID)
    raw_dict = {
        "name": "Aragorn",
        "character_class": "Ranger",
        "class_level": "5",
        "race": "Human",
        "abilities_str": "15 18 14 12 10 8",
    }

    with patch.object(cog, "_get_lobby_message", new=AsyncMock(return_value=mock_lobby_msg)):
        with patch("eldritch_dm.bot.cogs.ingest.lobby_embed_with_joined_member", return_value=MagicMock()):
            await cog._on_character_submit(interaction, raw_dict, campaign_name=_FAKE_CAMPAIGN)

    create_calls = [(t, k) for t, k in calls if "create_character" in t]
    assert len(create_calls) >= 1
    _, create_kwargs = create_calls[0]
    # player_id must be in the payload
    assert str(_FAKE_PLAYER_ID) in str(create_kwargs)


@pytest.mark.asyncio
async def test_upload_file_all_responses_ephemeral():
    """All error replies from upload_character_file use ephemeral=True (INGEST-10)."""
    cog = _make_cog()
    interaction = _make_interaction()
    # Test oversize path
    attachment = _make_attachment(size=20 * 1024 * 1024)
    await cog.upload_character_file.callback(cog, interaction, attachment=attachment)
    assert call_kwargs_has_ephemeral(interaction.followup.send), "oversize reply must be ephemeral"


@pytest.mark.asyncio
async def test_upload_file_ingest_called_once():
    """ingest() is called exactly once in the happy path (INGEST-11 budget)."""
    cog = _make_cog()
    interaction = _make_interaction()
    attachment = _make_attachment()

    with patch("eldritch_dm.bot.cogs.ingest.ingest", new=AsyncMock(return_value=_GOOD_INGEST_RESULT)) as mock_ingest:
        await cog.upload_character_file.callback(cog, interaction, attachment=attachment)
        assert mock_ingest.await_count == 1


@pytest.mark.asyncio
async def test_upload_file_timing(monkeypatch):
    """Cog completes ingest dispatch in <8s (mocked fast — tests the path, not actual OCR)."""
    cog = _make_cog()
    interaction = _make_interaction()
    attachment = _make_attachment()

    async def instant_ingest(*args, **kwargs):
        return _GOOD_INGEST_RESULT

    with patch("eldritch_dm.bot.cogs.ingest.ingest", new=instant_ingest):
        start = time.monotonic()
        await cog.upload_character_file.callback(cog, interaction, attachment=attachment)
        elapsed = time.monotonic() - start

    assert elapsed < 8.0, f"Cog dispatch took {elapsed:.2f}s — exceeds 8s budget"


# ── /upload_character_manual ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_manual_no_ingest_calls():
    """upload_character_manual opens an entry modal without OCR/ingest."""
    cog = _make_cog()
    interaction = _make_interaction()

    with patch("eldritch_dm.bot.cogs.ingest.ingest", new=AsyncMock()) as mock_ingest:
        await cog.upload_character_manual.callback(cog, interaction)
        mock_ingest.assert_not_awaited()

    # Should have sent ephemeral with a button (entry modal)
    interaction.followup.send.assert_awaited()
    assert call_kwargs_has_ephemeral(interaction.followup.send)


@pytest.mark.asyncio
async def test_upload_manual_sends_ephemeral_button():
    """upload_character_manual sends a view (button) as ephemeral followup."""
    cog = _make_cog()
    interaction = _make_interaction()

    await cog.upload_character_manual.callback(cog, interaction)

    send_kwargs = interaction.followup.send.call_args.kwargs
    assert send_kwargs.get("ephemeral") is True
    assert send_kwargs.get("view") is not None


# ── lobby embed update after commit ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_character_submit_edits_lobby_embed():
    """After successful character commit, lobby embed is edited with the new member."""
    bot = _make_bot(_make_session())
    calls: list[tuple] = []

    async def mock_call(tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        return {"character_id": "char-new", "name": "Aragorn"}

    bot.mcp.call = mock_call
    cog = _make_cog(bot)

    mock_lobby_msg = AsyncMock()
    mock_lobby_msg.edit = AsyncMock()

    interaction = _make_interaction(user_id=_FAKE_PLAYER_ID)
    raw_dict = {
        "name": "Aragorn",
        "character_class": "Ranger",
        "class_level": "5",
        "race": "Human",
        "abilities_str": "15 18 14 12 10 8",
    }

    with patch.object(cog, "_get_lobby_message", new=AsyncMock(return_value=mock_lobby_msg)):
        with patch("eldritch_dm.bot.cogs.ingest.lobby_embed_with_joined_member",
                   return_value=MagicMock()) as mock_embed_fn:
            await cog._on_character_submit(interaction, raw_dict, campaign_name=_FAKE_CAMPAIGN)
            mock_embed_fn.assert_called_once()

    mock_lobby_msg.edit.assert_awaited_once()
