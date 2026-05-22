"""
End-to-end smoke test for the Riposte feature (Phase 5 Plan 01 Task 3).

Three happy-path scenarios with all dependencies mocked except for the real
SQLite-backed repos so we exercise the actual ALTER + persistence + eligibility
check + surface flow. The Plan 02 restart-survival drill (OPS-01) lives
separately; this file only covers single-process behavior.

Test 6: monster MISS against eligible Battle Master → 1 pending row, channel
        send mentions BM, next_turn called.
Test 7: monster MISS against ineligible wizard PC → 0 riposte rows; next_turn
        still called.
Test 8: monster MISS against BM with already-consumed-this-round → 0 new rows
        (budget exhausted); next_turn still called.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio

from eldritch_dm.gameplay.monster_driver import MonsterDriver
from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
from eldritch_dm.persistence.connection import WriterQueue
from eldritch_dm.persistence.models import RiposteStatus, RiposteTimer
from eldritch_dm.persistence.pc_classes_repo import PCClassesRepo
from eldritch_dm.persistence.riposte_timers_repo import RiposteTimerRepo


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def smoke_env(tmp_path):
    """Bootstrap a real DB, set up channel session + battle master + wizard PCs."""
    db_path = str(tmp_path / "smoke.sqlite3")
    await bootstrap(db_path)
    wq = WriterQueue(db_path)
    await wq.start()
    try:
        channel_repo = ChannelSessionRepo(db_path, wq)
        await channel_repo.upsert(
            channel_id="ch-1", campaign_name="IntCamp"
        )
        # Pre-seed pc_classes with one Battle Master Fighter and one wizard
        pc_repo = PCClassesRepo(db_path)
        await pc_repo.upsert(
            channel_id="ch-1",
            character_id="hero-bm",
            class_name="Fighter",
            subclass="Battle Master",
        )
        await pc_repo.upsert(
            channel_id="ch-1",
            character_id="hero-wiz",
            class_name="Wizard",
            subclass="Evocation",
        )
        riposte_repo = RiposteTimerRepo(db_path, wq)

        yield {
            "db_path": db_path,
            "channel_repo": channel_repo,
            "pc_repo": pc_repo,
            "riposte_repo": riposte_repo,
        }
    finally:
        await wq.stop()


def _make_button_factory():
    def _factory(timer_id: int, user_id: int) -> discord.ui.Button:
        return discord.ui.Button(label="r", custom_id=f"riposte:{timer_id}:{user_id}")
    return _factory


def _make_state_provider(pcs: list[dict]):
    async def _provider(channel_id: str, campaign_name: str) -> dict:
        return {"round_number": 1, "pcs": pcs}
    return _provider


def _make_channel():
    channel = MagicMock()
    msg = MagicMock()
    msg.id = 12345
    channel.send = AsyncMock(return_value=msg)
    return channel


# ── Test 6: BM miss → 1 pending row + mention + next_turn ─────────────────────


class TestMonsterMissesBattleMaster:
    @pytest.mark.asyncio
    async def test_riposte_row_created_with_correct_attributes(self, smoke_env):
        env = smoke_env
        channel = _make_channel()

        pcs = [
            {
                "character_id": "hero-bm",
                "user_id": 1001,
                "player_id": "1001",
                "name": "Thorin",
                "primary_weapon": "longsword",
            },
            {
                "character_id": "hero-wiz",
                "user_id": 1002,
                "player_id": "1002",
                "name": "Gandalf",
                "primary_weapon": "staff",
            },
        ]

        driver = MonsterDriver(
            mcp=MagicMock(),
            rate_limiter=MagicMock(acquire=AsyncMock()),
            pc_classes_repo=env["pc_repo"],
            riposte_timers_repo=env["riposte_repo"],
            button_factory=_make_button_factory(),
            state_provider=_make_state_provider(pcs),
            channel_resolver=lambda _ch: channel,
            ttl_seconds=8,
            # Force pick BM (first entry after exclusion)
            random_choice=lambda seq: next(p for p in seq if p["character_id"] == "hero-bm"),
        )

        monster_actor = {"character_id": "goblin-001", "player_id": None}

        with patch(
            "eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Miss.** Goblin Scout misses Thorin."),
        ):
            with patch(
                "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
                new=AsyncMock(),
            ) as mock_nt:
                await driver.drive(
                    channel_id="ch-1",
                    campaign_name="IntCamp",
                    current_actor=monster_actor,
                )

        # Exactly one pending riposte row for hero-bm
        rows = await env["riposte_repo"].list_for_character("ch-1", "hero-bm")
        assert len(rows) == 1
        row = rows[0]
        assert row.status == RiposteStatus.PENDING
        assert row.user_id == "1001"
        assert row.monster_uuid == "goblin-001"
        assert row.weapon_used == "longsword"
        # Deadline ~8s in the future
        assert row.deadline_ts > datetime.now(UTC) + timedelta(seconds=5)

        # channel.send received a mention + view
        channel.send.assert_awaited_once()
        send_kwargs = channel.send.call_args.kwargs
        assert "<@1001>" in send_kwargs["content"]
        assert send_kwargs.get("view") is not None

        # next_turn called
        mock_nt.assert_awaited_once()


# ── Test 7: monster misses wizard → no row; next_turn still called ───────────


class TestMonsterMissesWizard:
    @pytest.mark.asyncio
    async def test_no_row_for_non_eligible_target(self, smoke_env):
        env = smoke_env
        channel = _make_channel()

        pcs = [
            {
                "character_id": "hero-bm",
                "user_id": 1001,
                "player_id": "1001",
                "primary_weapon": "longsword",
            },
            {
                "character_id": "hero-wiz",
                "user_id": 1002,
                "player_id": "1002",
                "primary_weapon": "staff",
            },
        ]

        driver = MonsterDriver(
            mcp=MagicMock(),
            rate_limiter=MagicMock(acquire=AsyncMock()),
            pc_classes_repo=env["pc_repo"],
            riposte_timers_repo=env["riposte_repo"],
            button_factory=_make_button_factory(),
            state_provider=_make_state_provider(pcs),
            channel_resolver=lambda _ch: channel,
            ttl_seconds=8,
            # Force pick wizard
            random_choice=lambda seq: next(p for p in seq if p["character_id"] == "hero-wiz"),
        )

        monster_actor = {"character_id": "goblin-001", "player_id": None}

        with patch(
            "eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Miss.** Goblin misses Gandalf."),
        ):
            with patch(
                "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
                new=AsyncMock(),
            ) as mock_nt:
                await driver.drive(
                    channel_id="ch-1",
                    campaign_name="IntCamp",
                    current_actor=monster_actor,
                )

        # No riposte rows for wizard
        wiz_rows = await env["riposte_repo"].list_for_character("ch-1", "hero-wiz")
        assert wiz_rows == []
        # No riposte rows for BM either (wasn't chosen)
        bm_rows = await env["riposte_repo"].list_for_character("ch-1", "hero-bm")
        assert bm_rows == []

        # channel.send NOT called for wizard miss
        channel.send.assert_not_called()

        # next_turn still called
        mock_nt.assert_awaited_once()


# ── Test 8: BM already consumed this round → no new row ───────────────────────


class TestMonsterMissesBudgetExhausted:
    @pytest.mark.asyncio
    async def test_no_new_row_when_consumed_in_current_round(self, smoke_env):
        env = smoke_env
        channel = _make_channel()

        # Pre-insert a consumed riposte for BM in round 1
        pre_existing = RiposteTimer(
            channel_id="ch-1",
            character_id="hero-bm",
            user_id="1001",
            message_id="msg-prev",
            custom_id="riposte:99:1001",
            deadline_ts=datetime.now(UTC) - timedelta(seconds=60),
            status=RiposteStatus.CONSUMED,
            created_at=datetime.now(UTC),
            monster_uuid="goblin-prev",
            weapon_used="longsword",
            consumed_in_round=1,
        )
        await env["riposte_repo"].insert(pre_existing)

        pcs = [
            {
                "character_id": "hero-bm",
                "user_id": 1001,
                "player_id": "1001",
                "primary_weapon": "longsword",
            },
        ]

        driver = MonsterDriver(
            mcp=MagicMock(),
            rate_limiter=MagicMock(acquire=AsyncMock()),
            pc_classes_repo=env["pc_repo"],
            riposte_timers_repo=env["riposte_repo"],
            button_factory=_make_button_factory(),
            state_provider=_make_state_provider(pcs),
            channel_resolver=lambda _ch: channel,
            ttl_seconds=8,
            random_choice=lambda seq: list(seq)[0],
        )

        monster_actor = {"character_id": "goblin-001", "player_id": None}

        with patch(
            "eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Miss.** Goblin misses Thorin."),
        ):
            with patch(
                "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
                new=AsyncMock(),
            ) as mock_nt:
                await driver.drive(
                    channel_id="ch-1",
                    campaign_name="IntCamp",
                    current_actor=monster_actor,
                )

        # Still only the pre-existing consumed row (no new pending)
        rows = await env["riposte_repo"].list_for_character("ch-1", "hero-bm")
        assert len(rows) == 1, f"Expected 1 row (the pre-existing); got {len(rows)}"
        assert rows[0].status == RiposteStatus.CONSUMED
        assert rows[0].consumed_in_round == 1

        # channel.send NOT called
        channel.send.assert_not_called()
        # next_turn still called
        mock_nt.assert_awaited_once()
