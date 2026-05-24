"""Lazy OpenTelemetry TracerProvider setup (Phase 11 / OBS-01 / D-62, D-65d).

Module-level invariant: importing this module MUST NOT import
``opentelemetry``. All OTel imports happen inside :func:`init_tracing` and
are guarded by ``is_enabled()`` so a startup with
``OBSERVABILITY_ENABLED=false`` (the default) pays nothing.

The lazy-import invariant is verified by
``tests/observability/test_lazy_import.py``.

Public API:

- :func:`is_enabled` — read the ``OBSERVABILITY_ENABLED`` env var.
- :func:`init_tracing` — set up ``TracerProvider`` + ``OTLPSpanExporter``
  + ``BatchSpanProcessor`` if enabled, else return ``False`` immediately.
  Idempotent.
"""

from __future__ import annotations

import os

from eldritch_dm.logging import get_logger
from eldritch_dm.observability import instrumentation

log = get_logger(__name__)

#: Default OTLP/HTTP endpoint — Phoenix's unified port (D-64). Operators can
#: override via ``OTEL_EXPORTER_OTLP_ENDPOINT`` (e.g. ``:4318/v1/traces`` if
#: their Phoenix image disabled the unified port).
DEFAULT_ENDPOINT = "http://localhost:6006/v1/traces"

#: ``service.name`` attribute on every emitted span.
SERVICE_NAME = "eldritch-dm"


def is_enabled() -> bool:
    """Return True iff ``OBSERVABILITY_ENABLED`` env is a truthy string."""
    return os.environ.get("OBSERVABILITY_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def init_tracing() -> bool:
    """Initialize OTel tracing if enabled. Idempotent.

    Returns:
        True if tracing is active after this call (newly initialized or
        already-initialized); False if observability is disabled by env.
    """
    if not is_enabled():
        log.info("observability_disabled")
        return False
    if instrumentation._TRACER is not None:
        # Already initialized — idempotent re-entry.
        return True

    # ── Lazy OTel imports — only paid when enabled (D-65d) ───────────────────
    from opentelemetry import trace  # noqa: PLC0415
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_ENDPOINT)
    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    instrumentation._TRACER = trace.get_tracer(SERVICE_NAME)
    log.info(
        "observability_enabled",
        endpoint=endpoint,
        service=SERVICE_NAME,
    )
    return True
