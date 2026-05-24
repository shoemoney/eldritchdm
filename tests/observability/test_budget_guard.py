"""Tests for the daily-budget guard (Phase 13 / MON-03)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from eldritch_dm.observability.budget_guard import BudgetEvaluator
from eldritch_dm.observability.cost import load_pricing
from eldritch_dm.observability.degraded_mode import get_degraded_mode
from eldritch_dm.observability.span_buffer import BufferRow, init_buffer, reset_for_tests


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite"))
    get_degraded_mode().reset_for_tests()
    reset_for_tests()
    yield
    get_degraded_mode().reset_for_tests()
    reset_for_tests()


def _spend(buf, *, model: str, ts: datetime, tin: int = 1_000_000, tout: int = 0):
    """Seed one big translate-span row to simulate $X of spend."""
    buf.record(
        BufferRow(
            span_name="eldritch.ingest.translate",
            channel_id="c",
            model=model,
            latency_ms=100,
            tokens_input=tin,
            tokens_output=tout,
            timestamp_utc=ts,
        )
    )


def _table():
    from unittest.mock import MagicMock

    return load_pricing(MagicMock(pricing_yaml_path=None))


def test_no_spend_no_trip():
    table = _table()
    clock = {"now": datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)}
    ev = BudgetEvaluator(
        cap_usd=Decimal("5.00"),
        table=table,
        time_source=lambda: clock["now"],
    )
    r = ev.tick()
    assert r.spent_usd == Decimal(0)
    assert r.tripped is False
    assert get_degraded_mode().is_active() is False


def test_alert_at_2_usd_fires_once_per_day():
    table = _table()
    buf = init_buffer()
    clock = {"now": datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)}
    # gpt-4o-mini at $0.15/M in = $3 for 20M in. Push 1M tokens at $2.50/M in
    # via gpt-4o ($2.50 in tokens).
    _spend(buf, model="gpt-4o", ts=clock["now"], tin=1_000_000, tout=0)
    buf.flush(timeout_s=3.0)
    ev = BudgetEvaluator(
        cap_usd=Decimal("100.00"),  # Far above to avoid trip
        alert_threshold_usd=Decimal("2.00"),
        table=table,
        time_source=lambda: clock["now"],
    )
    r1 = ev.tick()
    assert r1.alerted is True
    assert r1.tripped is False  # well under cap
    r2 = ev.tick()
    assert r2.alerted is False  # already alerted this day


def test_cap_breach_trips_degraded_mode():
    table = _table()
    buf = init_buffer()
    clock = {"now": datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)}
    # 10M gpt-4o input tokens = $25 — way over $5 cap
    _spend(buf, model="gpt-4o", ts=clock["now"], tin=10_000_000, tout=0)
    buf.flush(timeout_s=3.0)
    ev = BudgetEvaluator(
        cap_usd=Decimal("5.00"),
        table=table,
        time_source=lambda: clock["now"],
    )
    r = ev.tick()
    assert r.tripped is True
    dm = get_degraded_mode()
    assert dm.is_active() is True
    assert dm.snapshot().reason is not None
    assert dm.snapshot().reason.startswith("budget_exceeded:")


def test_midnight_utc_rollover_recovers_budget_trip():
    """After tripping on day N, the next-day tick recovers degraded mode."""
    table = _table()
    buf = init_buffer()
    clock = {"now": datetime(2026, 5, 24, 23, 30, 0, tzinfo=UTC)}
    _spend(buf, model="gpt-4o", ts=clock["now"], tin=10_000_000, tout=0)
    buf.flush(timeout_s=3.0)
    ev = BudgetEvaluator(
        cap_usd=Decimal("5.00"),
        table=table,
        time_source=lambda: clock["now"],
    )
    ev.tick()
    assert get_degraded_mode().is_active() is True

    # Advance past UTC midnight.
    clock["now"] = datetime(2026, 5, 25, 0, 5, 0, tzinfo=UTC)
    # No spend on the new day yet.
    r = ev.tick()
    assert r.recovered is True
    assert get_degraded_mode().is_active() is False


def test_midnight_rollover_does_not_recover_non_budget_reasons():
    """A latency trip must NOT be recovered by the budget-day rollover."""
    table = _table()
    clock = {"now": datetime(2026, 5, 24, 23, 30, 0, tzinfo=UTC)}
    get_degraded_mode().trip("latency_breach:1800ms>1500ms")
    ev = BudgetEvaluator(
        cap_usd=Decimal("5.00"),
        table=table,
        time_source=lambda: clock["now"],
    )
    ev.tick()  # establish last_seen_date
    clock["now"] += timedelta(hours=1)  # cross midnight
    ev.tick()
    # Still degraded — the reason wasn't budget.
    assert get_degraded_mode().is_active() is True


def test_cap_zero_disables_guard():
    table = _table()
    buf = init_buffer()
    clock = {"now": datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)}
    # Even with huge spend, cap<=0 → no trip
    _spend(buf, model="gpt-4o", ts=clock["now"], tin=10_000_000, tout=0)
    buf.flush(timeout_s=3.0)
    ev = BudgetEvaluator(
        cap_usd=Decimal("0"),
        table=table,
        time_source=lambda: clock["now"],
    )
    r = ev.tick()
    assert r.tripped is False
    assert get_degraded_mode().is_active() is False
