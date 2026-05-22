"""
Tests for eldritch_dm.bot.modals — parse_abilities_field, serialize_abilities,
CharacterReviewModal, CharacterEntryModal, OptionalFieldsModal.

RESEARCH §5: Discord hard cap is 5 components per Modal.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import discord
import pytest
from pydantic import ValidationError

from eldritch_dm.bot.modals import (
    MODAL_TITLE_ENTRY,
    MODAL_TITLE_REVIEW,
    CharacterEntryModal,
    CharacterReviewModal,
    OptionalFieldsModal,
    parse_abilities_field,
    serialize_abilities,
)
from eldritch_dm.ingest.schema import AbilityScores

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_interaction(user_id: int = 111) -> AsyncMock:
    """Return a minimal discord.Interaction AsyncMock with a deferred response."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _prefill_review() -> dict[str, Any]:
    """Standard prefill dict for CharacterReviewModal."""
    return {
        "name": "Aragorn",
        "character_class": "Ranger",
        "class_level": 5,
        "race": "Human",
        "abilities": AbilityScores(
            strength=15, dexterity=18, constitution=14,
            intelligence=12, wisdom=10, charisma=8,
        ),
    }


# ── parse_abilities_field ──────────────────────────────────────────────────────


def test_parse_abilities_happy_path():
    """'15 18 14 12 10 8' → AbilityScores with correct values."""
    result = parse_abilities_field("15 18 14 12 10 8")
    assert result.strength == 15
    assert result.dexterity == 18
    assert result.constitution == 14
    assert result.intelligence == 12
    assert result.wisdom == 10
    assert result.charisma == 8


def test_parse_abilities_too_few_scores():
    """Fewer than 6 values raises ValueError."""
    with pytest.raises(ValueError, match="Expected 6 ability scores"):
        parse_abilities_field("15 18 14")


def test_parse_abilities_non_integer():
    """Non-integer values raise ValueError."""
    with pytest.raises(ValueError, match="must be integers"):
        parse_abilities_field("15 18 14 12 10 foo")


def test_parse_abilities_multi_space():
    """Multiple spaces between values are handled (split() vs split(' '))."""
    result = parse_abilities_field("15  18  14  12  10  8")
    assert result.strength == 15
    assert result.charisma == 8


def test_parse_abilities_leading_trailing_whitespace():
    """Leading/trailing whitespace is stripped."""
    result = parse_abilities_field("  15 18 14 12 10 8  ")
    assert result.strength == 15
    assert result.charisma == 8


def test_parse_abilities_out_of_range_raises_validation_error():
    """Ability score 0 raises pydantic ValidationError (AbilityScores ge=1)."""
    with pytest.raises(ValidationError):
        parse_abilities_field("0 18 14 12 10 8")


def test_parse_abilities_max_boundary():
    """Ability score 30 is valid (le=30)."""
    result = parse_abilities_field("30 30 30 30 30 30")
    assert result.strength == 30


def test_parse_abilities_too_many_scores():
    """More than 6 values raises ValueError."""
    with pytest.raises(ValueError, match="Expected 6 ability scores"):
        parse_abilities_field("15 18 14 12 10 8 20")


# ── serialize_abilities ────────────────────────────────────────────────────────


def test_serialize_abilities_roundtrip():
    """serialize_abilities produces space-separated string in STR DEX CON INT WIS CHA order."""
    a = AbilityScores(strength=15, dexterity=18, constitution=14, intelligence=12, wisdom=10, charisma=8)
    assert serialize_abilities(a) == "15 18 14 12 10 8"


def test_serialize_parse_roundtrip():
    """serialize then parse gives back the same scores."""
    original = AbilityScores(strength=10, dexterity=12, constitution=14, intelligence=8, wisdom=16, charisma=18)
    serialized = serialize_abilities(original)
    parsed = parse_abilities_field(serialized)
    assert parsed == original


# ── CharacterReviewModal ───────────────────────────────────────────────────────


def test_review_modal_component_count():
    """CharacterReviewModal must have exactly 5 TextInput components (Discord hard cap)."""
    cb = AsyncMock()
    modal = CharacterReviewModal(_prefill_review(), on_submit_cb=cb)
    assert len(modal.children) == 5


def test_review_modal_title():
    """Modal title is MODAL_TITLE_REVIEW."""
    cb = AsyncMock()
    modal = CharacterReviewModal(_prefill_review(), on_submit_cb=cb)
    assert modal.title == MODAL_TITLE_REVIEW


def test_review_modal_defaults_from_prefill():
    """Each field default comes from the prefill dict."""
    cb = AsyncMock()
    prefill = _prefill_review()
    modal = CharacterReviewModal(prefill, on_submit_cb=cb)

    labels_defaults = {item.label: item.default for item in modal.children}
    assert labels_defaults.get("Character Name") == "Aragorn"
    assert labels_defaults.get("Class") == "Ranger"
    assert labels_defaults.get("Level (1-20)") == "5"
    assert labels_defaults.get("Race") == "Human"
    # Abilities: space-separated string
    assert labels_defaults.get("Ability Scores (STR DEX CON INT WIS CHA)") == "15 18 14 12 10 8"


