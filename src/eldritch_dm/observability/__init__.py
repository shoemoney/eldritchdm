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

from eldritch_dm.observability.instrumentation import (
    FallbackReason,
    traced_decision,
    traced_translate,
)
from eldritch_dm.observability.tracer import init_tracing, is_enabled

__all__ = [
    "FallbackReason",
    "init_tracing",
    "is_enabled",
    "traced_decision",
    "traced_translate",
]
