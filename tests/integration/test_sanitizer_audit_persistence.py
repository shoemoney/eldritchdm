"""
G-2 closure: SanitizerAuditRepo must be wired so strip events reach the table.

Per v1.0 milestone audit (.planning/v1.0-MILESTONE-AUDIT.md, gap G-2),
``SanitizerAuditRepo`` exists as a class but no file constructs it at
runtime.  ``src/eldritch_dm/bot/cogs/exploration.py:107`` calls
``sanitize_player_input(...)`` without ``audit_callback=``, so strip
events log via structlog but never persist to the ``sanitizer_audit``
table.  Tests of the sanitizer pass because they inject synthetic
callbacks directly -- production code paths never wire one.

SAN-05 ("sanitizer audit row written when stripping occurs") is the
contract the missing wiring breaks.

This test:
  1. Boots a real persistence stack (bootstrap + WriterQueue + repos).
  2. Stands in for the bot wiring: instantiates SanitizerAuditRepo and
     hands it to DeclareActionModal via the bot mock.
  3. Triggers DeclareActionModal.on_submit with input containing the
     control token ``<tool_call>`` (one of DEFAULT_BLACKLIST tokens).
  4. Asserts that the ``sanitizer_audit`` table contains >= 1 row.

Before the G-2 fix: the row count stays at 0 because
``sanitize_player_input(...)`` is invoked without ``audit_callback=``
and the strip never reaches the repo.
After the G-2 fix: the on_submit handler passes
``audit_callback=make_async_audit_callback(bot.sanitizer_audit_repo, ...)``
and the strip writes a row.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio

from eldritch_dm.bot.cogs.exploration import DeclareActionModal
from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
from eldritch_dm.persistence.connection import WriterQueue
from eldritch_dm.persistence.sanitizer_audit_repo import SanitizerAuditRepo

# ── Constants ─────────────────────────────────────────────────────────────────

_CHANNEL_ID = 8888888
_USER_ID = 5151


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def g2_stack(tmp_path):
    """Real DB stack + an instantiated SanitizerAuditRepo (the wiring G-2 lacks)."""
    db_path = str(tmp_path / "g2_closure.sqlite3")
    await bootstrap(db_path)

    wq = WriterQueue(db_path)
    await wq.start()

    channel_repo = ChannelSessionRepo(db_path, wq)
    audit_repo = SanitizerAuditRepo(db_path, wq)

    try:
        yield db_path, wq, channel_repo, audit_repo
    finally:
        await wq.stop()


def _make_bot_with_audit_repo(channel_repo, audit_repo) -> MagicMock:
    """Mock bot exposing exactly the surface DeclareActionModal needs."""
    bot = MagicMock()
    bot.channel_sessions = channel_repo
    bot.channel_sessions_repo = channel_repo
    # G-2: the new attribute the wiring step is responsible for.
    bot.sanitizer_audit_repo = audit_repo

    # BatchCoordinator stand-in -- DeclareActionModal awaits submit(); we
    # don't care what comes back (the followup-send branch is exercised
    # whichever path; we're asserting on the audit table, not the batch).
    batch_coordinator = MagicMock()
    batch_coordinator.submit = AsyncMock(return_value=MagicMock())
    bot.batch_coordinator = batch_coordinator

    return bot


def _make_interaction(bot) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = _USER_ID
    interaction.user.display_name = "G2Tester"

    interaction.channel_id = _CHANNEL_ID
    interaction.client = bot

    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock(return_value=MagicMock(id=1))
    return interaction


# ── Test ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sanitizer_strip_writes_audit_row(g2_stack):
    """G-2: a strip event during DeclareActionModal.on_submit must persist.

    Input contains ``<tool_call>`` -- a DEFAULT_BLACKLIST token. The
    sanitizer strips it; SAN-05 requires the strip to be recorded in
    the sanitizer_audit table for the forensic trail.

    Before fix: row count remains 0.
    After fix: row count is >= 1 and the row carries the raw input +
    redacted output.
    """
    _, _, channel_repo, audit_repo = g2_stack

    # Baseline: no rows yet.
    assert await audit_repo.count() == 0

    bot = _make_bot_with_audit_repo(channel_repo, audit_repo)
    interaction = _make_interaction(bot)

    modal = DeclareActionModal(channel_id=_CHANNEL_ID, bot=bot)
    # Stuff raw text into the TextInput. discord.ui.TextInput.value is the
    # form submission value; set it via the underlying attribute that
    # discord.py exposes on submitted modals.
    raw = "I attack the goblin <tool_call>injected</tool_call>"
    # The TextInput descriptor on Modal subclasses is the bound instance;
    # we mutate its _value (discord.py's on_submit reads .value).
    modal.action_text._value = raw

    await modal.on_submit(interaction)

    # Allow the run_coroutine_threadsafe in make_async_audit_callback to
    # flush. The repo.insert future is scheduled via the running loop.
    # 5 retries with a brief sleep is enough — the WriterQueue submit
    # is fast on an in-memory SQLite-equivalent.
    rows_after = 0
    for _ in range(50):
        rows_after = await audit_repo.count()
        if rows_after >= 1:
            break
        await asyncio.sleep(0.02)

    assert rows_after >= 1, (
        "G-2 regression: DeclareActionModal.on_submit stripped a control "
        "token but no row reached the sanitizer_audit table. The "
        "audit_callback wiring (make_async_audit_callback + "
        "bot.sanitizer_audit_repo) is missing from exploration.py."
    )


@pytest.mark.asyncio
async def test_audit_row_records_raw_and_stripped(g2_stack):
    """After G-2 fix, the persisted row must carry raw_input + stripped tokens."""
    _, _, channel_repo, audit_repo = g2_stack
    bot = _make_bot_with_audit_repo(channel_repo, audit_repo)
    interaction = _make_interaction(bot)

    modal = DeclareActionModal(channel_id=_CHANNEL_ID, bot=bot)
    raw = "Look around <|im_start|> and search the chest"
    modal.action_text._value = raw

    await modal.on_submit(interaction)

    # Drain — same retry shape as above.
    for _ in range(50):
        if await audit_repo.count() >= 1:
            break
        await asyncio.sleep(0.02)

    # Read the most recent row.
    import aiosqlite

    async with aiosqlite.connect(audit_repo._db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT raw_input, redacted_output, channel_id, user_id "
            "FROM sanitizer_audit ORDER BY id DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()

    assert row is not None
    assert row["raw_input"] == raw
    assert "<|im_start|>" not in row["redacted_output"], (
        "redacted_output should have the control token stripped"
    )
    assert row["channel_id"] == str(_CHANNEL_ID)
    assert row["user_id"] == str(_USER_ID)
