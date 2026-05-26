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
# SPDX-License-Identifier: Apache-2.0

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
        latency = (
            a.get("eldritch.latency_ms")
            or a.get("eldritch.mcp.cache.latency_ms")
            or a.get("eldritch.character_cache.latency_ms")
            or a.get("eldritch.narrcache.latency_ms")
        )
        tokens_in = a.get("eldritch.tokens.input") or a.get("eldritch.mcp.cache.size_l2")
        tokens_out = a.get("eldritch.tokens.output")
        fallback = a.get("eldritch.fallback.reason")
        # Phase 16 mcp cache: reuse existing BufferRow fields without
        # extending the schema (keeps the test_span_buffer canaries green):
        #   model         <- eldritch.mcp.tool_name
        #   driver_path   <- eldritch.mcp.cache.layer
        #                    OR eldritch.mcp.cache.invalidation.scope
        #   combat_round  <- eldritch.mcp.cache.size_l1
        #                    OR eldritch.mcp.cache.invalidation.entries_removed
        #   tokens_input  <- eldritch.mcp.cache.size_l2
        # Phase 17 character cache: same approach — reuse BufferRow columns:
        #   monster_id    <- eldritch.character_cache.character_id
        #   driver_path   <- eldritch.character_cache.layer
        #                    OR eldritch.character_cache.invalidation.scope
        #   combat_round  <- eldritch.character_cache.size
        #                    OR eldritch.character_cache.invalidation.entries_removed
        #   latency_ms    <- eldritch.character_cache.latency_ms
        # Phase 18 narrcache: same approach — reuse BufferRow columns:
        #   model         <- eldritch.narrcache.model
        #   driver_path   <- eldritch.narrcache.layer
        #                    (bypass | hit | miss | gate_reject_store | gate_reject_serve)
        #   combat_round  <- eldritch.narrcache.size
        #   latency_ms    <- eldritch.narrcache.latency_ms
        #   tokens_input  <- eldritch.tokens.input  (already shared)
        #   tokens_output <- eldritch.tokens.output (already shared)
        #   overall_score <- eldritch.narrcache.savings_usd (float reuse)
        driver_path = (
            a.get("eldritch.driver.path")
            or a.get("eldritch.mcp.cache.layer")
            or a.get("eldritch.mcp.cache.invalidation.scope")
            or a.get("eldritch.character_cache.layer")
            or a.get("eldritch.character_cache.invalidation.scope")
            or a.get("eldritch.narrcache.layer")
        )
        combat_round = (
            a.get("eldritch.combat.round")
            if a.get("eldritch.combat.round") is not None
            else a.get("eldritch.mcp.cache.size_l1")
            if a.get("eldritch.mcp.cache.size_l1") is not None
            else a.get("eldritch.mcp.cache.invalidation.entries_removed")
            if a.get("eldritch.mcp.cache.invalidation.entries_removed") is not None
            else a.get("eldritch.character_cache.size")
            if a.get("eldritch.character_cache.size") is not None
            else a.get("eldritch.character_cache.invalidation.entries_removed")
            if a.get("eldritch.character_cache.invalidation.entries_removed") is not None
            else a.get("eldritch.narrcache.size")
        )
        model = (
            a.get("eldritch.ingest.model")
            or a.get("eldritch.eval.judge_model")
            or a.get("eldritch.mcp.tool_name")
            or a.get("eldritch.mcp.cache.invalidation.tool_name")
            or a.get("eldritch.narrcache.model")
        )
        monster_id = (
            a.get("eldritch.monster.id")
            or a.get("eldritch.character_cache.character_id")
            or a.get("eldritch.character_cache.invalidation.character_id")
        )
        overall_score = a.get("eldritch.eval.overall_score")
        if overall_score is None:
            # Phase 18 narrcache reuses overall_score for savings_usd (float).
            overall_score = a.get("eldritch.narrcache.savings_usd")
        return BufferRow(
            span_name=self._span_name,
            monster_id=monster_id,
            channel_id=a.get("eldritch.channel.id"),
            combat_round=combat_round,
            driver_path=driver_path,
            latency_ms=int(latency) if latency is not None else None,
            tokens_input=int(tokens_in) if tokens_in is not None else None,
            tokens_output=int(tokens_out) if tokens_out is not None else None,
            fallback_reason=str(fallback) if fallback is not None else None,
            model=model,
            scenario_id=a.get("eldritch.eval.scenario_id"),
            overall_score=overall_score,
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


# ── Phase 16 — MCP cache spans ───────────────────────────────────────────────
#
# Two new span names, both routed through the same dual-sink machinery as the
# Phase 11/13 spans above. Attributes are mapped onto existing ``BufferRow``
# fields in ``_BufferingSpan._build_row`` so we do NOT extend the buffer
# schema (keeps the ``test_span_buffer`` canaries green).
#
# eldritch.mcp.cache attributes:
#   - eldritch.mcp.tool_name           (str)
#   - eldritch.mcp.cache.layer         ("l1" | "l2" | "miss" | "bypass")
#   - eldritch.mcp.cache.size_l1       (int)
#   - eldritch.mcp.cache.size_l2       (int — -1 when L2 disabled)
#   - eldritch.mcp.cache.latency_ms    (int)
#
# eldritch.mcp.cache.invalidation attributes:
#   - eldritch.mcp.cache.invalidation.scope            ("all"|"tool"|"entry"|"schema_version")
#   - eldritch.mcp.cache.invalidation.tool_name        (str | None)
#   - eldritch.mcp.cache.invalidation.entries_removed  (int)


@contextmanager
def traced_mcp_cache(
    *,
    tool_name: str,
) -> Iterator[Any]:
    """Open a span for one MCPCache.call().

    The caller (MCPCache.call) is responsible for setting
    ``eldritch.mcp.cache.layer``, ``eldritch.mcp.cache.size_l1``,
    ``eldritch.mcp.cache.size_l2``, and ``eldritch.mcp.cache.latency_ms``
    on the proxy before exit. Buffer row is always written; OTel export is
    secondary (gated on ``OBSERVABILITY_ENABLED``).
    """
    fixed_attrs = {
        "eldritch.mcp.tool_name": tool_name,
    }
    if _TRACER is None:
        proxy = _BufferingSpan("eldritch.mcp.cache", fixed_attrs, None)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)
        return
    with _TRACER.start_as_current_span("eldritch.mcp.cache") as otel_span:
        for k, v in fixed_attrs.items():
            otel_span.set_attribute(k, v)
        proxy = _BufferingSpan("eldritch.mcp.cache", fixed_attrs, otel_span)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)


