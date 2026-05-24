"""Alert evaluator cold-start replay runs at bot boot (Phase 13 / Task 06)."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest

from eldritch_dm.bot import __main__ as bot_main
from eldritch_dm.observability.alert_evaluator import boot_alert_evaluator
from eldritch_dm.observability.alerts_loader import AlertRule
from eldritch_dm.observability.degraded_mode import get_degraded_mode
from eldritch_dm.observability.span_buffer import (
    BufferRow,
    init_buffer,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite"))
    monkeypatch.delenv("OBSERVABILITY_ENABLED", raising=False)
    monkeypatch.delenv("OBSERVABILITY_METRICS_ENDPOINT", raising=False)
    get_degraded_mode().reset_for_tests()
    reset_for_tests()
    yield
    get_degraded_mode().reset_for_tests()
    reset_for_tests()


def test_boot_alert_evaluator_returns_none_when_observability_off():
    """No env gate set → boot helper is a no-op."""
    assert boot_alert_evaluator() is None
    assert get_degraded_mode().is_active() is False


def test_boot_helper_called_from_bot_main():
    """bot.__main__.main wires boot_alert_evaluator() into startup."""
    src = inspect.getsource(bot_main.main)
    assert "boot_alert_evaluator" in src


def test_boot_alert_evaluator_cold_start_trip_when_buffer_breaches(monkeypatch):
    """With observability on + pre-seeded breach data, boot trips degraded mode."""
    monkeypatch.setenv("OBSERVABILITY_METRICS_ENDPOINT", "true")

    buf = init_buffer()
    now = datetime.now(UTC)
    # 5 one-minute buckets each with breach rows.
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

    # The default rules from database/alerts.yaml include the critical
    # latency-breach rule that boot_alert_evaluator will pick up. But we
    # cannot rely on the default file being readable from this test's CWD;
    # patch load_alerts to return a controlled rule.
    from eldritch_dm.observability import alerts_loader as al_mod

    custom_rules = (
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
    monkeypatch.setattr(al_mod, "load_alerts", lambda settings=None: custom_rules)

    ev = boot_alert_evaluator()
    assert ev is not None
    # Cold-start replay tripped immediately.
    assert get_degraded_mode().is_active() is True
    assert "cold_start_replay" in (get_degraded_mode().snapshot().reason or "")
