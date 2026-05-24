"""Tests for the Prometheus /metrics endpoint (Phase 13 / MON-01 / Task 05)."""

from __future__ import annotations

import time
import urllib.request
from datetime import UTC, datetime

import pytest

from eldritch_dm.observability.kpi import reset_cache_for_tests
from eldritch_dm.observability.metrics_endpoint import (
    get_endpoint_port,
    is_metrics_endpoint_enabled,
    start_metrics_endpoint,
    stop_for_tests,
)
from eldritch_dm.observability.span_buffer import BufferRow, init_buffer, reset_for_tests


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite")
    )
    reset_for_tests()
    reset_cache_for_tests()
    stop_for_tests()
    yield
    stop_for_tests()
    reset_for_tests()
    reset_cache_for_tests()


def _scrape(port: int) -> str:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/metrics", timeout=3.0
    ) as resp:
        return resp.read().decode("utf-8")


# ── Env gate ────────────────────────────────────────────────────────────────


def test_is_metrics_endpoint_enabled_false_by_default(monkeypatch):
    monkeypatch.delenv("OBSERVABILITY_METRICS_ENDPOINT", raising=False)
    assert is_metrics_endpoint_enabled() is False


def test_is_metrics_endpoint_enabled_truthy_strings(monkeypatch):
    for val in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("OBSERVABILITY_METRICS_ENDPOINT", val)
        assert is_metrics_endpoint_enabled() is True


def test_start_metrics_endpoint_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("OBSERVABILITY_METRICS_ENDPOINT", raising=False)
    assert start_metrics_endpoint() is False
    assert get_endpoint_port() is None


# ── Live endpoint serves the gauges ─────────────────────────────────────────


def test_endpoint_exposes_5_kpi_gauges(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_METRICS_ENDPOINT", "true")
    # port=0 → ephemeral; metrics_endpoint resolves the real port.
    monkeypatch.setenv("OBSERVABILITY_METRICS_PORT", "0")
    assert start_metrics_endpoint() is True
    port = get_endpoint_port()
    assert port is not None and port > 0
    # The gauge name appears in the # HELP/# TYPE preamble as soon as the
    # registry is built, so we don't need to wait for the refresh tick for
    # this assertion. But poll briefly to avoid races on slow CI.
    deadline = time.time() + 3.0
    expected_names = (
        "eldritch_smart_driver_latency_p99_ms",
        "eldritch_smart_driver_success_rate",
        "eldritch_smart_driver_tactical_score",
        "eldritch_smart_driver_refusal_rate",
        "eldritch_smart_driver_fallback_rate",
    )
    while time.time() < deadline:
        body = _scrape(port)
        if all(name in body for name in expected_names):
            return
        time.sleep(0.1)
    raise AssertionError(
        f"gauges never appeared within 3s; final body:\n{body[:1500]}"
    )


def test_endpoint_decision_counter_increments_on_buffer_write(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_METRICS_ENDPOINT", "true")
    monkeypatch.setenv("OBSERVABILITY_METRICS_PORT", "0")
    assert start_metrics_endpoint() is True
    port = get_endpoint_port()
    assert port is not None

    # Record 3 decisions of varying paths.
    buf = init_buffer()
    buf.record(
        BufferRow(
            span_name="eldritch.monster.decision",
            monster_id="m1",
            channel_id="c1",
            combat_round=1,
            driver_path="smart",
            latency_ms=200,
            tokens_input=100,
            tokens_output=20,
            timestamp_utc=datetime.now(UTC),
        )
    )
    buf.record(
        BufferRow(
            span_name="eldritch.monster.decision",
            monster_id="m2",
            channel_id="c2",
            combat_round=1,
            driver_path="random",
            latency_ms=10,
            fallback_reason="timeout",
            timestamp_utc=datetime.now(UTC),
        )
    )
    buf.record(
        BufferRow(
            span_name="eldritch.monster.decision",
            monster_id="m3",
            channel_id="c3",
            combat_round=1,
            driver_path="smart",
            latency_ms=300,
            tokens_input=100,
            tokens_output=20,
            timestamp_utc=datetime.now(UTC),
        )
    )
    buf.flush(timeout_s=2.0)

    # Counter increments synchronously via the observer hook — scrape now.
    body = _scrape(port)
    assert "eldritch_smart_driver_decisions_total" in body
    # Labels are present.
    assert 'driver_path="smart"' in body
    assert 'driver_path="random"' in body
    assert 'fallback_reason="timeout"' in body


def test_endpoint_idempotent_start(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_METRICS_ENDPOINT", "true")
    monkeypatch.setenv("OBSERVABILITY_METRICS_PORT", "0")
    assert start_metrics_endpoint() is True
    port_a = get_endpoint_port()
    assert start_metrics_endpoint() is True
    port_b = get_endpoint_port()
    assert port_a == port_b


def test_endpoint_publishes_nan_for_empty_kpis(monkeypatch):
    """No spans → gauges publish NaN (Prometheus 'absent' compatible)."""
    monkeypatch.setenv("OBSERVABILITY_METRICS_ENDPOINT", "true")
    monkeypatch.setenv("OBSERVABILITY_METRICS_PORT", "0")
    assert start_metrics_endpoint() is True
    port = get_endpoint_port()
    assert port is not None

    # Poll up to 3s for the first refresh tick to populate gauges. The
    # refresh thread fires once on startup, but it has to run SQLite query
    # + acquire the buffer lock — sub-second on a quiet machine, but CI
    # can be slow. Polling avoids a flaky sleep.
    deadline = time.time() + 3.0
    while time.time() < deadline:
        body = _scrape(port)
        if "eldritch_smart_driver_latency_p99_ms NaN" in body:
            return
        time.sleep(0.1)
    raise AssertionError(
        f"gauge never published NaN within 3s; final body:\n{body[:1500]}"
    )
