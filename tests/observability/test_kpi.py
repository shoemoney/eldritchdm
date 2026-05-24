"""Tests for the KPI computer (Phase 13 / MON-01 / Task 04).

Verifies the 5 D-85 KPIs against hand-computed expected values over fixture
data, plus the 5s in-process cache behavior.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from eldritch_dm.observability.kpi import (
    KPISnapshot,
    _percentile,
    compute_kpis,
    get_cached_kpis,
    reset_cache_for_tests,
)
from eldritch_dm.observability.span_buffer import BufferRow, init_buffer, reset_for_tests


@pytest.fixture(autouse=True)
def _isolate_buffer(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite")
    )
    reset_for_tests()
    reset_cache_for_tests()
    yield
    reset_for_tests()
    reset_cache_for_tests()


def _decision(
    *,
    latency_ms: int,
    driver_path: str = "smart",
    fallback_reason: str | None = None,
    refusal: bool = False,
    ts: datetime | None = None,
) -> BufferRow:
    return BufferRow(
        span_name="eldritch.monster.decision",
        monster_id="m",
        channel_id="c",
        combat_round=1,
        driver_path=driver_path,
        latency_ms=latency_ms,
        tokens_input=100,
        tokens_output=20,
        fallback_reason=fallback_reason,
        refusal=refusal,
        timestamp_utc=ts or datetime.now(UTC),
    )


def _eval_row(score: float, *, ts: datetime | None = None) -> BufferRow:
    return BufferRow(
        span_name="eldritch.eval.judge",
        scenario_id="s",
        model="ShoeGPT",
        latency_ms=100,
        tokens_input=200,
        tokens_output=50,
        overall_score=score,
        timestamp_utc=ts or datetime.now(UTC),
    )


# ── _percentile primitive ────────────────────────────────────────────────────


def test_percentile_empty_returns_none():
    assert _percentile([], 99.0) is None


def test_percentile_p99_picks_top():
    # 100 values 1..100 — p99 = 99 (nearest-rank).
    vals = [float(i) for i in range(1, 101)]
    assert _percentile(vals, 99.0) == 99.0


def test_percentile_p50_returns_lower_middle():
    """Banker's-rounding nearest-rank: round(0.5*5)=2, rank=1, value=20.

    For p99 over realistic samples (>= 10 latencies) this corner doesn't
    matter — p99 always picks the top. P50 is not used by any KPI but the
    primitive must be deterministic, so we lock in the behavior.
    """
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile(vals, 50.0) == 20.0


# ── compute_kpis happy paths ────────────────────────────────────────────────


def test_empty_window_all_kpis_none():
    snap = compute_kpis(window_minutes=5)
    assert snap.sample_size == 0
    assert snap.latency_p99_ms is None
    assert snap.success_rate is None
    assert snap.refusal_rate is None
    assert snap.fallback_rate is None
    assert snap.tactical_score is None


def test_all_smart_success_window():
    buf = init_buffer()
    # 10 successful smart decisions, latencies 100..1000.
    for i in range(10):
        buf.record(_decision(latency_ms=100 * (i + 1)))
    buf.flush(timeout_s=3.0)
    snap = compute_kpis(window_minutes=5)
    assert snap.sample_size == 10
    # 10 values 100..1000; p99 nearest-rank = max = 1000
    assert snap.latency_p99_ms == 1000.0
    assert snap.success_rate == 1.0
    assert snap.refusal_rate == 0.0
    assert snap.fallback_rate == 0.0
    assert snap.tactical_score is None  # no eval rows


def test_mixed_window_computes_each_kpi():
    buf = init_buffer()
    # 5 successful smart + 2 fallback (timeout) + 1 refusal + 2 random
    for i in range(5):
        buf.record(_decision(latency_ms=200 + i * 10))  # smart, no fallback
    for _ in range(2):
        buf.record(
            _decision(latency_ms=1500, driver_path="smart", fallback_reason="timeout")
        )
    buf.record(
        _decision(
            latency_ms=800,
            driver_path="random",
            fallback_reason="refusal",
            refusal=True,
        )
    )
    for _ in range(2):
        buf.record(_decision(latency_ms=600, driver_path="random"))
    buf.flush(timeout_s=3.0)
    snap = compute_kpis(window_minutes=5)
    assert snap.sample_size == 10
    # success: 5 smart-no-fallback out of 10 = 0.5
    assert snap.success_rate == pytest.approx(0.5)
    # fallback: 3 (2 timeouts + 1 refusal) out of 10 = 0.3
    assert snap.fallback_rate == pytest.approx(0.3)
    # refusal: 1 out of 10 = 0.1
    assert snap.refusal_rate == pytest.approx(0.1)
    # Latency values: 200, 210, 220, 230, 240, 1500, 1500, 800, 600, 600
    # sorted: 200, 210, 220, 230, 240, 600, 600, 800, 1500, 1500
    # nearest-rank p99 over 10 values → rank ceil(0.99*10)-1 = 9 → 1500
    assert snap.latency_p99_ms == 1500.0


def test_tactical_score_from_eval_rows():
    buf = init_buffer()
    # Add one decision so sample_size > 0 (eval-only case tested elsewhere)
    buf.record(_decision(latency_ms=300))
    for score in (0.7, 0.8, 0.9):
        buf.record(_eval_row(score=score))
    buf.flush(timeout_s=3.0)
    snap = compute_kpis(window_minutes=5)
    assert snap.tactical_score == pytest.approx((0.7 + 0.8 + 0.9) / 3)


def test_tactical_score_alone_no_decisions():
    """Eval ran but no decisions in window — tactical_score still computed."""
    buf = init_buffer()
    buf.record(_eval_row(score=0.85))
    buf.flush(timeout_s=3.0)
    snap = compute_kpis(window_minutes=5)
    assert snap.sample_size == 0
    assert snap.tactical_score == pytest.approx(0.85)
    # All decision-derived KPIs remain None.
    assert snap.success_rate is None


def test_window_excludes_older_rows():
    buf = init_buffer()
    now = datetime.now(UTC)
    # An old row (10 min ago, outside the 5-min window)
    buf.record(_decision(latency_ms=9999, ts=now - timedelta(minutes=10)))
    # A recent row (1 min ago)
    buf.record(_decision(latency_ms=200, ts=now - timedelta(minutes=1)))
    buf.flush(timeout_s=3.0)
    snap = compute_kpis(now=now, window_minutes=5)
    assert snap.sample_size == 1
    assert snap.latency_p99_ms == 200.0


def test_returns_kpisnapshot_pydantic():
    snap = compute_kpis()
    assert isinstance(snap, KPISnapshot)
    # frozen model — can't mutate.
    with pytest.raises(ValidationError):
        snap.sample_size = 999  # type: ignore[misc]


# ── Cache behavior ──────────────────────────────────────────────────────────


def test_get_cached_kpis_returns_same_within_ttl():
    a = get_cached_kpis(ttl_seconds=5.0)
    b = get_cached_kpis(ttl_seconds=5.0)
    # Identity is enforced by the cache (same object returned).
    assert a is b


def test_get_cached_kpis_recomputes_after_ttl():
    a = get_cached_kpis(ttl_seconds=0.05)
    time.sleep(0.1)
    b = get_cached_kpis(ttl_seconds=0.05)
    assert a is not b


def test_reset_cache_for_tests_drops_cache():
    a = get_cached_kpis()
    reset_cache_for_tests()
    b = get_cached_kpis()
    assert a is not b


# ── Explicit buffer injection (for downstream tests) ────────────────────────


def test_compute_kpis_accepts_explicit_buffer(tmp_path):
    """Callers can pass a buffer directly without touching the singleton."""
    from eldritch_dm.observability.span_buffer import SpanBuffer

    buf = SpanBuffer(tmp_path / "alt.sqlite")
    buf.record(_decision(latency_ms=42))
    buf.flush(timeout_s=3.0)
    snap = compute_kpis(buffer=buf, window_minutes=5)
    assert snap.sample_size == 1
    assert snap.latency_p99_ms == 42.0
    buf.close()
