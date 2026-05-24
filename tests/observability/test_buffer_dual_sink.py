"""Dual-sink verification: traced_* always writes to span buffer (Phase 13 / Task 03).

R-13-01-a: span buffer is the PRIMARY sink. Whether or not OTel is enabled,
every ``traced_decision`` / ``traced_translate`` / ``traced_eval`` context-
manager exit must write a row to the local SQLite buffer. When OTel is also
enabled, the OTel span is the SECONDARY sink (Phoenix/Grafana visualization
backend).

This file verifies the OTel-OFF path. The OTel-ON path is exercised
incidentally by ``test_span_attributes.py``, but we add a small dual-sink
assertion here to confirm both sinks fire when both are on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from eldritch_dm.observability import (
    traced_decision,
    traced_eval,
    traced_translate,
)
from eldritch_dm.observability.span_buffer import init_buffer, reset_for_tests


@pytest.fixture(autouse=True)
def _isolate_buffer(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite")
    )
    # Force OTel disabled for the OTel-off path tests.
    monkeypatch.delenv("OBSERVABILITY_ENABLED", raising=False)
    reset_for_tests()
    yield
    reset_for_tests()


def test_traced_decision_writes_to_buffer_when_otel_disabled():
    """OTel off → buffer still receives the row with all fixed + dynamic attrs."""
    before = datetime.now(UTC) - timedelta(seconds=1)
    with traced_decision(
        monster_id="m1",
        channel_id="c1",
        combat_round=3,
        driver_path="smart",
    ) as span:
        span.set_attribute("eldritch.latency_ms", 412)
        span.set_attribute("eldritch.tokens.input", 120)
        span.set_attribute("eldritch.tokens.output", 18)
    buf = init_buffer()
    buf.flush(timeout_s=3.0)
    rows = buf.query(since=before, span_name="eldritch.monster.decision")
    assert len(rows) == 1
    r = rows[0]
    assert r.monster_id == "m1"
    assert r.channel_id == "c1"
    assert r.combat_round == 3
    assert r.driver_path == "smart"
    assert r.latency_ms == 412
    assert r.tokens_input == 120
    assert r.tokens_output == 18
    assert r.fallback_reason is None
    assert r.refusal is False


def test_traced_decision_captures_fallback_reason():
    before = datetime.now(UTC) - timedelta(seconds=1)
    with traced_decision(
        monster_id="m2",
        channel_id="c2",
        combat_round=1,
        driver_path="random",
    ) as span:
        span.set_attribute("eldritch.latency_ms", 1500)
        span.set_attribute("eldritch.tokens.input", 0)
        span.set_attribute("eldritch.tokens.output", 0)
        span.set_attribute("eldritch.fallback.reason", "timeout")
    buf = init_buffer()
    buf.flush(timeout_s=3.0)
    rows = buf.query(since=before, span_name="eldritch.monster.decision")
    assert len(rows) == 1
    assert rows[0].fallback_reason == "timeout"
    assert rows[0].driver_path == "random"
    assert rows[0].refusal is False  # only "refusal" reason sets refusal=True


def test_traced_decision_refusal_sets_refusal_flag():
    before = datetime.now(UTC) - timedelta(seconds=1)
    with traced_decision(
        monster_id="m3",
        channel_id="c3",
        combat_round=2,
        driver_path="random",
    ) as span:
        span.set_attribute("eldritch.latency_ms", 800)
        span.set_attribute("eldritch.tokens.input", 100)
        span.set_attribute("eldritch.tokens.output", 0)
        span.set_attribute("eldritch.fallback.reason", "refusal")
    buf = init_buffer()
    buf.flush(timeout_s=3.0)
    rows = buf.query(since=before, span_name="eldritch.monster.decision")
    assert len(rows) == 1
    assert rows[0].refusal is True
    assert rows[0].fallback_reason == "refusal"


def test_traced_translate_writes_to_buffer():
    before = datetime.now(UTC) - timedelta(seconds=1)
    with traced_translate(channel_id="ch-9", model="ShoeGPT") as span:
        span.set_attribute("eldritch.latency_ms", 3200)
        span.set_attribute("eldritch.tokens.input", 480)
        span.set_attribute("eldritch.tokens.output", 220)
        span.set_attribute("eldritch.ingest.parse_error", False)
    buf = init_buffer()
    buf.flush(timeout_s=3.0)
    rows = buf.query(since=before, span_name="eldritch.ingest.translate")
    assert len(rows) == 1
    r = rows[0]
    assert r.channel_id == "ch-9"
    assert r.model == "ShoeGPT"
    assert r.latency_ms == 3200
    assert r.tokens_input == 480
    assert r.tokens_output == 220


def test_traced_eval_writes_to_buffer_with_score():
    before = datetime.now(UTC) - timedelta(seconds=1)
    with traced_eval(
        scenario_id="brute-01",
        judge_model="claude-haiku-4-5-20251001",
        driver_model="ShoeGPT",
        archetype="low-int-brute",
    ) as span:
        span.set_attribute("eldritch.latency_ms", 350)
        span.set_attribute("eldritch.tokens.input", 1500)
        span.set_attribute("eldritch.tokens.output", 400)
        span.set_attribute("eldritch.eval.overall_score", 0.85)
    buf = init_buffer()
    buf.flush(timeout_s=3.0)
    rows = buf.query(since=before, span_name="eldritch.eval.judge")
    assert len(rows) == 1
    r = rows[0]
    assert r.scenario_id == "brute-01"
    assert r.model == "claude-haiku-4-5-20251001"
    assert r.overall_score == pytest.approx(0.85)
    assert r.tokens_input == 1500
    assert r.tokens_output == 400


def test_traced_decision_dual_sink_when_otel_enabled(monkeypatch):
    """Both OTel and buffer receive the row when observability is enabled."""
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from eldritch_dm.observability import instrumentation

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(
        instrumentation, "_TRACER", provider.get_tracer("eldritch-test")
    )

    before = datetime.now(UTC) - timedelta(seconds=1)
    with traced_decision(
        monster_id="m-otel",
        channel_id="c-otel",
        combat_round=5,
        driver_path="smart",
    ) as span:
        span.set_attribute("eldritch.latency_ms", 250)
        span.set_attribute("eldritch.tokens.input", 50)
        span.set_attribute("eldritch.tokens.output", 12)

    # OTel sink fired.
    otel_spans = exporter.get_finished_spans()
    assert len(otel_spans) == 1
    assert otel_spans[0].name == "eldritch.monster.decision"
    otel_attrs = dict(otel_spans[0].attributes or {})
    assert otel_attrs["eldritch.monster.id"] == "m-otel"

    # Buffer sink also fired.
    buf = init_buffer()
    buf.flush(timeout_s=3.0)
    rows = buf.query(since=before, span_name="eldritch.monster.decision")
    assert len(rows) == 1
    assert rows[0].monster_id == "m-otel"
    assert rows[0].latency_ms == 250
