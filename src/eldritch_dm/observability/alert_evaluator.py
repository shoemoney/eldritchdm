"""AlertEvaluator — rule engine + hysteresis + cold-start replay (Phase 13 / MON-02).

Periodically ticks against the KPI computer, evaluates each rule from
alerts.yaml, accumulates per-rule consecutive-breach counters, and fires
actions (log / degrade) when a rule's ``window_minutes`` consecutive ticks
breach.

Hysteresis (R-13-02-d + AI-SPEC §7):
  For ``degrade``-action rules, recovery is triggered when the inverse
  condition holds for ``window_minutes`` consecutive ticks, with the recover
  threshold set to ``threshold * recover_threshold_factor`` (default
  ``1200/1500`` so a 1500ms trip recovers at 1200ms — matches AI-SPEC §7).

Cold-start replay (R-13-02-f):
  ``cold_start_replay()`` reads the last ``window_minutes`` minutes of buffer
  data, buckets by minute, and for each ``degrade`` rule asks "was the
  condition true in EVERY one-minute bucket?" If yes, calls
  ``degraded_mode.trip(reason=f"cold_start_replay:{rule.name}")`` so a bot
  restart during an ongoing breach immediately enters degraded mode.

Time source:
  All time-of-day calls go through ``self._time_source()`` (defaults to
  ``datetime.now(UTC)``). Tests pass a mutable-clock callable so trip + recover
  thresholds can be asserted deterministically without freezegun (avoids
  freezegun's known races with threading.Event in the span buffer drainer).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict

from eldritch_dm.logging import get_logger
from eldritch_dm.observability.alerts_loader import AlertRule
from eldritch_dm.observability.degraded_mode import get_degraded_mode
from eldritch_dm.observability.kpi import KPISnapshot, compute_kpis
from eldritch_dm.observability.span_buffer import SpanBuffer, init_buffer

log = get_logger(__name__)

#: AI-SPEC §7: recover threshold is 1200ms when trip threshold is 1500ms.
#: Expressed as a ratio so the same factor applies to any rule with action=degrade.
DEFAULT_RECOVER_THRESHOLD_FACTOR = 1200.0 / 1500.0


# ── Outputs ─────────────────────────────────────────────────────────────────


@dataclass
class _RuleState:
    """Per-rule mutable counters tracked across ticks."""

    consecutive_breach_count: int = 0
    consecutive_recover_count: int = 0
    has_tripped_degrade: bool = False  # whether THIS rule's degrade has fired


class AlertEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot: KPISnapshot
    fired: tuple[str, ...]  # rule names that fired an action this tick
    tripped_degrade: bool   # whether degraded_mode.trip() was called this tick
    recovered: bool         # whether degraded_mode.recover() was called this tick


class ColdStartReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tripped_rules: tuple[str, ...]  # names of degrade rules that fired during replay


# ── Operator/comparison helpers ─────────────────────────────────────────────


def _evaluate(value: float | None, op: str, threshold: float) -> bool:
    """Return True if value (op) threshold holds. None always returns False."""
    if value is None:
        return False
    if op == "gt":
        return value > threshold
    if op == "gte":
        return value >= threshold
    if op == "lt":
        return value < threshold
    if op == "lte":
        return value <= threshold
    raise ValueError(f"unknown op: {op!r}")


def _invert_op(op: str) -> str:
    """Return the operator that defines the 'recover' (opposite) condition."""
    return {"gt": "lt", "gte": "lte", "lt": "gt", "lte": "gte"}[op]


def _kpi_value(snap: KPISnapshot, kpi_name: str) -> float | None:
    return getattr(snap, kpi_name, None)


# ── Evaluator ───────────────────────────────────────────────────────────────


class AlertEvaluator:
    def __init__(
        self,
        rules: Sequence[AlertRule],
        *,
        kpi_provider: Callable[[], KPISnapshot] | None = None,
        time_source: Callable[[], datetime] | None = None,
        recover_threshold_factor: float = DEFAULT_RECOVER_THRESHOLD_FACTOR,
        buffer: SpanBuffer | None = None,
    ):
        self._rules = tuple(rules)
        self._kpi_provider = kpi_provider or (lambda: compute_kpis())
        self._time_source = time_source or (lambda: datetime.now(UTC))
        self._recover_factor = recover_threshold_factor
        self._buffer = buffer
        self._rule_state: dict[str, _RuleState] = {r.name: _RuleState() for r in rules}
        self._tick_seconds: float = 30.0  # set by start()
        self._task: asyncio.Task | None = None

    # ── Single tick ─────────────────────────────────────────────────────────

    def tick(self) -> AlertEvaluationResult:
        snap = self._kpi_provider()
        fired: list[str] = []
        tripped = False
        recovered = False

        for rule in self._rules:
            state = self._rule_state[rule.name]
            value = _kpi_value(snap, rule.kpi)
            condition_true = _evaluate(value, rule.op, rule.threshold)

            if rule.action == "log":
                # Edge-trigger semantics for log rules — fire every tick the
                # condition is true (operators want to see ongoing breaches).
                if condition_true:
                    log_method = {
                        "critical": log.error,
                        "high": log.warning,
                        "warning": log.info,
                    }.get(rule.severity, log.info)
                    log_method(
                        "eldritch.alert.fired",
                        rule=rule.name,
                        severity=rule.severity,
                        kpi=rule.kpi,
                        value=value,
                        threshold=rule.threshold,
                    )
                    fired.append(rule.name)
                continue

            if rule.action in ("throttle", "webhook"):
                if condition_true:
                    log.warning(
                        "eldritch.alert.deferred",
                        rule=rule.name,
                        action=rule.action,
                        note="v1.3 routing not yet implemented",
                    )
                    fired.append(rule.name)
                continue

            if rule.action == "degrade":
                # Trip: consecutive-breach counting.
                if condition_true:
                    state.consecutive_breach_count += 1
                    state.consecutive_recover_count = 0
                else:
                    state.consecutive_breach_count = 0

                ticks_per_window = max(
                    1, int(rule.window_minutes * 60 / self._tick_seconds)
                )

                if (
                    state.consecutive_breach_count >= ticks_per_window
                    and not state.has_tripped_degrade
                ):
                    reason = f"{rule.name}:{rule.kpi}={value}>{rule.threshold}"
                    get_degraded_mode().trip(reason, now=self._time_source())
                    state.has_tripped_degrade = True
                    tripped = True
                    fired.append(rule.name)

                # Recover: consecutive-NON-breach counting against inverse condition.
                if state.has_tripped_degrade:
                    recover_threshold = rule.threshold * self._recover_factor
                    recover_op = _invert_op(rule.op)
                    recovered_now = _evaluate(value, recover_op, recover_threshold)
                    if recovered_now:
                        state.consecutive_recover_count += 1
                    else:
                        state.consecutive_recover_count = 0

                    if state.consecutive_recover_count >= ticks_per_window:
                        get_degraded_mode().recover(now=self._time_source())
                        state.has_tripped_degrade = False
                        state.consecutive_breach_count = 0
                        state.consecutive_recover_count = 0
                        recovered = True

        return AlertEvaluationResult(
            snapshot=snap,
            fired=tuple(fired),
            tripped_degrade=tripped,
            recovered=recovered,
        )

    # ── Cold-start replay ───────────────────────────────────────────────────

    def cold_start_replay(self) -> ColdStartReplayResult:
        """Per R-13-02-f: re-enter degraded mode if buffer shows ongoing breach.

        For each rule with action=degrade, bucket the last ``window_minutes``
        minutes into per-minute KPI snapshots; if EVERY bucket breaches the
        rule's condition, trip degraded_mode immediately.

        Safe to call when buffer is empty — no-op.
        """
        tripped: list[str] = []
        buf = self._buffer or init_buffer()
        now = self._time_source()

        for rule in self._rules:
            if rule.action != "degrade":
                continue
            window_minutes = rule.window_minutes
            all_buckets_breach = True
            for minute_offset in range(window_minutes, 0, -1):
                bucket_end = now - timedelta(minutes=minute_offset - 1)
                # bucket_start is implicit: compute_kpis(now=bucket_end,
                # window_minutes=1) defines the [bucket_end - 1min, bucket_end)
                # range internally.
                # Compute KPI over the one-minute bucket.
                snap = compute_kpis(
                    now=bucket_end,
                    window_minutes=1,
                    buffer=buf,
                )
                # Override sample-size short-circuit: an empty bucket means
                # NO data, which we treat as NOT breaching. This is
                # operationally correct — the bot was offline / quiet.
                if snap.sample_size == 0:
                    all_buckets_breach = False
                    break
                value = _kpi_value(snap, rule.kpi)
                if not _evaluate(value, rule.op, rule.threshold):
                    all_buckets_breach = False
                    break

            if all_buckets_breach:
                reason = f"cold_start_replay:{rule.name}"
                get_degraded_mode().trip(reason, now=now)
                self._rule_state[rule.name].has_tripped_degrade = True
                self._rule_state[rule.name].consecutive_breach_count = (
                    max(1, int(window_minutes * 60 / self._tick_seconds))
                )
                tripped.append(rule.name)

        if tripped:
            log.warning(
                "eldritch.alert.cold_start_replay_tripped",
                rules=tripped,
            )
        return ColdStartReplayResult(tripped_rules=tuple(tripped))

    # ── Background task scheduling ──────────────────────────────────────────

    def start(
        self, loop: asyncio.AbstractEventLoop, tick_seconds: float = 30.0
    ) -> asyncio.Task:
        """Schedule periodic tick() on the running event loop."""
        self._tick_seconds = tick_seconds

        async def _runner() -> None:
            while True:
                try:
                    await asyncio.get_event_loop().run_in_executor(None, self.tick)
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "alert_evaluator.tick_error",
                        error_type=type(exc).__name__,
                        error=str(exc)[:200],
                    )
                await asyncio.sleep(tick_seconds)

        self._task = loop.create_task(_runner())
        return self._task


# ── Boot-time helper ────────────────────────────────────────────────────────


def boot_alert_evaluator(
    *, tick_seconds: float | None = None, settings=None
) -> AlertEvaluator | None:
    """Synchronous bootstrap: load rules, run cold-start replay, return evaluator.

    Phase 13 design choice (Rule-3 deviation from CONTEXT 13-02 Task 06):
    we do the cold-start replay synchronously at boot time so a restart
    during an ongoing breach immediately enters degraded mode BEFORE the
    bot accepts the first Discord command. Periodic ticking on the asyncio
    loop is started by the bot's setup_hook (future v1.3 integration) or by
    the caller via ``ev.start(loop, ...)``.

    Returns the evaluator if observability is enabled, else None.
    """
    from eldritch_dm.observability.alerts_loader import load_alerts
    from eldritch_dm.observability.metrics_endpoint import (
        is_metrics_endpoint_enabled,
    )
    from eldritch_dm.observability.tracer import is_enabled as is_tracing_enabled

    if not (is_tracing_enabled() or is_metrics_endpoint_enabled()):
        return None

    rules = load_alerts(settings)
    ev = AlertEvaluator(rules)
    if tick_seconds is not None:
        ev._tick_seconds = tick_seconds
    # Cold-start replay — synchronous, must complete before returning.
    ev.cold_start_replay()
    return ev


# field re-exported for potential future serialization needs; no current use.
_ = field
