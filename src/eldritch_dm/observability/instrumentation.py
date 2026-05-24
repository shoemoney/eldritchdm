"""Observability context managers — dual-sink (span buffer + optional OTel).

History:
  - Phase 11 (OBS-01 / D-65d): introduced no-OTel-imports-at-module-level
    invariant. Three context managers (decision/translate/eval) emit spans
    iff ``OBSERVABILITY_ENABLED=true`` and ``init_tracing()`` was called.
  - Phase 13 (MON-01 / R-13-01-a): made the local SQLite span buffer
    (``span_buffer.py``) the PRIMARY sink. Every traced_* exit now records
    a row to the buffer regardless of OTel state. OTel export remains
    secondary, still gated by ``OBSERVABILITY_ENABLED``.

Architectural invariants this module preserves:

1. No ``opentelemetry`` import at module level. The lazy-import canary in
   ``tests/observability/test_lazy_import.py`` asserts this.
2. No ``prometheus_client`` import anywhere in this module. The sibling
   canary in ``test_metrics_lazy_import.py`` asserts this.
3. The no-op span path (``_TRACER is None``) is allowed to write to the
   buffer because ``span_buffer`` itself uses only stdlib ``sqlite3``.

Design — buffering proxy:

Each ``traced_*`` context manager yields a small ``_BufferingSpan`` proxy
that:

- Forwards ``set_attribute(key, value)`` to the underlying OTel Span (when
  one exists) and stores ``(key, value)`` in a local dict.
- On context exit, builds a ``BufferRow`` from the captured attrs + the
  fixed attrs set on entry, and calls ``span_buffer.init_buffer().record(row)``.

The OTel-attribute-key → BufferRow-field mapping is hardcoded in
``_BufferingSpan._build_row`` to avoid forcing callers to learn new keys —
the legacy Phase 11 dotted keys keep working.

D-65 span schema for ``eldritch.monster.decision``:

- ``eldritch.monster.id`` (str)
- ``eldritch.channel.id`` (str)
- ``eldritch.combat.round`` (int)
- ``eldritch.driver.path`` (Literal["smart","random","cache","mixed"])
- ``eldritch.latency_ms`` (int)
- ``eldritch.tokens.input`` (int)
- ``eldritch.tokens.output`` (int)
- ``eldritch.fallback.reason`` (Optional[FallbackReason])

D-65b ingest schema for ``eldritch.ingest.translate``:

- ``eldritch.channel.id`` (str)
- ``eldritch.latency_ms`` (int)
- ``eldritch.tokens.input`` (int)
- ``eldritch.tokens.output`` (int)
- ``eldritch.ingest.parse_error`` (bool)
- ``eldritch.ingest.model`` (str)

D-81 eval schema for ``eldritch.eval.judge``:

- ``eldritch.eval.scenario_id`` (str)
- ``eldritch.eval.judge_model`` (str)
- ``eldritch.eval.driver_model`` (str)
- ``eldritch.eval.archetype`` (str)
- ``eldritch.eval.overall_score`` (float, stamped by caller)
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

from eldritch_dm.logging import get_logger
from eldritch_dm.observability.span_buffer import BufferRow, init_buffer

log = get_logger(__name__)

FallbackReason = Literal[
    "timeout",
    "json_parse",
    "hallucinated_id",
    "refusal",
    "generic",
    "rate_limit",
]

# Module-level sentinel. ``tracer.init_tracing()`` mutates this when
# OBSERVABILITY_ENABLED=true to point at a real OTel Tracer. Type kept as
# ``Any`` to avoid an ``opentelemetry`` import here.
_TRACER: Any | None = None


class _BufferingSpan:
    """Span proxy: forwards to OTel (if present), captures attrs for buffer write.

    Constructed inside each ``traced_*`` context manager with the fixed-attr
    snapshot from the entry call and (optionally) the real OTel span. The
    enclosing context manager calls ``_to_row()`` on exit and records to the
    buffer.
    """

    def __init__(self, span_name: str, fixed_attrs: dict[str, Any], otel_span: Any | None):
        self._span_name = span_name
        self._otel_span = otel_span
        # Captured attrs (mutable). Caller may overwrite same key multiple
        # times — last write wins, matches OTel semantics.
        self._attrs: dict[str, Any] = dict(fixed_attrs)

    # ── OTel Span subset we forward ──────────────────────────────────────────

    def set_attribute(self, key: str, value: Any) -> None:
        self._attrs[key] = value
        if self._otel_span is not None:
            self._otel_span.set_attribute(key, value)

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        self._attrs.update(attributes)
        if self._otel_span is not None:
            self._otel_span.set_attributes(attributes)

    def record_exception(self, exception: BaseException) -> None:
        # Errors are recorded both on the OTel span and into the local attr
        # dict so the buffer row captures the error string.
        self._attrs.setdefault("eldritch.error", str(exception)[:500])
        if self._otel_span is not None:
            self._otel_span.record_exception(exception)

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        if self._otel_span is not None:
            self._otel_span.set_status(*args, **kwargs)

    # ── Buffer-row builder ──────────────────────────────────────────────────

    def _to_row(self) -> BufferRow:
        a = self._attrs
        # Pull common fields with safe fallbacks.
        latency = a.get("eldritch.latency_ms")
        tokens_in = a.get("eldritch.tokens.input")
        tokens_out = a.get("eldritch.tokens.output")
        fallback = a.get("eldritch.fallback.reason")
        return BufferRow(
            span_name=self._span_name,
            monster_id=a.get("eldritch.monster.id"),
            channel_id=a.get("eldritch.channel.id"),
            combat_round=a.get("eldritch.combat.round"),
            driver_path=a.get("eldritch.driver.path"),
            latency_ms=int(latency) if latency is not None else None,
            tokens_input=int(tokens_in) if tokens_in is not None else None,
            tokens_output=int(tokens_out) if tokens_out is not None else None,
            fallback_reason=str(fallback) if fallback is not None else None,
            # ingest + eval populate model differently — try both keys.
            model=a.get("eldritch.ingest.model") or a.get("eldritch.eval.judge_model"),
            scenario_id=a.get("eldritch.eval.scenario_id"),
            overall_score=a.get("eldritch.eval.overall_score"),
            refusal=(fallback == "refusal"),
            error=a.get("eldritch.error"),
        )


def _record_to_buffer(proxy: _BufferingSpan) -> None:
    """Build the row and record it. Never raises onto the hot path."""
    try:
        row = proxy._to_row()  # noqa: SLF001 — internal proxy method
        init_buffer().record(row)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "instrumentation.buffer_record_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )


# ── Context managers ─────────────────────────────────────────────────────────


@contextmanager
def traced_decision(
    *,
    monster_id: str,
    channel_id: str,
    combat_round: int,
    driver_path: str,
) -> Iterator[Any]:
    """Open a span for one SmartMonsterDriver tactical decision.

    Always writes to the local span buffer on exit (primary sink). When
    ``OBSERVABILITY_ENABLED=true`` and ``init_tracing()`` has been called,
    ALSO emits an OTel ``eldritch.monster.decision`` span (secondary sink for
    Phoenix / Grafana / any OTLP backend).
    """
    fixed_attrs = {
        "eldritch.monster.id": monster_id,
        "eldritch.channel.id": channel_id,
        "eldritch.combat.round": combat_round,
        "eldritch.driver.path": driver_path,
    }
    if _TRACER is None:
        proxy = _BufferingSpan("eldritch.monster.decision", fixed_attrs, None)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)
        return
    with _TRACER.start_as_current_span("eldritch.monster.decision") as otel_span:
        for k, v in fixed_attrs.items():
            otel_span.set_attribute(k, v)
        proxy = _BufferingSpan("eldritch.monster.decision", fixed_attrs, otel_span)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)


@contextmanager
def traced_eval(
    *,
    scenario_id: str,
    judge_model: str,
    driver_model: str,
    archetype: str,
) -> Iterator[Any]:
    """Open a span for one TacticalJudge score() call (Phase 12 / D-81).

    Always writes to the buffer on exit. OTel export is secondary.
    """
    fixed_attrs = {
        "eldritch.eval.scenario_id": scenario_id,
        "eldritch.eval.judge_model": judge_model,
        "eldritch.eval.driver_model": driver_model,
        "eldritch.eval.archetype": archetype,
    }
    if _TRACER is None:
        proxy = _BufferingSpan("eldritch.eval.judge", fixed_attrs, None)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)
        return
    with _TRACER.start_as_current_span("eldritch.eval.judge") as otel_span:
        for k, v in fixed_attrs.items():
            otel_span.set_attribute(k, v)
        proxy = _BufferingSpan("eldritch.eval.judge", fixed_attrs, otel_span)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)


@contextmanager
def traced_translate(*, channel_id: str, model: str) -> Iterator[Any]:
    """Open a span for one ingest character-sheet translate call.

    Always writes to the buffer on exit. OTel export is secondary.
    """
    fixed_attrs = {
        "eldritch.channel.id": channel_id,
        "eldritch.ingest.model": model,
    }
    if _TRACER is None:
        proxy = _BufferingSpan("eldritch.ingest.translate", fixed_attrs, None)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)
        return
    with _TRACER.start_as_current_span("eldritch.ingest.translate") as otel_span:
        for k, v in fixed_attrs.items():
            otel_span.set_attribute(k, v)
        proxy = _BufferingSpan("eldritch.ingest.translate", fixed_attrs, otel_span)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)
