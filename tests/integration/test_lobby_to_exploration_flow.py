"""
G-1 closure: ReadyButton all-ready transition must start the orchestrator.

Per v1.0 milestone audit (.planning/v1.0-MILESTONE-AUDIT.md), the lobby ->
EXPLORATION transition in ``ReadyButton.callback`` (src/eldritch_dm/bot/
dynamic_items.py:325-376) calls ``channel_sessions_repo.set_state(EXPLORATION)``
and ``mcp_tools.player_action(party_ready)`` but NEVER calls
``bot.orchestrator.start_orchestrator_for_channel(...)``.  As a result, a
fresh cold-start ``/start_game -> all-ready`` lifetime leaves the channel
in EXPLORATION with no orchestrator task running.  EXPLORE-01..07 and
COMBAT-01..12 are silently inert until the bot is restarted (the
``setup_hook`` RESUME loop is what currently starts the orchestrator for
all EXPLORATION/COMBAT rows on boot).

This test exercises the all-ready branch end-to-end and asserts that the
orchestrator has an active task for the channel after the click resolves.

Before the G-1 fix: this test MUST fail (the dict ``_tasks`` is empty).
After the G-1 fix:  this test passes.

Run with::

    pytest tests/integration/test_lobby_to_exploration_flow.py -v
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio

from eldritch_dm.bot.dynamic_items import ReadyButton
from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
from eldritch_dm.persistence.connection import WriterQueue
from eldritch_dm.persistence.models import ChannelState
from eldritch_dm.persistence.persistent_views_repo import PersistentViewRepo

# ── Test constants ────────────────────────────────────────────────────────────

_CAMPAIGN_NAME = "G1 Closure Pilot"
_USER_ID = 4242
_CHANNEL_ID = 7777777
_CHANNEL_ID_STR = str(_CHANNEL_ID)
_CM_SESSION_ID = "cm-session-g1"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def g1_db(tmp_path):
    """Real in-memory SQLite stack with the lobby session already seeded."""
    db_path = str(tmp_path / "g1_closure.sqlite3")
    await bootstrap(db_path)

    wq = WriterQueue(db_path)
    await wq.start()

    channel_repo = ChannelSessionRepo(db_path, wq)
    view_repo = PersistentViewRepo(db_path, wq)

    # Seed a LOBBY session for the channel we'll click ReadyButton on
    await channel_repo.upsert(
        channel_id=_CHANNEL_ID_STR,
        campaign_name=_CAMPAIGN_NAME,
        state=ChannelState.LOBBY,
        claudmaster_session_id=_CM_SESSION_ID,
    )

    try:
        yield db_path, wq, channel_repo, view_repo
    finally:
        await wq.stop()


def _make_bot_with_real_orchestrator(channel_repo, view_repo) -> MagicMock:
    """Construct a MagicMock bot wired to real repos + a real PartyModeOrchestrator.

    The orchestrator is the unit-under-test: we want to assert that
    ``bot.orchestrator._tasks`` contains an entry keyed by the channel id
    after ReadyButton's all-ready branch runs.
    """
    from eldritch_dm.gameplay.exploration_batch import BatchCoordinator
    from eldritch_dm.gameplay.party_mode import PartyModeOrchestrator
    from eldritch_dm.mcp.rate_limit import ChannelRateLimiter

    bot = MagicMock()

    # MCP mock returns canned responses for the calls ReadyButton makes.
    async def _mcp_call(tool_name: str, **kwargs: Any) -> Any:
        if tool_name == "dm20__list_characters":
            return {
                "characters": [
                    {
                        "id": "char-1",
                        "name": "Hero",
                        "player_id": str(_USER_ID),
                    }
                ]
            }
        if tool_name == "dm20__player_action":
            return {"ok": True, "action": kwargs.get("action")}
        return {"ok": True}

    bot.mcp = AsyncMock()
    bot.mcp.call = _mcp_call

    bot.channel_sessions = channel_repo
    bot.pv_repo = view_repo

    # Real PartyModeOrchestrator — the thing whose _tasks dict we will inspect.
    bot.rate_limiter = ChannelRateLimiter(min_interval_ms=0)
    bot.batch_coordinator = BatchCoordinator(window_seconds=30.0)
    bot.orchestrator = PartyModeOrchestrator(
        mcp=bot.mcp,
        rate_limiter=bot.rate_limiter,
        batch_coordinator=bot.batch_coordinator,
        channel_sessions=channel_repo,
        monster_driver=None,
    )

    bot._logger = MagicMock()
    bot._logger.bind.return_value = bot._logger
    return bot


def _make_interaction(bot, user_id: int = _USER_ID, channel_id: int = _CHANNEL_ID) -> MagicMock:
    """Build a discord.Interaction stand-in routed at ``bot``."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.display_name = f"Player{user_id}"

    interaction.channel_id = channel_id
    interaction.channel = MagicMock()
    interaction.message = AsyncMock()
    interaction.message.edit = AsyncMock()

    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock(return_value=MagicMock(id=999))

    # ReadyButton reads dependencies off ``interaction.client``.
    interaction.client = bot
    return interaction


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ready_button_all_ready_starts_orchestrator(g1_db):
    """G-1: After all-ready, bot.orchestrator must have an active task for the channel.

    Before the fix, ReadyButton sets EXPLORATION + fires player_action but
    never calls bot.orchestrator.start_orchestrator_for_channel(...). The
    `_tasks` dict on the real orchestrator stays empty and gameplay is
    silently inert.
    """
    _, _, channel_repo, view_repo = g1_db

    bot = _make_bot_with_real_orchestrator(channel_repo, view_repo)
    interaction = _make_interaction(bot)

    ready_btn = ReadyButton(_CHANNEL_ID)

    try:
        await ready_btn.callback(interaction)

        # Sanity: the state machine performed the all-ready branch.
        session = await channel_repo.get(_CHANNEL_ID_STR)
        assert session is not None
        assert session.state == ChannelState.EXPLORATION, (
            f"all-ready branch should have transitioned to EXPLORATION; "
            f"got {session.state}"
        )

        # Core G-1 assertion: orchestrator task is registered AND not done.
        assert _CHANNEL_ID_STR in bot.orchestrator._tasks, (
            "G-1 regression: ReadyButton's all-ready branch did NOT call "
            "bot.orchestrator.start_orchestrator_for_channel(...). "
            f"_tasks keys: {list(bot.orchestrator._tasks.keys())}"
        )
        task = bot.orchestrator._tasks[_CHANNEL_ID_STR]
        assert not task.done(), (
            "Orchestrator task for the channel exists but is already done — "
            "expected an active loop."
        )
    finally:
        # Tear down the orchestrator task before the event loop closes,
        # otherwise pytest-asyncio warns about pending tasks.
        if _CHANNEL_ID_STR in bot.orchestrator._tasks:
            await bot.orchestrator.stop_orchestrator_for_channel(_CHANNEL_ID_STR)
