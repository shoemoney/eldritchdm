"""Corpus loader (Phase 18 / NARRCACHE-02).

Reads ``corpus.jsonl`` line-by-line and pydantic-validates each entry. A
malformed entry fails the test suite at corpus IMPORT time, not at first
assert, so the corpus is treated as a spec, not as test data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CorpusEntry(BaseModel):
    """One entry in ``corpus.jsonl``.

    `expected_cacheable` is the ground-truth: True iff a fail-CLOSED gate
    should accept this text. False-negative rate (mechanical text wrongly
    classified as cacheable) MUST be 0%.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    text: str
    expected_cacheable: bool
    rationale: str
    category: Literal[
        # cacheable
        "scene",
        "dialogue",
        "atmosphere",
        "lore",
        "hook",
        "travel",
        "worldbuilding",
        "adversarial_safe",
        # non-cacheable
        "explicit_damage",
        "explicit_hp_change",
        "save_dc",
        "dice_notation",
        "condition",
        "crit",
        "death",
        "ac_check",
        "adversarial_leak",
    ]


def corpus_path() -> Path:
    """Return the path to the corpus JSONL file."""
    return Path(__file__).resolve().parent / "corpus.jsonl"


def load_corpus(path: Path | None = None) -> list[CorpusEntry]:
    """Return all corpus entries, pydantic-validated.

    Raises if any line is malformed JSON or fails schema validation.
    """
    p = path or corpus_path()
    entries: list[CorpusEntry] = []
    with p.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"corpus.jsonl:{lineno}: invalid JSON — {exc}") from exc
            try:
                entry = CorpusEntry.model_validate(raw)
            except Exception as exc:  # pydantic.ValidationError chain
                raise ValueError(
                    f"corpus.jsonl:{lineno}: schema validation failed — {exc}"
                ) from exc
            entries.append(entry)
    return entries
