"""Aggregation, baseline-diff, and exit-code derivation (Phase 12 / D-79).

Public surface:
    ScenarioResult       — one row of (scenario, driver_choice, verdict).
    AggregateStats       — rolled-up stats for a full run.
    BaselineDiff         — current-vs-baseline overall_mean delta.
    aggregate            — fold results into stats.
    compute_baseline_diff — read prior JSON and compute delta.
    derive_exit_code     — S-12-02-B precedence: critical > regression > pass.

Exit-code precedence (S-12-02-B):
    2 = critical: any per-dimension mean < 0.5 (ship blocker).
    1 = regression: baseline supplied AND delta < -0.05.
        OR no baseline AND overall_mean < 0.7 (implicit-baseline regression).
    0 = pass: overall_mean >= 0.7 AND no critical dim.

A run that is BOTH critical AND regressed exits 2 — critical wins.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from eldritch_dm.eval.judge import JudgeVerdict
from eldritch_dm.eval.scenarios import Archetype
from eldritch_dm.logging import get_logger

log = get_logger(__name__)


# Pass thresholds — kept as module constants so tests can import them.
PASS_OVERALL_MIN = 0.7
REGRESSION_DELTA_THRESHOLD = 0.05  # negative-direction
CRITICAL_DIM_MIN = 0.5

EXIT_PASS = 0
EXIT_REGRESSION = 1
EXIT_CRITICAL = 2


# Dimension keys (kept in sync with judge.DimensionKey) — typed as plain str
# here to avoid a circular import; the judge module owns the Literal alias.
_DIMENSION_KEYS: tuple[str, ...] = (
    "tactical_intent",
    "meta_knowledge",
    "narrative_fairness",
    "edge_case",
)


class ScenarioResult(BaseModel):
    """One row in the run: scenario + driver choice + judge verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    archetype: Archetype
    driver_target_pc_id: str | None
    driver_rationale: str | None = None
    verdict: JudgeVerdict | None
    judge_error: str | None = None
    latency_ms_driver: int = 0
    latency_ms_judge: int = 0


class AggregateStats(BaseModel):
    """Rolled-up stats for a full eval run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    n: int = Field(ge=0)
    overall_mean: float
    per_dimension_mean: dict[str, float]
    per_archetype_mean: dict[str, float]
    judge_failure_count: int = 0
    driver_failure_count: int = 0


class BaselineDiff(BaseModel):
    """Current-vs-baseline overall_mean delta."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_overall_mean: float
    current_overall_mean: float
    delta: float
    regressed: bool
    regression_threshold: float = REGRESSION_DELTA_THRESHOLD


def aggregate(results: list[ScenarioResult]) -> AggregateStats:
    """Fold a list of ScenarioResult into AggregateStats.

    None verdicts (judge failures) contribute 0.0 across all dimensions.
    Driver failures (driver_target_pc_id is None) are tallied separately
    and ALSO contribute 0.0 (the judge can't score "no choice made").
    """
    n = len(results)
    if n == 0:
        return AggregateStats(
            n=0,
            overall_mean=0.0,
            per_dimension_mean={k: 0.0 for k in _DIMENSION_KEYS},
            per_archetype_mean={},
            judge_failure_count=0,
            driver_failure_count=0,
        )

    total_overall = 0.0
    dim_totals = dict.fromkeys(_DIMENSION_KEYS, 0.0)
    archetype_totals: dict[str, list[float]] = {}
    judge_failures = 0
    driver_failures = 0

    for r in results:
        if r.driver_target_pc_id is None:
            driver_failures += 1
        if r.verdict is None:
            judge_failures += 1
            scenario_overall = 0.0
            scenario_dims = dict.fromkeys(_DIMENSION_KEYS, 0.0)
        else:
            scenario_overall = r.verdict.overall_score
            scenario_dims = {
                k: r.verdict.per_dimension[k]  # type: ignore[index]
                for k in _DIMENSION_KEYS
            }

        total_overall += scenario_overall
        for k in _DIMENSION_KEYS:
            dim_totals[k] += scenario_dims[k]
        archetype_totals.setdefault(r.archetype, []).append(scenario_overall)

    return AggregateStats(
        n=n,
        overall_mean=total_overall / n,
        per_dimension_mean={k: dim_totals[k] / n for k in _DIMENSION_KEYS},
        per_archetype_mean={
            arch: sum(vals) / len(vals) for arch, vals in archetype_totals.items()
        },
        judge_failure_count=judge_failures,
        driver_failure_count=driver_failures,
    )


def compute_baseline_diff(
    current: AggregateStats, baseline_path: Path
) -> BaselineDiff:
    """Read a prior eval JSON and compute the delta vs the current run.

    Raises FileNotFoundError if the baseline file doesn't exist (the CLI
    catches this and surfaces a clear error to the operator).

    The baseline JSON shape is the same as written by Plan 02's CLI:
    top-level `{"aggregate": {"overall_mean": float, ...}, ...}`.
    """
    raw = json.loads(baseline_path.read_text(encoding="utf-8"))
    aggregate_section = raw.get("aggregate")
    if not isinstance(aggregate_section, dict):
        raise ValueError(
            f"baseline {baseline_path} has no 'aggregate' object at top level"
        )
    baseline_mean = float(aggregate_section.get("overall_mean", 0.0))
    delta = current.overall_mean - baseline_mean
    regressed = delta < -REGRESSION_DELTA_THRESHOLD
    return BaselineDiff(
        baseline_overall_mean=baseline_mean,
        current_overall_mean=current.overall_mean,
        delta=delta,
        regressed=regressed,
    )


def derive_exit_code(
    stats: AggregateStats, baseline_diff: BaselineDiff | None
) -> Literal[0, 1, 2]:
    """S-12-02-B precedence: critical (2) > regression (1) > pass (0).

    Critical: any per-dimension mean < CRITICAL_DIM_MIN (0.5).
    Regression: baseline_diff.regressed OR (no baseline AND overall < 0.7).
    Pass: overall_mean >= 0.7 AND no critical dim.
    """
    # 1. Critical FIRST — short-circuits regression.
    if any(v < CRITICAL_DIM_MIN for v in stats.per_dimension_mean.values()):
        log.warning(
            "eval.exit_code.critical",
            failing_dims={
                k: v
                for k, v in stats.per_dimension_mean.items()
                if v < CRITICAL_DIM_MIN
            },
        )
        return EXIT_CRITICAL

    # 2. Regression.
    if baseline_diff is not None:
        if baseline_diff.regressed:
            return EXIT_REGRESSION
        # baseline supplied AND not regressed → defer to pass-check.

    # No baseline (or baseline non-regressed): still enforce the absolute
    # pass bar from D-79 (avg overall >= 0.7).
    if stats.overall_mean < PASS_OVERALL_MIN:
        return EXIT_REGRESSION

    return EXIT_PASS


__all__ = [
    "AggregateStats",
    "BaselineDiff",
    "CRITICAL_DIM_MIN",
    "EXIT_CRITICAL",
    "EXIT_PASS",
    "EXIT_REGRESSION",
    "PASS_OVERALL_MIN",
    "REGRESSION_DELTA_THRESHOLD",
    "ScenarioResult",
    "aggregate",
    "compute_baseline_diff",
    "derive_exit_code",
]
