"""Pydantic v2 models for the ingest pipeline.

CharacterSheet  — parsed + validated character data
AbilityScores   — D&D 5e ability scores (STR/DEX/CON/INT/WIS/CHA)
IngestResult    — output envelope from the ingest pipeline
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AbilityScores(BaseModel):
    """D&D 5e ability scores.  All values must be 1-30."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strength: int = Field(ge=1, le=30)
    dexterity: int = Field(ge=1, le=30)
    constitution: int = Field(ge=1, le=30)
    intelligence: int = Field(ge=1, le=30)
    wisdom: int = Field(ge=1, le=30)
    charisma: int = Field(ge=1, le=30)


class CharacterSheet(BaseModel):
    """Validated, normalised character sheet.

    extra="ignore" lets oMLX responses include additional fields without
    raising a ValidationError — we keep only what we care about.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    # Required fields
    name: str = Field(min_length=1, max_length=80)
    character_class: str = Field(min_length=1, max_length=40)
    class_level: int = Field(ge=1, le=20)
    race: str = Field(min_length=1, max_length=40)
    abilities: AbilityScores

    # Optional but common
    subclass: str | None = None
    subrace: str | None = None
    background: str | None = None
    alignment: str | None = None
    hp: int | None = Field(default=None, ge=1)
    ac: int | None = Field(default=None, ge=1)

    # List fields — kept bounded to prevent runaway payloads
    skills: list[str] = Field(default_factory=list, max_length=30)
    weapons: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    spells: list[str] = Field(default_factory=list, max_length=50)


@dataclass(frozen=True)
class IngestResult:
    """Output envelope from the async ingest() pipeline.

    Attributes:
        raw_text:            OCR/PDF text extracted from the attachment.
        parsed_sheet:        Validated CharacterSheet, or None when confidence
                             is too low or parsing failed.
        confidence_score:    0.0-1.0 estimate from the OCR/translate layer.
        validation_warnings: Non-fatal issues that the human reviewer should see.
        ocr_backend:         "ocrmac" | "easyocr" | None (None for PDF path).
        pdf_backend:         "pymupdf" | "pypdf" | None (None for image path).
    """

    raw_text: str
    parsed_sheet: CharacterSheet | None
    confidence_score: float
    validation_warnings: list[str] = field(default_factory=list)
    ocr_backend: str | None = None
    pdf_backend: str | None = None
