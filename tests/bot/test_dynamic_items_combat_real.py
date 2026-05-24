"""
Tests for combat DynamicItem subclasses: AttackButton, DodgeButton,
CastSpellButton, and the promoted EndTurnButton.callback.

Tests verify:
  - custom_id round-trip (instance.custom_id parses back via regex)
  - actor_id pattern: accepts UUID/lowercase; rejects uppercase/special chars
  - Active-actor path: correct MCP call dispatched
  - Non-active-actor path: NOT_YOUR_TURN, no MCP call
  - Monster-turn: all player clicks rejected
  - Stale-round: INVALID_ACTION when round in custom_id != current round
  - Dodge: writes row + calls apply_effect + next_turn
  - CastSpell stub: ephemeral v2 message; still gated by is_actor

Phase 4 Plan 02.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from eldritch_dm.bot.dynamic_items import (
    AttackButton,
    CastSpellButton,
    DodgeButton,
    EndTurnButton,
)

# ── Template regex helpers ────────────────────────────────────────────────────

def parse_custom_id(pattern: re.Pattern, custom_id: str) -> re.Match | None:
    return pattern.fullmatch(custom_id)


# ── Test 1 / Test 7: custom_id round-trips ───────────────────────────────────

class TestAttackButtonCustomId:
    """Tests 1-2: custom_id round-trip and actor_id pattern acceptance."""

    def test_custom_id_round_trip_integer_channel(self) -> None:
        """AttackButton.custom_id parses back via template."""
        btn = AttackButton(channel_id=123456789, actor_id="abc-123", round_n=5)
        cid = btn.custom_id
        match = AttackButton.template.fullmatch(cid)
        assert match is not None
        assert match["channel_id"] == "123456789"
        assert match["actor_id"] == "abc-123"
        assert match["round"] == "5"

    def test_custom_id_round_trip_uuid_actor(self) -> None:
        """AttackButton custom_id accepts UUID-style actor_id (8-4-4-4-12 hex)."""
        actor_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        btn = AttackButton(channel_id=111, actor_id=actor_id, round_n=1)
        match = AttackButton.template.fullmatch(btn.custom_id)
        assert match is not None
        assert match["actor_id"] == actor_id

    def test_actor_id_accepts_lowercase_alphanumeric_dash(self) -> None:
        """actor_id pattern allows lowercase alphanumeric + dash."""
        for actor_id in ["abc123", "a-b-c", "deadbeef", "hero-001"]:
            btn = AttackButton(channel_id=1, actor_id=actor_id, round_n=1)
            match = AttackButton.template.fullmatch(btn.custom_id)
            assert match is not None, f"Should match: {actor_id}"

    def test_actor_id_rejects_uppercase(self) -> None:
        """Uppercase in actor_id must not match the template regex."""
        # The template pattern should reject uppercase
        # (we test the regex directly since invalid ids won't be created normally)
        pattern = AttackButton.template
        assert pattern.fullmatch("attack:123:UPPERCASE:1") is None

    def test_actor_id_rejects_special_chars(self) -> None:
        """actor_id pattern rejects @ # $ etc."""
        pattern = AttackButton.template
        for bad in ["attack:123:abc@def:1", "attack:123:abc#:1", "attack:123:a b:1"]:
            assert pattern.fullmatch(bad) is None, f"Should not match: {bad}"


class TestDodgeButtonCustomId:
    def test_custom_id_round_trip(self) -> None:
        """DodgeButton.custom_id parses back via template."""
        btn = DodgeButton(channel_id=999, actor_id="hero-002", round_n=3)
        cid = btn.custom_id
        match = DodgeButton.template.fullmatch(cid)
        assert match is not None
        assert match["channel_id"] == "999"
        assert match["actor_id"] == "hero-002"
        assert match["round"] == "3"


