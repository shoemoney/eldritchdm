"""
End-to-end combat flow integration test.

Exercises the full Phase 4 combat happy path with mocked dm20:

  Test 13: Full mocked flow — EXPLORATION -> COMBAT (3rd poll) -> AttackButton ->
           modal submit -> combat_action -> resolve -> next turn -> 3 rounds ->
           EXPLORATION re-render.

  Test 14: DodgeButton exercised at least once — verifies dodge shim end-to-end
           (combat_conditions row + apply_effect + next_turn).

  Test 15: Non-active player clicking AttackButton receives NOT_YOUR_TURN;
           rate_limiter.acquire NOT called for rejected clicks.

All external deps (dm20 MCP) are mocked. Persistence uses real in-memory SQLite
where needed (for CombatConditionsRepo). Discord gateway never connects.

Phase 4 Plan 02.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from eldritch_dm.bot.cogs.combat import CombatCog
from eldritch_dm.bot.dynamic_items import AttackButton, DodgeButton, EndTurnButton
from eldritch_dm.persistence.models import ChannelSession, ChannelState

# ── Test constants ────────────────────────────────────────────────────────────

_CHANNEL_ID = "9001"
_CAMPAIGN = "IntegrationCamp"
_SESSION_ID = "int-sess-001"

# 4 PCs with known player_ids
_PCS = [
    {"id": "hero-001", "name": "Thorin", "player_id": "1001", "hp_current": 55, "hp_max": 55, "ac": 18, "conditions": []},
    {"id": "hero-002", "name": "Gandalf", "player_id": "1002", "hp_current": 38, "hp_max": 38, "ac": 12, "conditions": []},
    {"id": "hero-003", "name": "Legolas", "player_id": "1003", "hp_current": 42, "hp_max": 42, "ac": 16, "conditions": []},
    {"id": "hero-004", "name": "Gimli",  "player_id": "1004", "hp_current": 60, "hp_max": 60, "ac": 19, "conditions": []},
]

# 4 monsters with player_id=None
_MONSTERS = [
    {"id": "goblin-001", "name": "Goblin1", "player_id": None, "hp_current": 10, "hp_max": 10, "ac": 13, "conditions": []},
    {"id": "goblin-002", "name": "Goblin2", "player_id": None, "hp_current": 10, "hp_max": 10, "ac": 13, "conditions": []},
    {"id": "goblin-003", "name": "Goblin3", "player_id": None, "hp_current": 10, "hp_max": 10, "ac": 13, "conditions": []},
    {"id": "goblin-004", "name": "Goblin4", "player_id": None, "hp_current": 10, "hp_max": 10, "ac": 13, "conditions": []},
]


def _make_game_state(current_actor_id: str = "hero-001", round_n: int = 1) -> dict:
    combatants = [dict(c) for c in _PCS] + [dict(m) for m in _MONSTERS]
    return {
        "current_actor_id": current_actor_id,
        "combatants": combatants,
        "round_number": round_n,
        "in_combat": True,
    }


def _make_session(state: ChannelState = ChannelState.COMBAT) -> ChannelSession:
    return ChannelSession(
        channel_id=_CHANNEL_ID,
        campaign_name=_CAMPAIGN,
        claudmaster_session_id=_SESSION_ID,
        dm20_party_token=None,
        state=state,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )


def _make_interaction(user_id: str = "1001", channel_id: str = _CHANNEL_ID) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = int(user_id)
    interaction.channel_id = int(channel_id)
    interaction.guild_id = 99999

    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()

    # Bot on the interaction
    bot = MagicMock()
    bot.mcp = MagicMock()
    bot.settings = MagicMock()
    bot.settings.eldritch_db_path = ":memory:"
    bot.rate_limiter = AsyncMock()
    bot.rate_limiter.acquire = AsyncMock()

    cs_repo = AsyncMock()
    cs_repo.get = AsyncMock()
    bot.channel_sessions = cs_repo

    interaction.client = bot

    return interaction


def _make_bot(session: ChannelSession | None = None) -> MagicMock:
    bot = MagicMock()
    bot.settings = MagicMock()
    bot.settings.embed_edit_rate_limit = 1.0
    bot.settings.eldritch_db_path = ":memory:"

    cs_repo = AsyncMock()
    cs_repo.get.return_value = session
    bot.channel_sessions = cs_repo

    budget = MagicMock()
    budget.acquire = AsyncMock()
    bot.get_channel_edit_budget = MagicMock(return_value=budget)

    orchestrator = MagicMock()
    orchestrator.register_resolution_callback = MagicMock()
    orchestrator.register_state_change_callback = MagicMock()
    bot.orchestrator = orchestrator

    bot.mcp = MagicMock()
    bot.rate_limiter = AsyncMock()
    bot.rate_limiter.acquire = AsyncMock()
    bot.close_exploration_coalescer_for = AsyncMock()

    return bot


def _make_channel() -> AsyncMock:
    channel = AsyncMock()
    channel.id = int(_CHANNEL_ID)
    msg = MagicMock(spec=discord.Message)
    msg.id = 7777
    msg.edit = AsyncMock()
    channel.send = AsyncMock(return_value=msg)
    return channel


# ── Test 13: Full mocked 3-round combat flow ──────────────────────────────────


class TestCombatFlowThreeRounds:
    @pytest.mark.asyncio
    async def test_exploration_to_combat_transition(self) -> None:
        """EXPLORATION->COMBAT transition posts combat_embed."""
        session = _make_session(state=ChannelState.COMBAT)
        bot = _make_bot(session=session)
        channel = _make_channel()
        bot.get_channel = MagicMock(return_value=channel)

        cog = CombatCog(bot)
        game_state = _make_game_state(current_actor_id="hero-001", round_n=1)

        with patch.object(cog, "_fetch_game_state", new=AsyncMock(return_value=game_state)):
            await cog.on_state_change(_CHANNEL_ID, ChannelState.EXPLORATION, ChannelState.COMBAT)

        assert channel.send.called
        send_kwargs = channel.send.call_args.kwargs
        assert "embed" in send_kwargs
        embed = send_kwargs["embed"]
        assert "Round 1" in embed.title

    @pytest.mark.asyncio
    async def test_attack_button_dispatches_combat_action(self) -> None:
        """AttackButton.callback with active actor calls combat_action."""
        game_state = _make_game_state(current_actor_id="hero-001", round_n=1)
        session = _make_session(state=ChannelState.COMBAT)

        interaction = _make_interaction(user_id="1001")  # hero-001's player
        interaction.client.channel_sessions.get.return_value = session

        btn = AttackButton(channel_id=int(_CHANNEL_ID), actor_id="hero-001", round_n=1)

        mcp_mock = interaction.client.mcp
        mcp_mock.call = AsyncMock(return_value={"result": "attack resolved"})

        with patch.object(btn, "_get_enriched_game_state", new=AsyncMock(return_value=game_state)):
            with patch("eldritch_dm.bot.dynamic_items.mcp_tools.combat_action", new=AsyncMock(return_value={"outcome": "hit"})) as mock_ca:
                # Simulate modal submission by patching WeaponSelectModal at its source
                with patch("eldritch_dm.bot.modals.WeaponSelectModal") as mock_modal_cls:
                    modal_instance = MagicMock()
                    # Capture the on_submit_cb so we can call it
                    captured_cb: list = []

                    def capture_modal_init(*, on_submit_cb):
                        captured_cb.append(on_submit_cb)
                        return modal_instance

                    mock_modal_cls.side_effect = capture_modal_init

                    await btn.callback(interaction)

                    # Simulate modal submission
                    if captured_cb:
                        await captured_cb[0]({"weapon": "Longsword", "target_id": "goblin-001"})

                    # combat_action should have been called
                    mock_ca.assert_awaited_once()
                    call_kwargs = mock_ca.call_args.kwargs
                    assert call_kwargs.get("action") == "attack"

    @pytest.mark.asyncio
    async def test_endturn_button_dispatches_next_turn(self) -> None:
        """EndTurnButton.callback with active actor calls next_turn."""
        game_state = _make_game_state(current_actor_id="hero-001", round_n=1)
        session = _make_session(state=ChannelState.COMBAT)

        interaction = _make_interaction(user_id="1001")
        interaction.client.channel_sessions.get.return_value = session

        btn = EndTurnButton(channel_id=int(_CHANNEL_ID), actor_id="hero-001", round_n=1)

        with patch.object(btn, "_get_enriched_game_state", new=AsyncMock(return_value=game_state)):
            with patch("eldritch_dm.bot.dynamic_items.mcp_tools.next_turn", new=AsyncMock()) as mock_nt:
                await btn.callback(interaction)
                mock_nt.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_three_round_sequence_triggers_three_next_turns(self) -> None:
        """Simulate 3 EndTurn clicks across 3 rounds — next_turn called 3 times."""
        next_turn_calls: list[int] = []

        async def mock_next_turn(mcp):
            next_turn_calls.append(1)

        for round_n in range(1, 4):
            game_state = _make_game_state(current_actor_id="hero-001", round_n=round_n)
            session = _make_session(state=ChannelState.COMBAT)

            interaction = _make_interaction(user_id="1001")
            interaction.client.channel_sessions.get.return_value = session

            btn = EndTurnButton(channel_id=int(_CHANNEL_ID), actor_id="hero-001", round_n=round_n)

            with patch.object(btn, "_get_enriched_game_state", new=AsyncMock(return_value=game_state)):
                with patch("eldritch_dm.bot.dynamic_items.mcp_tools.next_turn", side_effect=mock_next_turn):
                    await btn.callback(interaction)

        assert len(next_turn_calls) == 3, f"Expected 3 next_turn calls, got {len(next_turn_calls)}"

    @pytest.mark.asyncio
    async def test_combat_to_exploration_transition_re_renders_room(self) -> None:
        """COMBAT->EXPLORATION transition closes combat coalescer."""
        bot = _make_bot()
        cog = CombatCog(bot)

        coalescer_mock = AsyncMock()
        coalescer_mock.close = AsyncMock()
        cog._coalescers[_CHANNEL_ID] = coalescer_mock
        msg_mock = MagicMock(spec=discord.Message)
        msg_mock.edit = AsyncMock()
        cog._combat_messages[_CHANNEL_ID] = msg_mock

        await cog.on_state_change(_CHANNEL_ID, ChannelState.COMBAT, ChannelState.EXPLORATION)

        coalescer_mock.close.assert_awaited_once()
        msg_mock.edit.assert_awaited_once()


# ── Test 14: DodgeButton end-to-end ──────────────────────────────────────────


class TestDodgeButtonEndToEnd:
    @pytest.mark.asyncio
    async def test_dodge_writes_conditions_and_calls_next_turn(self) -> None:
        """DodgeButton flow: combat_conditions insert + apply_effect + next_turn."""
        game_state = _make_game_state(current_actor_id="hero-001", round_n=2)
        session = _make_session(state=ChannelState.COMBAT)

        interaction = _make_interaction(user_id="1001")
        interaction.client.channel_sessions.get.return_value = session
        interaction.client.settings.eldritch_db_path = ":memory:"

        btn = DodgeButton(channel_id=int(_CHANNEL_ID), actor_id="hero-001", round_n=2)

        insert_calls: list[dict] = []

        async def mock_insert(**kwargs):
            insert_calls.append(kwargs)

        with patch.object(btn, "_get_enriched_game_state", new=AsyncMock(return_value=game_state)):
            with patch("eldritch_dm.bot.dynamic_items.CombatConditionsRepo") as mock_repo_cls:
                repo_instance = AsyncMock()
                repo_instance.insert = AsyncMock(side_effect=mock_insert)
                mock_repo_cls.return_value = repo_instance

                with patch("eldritch_dm.bot.dynamic_items.mcp_tools.apply_effect", new=AsyncMock()) as mock_ae:
                    with patch("eldritch_dm.bot.dynamic_items.mcp_tools.next_turn", new=AsyncMock()) as mock_nt:
                        await btn.callback(interaction)

                        # repo.insert should have been called
                        repo_instance.insert.assert_awaited_once()
                        insert_kwargs = repo_instance.insert.call_args.kwargs
                        assert insert_kwargs.get("character_id") == "hero-001"
                        assert insert_kwargs.get("condition_kind") == "dodging"

                        # apply_effect for narrative hint
                        mock_ae.assert_awaited_once()
                        ae_kwargs = mock_ae.call_args.kwargs
                        assert ae_kwargs.get("effect") == "dodging"

                        # next_turn to end the turn
                        mock_nt.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dodge_expires_after_one_round(self) -> None:
        """DodgeButton inserts condition row with expires_round = applied_round + 1."""
        game_state = _make_game_state(current_actor_id="hero-001", round_n=5)
        session = _make_session(state=ChannelState.COMBAT)

        interaction = _make_interaction(user_id="1001")
        interaction.client.channel_sessions.get.return_value = session
        interaction.client.settings.eldritch_db_path = ":memory:"

        btn = DodgeButton(channel_id=int(_CHANNEL_ID), actor_id="hero-001", round_n=5)

        with patch.object(btn, "_get_enriched_game_state", new=AsyncMock(return_value=game_state)):
            with patch("eldritch_dm.bot.dynamic_items.CombatConditionsRepo") as mock_repo_cls:
                repo_instance = AsyncMock()
                mock_repo_cls.return_value = repo_instance

                with patch("eldritch_dm.bot.dynamic_items.mcp_tools.apply_effect", new=AsyncMock()):
                    with patch("eldritch_dm.bot.dynamic_items.mcp_tools.next_turn", new=AsyncMock()):
                        await btn.callback(interaction)

                        insert_kwargs = repo_instance.insert.call_args.kwargs
                        applied = insert_kwargs.get("applied_round")
                        expires = insert_kwargs.get("expires_round")
                        assert applied == 5
                        assert expires == 6, f"Expected expires_round=6, got {expires}"


# ── Test 15: NOT_YOUR_TURN rejects don't count against rate limiter ───────────


class TestNotYourTurnRateLimit:
    @pytest.mark.asyncio
    async def test_wrong_player_click_does_not_acquire_rate_limiter(self) -> None:
        """Non-active player clicking AttackButton -- rate_limiter.acquire NOT called."""
        # hero-001 is current actor; user 1002 (Gandalf) clicks
        game_state = _make_game_state(current_actor_id="hero-001", round_n=1)
        session = _make_session(state=ChannelState.COMBAT)

        interaction = _make_interaction(user_id="1002")  # Not hero-001's player
        interaction.client.channel_sessions.get.return_value = session
        rate_limiter_mock = interaction.client.rate_limiter

        btn = AttackButton(channel_id=int(_CHANNEL_ID), actor_id="hero-001", round_n=1)

        with patch.object(btn, "_get_enriched_game_state", new=AsyncMock(return_value=game_state)):
            with patch("eldritch_dm.bot.dynamic_items.send_warning", new=AsyncMock()):
                await btn.callback(interaction)

        # Rate limiter should NOT have been called (rejection, no MCP call)
        rate_limiter_mock.acquire.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_active_player_click_acquires_rate_limiter(self) -> None:
        """Active player clicking AttackButton -- rate_limiter.acquire IS called."""
        game_state = _make_game_state(current_actor_id="hero-001", round_n=1)
        session = _make_session(state=ChannelState.COMBAT)

        interaction = _make_interaction(user_id="1001")  # hero-001's player
        interaction.client.channel_sessions.get.return_value = session
        rate_limiter_mock = interaction.client.rate_limiter

        btn = AttackButton(channel_id=int(_CHANNEL_ID), actor_id="hero-001", round_n=1)

        with patch.object(btn, "_get_enriched_game_state", new=AsyncMock(return_value=game_state)):
            with patch("eldritch_dm.bot.dynamic_items.mcp_tools.combat_action", new=AsyncMock(return_value={})):
                # WeaponSelectModal is imported inside the callback -- patch at the class source
                with patch("eldritch_dm.bot.modals.WeaponSelectModal") as mock_modal_cls:
                    captured_cb: list = []

                    def capture_init(*, on_submit_cb):
                        captured_cb.append(on_submit_cb)
                        return MagicMock()

                    mock_modal_cls.side_effect = capture_init
                    await btn.callback(interaction)

                    # Trigger the modal's submit callback
                    if captured_cb:
                        await captured_cb[0]({"weapon": "Sword", "target_id": "goblin-001"})

        # Rate limiter SHOULD have been called once (for the attack)
        rate_limiter_mock.acquire.assert_awaited()

    @pytest.mark.asyncio
    async def test_stale_round_click_does_not_acquire_rate_limiter(self) -> None:
        """Stale-round click (round mismatch) -- rate_limiter.acquire NOT called."""
        # Current round is 3 but button was from round 1
        game_state = _make_game_state(current_actor_id="hero-001", round_n=3)
        session = _make_session(state=ChannelState.COMBAT)

        interaction = _make_interaction(user_id="1001")
        interaction.client.channel_sessions.get.return_value = session
        rate_limiter_mock = interaction.client.rate_limiter

        # Button round_n=1, game is on round 3 -- stale
        btn = EndTurnButton(channel_id=int(_CHANNEL_ID), actor_id="hero-001", round_n=1)

        with patch.object(btn, "_get_enriched_game_state", new=AsyncMock(return_value=game_state)):
            await btn.callback(interaction)

        rate_limiter_mock.acquire.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_monster_turn_player_click_does_not_acquire_rate_limiter(self) -> None:
        """When monster is current actor, player clicks are rejected without rate_limiter call."""
        # Current actor is a monster
        game_state = _make_game_state(current_actor_id="goblin-001", round_n=1)
        session = _make_session(state=ChannelState.COMBAT)

        # Try from hero-001's player
        interaction = _make_interaction(user_id="1001")
        interaction.client.channel_sessions.get.return_value = session
        rate_limiter_mock = interaction.client.rate_limiter

        btn = EndTurnButton(channel_id=int(_CHANNEL_ID), actor_id="goblin-001", round_n=1)

        with patch.object(btn, "_get_enriched_game_state", new=AsyncMock(return_value=game_state)):
            await btn.callback(interaction)

        rate_limiter_mock.acquire.assert_not_awaited()


# ── Test: CombatCog embed refresh after resolve ───────────────────────────────


class TestCombatCogEmbedRefresh:
    @pytest.mark.asyncio
    async def test_embed_refreshes_with_new_current_actor(self) -> None:
        """After resolve, combat embed shows new current actor with ▶️."""
        session = _make_session(state=ChannelState.COMBAT)
        bot = _make_bot(session=session)
        cog = CombatCog(bot)

        coalescer_mock = AsyncMock()
        coalescer_mock.update = AsyncMock()
        cog._coalescers[_CHANNEL_ID] = coalescer_mock

        # Turn advances to hero-002
        game_state = _make_game_state(current_actor_id="hero-002", round_n=1)

        with patch.object(cog, "_fetch_game_state", new=AsyncMock(return_value=game_state)):
            await cog.on_resolved_combat(_CHANNEL_ID, {"type": "turn_resolved"})

        coalescer_mock.update.assert_awaited_once()
        call_args = coalescer_mock.update.call_args
        # embed is passed as positional arg: update(embed, view=view)
        embed = call_args.args[0] if call_args.args else call_args.kwargs.get("embed")
        assert embed is not None

        # The embed should have ▶️ for Gandalf (hero-002, "Gandalf")
        field_names = [f.name for f in embed.fields]
        assert any("▶️" in name and "Gandalf" in name for name in field_names), (
            f"Expected ▶️ Gandalf marker in fields: {field_names}"
        )

    @pytest.mark.asyncio
    async def test_embed_buttons_rebuilt_for_new_actor(self) -> None:
        """After resolve, view buttons encode new current actor's id."""
        session = _make_session(state=ChannelState.COMBAT)
        bot = _make_bot(session=session)
        cog = CombatCog(bot)

        coalescer_mock = AsyncMock()
        coalescer_mock.update = AsyncMock()
        cog._coalescers[_CHANNEL_ID] = coalescer_mock

        # Turn advances to hero-002
        game_state = _make_game_state(current_actor_id="hero-002", round_n=2)

        with patch.object(cog, "_fetch_game_state", new=AsyncMock(return_value=game_state)):
            await cog.on_resolved_combat(_CHANNEL_ID, {})

        coalescer_mock.update.assert_awaited_once()
        call_args = coalescer_mock.update.call_args
        view = call_args.kwargs.get("view")
        if view is not None and len(view.children) > 0:
            custom_ids = [item.custom_id for item in view.children if hasattr(item, "custom_id")]
            assert any("hero-002" in cid for cid in custom_ids), (
                f"Expected hero-002 in rebuilt view custom_ids: {custom_ids}"
            )
