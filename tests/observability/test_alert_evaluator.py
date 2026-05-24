"""Tests for AlertEvaluator hysteresis + cold-start replay (Phase 13 / Task 04)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from eldritch_dm.observability.alert_evaluator import (
    DEFAULT_RECOVER_THRESHOLD_FACTOR,
    AlertEvaluator,
    _evaluate,
    _invert_op,
)
from eldritch_dm.observability.alerts_loader import AlertRule
from eldritch_dm.observability.degraded_mode import get_degraded_mode
from eldritch_dm.observability.kpi import KPISnapshot
from eldritch_dm.observability.span_buffer import BufferRow, init_buffer, reset_for_tests


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite")
    )
    get_degraded_mode().reset_for_tests()
    reset_for_tests()
    yield
    get_degraded_mode().reset_for_tests()
    reset_for_tests()


def _make_snapshot(
    *,
    latency_p99_ms: float | None = None,
    success_rate: float | None = None,
    fallback_rate: float | None = None,
    refusal_rate: float | None = None,
    tactical_score: float | None = None,
    sample_size: int = 1,
) -> KPISnapshot:
    return KPISnapshot(
        latency_p99_ms=latency_p99_ms,
        success_rate=success_rate,
        tactical_score=tactical_score,
        refusal_rate=refusal_rate,
        fallback_rate=fallback_rate,
        window_seconds=300,
        sample_size=sample_size,
        computed_at_utc=datetime.now(UTC),
    )


# ── primitives ──────────────────────────────────────────────────────────────


def test_evaluate_none_always_false():
    assert _evaluate(None, "gt", 100) is False


def test_evaluate_ops():
    assert _evaluate(150, "gt", 100) is True
    assert _evaluate(100, "gt", 100) is False
    assert _evaluate(100, "gte", 100) is True
    assert _evaluate(50, "lt", 100) is True
    assert _evaluate(100, "lte", 100) is True


def test_invert_op():
    assert _invert_op("gt") == "lt"
    assert _invert_op("gte") == "lte"
    assert _invert_op("lt") == "gt"


# ── tick: degrade + hysteresis ──────────────────────────────────────────────


def test_degrade_trips_after_window_consecutive_breaches():
    """5 consecutive ticks at 1min each = 5min; trip at the 5th."""
    rules = (
        AlertRule(
            name="crit_latency",
            severity="critical",
            kpi="latency_p99_ms",
            op="gt",
            threshold=1500,
            window_minutes=5,
            action="degrade",
        ),
    )
    snapshots = [
        _make_snapshot(latency_p99_ms=1800) for _ in range(5)
    ]
    iter_snapshots = iter(snapshots)
    ev = AlertEvaluator(rules, kpi_provider=lambda: next(iter_snapshots))
    ev._tick_seconds = 60.0  # 1 tick = 1 minute → 5 ticks = 5 min

    for i in range(4):
        r = ev.tick()
        assert r.tripped_degrade is False, f"tripped at tick {i+1} (too early)"
        assert get_degraded_mode().is_active() is False

    r = ev.tick()
    assert r.tripped_degrade is True
    assert get_degraded_mode().is_active() is True


def test_degrade_does_not_trip_when_one_tick_misses():
    """Window of 5; if even ONE tick is under threshold, count resets."""
    rules = (
        AlertRule(
            name="crit_latency",
            severity="critical",
            kpi="latency_p99_ms",
            op="gt",
            threshold=1500,
            window_minutes=5,
            action="degrade",
        ),
    )
    # 3 over, 1 under (resets), then 1 over → total only 1 consecutive
    seq = [
        _make_snapshot(latency_p99_ms=1800),
        _make_snapshot(latency_p99_ms=1800),
        _make_snapshot(latency_p99_ms=1800),
        _make_snapshot(latency_p99_ms=900),
        _make_snapshot(latency_p99_ms=1800),
    ]
    it = iter(seq)
    ev = AlertEvaluator(rules, kpi_provider=lambda: next(it))
    ev._tick_seconds = 60.0
    for _ in range(5):
        ev.tick()
    assert get_degraded_mode().is_active() is False


def test_recover_after_window_consecutive_under_recover_threshold():
    """After trip, 5 consecutive ticks under 1200ms (=1500*0.8) → recover."""
    rules = (
        AlertRule(
            name="crit_latency",
            severity="critical",
            kpi="latency_p99_ms",
            op="gt",
            threshold=1500,
            window_minutes=5,
            action="degrade",
        ),
    )
    # First 5 ticks trip; next 5 ticks under 1200 recover.
    seq = (
        [_make_snapshot(latency_p99_ms=1800)] * 5
        + [_make_snapshot(latency_p99_ms=900)] * 5
    )
    it = iter(seq)
    ev = AlertEvaluator(rules, kpi_provider=lambda: next(it))
    ev._tick_seconds = 60.0

    for _ in range(5):
        ev.tick()
    assert get_degraded_mode().is_active() is True

    for i in range(4):
        r = ev.tick()
        assert r.recovered is False, f"recovered at tick {i+1} (too early)"
        assert get_degraded_mode().is_active() is True
    r = ev.tick()
    assert r.recovered is True
    assert get_degraded_mode().is_active() is False


def test_recover_threshold_factor_matches_ai_spec():
    """1200/1500 = 0.8 — the AI-SPEC §7 hysteresis."""
    assert DEFAULT_RECOVER_THRESHOLD_FACTOR == pytest.approx(1200.0 / 1500.0)


def test_recover_not_triggered_when_latency_between_1200_and_1500():
    """A 'lingering bad' state (between recover threshold and trip threshold)
    must NOT recover — that's the whole point of hysteresis."""
    rules = (
        AlertRule(
            name="crit",
            severity="critical",
            kpi="latency_p99_ms",
            op="gt",
            threshold=1500,
            window_minutes=5,
            action="degrade",
        ),
    )
    # Trip with 5 hot ticks, then sit at 1300ms — between recover (1200) and
    # trip (1500). consecutive_breach drops to 0 (1300 not > 1500), but
    # consecutive_recover doesn't accumulate either (1300 not < 1200).
    seq = (
        [_make_snapshot(latency_p99_ms=1800)] * 5
        + [_make_snapshot(latency_p99_ms=1300)] * 20
    )
    it = iter(seq)
    ev = AlertEvaluator(rules, kpi_provider=lambda: next(it))
    ev._tick_seconds = 60.0
    for _ in range(25):
        ev.tick()
    # Still active — hysteresis prevented bounce-back.
    assert get_degraded_mode().is_active() is True


