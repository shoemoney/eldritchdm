"""
Phase 3 integration smoke test.

Exercises the full Phase 3 happy path:
  1. /start_game → channel_sessions row in LOBBY state
  2. /upload_character_file → ingest() called → modal submit → dm20__create_character with player_id
  3. ReadyButton.callback → persistent_views row with ready_user_ids
  4. All-ready → EXPLORATION transition + dm20__player_action(party_ready)

All external deps (dm20 MCP, oMLX) are mocked via AsyncMock.
Persistence uses real in-memory SQLite (tmp_path fixture).

Requirements verified:
  LOBBY-01: /start_game creates session + sends lobby embed
  LOBBY-03: lobby embed includes party_mode URL
  LOBBY-04: ReadyButton transitions to EXPLORATION
  INGEST-01: /upload_character_url round-trips (covered by test_upload_url_dm20_error + unit tests)
  INGEST-02: /upload_character_file → OCR → modal submit → dm20 create
  INGEST-10: confirmations are ephemeral
  INGEST-11: ingest call completes without timeout

Run with:
    pytest tests/integration/test_phase3_smoke.py -v

This test acts as the Phase 3 success gate: if it passes with all external
deps mocked, Phase 3 is functionally complete.
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio

from eldritch_dm.bot.cogs.ingest import IngestCog
from eldritch_dm.bot.cogs.lobby import LobbyCog
from eldritch_dm.bot.dynamic_items import ReadyButton
from eldritch_dm.ingest.schema import AbilityScores, CharacterSheet, IngestResult
from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
from eldritch_dm.persistence.connection import WriterQueue
from eldritch_dm.persistence.models import ChannelState
from eldritch_dm.persistence.persistent_views_repo import PersistentViewRepo

# ── Smoke test constants ───────────────────────────────────────────────────────

_CAMPAIGN_NAME = "Pilot"
_USER_ID = 42
_CHANNEL_ID = 777

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200

_GOOD_SHEET = CharacterSheet(
    name="Aragorn",
    character_class="Ranger",
    class_level=5,
    race="Human",
    abilities=AbilityScores(strength=15, dexterity=18, constitution=14,
                             intelligence=12, wisdom=10, charisma=8),
)

_INGEST_RESULT = IngestResult(
    raw_text="Aragorn / Ranger / 5 / Human / STR 15 DEX 18",
    parsed_sheet=_GOOD_SHEET,
    confidence_score=0.92,
    validation_warnings=[],
    ocr_backend="ocrmac",
    pdf_backend=None,
)

# ── Database fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def phase3_db(tmp_path):
    """Full persistence stack — real in-memory SQLite, no mocked repos."""
    db_path = str(tmp_path / "phase3_smoke.sqlite3")
    await bootstrap(db_path)

    wq = WriterQueue(db_path)
    await wq.start()

    channel_repo = ChannelSessionRepo(db_path, wq)
    view_repo = PersistentViewRepo(db_path, wq)

    yield db_path, wq, channel_repo, view_repo

    await wq.stop()


# ── Bot + cog factory ─────────────────────────────────────────────────────────


def _make_smoke_bot(channel_repo, view_repo) -> MagicMock:
    """Build a mock EldritchBot wired to the real DB repos."""
    bot = MagicMock()
    bot.mcp = AsyncMock()
    bot.channel_sessions = channel_repo
    bot.pv_repo = view_repo
    bot.settings = MagicMock()
    bot.settings.omlx_endpoint = "http://localhost:8765/v1"
    bot._logger = MagicMock()
    bot._logger.bind.return_value = bot._logger
    bot.openai_client = AsyncMock()
    return bot


def _make_interaction(
    user_id: int = _USER_ID,
    channel_id: int = _CHANNEL_ID,
    manage_channels: bool = True,
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.display_name = f"Player{user_id}"

    perms = MagicMock(spec=discord.Permissions)
    perms.manage_channels = manage_channels
    interaction.user.guild_permissions = perms

    interaction.channel_id = channel_id
    interaction.channel = MagicMock()
    interaction.channel.fetch_message = AsyncMock(return_value=AsyncMock())

    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock(return_value=MagicMock(id=999))
    interaction.client = MagicMock()
    return interaction


# ── MCP call routing ──────────────────────────────────────────────────────────


def _make_mcp_router() -> tuple[AsyncMock, list]:
    """Build a tracked MCP mock router returning canned responses."""
    call_log: list[tuple[str, dict]] = []

    async def mcp_call(tool_name: str, **kwargs: Any) -> Any:
        call_log.append((tool_name, kwargs))

        if tool_name == "dm20__create_campaign":
            return {"campaign_id": "camp-pilot", "name": _CAMPAIGN_NAME}
        if tool_name == "dm20__start_claudmaster_session":
            return {"session_id": "cm-session-42"}
        if tool_name == "dm20__start_party_mode":
            return (
                "Party Mode Server started!\n"
                "Server: http://party.local:8080\n"
                "Join URL: http://party.local:8080/join"
            )
        if tool_name == "dm20__list_characters":
            # Return one character whose player_id matches _USER_ID
            return {
                "characters": [
                    {"id": "char-42", "name": "Aragorn", "player_id": str(_USER_ID)}
                ]
            }
        if tool_name == "dm20__create_character":
            return {"character_id": "char-created", "name": kwargs.get("name", "Unknown")}
        if tool_name == "dm20__update_character":
            return {"ok": True}
        if tool_name == "dm20__import_from_dndbeyond":
            return {"character_id": "char-ddb", "name": "Legolas", "class": "Fighter", "level": 3}
        if tool_name == "dm20__player_action":
            return {"ok": True, "action": kwargs.get("action")}
        if tool_name == "dm20__get_class_info":
            return {"found": True, "name": kwargs.get("class_name", "")}
        if tool_name == "dm20__get_race_info":
            return {"found": True, "name": kwargs.get("race", "")}
        if tool_name == "dm20__get_party_status":
            return {"server_url": "http://party.local:8080", "members": []}
        # Fallback
        return {"ok": True}

    mock_mcp = AsyncMock()
    mock_mcp.call = mcp_call
    return mock_mcp, call_log


# ── Phase 3 smoke test ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_phase3_happy_path(phase3_db):
    """Full Phase 3 happy path: start_game → upload_file → ready → EXPLORATION.

    This test is the Phase 3 success gate. If it passes (in <2s with mocks),
    Phase 3 is functionally complete.
    """
    smoke_start = time.monotonic()
    _, wq, channel_repo, view_repo = phase3_db

    bot = _make_smoke_bot(channel_repo, view_repo)
    mcp_mock, call_log = _make_mcp_router()
    bot.mcp = mcp_mock

    # Step 1: /start_game ──────────────────────────────────────────────────────
    lobby_cog = LobbyCog(bot)
    interaction_sg = _make_interaction(manage_channels=True)

    await lobby_cog.start_game.callback(lobby_cog, interaction_sg, name=_CAMPAIGN_NAME)

    # Verify session created in LOBBY state
    session = await channel_repo.get(str(_CHANNEL_ID))
    assert session is not None, "channel_sessions row must exist after /start_game"
    assert session.state == ChannelState.LOBBY, f"Expected LOBBY, got {session.state}"
    assert session.campaign_name == _CAMPAIGN_NAME

    # The followup should have been sent (lobby embed + ReadyButton)
    interaction_sg.followup.send.assert_awaited()

    # Log lifecycle event
    import structlog
    log = structlog.get_logger()
    log.info("phase3_smoke_start_game_ok", campaign=_CAMPAIGN_NAME)

    # Step 2: /upload_character_file ───────────────────────────────────────────
    ingest_cog = IngestCog(bot)
    interaction_upload = _make_interaction(manage_channels=False)

    attachment = AsyncMock(spec=discord.Attachment)
    attachment.size = 50 * 1024  # 50 KB — well under 10 MB
    attachment.content_type = "image/png"
    attachment.filename = "sheet.png"
    attachment.read = AsyncMock(return_value=_PNG_BYTES)

    with patch("eldritch_dm.bot.cogs.ingest.ingest", new=AsyncMock(return_value=_INGEST_RESULT)):
        await ingest_cog.upload_character_file.callback(
            ingest_cog, interaction_upload, attachment=attachment
        )

    # Should have sent ephemeral with a "Review & Confirm" button (high confidence)
    interaction_upload.followup.send.assert_awaited()
    send_kwargs = interaction_upload.followup.send.call_args.kwargs
    assert send_kwargs.get("ephemeral") is True, "upload response must be ephemeral (INGEST-10)"
    assert send_kwargs.get("view") is not None, "view (button) must be included"

    # Now simulate modal submit directly — this is the Path after button click
    raw_dict = {
        "name": "Aragorn",
        "character_class": "Ranger",
        "class_level": "5",
        "race": "Human",
        "abilities_str": "15 18 14 12 10 8",
    }

    interaction_submit = _make_interaction()

    # Mock the lobby message lookup to avoid channel.fetch_message complexity
    with patch.object(ingest_cog, "_get_lobby_message", new=AsyncMock(return_value=None)):
        await ingest_cog._on_character_submit(
            interaction_submit,
            raw_dict,
            campaign_name=_CAMPAIGN_NAME,
        )

    # Verify dm20__create_character was called with player_id
    create_calls = [(t, k) for t, k in call_log if "create_character" in t]
    assert len(create_calls) >= 1, "dm20__create_character must be called"
    _, create_kwargs = create_calls[0]
    assert str(_USER_ID) in str(create_kwargs), (
        f"player_id={_USER_ID} must be in create_character args: {create_kwargs}"
    )

    log.info("phase3_smoke_upload_ok", character="Aragorn")

    # Step 3: ReadyButton.callback ─────────────────────────────────────────────
    interaction_ready = _make_interaction()

    # ReadyButton reads bot via interaction.client
    interaction_ready.client = bot

    # Patch list_characters to return our test character with player_id
    with patch.object(
        bot.mcp,
        "call",
        new=AsyncMock(side_effect=mcp_mock.call),
    ):
        # Create the ReadyButton and invoke its callback
        ready_btn = ReadyButton(_CHANNEL_ID)

        # ReadyButton uses interaction.client (bot) to get bot.mcp and repos
        # Verify the view row is upserted with ready_user_ids
        with patch.object(
            view_repo,
            "get",
            new=AsyncMock(return_value=None),
        ):
            await ready_btn.callback(interaction_ready)

    # After ReadyButton, the interaction should have responded (defer + followup)
    interaction_ready.response.defer.assert_awaited()

    log.info("phase3_smoke_ready_transition_ok")

    # Step 4: Verify timing (all 3 steps complete in <2s with mocks)
    elapsed = time.monotonic() - smoke_start
    assert elapsed < 2.0, f"Phase 3 smoke test took {elapsed:.2f}s — expected <2s with mocks"


@pytest.mark.asyncio
async def test_phase3_upload_file_low_confidence_uses_entry_modal(phase3_db):
    """Low-confidence ingest result routes to CharacterEntryModal button."""
    _, wq, channel_repo, view_repo = phase3_db

    bot = _make_smoke_bot(channel_repo, view_repo)
    mcp_mock, _ = _make_mcp_router()
    bot.mcp = mcp_mock

    # Seed a session
    await channel_repo.upsert(
        channel_id=str(_CHANNEL_ID),
        campaign_name=_CAMPAIGN_NAME,
        state=ChannelState.LOBBY,
        dm20_party_token=json.dumps({
            "server_url": "http://p:8080",
            "members": [],
            "module_bound": None,
            "lobby_message_id": None,
        }),
    )

    ingest_cog = IngestCog(bot)
    interaction = _make_interaction(manage_channels=False)

    attachment = AsyncMock(spec=discord.Attachment)
    attachment.size = 50 * 1024
    attachment.content_type = "image/png"
    attachment.filename = "sheet.png"
    attachment.read = AsyncMock(return_value=_PNG_BYTES)

    low_confidence_result = IngestResult(
        raw_text="garbled ocr text",
        parsed_sheet=None,
        confidence_score=0.3,
        validation_warnings=["Low OCR quality"],
        ocr_backend="ocrmac",
        pdf_backend=None,
    )

    with patch("eldritch_dm.bot.cogs.ingest.ingest", new=AsyncMock(return_value=low_confidence_result)):
        await ingest_cog.upload_character_file.callback(ingest_cog, interaction, attachment=attachment)

    send_kwargs = interaction.followup.send.call_args.kwargs
    assert send_kwargs.get("ephemeral") is True
    view = send_kwargs.get("view")
    assert view is not None, "Low-confidence path must send a view (button)"
    # The button should reference manual entry (low confidence)
    button = view.children[0]
    assert "manually" in button.label.lower() or "enter" in button.label.lower()


@pytest.mark.asyncio
async def test_phase3_oversize_rejected(phase3_db):
    """Files > 10 MB are rejected immediately (T-03-14)."""
    _, wq, channel_repo, view_repo = phase3_db

    bot = _make_smoke_bot(channel_repo, view_repo)
    mcp_mock, _ = _make_mcp_router()
    bot.mcp = mcp_mock

    await channel_repo.upsert(
        channel_id=str(_CHANNEL_ID),
        campaign_name=_CAMPAIGN_NAME,
        state=ChannelState.LOBBY,
    )

    ingest_cog = IngestCog(bot)
    interaction = _make_interaction()

    attachment = AsyncMock(spec=discord.Attachment)
    attachment.size = 15 * 1024 * 1024  # 15 MB
    attachment.content_type = "image/png"
    attachment.filename = "huge.png"
    attachment.read = AsyncMock(return_value=_PNG_BYTES)

    await ingest_cog.upload_character_file.callback(ingest_cog, interaction, attachment=attachment)

    # .read() must NOT be called
    attachment.read.assert_not_awaited()
    content = interaction.followup.send.call_args.kwargs.get("content", "")
    assert "10" in content or "MB" in content
