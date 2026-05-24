"""Observability context managers — no OTel imports at module level (D-65d).

These helpers are imported unconditionally by ``smart_monster_driver`` and
``ingest.translate``. To honor the lazy-import invariant (no
``opentelemetry`` in ``sys.modules`` when ``OBSERVABILITY_ENABLED=false``),
this module MUST NOT do ``from opentelemetry import ...`` at the top level.

When ``init_tracing()`` (in ``tracer.py``) successfully wires up an OTel
``TracerProvider``, it sets the module-level :data:`_TRACER` to a real
tracer instance. The context managers below check that sentinel at call
time:

- ``_TRACER is None`` → yield a pure-Python no-op span (zero overhead, no
  imports).
- ``_TRACER is not None`` → call ``_TRACER.start_as_current_span(...)``,
  yield the real span. The Span object reaches us via the
  already-imported OTel SDK (imported inside ``init_tracing``), so we
  never need an ``import opentelemetry`` statement in this module.

D-65 span schema for ``eldritch.monster.decision``:

- ``eldritch.monster.id`` (str)
- ``eldritch.channel.id`` (str)
- ``eldritch.combat.round`` (int)
- ``eldritch.driver.path`` (Literal["smart","random","cache","mixed"])
- ``eldritch.latency_ms`` (int)
- ``eldritch.tokens.input`` (int, 0 if cache/random)
- ``eldritch.tokens.output`` (int, 0 if cache/random)
- ``eldritch.fallback.reason`` (Optional[FallbackReason])

D-65b ingest schema for ``eldritch.ingest.translate``:

- ``eldritch.channel.id`` (str)
- ``eldritch.latency_ms`` (int)
- ``eldritch.tokens.input`` (int)
- ``eldritch.tokens.output`` (int)
- ``eldritch.ingest.parse_error`` (bool)
- ``eldritch.ingest.model`` (str)
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

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


class _NoopSpan:
    """Pure-Python no-op span. Matches the subset of the OTel Span API we use."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D401
        """Accept and discard."""
        return None

    def set_attributes(self, attributes: dict[str, Any]) -> None:  # noqa: D401
        """Accept and discard."""
        return None

    def record_exception(self, exception: BaseException) -> None:  # noqa: D401
        """Accept and discard."""
        return None

    def set_status(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        """Accept and discard."""
        return None


@contextmanager
def traced_decision(
    *,
    monster_id: str,
    channel_id: str,
    combat_round: int,
    driver_path: str,
) -> Iterator[Any]:
    """Open a span for one SmartMonsterDriver tactical decision.

    No-op when tracing is disabled. When enabled, yields the underlying OTel
    Span so callers can update ``driver.path``, ``latency_ms``, tokens, and
    ``fallback.reason`` over the lifetime of the decision.
    """
    if _TRACER is None:
        yield _NoopSpan()
        return
    with _TRACER.start_as_current_span("eldritch.monster.decision") as span:
        span.set_attribute("eldritch.monster.id", monster_id)
        span.set_attribute("eldritch.channel.id", channel_id)
        span.set_attribute("eldritch.combat.round", combat_round)
        span.set_attribute("eldritch.driver.path", driver_path)
        yield span


@contextmanager
def traced_translate(*, channel_id: str, model: str) -> Iterator[Any]:
    """Open a span for one ingest character-sheet translate call.

    No-op when tracing is disabled. When enabled, yields the underlying OTel
    Span so the caller can update ``latency_ms``, tokens, and
    ``ingest.parse_error``.
    """
    if _TRACER is None:
        yield _NoopSpan()
        return
    with _TRACER.start_as_current_span("eldritch.ingest.translate") as span:
        span.set_attribute("eldritch.channel.id", channel_id)
        span.set_attribute("eldritch.ingest.model", model)
        yield span
