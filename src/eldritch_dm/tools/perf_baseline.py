"""eldritch-dm-perf-baseline — Phase 28 / TUNE-02 / D-218.

Runs the Phase 27 hot-path profiler (``scripts.perf.profile_hot_paths``)
and diffs the fresh result against a committed baseline JSON. Exit codes
mirror Phase 12's ``eldritch-dm-eval`` precedence pattern.

Exit codes (D-218):
  0 — all p99s within ±10% of baseline
  1 — at least one p99 > +10% of baseline (regression)
  2 — at least one p99 > +25% of baseline (critical regression)

CLI shape (D-218):
  eldritch-dm-perf-baseline [--baseline PATH] [--output DIR]
                            [--limit-iterations N] [--skip-cprofile]
                            [--paths LIST]

The CLI is consumed by ``.github/workflows/perf.yml`` on a weekly
schedule (TUNE-03 / D-219). Failure is informational — perf is
operator-tunable, not a hard ship gate.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from eldritch_dm.logging import get_logger

# The ``scripts/`` directory is intentionally NOT a package under ``src/`` —
# it lives at the repo root alongside the installed source. When running
# inside the dev checkout (``pip install -e .``) the repo root is on
# ``sys.path`` via pytest conftest, but a bare console-script invocation
# (``uv run eldritch-dm-perf-baseline``) doesn't get that bootstrap. Anchor
# the path here so the import works in both modes.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.perf._schema import BaselineSchema  # noqa: E402

log = get_logger(__name__)

# ────────────────────────────────────────────────────────────────────────────
# Constants — exit codes + thresholds
# ────────────────────────────────────────────────────────────────────────────

EXIT_OK = 0
EXIT_WARN = 1
EXIT_CRITICAL = 2

WARN_PCT = 10.0
CRITICAL_PCT = 25.0

_DEFAULT_BASELINE = _REPO_ROOT / ".planning" / "perf-baseline-v1.9.0.json"

# ────────────────────────────────────────────────────────────────────────────
# Pure-function diff API
# ────────────────────────────────────────────────────────────────────────────

OpStatus = Literal["ok", "warn", "critical", "new", "missing"]


@dataclass(frozen=True)
class OpDelta:
    """Per-operation diff record."""

    name: str
    baseline_p99_ms: float | None  # None for "new" ops
    current_p99_ms: float | None   # None for "missing" ops
    delta_pct: float | None        # None for "new"/"missing"
    status: OpStatus


@dataclass(frozen=True)
class PerfDiff:
    """Full diff between a baseline and a current run."""

    deltas: list[OpDelta] = field(default_factory=list)


def compute_diff(baseline: BaselineSchema, current: BaselineSchema) -> PerfDiff:
    """Compare two baselines, return per-op deltas.

    Rules (D-218 + advisor guidance):
      - matched op, baseline.p99 > 0:
          delta_pct = (current.p99 - baseline.p99) / baseline.p99 * 100
          status = "critical" if delta_pct > 25, else "warn" if > 10, else "ok"
      - matched op, baseline.p99 == 0:
          status = "ok" if current.p99 == 0 else "critical"
      - op only in current → "new"
      - op only in baseline → "missing"
    """
    deltas: list[OpDelta] = []
    baseline_ops = baseline.operations
    current_ops = current.operations

    for name in sorted(set(baseline_ops) | set(current_ops)):
        b = baseline_ops.get(name)
        c = current_ops.get(name)

        if b is not None and c is None:
            deltas.append(
                OpDelta(
                    name=name,
                    baseline_p99_ms=b.p99_ms,
                    current_p99_ms=None,
                    delta_pct=None,
                    status="missing",
                )
            )
            continue
        if b is None and c is not None:
            deltas.append(
                OpDelta(
                    name=name,
                    baseline_p99_ms=None,
                    current_p99_ms=c.p99_ms,
                    delta_pct=None,
                    status="new",
                )
            )
            continue

        assert b is not None and c is not None  # both present

        if b.p99_ms == 0.0:
            status: OpStatus = "ok" if c.p99_ms == 0.0 else "critical"
            deltas.append(
                OpDelta(
                    name=name,
                    baseline_p99_ms=b.p99_ms,
                    current_p99_ms=c.p99_ms,
                    delta_pct=None,
                    status=status,
                )
            )
            continue

        delta_pct = (c.p99_ms - b.p99_ms) / b.p99_ms * 100.0
        if delta_pct > CRITICAL_PCT:
            status = "critical"
        elif delta_pct > WARN_PCT:
            status = "warn"
        else:
            status = "ok"
        deltas.append(
            OpDelta(
                name=name,
                baseline_p99_ms=b.p99_ms,
                current_p99_ms=c.p99_ms,
                delta_pct=delta_pct,
                status=status,
            )
        )

    return PerfDiff(deltas=deltas)


def derive_exit_code(diff: PerfDiff) -> int:
    """Per-op worst case wins. New/missing are informational only."""
    has_warn = False
    for d in diff.deltas:
        if d.status == "critical":
            return EXIT_CRITICAL
        if d.status == "warn":
            has_warn = True
    return EXIT_WARN if has_warn else EXIT_OK


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eldritch-dm-perf-baseline",
        description=(
            "Run the Phase 27 hot-path profiler and diff the result against "
            "a committed baseline JSON. Reports per-op p99 deltas and exits "
            "with a code suitable for CI status."
        ),
        epilog=(
            "Exit codes (D-218):\n"
            "  0 — all p99s within +10% of baseline\n"
            "  1 — at least one p99 > +10% of baseline (regression)\n"
            "  2 — at least one p99 > +25% of baseline (critical)\n"
            "\n"
            "Operators: do NOT commit a new baseline to silence WARN/FAIL — "
            "investigate the regression first. See docs/PERFORMANCE.md "
            "'When to commit a new baseline'."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_DEFAULT_BASELINE,
        help=f"Path to baseline JSON (default: {_DEFAULT_BASELINE}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./perf-runs"),
        help="Output directory for perf-{timestamp}-{sha}.json + .md (default: ./perf-runs).",
    )
    parser.add_argument(
        "--limit-iterations",
        type=int,
        default=100,
        help="Wall-clock iterations per (sub-)path (default: 100).",
    )
    parser.add_argument(
        "--skip-cprofile",
        action="store_true",
        help="Skip cProfile run (faster; cprofile_top_10 will be empty).",
    )
    parser.add_argument(
        "--paths",
        type=str,
        default="",
        help="Comma-separated subset of hot paths (default: all 6).",
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


def _render_markdown_report(diff: PerfDiff, *, baseline_path: Path) -> str:
    """Render a Markdown report for the diff (operator-readable)."""
    lines = [
        "# eldritch-dm-perf-baseline — diff report",
        "",
        f"Baseline: `{baseline_path}`",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "| Operation | Baseline p99 (ms) | Current p99 (ms) | Δ % | Status |",
        "|---|---:|---:|---:|---|",
    ]
    for d in diff.deltas:
        b = f"{d.baseline_p99_ms:.3f}" if d.baseline_p99_ms is not None else "—"
        c = f"{d.current_p99_ms:.3f}" if d.current_p99_ms is not None else "—"
        dp = f"{d.delta_pct:+.1f}%" if d.delta_pct is not None else "—"
        lines.append(f"| {d.name} | {b} | {c} | {dp} | **{d.status.upper()}** |")
    lines.append("")
    lines.append(f"Exit code: **{derive_exit_code(diff)}**")
    lines.append("")
    return "\n".join(lines)


def _invoke_profiler(
    *,
    output: Path,
    iterations: int,
    skip_cprofile: bool,
    paths: str,
) -> int:
    """Invoke ``scripts.perf.profile_hot_paths.main`` in-process.

    Indirection exists so tests can monkeypatch this with a fake that
    writes a deterministic JSON without running the real profiler.
    """
    from scripts.perf.profile_hot_paths import main as profiler_main

    argv = [
        "--output",
        str(output),
        "--iterations",
        str(iterations),
    ]
    if skip_cprofile:
        argv.append("--skip-cprofile")
    if paths:
        argv.extend(["--paths", paths])
    return profiler_main(argv)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.baseline.is_file():
        log.error("perf_baseline.missing_baseline", path=str(args.baseline))
        return EXIT_WARN  # treat unreadable baseline as a regression signal

    try:
        baseline = BaselineSchema.model_validate_json(args.baseline.read_text())
    except (ValueError, OSError) as exc:
        log.error("perf_baseline.invalid_baseline", error=str(exc))
        return EXIT_WARN

    with tempfile.TemporaryDirectory() as tmp:
        tmp_json = Path(tmp) / "current.json"
        rc = _invoke_profiler(
            output=tmp_json,
            iterations=args.limit_iterations,
            skip_cprofile=args.skip_cprofile,
            paths=args.paths,
        )
        if rc != 0:
            log.error("perf_baseline.profiler_failed", returncode=rc)
            return EXIT_WARN
        try:
            current = BaselineSchema.model_validate_json(tmp_json.read_text())
        except (ValueError, OSError) as exc:
            log.error("perf_baseline.invalid_current", error=str(exc))
            return EXIT_WARN

        # Copy the fresh baseline into the output dir alongside the diff.
        args.output.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        sha = _git_short_sha()
        json_path = args.output / f"perf-{timestamp}-{sha}.json"
        md_path = args.output / f"perf-{timestamp}-{sha}.md"

        diff = compute_diff(baseline, current)
        exit_code = derive_exit_code(diff)

        json_payload = {
            "baseline_path": str(args.baseline),
            "current": current.model_dump(),
            "diff": {
                "deltas": [
                    {
                        "name": d.name,
                        "baseline_p99_ms": d.baseline_p99_ms,
                        "current_p99_ms": d.current_p99_ms,
                        "delta_pct": d.delta_pct,
                        "status": d.status,
                    }
                    for d in diff.deltas
                ],
            },
            "exit_code": exit_code,
        }
        json_path.write_text(json.dumps(json_payload, indent=2) + "\n")
        md_path.write_text(_render_markdown_report(diff, baseline_path=args.baseline))

        log.info(
            "perf_baseline.finished",
            exit_code=exit_code,
            json=str(json_path),
            md=str(md_path),
        )
        return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
