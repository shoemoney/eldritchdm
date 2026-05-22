"""
Tests for eldritch_dm.gameplay.turn_gatekeeper — pure dict-shape helpers.

Tests:
  1. is_actor returns True when user_id matches actor.player_id
  2. is_actor returns False when user_id does NOT match actor.player_id
  3. is_actor returns False when actor.player_id is None (monster turn)
  4. player_id_for_actor returns str(actor["player_id"]) or None
  5. current_actor_from_game_state returns the matching actor dict
  6. 8-actor gatekeeper matrix — 64 (current_actor_idx, clicker_idx) combos

Phase 4 Plan 02.
"""

from __future__ import annotations

import pytest

from eldritch_dm.gameplay.turn_gatekeeper import (
    current_actor_from_game_state,
    is_actor,
    player_id_for_actor,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────

# Minimal valid actor dict shape (all fields documented in turn_gatekeeper.py)
ACTOR_THORIN = {
    "id": "abc-001",
    "name": "Thorin",
    "player_id": "111111111111111111",  # Discord snowflake as string
    "hp_current": 55,
    "hp_max": 55,
    "ac": 18,
    "conditions": [],
}

ACTOR_GOBLIN = {
    "id": "monster-001",
    "name": "Goblin King",
    "player_id": None,  # monster — no Discord player
    "hp_current": 40,
    "hp_max": 60,
    "ac": 14,
    "conditions": ["stunned"],
}

ACTOR_ARIA = {
    "id": "abc-002",
    "name": "Aria",
    "player_id": "222222222222222222",
    "hp_current": 42,
    "hp_max": 50,
    "ac": 15,
    "conditions": [],
}


# ── Test 1: is_actor returns True when user_id matches player_id ─────────────


class TestIsActor:
    def test_matching_player_id_returns_true(self) -> None:
        """is_actor(user_id, actor) is True when user_id == actor.player_id."""
        assert is_actor("111111111111111111", ACTOR_THORIN) is True

    def test_matching_str_coercion_returns_true(self) -> None:
        """is_actor coerces both sides to str before comparing."""
        actor = {**ACTOR_THORIN, "player_id": 111111111111111111}
        assert is_actor("111111111111111111", actor) is True

    # ── Test 2: non-matching ──────────────────────────────────────────────

    def test_non_matching_player_id_returns_false(self) -> None:
        """is_actor returns False when user_id != actor.player_id."""
        assert is_actor("999999999999999999", ACTOR_THORIN) is False

    def test_aria_user_cannot_act_as_thorin(self) -> None:
        """Aria's player_id cannot impersonate Thorin's turn."""
        assert is_actor(ACTOR_ARIA["player_id"], ACTOR_THORIN) is False  # type: ignore[arg-type]

    # ── Test 3: None player_id (monster) always False ─────────────────────

    def test_monster_player_id_none_returns_false(self) -> None:
        """is_actor returns False when actor.player_id is None (monster turn)."""
        assert is_actor("111111111111111111", ACTOR_GOBLIN) is False

    def test_any_user_rejected_on_monster_turn(self) -> None:
        """Any player clicking during a monster turn gets rejected."""
        for uid in ["111", "222", "999", "0"]:
            assert is_actor(uid, ACTOR_GOBLIN) is False


# ── Test 4: player_id_for_actor ──────────────────────────────────────────────


class TestPlayerIdForActor:
    def test_returns_str_player_id(self) -> None:
        """player_id_for_actor returns str version of actor["player_id"]."""
        result = player_id_for_actor(ACTOR_THORIN)
        assert result == "111111111111111111"
        assert isinstance(result, str)

    def test_returns_none_for_monster(self) -> None:
        """player_id_for_actor returns None when actor.player_id is None."""
        result = player_id_for_actor(ACTOR_GOBLIN)
        assert result is None

    def test_coerces_int_to_str(self) -> None:
        """player_id_for_actor converts int player_id to str."""
        actor = {**ACTOR_THORIN, "player_id": 111111111111111111}
        assert player_id_for_actor(actor) == "111111111111111111"

    def test_missing_key_returns_none(self) -> None:
        """player_id_for_actor returns None if 'player_id' key is absent."""
        assert player_id_for_actor({}) is None


# ── Test 5: current_actor_from_game_state ────────────────────────────────────


# game_state shape from dm20 parsed output:
# {
#   "current_actor_id": str | None,  -- maps to combatant["id"]
#   "combatants": list[dict],        -- each dict has "id", "name", etc.
# }

SAMPLE_GAME_STATE = {
    "current_actor_id": "abc-001",
    "combatants": [ACTOR_THORIN, ACTOR_GOBLIN, ACTOR_ARIA],
    "round_number": 2,
    "in_combat": True,
}


class TestCurrentActorFromGameState:
    def test_returns_matching_combatant(self) -> None:
        """Returns the combatant dict whose id == current_actor_id."""
        result = current_actor_from_game_state(SAMPLE_GAME_STATE)
        assert result is not None
        assert result["id"] == "abc-001"
        assert result["name"] == "Thorin"

    def test_returns_none_when_current_actor_id_absent(self) -> None:
        """Returns None if current_actor_id is None."""
        state = {**SAMPLE_GAME_STATE, "current_actor_id": None}
        assert current_actor_from_game_state(state) is None

    def test_returns_none_when_combatants_empty(self) -> None:
        """Returns None if combatants list is empty."""
        state = {**SAMPLE_GAME_STATE, "combatants": []}
        assert current_actor_from_game_state(state) is None

    def test_returns_none_when_id_not_found(self) -> None:
        """Returns None if current_actor_id does not match any combatant."""
        state = {**SAMPLE_GAME_STATE, "current_actor_id": "nonexistent-id"}
        assert current_actor_from_game_state(state) is None

    def test_returns_none_for_empty_game_state(self) -> None:
        """Returns None when game_state dict is empty."""
        assert current_actor_from_game_state({}) is None


# ── Test 6: 8-actor gatekeeper matrix (64 combos) ────────────────────────────

# Build a synthetic game state with 4 PCs + 4 monsters.
_PC_ACTORS = [
    {
        "id": f"pc-{i:03d}",
        "name": f"Hero{i}",
        "player_id": f"{100 + i:019d}",  # 19-digit zero-padded to simulate snowflake
        "hp_current": 50,
        "hp_max": 50,
        "ac": 14 + i,
        "conditions": [],
    }
    for i in range(1, 5)  # pc-001..pc-004
]

_MONSTER_ACTORS = [
    {
        "id": f"monster-{i:03d}",
        "name": f"Monster{i}",
        "player_id": None,
        "hp_current": 30,
        "hp_max": 30,
        "ac": 12,
        "conditions": [],
    }
    for i in range(1, 5)  # monster-001..monster-004
]

_ALL_8_ACTORS = _PC_ACTORS + _MONSTER_ACTORS  # 4 PCs then 4 monsters


def _expected_is_actor(clicker_user_id: str, current_actor: dict) -> bool:
    """Reference implementation: True only if player_id matches and is not None."""
    pid = current_actor.get("player_id")
    if pid is None:
        return False
    return str(clicker_user_id) == str(pid)


# Generate all 64 (current_actor_idx, clicker_idx) pairs.
# clicker_user_id is derived from the "clicker" actor's player_id if they're a PC,
# or a dummy ID "000000000000000000" if they're a monster.
@pytest.mark.parametrize(
    "current_actor_idx,clicker_idx",
    [(ca_idx, cl_idx) for ca_idx in range(8) for cl_idx in range(8)],
)
class TestGatekeeperMatrix:
    def test_is_actor_64_combos(
        self, current_actor_idx: int, clicker_idx: int
    ) -> None:
        """For each (current_actor, clicker) pair, is_actor matches reference impl.

        8 current actors × 8 clickers = 64 combinations.
        PC clickers use their player_id; monster clickers use dummy snowflake.
        """
        current_actor = _ALL_8_ACTORS[current_actor_idx]
        clicker_actor = _ALL_8_ACTORS[clicker_idx]

        # Determine what user_id the clicker would present to the interaction
        if clicker_actor["player_id"] is not None:
            clicker_user_id = str(clicker_actor["player_id"])
        else:
            # Monsters don't click; simulate an anonymous user_id
            clicker_user_id = f"monster-click-{clicker_idx:03d}"

        expected = _expected_is_actor(clicker_user_id, current_actor)
        result = is_actor(clicker_user_id, current_actor)

        assert result == expected, (
            f"FAIL: current_actor={current_actor['name']!r} (idx={current_actor_idx}), "
            f"clicker={clicker_actor['name']!r} (idx={clicker_idx}), "
            f"clicker_user_id={clicker_user_id!r}, "
            f"expected={expected}, got={result}"
        )
