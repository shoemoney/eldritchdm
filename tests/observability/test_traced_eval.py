"""traced_eval span (eldritch.eval.judge) tests — Phase 12 / D-81.

Mirrors the in-memory exporter fixture pattern from test_span_attributes.py.
"""

from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry.sdk.trace")


@pytest.fixture
def in_memory_tracer():  # type: ignore[no-untyped-def]
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from eldritch_dm.observability import instrumentation

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    original = instrumentation._TRACER
    instrumentation._TRACER = provider.get_tracer("eldritch-test")
    try:
        yield exporter
    finally:
        instrumentation._TRACER = original
        exporter.clear()


REQUIRED_EVAL_ATTRS = {
    "eldritch.eval.scenario_id",
    "eldritch.eval.judge_model",
    "eldritch.eval.driver_model",
    "eldritch.eval.archetype",
}


def test_traced_eval_noop_when_tracer_disabled() -> None:
    """With _TRACER = None (default), the context manager is a no-op."""
    from eldritch_dm.observability import traced_eval

    # Don't touch the fixture — _TRACER must be None at module import time.
    with traced_eval(
        scenario_id="brute-001",
        judge_model="ShoeGPT",
        driver_model="ShoeGPT",
        archetype="brute",
    ) as span:
        # set_attribute on the noop span must not raise.
        span.set_attribute("eldritch.eval.latency_ms", 100)


def test_traced_eval_emits_span_with_d81_attributes(in_memory_tracer) -> None:  # type: ignore[no-untyped-def]
    from eldritch_dm.observability import traced_eval

    with traced_eval(
        scenario_id="brute-001",
        judge_model="ShoeGPT",
        driver_model="ShoeGPT",
        archetype="brute",
    ) as span:
        span.set_attribute("eldritch.eval.latency_ms", 412)
        span.set_attribute("eldritch.eval.tokens.input", 120)
        span.set_attribute("eldritch.eval.tokens.output", 18)
        span.set_attribute("eldritch.eval.overall_score", 0.85)

    spans = in_memory_tracer.get_finished_spans()
    assert len(spans) == 1
    s = spans[0]
    assert s.name == "eldritch.eval.judge"
    attrs = dict(s.attributes or {})
    missing = REQUIRED_EVAL_ATTRS - set(attrs)
    assert not missing, f"D-81 required attrs missing: {missing}"
    assert attrs["eldritch.eval.scenario_id"] == "brute-001"
    assert attrs["eldritch.eval.judge_model"] == "ShoeGPT"
    assert attrs["eldritch.eval.driver_model"] == "ShoeGPT"
    assert attrs["eldritch.eval.archetype"] == "brute"
    assert attrs["eldritch.eval.latency_ms"] == 412
    assert attrs["eldritch.eval.overall_score"] == 0.85
