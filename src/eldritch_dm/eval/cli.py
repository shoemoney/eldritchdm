"""eldritch-dm-eval CLI (Phase 12 / EVAL-03 / D-77, D-78, D-79).

Runs the corpus: for each scenario, invokes SmartMonsterDriver directly
(no Discord), captures the choice, asks TacticalJudge to score, aggregates,
diffs against an optional baseline, writes JSON + Markdown outputs, exits
with a code derived from S-12-02-B precedence (critical > regression > pass).

Exit codes:
  0 = passed (overall_mean >= 0.7, no per-dimension mean < 0.5)
  1 = regression (baseline supplied AND delta < -0.05; OR no baseline
      AND overall_mean < 0.7)
  2 = critical (any per-dimension mean < 0.5, regardless of baseline)
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from eldritch_dm.eval.aggregator import (
    BaselineDiff,
    ScenarioResult,
    aggregate,
    compute_baseline_diff,
    derive_exit_code,
)
from eldritch_dm.eval.judge import TacticalJudge
from eldritch_dm.eval.reporter import render_report
from eldritch_dm.eval.runner import build_eval_driver, run_scenario
from eldritch_dm.eval.scenarios import load_scenarios
from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from openai import AsyncOpenAI

log = get_logger(__name__)


_DEFAULT_DATASET = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "eval"
    / "dataset"
    / "tactical_corpus.jsonl"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eldritch-dm-eval",
        description=(
            "Run the LLM-as-judge tactical-scoring corpus against "
            "SmartMonsterDriver (no Discord, no live combat state)."
        ),
        epilog=(
            "Exit codes:\n"
            "  0 = passed (overall_mean >= 0.7, no per-dimension mean < 0.5)\n"
            "  1 = regression (baseline delta < -0.05, or no baseline AND below 0.7)\n"
            "  2 = critical (any per-dimension mean < 0.5)\n"
            "\n"
            "The corpus is the bundled tests/eval/dataset/tactical_corpus.jsonl\n"
            "(Apache-2.0; see tests/eval/dataset/LICENSE.md). The judge prompt\n"
            "is versioned via a SemVer header — runs record the version so\n"
            "prior eval runs remain comparable to new ones.\n"
            "\n"
            "Escape-hatch: --judge-model gpt-4o (requires OPENAI_API_KEY +\n"
            "OPENAI_BASE_URL=https://api.openai.com/v1)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=_DEFAULT_DATASET,
        help=f"Path to JSONL corpus (default: {_DEFAULT_DATASET}).",
    )
    parser.add_argument(
        "--judge-model",
        default="ShoeGPT",
        help="Model name for TacticalJudge (default: ShoeGPT). "
        "Use 'gpt-4o' with hosted OpenAI for higher-quality audits.",
    )
    parser.add_argument(
        "--driver-model",
        default="ShoeGPT",
        help="Model name for SmartMonsterDriver (default: ShoeGPT).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit the number of scenarios (default: 0 = all).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Path to a prior eval JSON output for diff/regression detection.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./eval-runs"),
        help="Output directory for eval-{timestamp}-{sha}.json and .md.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Emit per-scenario log records at DEBUG level.",
    )
    return parser


def _git_short_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or "unknown"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def _build_openai_client(*, base_url: str, api_key: str) -> AsyncOpenAI:
    """Construct an AsyncOpenAI client. Indirection exists so tests can patch."""
    from openai import AsyncOpenAI

    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scenario_to_json(r: ScenarioResult) -> dict:
    return {
        "scenario_id": r.scenario_id,
        "archetype": r.archetype,
        "driver_target_pc_id": r.driver_target_pc_id,
        "driver_rationale": r.driver_rationale,
        "verdict": r.verdict.model_dump() if r.verdict is not None else None,
        "judge_error": r.judge_error,
        "latency_ms_driver": r.latency_ms_driver,
        "latency_ms_judge": r.latency_ms_judge,
    }


def _baseline_diff_to_json(d: BaselineDiff | None) -> dict | None:
    if d is None:
        return None
    return d.model_dump()


async def _run_async(args: argparse.Namespace) -> int:
    started_at = _now_iso()
    scenarios = load_scenarios(args.dataset)
    if args.limit and args.limit > 0:
        scenarios = scenarios[: args.limit]
    if not scenarios:
        log.error("eval.empty_corpus", path=str(args.dataset))
        return 1

    base_url = os.environ.get("OMLX_ENDPOINT", "http://localhost:8765/v1")
    api_key = os.environ.get("OPENAI_API_KEY", "not-needed")
    client = _build_openai_client(base_url=base_url, api_key=api_key)

    driver = build_eval_driver(
        openai_client=client, model=args.driver_model
    )
    judge = TacticalJudge(openai_client=client, model=args.judge_model)

    log.info(
        "eval.starting",
        n=len(scenarios),
        driver_model=args.driver_model,
        judge_model=args.judge_model,
        judge_prompt_version=judge.prompt_version,
    )

    results: list[ScenarioResult] = []
    for scenario in scenarios:
        result = await run_scenario(
            driver=driver,
            judge=judge,
            scenario=scenario,
            driver_model=args.driver_model,
            judge_model=args.judge_model,
        )
        results.append(result)
        log.info(
            "eval.scenario_done",
            scenario_id=scenario.scenario_id,
            archetype=scenario.archetype,
            overall=result.verdict.overall_score if result.verdict else None,
            judge_error=result.judge_error,
        )

    stats = aggregate(results)
    baseline_diff: BaselineDiff | None = None
    if args.baseline is not None:
        try:
            baseline_diff = compute_baseline_diff(stats, args.baseline)
        except (FileNotFoundError, ValueError, OSError) as exc:
            log.error("eval.baseline_error", error=str(exc))
            return 1

    finished_at = _now_iso()
    exit_code = derive_exit_code(stats, baseline_diff)

    args.output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sha = _git_short_sha()
    json_path = args.output / f"eval-{timestamp}-{sha}.json"
    md_path = args.output / f"eval-{timestamp}-{sha}.md"

    json_payload = {
        "judge_prompt_version": judge.prompt_version,
        "driver_model": args.driver_model,
        "judge_model": args.judge_model,
        "started_at": started_at,
        "finished_at": finished_at,
        "git_sha": sha,
        "aggregate": stats.model_dump(),
        "baseline_diff": _baseline_diff_to_json(baseline_diff),
        "scenarios": [_scenario_to_json(r) for r in results],
        "exit_code": exit_code,
    }
    json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    md = render_report(
        stats,
        results,
        baseline_diff,
        judge_prompt_version=judge.prompt_version,
        driver_model=args.driver_model,
        judge_model=args.judge_model,
        started_at=started_at,
        finished_at=finished_at,
    )
    md_path.write_text(md, encoding="utf-8")

    log.info(
        "eval.finished",
        exit_code=exit_code,
        json=str(json_path),
        md=str(md_path),
        overall_mean=stats.overall_mean,
    )
    return exit_code


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_run_async(args))
    except KeyboardInterrupt:
        log.warning("eval.interrupted")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
