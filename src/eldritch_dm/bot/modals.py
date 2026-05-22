"""
Discord Modal classes for EldritchDM character ingest flow.

All modals follow the "callback pattern" (D-03): the cog passes an
``on_submit_cb`` callable at construction time, keeping modal classes
testable in isolation (no cog reference inside the modal).

RESEARCH §5 — Discord hard cap: 5 TextInput components per Modal.
Every class in this module asserts this limit at construction time via a
custom ``add_item`` override and the ``_assert_cap`` helper.

Confidence routing (D-27):
    confidence >= 0.6 → CharacterReviewModal (player confirms extracted data)
    confidence  < 0.6 → CharacterEntryModal  (player types from scratch)
    "Refine" button   → OptionalFieldsModal  (subclass/background/skills/spells)

The ability-score field (field 5 in both primary modals) is a single
space-separated string because Discord's modal cap is 5 — we cannot have 6
separate score fields. Parser and serializer live here as module-level helpers.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

import discord
from discord import ui

from eldritch_dm.bot.warnings import WarningKind, send_warning
from eldritch_dm.ingest.schema import AbilityScores

# ── Constants ──────────────────────────────────────────────────────────────────

MODAL_TITLE_REVIEW: str = "Confirm Character"
MODAL_TITLE_ENTRY: str = "Enter Character"
MODAL_TITLE_OPTIONAL: str = "Optional Details"

_MAX_MODAL_COMPONENTS = 5  # Discord hard cap (RESEARCH §5)


# ── Ability-score helpers ──────────────────────────────────────────────────────


def parse_abilities_field(s: str) -> AbilityScores:
    """Parse a space-separated ability score string into an AbilityScores model.

    Accepts any amount of whitespace between values (uses str.split()).
    Raises ValueError on wrong count or non-integer values.
    Pydantic validates the range (ge=1, le=30) and raises ValidationError on
    out-of-range values.

    Args:
        s: Space-separated string, e.g. "15 18 14 12 10 8"
           representing STR DEX CON INT WIS CHA.

    Returns:
        Validated AbilityScores instance.

    Raises:
        ValueError:         Wrong number of tokens or non-integer tokens.
        ValidationError:    Out-of-range score (ge=1, le=30 from AbilityScores).
    """
    parts = s.split()
    if len(parts) != 6:
        raise ValueError(
            f"Expected 6 ability scores separated by spaces, got {len(parts)}"
        )
    try:
        ints = [int(p) for p in parts]
    except ValueError as e:
        raise ValueError(f"Ability scores must be integers: {e}") from e
    return AbilityScores(
        strength=ints[0],
        dexterity=ints[1],
        constitution=ints[2],
        intelligence=ints[3],
        wisdom=ints[4],
        charisma=ints[5],
    )


def serialize_abilities(a: AbilityScores) -> str:
    """Serialize AbilityScores to a space-separated string.

    Order is STR DEX CON INT WIS CHA — matching the parse order of
    ``parse_abilities_field``.

    Args:
        a: AbilityScores instance.

    Returns:
        Space-separated string, e.g. "15 18 14 12 10 8".
    """
    return (
        f"{a.strength} {a.dexterity} {a.constitution}"
        f" {a.intelligence} {a.wisdom} {a.charisma}"
    )


# ── 5-component cap enforcement mixin ─────────────────────────────────────────


class _CapEnforcedModal(ui.Modal):
    """Base Modal that raises AssertionError if a 6th component is added.

    All EldritchDM modal subclasses inherit from this to get compile-time
    and runtime protection against RESEARCH §5 pitfall.
    """

    def add_item(self, item: ui.Item) -> _CapEnforcedModal:  # type: ignore[override]
        """Add a component, asserting the 5-component hard cap is not exceeded."""
        assert len(self.children) < _MAX_MODAL_COMPONENTS, (
            f"5-component Discord Modal cap exceeded — cannot add '{getattr(item, 'label', item)}'."
            f" This modal already has {len(self.children)} components."
        )
        return super().add_item(item)  # type: ignore[return-value]


# ── CharacterReviewModal ───────────────────────────────────────────────────────


class CharacterReviewModal(_CapEnforcedModal, title=MODAL_TITLE_REVIEW):
    """Modal for player to review/confirm extracted character data (confidence ≥ 0.6).

    Five fields (Discord hard cap):
        1. Character Name     — short text, max 80 chars
        2. Class              — short text, max 40 chars
        3. Level (1-20)       — short text, max 2 chars
        4. Race               — short text, max 40 chars
        5. Ability Scores     — "STR DEX CON INT WIS CHA" space-separated, max 23

    The modal passes the raw field values through to ``on_submit_cb`` as a dict.
    Validation of the ability string is the cog's responsibility (keeps modal pure).

    Args:
        prefill:       Dict with keys matching the field names (from IngestResult).
                       Keys: name, character_class, class_level, race, abilities
                       (where abilities is an AbilityScores instance or None).
        on_submit_cb:  Async callable ``(interaction, raw_dict) -> None`` called
                       after defer with the raw field values.
    """

    def __init__(
        self,
        prefill: dict[str, Any],
        *,
        on_submit_cb: Callable[[discord.Interaction, dict[str, Any]], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._on_submit_cb = on_submit_cb

        abilities_obj = prefill.get("abilities")
        abilities_default = (
            serialize_abilities(abilities_obj)
            if isinstance(abilities_obj, AbilityScores)
            else "10 10 10 10 10 10"
        )

        # Field 1: Character Name
        self.name_field = ui.TextInput(
            label="Character Name",
            default=str(prefill.get("name", "")) or None,
            max_length=80,
            style=discord.TextStyle.short,
        )
        self.add_item(self.name_field)

        # Field 2: Class
        self.class_field = ui.TextInput(
            label="Class",
            default=str(prefill.get("character_class", "")) or None,
            max_length=40,
            style=discord.TextStyle.short,
        )
        self.add_item(self.class_field)

        # Field 3: Level
        self.level_field = ui.TextInput(
            label="Level (1-20)",
            default=str(prefill.get("class_level", "")) or None,
            max_length=2,
            style=discord.TextStyle.short,
        )
        self.add_item(self.level_field)

        # Field 4: Race
        self.race_field = ui.TextInput(
            label="Race",
            default=str(prefill.get("race", "")) or None,
            max_length=40,
            style=discord.TextStyle.short,
        )
        self.add_item(self.race_field)

        # Field 5: Ability scores — single space-separated field (RESEARCH §5)
        self.abilities_field = ui.TextInput(
            label="Ability Scores (STR DEX CON INT WIS CHA)",
            default=abilities_default,
            max_length=23,
            style=discord.TextStyle.short,
        )
        self.add_item(self.abilities_field)

    async def on_submit(self, interaction: discord.Interaction) -> None:  # noqa: EDM001 — modal submit responds directly
        """Defer, collect raw field values, call the cog-supplied callback.

        The callback receives a raw dict — ability scores are NOT pre-validated
        here; the cog handles parse failures so users get a clear error message.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)

        raw: dict[str, Any] = {
            "name": self.name_field.value,
            "character_class": self.class_field.value,
            "class_level": self.level_field.value,
            "race": self.race_field.value,
            "abilities_str": self.abilities_field.value,
        }
        await self._on_submit_cb(interaction, raw)


