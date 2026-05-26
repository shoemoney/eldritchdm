"""Markdown reporter for eval runs (Phase 12 / D-78).

Produces a human-readable companion to the JSON output: aggregate stats,
per-archetype scoreboard, baseline diff (when supplied), top failures,
and top reasons.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections import Counter

from eldritch_dm.eval.aggregator import (
    AggregateStats,
    BaselineDiff,
    ScenarioResult,
)


def _fmt(v: float) -> str:
    return f"{v:.3f}"


def _table(rows: list[list[str]], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_report(
    stats: AggregateStats,
    results: list[ScenarioResult],
    baseline_diff: BaselineDiff | None,
    *,
    judge_prompt_version: str,
    driver_model: str,
    judge_model: str,
    started_at: str,
    finished_at: str,
) -> str:
    """Return a Markdown string summarizing one eval run."""
    out: list[str] = []
    out.append("# EldritchDM Tactical Eval Report")
    out.append("")
    out.append(f"- **Started:** `{started_at}`")
    out.append(f"- **Finished:** `{finished_at}`")
    out.append(f"- **Driver model:** `{driver_model}`")
    out.append(f"- **Judge model:** `{judge_model}`")
    out.append(f"- **Judge prompt version:** `{judge_prompt_version}`")
    out.append(f"- **Scenarios:** {stats.n}")
    out.append("")

    # ── Aggregate ───────────────────────────────────────────────────────
    out.append("## Aggregate")
    out.append("")
    out.append(
        _table(
            [
                ["overall_mean", _fmt(stats.overall_mean)],
                ["judge_failure_count", str(stats.judge_failure_count)],
                ["driver_failure_count", str(stats.driver_failure_count)],
            ],
            ["metric", "value"],
        )
    )
    out.append("")
    out.append("### Per-Dimension Mean")
    out.append("")
    out.append(
        _table(
            [[dim, _fmt(v)] for dim, v in stats.per_dimension_mean.items()],
            ["dimension", "mean"],
        )
    )
    out.append("")

    # ── Per-Archetype Scoreboard ────────────────────────────────────────
    out.append("## Per-Archetype Scoreboard")
    out.append("")
    archetype_counts: Counter[str] = Counter(r.archetype for r in results)
    archetype_rows: list[list[str]] = [
        [arch, str(archetype_counts.get(arch, 0)), _fmt(mean)]
        for arch, mean in sorted(stats.per_archetype_mean.items())
    ]
    out.append(_table(archetype_rows, ["archetype", "n", "mean"]))
    out.append("")

    # ── Baseline Diff (optional) ────────────────────────────────────────
    if baseline_diff is not None:
        out.append("## Baseline Diff")
        out.append("")
        out.append(
            _table(
                [
                    ["baseline_overall_mean", _fmt(baseline_diff.baseline_overall_mean)],
                    ["current_overall_mean", _fmt(baseline_diff.current_overall_mean)],
                    ["delta", _fmt(baseline_diff.delta)],
                    ["regressed", str(baseline_diff.regressed)],
                ],
                ["metric", "value"],
            )
        )
        out.append("")

    # ── Top Failures (lowest 5 overall scores) ──────────────────────────
    out.append("## Top 5 Failures")
    out.append("")
    scored = [r for r in results if r.verdict is not None]
    scored.sort(key=lambda r: r.verdict.overall_score)  # type: ignore[union-attr]
    failures = scored[:5]
    if not failures:
        out.append("_No scored scenarios._")
    else:
        rows = []
        for r in failures:
            assert r.verdict is not None  # for the type checker
            rows.append(
                [
                    r.scenario_id,
                    r.archetype,
                    _fmt(r.verdict.overall_score),
                    r.driver_target_pc_id or "—",
                    r.verdict.reasoning[:80].replace("|", "/"),
                ]
            )
        out.append(
            _table(
                rows,
                ["scenario_id", "archetype", "overall", "driver_target", "reasoning_excerpt"],
            )
        )
    out.append("")

    # ── Top Reasons ─────────────────────────────────────────────────────
    out.append("## Top Reasons")
    out.append("")
    error_counts: Counter[str] = Counter(
        r.judge_error for r in results if r.judge_error is not None
    )
    if error_counts:
        out.append("### Judge Errors")
        out.append("")
        rows = [[reason, str(count)] for reason, count in error_counts.most_common(3)]
        out.append(_table(rows, ["error", "count"]))
        out.append("")
    if not error_counts and not failures:
        out.append("_No errors or failures to triage._")
        out.append("")

    return "\n".join(out)


__all__ = ["render_report"]
