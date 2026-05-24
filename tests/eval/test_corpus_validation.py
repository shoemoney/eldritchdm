"""Corpus loads + validates against the schema (T-12-02-07, T-12-02-08)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from eldritch_dm.eval.scenarios import load_scenarios

CORPUS_PATH = Path(__file__).parent / "dataset" / "tactical_corpus.jsonl"
EXPECTED_ARCHETYPES = {"brute", "spellcaster", "swarm", "predator", "edge_case"}
EXPECTED_TOTAL = 50
EXPECTED_PER_ARCHETYPE = 10


def test_corpus_loads_and_validates() -> None:
    scenarios = load_scenarios(CORPUS_PATH)
    assert len(scenarios) == EXPECTED_TOTAL, (
        f"expected {EXPECTED_TOTAL} scenarios, got {len(scenarios)}"
    )


def test_archetype_balance() -> None:
    scenarios = load_scenarios(CORPUS_PATH)
    counts = Counter(s.archetype for s in scenarios)
    assert set(counts.keys()) == EXPECTED_ARCHETYPES
    for arch in EXPECTED_ARCHETYPES:
        assert counts[arch] == EXPECTED_PER_ARCHETYPE, (
            f"archetype {arch!r}: expected {EXPECTED_PER_ARCHETYPE}, "
            f"got {counts[arch]}"
        )


def test_scenario_ids_unique() -> None:
    scenarios = load_scenarios(CORPUS_PATH)
    ids = [s.scenario_id for s in scenarios]
    assert len(ids) == len(set(ids)), "scenario_ids must be unique"


def test_each_scenario_has_substantive_rationale() -> None:
    scenarios = load_scenarios(CORPUS_PATH)
    for s in scenarios:
        assert len(s.rationale) >= 10, (
            f"{s.scenario_id}: rationale too short"
        )


def test_license_file_present() -> None:
    license_path = CORPUS_PATH.parent / "LICENSE.md"
    assert license_path.is_file()
    text = license_path.read_text()
    assert "Apache" in text
    assert "Original content" in text or "original content" in text
