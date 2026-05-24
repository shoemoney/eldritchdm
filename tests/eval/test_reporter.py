"""Markdown reporter tests (T-12-02-03)."""

from __future__ import annotations

from eldritch_dm.eval.aggregator import (
    AggregateStats,
    BaselineDiff,
    ScenarioResult,
    aggregate,
)
from eldritch_dm.eval.judge import JudgeVerdict
from eldritch_dm.eval.reporter import render_report


def _verdict(overall: float) -> JudgeVerdict:
    return JudgeVerdict.model_validate(
        {
            "overall_score": overall,
            "per_dimension": {
                "tactical_intent": overall,
                "meta_knowledge": overall,
                "narrative_fairness": overall,
                "edge_case": overall,
            },
            "reasoning": "synthetic verdict for reporter test.",
            "would_a_veteran_dm_approve": overall >= 0.7,
        }
    )


def _result(sid: str, arch: str, overall: float | None, err: str | None = None) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=sid,
        archetype=arch,  # type: ignore[arg-type]
        driver_target_pc_id="pc-1",
        verdict=_verdict(overall) if overall is not None else None,
        judge_error=err,
    )


def _common_kwargs() -> dict:
    return {
        "judge_prompt_version": "1.0.0",
        "driver_model": "ShoeGPT",
        "judge_model": "ShoeGPT",
        "started_at": "2026-05-24T10:00:00Z",
        "finished_at": "2026-05-24T10:05:00Z",
    }


def test_render_report_basic() -> None:
    results = [_result(f"b-{i}", "brute", 0.8) for i in range(5)]
    stats = aggregate(results)
    md = render_report(stats, results, None, **_common_kwargs())
    assert "# EldritchDM Tactical Eval Report" in md
    assert "## Aggregate" in md
    assert "## Per-Archetype Scoreboard" in md
    assert "## Top 5 Failures" in md
    assert "0.800" in md  # overall mean rendered
    assert "ShoeGPT" in md
    assert "1.0.0" in md
    # Baseline section absent when not provided
    assert "## Baseline Diff" not in md


def test_render_report_includes_baseline_diff() -> None:
    results = [_result(f"b-{i}", "brute", 0.7) for i in range(5)]
    stats = aggregate(results)
    diff = BaselineDiff(
        baseline_overall_mean=0.85,
        current_overall_mean=0.7,
        delta=-0.15,
        regressed=True,
    )
    md = render_report(stats, results, diff, **_common_kwargs())
    assert "## Baseline Diff" in md
    assert "0.850" in md
    assert "regressed" in md


def test_render_report_failures_sorted_ascending() -> None:
    results = [
        _result("hi-1", "brute", 0.9),
        _result("lo-1", "brute", 0.1),
        _result("mid-1", "brute", 0.5),
    ]
    stats = aggregate(results)
    md = render_report(stats, results, None, **_common_kwargs())
    # The lowest score (lo-1) should appear earlier in the failures table
    # than the highest (hi-1).
    failures_section = md.split("## Top 5 Failures", 1)[1]
    assert failures_section.index("lo-1") < failures_section.index("hi-1")


def test_render_report_judge_errors_section_when_present() -> None:
    results = [
        _result("s-1", "brute", 0.8),
        _result("s-2", "brute", None, err="timeout"),
        _result("s-3", "brute", None, err="timeout"),
        _result("s-4", "brute", None, err="parse_error"),
    ]
    stats = aggregate(results)
    md = render_report(stats, results, None, **_common_kwargs())
    assert "### Judge Errors" in md
    assert "timeout" in md
    assert "parse_error" in md


def test_render_report_empty_results() -> None:
    stats = AggregateStats(
        n=0,
        overall_mean=0.0,
        per_dimension_mean={
            "tactical_intent": 0.0,
            "meta_knowledge": 0.0,
            "narrative_fairness": 0.0,
            "edge_case": 0.0,
        },
        per_archetype_mean={},
    )
    md = render_report(stats, [], None, **_common_kwargs())
    assert "_No scored scenarios._" in md
    assert "_No errors or failures to triage._" in md
