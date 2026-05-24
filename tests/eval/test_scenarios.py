"""ScenarioEntry schema + load_scenarios tests (T-12-01-01)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eldritch_dm.eval.scenarios import (
    MonsterStats,
    PCEntry,
    ScenarioEntry,
    ScenarioLoadError,
    load_scenarios,
)


def _valid_payload(scenario_id: str = "brute-001") -> dict:
    return {
        "scenario_id": scenario_id,
        "archetype": "brute",
        "monster_stats": {
            "name": "Ogre",
            "intelligence": 5,
            "hp": 59,
            "ac": 11,
            "traits": ["brutish"],
        },
        "pc_list": [
            {
                "character_id": "pc-1",
                "name": "Aria",
                "hp_current": 30,
                "hp_max": 30,
                "ac": 16,
                "active_conditions": [],
            },
            {
                "character_id": "pc-2",
                "name": "Borin",
                "hp_current": 25,
                "hp_max": 25,
                "ac": 18,
                "active_conditions": [],
            },
        ],
        "environment": "dungeon corridor",
        "expected_target_pool": ["pc-2"],
        "expected_avoidance": [],
        "rationale": "Ogre INT 5 picks closest melee threat (Borin).",
    }


def test_scenario_entry_happy_path() -> None:
    entry = ScenarioEntry.model_validate(_valid_payload())
    assert entry.scenario_id == "brute-001"
    assert entry.archetype == "brute"
    assert isinstance(entry.monster_stats, MonsterStats)
    assert len(entry.pc_list) == 2
    assert isinstance(entry.pc_list[0], PCEntry)


def test_scenario_entry_rejects_unknown_archetype() -> None:
    payload = _valid_payload()
    payload["archetype"] = "wizard"
    with pytest.raises(ValidationError):
        ScenarioEntry.model_validate(payload)


def test_scenario_entry_rejects_short_pc_list() -> None:
    payload = _valid_payload()
    payload["pc_list"] = payload["pc_list"][:1]
    with pytest.raises(ValidationError):
        ScenarioEntry.model_validate(payload)


def test_scenario_entry_rejects_pc_list_too_long() -> None:
    payload = _valid_payload()
    extra = payload["pc_list"][0]
    payload["pc_list"] = [
        {**extra, "character_id": f"pc-{i}"} for i in range(9)
    ]
    with pytest.raises(ValidationError):
        ScenarioEntry.model_validate(payload)


def test_scenario_entry_rejects_intelligence_out_of_range() -> None:
    payload = _valid_payload()
    payload["monster_stats"]["intelligence"] = 99
    with pytest.raises(ValidationError):
        ScenarioEntry.model_validate(payload)


def test_scenario_entry_rejects_short_rationale() -> None:
    payload = _valid_payload()
    payload["rationale"] = "short"  # < 10 chars
    with pytest.raises(ValidationError):
        ScenarioEntry.model_validate(payload)


def test_scenario_entry_rejects_extra_fields() -> None:
    payload = _valid_payload()
    payload["surprise"] = "unexpected"
    with pytest.raises(ValidationError):
        ScenarioEntry.model_validate(payload)


def test_load_scenarios_happy_path(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    p1 = _valid_payload("brute-001")
    p2 = _valid_payload("spellcaster-001")
    p2["archetype"] = "spellcaster"
    p2["monster_stats"]["intelligence"] = 19
    corpus.write_text(json.dumps(p1) + "\n" + json.dumps(p2) + "\n")
    entries = load_scenarios(corpus)
    assert len(entries) == 2
    assert entries[0].scenario_id == "brute-001"
    assert entries[1].archetype == "spellcaster"


def test_load_scenarios_skips_blank_lines(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    p1 = _valid_payload("brute-001")
    corpus.write_text("\n\n" + json.dumps(p1) + "\n\n")
    entries = load_scenarios(corpus)
    assert len(entries) == 1


def test_load_scenarios_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ScenarioLoadError, match="not found"):
        load_scenarios(tmp_path / "nope.jsonl")


def test_load_scenarios_invalid_json_includes_line_number(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    p1 = _valid_payload("brute-001")
    corpus.write_text(json.dumps(p1) + "\n{not json\n")
    with pytest.raises(ScenarioLoadError, match="line 2"):
        load_scenarios(corpus)


def test_load_scenarios_schema_violation_includes_line_number(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    bad = _valid_payload("brute-001")
    bad["archetype"] = "not-an-archetype"
    corpus.write_text(json.dumps(bad) + "\n")
    with pytest.raises(ScenarioLoadError, match="line 1.*schema validation"):
        load_scenarios(corpus)
