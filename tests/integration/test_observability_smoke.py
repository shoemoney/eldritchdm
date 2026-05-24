"""Phase 11 / OBS-02 smoke test.

Brings up no infrastructure itself — assumes the operator (or a manual CI
step) has already run::

    docker compose -f docker-compose.observability.yml up -d

Then with ``OBSERVABILITY_ENABLED=true`` set, emits 5 spans via
``traced_decision`` and asserts ``BatchSpanProcessor.force_flush()`` returns
``True`` within 10 seconds — i.e. the OTLP HTTP exporter resolved the
endpoint and Phoenix accepted the bytes.

Skips cleanly when:

- the ``docker`` Python lib is not installed,
- the docker daemon is not reachable,
- Phoenix is not running on the configured base URL,
- the ``opentelemetry`` SDK is not installed.

Operator-side verification (NOT automated by this test): open the Phoenix UI
and confirm spans named ``eldritch.monster.decision`` with
``eldritch.channel.id="obs-smoke"`` appear. Phoenix's HTTP query surface
has drifted across versions, so we do NOT bake a poll path here — that's a
follow-up task once ``arize-phoenix-client`` is integrated.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def phoenix_running() -> None:
    """Skip if docker / Phoenix unavailable."""
    pytest.importorskip("docker")
    import docker  # noqa: PLC0415

    try:
        client = docker.from_env()
        client.ping()
    except Exception:  # noqa: BLE001 — env-detection layer
        pytest.skip("docker daemon unavailable")

    base_url = os.environ.get("PHOENIX_BASE_URL", "http://localhost:6006")
    try:
        urllib.request.urlopen(base_url + "/", timeout=3).read()  # noqa: S310
    except (urllib.error.URLError, TimeoutError, OSError):
        pytest.skip(f"Phoenix container not reachable at {base_url}")


def test_five_spans_force_flush(
    phoenix_running: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Five emitted spans + a force_flush() returning True = exporter wired end-to-end."""
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:6006/v1/traces"
        ),
    )

    pytest.importorskip("opentelemetry.sdk.trace")
    from eldritch_dm.observability import instrumentation, traced_decision  # noqa: PLC0415
    from eldritch_dm.observability.tracer import init_tracing  # noqa: PLC0415

    # Force a fresh init each invocation
    instrumentation._TRACER = None
    assert init_tracing() is True, "init_tracing returned False with env enabled"

    try:
        for i in range(5):
            with traced_decision(
                monster_id=f"goblin-{i}",
                channel_id="obs-smoke",
                combat_round=i + 1,
                driver_path="smart",
            ) as span:
                span.set_attribute("eldritch.latency_ms", 400 + i)
                span.set_attribute("eldritch.tokens.input", 100)
                span.set_attribute("eldritch.tokens.output", 20)

        from opentelemetry import trace  # noqa: PLC0415

        provider = trace.get_tracer_provider()
        assert hasattr(
            provider, "force_flush"
        ), "TracerProvider lacks force_flush — wrong provider class"
        flushed = provider.force_flush(timeout_millis=10000)
        assert flushed, (
            "BatchSpanProcessor.force_flush returned False — exporter unreachable "
            "or dropped spans"
        )
    finally:
        instrumentation._TRACER = None