@contextmanager
def traced_mcp_cache_invalidation(
    *,
    scope: Literal["all", "tool", "entry", "schema_version"],
    tool_name: str | None = None,
) -> Iterator[Any]:
    """Open a span for one MCPCache.invalidate() / schema-version wipe.

    The caller is responsible for setting
    ``eldritch.mcp.cache.invalidation.entries_removed`` before exit.
    """
    fixed_attrs: dict[str, Any] = {
        "eldritch.mcp.cache.invalidation.scope": scope,
    }
    if tool_name is not None:
        fixed_attrs["eldritch.mcp.cache.invalidation.tool_name"] = tool_name
    if _TRACER is None:
        proxy = _BufferingSpan("eldritch.mcp.cache.invalidation", fixed_attrs, None)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)
        return
    with _TRACER.start_as_current_span("eldritch.mcp.cache.invalidation") as otel_span:
        for k, v in fixed_attrs.items():
            otel_span.set_attribute(k, v)
        proxy = _BufferingSpan("eldritch.mcp.cache.invalidation", fixed_attrs, otel_span)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)


# ── Phase 17 — Character cache spans ─────────────────────────────────────────
#
# eldritch.character_cache.lookup attributes:
#   - eldritch.character_cache.character_id  (str)
#   - eldritch.character_cache.layer         ("ttl_hit" | "etag_match" | "miss")
#   - eldritch.character_cache.size          (int)
#   - eldritch.character_cache.latency_ms    (int)
#
# eldritch.character_cache.invalidation attributes:
#   - eldritch.character_cache.invalidation.scope            ("all" | "entry")
#   - eldritch.character_cache.invalidation.character_id     (str | None)
#   - eldritch.character_cache.invalidation.entries_removed  (int)


