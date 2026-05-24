"""Disabled-mode no-op behavior (Phase 11 / OBS-01)."""

from __future__ import annotations

import pytest

from eldritch_dm.observability import (
    instrumentation,
    traced_decision,
    traced_translate,
)


@pytest.fixture(autouse=True)
def _ensure_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the disabled-mode sentinel for every test in this module."""
    monkeypatch.delenv("OBSERVABILITY_ENABLED", raising=False)
    monkeypatch.setattr(instrumentation, "_TRACER", None)


def test_traced_decision_disabled_yields_noop_span() -> None:
    """When _TRACER is None, traced_decision yields a no-op span."""
    with traced_decision(
        monster_id="goblin-1",
        channel_id="ch-1",
        combat_round=1,
        driver_path="smart",
    ) as span:
        # All Span-API methods we use must accept calls without raising.
        span.set_attribute("eldritch.latency_ms", 412)
        span.set_attribute("eldritch.tokens.input", 100)
        span.set_attribute("eldritch.tokens.output", 20)
        span.set_attribute("eldritch.fallback.reason", "timeout")
        span.set_attributes({"foo": "bar"})
        span.record_exception(RuntimeError("synthetic"))
        span.set_status("ok")


def test_traced_translate_disabled_yields_noop_span() -> None:
    """Same invariant for the ingest span helper."""
    with traced_translate(channel_id="ch-1", model="ShoeGPT") as span:
        span.set_attribute("eldritch.latency_ms", 100)
        span.set_attribute("eldritch.ingest.parse_error", False)


def test_noop_span_is_not_otel_span() -> None:
    """The OTel-off span must be the pure-Python proxy — no OTel coupling.

    Phase 13 / R-13-01-a renamed the proxy from ``_NoopSpan`` to
    ``_BufferingSpan`` (because it now also writes to the local SQLite buffer
    even when OTel is off). The invariant being protected is still:
    the yielded object lives in ``eldritch_dm.observability``, NOT
    ``opentelemetry``.
    """
    with traced_decision(
        monster_id="m", channel_id="c", combat_round=1, driver_path="smart"
    ) as span:
        cls = type(span)
        assert cls.__module__.startswith("eldritch_dm.observability"), (
            f"OTel-off path yielded {cls.__module__}.{cls.__name__} — "
            "expected our pure-Python proxy"
        )
        assert "opentelemetry" not in cls.__module__