# ── tick: log action ────────────────────────────────────────────────────────


def test_log_action_fires_every_tick_condition_true():
    rules = (
        AlertRule(
            name="high_fallback",
            severity="high",
            kpi="fallback_rate",
            op="gt",
            threshold=0.10,
            window_minutes=5,
            action="log",
        ),
    )
    snap = _make_snapshot(fallback_rate=0.20)
    ev = AlertEvaluator(rules, kpi_provider=lambda: snap)
    r = ev.tick()
    assert "high_fallback" in r.fired
    assert r.tripped_degrade is False
    # Log-only rules never trip degraded mode.
    assert get_degraded_mode().is_active() is False


def test_log_action_does_not_fire_when_under_threshold():
    rules = (
        AlertRule(
            name="high_fallback",
            severity="high",
            kpi="fallback_rate",
            op="gt",
            threshold=0.10,
            action="log",
        ),
    )
    snap = _make_snapshot(fallback_rate=0.05)
    ev = AlertEvaluator(rules, kpi_provider=lambda: snap)
    r = ev.tick()
    assert "high_fallback" not in r.fired


# ── tick: throttle / webhook deferred ──────────────────────────────────────


def test_throttle_and_webhook_emit_deferred_warning():
    rules = (
        AlertRule(
            name="rule_throttle",
            severity="warning",
            kpi="refusal_rate",
            op="gt",
            threshold=0.001,
            action="throttle",
        ),
        AlertRule(
            name="rule_webhook",
            severity="warning",
            kpi="refusal_rate",
            op="gt",
            threshold=0.001,
            action="webhook",
        ),
    )
    snap = _make_snapshot(refusal_rate=0.01)
    ev = AlertEvaluator(rules, kpi_provider=lambda: snap)
    r = ev.tick()
    assert "rule_throttle" in r.fired
    assert "rule_webhook" in r.fired
    # No degrade.
    assert get_degraded_mode().is_active() is False


# ── cold_start_replay ───────────────────────────────────────────────────────


def test_cold_start_replay_trips_when_every_minute_bucket_breaches():
    rules = (
        AlertRule(
            name="crit",
            severity="critical",
            kpi="latency_p99_ms",
            op="gt",
            threshold=1500,
            window_minutes=5,
            action="degrade",
        ),
    )
    buf = init_buffer()
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    # Seed 1 row in each of the last 5 one-minute buckets, all at 1800ms.
    for minute_offset in range(5):
        ts = now - timedelta(minutes=minute_offset, seconds=10)
        buf.record(
            BufferRow(
                span_name="eldritch.monster.decision",
                monster_id="m",
                channel_id="c",
                combat_round=1,
                driver_path="smart",
                latency_ms=1800,
                fallback_reason="timeout",
                timestamp_utc=ts,
            )
        )
    buf.flush(timeout_s=3.0)

    ev = AlertEvaluator(rules, time_source=lambda: now, buffer=buf)
    result = ev.cold_start_replay()
    assert "crit" in result.tripped_rules
    assert get_degraded_mode().is_active() is True
    assert "cold_start_replay" in get_degraded_mode().snapshot().reason


def test_cold_start_replay_does_not_trip_when_one_bucket_misses():
    rules = (
        AlertRule(
            name="crit",
            severity="critical",
            kpi="latency_p99_ms",
            op="gt",
            threshold=1500,
            window_minutes=5,
            action="degrade",
        ),
    )
    buf = init_buffer()
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    # 4 out of 5 buckets breach; one is healthy.
    for minute_offset in range(5):
        latency = 1800 if minute_offset != 2 else 900
        ts = now - timedelta(minutes=minute_offset, seconds=10)
        buf.record(
            BufferRow(
                span_name="eldritch.monster.decision",
                monster_id="m",
                channel_id="c",
                combat_round=1,
                driver_path="smart",
                latency_ms=latency,
                timestamp_utc=ts,
            )
        )
    buf.flush(timeout_s=3.0)
    ev = AlertEvaluator(rules, time_source=lambda: now, buffer=buf)
    result = ev.cold_start_replay()
    assert result.tripped_rules == ()
    assert get_degraded_mode().is_active() is False


def test_cold_start_replay_empty_buffer_noop():
    rules = (
        AlertRule(
            name="crit",
            severity="critical",
            kpi="latency_p99_ms",
            op="gt",
            threshold=1500,
            window_minutes=5,
            action="degrade",
        ),
    )
    ev = AlertEvaluator(rules)
    result = ev.cold_start_replay()
    assert result.tripped_rules == ()
    assert get_degraded_mode().is_active() is False
