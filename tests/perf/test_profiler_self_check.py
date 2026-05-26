"""
Phase 27 / PROFILE-01 — Self-check for the hot-path profiler.

Two cheap tests:

1. ``test_profiler_runs_clean_5_iterations`` — invokes
   ``scripts/perf/profile_hot_paths.py`` as a subprocess with
   ``--iterations 5 --skip-cprofile``. Asserts exit 0, JSON validates,
   all 6 hot paths emit at least one operation entry, wallclock <30 s.

2. ``test_committed_baseline_validates`` — re-validates the committed
   ``.planning/perf-baseline-v1.9.0.json`` against ``BaselineSchema``.
   Skips when the file is missing (so the test exists pre-baseline).

Run with:
    RUN_STRESS=1 pytest tests/perf/ -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Gate behind RUN_STRESS so the default `pytest` run skips this slow test.
pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("RUN_STRESS") != "1",
        reason="Set RUN_STRESS=1 to run the perf-profiler self-check",
    ),
]

# Worktree-safe: anchor everything at the repo root via this file's location.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILER = _REPO_ROOT / "scripts" / "perf" / "profile_hot_paths.py"
_COMMITTED_BASELINE = _REPO_ROOT / ".planning" / "perf-baseline-v1.9.0.json"

# Ensure the script's parent of `scripts/perf/_schema` is importable in this test.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.perf._schema import BaselineSchema  # noqa: E402

# The 6 top-level hot paths (with sub-paths) that must appear in the output.
_REQUIRED_PREFIXES = (
    "mcp-cache-roundtrip",
    "smart-driver-oracle",
    "character-ingest-fast-path",
    "ingest-pipeline-ocr",
    "riposte-click-handler",
    "combat-turn-resolution",
)


def test_profiler_runs_clean_5_iterations(tmp_path: Path) -> None:
    """End-to-end subprocess smoke: profiler exits 0, JSON validates, all paths present."""
    out_path = tmp_path / "baseline_test.json"

    env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "src")}
    # Direct stdout/stderr to files so the pipe buffer can't fill mid-run
    # (the profiler emits a large volume of structlog INFO output; with
    # subprocess.PIPE the kernel buffer caps at ~64 KiB and the writer
    # would block forever).
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"
    t0 = time.monotonic()
    with open(stdout_path, "wb") as out_fp, open(stderr_path, "wb") as err_fp:
        result = subprocess.run(
            [
                sys.executable,
                "-u",
                str(_PROFILER),
                "--iterations",
                "5",
                "--skip-cprofile",
                "--output",
                str(out_path),
            ],
            stdout=out_fp,
            stderr=err_fp,
            env=env,
            cwd=str(_REPO_ROOT),
        )
    stderr_tail = stderr_path.read_text()[-2000:] if stderr_path.exists() else ""
    wallclock_s = time.monotonic() - t0

    assert result.returncode == 0, (
        f"profiler exited {result.returncode}\n--- stderr ---\n{stderr_tail}"
    )
    assert wallclock_s < 30.0, f"profiler took {wallclock_s:.1f}s (>30s smoke ceiling)"
    assert out_path.exists(), "profiler should have written the output JSON"

    # Validate against the canonical schema.
    payload = json.loads(out_path.read_text())
    doc = BaselineSchema.model_validate(payload)
    assert doc.version == "1.9.0"
    assert doc.git_sha != ""
    assert len(doc.operations) >= len(_REQUIRED_PREFIXES)

    # Every required hot-path prefix must have at least one entry (top-level
    # or sub-path, e.g. "mcp-cache-roundtrip.l1-hit").
    op_keys = list(doc.operations.keys())
    for prefix in _REQUIRED_PREFIXES:
        assert any(k == prefix or k.startswith(prefix + ".") for k in op_keys), (
            f"hot path {prefix!r} missing from output (got {op_keys!r})"
        )

    # Every entry must have non-negative percentiles + exactly 5 iterations.
    for name, stats in doc.operations.items():
        assert stats.iterations == 5, f"{name}: expected 5 iter, got {stats.iterations}"
        assert stats.p50_ms >= 0.0
        assert stats.p95_ms >= stats.p50_ms  # nearest-rank guarantee
        assert stats.p99_ms >= stats.p95_ms
        assert stats.cprofile_top_10 == []  # --skip-cprofile


def test_committed_baseline_validates() -> None:
    """The committed v1.9.0 baseline must re-validate against BaselineSchema."""
    if not _COMMITTED_BASELINE.exists():
        pytest.skip(
            f"{_COMMITTED_BASELINE} not yet committed — test will activate "
            "after Task 9 of plan 27-01."
        )
    payload = json.loads(_COMMITTED_BASELINE.read_text())
    doc = BaselineSchema.model_validate(payload)
    assert doc.version == "1.9.0", "committed baseline must be tagged v1.9.0"
    # Every required hot-path prefix must appear.
    op_keys = list(doc.operations.keys())
    for prefix in _REQUIRED_PREFIXES:
        assert any(k == prefix or k.startswith(prefix + ".") for k in op_keys), (
            f"committed baseline missing {prefix!r}"
        )
