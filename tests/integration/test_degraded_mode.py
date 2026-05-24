"""End-to-end degraded-mode test (Phase 13 / MON-02 / Task 05 / D-88).

Wires the real components (span_buffer + kpi + alert_evaluator +
degraded_mode + monster_driver_factory) and synthesizes latency-injection
data to assert the trip → recover hysteresis works across the full stack.

This is the integration test promised by CONTEXT D-88. It uses an
injectable time_source rather than freezegun (R-13-02-d) to avoid races
with the span-buffer drainer's threading.Event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.gameplay.monster_driver import MonsterDriver
from eldritch_dm.gameplay.monster_driver_factory import make_monster_driver
from eldritch_dm.gameplay.smart_monster_driver import SmartMonsterDriver
from eldritch_dm.observability.alert_evaluator import AlertEvaluator
from eldritch_dm.observability.alerts_loader import AlertRule
from eldritch_dm.observability.degraded_mode import get_degraded_mode
from eldritch_dm.observability.kpi import compute_kpis, reset_cache_for_tests
from eldritch_dm.observability.span_buffer import (
    BufferRow,
    init_buffer,
    reset_for_tests,
)


def _factory_kwargs() -> dict[str, Any]:
    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock()

    def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
        return discord.ui.Button(label="r", custom_id=f"r:{timer_id}:{user_id}")

    async def state_provider(channel_id, campaign_name):
        return {"round_number": 1, "pcs": []}

    return {
        "mcp": MagicMock(),
        "rate_limiter": rate_limiter,
        "pc_classes_repo": MagicMock(),
        "riposte_timers_repo": MagicMock(),
        "button_factory": button_factory,
        "state_provider": state_provider,
        "channel_resolver": lambda c: None,
        "openai_client": MagicMock(),
    }


def _seed_decisions(
    buf, *, count: int, latency_ms: int, ts_anchor: datetime, fallback: str | None = None
):
    for i in range(count):
        buf.record(
            BufferRow(
                span_name="eldritch.monster.decision",
                monster_id=f"m{i}",
                channel_id="c1",
                combat_round=1,
                driver_path="smart",
                latency_ms=latency_ms,
                tokens_input=100,
                tokens_output=20,
                fallback_reason=fallback,
                timestamp_utc=ts_anchor - timedelta(seconds=i * 5),
            )
        )


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite"))
    get_degraded_mode().reset_for_tests()
    reset_for_tests()
    reset_cache_for_tests()
    yield
    get_degraded_mode().reset_for_tests()
    reset_for_tests()
    reset_cache_for_tests()


def test_synthetic_latency_breach_trips_then_recovers():
    """Full round-trip: latency injection → degraded mode → factory swaps
    to MonsterDriver → latency drops → recover → factory returns smart."""
    buf = init_buffer()
    # Mutable clock starting fixed.
    clock = {"now": datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)}

    def time_source() -> datetime:
        return clock["now"]

    rules = (
        AlertRule(
            name="crit_latency",
            severity="critical",
            kpi="latency_p99_ms",
            op="gt",
            threshold=1500,
            window_minutes=5,
            action="degrade",
        ),
    )

    def kpi_provider():
        # Recompute against the current clock (each tick advances clock).
        return compute_kpis(now=clock["now"], window_minutes=5, buffer=buf)

    ev = AlertEvaluator(
        rules,
        kpi_provider=kpi_provider,
        time_source=time_source,
        buffer=buf,
    )
    ev._tick_seconds = 60.0  # 1 tick = 1 min → window of 5 ticks

    # ── Phase 1: Inject 5 minutes of breaching latency, tick 5x ──
    for _ in range(5):
        # At each minute, add fresh rows with latency=1800 in the most-recent
        # 60s of buffer history relative to clock.
        _seed_decisions(
            buf,
            count=5,
            latency_ms=1800,
            ts_anchor=clock["now"],
            fallback="timeout",
        )
        buf.flush(timeout_s=2.0)
        ev.tick()
        clock["now"] += timedelta(minutes=1)

    assert get_degraded_mode().is_active() is True
    # Factory now returns the random driver, even when caller asks for smart.
    d = make_monster_driver(env_override="smart", **_factory_kwargs())
    assert isinstance(d, MonsterDriver)
    assert not isinstance(d, SmartMonsterDriver)

    # ── Phase 2: simulate latency drop. Advance the clock past the entire
    #             window of breach data before seeding healthy rows so the
    #             5-min KPI window contains ONLY healthy data on each tick.
    clock["now"] += timedelta(minutes=5)
    for _ in range(5):
        _seed_decisions(
            buf,
            count=5,
            latency_ms=900,  # under recover floor (1200ms)
            ts_anchor=clock["now"],
        )
        buf.flush(timeout_s=2.0)
        reset_cache_for_tests()  # bypass 5s KPI cache for deterministic recompute
        ev.tick()
        clock["now"] += timedelta(minutes=1)

    assert get_degraded_mode().is_active() is False
    # Factory returns smart again.
    d2 = make_monster_driver(**_factory_kwargs())
    assert isinstance(d2, SmartMonsterDriver)


def test_synthetic_latency_breach_does_not_trip_after_only_4_minutes():
    """Operationally critical: 4-minute breach must NOT trip (5min threshold)."""
    buf = init_buffer()
    clock = {"now": datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)}

    def time_source() -> datetime:
        return clock["now"]

    rules = (
        AlertRule(
            name="crit",
            severity="critical",
            kpi="latency_p99_ms",
            op="gt",
            threshold=1500,
            window_minutes=5,
            action="degrade",
        ),
    )

    ev = AlertEvaluator(
        rules,
        kpi_provider=lambda: compute_kpis(
            now=clock["now"], window_minutes=5, buffer=buf
        ),
        time_source=time_source,
        buffer=buf,
    )
    ev._tick_seconds = 60.0

    for _ in range(4):  # Only 4 ticks!
        _seed_decisions(
            buf,
            count=5,
            latency_ms=1800,
            ts_anchor=clock["now"],
            fallback="timeout",
        )
        buf.flush(timeout_s=2.0)
        reset_cache_for_tests()
        ev.tick()
        clock["now"] += timedelta(minutes=1)

    # Still NOT degraded — needs 5 consecutive ticks.
    assert get_degraded_mode().is_active() is False