class TestEndTurnButtonCustomId:
    def test_custom_id_round_trip(self) -> None:
        """EndTurnButton.custom_id parses back via template (Phase 4 format)."""
        btn = EndTurnButton(channel_id=555, actor_id="thorin-001", round_n=2)
        cid = btn.custom_id
        match = EndTurnButton.template.fullmatch(cid)
        assert match is not None
        assert match["channel_id"] == "555"
        assert match["actor_id"] == "thorin-001"
        assert match["round"] == "2"

    def test_endturn_template_requires_round(self) -> None:
        """Phase 4 EndTurnButton template requires round segment."""
        pattern = EndTurnButton.template
        # New format: endturn:channel_id:actor_id:round
        assert pattern.fullmatch("endturn:123:hero-001:5") is not None
        # Old Phase-2 format (no round) should NOT match
        assert pattern.fullmatch("endturn:123:111111111") is None


class TestCastSpellButtonCustomId:
    def test_custom_id_round_trip(self) -> None:
        """CastSpellButton.custom_id parses back via template."""
        btn = CastSpellButton(channel_id=777, actor_id="wizard-001", round_n=4)
        cid = btn.custom_id
        match = CastSpellButton.template.fullmatch(cid)
        assert match is not None
        assert match["actor_id"] == "wizard-001"


# ── Registration ──────────────────────────────────────────────────────────────

class TestDynamicItemRegistration:
    def test_attack_button_in_dynamic_item_classes(self) -> None:
        """AttackButton is in DYNAMIC_ITEM_CLASSES."""
        from eldritch_dm.bot.dynamic_items import DYNAMIC_ITEM_CLASSES
        assert AttackButton in DYNAMIC_ITEM_CLASSES

    def test_dodge_button_in_dynamic_item_classes(self) -> None:
        """DodgeButton is in DYNAMIC_ITEM_CLASSES."""
        from eldritch_dm.bot.dynamic_items import DYNAMIC_ITEM_CLASSES
        assert DodgeButton in DYNAMIC_ITEM_CLASSES

    def test_cast_spell_button_in_dynamic_item_classes(self) -> None:
        """CastSpellButton is in DYNAMIC_ITEM_CLASSES."""
        from eldritch_dm.bot.dynamic_items import DYNAMIC_ITEM_CLASSES
        assert CastSpellButton in DYNAMIC_ITEM_CLASSES


# ── Shared interaction mock factory ──────────────────────────────────────────

def _make_interaction(
    user_id: str = "111111111111111111",
    channel_id_str: str = "999999999999",
) -> MagicMock:
    """Build a minimal discord.Interaction mock for callback testing."""
    interaction = MagicMock()
    interaction.user = MagicMock()
    interaction.user.id = int(user_id)
    interaction.user.display_name = "TestPlayer"
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    # interaction.client is the bot
    bot = MagicMock()
    bot.channel_sessions = AsyncMock()
    bot.mcp = MagicMock()
    bot.rate_limiter = MagicMock()
    bot.rate_limiter.acquire = AsyncMock()
    interaction.client = bot
    return interaction


def _make_game_state_response(
    current_actor_name: str,
    current_actor_id: str,
    current_actor_player_id: str | None,
    round_number: int,
    in_combat: bool = True,
) -> str:
    """Build a minimal dm20-style game_state markdown string."""
    player_id_str = current_actor_player_id or "None"
    return (
        f"## Game State\n\n"
        f"**Campaign:** TestCampaign\n"
        f"**In Combat:** {'Yes' if in_combat else 'No'}\n"
        f"**Current Turn:** {current_actor_name}\n"
        f"**Round:** {round_number}\n\n"
        f"### Initiative Order\n"
        f"  1. {current_actor_name} (Initiative: 20)\n"
        f"**Current Actor ID:** {current_actor_id}\n"
        f"**Player ID:** {player_id_str}\n"
    )


def _make_session(state: str = "COMBAT", campaign_name: str = "TestCampaign") -> MagicMock:
    sess = MagicMock()
    sess.state = state
    sess.campaign_name = campaign_name
    sess.claudmaster_session_id = "session-123"
    return sess


# ── Test 4: Non-active actor → NOT_YOUR_TURN ─────────────────────────────────

