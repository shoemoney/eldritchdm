"""
DEBT-02 — Cold-start E2E regression guard for the orchestrator-wiring class.

Why this test exists (META meta-pitfall):
    v1.0 shipped G-1: ``ReadyButton.callback``'s all-ready branch transitioned
    the channel to EXPLORATION and signaled Claudmaster, but NEVER called
    ``bot.orchestrator.start_orchestrator_for_channel(...)``. All 870
    pre-ship tests either constructed the orchestrator directly OR routed
    through ``setup_hook``'s RESUME loop (which DOES start the orchestrator
    for existing EXPLORATION/COMBAT rows on boot). A genuine cold-start —
    fresh DB, ``/start_game`` → ready-up in a single process lifetime — was
    never asserted on, so the missing call was silently inert. Phase 6 plan
    02 installs this regression guard.

What this test exercises:
    - settings → bootstrap → EldritchBot construction → ``setup_hook`` —
      all in-process, no ``bot.run``, no subprocess, no Discord network.
    - Simulate ``/start_game`` by inserting one LOBBY ``channel_sessions``
      row through the bot's real repo (no fixtures pre-creating state).
    - Drive the ready-up click by invoking ``ReadyButton.callback`` with a
      MagicMock-of-``discord.Interaction``.
    - Assert the load-bearing fact: ``bot.orchestrator._tasks[channel_id]``
      exists and is not ``.done()`` after the click.

Historical-regression verification protocol (Task 2 of plan 06-02):
    - Against commit ``7d307a1`` (Phase 5 Plan 03 closure, pre-G-1-fix):
      this test MUST FAIL on the ``channel_id in _tasks`` assertion.
    - Against current ``main`` (post-G-1-fix ``4c15641``): this test MUST
      PASS. Output excerpts captured in
      ``.planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md``.

Mock boundary:
    - ``MCPClient.call`` is patched at the class via ``unittest.mock.patch``
      with a dispatch ``side_effect`` so every dm20 tool name returns a
      sane canned shape. This keeps the orchestrator parked at the
      ``party_pop_action`` "empty" branch (``await self._sleep(...)``).
    - ``bot.tree.sync`` is replaced with an ``AsyncMock`` so setup_hook's
      app-command-sync step does not contact Discord.
    - Discord gateway is NEVER reached; we don't call ``bot.run``.

Zero shared fixtures: only ``tmp_path`` is used (pytest builtin). NO
``conftest`` imports beyond what pytest discovers automatically. Every
piece of state this test inspects is constructed inline so the RESUME
loop has nothing to save us with — the orchestrator MUST start from the
click for the assertion to pass (D-37 / D-41 plan-level mitigations).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from eldritch_dm.bot.bot import EldritchBot
from eldritch_dm.bot.dynamic_items import ReadyButton
from eldritch_dm.config import Settings
from eldritch_dm.persistence.models import ChannelState

# ── Test constants ────────────────────────────────────────────────────────────

_CAMPAIGN = "Cold Start Pilot"
_USER_ID = 4242
_CHANNEL_ID = 7777777
_CHANNEL_ID_STR = str(_CHANNEL_ID)
_SESSION_ID = "cm-session-cold-start"


# ── MCP dispatch ──────────────────────────────────────────────────────────────


async def _mcp_dispatch(self: Any, tool_name: str, **kwargs: Any) -> dict[str, Any]:
    """Canned MCPClient.call replacement covering every dm20 tool the
    cold-start path touches.

    ``self`` is bound because we patch the unbound method on the class —
    ``new_callable=AsyncMock`` would lose the dispatch behaviour, so we
    instead use a plain ``async def`` with ``side_effect``-equivalent
    semantics by patching directly with ``new=<callable>``.
    """
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
    if tool_name == "dm20__party_pop_action":
        # Keeps the orchestrator parked at `await self._sleep(poll_interval_s)`
        # in PartyModeOrchestrator._loop — no further MCP traffic per tick.
        return {"empty": True, "pending": 0}
    if tool_name == "dm20__player_action":
        return {"ok": True, "action": kwargs.get("action")}
    if tool_name == "dm20__get_game_state":
        # State-transition watcher and current_round_for_channel parse this.
        return {"round_number": 0, "actor": None}
    # Lenient default: a regression guard for ONE bug should not break on an
    # unrelated future MCP call site. R-1 in the plan's <verification>
    # acknowledges this trade-off explicitly.
    return {"ok": True}


# ── The test ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cold_start_e2e_orchestrator_alive_after_ready(tmp_path) -> None:
    """Cold-start happy path: setup_hook → /start_game → all-ready click
    leaves an alive orchestrator task for the channel.

    Load-bearing assertion (DEBT-02 / G-1 regression guard):
        ``str(_CHANNEL_ID) in bot.orchestrator._tasks`` AND that task is
        not ``.done()`` after ``ReadyButton.callback`` returns.
    """
    # ── Phase A — Settings ----------------------------------------------------
    # discord_token is non-empty to satisfy any defensive checks even though
    # we never call bot.run. eldritch_db_path → tmp_path keeps the test
    # hermetic (T-06-02-06).
    settings = Settings(
        discord_token="x" * 50,
        discord_application_id=123456789012345678,
        eldritch_db_path=str(tmp_path / "cold_start.sqlite3"),
    )

    bot = EldritchBot(settings)

    # ── Phase B — patch external surfaces BEFORE setup_hook -------------------
    # MCPClient.call: replace the unbound class method so every MCPClient
    # instance constructed in setup_hook (the bot's `self.mcp`) uses our
    # dispatch. patch as ``new=_mcp_dispatch`` (a coroutine function) so
    # ``self`` binds normally on the descriptor protocol.
    mcp_patch = patch(
        "eldritch_dm.mcp.client.MCPClient.call",
        new=_mcp_dispatch,
    )
    tree_sync_mock = AsyncMock(return_value=[])
    bot.tree.sync = tree_sync_mock  # type: ignore[method-assign]

    try:
        with mcp_patch:
            await bot.setup_hook()

            # Sanity: setup_hook wired the subsystems we depend on.
            assert bot.orchestrator is not None, "setup_hook did not wire orchestrator"
            assert bot.channel_sessions_repo is not None, (
                "setup_hook did not wire channel_sessions_repo"
            )
            # RESUME loop saw an empty DB → no tasks. CRITICAL pre-condition
            # for the meta-pitfall guard: any task in _tasks after the click
            # must have come from the click itself, not from the RESUME path.
            assert bot.orchestrator._tasks == {}, (
                f"RESUME loop unexpectedly populated _tasks on a fresh DB: "
                f"{list(bot.orchestrator._tasks.keys())}. "
                "This test would mask G-1 if any pre-existing rows leaked in."
            )

            # ── Phase C — simulate /start_game ---------------------------------
            # Insert exactly one LOBBY row directly through the bot's real
            # repo. The plan body says "create" but the actual ChannelSessionRepo
            # API is upsert(...).
            await bot.channel_sessions_repo.upsert(
                channel_id=_CHANNEL_ID_STR,
                campaign_name=_CAMPAIGN,
                state=ChannelState.LOBBY,
                claudmaster_session_id=_SESSION_ID,
            )

            # ── Phase D — drive the ready-up click -----------------------------
            interaction = MagicMock(spec=discord.Interaction)
            interaction.user = MagicMock(spec=discord.Member)
            interaction.user.id = _USER_ID
            interaction.user.display_name = f"Player{_USER_ID}"
            interaction.channel_id = _CHANNEL_ID
            interaction.channel = MagicMock()
            interaction.message = AsyncMock()
            interaction.message.edit = AsyncMock()
            interaction.response = AsyncMock()
            interaction.response.defer = AsyncMock()
            interaction.followup = AsyncMock()
            interaction.followup.send = AsyncMock(return_value=MagicMock(id=999))
            # ReadyButton.callback resolves dependencies off interaction.client.
            interaction.client = bot

            ready_button = ReadyButton(_CHANNEL_ID)
            await ready_button.callback(interaction)

            # ── Phase E — load-bearing assertions (THE point of this test) ----
            assert _CHANNEL_ID_STR in bot.orchestrator._tasks, (
                "G-1 regression (DEBT-02): orchestrator task NOT started after "
                "all-ready click. ReadyButton.callback's all-ready branch is "
                "missing the start_orchestrator_for_channel(...) call. "
                "See .planning/milestones/v1.0-MILESTONE-AUDIT.md G-1 and "
                ".planning/research/PITFALLS.md META meta-pitfall. "
                f"_tasks keys: {list(bot.orchestrator._tasks.keys())}"
            )
            task = bot.orchestrator._tasks[_CHANNEL_ID_STR]
            assert not task.done(), (
                f"Orchestrator task for channel {_CHANNEL_ID_STR} is already "
                f"done (exception="
                f"{task.exception() if task.done() else 'n/a'}). "
                "Expected an alive task driving the pop→thinking→resolve loop."
            )
            # Belt-and-suspenders: the state machine actually flipped.
            session = await bot.channel_sessions_repo.get(_CHANNEL_ID_STR)
            assert session is not None
            assert session.state == ChannelState.EXPLORATION, (
                f"all-ready branch should have transitioned to EXPLORATION; "
                f"got {session.state}"
            )
    finally:
        # ── Phase F — teardown (CRITICAL — without this pytest-asyncio warns
        # about pending tasks and the next test run leaks file handles).
        if bot.orchestrator is not None:
            try:
                await bot.orchestrator.stop_all()
            except Exception:  # noqa: BLE001
                pass
        if bot.riposte_sweeper is not None:
            try:
                await bot.riposte_sweeper.stop()
            except Exception:  # noqa: BLE001
                pass
        if bot.health is not None:
            try:
                await bot.health.stop()
            except Exception:  # noqa: BLE001
                pass
        if bot.writer_queue is not None:
            try:
                await bot.writer_queue.stop()
            except Exception:  # noqa: BLE001
                pass
        if bot.mcp is not None:
            try:
                await bot.mcp.aclose()
            except Exception:  # noqa: BLE001
                pass
