"""Aggregator + baseline-diff + exit-code tests (T-12-02-01, T-12-02-02)."""

from __future__ import annotations

import json
from pathlib import Path

from eldritch_dm.eval.aggregator import (
    EXIT_CRITICAL,
    EXIT_PASS,
    EXIT_REGRESSION,
    AggregateStats,
    BaselineDiff,
    ScenarioResult,
    aggregate,
    compute_baseline_diff,
    derive_exit_code,
)
from eldritch_dm.eval.judge import JudgeVerdict


def _verdict(overall: float, approve: bool = True) -> JudgeVerdict:
    return JudgeVerdict.model_validate(
        {
            "overall_score": overall,
            "per_dimension": {
                "tactical_intent": overall,
                "meta_knowledge": overall,
                "narrative_fairness": overall,
                "edge_case": overall,
            },
            "reasoning": "synthetic",
            "would_a_veteran_dm_approve": approve,
        }
    )


def _result(
    sid: str,
    archetype: str,
    overall: float | None,
    *,
    judge_error: str | None = None,
    target: str | None = "pc-1",
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=sid,
        archetype=archetype,  # type: ignore[arg-type]
        driver_target_pc_id=target,
        driver_rationale=None,
        verdict=_verdict(overall) if overall is not None else None,
        judge_error=judge_error,
    )


# ── aggregate() ──────────────────────────────────────────────────────────────


def test_aggregate_empty_list() -> None:
    stats = aggregate([])
    assert stats.n == 0
    assert stats.overall_mean == 0.0
    assert stats.per_archetype_mean == {}


def test_aggregate_all_perfect() -> None:
    results = [_result(f"s-{i}", "brute", 1.0) for i in range(5)]
    stats = aggregate(results)
    assert stats.n == 5
    assert stats.overall_mean == 1.0
    assert stats.per_dimension_mean == {
        "tactical_intent": 1.0,
        "meta_knowledge": 1.0,
        "narrative_fairness": 1.0,
        "edge_case": 1.0,
    }
    assert stats.per_archetype_mean == {"brute": 1.0}


def test_aggregate_mixed_with_judge_failure() -> None:
    # 4 successes @ 0.8 + 1 None verdict → (0.8*4 + 0)/5 = 0.64
    results = [
        _result("s-1", "brute", 0.8),
        _result("s-2", "brute", 0.8),
        _result("s-3", "brute", 0.8),
        _result("s-4", "brute", 0.8),
        _result("s-5", "brute", None, judge_error="timeout"),
    ]
    stats = aggregate(results)
    assert stats.n == 5
    assert abs(stats.overall_mean - 0.64) < 1e-9
    assert stats.judge_failure_count == 1
    assert stats.driver_failure_count == 0


def test_aggregate_per_archetype_grouping() -> None:
    results = [
        _result("b-1", "brute", 1.0),
        _result("b-2", "brute", 0.5),
        _result("s-1", "spellcaster", 0.8),
    ]
    stats = aggregate(results)
    assert stats.per_archetype_mean == {"brute": 0.75, "spellcaster": 0.8}


def test_aggregate_driver_failure_counts() -> None:
    results = [
        _result("s-1", "brute", 0.8, target=None),  # driver failed
        _result("s-2", "brute", 0.8, target="pc-1"),
    ]
    stats = aggregate(results)
    assert stats.driver_failure_count == 1


def test_aggregate_per_dimension_means_independent() -> None:
    # Custom per-dim values via raw verdict construction.
    raw_verdict = JudgeVerdict.model_validate(
        {
            "overall_score": 0.5,
            "per_dimension": {
                "tactical_intent": 1.0,
                "meta_knowledge": 0.5,
                "narrative_fairness": 0.5,
                "edge_case": 0.0,
            },
            "reasoning": "x",
            "would_a_veteran_dm_approve": False,
        }
    )
    results = [
        ScenarioResult(
            scenario_id="s-1",
            archetype="brute",
            driver_target_pc_id="pc-1",
            verdict=raw_verdict,
        )
    ]
    stats = aggregate(results)
    assert stats.per_dimension_mean["tactical_intent"] == 1.0
    assert stats.per_dimension_mean["edge_case"] == 0.0


# ── compute_baseline_diff() ──────────────────────────────────────────────────


def _stats(overall: float, dim_overrides: dict[str, float] | None = None) -> AggregateStats:
    base = {k: overall for k in ("tactical_intent", "meta_knowledge", "narrative_fairness", "edge_case")}
    if dim_overrides:
        base.update(dim_overrides)
    return AggregateStats(
        n=10,
        overall_mean=overall,
        per_dimension_mean=base,
        per_archetype_mean={"brute": overall},
    )


def test_baseline_diff_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"aggregate": {"overall_mean": 0.85}}))
    current = _stats(0.7)
    diff = compute_baseline_diff(current, baseline)
    assert diff.baseline_overall_mean == 0.85
    assert diff.current_overall_mean == 0.7
    assert abs(diff.delta - (-0.15)) < 1e-9
    assert diff.regressed is True


def test_baseline_diff_no_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"aggregate": {"overall_mean": 0.7}}))
    current = _stats(0.72)  # +0.02 — within threshold
    diff = compute_baseline_diff(current, baseline)
    assert diff.regressed is False


def test_baseline_diff_below_threshold_not_regression(tmp_path: Path) -> None:
    # delta = -0.04 (within REGRESSION_DELTA_THRESHOLD of 0.05) → not regressed
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"aggregate": {"overall_mean": 0.75}}))
    current = _stats(0.71)
    diff = compute_baseline_diff(current, baseline)
    assert diff.regressed is False


# ── derive_exit_code() ───────────────────────────────────────────────────────


def test_exit_code_pass_no_baseline() -> None:
    stats = _stats(0.85)
    assert derive_exit_code(stats, None) == EXIT_PASS


def test_exit_code_pass_with_baseline() -> None:
    stats = _stats(0.85)
    diff = BaselineDiff(
        baseline_overall_mean=0.85,
        current_overall_mean=0.85,
        delta=0.0,
        regressed=False,
    )
    assert derive_exit_code(stats, diff) == EXIT_PASS


def test_exit_code_critical_dim_below_0_5() -> None:
    stats = _stats(0.8, dim_overrides={"edge_case": 0.4})
    assert derive_exit_code(stats, None) == EXIT_CRITICAL


def test_exit_code_regression() -> None:
    stats = _stats(0.65)
    diff = BaselineDiff(
        baseline_overall_mean=0.85,
        current_overall_mean=0.65,
        delta=-0.20,
        regressed=True,
    )
    assert derive_exit_code(stats, diff) == EXIT_REGRESSION


def test_exit_code_critical_beats_regression() -> None:
    # Both critical AND regressed — critical wins (S-12-02-B).
    stats = _stats(0.5, dim_overrides={"narrative_fairness": 0.4})
    diff = BaselineDiff(
        baseline_overall_mean=0.85,
        current_overall_mean=0.5,
        delta=-0.35,
        regressed=True,
    )
    assert derive_exit_code(stats, diff) == EXIT_CRITICAL


def test_exit_code_no_baseline_below_pass_bar_is_regression() -> None:
    # No baseline, overall 0.65 < 0.7, no critical → implicit regression (1).
    stats = _stats(0.65)
    assert derive_exit_code(stats, None) == EXIT_REGRESSION


def test_exit_code_no_baseline_exactly_at_pass_bar() -> None:
    stats = _stats(0.70)
    assert derive_exit_code(stats, None) == EXIT_PASS