class TestEndTurnCallbackGatekeeper:
    """Tests 12-14: EndTurnButton callback — promoted from Phase 2 stub."""

    @pytest.mark.asyncio
    async def test_endturn_no_phase2_stub_log(self) -> None:
        """EndTurnButton callback must NOT log phase2_stub_callback_invoked."""
        btn = EndTurnButton(channel_id=123, actor_id="hero-001", round_n=1)
        interaction = _make_interaction(user_id="111111111111111111")

        # Mock session returning COMBAT state
        session = _make_session(state="COMBAT")
        interaction.client.channel_sessions.get = AsyncMock(return_value=session)

        # Mock game_state — actor id hero-001 maps to player_id 111111111111111111
        enriched_state = {
            "current_actor_id": "hero-001",
            "combatants": [
                {
                    "id": "hero-001",
                    "name": "Thorin",
                    "player_id": "111111111111111111",
                    "hp_current": 50,
                    "hp_max": 50,
                    "ac": 18,
                    "conditions": [],
                }
            ],
            "round_number": 1,
            "in_combat": True,
        }

        with patch.object(btn, "_get_enriched_game_state", AsyncMock(return_value=enriched_state)):
            with patch("eldritch_dm.bot.dynamic_items.mcp_tools") as mock_tools:
                mock_tools.next_turn = AsyncMock(return_value={})
                with patch("eldritch_dm.bot.dynamic_items.log") as mock_log:
                    await btn.callback(interaction)
                    # Verify "phase2_stub_callback_invoked" was never logged
                    for call in mock_log.info.call_args_list:
                        assert "phase2_stub_callback_invoked" not in str(call)

    @pytest.mark.asyncio
    async def test_endturn_not_active_actor_warns(self) -> None:
        """Non-active actor clicking EndTurn gets NOT_YOUR_TURN."""
        btn = EndTurnButton(channel_id=123, actor_id="hero-001", round_n=1)
        # Clicker user_id is different from actor player_id
        interaction = _make_interaction(user_id="999999999999999999")
        session = _make_session(state="COMBAT")
        interaction.client.channel_sessions.get = AsyncMock(return_value=session)

        enriched_state = {
            "current_actor_id": "hero-001",
            "combatants": [
                {
                    "id": "hero-001",
                    "name": "Thorin",
                    "player_id": "111111111111111111",  # different from clicker
                    "hp_current": 50,
                    "hp_max": 50,
                    "ac": 18,
                    "conditions": [],
                }
            ],
            "round_number": 1,
            "in_combat": True,
        }
        with patch.object(btn, "_get_enriched_game_state", AsyncMock(return_value=enriched_state)):
            with patch("eldritch_dm.bot.dynamic_items.mcp_tools") as mock_tools:
                mock_tools.next_turn = AsyncMock(return_value={})
                with patch("eldritch_dm.bot.dynamic_items.send_warning", new_callable=AsyncMock) as mock_warn:
                    await btn.callback(interaction)
                    # NOT_YOUR_TURN warning should be sent
                    mock_warn.assert_called_once()
                    warn_kind = mock_warn.call_args[0][1]
                    from eldritch_dm.bot.warnings import WarningKind
                    assert warn_kind == WarningKind.NOT_YOUR_TURN
                    # next_turn should NOT have been called
                    mock_tools.next_turn.assert_not_called()


# ── Test 5: Monster turn → all player clicks rejected ────────────────────────

