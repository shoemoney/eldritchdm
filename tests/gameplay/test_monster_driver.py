"""
Tests for gameplay/monster_driver.py (Phase 5 Plan 01 Task 2).

Covers (per plan):
  - PC turn no-op
  - Random target picks PC excluding monster itself
  - combat_action called through rate_limiter
  - On MISS / NATURAL_ONE → eligibility check + surface_riposte_button
  - On HIT / CRITICAL → no riposte surface
  - next_turn always called
  - Empty target list → warning log + next_turn
  - TODO comment present for v2 smart targeting (D-B)
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from eldritch_dm.gameplay.monster_driver import MonsterDriver
from eldritch_dm.gameplay.reactions import RiposteEligibility

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_driver(
    *,
    random_choice=None,
    state_provider=None,
    pc_eligibility=None,
) -> tuple[MonsterDriver, dict]:
    """Build a MonsterDriver wired with AsyncMocks.

    Returns the driver plus a dict of references to inspect mock calls.
    """
    mcp = MagicMock()

    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock()

    pc_classes_repo = MagicMock()
    riposte_timers_repo = MagicMock()

    def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
        return discord.ui.Button(label="r", custom_id=f"riposte:{timer_id}:{user_id}")

    channel = MagicMock()
    channel.send = AsyncMock(return_value=MagicMock(id=12345))

    def channel_resolver(channel_id: str):
        return channel

    if state_provider is None:
        async def default_state_provider(channel_id, campaign_name):
            return {
                "round_number": 1,
                "pcs": [
                    {
                        "character_id": "hero-001",
                        "user_id": 1001,
                        "player_id": "1001",
                        "name": "Thorin",
                        "primary_weapon": "longsword",
                    },
                ],
            }
        state_provider = default_state_provider

    driver = MonsterDriver(
        mcp=mcp,
        rate_limiter=rate_limiter,
        pc_classes_repo=pc_classes_repo,
        riposte_timers_repo=riposte_timers_repo,
        button_factory=button_factory,
        state_provider=state_provider,
        channel_resolver=channel_resolver,
        ttl_seconds=8,
        random_choice=random_choice or (lambda seq: list(seq)[0]),
    )
    refs = {
        "mcp": mcp,
        "rate_limiter": rate_limiter,
        "channel": channel,
        "pc_classes_repo": pc_classes_repo,
        "riposte_timers_repo": riposte_timers_repo,
    }
    return driver, refs


# ── Test 17: PC turn no-op ────────────────────────────────────────────────────


class TestPCTurnNoOp:
    @pytest.mark.asyncio
    async def test_player_id_not_none_skips_drive(self) -> None:
        driver, refs = _make_driver()
        current_actor = {"character_id": "hero-001", "player_id": "1001"}

        with patch("eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action") as mock_ca:
            await driver.drive(
                channel_id="ch-1", campaign_name="Camp1", current_actor=current_actor
            )
            mock_ca.assert_not_called()
        refs["rate_limiter"].acquire.assert_not_called()


# ── Test 18: random target excludes monster itself ────────────────────────────


class TestRandomTargetExcludesMonster:
    @pytest.mark.asyncio
    async def test_target_chosen_from_pcs_only(self) -> None:
        async def state_provider(channel_id, campaign_name):
            return {
                "round_number": 1,
                "pcs": [
                    {"character_id": "hero-001", "user_id": 1001, "player_id": "1001"},
                    {"character_id": "hero-002", "user_id": 1002, "player_id": "1002"},
                ],
            }

        captured: dict = {}

        def fake_random(seq):
            captured["seq"] = list(seq)
            return list(seq)[0]

        driver, _ = _make_driver(random_choice=fake_random, state_provider=state_provider)
        current_actor = {"character_id": "goblin-001", "player_id": None}

        with patch(
            "eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Hit!** Goblin Scout hits Thorin."),
        ):
            with patch(
                "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
                new=AsyncMock(),
            ):
                await driver.drive(
                    channel_id="ch-1",
                    campaign_name="Camp1",
                    current_actor=current_actor,
                )

        # Monster ("goblin-001") must NOT be in the candidate set
        ids = [p.get("character_id") for p in captured["seq"]]
        assert "goblin-001" not in ids
        assert "hero-001" in ids


# ── Test 19: combat_action called through rate_limiter ────────────────────────


class TestCombatActionRateLimited:
    @pytest.mark.asyncio
    async def test_rate_limiter_acquired_before_combat_action(self) -> None:
        driver, refs = _make_driver()
        current_actor = {"character_id": "goblin-001", "player_id": None}

        call_order: list[str] = []

        async def track_acquire(channel_id):
            call_order.append("acquire")

        refs["rate_limiter"].acquire = AsyncMock(side_effect=track_acquire)

        async def fake_ca(*args, **kwargs):
            call_order.append("combat_action")
            return "**Hit!** A hits B."

        async def fake_nt(*args, **kwargs):
            call_order.append("next_turn")

        with patch(
            "eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action",
            new=AsyncMock(side_effect=fake_ca),
        ) as mock_ca:
            with patch(
                "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
                new=AsyncMock(side_effect=fake_nt),
            ):
                await driver.drive(
                    channel_id="ch-1",
                    campaign_name="Camp1",
                    current_actor=current_actor,
                )

        # acquire happens BEFORE combat_action
        assert call_order[0] == "acquire"
        assert "combat_action" in call_order
        # Combat-action kwargs include attacker + target
        ca_kwargs = mock_ca.call_args.kwargs
        assert ca_kwargs["action"] == "attack"
        assert ca_kwargs["attacker"] == "goblin-001"
        assert ca_kwargs["target"] == "hero-001"


# ── Test 20: MISS / NAT1 surface; HIT / CRIT do not ───────────────────────────


class TestRiposteSurfaceTrigger:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "result_text,should_check",
        [
            ("**Miss.** Goblin misses Thorin.", True),
            ("**Natural 1!** Goblin misses Thorin.", True),
            ("**Hit!** Goblin hits Thorin.", False),
            ("**CRITICAL HIT!** Goblin strikes Thorin!", False),
        ],
    )
    async def test_only_miss_paths_call_eligibility(
        self, result_text: str, should_check: bool
    ) -> None:
        driver, refs = _make_driver()
        current_actor = {"character_id": "goblin-001", "player_id": None}

        with patch(
            "eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action",
            new=AsyncMock(return_value=result_text),
        ):
            with patch(
                "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
                new=AsyncMock(),
            ):
                with patch(
                    "eldritch_dm.gameplay.monster_driver.check_riposte_eligibility",
                    new=AsyncMock(return_value=None),
                ) as mock_check:
                    with patch(
                        "eldritch_dm.gameplay.monster_driver.surface_riposte_button",
                        new=AsyncMock(return_value=42),
                    ) as mock_surf:
                        await driver.drive(
                            channel_id="ch-1",
                            campaign_name="Camp1",
                            current_actor=current_actor,
                        )

        if should_check:
            mock_check.assert_awaited()
        else:
            mock_check.assert_not_called()
            mock_surf.assert_not_called()

    @pytest.mark.asyncio
    async def test_miss_with_eligible_pc_calls_surface(self) -> None:
        driver, refs = _make_driver()
        current_actor = {"character_id": "goblin-001", "player_id": None}

        eligibility = RiposteEligibility(
            character_id="hero-001", user_id=1001, primary_weapon="longsword"
        )

        with patch(
            "eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Miss.** Goblin Scout misses Thorin."),
        ):
            with patch(
                "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
                new=AsyncMock(),
            ):
                with patch(
                    "eldritch_dm.gameplay.monster_driver.check_riposte_eligibility",
                    new=AsyncMock(return_value=eligibility),
                ):
                    with patch(
                        "eldritch_dm.gameplay.monster_driver.surface_riposte_button",
                        new=AsyncMock(return_value=42),
                    ) as mock_surf:
                        await driver.drive(
                            channel_id="ch-1",
                            campaign_name="Camp1",
                            current_actor=current_actor,
                        )

        mock_surf.assert_awaited_once()


# ── Test 21: next_turn always called ─────────────────────────────────────────


class TestNextTurnAlwaysCalled:
    @pytest.mark.asyncio
    async def test_next_turn_called_after_hit(self) -> None:
        driver, _ = _make_driver()
        current_actor = {"character_id": "goblin-001", "player_id": None}

        with patch(
            "eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Hit!** A hits B."),
        ):
            with patch(
                "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
                new=AsyncMock(),
            ) as mock_nt:
                await driver.drive(
                    channel_id="ch-1",
                    campaign_name="Camp1",
                    current_actor=current_actor,
                )
        mock_nt.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_next_turn_called_after_miss(self) -> None:
        driver, _ = _make_driver()
        current_actor = {"character_id": "goblin-001", "player_id": None}

        with patch(
            "eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action",
            new=AsyncMock(return_value="**Miss.** A misses B."),
        ):
            with patch(
                "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
                new=AsyncMock(),
            ) as mock_nt:
                with patch(
                    "eldritch_dm.gameplay.monster_driver.check_riposte_eligibility",
                    new=AsyncMock(return_value=None),
                ):
                    await driver.drive(
                        channel_id="ch-1",
                        campaign_name="Camp1",
                        current_actor=current_actor,
                    )
        mock_nt.assert_awaited_once()


# ── Test 22: empty PC list → warning + next_turn, NO combat_action ───────────


class TestNoEligibleTargets:
    @pytest.mark.asyncio
    async def test_zero_pcs_warns_and_advances(self) -> None:
        async def empty_state(channel_id, campaign_name):
            return {"round_number": 1, "pcs": []}

        driver, _ = _make_driver(state_provider=empty_state)
        current_actor = {"character_id": "goblin-001", "player_id": None}

        with patch(
            "eldritch_dm.gameplay.monster_driver.mcp_tools.combat_action",
            new=AsyncMock(),
        ) as mock_ca:
            with patch(
                "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
                new=AsyncMock(),
            ) as mock_nt:
                await driver.drive(
                    channel_id="ch-1",
                    campaign_name="Camp1",
                    current_actor=current_actor,
                )

        mock_ca.assert_not_called()
        mock_nt.assert_awaited_once()


# ── Test 23: D-B TODO comment present ────────────────────────────────────────


class TestPartyModeOrchestratorDispatch:
    """Phase 5 Plan 01 — orchestrator delegates monster turns once per turn key."""

    @pytest.mark.asyncio
    async def test_monster_turn_dispatched_once(self) -> None:
        from eldritch_dm.gameplay.exploration_batch import BatchCoordinator
        from eldritch_dm.gameplay.party_mode import PartyModeOrchestrator
        from eldritch_dm.mcp.rate_limit import ChannelRateLimiter

        driver = MagicMock()
        driver.drive = AsyncMock()

        orch = PartyModeOrchestrator(
            mcp=MagicMock(),
            rate_limiter=ChannelRateLimiter(min_interval_ms=0),
            batch_coordinator=BatchCoordinator(window_seconds=1.0),
            channel_sessions=MagicMock(),
            monster_driver=driver,
        )
        current_actor = {"character_id": "goblin-001", "player_id": None}

        result = await orch.maybe_drive_monster_turn(
            channel_id="ch-1",
            campaign_name="Camp1",
            current_actor=current_actor,
            round_number=1,
        )
        assert result is True
        driver.drive.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_consecutive_ticks_same_key_skipped(self) -> None:
        from eldritch_dm.gameplay.exploration_batch import BatchCoordinator
        from eldritch_dm.gameplay.party_mode import PartyModeOrchestrator
        from eldritch_dm.mcp.rate_limit import ChannelRateLimiter

        driver = MagicMock()
        driver.drive = AsyncMock()

        orch = PartyModeOrchestrator(
            mcp=MagicMock(),
            rate_limiter=ChannelRateLimiter(min_interval_ms=0),
            batch_coordinator=BatchCoordinator(window_seconds=1.0),
            channel_sessions=MagicMock(),
            monster_driver=driver,
        )
        current_actor = {"character_id": "goblin-001", "player_id": None}

        # First tick fires
        first = await orch.maybe_drive_monster_turn(
            channel_id="ch-1",
            campaign_name="Camp1",
            current_actor=current_actor,
            round_number=1,
        )
        # Second tick — same (round, monster) — skipped
        second = await orch.maybe_drive_monster_turn(
            channel_id="ch-1",
            campaign_name="Camp1",
            current_actor=current_actor,
            round_number=1,
        )
        assert first is True
        assert second is False
        assert driver.drive.await_count == 1

    @pytest.mark.asyncio
    async def test_pc_turn_skipped(self) -> None:
        from eldritch_dm.gameplay.exploration_batch import BatchCoordinator
        from eldritch_dm.gameplay.party_mode import PartyModeOrchestrator
        from eldritch_dm.mcp.rate_limit import ChannelRateLimiter

        driver = MagicMock()
        driver.drive = AsyncMock()

        orch = PartyModeOrchestrator(
            mcp=MagicMock(),
            rate_limiter=ChannelRateLimiter(min_interval_ms=0),
            batch_coordinator=BatchCoordinator(window_seconds=1.0),
            channel_sessions=MagicMock(),
            monster_driver=driver,
        )
        current_actor = {"character_id": "hero-001", "player_id": "1001"}

        result = await orch.maybe_drive_monster_turn(
            channel_id="ch-1",
            campaign_name="Camp1",
            current_actor=current_actor,
            round_number=1,
        )
        assert result is False
        driver.drive.assert_not_called()


class TestDBDecisionTodo:
    def test_db_random_targeting_todo_comment_present(self) -> None:
        """User decision D-B mandates a TODO comment noting random targeting is v1 only."""
        src = inspect.getsource(MonsterDriver)
        module_src = inspect.getsource(inspect.getmodule(MonsterDriver))
        combined = src + "\n" + module_src
        assert "D-B" in combined or "random PC targeting" in combined, (
            "MonsterDriver must contain a TODO/comment noting D-B v1 random targeting."
        )
        assert "Claudmaster" in combined or "smart targeting" in combined.lower(), (
            "MonsterDriver must document deferred v2 smart targeting."
        )
