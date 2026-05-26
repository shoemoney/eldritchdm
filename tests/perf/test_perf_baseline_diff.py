"""Phase 28 / TUNE-02 — perf-baseline diff pure-function tests.

Tests the diff/exit-code logic in isolation. CLI tests live in
``test_perf_baseline_cli.py``; smoke test lives in
``test_perf_baseline_smoke.py``.
"""

from __future__ import annotations

import pytest

from eldritch_dm.tools.perf_baseline import (
    OpDelta,
    PerfDiff,
    compute_diff,
    derive_exit_code,
)
from scripts.perf._schema import BaselineSchema, OperationStats


def _baseline(ops: dict[str, float]) -> BaselineSchema:
    """Build a BaselineSchema with the given operation→p99_ms mapping."""
    return BaselineSchema(
        version="test",
        git_sha="0" * 40,
        generated_at="2026-05-26T00:00:00+00:00",
        operations={
            name: OperationStats(
                p50_ms=p99 * 0.5,
                p95_ms=p99 * 0.9,
                p99_ms=p99,
                iterations=100,
                cprofile_top_10=[],
            )
            for name, p99 in ops.items()
        },
    )


def test_matched_op_within_tolerance_is_ok():
    base = _baseline({"op-a": 1.0})
    curr = _baseline({"op-a": 1.05})  # +5%
    diff = compute_diff(base, curr)
    assert diff.deltas[0].status == "ok"
    assert derive_exit_code(diff) == 0


def test_matched_op_at_15pct_is_warn():
    base = _baseline({"op-a": 1.0})
    curr = _baseline({"op-a": 1.15})  # +15%
    diff = compute_diff(base, curr)
    assert diff.deltas[0].status == "warn"
    assert derive_exit_code(diff) == 1


def test_matched_op_at_30pct_is_critical():
    base = _baseline({"op-a": 1.0})
    curr = _baseline({"op-a": 1.30})  # +30%
    diff = compute_diff(base, curr)
    assert diff.deltas[0].status == "critical"
    assert derive_exit_code(diff) == 2


def test_baseline_zero_current_positive_is_critical():
    base = _baseline({"op-a": 0.0})
    curr = _baseline({"op-a": 1.0})
    diff = compute_diff(base, curr)
    assert diff.deltas[0].status == "critical"
    assert derive_exit_code(diff) == 2


def test_baseline_zero_current_zero_is_ok():
    base = _baseline({"op-a": 0.0})
    curr = _baseline({"op-a": 0.0})
    diff = compute_diff(base, curr)
    assert diff.deltas[0].status == "ok"
    assert derive_exit_code(diff) == 0


def test_new_op_in_current_is_new_status_no_effect_on_exit():
    base = _baseline({"op-a": 1.0})
    curr = _baseline({"op-a": 1.0, "op-new": 5.0})
    diff = compute_diff(base, curr)
    statuses = {d.name: d.status for d in diff.deltas}
    assert statuses["op-new"] == "new"
    assert derive_exit_code(diff) == 0


def test_missing_op_in_current_is_missing_status_no_effect_on_exit():
    base = _baseline({"op-a": 1.0, "op-gone": 2.0})
    curr = _baseline({"op-a": 1.0})
    diff = compute_diff(base, curr)
    statuses = {d.name: d.status for d in diff.deltas}
    assert statuses["op-gone"] == "missing"
    assert derive_exit_code(diff) == 0


def test_mixed_warn_and_critical_exits_2():
    base = _baseline({"op-a": 1.0, "op-b": 1.0})
    curr = _baseline({"op-a": 1.15, "op-b": 1.30})
    diff = compute_diff(base, curr)
    assert derive_exit_code(diff) == 2


def test_improvement_negative_delta_is_ok():
    base = _baseline({"op-a": 2.0})
    curr = _baseline({"op-a": 1.0})  # -50%, an improvement
    diff = compute_diff(base, curr)
    assert diff.deltas[0].status == "ok"
    assert diff.deltas[0].delta_pct == pytest.approx(-50.0)
    assert derive_exit_code(diff) == 0


def test_perfdiff_structure_returns_opdeltas():
    base = _baseline({"op-a": 1.0})
    curr = _baseline({"op-a": 1.0})
    diff = compute_diff(base, curr)
    assert isinstance(diff, PerfDiff)
    assert all(isinstance(d, OpDelta) for d in diff.deltas)