class TestMonsterTurnGatekeeper:
    @pytest.mark.asyncio
    async def test_attack_rejected_on_monster_turn(self) -> None:
        """Any player click on AttackButton during monster turn gets NOT_YOUR_TURN."""
        btn = AttackButton(channel_id=123, actor_id="monster-001", round_n=2)
        interaction = _make_interaction(user_id="111111111111111111")
        session = _make_session(state="COMBAT")
        interaction.client.channel_sessions.get = AsyncMock(return_value=session)

        # Monster turn: player_id is None
        enriched_state = {
            "current_actor_id": "monster-001",
            "combatants": [
                {
                    "id": "monster-001",
                    "name": "Goblin King",
                    "player_id": None,  # monster
                    "hp_current": 40,
                    "hp_max": 60,
                    "ac": 14,
                    "conditions": [],
                }
            ],
            "round_number": 2,
            "in_combat": True,
        }
        with patch.object(btn, "_get_enriched_game_state", AsyncMock(return_value=enriched_state)):
            with patch("eldritch_dm.bot.dynamic_items.mcp_tools") as mock_tools:
                mock_tools.combat_action = AsyncMock()
                with patch("eldritch_dm.bot.dynamic_items.send_warning", new_callable=AsyncMock) as mock_warn:
                    await btn.callback(interaction)
                    mock_warn.assert_called_once()
                    warn_kind = mock_warn.call_args[0][1]
                    from eldritch_dm.bot.warnings import WarningKind
                    assert warn_kind == WarningKind.NOT_YOUR_TURN
                    mock_tools.combat_action.assert_not_called()


# ── Test 6: Stale round → INVALID_ACTION ─────────────────────────────────────

class TestStaleRoundDetection:
    @pytest.mark.asyncio
    async def test_stale_round_endturn_returns_invalid_action(self) -> None:
        """EndTurnButton with stale round sends INVALID_ACTION."""
        # round_n=1 in custom_id but current round is 3
        btn = EndTurnButton(channel_id=123, actor_id="hero-001", round_n=1)
        interaction = _make_interaction(user_id="111111111111111111")
        session = _make_session(state="COMBAT")
        interaction.client.channel_sessions.get = AsyncMock(return_value=session)

        enriched_state = {
            "current_actor_id": "hero-001",
            "combatants": [
                {
                    "id": "hero-001",
                    "name": "Thorin",
                    "player_id": "111111111111111111",
                    "hp_current": 50,
                    "hp_max": 50,
                    "ac": 18,
                    "conditions": [],
                }
            ],
            "round_number": 3,  # different from round_n=1 in button
            "in_combat": True,
        }
        with patch.object(btn, "_get_enriched_game_state", AsyncMock(return_value=enriched_state)):
            with patch("eldritch_dm.bot.dynamic_items.send_warning", new_callable=AsyncMock) as mock_warn:
                with patch("eldritch_dm.bot.dynamic_items.mcp_tools") as mock_tools:
                    mock_tools.next_turn = AsyncMock()
                    await btn.callback(interaction)
                    mock_warn.assert_called_once()
                    warn_kind = mock_warn.call_args[0][1]
                    from eldritch_dm.bot.warnings import WarningKind
                    assert warn_kind == WarningKind.INVALID_ACTION
                    mock_tools.next_turn.assert_not_called()


# ── Test 9/11: DodgeButton active path ───────────────────────────────────────

