"""Homebrew Riposte eligibility YAML loader (Phase 08 / HOMEBREW-01 + 02).

Decisions referenced (CONTEXT D-29..D-40):
  - D-29  3-tier path precedence: env > per-install > in-repo default.
  - D-30  In-repo default ships v1.0 D-C frozenset (battle-master fighter only).
  - D-31  `yaml.safe_load` ONLY — CI grep gate enforces this discipline.
  - D-32  Pydantic v2 schema with `model_config = ConfigDict(extra='forbid')`.
  - D-33  Fail-soft to DEFAULT_ELIGIBILITY on any error; never crash the bot.
  - D-34  Extend-by-default; `mode: replace` opts in to full override.
  - D-36  Casing normalized via shared `gameplay.normalize.normalize`.
  - D-40  Schema reserves `version` field; reject version != 1 with fallback.

Pitfalls referenced (research/PITFALLS.md):
  - YAML-1 (CRITICAL)  yaml.load is RCE; we use safe_load exclusively.
  - YAML-3 (HIGH)      Fail-soft + structured warning on any error.
  - YAML-4             Mode is explicit; resolved set is logged.
  - YAML-6             Case normalization is non-optional.

Threat mitigations (T-08-01, T-08-02, T-08-05): see PHASE 08 threat register.

Public surface:
    DEFAULT_ELIGIBILITY  — frozenset[tuple[str, str]] matching v1.0 reactions.
    EligibilityFile      — Pydantic schema for the on-disk YAML.
    load_eligibility(s)  — Public entrypoint. NEVER raises.

This module is import-linter-safe: lives in `gameplay/`, imports only
`gameplay.normalize`, `logging`, `pydantic`, `yaml`, `pathlib`, and TYPE_CHECKING
`config.Settings`. No upward imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from eldritch_dm.gameplay.normalize import normalize
from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from eldritch_dm.config import Settings

log = get_logger(__name__)


# D-30: matches v1.0 reactions.ELIGIBLE_CLASS_SUBCLASSES exactly.
DEFAULT_ELIGIBILITY: frozenset[tuple[str, str]] = frozenset(
    {("fighter", "battle master")}
)


class EligibilityFile(BaseModel):
    """Pydantic v2 schema for the homebrew eligibility YAML (D-32, D-40)."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    mode: Literal["extend", "replace"] = "extend"
    eligible: dict[str, list[str]]


# ── Path resolution (D-29 — 3-tier precedence; FIRST hit wins) ────────────────


def _resolve_path(settings: Settings) -> Path | None:
    """Walk the 3-tier path order: env > per-install > in-repo default.

    Returns the first existing path, or None if no file is found at any tier.
    """
    # Tier 1: explicit env override via Settings.eligibility_yaml_path.
    env_path = getattr(settings, "eligibility_yaml_path", None)
    if env_path is not None:
        p = Path(env_path)
        if p.is_file():
            return p

    # Tier 2: per-install user file under $HOME/.eldritch/eligibility.yaml.
    per_install = Path.home() / ".eldritch" / "eligibility.yaml"
    if per_install.is_file():
        return per_install

    # Tier 3: in-repo default. `__file__` lives in
    #   <repo>/src/eldritch_dm/gameplay/eligibility_loader.py
    # so `parents[3]` is `<repo>`. Under `pip install` (site-packages) this
    # walk falls outside the source tree and the `is_file()` check returns
    # False — caller falls through to DEFAULT_ELIGIBILITY (D-33), which IS
    # the v1.0 default (D-30), so the behavior is correct either way.
    in_repo = Path(__file__).resolve().parents[3] / "database" / "eligibility.yaml"
    if in_repo.is_file():
        return in_repo

    return None


# ── Conversion (extend vs replace; normalize casing) ──────────────────────────


def _to_frozenset(parsed: EligibilityFile) -> frozenset[tuple[str, str]]:
    """Normalize + apply extend/replace semantics (D-34, D-36)."""
    user_set: frozenset[tuple[str, str]] = frozenset(
        (normalize(cls), normalize(sub))
        for cls, subs in parsed.eligible.items()
        for sub in subs
    )
    if parsed.mode == "replace":
        return user_set
    # extend — union with DEFAULT_ELIGIBILITY.
    return DEFAULT_ELIGIBILITY | user_set


# ── Public entrypoint ─────────────────────────────────────────────────────────


def load_eligibility(settings: Settings) -> frozenset[tuple[str, str]]:
    """Resolve the eligibility frozenset. NEVER raises (D-33 fail-soft).

    On any failure (missing file, parse error, schema violation, unsupported
    version), logs a structured `eligibility.fallback` warning and returns
    DEFAULT_ELIGIBILITY. On success, logs `eligibility.resolved` at INFO
    (PITFALLS YAML-4 — operator can grep their JSON log for what was loaded).
    """
    try:
        path = _resolve_path(settings)
        if path is None:
            log.warning(
                "eligibility.fallback",
                reason="no_eligibility_yaml_found",
            )
            return DEFAULT_ELIGIBILITY

        raw_text = path.read_text(encoding="utf-8")

        # D-31 / PITFALLS YAML-1 / T-08-01: safe_load ONLY. CI gate enforces.
        try:
            raw = yaml.safe_load(raw_text)
        except yaml.YAMLError as e:
            log.warning(
                "eligibility.fallback",
                reason="yaml_parse_error",
                error=str(e),
                source=str(path),
            )
            return DEFAULT_ELIGIBILITY

        if raw is None:
            log.warning(
                "eligibility.fallback",
                reason="empty_yaml_file",
                source=str(path),
            )
            return DEFAULT_ELIGIBILITY

        try:
            parsed = EligibilityFile.model_validate(raw)
        except ValidationError as e:
            log.warning(
                "eligibility.fallback",
                reason="schema_validation_error",
                error=str(e),
                source=str(path),
            )
            return DEFAULT_ELIGIBILITY

        if parsed.version != 1:
            log.warning(
                "eligibility.fallback",
                reason="unsupported_schema_version",
                version=parsed.version,
                source=str(path),
            )
            return DEFAULT_ELIGIBILITY

        resolved = _to_frozenset(parsed)

        log.info(
            "eligibility.resolved",
            source=str(path),
            mode=parsed.mode,
            count=len(resolved),
            entries=sorted(f"{c}:{s}" for c, s in resolved),
        )
        return resolved

    except Exception as e:  # noqa: BLE001
        # Belt-and-suspenders catch-all per D-33: NEVER crash on bad YAML.
        log.warning(
            "eligibility.fallback",
            reason=e.__class__.__name__,
            error=str(e),
        )
        return DEFAULT_ELIGIBILITY
