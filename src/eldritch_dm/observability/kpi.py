"""KPI computer over the local span buffer (Phase 13 / MON-01 / D-85, R-13-01-e).

Reads from ``span_buffer.SpanBuffer`` (NEVER from OTel APIs) so the 5 KPIs
required by AI-SPEC §7 are computable whether or not Phoenix is running.

The 5 KPIs (D-85, AI-SPEC §7):

1. ``latency_p99_ms``   — gauge, 5min rolling. P99 over the latencies of
   ``eldritch.monster.decision`` spans in the window.
2. ``success_rate``     — smart-path-without-fallback / total decisions over
   the window. ``None`` when no decisions in the window.
3. ``tactical_score``   — avg of ``overall_score`` over ``eldritch.eval.judge``
   spans in the window. ``None`` when no judge spans (the eval run is offline
   and infrequent; on a fresh day there will be no rows).
4. ``refusal_rate``     — count(refusal=True) / count(decisions) over window.
5. ``fallback_rate``    — count(fallback_reason IS NOT NULL) / count(decisions).

A module-level 5-second cache (``get_cached_kpis``) means a Prometheus scrape
every 15s never triggers more than one SQL aggregation per 5s. The cache is
keyed only on the (now, window) tuple at the seconds level — finer granularity
is wasted because KPIs are bucketed at the minute level anyway.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict

from eldritch_dm.logging import get_logger
from eldritch_dm.observability.span_buffer import BufferRow, SpanBuffer, init_buffer

log = get_logger(__name__)

_DEFAULT_WINDOW_MINUTES = 5


# ── Output model ─────────────────────────────────────────────────────────────


class KPISnapshot(BaseModel):
    """Single read-only snapshot of the 5 KPIs over a rolling window.

    A field value of ``None`` indicates "insufficient data" — for example
    ``tactical_score`` will be ``None`` whenever no ``eldritch.eval.judge``
    spans landed in the window, which is the normal case when no eval has
    been run that hour.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    latency_p99_ms: float | None
    success_rate: float | None
    tactical_score: float | None
    refusal_rate: float | None
    fallback_rate: float | None
    window_seconds: int
    sample_size: int
    computed_at_utc: datetime


# ── Computation primitives ───────────────────────────────────────────────────


def _percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile (no interpolation).

    For p99 over a small sample (e.g. 7 decisions in 5 min) interpolation
    would oversmooth. AI-SPEC §7 talks about "P99 > 1500ms for 5 min" — a
    nearest-rank P99 matches operator intuition: at least one bad decision in
    the recent past.
    """
    if not values:
        return None
    s = sorted(values)
    # rank index for percentile p: ceil(p/100 * N) - 1
    n = len(s)
    rank = max(0, min(n - 1, int(round(pct / 100.0 * n)) - 1))
    return float(s[rank])


def _compute_from_rows(
    decision_rows: list[BufferRow],
    eval_rows: list[BufferRow],
    window_seconds: int,
    now: datetime,
) -> KPISnapshot:
    sample_size = len(decision_rows)

    if sample_size == 0:
        # No decisions — but we can still compute tactical_score if an eval
        # run dropped rows in the window. Otherwise everything is None.
        tactical_score = (
            sum(r.overall_score for r in eval_rows if r.overall_score is not None)
            / len([r for r in eval_rows if r.overall_score is not None])
            if any(r.overall_score is not None for r in eval_rows)
            else None
        )
        return KPISnapshot(
            latency_p99_ms=None,
            success_rate=None,
            tactical_score=tactical_score,
            refusal_rate=None,
            fallback_rate=None,
            window_seconds=window_seconds,
            sample_size=0,
            computed_at_utc=now,
        )

    latencies = [r.latency_ms for r in decision_rows if r.latency_ms is not None]
    latency_p99 = _percentile([float(v) for v in latencies], 99.0)

    smart_no_fallback = sum(
        1
        for r in decision_rows
        if r.driver_path == "smart" and r.fallback_reason is None
    )
    success_rate = smart_no_fallback / sample_size

    refusals = sum(1 for r in decision_rows if r.refusal)
    refusal_rate = refusals / sample_size

    fallbacks = sum(1 for r in decision_rows if r.fallback_reason is not None)
    fallback_rate = fallbacks / sample_size

    eval_scored = [r.overall_score for r in eval_rows if r.overall_score is not None]
    tactical_score = sum(eval_scored) / len(eval_scored) if eval_scored else None

    return KPISnapshot(
        latency_p99_ms=latency_p99,
        success_rate=success_rate,
        tactical_score=tactical_score,
        refusal_rate=refusal_rate,
        fallback_rate=fallback_rate,
        window_seconds=window_seconds,
        sample_size=sample_size,
        computed_at_utc=now,
    )


# ── Public API ───────────────────────────────────────────────────────────────


def compute_kpis(
    now: datetime | None = None,
    window_minutes: int = _DEFAULT_WINDOW_MINUTES,
    *,
    buffer: SpanBuffer | None = None,
) -> KPISnapshot:
    """Compute the 5 KPIs over the rolling ``window_minutes`` ending at ``now``.

    Args:
        now: Anchor "now" for the window. Default: ``datetime.now(UTC)``.
        window_minutes: Window length in minutes. Default 5 per AI-SPEC §7.
        buffer: Optional explicit buffer (tests). Default: ``init_buffer()``.
    """
    now = now or datetime.now(UTC)
    window_seconds = window_minutes * 60
    since = now - timedelta(seconds=window_seconds)
    buf = buffer or init_buffer()
    # Flush pending writes so newly recorded rows are visible.
    buf.flush(timeout_s=1.0)
    decisions = buf.query(
        since=since, until=now, span_name="eldritch.monster.decision"
    )
    evals = buf.query(since=since, until=now, span_name="eldritch.eval.judge")
    return _compute_from_rows(decisions, evals, window_seconds, now)


# ── 5-second in-process cache (R-13-01-e) ────────────────────────────────────


_CACHE_LOCK = threading.Lock()
_CACHED: tuple[KPISnapshot, datetime] | None = None


def get_cached_kpis(ttl_seconds: float = 5.0) -> KPISnapshot:
    """Return a cached snapshot if recent enough, else recompute.

    A Prometheus scrape interval of 15s combined with a 5s cache means the
    KPI computer runs ~3x/min in steady state regardless of how many scrape
    clients connect — bounded SQLite load.
    """
    global _CACHED
    now = datetime.now(UTC)
    with _CACHE_LOCK:
        if _CACHED is not None:
            snapshot, computed_at = _CACHED
            if (now - computed_at).total_seconds() < ttl_seconds:
                return snapshot
        snapshot = compute_kpis(now=now)
        _CACHED = (snapshot, now)
        return snapshot


def reset_cache_for_tests() -> None:
    """Drop the cache so the next call recomputes. Test-only."""
    global _CACHED
    with _CACHE_LOCK:
        _CACHED = None