class TestDodgeButtonCallback:
    @pytest.mark.asyncio
    async def test_dodge_active_actor_calls_apply_effect_and_next_turn(self) -> None:
        """Active actor clicking DodgeButton: apply_effect + next_turn called."""
        btn = DodgeButton(channel_id=123, actor_id="hero-001", round_n=2)
        interaction = _make_interaction(user_id="111111111111111111")
        session = _make_session(state="COMBAT")
        interaction.client.channel_sessions.get = AsyncMock(return_value=session)

        enriched_state = {
            "current_actor_id": "hero-001",
            "combatants": [
                {
                    "id": "hero-001",
                    "name": "Thorin",
                    "player_id": "111111111111111111",
                    "hp_current": 50,
                    "hp_max": 50,
                    "ac": 18,
                    "conditions": [],
                }
            ],
            "round_number": 2,
            "in_combat": True,
        }
        with patch.object(btn, "_get_enriched_game_state", AsyncMock(return_value=enriched_state)):
            with patch("eldritch_dm.bot.dynamic_items.mcp_tools") as mock_tools:
                mock_tools.apply_effect = AsyncMock(return_value={})
                mock_tools.next_turn = AsyncMock(return_value={})
                with patch("eldritch_dm.bot.dynamic_items.CombatConditionsRepo") as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.insert = AsyncMock(return_value=1)
                    mock_repo_cls.return_value = mock_repo
                    await btn.callback(interaction)
                    # apply_effect must be called with target=actor_id, effect="dodging"
                    mock_tools.apply_effect.assert_called_once()
                    call_kwargs = mock_tools.apply_effect.call_args[1]
                    assert call_kwargs["target"] == "hero-001"
                    assert call_kwargs["effect"] == "dodging"
                    # next_turn must be called
                    mock_tools.next_turn.assert_called_once()

    @pytest.mark.asyncio
    async def test_dodge_not_active_actor_warns(self) -> None:
        """Non-active actor clicking DodgeButton gets NOT_YOUR_TURN."""
        btn = DodgeButton(channel_id=123, actor_id="hero-001", round_n=2)
        interaction = _make_interaction(user_id="999999999999999999")
        session = _make_session(state="COMBAT")
        interaction.client.channel_sessions.get = AsyncMock(return_value=session)

        enriched_state = {
            "current_actor_id": "hero-001",
            "combatants": [
                {
                    "id": "hero-001",
                    "name": "Thorin",
                    "player_id": "111111111111111111",
                    "hp_current": 50,
                    "hp_max": 50,
                    "ac": 18,
                    "conditions": [],
                }
            ],
            "round_number": 2,
            "in_combat": True,
        }
        with patch.object(btn, "_get_enriched_game_state", AsyncMock(return_value=enriched_state)):
            with patch("eldritch_dm.bot.dynamic_items.mcp_tools") as mock_tools:
                mock_tools.apply_effect = AsyncMock()
                mock_tools.next_turn = AsyncMock()
                with patch("eldritch_dm.bot.dynamic_items.send_warning", new_callable=AsyncMock) as mock_warn:
                    await btn.callback(interaction)
                    mock_warn.assert_called_once()
                    from eldritch_dm.bot.warnings import WarningKind
                    assert mock_warn.call_args[0][1] == WarningKind.NOT_YOUR_TURN
                    mock_tools.apply_effect.assert_not_called()
                    mock_tools.next_turn.assert_not_called()

    @pytest.mark.asyncio
    async def test_dodge_writes_combat_conditions_row(self) -> None:
        """DodgeButton active path inserts a combat_conditions row (T-04-16)."""
        btn = DodgeButton(channel_id=123, actor_id="hero-001", round_n=2)
        interaction = _make_interaction(user_id="111111111111111111")
        session = _make_session(state="COMBAT")
        interaction.client.channel_sessions.get = AsyncMock(return_value=session)

        enriched_state = {
            "current_actor_id": "hero-001",
            "combatants": [
                {
                    "id": "hero-001",
                    "name": "Thorin",
                    "player_id": "111111111111111111",
                    "hp_current": 50,
                    "hp_max": 50,
                    "ac": 18,
                    "conditions": [],
                }
            ],
            "round_number": 2,
            "in_combat": True,
        }
        with patch.object(btn, "_get_enriched_game_state", AsyncMock(return_value=enriched_state)):
            with patch("eldritch_dm.bot.dynamic_items.mcp_tools") as mock_tools:
                mock_tools.apply_effect = AsyncMock(return_value={})
                mock_tools.next_turn = AsyncMock(return_value={})
                with patch("eldritch_dm.bot.dynamic_items.CombatConditionsRepo") as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.insert = AsyncMock(return_value=1)
                    mock_repo_cls.return_value = mock_repo
                    await btn.callback(interaction)
                    # Repo.insert should have been called with dodging condition
                    mock_repo.insert.assert_called_once()
                    insert_kwargs = mock_repo.insert.call_args[1]
                    assert insert_kwargs.get("condition_kind") == "dodging"
                    assert insert_kwargs.get("character_id") == "hero-001"


# ── Test 15-16: CastSpellButton stub ─────────────────────────────────────────