@contextmanager
def traced_character_cache(
    *,
    character_id: str,
) -> Iterator[Any]:
    """Open a span for one CharacterCacheRepo.get_or_fetch() call.

    The caller (CharacterCacheRepo.get_or_fetch) is responsible for stamping
    ``eldritch.character_cache.layer``, ``eldritch.character_cache.size``, and
    ``eldritch.character_cache.latency_ms`` on the proxy before exit. Buffer
    row is always written; OTel export is secondary (gated on
    ``OBSERVABILITY_ENABLED``).
    """
    fixed_attrs = {
        "eldritch.character_cache.character_id": character_id,
    }
    if _TRACER is None:
        proxy = _BufferingSpan("eldritch.character_cache.lookup", fixed_attrs, None)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)
        return
    with _TRACER.start_as_current_span("eldritch.character_cache.lookup") as otel_span:
        for k, v in fixed_attrs.items():
            otel_span.set_attribute(k, v)
        proxy = _BufferingSpan("eldritch.character_cache.lookup", fixed_attrs, otel_span)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)


@contextmanager
def traced_character_cache_invalidation(
    *,
    scope: Literal["all", "entry"],
    character_id: str | None = None,
) -> Iterator[Any]:
    """Open a span for one CharacterCacheRepo.invalidate() call.

    The caller is responsible for stamping
    ``eldritch.character_cache.invalidation.entries_removed`` before exit.
    """
    fixed_attrs: dict[str, Any] = {
        "eldritch.character_cache.invalidation.scope": scope,
    }
    if character_id is not None:
        fixed_attrs["eldritch.character_cache.invalidation.character_id"] = character_id
    if _TRACER is None:
        proxy = _BufferingSpan("eldritch.character_cache.invalidation", fixed_attrs, None)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)
        return
    with _TRACER.start_as_current_span("eldritch.character_cache.invalidation") as otel_span:
        for k, v in fixed_attrs.items():
            otel_span.set_attribute(k, v)
        proxy = _BufferingSpan("eldritch.character_cache.invalidation", fixed_attrs, otel_span)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)


# ── Phase 18 — Narration cache spans ────────────────────────────────────────
#
# eldritch.narrcache.call attributes:
#   - eldritch.narrcache.model        (str)
#   - eldritch.narrcache.layer        ("bypass" | "hit" | "miss"
#                                      | "gate_reject_store"
#                                      | "gate_reject_serve")
#   - eldritch.narrcache.size         (int) — L1 size at exit
#   - eldritch.narrcache.latency_ms   (int)
#   - eldritch.narrcache.savings_usd  (float, populated on HIT only)
#   - eldritch.tokens.input/output    (int)  — reused from existing schema


@contextmanager
def traced_narrcache(
    *,
    model: str,
) -> Iterator[Any]:
    """Open a span for one NarrCache.acompletion() call (Phase 18).

    The caller (NarrCache.acompletion) is responsible for stamping
    ``eldritch.narrcache.layer``, ``eldritch.narrcache.size``,
    ``eldritch.narrcache.latency_ms``, ``eldritch.tokens.input``,
    ``eldritch.tokens.output``, and on HIT ``eldritch.narrcache.savings_usd``
    before the context manager exits. Buffer row is always written; OTel
    export is secondary (gated on ``OBSERVABILITY_ENABLED``).
    """
    fixed_attrs = {
        "eldritch.narrcache.model": model,
    }
    if _TRACER is None:
        proxy = _BufferingSpan("eldritch.narrcache.call", fixed_attrs, None)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)
        return
    with _TRACER.start_as_current_span("eldritch.narrcache.call") as otel_span:
        for k, v in fixed_attrs.items():
            otel_span.set_attribute(k, v)
        proxy = _BufferingSpan("eldritch.narrcache.call", fixed_attrs, otel_span)
        try:
            yield proxy
        finally:
            _record_to_buffer(proxy)