# ── CharacterEntryModal ────────────────────────────────────────────────────────


class CharacterEntryModal(_CapEnforcedModal, title=MODAL_TITLE_ENTRY):
    """Modal for manual character entry when confidence < 0.6 or /upload_character_manual.

    Identical layout to CharacterReviewModal but with empty/placeholder defaults.
    An optional ``prefill`` dict can seed best-guess values from a low-confidence
    ingest result (players still need to verify everything).

    Args:
        prefill:       Optional dict of best-guess values (same shape as
                       CharacterReviewModal.prefill); omitted → empty fields.
        on_submit_cb:  Async callable ``(interaction, raw_dict) -> None``.
    """

    def __init__(
        self,
        prefill: dict[str, Any] | None = None,
        *,
        on_submit_cb: Callable[[discord.Interaction, dict[str, Any]], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._on_submit_cb = on_submit_cb
        p = prefill or {}

        abilities_obj = p.get("abilities")
        abilities_default = (
            serialize_abilities(abilities_obj)
            if isinstance(abilities_obj, AbilityScores)
            else None
        )

        # Field 1: Character Name
        self.name_field = ui.TextInput(
            label="Character Name",
            placeholder="e.g. Aragorn",
            default=str(p.get("name", "")) if p.get("name") else None,
            max_length=80,
            style=discord.TextStyle.short,
        )
        self.add_item(self.name_field)

        # Field 2: Class
        self.class_field = ui.TextInput(
            label="Class",
            placeholder="e.g. Ranger",
            default=str(p.get("character_class", "")) if p.get("character_class") else None,
            max_length=40,
            style=discord.TextStyle.short,
        )
        self.add_item(self.class_field)

        # Field 3: Level
        self.level_field = ui.TextInput(
            label="Level (1-20)",
            placeholder="e.g. 5",
            default=str(p.get("class_level", "")) if p.get("class_level") else None,
            max_length=2,
            style=discord.TextStyle.short,
        )
        self.add_item(self.level_field)

        # Field 4: Race
        self.race_field = ui.TextInput(
            label="Race",
            placeholder="e.g. Human",
            default=str(p.get("race", "")) if p.get("race") else None,
            max_length=40,
            style=discord.TextStyle.short,
        )
        self.add_item(self.race_field)

        # Field 5: Ability scores
        self.abilities_field = ui.TextInput(
            label="Ability Scores (STR DEX CON INT WIS CHA)",
            placeholder="e.g. 15 18 14 12 10 8",
            default=abilities_default,
            max_length=23,
            style=discord.TextStyle.short,
        )
        self.add_item(self.abilities_field)

    async def on_submit(self, interaction: discord.Interaction) -> None:  # noqa: EDM001 — modal submit responds directly
        """Defer, collect raw field values, call the cog-supplied callback."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        raw: dict[str, Any] = {
            "name": self.name_field.value,
            "character_class": self.class_field.value,
            "class_level": self.level_field.value,
            "race": self.race_field.value,
            "abilities_str": self.abilities_field.value,
        }
        await self._on_submit_cb(interaction, raw)


# ── OptionalFieldsModal ────────────────────────────────────────────────────────


class OptionalFieldsModal(_CapEnforcedModal, title=MODAL_TITLE_OPTIONAL):
    """Secondary modal for optional character details.

    Opened via a "Refine" button in the character confirmation embed (D-28).
    Not auto-launched in Phase 3 — documented as deferred until Phase 4/v2
    per Plan 03 SUMMARY Deferred Items.

    Five fields:
        1. Subclass          — optional
        2. Background        — optional
        3. Skills            — comma-separated, optional
        4. Spells            — comma-separated, optional
        5. Alignment         — optional
    """

    def __init__(
        self,
        prefill: dict[str, Any] | None = None,
        *,
        on_submit_cb: Callable[[discord.Interaction, dict[str, Any]], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._on_submit_cb = on_submit_cb
        p = prefill or {}

        self.subclass_field = ui.TextInput(
            label="Subclass",
            placeholder="e.g. Battle Master",
            default=p.get("subclass"),
            max_length=40,
            required=False,
            style=discord.TextStyle.short,
        )
        self.add_item(self.subclass_field)

        self.background_field = ui.TextInput(
            label="Background",
            placeholder="e.g. Folk Hero",
            default=p.get("background"),
            max_length=40,
            required=False,
            style=discord.TextStyle.short,
        )
        self.add_item(self.background_field)

        self.skills_field = ui.TextInput(
            label="Skills (comma-separated)",
            placeholder="e.g. Perception, Stealth, Athletics",
            default=p.get("skills"),
            max_length=200,
            required=False,
            style=discord.TextStyle.short,
        )
        self.add_item(self.skills_field)

        self.spells_field = ui.TextInput(
            label="Spells (comma-separated)",
            placeholder="e.g. Fireball, Magic Missile",
            default=p.get("spells"),
            max_length=200,
            required=False,
            style=discord.TextStyle.short,
        )
        self.add_item(self.spells_field)

        self.alignment_field = ui.TextInput(
            label="Alignment",
            placeholder="e.g. Chaotic Good",
            default=p.get("alignment"),
            max_length=30,
            required=False,
            style=discord.TextStyle.short,
        )
        self.add_item(self.alignment_field)

    async def on_submit(self, interaction: discord.Interaction) -> None:  # noqa: EDM001 — modal submit responds directly
        """Defer, collect raw field values, call the cog-supplied callback."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        raw: dict[str, Any] = {
            "subclass": self.subclass_field.value or None,
            "background": self.background_field.value or None,
            "skills": self.skills_field.value or None,
            "spells": self.spells_field.value or None,
            "alignment": self.alignment_field.value or None,
        }
        await self._on_submit_cb(interaction, raw)


# ── WeaponSelectModal ──────────────────────────────────────────────────────────

# Validation regexes (T-04-11 field-level injection rejection):
#   weapon:    alphanumeric, spaces, apostrophes, plus signs only
#   target_id: lowercase alphanumeric and hyphens only (dm20 UUID format)
_WEAPON_VALID_RE = re.compile(r"^[a-zA-Z0-9 '+]+$")
_TARGET_ID_VALID_RE = re.compile(r"^[a-z0-9-]+$")


class WeaponSelectModal(_CapEnforcedModal, title="Attack: Select Weapon & Target"):
    """Modal for selecting weapon and target in the attack flow (D-18).

    Two TextInput components (well under the 5-component Discord cap):
      1. weapon:    Name of the weapon to use (max 80 chars).
      2. target_id: dm20 character UUID of the target (max 80 chars).

    The on_submit_cb receives ``{"weapon": str, "target_id": str}`` after
    field validation. Malformed fields trigger INVALID_ACTION (T-04-11).

    Validation rules (T-04-11 -- structured fields, NOT free-prose):
      weapon:    r'^[a-zA-Z0-9 \\'+]+$'  (alphanumeric + space + apostrophe + plus)
      target_id: r'^[a-z0-9-]+$'          (lowercase + digits + hyphen)

    Args:
        on_submit_cb: Async callable ``(payload: dict) -> None`` called after
                      validation with ``{"weapon": str, "target_id": str}``.
    """

    def __init__(
        self,
        *,
        on_submit_cb: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._on_submit_cb = on_submit_cb

        # Field 1: Weapon name
        self.weapon_field = ui.TextInput(
            label="Weapon",
            placeholder="e.g. Longsword, Hand Axe, Fireball",
            max_length=80,
            style=discord.TextStyle.short,
            required=True,
        )
        self.add_item(self.weapon_field)

        # Field 2: Target ID (dm20 character UUID)
        self.target_field = ui.TextInput(
            label="Target ID",
            placeholder="e.g. goblin-king-001 (dm20 character id)",
            max_length=80,
            style=discord.TextStyle.short,
            required=True,
        )
        self.add_item(self.target_field)

    async def on_submit(self, interaction: discord.Interaction) -> None:  # noqa: EDM001 — modal submit responds directly
        """Validate fields and dispatch to on_submit_cb.

        Validation (T-04-11):
          weapon:    alphanumeric + space + apostrophe + plus only.
          target_id: lowercase + digits + hyphen only.

        On validation failure: send INVALID_ACTION warning; do NOT call callback.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)

        weapon = self.weapon_field.value or ""
        target_id = self.target_field.value or ""

        # Validate weapon field
        if not _WEAPON_VALID_RE.match(weapon):
            await send_warning(
                interaction,
                WarningKind.INVALID_ACTION,
                reason=(
                    "Weapon name contains invalid characters. "
                    "Use alphanumeric, spaces, apostrophes, and plus signs only."
                ),
            )
            return

        # Validate target_id field
        if not _TARGET_ID_VALID_RE.match(target_id):
            await send_warning(
                interaction,
                WarningKind.INVALID_ACTION,
                reason=(
                    "Target ID contains invalid characters. "
                    "Use lowercase letters, digits, and hyphens only."
                ),
            )
            return

        payload: dict[str, Any] = {
            "weapon": weapon,
            "target_id": target_id,
        }
        await self._on_submit_cb(payload)
