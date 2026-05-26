"""ScenarioEntry pydantic schema + JSONL loader (Phase 12 / D-74).

Decisions referenced:
  D-74  Corpus is JSONL; ScenarioEntry validates on load.
  D-75  5 archetypes — Literal-constrained.
  D-76  Corpus is original Apache-2.0 content (validated externally; the
        schema doesn't enforce licensing).

The eval loader fails LOUD on corruption (mirror of S-12-01-A semantics):
a malformed corpus is a developer bug, not an operator one. We DO NOT
fail soft like ``eligibility_loader``; that module exists to keep the
bot running, while a broken eval is not a production hot path.

Import-linter-safe: lives under ``eval/``; imports only stdlib + pydantic
+ ``eldritch_dm.logging``.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from eldritch_dm.logging import get_logger

log = get_logger(__name__)


Archetype = Literal["brute", "spellcaster", "swarm", "predator", "edge_case"]


class ScenarioLoadError(Exception):
    """Raised when the JSONL corpus cannot be parsed.

    Carries the line number to make corpus debugging easy. The eval CLI
    surfaces this directly to the operator (no fail-soft).
    """


class MonsterStats(BaseModel):
    """Stat block for the acting monster in a scenario.

    Only the fields the SmartMonsterDriver actually consults are required;
    the rest is decorative metadata used by the judge prompt for context.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    intelligence: int = Field(ge=0, le=30)
    hp: int = Field(ge=1)
    ac: int = Field(ge=1, le=30)
    traits: list[str] = Field(default_factory=list)


class PCEntry(BaseModel):
    """One PC in the scenario party.

    Field names mirror what ``SmartMonsterDriver._slim_candidate`` reads
    from the live combat state (``character_id``, ``name``, ``hp_current``,
    ``hp_max``, ``ac``, ``active_conditions``) so the runner can pass the
    dict form directly to ``_choose_target`` without remapping.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    hp_current: int = Field(ge=0)
    hp_max: int = Field(ge=1)
    ac: int = Field(ge=1, le=30)
    active_conditions: list[str] = Field(default_factory=list)
    notes: str = ""


class ScenarioEntry(BaseModel):
    """One corpus entry (D-74)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(min_length=1)
    archetype: Archetype
    monster_stats: MonsterStats
    pc_list: list[PCEntry] = Field(min_length=2, max_length=8)
    environment: str = Field(min_length=1)
    expected_target_pool: list[str] = Field(default_factory=list)
    expected_avoidance: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=10)


def load_scenarios(path: Path) -> list[ScenarioEntry]:
    """Load a JSONL corpus. Fails loud on any malformed line.

    Empty lines are skipped (so trailing newlines and blank-line padding
    in the file don't cause spurious failures). Every non-empty line MUST
    parse as a ``ScenarioEntry``; otherwise ``ScenarioLoadError`` is
    raised with the 1-indexed line number.
    """
    if not path.is_file():
        raise ScenarioLoadError(f"corpus not found: {path}")

    entries: list[ScenarioEntry] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ScenarioLoadError(
                    f"line {line_no}: invalid JSON: {exc}"
                ) from exc
            try:
                entry = ScenarioEntry.model_validate(payload)
            except ValidationError as exc:
                raise ScenarioLoadError(
                    f"line {line_no}: schema validation failed: {exc}"
                ) from exc
            entries.append(entry)

    log.info("eval.corpus_loaded", path=str(path), count=len(entries))
    return entries
