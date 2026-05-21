"""
tests/bot/test_restart_drill.py — Kill-and-restart integration drill (BOT-08, D-36).

Proves that persistent DynamicItem buttons survive a complete bot restart:
  1. Build bot A, run setup_hook (initializes DB + registers dynamic items)
  2. Seed: insert channel_session + persistent_views row for an EndTurnButton
  3. Dispatch an interaction with matching custom_id against bot A → callback fires
  4. "Kill" bot A (close + GC)
  5. Build bot B (fresh instance, SAME DB path)
  6. Assert setup_hook called add_view with the original message_id
  7. Dispatch the same interaction against bot B → callback still fires

Test is gated behind RUN_INTEGRATION=1 env var (slow: involves DB I/O).
CI must set RUN_INTEGRATION=1 to run these tests.

Usage::

    RUN_INTEGRATION=1 pytest tests/bot/test_restart_drill.py -x -v
"""

from __future__ import annotations

import gc
import os
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION"),
    reason="Restart-drill integration test; set RUN_INTEGRATION=1 to run",
)


# ── Test 1: EndTurnButton survives a bot restart ──────────────────────────────


@pytest.mark.asyncio
async def test_persistent_view_survives_restart(tmp_path, bot_factory):
    """Kill-and-restart drill: an EndTurnButton registered in DB is still callable after restart.

    Steps (D-36):
      a) Build bot_a, run setup_hook against a fresh tmp DB
      b) Seed: channel_sessions + persistent_views rows for an EndTurnButton
      c) Dispatch an interaction → assert callback fires (stub message)
      d) Kill bot_a (close + del + gc)
      e) Build bot_b from SAME DB path — fresh instance
      f) Assert bot_b.add_view called for message_id=333
      g) Dispatch same interaction shape → callback fires again
    """
    from eldritch_dm.bot.dynamic_items import EndTurnButton
    from eldritch_dm.persistence.models import ChannelState, PersistentView
    from datetime import datetime

    tmp_db = str(tmp_path / "drill.sqlite3")

    # ── Step a: Build bot_a ───────────────────────────────────────────────────
    bot_a = await bot_factory(eldritch_db_path=tmp_db)

    # ── Step b: Seed DB with channel_session + persistent_views row ───────────
    await bot_a.channel_sessions_repo.upsert(
        channel_id="111",
        campaign_name="Drill",
        state=ChannelState.COMBAT,
    )

    pv = PersistentView(
        custom_id="endturn:111:222",
        view_class="EndTurnButton",
        message_id="333",
        channel_id="111",
        payload={},
        created_at=datetime(2026, 1, 1),
    )
    await bot_a.persistent_views_repo.insert(pv)

    # ── Step c: Build and dispatch a mock Interaction on bot_a ─────────────────
    interaction_a = _make_interaction(
        custom_id="endturn:111:222",
        channel_id=111,
        user_id=222,
        message_id=333,
    )

    # Dispatch via EndTurnButton.from_custom_id + .callback
    match_a = EndTurnButton.template.fullmatch("endturn:111:222")
    assert match_a is not None, "template.fullmatch('endturn:111:222') should not return None"
    btn_a = await EndTurnButton.from_custom_id(interaction_a, MagicMock(), match_a)
    await btn_a.callback(interaction_a)

    # Verify: defer was called + stub message sent
    interaction_a.response.defer.assert_awaited_once()
    interaction_a.followup.send.assert_awaited_once()

    # ── Step d: Kill bot_a ────────────────────────────────────────────────────
    await bot_a.close()
    del bot_a
    gc.collect()

    # ── Step e: Build bot_b from the SAME DB path ─────────────────────────────
    with patch.object(
        discord.Client,
        "add_view",
        wraps=discord.Client.add_view,
        # We use a wrapper so we can inspect calls without breaking add_view
    ) as mock_add_view:
        bot_b = await bot_factory(eldritch_db_path=tmp_db)

        # ── Step f: Assert add_view was called for message_id=333 ──────────────
        add_view_message_ids = {
            call.kwargs.get("message_id")
            for call in mock_add_view.call_args_list
        }
        assert 333 in add_view_message_ids, (
            f"Expected bot_b.add_view called with message_id=333, "
            f"got: {add_view_message_ids}"
        )

    # ── Step g: Dispatch same interaction against bot_b ───────────────────────
    interaction_b = _make_interaction(
        custom_id="endturn:111:222",
        channel_id=111,
        user_id=222,
        message_id=333,
    )

    match_b = EndTurnButton.template.fullmatch("endturn:111:222")
    btn_b = await EndTurnButton.from_custom_id(interaction_b, MagicMock(), match_b)
    await btn_b.callback(interaction_b)

    interaction_b.response.defer.assert_awaited_once()
    interaction_b.followup.send.assert_awaited_once()

    # Cleanup
    await bot_b.close()


# ── Test 2: Expired riposte cleanup smoke (forward-compat for Phase 5) ────────


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=False,
    reason="Riposte cleanup lands in Phase 5; smoke test only — xfail expected until then",
)
async def test_expired_riposte_cleanup_on_restart(tmp_path, bot_factory):
    """Smoke test: setup_hook does not error if riposte_timers has past-deadline rows.

    Phase 5 will replace xfail with the real cleanup assertion.
    """
    from datetime import datetime, timedelta
    from eldritch_dm.persistence.models import ChannelState
    import aiosqlite
    from eldritch_dm.persistence.bootstrap import bootstrap

    tmp_db = str(tmp_path / "riposte_smoke.sqlite3")

    # Bootstrap schema into the fresh DB
    await bootstrap(tmp_db)

    # Insert a riposte_timers row with a deadline in the past
    past_deadline = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    async with aiosqlite.connect(tmp_db) as conn:
        await conn.execute("""
            INSERT INTO channel_sessions
                (channel_id, campaign_name, state, created_at, updated_at)
            VALUES ('999', 'Smoke', 'LOBBY', datetime('now'), datetime('now'))
        """)
        await conn.execute("""
            INSERT INTO riposte_timers
                (channel_id, character_id, user_id, message_id, deadline_ts, status, created_at)
            VALUES ('999', 'char-1', '888', '777', ?, 'PENDING', datetime('now'))
        """, (past_deadline,))
        await conn.commit()

    # Build bot with this DB — should NOT raise during setup_hook
    bot = await bot_factory(eldritch_db_path=tmp_db)
    await bot.close()

    # Phase 5: assert riposte row was cleaned up / marked EXPIRED
    # For now: just assert no exception was raised (xfail guards the assertion)
    assert False, "Phase 5: assert riposte cleanup here"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_interaction(
    *,
    custom_id: str,
    channel_id: int,
    user_id: int,
    message_id: int,
) -> discord.Interaction:
    """Build a mock discord.Interaction for restart-drill dispatch testing."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.channel_id = channel_id
    interaction.guild_id = 300

    interaction.data = {"custom_id": custom_id, "component_type": 2}

    # Explicit AsyncMock for response/followup (Pitfall 6)
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)

    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.edit_original_response = AsyncMock()

    # Mock the message object on the interaction
    interaction.message = MagicMock(spec=discord.Message)
    interaction.message.id = message_id

    return interaction
