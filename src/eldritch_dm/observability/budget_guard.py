"""Daily LLM budget guard (Phase 13 / MON-03 / D-91, R-13-03-c).

A separate evaluator from ``AlertEvaluator`` because budget enforcement has
fundamentally different cadence + semantics than KPI alerting:
  - Cumulative, not rate-of-error
  - Tick every 5min, not every 30s
  - Auto-recovers at UTC midnight when the daily cap resets

Behaviors:

  - `tick()` computes today's spend; logs `eldritch.budget.alert` WARNING
    once when crossing `alert_threshold_usd` ($2 default per AI-SPEC §6
    Offline Flywheel)
  - When spend exceeds `cap_usd`, calls `degraded_mode.trip(reason=...)` so
    the bot switches to the random driver (no LLM calls = no further spend)
  - When a new UTC day starts and the active degraded-mode reason starts
    with `budget_exceeded:`, calls `degraded_mode.recover()` so the bot
    resumes smart driving on the fresh daily budget
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from eldritch_dm.logging import get_logger
from eldritch_dm.observability.cost import (
    PricingTable,
    sum_daily_spend,
)
from eldritch_dm.observability.degraded_mode import get_degraded_mode
from eldritch_dm.observability.span_buffer import SpanBuffer, init_buffer

log = get_logger(__name__)


@dataclass(frozen=True)
class _BudgetState:
    """Mutable-via-replacement edge-trigger state."""

    last_alert_date: date | None = None
    last_seen_date: date | None = None


class BudgetTickResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    on_date: date
    spent_usd: Decimal
    cap_usd: Decimal
    alert_threshold_usd: Decimal
    tripped: bool
    recovered: bool
    alerted: bool


class BudgetEvaluator:
    def __init__(
        self,
        *,
        cap_usd: Decimal,
        alert_threshold_usd: Decimal = Decimal("2.00"),
        table: PricingTable,
        buffer: SpanBuffer | None = None,
        time_source: Callable[[], datetime] | None = None,
    ):
        self._cap = cap_usd
        self._alert_threshold = alert_threshold_usd
        self._table = table
        self._buffer = buffer
        self._time_source = time_source or (lambda: datetime.now(UTC))
        self._state = _BudgetState()
        self._task: asyncio.Task | None = None

        if cap_usd <= 0:
            log.info(
                "eldritch.budget.disabled",
                cap_usd=str(cap_usd),
                note="cap<=0 → budget guard inactive (no trips, no recovers)",
            )

    # ── Tick ────────────────────────────────────────────────────────────────

    def tick(self) -> BudgetTickResult:
        now = self._time_source()
        today = now.date()
        buf = self._buffer or init_buffer()

        # Day-rollover detection BEFORE computing spend.
        recovered = False
        if (
            self._state.last_seen_date is not None
            and today != self._state.last_seen_date
        ):
            # New UTC day — if degraded was tripped by budget, recover.
            dm = get_degraded_mode()
            snap = dm.snapshot()
            if snap.active and snap.reason and snap.reason.startswith("budget_exceeded:"):
                dm.recover(now=now)
                recovered = True
                log.info(
                    "eldritch.budget.daily_rollover_recovered",
                    new_date=today.isoformat(),
                )

        # If disabled (cap<=0), short-circuit to a zero-spend, no-action tick.
        if self._cap <= 0:
            self._state = _BudgetState(
                last_alert_date=self._state.last_alert_date,
                last_seen_date=today,
            )
            return BudgetTickResult(
                on_date=today,
                spent_usd=Decimal(0),
                cap_usd=self._cap,
                alert_threshold_usd=self._alert_threshold,
                tripped=False,
                recovered=recovered,
                alerted=False,
            )

        breakdown = sum_daily_spend(buf, on_date=today, table=self._table)
        spent = breakdown.total_usd

        # Edge-triggered $2/day alert — only on the tick that first crosses
        # the threshold this calendar day. State carries last_alert_date so
        # we don't re-alert on the same day.
        alerted = False
        if spent >= self._alert_threshold and self._state.last_alert_date != today:
            log.warning(
                "eldritch.budget.alert",
                on_date=today.isoformat(),
                spent_usd=str(spent),
                alert_threshold_usd=str(self._alert_threshold),
            )
            alerted = True

        # Cap breach → trip degraded mode.
        tripped = False
        if spent > self._cap:
            reason = f"budget_exceeded:${spent} over ${self._cap}"
            get_degraded_mode().trip(reason, now=now)
            log.error(
                "eldritch.budget.exceeded",
                on_date=today.isoformat(),
                spent_usd=str(spent),
                cap_usd=str(self._cap),
                over_by_usd=str(spent - self._cap),
            )
            tripped = True

        # Update state.
        self._state = _BudgetState(
            last_alert_date=today if alerted else self._state.last_alert_date,
            last_seen_date=today,
        )

        return BudgetTickResult(
            on_date=today,
            spent_usd=spent,
            cap_usd=self._cap,
            alert_threshold_usd=self._alert_threshold,
            tripped=tripped,
            recovered=recovered,
            alerted=alerted,
        )

    # ── Scheduler ───────────────────────────────────────────────────────────

    def start(
        self,
        loop: asyncio.AbstractEventLoop,
        tick_seconds: float = 300.0,
    ) -> asyncio.Task:
        """Schedule periodic tick() at 5-minute cadence by default."""

        async def _runner() -> None:
            while True:
                try:
                    await loop.run_in_executor(None, self.tick)
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "budget_evaluator.tick_error",
                        error_type=type(exc).__name__,
                        error=str(exc)[:200],
                    )
                await asyncio.sleep(tick_seconds)

        self._task = loop.create_task(_runner())
        return self._task
