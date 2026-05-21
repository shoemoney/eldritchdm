"""Unit tests for eldritch_dm.ingest.schema.

Tests:
  - AbilityScores: valid, out-of-range, extra field rejected
  - CharacterSheet: valid minimal, valid full, missing required, name length,
                    class_level bounds, extra fields ignored
  - IngestResult: dataclass frozen, default fields
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from eldritch_dm.ingest.schema import AbilityScores, CharacterSheet, IngestResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_ABILITIES = {
    "strength": 16,
    "dexterity": 14,
    "constitution": 15,
    "intelligence": 10,
    "wisdom": 12,
    "charisma": 8,
}


def make_sheet(**overrides):  # type: ignore[override]
    """Return a minimal valid CharacterSheet dict, with optional overrides."""
    base = {
        "name": "Thalindra",
        "character_class": "Wizard",
        "class_level": 5,
        "race": "High Elf",
        "abilities": VALID_ABILITIES,
    }
    base.update(overrides)
    return CharacterSheet(**base)


# ---------------------------------------------------------------------------
# AbilityScores tests
# ---------------------------------------------------------------------------


class TestAbilityScores:
    def test_valid_scores(self):
        scores = AbilityScores(**VALID_ABILITIES)
        assert scores.strength == 16
        assert scores.charisma == 8

    def test_minimum_values_allowed(self):
        scores = AbilityScores(
            strength=1, dexterity=1, constitution=1,
            intelligence=1, wisdom=1, charisma=1,
        )
        assert scores.strength == 1

    def test_maximum_values_allowed(self):
        scores = AbilityScores(
            strength=30, dexterity=30, constitution=30,
            intelligence=30, wisdom=30, charisma=30,
        )
        assert scores.strength == 30

    def test_below_minimum_raises(self):
        bad = dict(VALID_ABILITIES)
        bad["strength"] = 0
        with pytest.raises(ValidationError):
            AbilityScores(**bad)

    def test_above_maximum_raises(self):
        bad = dict(VALID_ABILITIES)
        bad["dexterity"] = 31
        with pytest.raises(ValidationError):
            AbilityScores(**bad)

    def test_extra_field_rejected(self):
        """extra='forbid' must reject unknown fields."""
        with pytest.raises(ValidationError):
            AbilityScores(**VALID_ABILITIES, luck=99)  # type: ignore[call-arg]

    def test_frozen(self):
        """Frozen model must not allow mutation."""
        scores = AbilityScores(**VALID_ABILITIES)
        with pytest.raises(Exception):  # ValidationError or TypeError
            scores.strength = 20  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CharacterSheet tests
# ---------------------------------------------------------------------------


class TestCharacterSheet:
    def test_valid_minimal(self):
        sheet = make_sheet()
        assert sheet.name == "Thalindra"
        assert sheet.character_class == "Wizard"
        assert sheet.class_level == 5
        assert sheet.abilities.strength == 16
        # Optional fields default to None/empty
        assert sheet.hp is None
        assert sheet.skills == []

    def test_valid_full(self):
        sheet = CharacterSheet(
            name="Brak Stonefist",
            character_class="Fighter",
            class_level=10,
            race="Mountain Dwarf",
            subclass="Battle Master",
            subrace="Shield Dwarf",
            background="Soldier",
            alignment="Lawful Good",
            abilities=VALID_ABILITIES,
            hp=92,
            ac=18,
            skills=["Athletics", "Intimidation"],
            weapons=[{"name": "Battleaxe", "damage": "1d8"}],
            spells=[],
        )
        assert sheet.hp == 92
        assert sheet.ac == 18
        assert sheet.subclass == "Battle Master"

    def test_missing_required_name_raises(self):
        with pytest.raises(ValidationError):
            CharacterSheet(
                character_class="Rogue",
                class_level=3,
                race="Halfling",
                abilities=VALID_ABILITIES,
            )  # type: ignore[call-arg]

    def test_name_too_long_raises(self):
        with pytest.raises(ValidationError):
            make_sheet(name="A" * 81)

    def test_name_empty_raises(self):
        with pytest.raises(ValidationError):
            make_sheet(name="")

    def test_class_level_too_high_raises(self):
        with pytest.raises(ValidationError):
            make_sheet(class_level=21)

    def test_class_level_zero_raises(self):
        with pytest.raises(ValidationError):
            make_sheet(class_level=0)

    def test_extra_fields_ignored(self):
        """extra='ignore' must silently drop unknown fields."""
        sheet = CharacterSheet(
            name="Elf",
            character_class="Druid",
            class_level=1,
            race="Wood Elf",
            abilities=VALID_ABILITIES,
            completely_made_up_field="yes",  # type: ignore[call-arg]
        )
        assert sheet.name == "Elf"
        assert not hasattr(sheet, "completely_made_up_field")

    def test_hp_must_be_positive(self):
        with pytest.raises(ValidationError):
            make_sheet(hp=0)

    def test_ac_must_be_positive(self):
        with pytest.raises(ValidationError):
            make_sheet(ac=0)

    def test_frozen(self):
        sheet = make_sheet()
        with pytest.raises(Exception):
            sheet.name = "Mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IngestResult tests
# ---------------------------------------------------------------------------


class TestIngestResult:
    def test_defaults(self):
        result = IngestResult(
            raw_text="some text",
            parsed_sheet=None,
            confidence_score=0.0,
        )
        assert result.validation_warnings == []
        assert result.ocr_backend is None
        assert result.pdf_backend is None

    def test_with_sheet(self):
        sheet = make_sheet()
        result = IngestResult(
            raw_text="raw",
            parsed_sheet=sheet,
            confidence_score=0.9,
            ocr_backend="ocrmac",
        )
        assert result.parsed_sheet is sheet
        assert result.confidence_score == 0.9
        assert result.ocr_backend == "ocrmac"

    def test_frozen_dataclass(self):
        result = IngestResult(
            raw_text="raw",
            parsed_sheet=None,
            confidence_score=0.5,
        )
        with pytest.raises(Exception):
            result.raw_text = "modified"  # type: ignore[misc]

    def test_mutable_list_fields_independent(self):
        """Each IngestResult instance gets its own list — not shared via default_factory."""
        r1 = IngestResult(raw_text="a", parsed_sheet=None, confidence_score=0.1)
        r2 = IngestResult(raw_text="b", parsed_sheet=None, confidence_score=0.2)
        # IngestResult is frozen — can't append; just verify they're separate objects
        assert r1.validation_warnings is not r2.validation_warnings
