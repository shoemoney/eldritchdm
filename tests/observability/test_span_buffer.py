"""Tests for the local SQLite span buffer (Phase 13 / MON-01 / Task 02).

Verifies:
  - Round-trip record→flush→query
  - WAL journaling active
  - Retention prune deletes rows older than N days
  - Queue overflow drops rows + logs (does not raise)
  - Parent directory auto-created
  - Thread-safe under 1000 concurrent records
  - Observer callbacks fire post-write
  - Raising observer is logged but does not propagate
  - ``init_buffer()`` hot-path early-return: a second call does not re-open SQLite
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta

import pytest

from eldritch_dm.observability import span_buffer
from eldritch_dm.observability.span_buffer import (
    BufferRow,
    init_buffer,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch, tmp_path):
    """Each test starts with a fresh singleton pointed at a tmp_path SQLite."""
    monkeypatch.setenv(
        "ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite")
    )
    reset_for_tests()
    yield
    reset_for_tests()


def _decision_row(latency_ms: int = 100, **overrides) -> BufferRow:
    base = {
        "span_name": "eldritch.monster.decision",
        "monster_id": "m1",
        "channel_id": "c1",
        "combat_round": 3,
        "driver_path": "smart",
        "latency_ms": latency_ms,
        "tokens_input": 500,
        "tokens_output": 100,
    }
    base.update(overrides)
    return BufferRow(**base)


def test_init_buffer_creates_parent_directory(tmp_path, monkeypatch):
    nested = tmp_path / "subdir" / "deeper" / "spans.sqlite"
    monkeypatch.setenv("ELDRITCH_SPAN_BUFFER_PATH", str(nested))
    reset_for_tests()
    buf = init_buffer()
    assert nested.parent.is_dir()
    assert nested.exists()
    assert buf.db_path == nested


def test_init_buffer_enables_wal_mode():
    buf = init_buffer()
    conn = sqlite3.connect(str(buf.db_path))
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal"


def test_init_buffer_is_singleton():
    a = init_buffer()
    b = init_buffer()
    assert a is b


def test_init_buffer_hot_path_skips_reinit(monkeypatch):
    """Calls 2..N must NOT re-enter the schema-create path."""
    a = init_buffer()
    # Patch sqlite3.connect to raise — if the hot path tried to re-open
    # the DB, this test would fail.
    monkeypatch.setattr(
        sqlite3,
        "connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("hot path should not re-open SQLite")
        ),
    )
    b = init_buffer()
    assert b is a


def test_record_flush_query_roundtrip():
    buf = init_buffer()
    now = datetime.now(UTC)
    rows = [
        _decision_row(
            latency_ms=i * 10,
            timestamp_utc=now - timedelta(seconds=10 - i),
        )
        for i in range(5)
    ]
    for r in rows:
        buf.record(r)
    buf.flush(timeout_s=3.0)
    fetched = buf.query(since=now - timedelta(minutes=1))
    assert len(fetched) == 5
    assert [r.latency_ms for r in fetched] == [0, 10, 20, 30, 40]


def test_query_filters_by_span_name():
    buf = init_buffer()
    now = datetime.now(UTC)
    buf.record(_decision_row(timestamp_utc=now - timedelta(seconds=1)))
    buf.record(
        BufferRow(
            span_name="eldritch.ingest.translate",
            channel_id="c1",
            latency_ms=200,
            tokens_input=100,
            tokens_output=50,
            model="ShoeGPT",
            timestamp_utc=now - timedelta(seconds=1),
        )
    )
    buf.flush(timeout_s=3.0)
    decisions = buf.query(
        since=now - timedelta(minutes=1),
        span_name="eldritch.monster.decision",
    )
    translates = buf.query(
        since=now - timedelta(minutes=1),
        span_name="eldritch.ingest.translate",
    )
    assert len(decisions) == 1
    assert len(translates) == 1
    assert translates[0].model == "ShoeGPT"


def test_prune_older_than_removes_old_rows():
    buf = init_buffer()
    now = datetime.now(UTC)
    # 1 row 10 days old, 1 row 1 day old.
    buf.record(_decision_row(timestamp_utc=now - timedelta(days=10)))
    buf.record(_decision_row(timestamp_utc=now - timedelta(days=1)))
    buf.flush(timeout_s=3.0)

    removed = buf.prune_older_than(days=7)
    assert removed == 1
    remaining = buf.query(since=now - timedelta(days=365))
    assert len(remaining) == 1


def test_queue_overflow_drops_rows_without_raising(monkeypatch, caplog):
    """Pathological-load safety valve: drop rather than block or OOM."""
    # Construct a tiny-capacity buffer directly so we don't have to flood
    # 10k rows.
    monkeypatch.setattr(span_buffer, "_MAX_QUEUE_DEPTH", 5)
    monkeypatch.setattr(span_buffer, "_DRAIN_MAX_WAIT_S", 1000.0)  # freeze drainer
    # Reset singleton so the new constants apply.
    reset_for_tests()
    buf = init_buffer()
    # Push 50 rows; only ~5 will fit before drainer eventually catches up.
    for _ in range(50):
        buf.record(_decision_row())
    # No exception above; drops_count should be >0.
    assert buf.dropped_count > 0


def test_observer_callbacks_fire_post_write():
    buf = init_buffer()
    received: list[BufferRow] = []
    buf.add_post_write_observer(lambda r: received.append(r))
    row = _decision_row()
    buf.record(row)
    # Observer fires synchronously in record(); no flush needed.
    assert len(received) == 1
    assert received[0].monster_id == "m1"


def test_raising_observer_does_not_propagate():
    buf = init_buffer()
    sentinel: list[str] = []

    def bad_observer(_row: BufferRow) -> None:
        raise RuntimeError("boom")

    def good_observer(row: BufferRow) -> None:
        sentinel.append(row.monster_id or "?")

    buf.add_post_write_observer(bad_observer)
    buf.add_post_write_observer(good_observer)
    buf.record(_decision_row())  # Must not raise.
    # Good observer still ran despite bad observer raising.
    assert sentinel == ["m1"]


def test_threadsafe_concurrent_records():
    buf = init_buffer()
    n_threads = 10
    rows_per_thread = 100

    def worker():
        for i in range(rows_per_thread):
            buf.record(_decision_row(latency_ms=i))

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    buf.flush(timeout_s=5.0)
    rows = buf.query(since=datetime.now(UTC) - timedelta(minutes=5))
    # All 1000 rows landed (no queue overflow at default depth=10_000).
    assert len(rows) == n_threads * rows_per_thread
    assert buf.dropped_count == 0


def test_record_with_fallback_reason_persists_column():
    buf = init_buffer()
    buf.record(
        _decision_row(fallback_reason="timeout", refusal=False)
    )
    buf.flush(timeout_s=3.0)
    rows = buf.query(since=datetime.now(UTC) - timedelta(minutes=1))
    assert len(rows) == 1
    assert rows[0].fallback_reason == "timeout"


def test_record_with_eval_judge_columns():
    """eldritch.eval.judge spans populate scenario_id + overall_score."""
    buf = init_buffer()
    buf.record(
        BufferRow(
            span_name="eldritch.eval.judge",
            scenario_id="brute-01",
            model="claude-haiku-4-5-20251001",
            latency_ms=350,
            tokens_input=1500,
            tokens_output=400,
            overall_score=0.85,
        )
    )
    buf.flush(timeout_s=3.0)
    rows = buf.query(
        since=datetime.now(UTC) - timedelta(minutes=1),
        span_name="eldritch.eval.judge",
    )
    assert len(rows) == 1
    assert rows[0].scenario_id == "brute-01"
    assert rows[0].overall_score == pytest.approx(0.85)