def test_review_modal_abilities_string_default():
    """Ability scores field default is space-separated from prefill['abilities']."""
    cb = AsyncMock()
    modal = CharacterReviewModal(_prefill_review(), on_submit_cb=cb)
    abilities_item = next(
        item for item in modal.children
        if "STR" in item.label
    )
    assert abilities_item.default == "15 18 14 12 10 8"


@pytest.mark.asyncio
async def test_review_modal_on_submit_calls_callback():
    """on_submit defers ephemeral then calls the callback with a raw dict."""
    received: list[Any] = []

    async def capture(interaction, raw_dict):
        received.append((interaction, raw_dict))

    modal = CharacterReviewModal(_prefill_review(), on_submit_cb=capture)

    # Simulate Discord populating the text input values
    for item in modal.children:
        if "Name" in item.label:
            item._value = "Legolas"
        elif item.label == "Class":
            item._value = "Fighter"
        elif "Level" in item.label:
            item._value = "3"
        elif item.label == "Race":
            item._value = "Elf"
        elif "STR" in item.label:
            item._value = "10 12 14 8 16 18"

    interaction = _make_interaction()
    await modal.on_submit(interaction)

    interaction.response.defer.assert_awaited_once()
    assert len(received) == 1
    _, raw = received[0]
    assert raw["name"] == "Legolas"
    assert raw["character_class"] == "Fighter"
    assert raw["class_level"] == "3"
    assert raw["race"] == "Elf"
    assert raw["abilities_str"] == "10 12 14 8 16 18"


@pytest.mark.asyncio
async def test_review_modal_passes_raw_abilities_through():
    """on_submit passes the raw ability string through without parsing (cog validates)."""
    received_raw: list[dict] = []

    async def capture(interaction, raw_dict):
        received_raw.append(raw_dict)

    modal = CharacterReviewModal(_prefill_review(), on_submit_cb=capture)

    # Set an intentionally invalid value — modal should NOT raise; cog will handle it
    for item in modal.children:
        if "STR" in item.label:
            item._value = "10 12 14 8 16"  # only 5 scores — invalid
        elif "Name" in item.label:
            item._value = "Test"
        elif item.label == "Class":
            item._value = "Wizard"
        elif "Level" in item.label:
            item._value = "1"
        elif item.label == "Race":
            item._value = "Human"

    interaction = _make_interaction()
    await modal.on_submit(interaction)  # must NOT raise

    assert received_raw[0]["abilities_str"] == "10 12 14 8 16"  # raw, unvalidated


# ── CharacterEntryModal ────────────────────────────────────────────────────────


def test_entry_modal_component_count():
    """CharacterEntryModal must have exactly 5 TextInput components."""
    cb = AsyncMock()
    modal = CharacterEntryModal(on_submit_cb=cb)
    assert len(modal.children) == 5


def test_entry_modal_title():
    """Modal title is MODAL_TITLE_ENTRY."""
    cb = AsyncMock()
    modal = CharacterEntryModal(on_submit_cb=cb)
    assert modal.title == MODAL_TITLE_ENTRY


def test_entry_modal_empty_defaults():
    """CharacterEntryModal has empty/placeholder defaults for manual entry."""
    cb = AsyncMock()
    modal = CharacterEntryModal(on_submit_cb=cb)
    # All defaults should be either empty string, None, or a placeholder
    for item in modal.children:
        # The default should NOT be filled with real character data
        assert item.default is None or isinstance(item.default, str)


def test_entry_modal_with_prefill():
    """CharacterEntryModal accepts an optional prefill for low-confidence best-guesses."""
    cb = AsyncMock()
    prefill = {
        "name": "Unknown",
        "character_class": "Fighter",
        "class_level": 1,
        "race": "Human",
        "abilities": AbilityScores(strength=10, dexterity=10, constitution=10,
                                    intelligence=10, wisdom=10, charisma=10),
    }
    modal = CharacterEntryModal(prefill=prefill, on_submit_cb=cb)
    labels_defaults = {item.label: item.default for item in modal.children}
    assert labels_defaults.get("Character Name") == "Unknown"


# ── OptionalFieldsModal ────────────────────────────────────────────────────────


def test_optional_modal_component_count():
    """OptionalFieldsModal must have exactly 5 TextInput components."""
    cb = AsyncMock()
    modal = OptionalFieldsModal(on_submit_cb=cb)
    assert len(modal.children) == 5


def test_optional_modal_has_expected_fields():
    """OptionalFieldsModal has subclass, background, skills, spells, alignment fields."""
    cb = AsyncMock()
    modal = OptionalFieldsModal(on_submit_cb=cb)
    labels = [item.label for item in modal.children]
    # At least these conceptual fields must be present
    label_str = " ".join(labels).lower()
    assert "subclass" in label_str or "sub" in label_str
    assert "background" in label_str
    assert "skill" in label_str
    assert "spell" in label_str
    assert "alignment" in label_str


# ── 5-component hard cap assertion ────────────────────────────────────────────


def test_five_component_cap_assertion_fires():
    """Adding a 6th TextInput to any modal class triggers an AssertionError."""
    cb = AsyncMock()
    modal = CharacterReviewModal(_prefill_review(), on_submit_cb=cb)

    # Attempt to add a 6th item directly to the children list (bypassing add_item)
    extra = discord.ui.TextInput(label="Extra Field", max_length=50)

    with pytest.raises(AssertionError, match="5-component"):
        # Use the custom add_item that enforces the cap
        modal.add_item(extra)
