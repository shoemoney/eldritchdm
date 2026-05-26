"""EldritchDM observability package (Phase 11 / OBS-01).

Lazy OpenTelemetry instrumentation. Off by default (controlled by the
``OBSERVABILITY_ENABLED`` env var). When disabled, importing this package
costs nothing extra — no ``opentelemetry`` symbols are pulled into
``sys.modules`` until ``tracer.init_tracing()`` is explicitly called AND
``OBSERVABILITY_ENABLED`` is truthy.

Public surface:

- :func:`init_tracing` — call from bot startup; reads env, wires
  ``TracerProvider`` + ``OTLPSpanExporter`` if enabled.
- :func:`is_enabled` — env-var probe.
- :func:`traced_decision` — context manager for SmartMonsterDriver decision spans.
- :func:`traced_translate` — context manager for ingest-translate spans.
- :data:`FallbackReason` — Literal alias for the D-65 fallback enum.

NOTE: ``init_tracing`` lives in ``tracer.py`` (lazy OTel import). The
context managers live in ``instrumentation.py`` (pure Python, no OTel
imports at module level). Importing ``observability`` re-exports them but
does NOT pull in OTel.
"""
# SPDX-License-Identifier: Apache-2.0

from eldritch_dm.observability.instrumentation import (
    FallbackReason,
    traced_decision,
    traced_eval,
    traced_translate,
)
from eldritch_dm.observability.tracer import init_tracing, is_enabled

# NOTE on lazy imports (Phase 13):
#   - ``metrics_endpoint`` is NOT imported eagerly. Importing it pulls
#     ``prometheus_client`` into ``sys.modules`` via the type annotations on
#     ``_MetricsEndpointHandle`` (resolved at class-body evaluation time
#     inside ``__init__``, not at module import time — so a bare
#     ``from .metrics_endpoint import ...`` here would NOT leak prometheus
#     by itself, but it would expand the surface importers see).
#   - ``span_buffer`` is imported by ``instrumentation`` already (stdlib
#     sqlite3 only — no leak).
#   - Callers that need the metrics endpoint should
#     ``from eldritch_dm.observability.metrics_endpoint import
#         is_metrics_endpoint_enabled, start_metrics_endpoint``
#     explicitly — keeps the lazy-import canaries strict.

__all__ = [
    "FallbackReason",
    "init_tracing",
    "is_enabled",
    "traced_decision",
    "traced_eval",
    "traced_translate",
]
