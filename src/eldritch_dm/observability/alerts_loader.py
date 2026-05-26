"""alerts.yaml loader — 3-tier path, safe_load only, fail-soft (Phase 13 / MON-02).

Mirrors ``eldritch_dm.gameplay.eligibility_loader`` (Phase 8 / D-29..D-40 patterns):

  - 3-tier path: env > per-install > in-repo default
  - ``yaml.safe_load`` only (CI grep gate enforces); RCE-resistant
  - Pydantic v2 schema with ``extra='forbid'``
  - Fail-soft to ``DEFAULT_RULES`` on ANY error; NEVER crashes the bot
  - Reserved ``version`` field; reject version != 1 with fallback

The default rules embedded in code match AI-SPEC §7 verbatim and are the
SAME rules that ship in ``database/alerts.yaml``. Both must stay in sync.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from eldritch_dm.config import Settings

log = get_logger(__name__)

KPI_NAME = Literal[
    "latency_p99_ms",
    "success_rate",
    "tactical_score",
    "refusal_rate",
    "fallback_rate",
]

OP = Literal["gt", "gte", "lt", "lte"]

ACTION = Literal["log", "degrade", "throttle", "webhook"]

SEVERITY = Literal["critical", "high", "warning"]


# ── Schema ──────────────────────────────────────────────────────────────────


class AlertRule(BaseModel):
    """One alert rule. ``extra='forbid'`` keeps the schema tight (D-32)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    severity: SEVERITY
    kpi: KPI_NAME
    op: OP
    threshold: float
    window_minutes: int = 5
    action: ACTION
    routing: dict[str, str] | None = None


class AlertsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    rules: list[AlertRule]


# ── Default rules (AI-SPEC §7) ───────────────────────────────────────────────


DEFAULT_RULES: tuple[AlertRule, ...] = (
    AlertRule(
        name="critical_latency_p99_breach",
        severity="critical",
        kpi="latency_p99_ms",
        op="gt",
        threshold=1500.0,
        window_minutes=5,
        action="degrade",
    ),
    AlertRule(
        name="high_fallback_rate",
        severity="high",
        kpi="fallback_rate",
        op="gt",
        threshold=0.10,
        window_minutes=5,
        action="log",
    ),
    AlertRule(
        name="warning_refusal_rate",
        severity="warning",
        kpi="refusal_rate",
        op="gt",
        threshold=0.001,
        window_minutes=5,
        action="log",
    ),
)


# ── Path resolution ─────────────────────────────────────────────────────────


def _resolve_path(settings: Settings | None) -> Path | None:
    """3-tier path: env > per-install > in-repo default."""
    if settings is not None:
        env_path = getattr(settings, "alerts_yaml_path", None)
        if env_path is not None:
            p = Path(env_path)
            if p.is_file():
                return p

    # Per-install
    per_install = Path.home() / ".eldritch" / "alerts.yaml"
    if per_install.is_file():
        return per_install

    # In-repo default
    in_repo = Path(__file__).resolve().parents[3] / "database" / "alerts.yaml"
    if in_repo.is_file():
        return in_repo

    return None


# ── Public entrypoint ───────────────────────────────────────────────────────


def load_alerts(settings: Settings | None = None) -> tuple[AlertRule, ...]:
    """Resolve alert rules. NEVER raises (fail-soft to ``DEFAULT_RULES``).

    On any failure (missing file, parse error, schema violation, unsupported
    version), logs a structured ``alerts.fallback`` warning and returns
    ``DEFAULT_RULES``. On success, logs ``alerts.resolved`` at INFO with
    the source path + rule count + severity breakdown.
    """
    try:
        path = _resolve_path(settings)
        if path is None:
            log.warning(
                "alerts.fallback",
                reason="no_alerts_yaml_found",
            )
            return DEFAULT_RULES

        raw_text = path.read_text(encoding="utf-8")

        try:
            raw = yaml.safe_load(raw_text)  # noqa: S506 — safe_load is the safe call
        except yaml.YAMLError as e:
            log.warning(
                "alerts.fallback",
                reason="yaml_parse_error",
                error=str(e),
                source=str(path),
            )
            return DEFAULT_RULES

        if raw is None:
            log.warning(
                "alerts.fallback",
                reason="empty_yaml_file",
                source=str(path),
            )
            return DEFAULT_RULES

        try:
            parsed = AlertsFile.model_validate(raw)
        except ValidationError as e:
            log.warning(
                "alerts.fallback",
                reason="schema_validation_error",
                error=str(e),
                source=str(path),
            )
            return DEFAULT_RULES

        if parsed.version != 1:
            log.warning(
                "alerts.fallback",
                reason="unsupported_schema_version",
                version=parsed.version,
                source=str(path),
            )
            return DEFAULT_RULES

        rules = tuple(parsed.rules)
        log.info(
            "alerts.resolved",
            source=str(path),
            count=len(rules),
            severities={r.severity for r in rules},
        )
        return rules

    except Exception as e:  # noqa: BLE001
        log.warning(
            "alerts.fallback",
            reason=e.__class__.__name__,
            error=str(e),
        )
        return DEFAULT_RULES
