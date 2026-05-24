"""
Tests for gameplay/reactions.py (Phase 5 Plan 01 Task 2).

Covers:
  - ELIGIBLE_CLASS_SUBCLASSES is strict RAW (Battle Master Fighter only).
  - check_riposte_eligibility: non-eligible class → None.
  - check_riposte_eligibility: missing pc_classes row → None.
  - check_riposte_eligibility: pending row → None.
  - check_riposte_eligibility: consumed-this-round → None.
  - check_riposte_eligibility: eligible Battle Master → RiposteEligibility.
  - check_riposte_eligibility: consumed-different-round does NOT block.
  - surface_riposte_button: insert + channel.send + update_message_ref order.
  - surface_riposte_button: View has timeout=None.
  - surface_riposte_button: returns the new timer_id.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.gameplay.reactions import (
    ELIGIBLE_CLASS_SUBCLASSES,
    RiposteEligibility,
    check_riposte_eligibility,
    surface_riposte_button,
)
from eldritch_dm.persistence.models import RiposteStatus, RiposteTimer
from eldritch_dm.persistence.pc_classes_repo import PCClassInfo

# ── Test 7: ELIGIBLE_CLASS_SUBCLASSES is strict RAW ──────────────────────────


class TestEligibleSetIsStrictRAW:
    def test_only_battle_master_fighter(self) -> None:
        assert ELIGIBLE_CLASS_SUBCLASSES == frozenset({("fighter", "battle master")})

    def test_no_swashbuckler(self) -> None:
        assert ("rogue", "swashbuckler") not in ELIGIBLE_CLASS_SUBCLASSES


# ── Helpers ────────────────────────────────────────────────────────────────────


def _mock_pc_repo(info: PCClassInfo | None) -> MagicMock:
    repo = MagicMock()
    repo.get = AsyncMock(return_value=info)
    return repo


def _mock_timer_repo(timers: list[RiposteTimer]) -> MagicMock:
    repo = MagicMock()
    repo.list_for_character = AsyncMock(return_value=timers)
    return repo


def _make_timer(
    *,
    status: RiposteStatus = RiposteStatus.PENDING,
    consumed_in_round: int | None = None,
    id_: int = 1,
) -> RiposteTimer:
    return RiposteTimer(
        id=id_,
        channel_id="ch-1",
        character_id="hero-001",
        user_id="123",
        message_id="m1",
        custom_id="cid",
        deadline_ts=datetime.now(UTC) + timedelta(seconds=8),
        status=status,
        created_at=datetime.now(UTC),
        consumed_in_round=consumed_in_round,
    )


# ── Test 8: non-eligible class → None ─────────────────────────────────────────


class TestCheckEligibilityNonEligibleClass:
    @pytest.mark.asyncio
    async def test_wizard_returns_none(self) -> None:
        pc_repo = _mock_pc_repo(PCClassInfo(class_name="wizard", subclass="evocation"))
        timer_repo = _mock_timer_repo([])

        result = await check_riposte_eligibility(
            channel_id="ch-1",
            character_id="hero-001",
            user_id=999,
            primary_weapon="staff",
            current_round=1,
            pc_classes_repo=pc_repo,
            riposte_timers_repo=timer_repo,
        )
        assert result is None


# ── Test 9: missing pc_classes row → None ─────────────────────────────────────


class TestCheckEligibilityMissingPCRow:
    @pytest.mark.asyncio
    async def test_missing_returns_none(self) -> None:
        pc_repo = _mock_pc_repo(None)
        timer_repo = _mock_timer_repo([])

        result = await check_riposte_eligibility(
            channel_id="ch-1",
            character_id="hero-001",
            user_id=999,
            primary_weapon="longsword",
            current_round=1,
            pc_classes_repo=pc_repo,
            riposte_timers_repo=timer_repo,
        )
        assert result is None


# ── Test 10: pending row → None ───────────────────────────────────────────────


class TestCheckEligibilityPendingBlocks:
    @pytest.mark.asyncio
    async def test_pending_row_blocks_new_one(self) -> None:
        pc_repo = _mock_pc_repo(PCClassInfo(class_name="fighter", subclass="battle master"))
        timer_repo = _mock_timer_repo([_make_timer(status=RiposteStatus.PENDING)])

        result = await check_riposte_eligibility(
            channel_id="ch-1",
            character_id="hero-001",
            user_id=999,
            primary_weapon="longsword",
            current_round=1,
            pc_classes_repo=pc_repo,
            riposte_timers_repo=timer_repo,
        )
        assert result is None


# ── Test 11: consumed_in_round == current_round → None ────────────────────────


class TestCheckEligibilityBudgetExhausted:
    @pytest.mark.asyncio
    async def test_consumed_this_round_blocks(self) -> None:
        pc_repo = _mock_pc_repo(PCClassInfo(class_name="fighter", subclass="battle master"))
        timer_repo = _mock_timer_repo(
            [_make_timer(status=RiposteStatus.CONSUMED, consumed_in_round=2)]
        )

        result = await check_riposte_eligibility(
            channel_id="ch-1",
            character_id="hero-001",
            user_id=999,
            primary_weapon="longsword",
            current_round=2,
            pc_classes_repo=pc_repo,
            riposte_timers_repo=timer_repo,
        )
        assert result is None


# ── Test 12: eligible BM → RiposteEligibility ─────────────────────────────────


class TestCheckEligibilityHappy:
    @pytest.mark.asyncio
    async def test_battle_master_no_pending_no_used_returns_eligibility(self) -> None:
        pc_repo = _mock_pc_repo(PCClassInfo(class_name="fighter", subclass="battle master"))
        timer_repo = _mock_timer_repo([])

        result = await check_riposte_eligibility(
            channel_id="ch-1",
            character_id="hero-001",
            user_id=999,
            primary_weapon="longsword",
            current_round=1,
            pc_classes_repo=pc_repo,
            riposte_timers_repo=timer_repo,
        )
        assert result == RiposteEligibility(
            character_id="hero-001",
            user_id=999,
            primary_weapon="longsword",
        )


# ── Test 13: consumed in DIFFERENT round does NOT block ───────────────────────


class TestCheckEligibilityPreviousRoundOK:
    @pytest.mark.asyncio
    async def test_consumed_prior_round_does_not_block(self) -> None:
        pc_repo = _mock_pc_repo(PCClassInfo(class_name="fighter", subclass="battle master"))
        # Consumed in round 2, current round 3 → fine
        timer_repo = _mock_timer_repo(
            [_make_timer(status=RiposteStatus.CONSUMED, consumed_in_round=2)]
        )

        result = await check_riposte_eligibility(
            channel_id="ch-1",
            character_id="hero-001",
            user_id=999,
            primary_weapon="longsword",
            current_round=3,
            pc_classes_repo=pc_repo,
            riposte_timers_repo=timer_repo,
        )
        assert result is not None
        assert result.character_id == "hero-001"


# ── Test 14: surface_riposte_button — insert, send, recompute deadline ────────


class _FakeDiscordMessage:
    def __init__(self, message_id: int = 7777) -> None:
        self.id = message_id


class TestSurfaceRiposteButton:
    @pytest.mark.asyncio
    async def test_inserts_then_sends_then_back_fills_message_ref(self) -> None:
        eligibility = RiposteEligibility(
            character_id="hero-001",
            user_id=999,
            primary_weapon="longsword",
        )

        # repo: insert returns timer with id=42; update_message_ref captures args
        repo = MagicMock()
        inserted_model = _make_timer(id_=42)
        repo.insert = AsyncMock(return_value=inserted_model)
        repo.update_message_ref = AsyncMock()

        # channel: send returns a message with id 7777
        channel = MagicMock()
        sent_message = _FakeDiscordMessage(message_id=7777)
        channel.send = AsyncMock(return_value=sent_message)

        # button_factory returns a sentinel that supports add_item
        def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
            btn = discord.ui.Button(label="riposte-test", custom_id=f"riposte:{timer_id}:{user_id}")
            return btn

        result_id = await surface_riposte_button(
            channel=channel,
            eligibility=eligibility,
            monster_uuid="goblin-001",
            round_number=1,
            channel_id="ch-1",
            repo=repo,
            button_factory=button_factory,
            ttl_seconds=8,
        )

        assert result_id == 42

        # repo.insert called first with a pending row
        assert repo.insert.await_count == 1
        # channel.send was called with mention + view
        assert channel.send.await_count == 1
        send_kwargs = channel.send.call_args.kwargs
        assert "<@999>" in send_kwargs["content"], (
            f"Expected user mention in content: {send_kwargs['content']!r}"
        )
        # update_message_ref called with the real ids
        repo.update_message_ref.assert_awaited_once()
        umr_kwargs = repo.update_message_ref.call_args.kwargs
        assert umr_kwargs["message_id"] == "7777"
        assert umr_kwargs["custom_id"] == "riposte:42:999"
        # deadline_ts is a datetime in the future
        assert isinstance(umr_kwargs["deadline_ts"], datetime)

    @pytest.mark.asyncio
    async def test_deadline_recomputed_after_channel_send(self) -> None:
        """Pitfall 1: deadline written via update_message_ref must be later than
        a timestamp captured immediately after channel.send returned."""
        eligibility = RiposteEligibility(
            character_id="hero-001", user_id=999, primary_weapon=None
        )

        repo = MagicMock()
        inserted_model = _make_timer(id_=10)
        repo.insert = AsyncMock(return_value=inserted_model)
        captured_deadline: list[datetime] = []

        async def capture_umr(timer_id, *, message_id, custom_id, deadline_ts):
            captured_deadline.append(deadline_ts)

        repo.update_message_ref = AsyncMock(side_effect=capture_umr)

        post_send_ts_holder: list[datetime] = []

        async def slow_send(*args, **kwargs):
            # Simulate API latency; capture the timestamp the moment send returns.
            import asyncio
            await asyncio.sleep(0.01)
            ts = datetime.now(UTC)
            post_send_ts_holder.append(ts)
            return _FakeDiscordMessage(message_id=12345)

        channel = MagicMock()
        channel.send = AsyncMock(side_effect=slow_send)

        def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
            return discord.ui.Button(label="x", custom_id=f"riposte:{timer_id}:{user_id}")

        await surface_riposte_button(
            channel=channel,
            eligibility=eligibility,
            monster_uuid="goblin-001",
            round_number=1,
            channel_id="ch-1",
            repo=repo,
            button_factory=button_factory,
            ttl_seconds=8,
        )

        assert captured_deadline, "update_message_ref should have been called"
        assert post_send_ts_holder, "channel.send should have been awaited"
        # deadline must be AFTER the post-send timestamp (NOW + ttl is well past then)
        assert captured_deadline[0] > post_send_ts_holder[0], (
            f"Deadline ({captured_deadline[0]}) must be later than post-send "
            f"timestamp ({post_send_ts_holder[0]}) — Pitfall 1 enforces recompute."
        )

    @pytest.mark.asyncio
    async def test_view_uses_timeout_none(self) -> None:
        """Sweeper owns the deadline — the View must be persistent (timeout=None)."""
        eligibility = RiposteEligibility(
            character_id="hero-001", user_id=999, primary_weapon=None
        )

        repo = MagicMock()
        repo.insert = AsyncMock(return_value=_make_timer(id_=1))
        repo.update_message_ref = AsyncMock()

        captured_view: list = []

        async def capture_send(*args, **kwargs):
            captured_view.append(kwargs.get("view"))
            return _FakeDiscordMessage(message_id=1)

        channel = MagicMock()
        channel.send = AsyncMock(side_effect=capture_send)

        def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
            return discord.ui.Button(label="x", custom_id=f"riposte:{timer_id}:{user_id}")

        await surface_riposte_button(
            channel=channel,
            eligibility=eligibility,
            monster_uuid="g",
            round_number=1,
            channel_id="ch-1",
            repo=repo,
            button_factory=button_factory,
            ttl_seconds=8,
        )

        assert captured_view, "channel.send should have been awaited with a view"
        view = captured_view[0]
        assert view is not None
        # discord.ui.View(timeout=None) means timeout attribute is None
        assert view.timeout is None, (
            f"View must be persistent (timeout=None); got timeout={view.timeout!r}"
        )

    @pytest.mark.asyncio
    async def test_returns_timer_id(self) -> None:
        """surface_riposte_button returns the new timer_id (int)."""
        eligibility = RiposteEligibility(
            character_id="hero-001", user_id=999, primary_weapon=None
        )

        repo = MagicMock()
        repo.insert = AsyncMock(return_value=_make_timer(id_=314))
        repo.update_message_ref = AsyncMock()

        channel = MagicMock()
        channel.send = AsyncMock(return_value=_FakeDiscordMessage(message_id=1))

        def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
            return discord.ui.Button(label="x", custom_id=f"riposte:{timer_id}:{user_id}")

        result = await surface_riposte_button(
            channel=channel,
            eligibility=eligibility,
            monster_uuid="g",
            round_number=1,
            channel_id="ch-1",
            repo=repo,
            button_factory=button_factory,
            ttl_seconds=8,
        )
        assert result == 314


# ── PLAN-02 LOCK INTEGRATION (post-Plan-02) ──────────────────────────────────


class TestPlan02LockIntegrated:
    """Plan 02 replaces the PLAN-01 marker with the real session_locks wrapper.

    These tests REPLACED the Plan 01 marker-present check now that Plan 02
    has shipped the actual lock plumbing.
    """

    def test_marker_is_gone_from_handle_riposte_click(self) -> None:
        """The PLAN-02-LOCK-SEAM marker MUST be absent post-Plan-02."""
        import inspect

        from eldritch_dm.gameplay.reactions import handle_riposte_click

        src = inspect.getsource(handle_riposte_click)
        assert "PLAN-02-LOCK-SEAM" not in src, (
            "Plan 02 should have replaced the PLAN-02-LOCK-SEAM marker with a "
            "real session_locks.lock_for('riposte', channel_id) wrapper."
        )

    def test_session_locks_lock_for_is_called(self) -> None:
        """handle_riposte_click must wrap the mutate path in session_locks."""
        import inspect

        from eldritch_dm.gameplay.reactions import handle_riposte_click

        src = inspect.getsource(handle_riposte_click)
        assert (
            'session_locks.lock_for("riposte"' in src
            or "session_locks.lock_for('riposte'" in src
        ), (
            "handle_riposte_click must wrap the read-then-mark sequence in "
            "session_locks.lock_for('riposte', channel_id). See Plan 02 task 1."
        )
