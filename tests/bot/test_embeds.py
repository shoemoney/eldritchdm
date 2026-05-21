"""
Tests for eldritch_dm.bot.embeds — pure-function embed renderers.

Strategy: hand-rolled dict comparison against JSON fixture files.
Timestamps are scrubbed from comparison dicts since they vary per call.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import discord
import pytest

from eldritch_dm.bot.embeds import (
    EmbedColor,
    PlayerStatus,
    _FOOTER_TEXT,
    character_confirm_embed,
    combat_embed,
    lobby_embed,
    room_embed,
)

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


def _scrub_ts(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively replace 'timestamp' values with '<TIMESTAMP>' for stable comparison."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if k == "timestamp":
            out[k] = "<TIMESTAMP>"
        elif isinstance(v, dict):
            out[k] = _scrub_ts(v)
        elif isinstance(v, list):
            out[k] = [_scrub_ts(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


# ── Sample data fixtures ───────────────────────────────────────────────────────

PLAYERS_4 = [
    PlayerStatus(display_name="Alice", ready=True, character_name="Aria Swiftfoot"),
    PlayerStatus(display_name="Bob", ready=True, character_name="Brog the Mighty"),
    PlayerStatus(display_name="Carol", ready=False, character_name="Celeste Vex"),
    PlayerStatus(display_name="Dave", ready=False, character_name=None),
]

PARTY_HP = [
    ("Alice", 42, 50),
    ("Bob", 30, 30),
    ("Carol", 18, 45),
    ("Dave", 8, 12),
]

INITIATIVE_5 = [
    ("Thorin", 20, 55, 55, []),
    ("Goblin King", 18, 40, 60, ["stunned"]),
    ("Aria", 15, 42, 50, []),
    ("Brog", 12, 30, 30, ["poisoned", "exhausted"]),
    ("Cave Troll", 5, 80, 120, ["frightened"]),
]

SAMPLE_CHARACTER = {
    "name": "Aria Swiftfoot",
    "race": "Wood Elf",
    "class": "Ranger",
    "level": 5,
    "ability_scores": {
        "strength": 12,
        "dexterity": 18,
        "constitution": 14,
        "intelligence": 11,
        "wisdom": 15,
        "charisma": 10,
    },
    "hp": {"current": 42, "max": 50},
    "ac": 16,
    # Extra fields that should NOT appear in the embed
    "background": "Outlander",
    "alignment": "Neutral Good",
    "proficiency_bonus": 3,
}


class TestLobbyEmbedSnapshot:
    def test_lobby_embed_snapshot(self) -> None:
        """lobby_embed output matches fixture (4 players, 2 ready, with invite link)."""
        embed = lobby_embed(
            campaign_name="Lost Mines of Phandelver",
            players=PLAYERS_4,
            party_invite="https://dm20.local/party/abc",
        )
        result = _scrub_ts(embed.to_dict())
        fixture_path = FIXTURE_DIR / "embed_lobby.json"
        if not fixture_path.exists():
            fixture_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            pytest.skip("Wrote fixture baseline — re-run to compare")
        expected = json.loads(fixture_path.read_text())
        assert result == expected

    def test_lobby_embed_no_invite(self) -> None:
        """lobby_embed with party_invite=None produces no 'Join Party Mode' field."""
        embed = lobby_embed(
            campaign_name="Lost Mines",
            players=PLAYERS_4[:2],
            party_invite=None,
        )
        field_names = [f.name for f in embed.fields]
        assert "Join Party Mode" not in field_names


class TestRoomEmbedSnapshot:
    def test_room_embed_snapshot(self) -> None:
        """room_embed output matches fixture."""
        embed = room_embed(
            room_title="The Goblin Lair",
            narration=(
                "You descend into the musty cavern. Torchlight flickers off damp stone walls. "
                "The scent of goblin musk hangs heavy in the air. You hear distant chanting."
            ),
            party_hp=PARTY_HP,
        )
        result = _scrub_ts(embed.to_dict())
        fixture_path = FIXTURE_DIR / "embed_room.json"
        if not fixture_path.exists():
            fixture_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            pytest.skip("Wrote fixture baseline — re-run to compare")
        expected = json.loads(fixture_path.read_text())
        assert result == expected


class TestCombatEmbedSnapshot:
    def test_combat_embed_snapshot(self) -> None:
        """combat_embed round 3, 5-actor initiative list, matches fixture."""
        embed = combat_embed(
            round_n=3,
            current_actor="Thorin",
            initiative=INITIATIVE_5,
        )
        result = _scrub_ts(embed.to_dict())
        fixture_path = FIXTURE_DIR / "embed_combat.json"
        if not fixture_path.exists():
            fixture_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            pytest.skip("Wrote fixture baseline — re-run to compare")
        expected = json.loads(fixture_path.read_text())
        assert result == expected


class TestCharacterConfirmEmbedSnapshot:
    def test_character_confirm_embed_snapshot(self) -> None:
        """character_confirm_embed for a sample character dict matches fixture."""
        embed = character_confirm_embed(
            player_name="Alice",
            character=SAMPLE_CHARACTER,
        )
        result = _scrub_ts(embed.to_dict())
        fixture_path = FIXTURE_DIR / "embed_character_confirm.json"
        if not fixture_path.exists():
            fixture_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            pytest.skip("Wrote fixture baseline — re-run to compare")
        expected = json.loads(fixture_path.read_text())
        assert result == expected


# ── Phase 3: server_url extension ────────────────────────────────────────────


class TestLobbyEmbedServerUrl:
    """Phase 3: lobby_embed accepts optional server_url kwarg."""

    def test_lobby_embed_with_server_url_shows_field(self) -> None:
        """When server_url is provided, a 'Party Mode server' field appears."""
        embed = lobby_embed(
            campaign_name="TestCamp",
            players=[],
            server_url="http://192.168.1.5:8080",
        )
        field_names = [f.name for f in embed.fields]
        assert "Party Mode Server" in field_names

    def test_lobby_embed_server_url_value_in_field(self) -> None:
        """The Party Mode Server field contains the provided URL."""
        url = "http://192.168.1.5:8080"
        embed = lobby_embed(
            campaign_name="TestCamp",
            players=[],
            server_url=url,
        )
        server_fields = [f for f in embed.fields if f.name == "Party Mode Server"]
        assert len(server_fields) == 1
        assert url in server_fields[0].value

    def test_lobby_embed_no_server_url_no_field(self) -> None:
        """When server_url is None (default), no 'Party Mode Server' field is added."""
        embed = lobby_embed(campaign_name="TestCamp", players=[])
        field_names = [f.name for f in embed.fields]
        assert "Party Mode Server" not in field_names

    def test_lobby_embed_backward_compat_party_invite_still_works(self) -> None:
        """Existing callers using party_invite= still work (no regression)."""
        embed = lobby_embed(
            campaign_name="TestCamp",
            players=[],
            party_invite="https://example.com/join",
        )
        field_names = [f.name for f in embed.fields]
        assert "Join Party Mode" in field_names

    def test_lobby_embed_transitioning_description(self) -> None:
        """Transitioning state produces exploration copy in description area."""
        player = PlayerStatus(display_name="Alice", ready=True, character_name="Aria")
        embed = lobby_embed(
            campaign_name="TestCamp",
            players=[player],
            transition_state="transitioning",
        )
        assert "EXPLORATION" in embed.description or "All ready" in embed.description

    def test_lobby_embed_exploration_description(self) -> None:
        """Exploration state produces green copy."""
        embed = lobby_embed(
            campaign_name="TestCamp",
            players=[],
            transition_state="exploration",
        )
        assert "EXPLORATION" in embed.description


class TestEmbedColorAndFooter:
    @pytest.mark.parametrize(
        "fn, kwargs, expected_color",
        [
            (
                lobby_embed,
                {"campaign_name": "X", "players": []},
                EmbedColor.LOBBY,
            ),
            (
                room_embed,
                {"room_title": "R", "narration": "N", "party_hp": []},
                EmbedColor.EXPLORATION,
            ),
            (
                combat_embed,
                {"round_n": 1, "current_actor": "A", "initiative": []},
                EmbedColor.COMBAT,
            ),
            (
                character_confirm_embed,
                {
                    "player_name": "P",
                    "character": {
                        "name": "X", "race": "H", "class": "F", "level": 1,
                        "ability_scores": {}, "hp": {}, "ac": 10,
                    },
                },
                EmbedColor.CHARACTER_CONFIRM,
            ),
        ],
    )
    def test_embed_color(self, fn, kwargs, expected_color) -> None:
        embed = fn(**kwargs)
        assert embed.color.value == int(expected_color)

    @pytest.mark.parametrize(
        "fn, kwargs",
        [
            (lobby_embed, {"campaign_name": "X", "players": []}),
            (room_embed, {"room_title": "R", "narration": "N", "party_hp": []}),
            (combat_embed, {"round_n": 1, "current_actor": "A", "initiative": []}),
            (
                character_confirm_embed,
                {
                    "player_name": "P",
                    "character": {
                        "name": "X", "race": "H", "class": "F", "level": 1,
                        "ability_scores": {}, "hp": {}, "ac": 10,
                    },
                },
            ),
        ],
    )
    def test_footer_text(self, fn, kwargs) -> None:
        embed = fn(**kwargs)
        assert embed.footer.text == _FOOTER_TEXT