class TestCastSpellButtonStub:
    @pytest.mark.asyncio
    async def test_cast_spell_returns_v2_message_for_active_actor(self) -> None:
        """CastSpell stub sends v2 message to active actor."""
        btn = CastSpellButton(channel_id=123, actor_id="wizard-001", round_n=1)
        interaction = _make_interaction(user_id="111111111111111111")
        session = _make_session(state="COMBAT")
        interaction.client.channel_sessions.get = AsyncMock(return_value=session)

        enriched_state = {
            "current_actor_id": "wizard-001",
            "combatants": [
                {
                    "id": "wizard-001",
                    "name": "Wizard",
                    "player_id": "111111111111111111",
                    "hp_current": 30,
                    "hp_max": 30,
                    "ac": 12,
                    "conditions": [],
                }
            ],
            "round_number": 1,
            "in_combat": True,
        }
        with patch.object(btn, "_get_enriched_game_state", AsyncMock(return_value=enriched_state)):
            await btn.callback(interaction)
            interaction.followup.send.assert_called_once()
            msg_content = interaction.followup.send.call_args[1].get("content", "") or str(
                interaction.followup.send.call_args[0]
            )
            assert "v2" in msg_content.lower() or "spell" in msg_content.lower()

    @pytest.mark.asyncio
    async def test_cast_spell_rejects_non_active_actor(self) -> None:
        """CastSpell stub still gates on is_actor (non-active player rejected)."""
        btn = CastSpellButton(channel_id=123, actor_id="wizard-001", round_n=1)
        interaction = _make_interaction(user_id="999999999999999999")  # different user
        session = _make_session(state="COMBAT")
        interaction.client.channel_sessions.get = AsyncMock(return_value=session)

        enriched_state = {
            "current_actor_id": "wizard-001",
            "combatants": [
                {
                    "id": "wizard-001",
                    "name": "Wizard",
                    "player_id": "111111111111111111",
                    "hp_current": 30,
                    "hp_max": 30,
                    "ac": 12,
                    "conditions": [],
                }
            ],
            "round_number": 1,
            "in_combat": True,
        }
        with patch.object(btn, "_get_enriched_game_state", AsyncMock(return_value=enriched_state)):
            with patch("eldritch_dm.bot.dynamic_items.send_warning", new_callable=AsyncMock) as mock_warn:
                await btn.callback(interaction)
                mock_warn.assert_called_once()
                from eldritch_dm.bot.warnings import WarningKind
                assert mock_warn.call_args[0][1] == WarningKind.NOT_YOUR_TURN


# ── Rate limiter not called on rejected clicks ────────────────────────────────

class TestRateLimiterNotCalledOnRejection:
    @pytest.mark.asyncio
    async def test_rate_limiter_not_acquired_on_not_your_turn(self) -> None:
        """NOT_YOUR_TURN rejection must NOT acquire the rate limiter (T-04-13)."""
        btn = EndTurnButton(channel_id=123, actor_id="hero-001", round_n=1)
        interaction = _make_interaction(user_id="999999999999999999")
        session = _make_session(state="COMBAT")
        interaction.client.channel_sessions.get = AsyncMock(return_value=session)

        enriched_state = {
            "current_actor_id": "hero-001",
            "combatants": [
                {
                    "id": "hero-001",
                    "name": "Thorin",
                    "player_id": "111111111111111111",
                    "hp_current": 50,
                    "hp_max": 50,
                    "ac": 18,
                    "conditions": [],
                }
            ],
            "round_number": 1,
            "in_combat": True,
        }
        with patch.object(btn, "_get_enriched_game_state", AsyncMock(return_value=enriched_state)):
            with patch("eldritch_dm.bot.dynamic_items.send_warning", new_callable=AsyncMock):
                with patch("eldritch_dm.bot.dynamic_items.mcp_tools"):
                    await btn.callback(interaction)
                    # Rate limiter NOT acquired
                    interaction.client.rate_limiter.acquire.assert_not_called()
