"""Span attribute coverage (Phase 11 / OBS-01 / D-65).

When tracing is enabled and a span is opened, asserts that every required
D-65 attribute is present on the emitted span. Skips cleanly when the
opentelemetry extras are not installed.
"""

from __future__ import annotations

import pytest

# Skip the entire module if OTel SDK is not installed (pip install -e ".[observability]")
pytest.importorskip("opentelemetry.sdk.trace")


@pytest.fixture
def in_memory_tracer():  # type: ignore[no-untyped-def]
    """Provide an in-memory exporter wired into instrumentation._TRACER.

    Restores the sentinel on teardown so subsequent tests see _TRACER=None.
    """
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


REQUIRED_DECISION_ATTRS = {
    "eldritch.monster.id",
    "eldritch.channel.id",
    "eldritch.combat.round",
    "eldritch.driver.path",
    "eldritch.latency_ms",
    "eldritch.tokens.input",
    "eldritch.tokens.output",
    # fallback.reason is OPTIONAL per D-65 (None on success); not asserted here.
}


def test_decision_span_records_all_required_attrs(in_memory_tracer) -> None:  # type: ignore[no-untyped-def]
    """The decision span carries every D-65 mandatory attribute."""
    from eldritch_dm.observability import traced_decision

    with traced_decision(
        monster_id="goblin-7",
        channel_id="ch-42",
        combat_round=3,
        driver_path="smart",
    ) as span:
        span.set_attribute("eldritch.latency_ms", 412)
        span.set_attribute("eldritch.tokens.input", 120)
        span.set_attribute("eldritch.tokens.output", 18)

    spans = in_memory_tracer.get_finished_spans()
    assert len(spans) == 1, f"expected exactly 1 emitted span, got {len(spans)}"
    s = spans[0]
    assert s.name == "eldritch.monster.decision"
    attrs = dict(s.attributes or {})
    missing = REQUIRED_DECISION_ATTRS - set(attrs)
    assert not missing, f"D-65 required attributes missing: {missing}"
    assert attrs["eldritch.monster.id"] == "goblin-7"
    assert attrs["eldritch.channel.id"] == "ch-42"
    assert attrs["eldritch.combat.round"] == 3
    assert attrs["eldritch.driver.path"] == "smart"
    assert attrs["eldritch.latency_ms"] == 412


def test_decision_span_fallback_reason_appears_on_failure(in_memory_tracer) -> None:  # type: ignore[no-untyped-def]
    """When the caller records a fallback reason, it lands on the span."""
    from eldritch_dm.observability import traced_decision

    with traced_decision(
        monster_id="goblin-7",
        channel_id="ch-42",
        combat_round=3,
        driver_path="random",
    ) as span:
        span.set_attribute("eldritch.latency_ms", 1500)
        span.set_attribute("eldritch.tokens.input", 0)
        span.set_attribute("eldritch.tokens.output", 0)
        span.set_attribute("eldritch.fallback.reason", "timeout")

    spans = in_memory_tracer.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes or {})
    assert attrs["eldritch.fallback.reason"] == "timeout"
    assert attrs["eldritch.driver.path"] == "random"


def test_translate_span_records_ingest_subset(in_memory_tracer) -> None:  # type: ignore[no-untyped-def]
    """The ingest span carries the D-65b subset of attributes."""
    from eldritch_dm.observability import traced_translate

    with traced_translate(channel_id="ch-9", model="ShoeGPT") as span:
        span.set_attribute("eldritch.latency_ms", 3200)
        span.set_attribute("eldritch.tokens.input", 480)
        span.set_attribute("eldritch.tokens.output", 220)
        span.set_attribute("eldritch.ingest.parse_error", False)

    spans = in_memory_tracer.get_finished_spans()
    assert len(spans) == 1
    s = spans[0]
    assert s.name == "eldritch.ingest.translate"
    attrs = dict(s.attributes or {})
    for key in (
        "eldritch.channel.id",
        "eldritch.ingest.model",
        "eldritch.latency_ms",
        "eldritch.tokens.input",
        "eldritch.tokens.output",
        "eldritch.ingest.parse_error",
    ):
        assert key in attrs, f"missing ingest attribute {key}"
    assert attrs["eldritch.channel.id"] == "ch-9"
    assert attrs["eldritch.ingest.model"] == "ShoeGPT"
    assert attrs["eldritch.ingest.parse_error"] is False


def test_init_tracing_returns_true_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When OBSERVABILITY_ENABLED=true, init_tracing wires the provider."""
    from eldritch_dm.observability import instrumentation, tracer

    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    monkeypatch.setattr(instrumentation, "_TRACER", None)
    try:
        assert tracer.init_tracing() is True
        assert instrumentation._TRACER is not None
        # Idempotent — second call also returns True without re-wiring.
        assert tracer.init_tracing() is True
    finally:
        instrumentation._TRACER = None
