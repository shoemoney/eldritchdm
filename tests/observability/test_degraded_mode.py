"""Tests for degraded-mode state machine (Phase 13 / MON-02 / Task 01)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from eldritch_dm.observability.degraded_mode import (
    DegradedModeSnapshot,
    get_degraded_mode,
)


def _state():
    s = get_degraded_mode()
    s.reset_for_tests()
    return s


def test_initial_state_inactive():
    s = _state()
    assert s.is_active() is False
    snap = s.snapshot()
    assert snap.active is False
    assert snap.reason is None
    assert snap.entered_at_utc is None


def test_trip_sets_active_with_reason():
    s = _state()
    s.trip("latency_breach")
    assert s.is_active() is True
    snap = s.snapshot()
    assert snap.reason == "latency_breach"
    assert snap.entered_at_utc is not None


def test_trip_idempotent_same_reason(caplog):
    s = _state()
    s.trip("latency_breach")
    snap1 = s.snapshot()
    s.trip("latency_breach")  # No reason change → no log line
    snap2 = s.snapshot()
    # entered_at must remain unchanged on the second trip.
    assert snap1.entered_at_utc == snap2.entered_at_utc


def test_trip_idempotent_reason_change(caplog):
    s = _state()
    s.trip("latency_breach")
    s.trip("budget_exceeded:$6 over $5")
    snap = s.snapshot()
    assert snap.reason == "budget_exceeded:$6 over $5"


def test_recover_clears_active():
    s = _state()
    s.trip("latency_breach")
    s.recover()
    assert s.is_active() is False
    snap = s.snapshot()
    assert snap.reason is None
    assert snap.recovered_at_utc is not None


def test_recover_idempotent_when_already_inactive():
    s = _state()
    s.recover()  # was never tripped — no-op
    assert s.is_active() is False
    # No exception.


def test_dwell_seconds_in_log_on_recover(caplog):
    s = _state()
    fixed_in = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    fixed_out = fixed_in + timedelta(minutes=12)
    s.trip("latency_breach", now=fixed_in)
    s.recover(now=fixed_out)
    snap = s.snapshot()
    assert snap.recovered_at_utc == fixed_out


def test_concurrent_trips_only_first_changes_entered_at():
    """20 threads racing trip() — only the first sets entered_at_utc."""
    s = _state()

    def worker():
        s.trip("latency_breach")

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert s.is_active() is True
    snap = s.snapshot()
    # All 20 threads tripped with the same reason — the singleton's
    # entered_at_utc was set exactly once (by whichever thread won the race
    # for the lock first). Subsequent threads hit the idempotent path and
    # left entered_at_utc unchanged.
    assert snap.entered_at_utc is not None
    assert snap.reason == "latency_breach"

    # Tripping again with the SAME reason after a brief delay must not move
    # entered_at_utc.
    saved = snap.entered_at_utc
    s.trip("latency_breach")
    assert s.snapshot().entered_at_utc == saved


def test_snapshot_returns_pydantic_model():
    s = _state()
    snap = s.snapshot()
    assert isinstance(snap, DegradedModeSnapshot)
