"""Local SQLite span buffer (Phase 13 / MON-01 / D-83, D-92, R-13-01-a/b).

Primary sink for every traced decision in EldritchDM. The 5-minute KPI
monitors (``kpi.py``) and the cost-report CLI (``tools/cost_report.py``) read
exclusively from this buffer, so KPI + budget enforcement work even when
``OBSERVABILITY_ENABLED=false`` (Phoenix off, OTLP exporter not initialized).

Architectural rules (R-13-01-a/b/c):

1. **Buffer is the primary sink**, OTLP is secondary. The ``traced_*`` context
   managers in ``instrumentation.py`` always write a row here on ``__exit__``;
   OTel export is opt-in via ``OBSERVABILITY_ENABLED``.

2. **Writes are non-blocking**. ``record(row)`` enqueues into an in-process
   ``queue.Queue``; a daemon thread drains the queue into SQLite, batching up
   to 100 rows or 500 ms. Worst-case enqueue cost on the bot's event loop is
   one ``put_nowait``.

3. **Lazy module-level imports only**. This module imports stdlib ``sqlite3``,
   ``queue``, ``threading``, ``pydantic`` — NEVER ``opentelemetry`` or
   ``prometheus_client``. The lazy-import canaries in
   ``tests/observability/test_lazy_import.py`` and
   ``tests/observability/test_metrics_lazy_import.py`` enforce this.

4. **Inversion of control for observers**. External modules (e.g.
   ``metrics_endpoint``) may register a post-write callback via
   ``SpanBuffer.add_post_write_observer(...)`` without forcing this module to
   import their libraries. Callbacks fire synchronously after enqueue; one
   raising observer cannot break the hot path or affect siblings.

5. **Hot-path init must be cheap**. ``init_buffer()`` checks a module-level
   sentinel under a one-time lock and returns immediately on calls 2..N — no
   ``mkdir``, no ``sqlite3.connect``, no schema check on the hot path.
"""

from __future__ import annotations

import os
import queue
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from eldritch_dm.logging import get_logger

log = get_logger(__name__)

# ── Schema ───────────────────────────────────────────────────────────────────

#: Maximum in-process queue depth before record() starts dropping rows. A
#: bot under pathological load will lose monitoring rather than block the
#: event loop or eat unbounded memory.
_MAX_QUEUE_DEPTH = 10_000

#: Drainer batch size. The background thread commits whenever it has this
#: many rows OR has been waiting longer than ``_DRAIN_MAX_WAIT_S``.
_DRAIN_BATCH_SIZE = 100

#: Maximum wait between drains, even if the queue hasn't reached the batch
#: size. Bounds the latency between record() and the row being queryable.
_DRAIN_MAX_WAIT_S = 0.5

#: Default rolling-retention window. ``init_buffer()`` calls
#: ``prune_older_than(days=7)`` on first open so a long-running bot doesn't
#: grow the buffer unboundedly.
_DEFAULT_RETENTION_DAYS = 7

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS spans (
    timestamp_utc    TEXT    NOT NULL,
    span_name        TEXT    NOT NULL,
    monster_id       TEXT,
    channel_id       TEXT,
    combat_round     INTEGER,
    driver_path      TEXT,
    latency_ms       INTEGER,
    tokens_input     INTEGER,
    tokens_output    INTEGER,
    fallback_reason  TEXT,
    model            TEXT,
    scenario_id      TEXT,
    overall_score    REAL,
    refusal          INTEGER NOT NULL DEFAULT 0,
    error            TEXT
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_spans_ts_monster_channel
ON spans (timestamp_utc, monster_id, channel_id)
"""

_INSERT_SQL = """
INSERT INTO spans (
    timestamp_utc, span_name, monster_id, channel_id, combat_round,
    driver_path, latency_ms, tokens_input, tokens_output,
    fallback_reason, model, scenario_id, overall_score, refusal, error
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_BUFFER_COLS = (
    "timestamp_utc",
    "span_name",
    "monster_id",
    "channel_id",
    "combat_round",
    "driver_path",
    "latency_ms",
    "tokens_input",
    "tokens_output",
    "fallback_reason",
    "model",
    "scenario_id",
    "overall_score",
    "refusal",
    "error",
)


# ── Pydantic row model ───────────────────────────────────────────────────────


class BufferRow(BaseModel):
    """One buffered span row.

    All metric-bearing fields are ``Optional`` because different span kinds
    populate different columns:

    - ``eldritch.monster.decision`` (Phase 11 / OBS-01) — populates
      monster_id, channel_id, combat_round, driver_path, latency_ms,
      tokens_input/output, fallback_reason, refusal.
    - ``eldritch.ingest.translate`` — populates channel_id, latency_ms,
      tokens_input/output, model.
    - ``eldritch.eval.judge`` (Phase 12 / EVAL-03) — populates scenario_id,
      model, latency_ms, tokens_input/output, overall_score.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    span_name: str
    monster_id: str | None = None
    channel_id: str | None = None
    combat_round: int | None = None
    driver_path: str | None = None
    latency_ms: int | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    fallback_reason: str | None = None
    model: str | None = None
    scenario_id: str | None = None
    overall_score: float | None = None
    refusal: bool = False
    error: str | None = None


# ── SpanBuffer (one per process) ─────────────────────────────────────────────


class SpanBuffer:
    """Thread-safe queue-and-drain buffer over a single SQLite file.

    Instances are managed via the module-level ``init_buffer()`` singleton —
    construct directly only for tests that need to bypass the singleton.
    """

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._queue: queue.Queue[BufferRow] = queue.Queue(maxsize=_MAX_QUEUE_DEPTH)
        self._stop_event = threading.Event()
        self._observers: list[Callable[[BufferRow], None]] = []
        self._observer_lock = threading.Lock()
        # Counter for tests + the "queue overflow" log throttle.
        self._dropped_count = 0
        self._dropped_lock = threading.Lock()

        # Schema setup runs in the foreground (one time, on first init_buffer
        # call) so failures are loud and immediate, not buried in the drainer.
        self._setup_schema()

        # Daemon thread keeps the process from hanging on shutdown even if
        # the queue still has rows. Tests should call ``flush()`` to drain
        # synchronously.
        self._drainer = threading.Thread(
            target=self._drain_loop,
            name="span-buffer-drainer",
            daemon=True,
        )
        self._drainer.start()

    @property
    def db_path(self) -> Path:
        """The SQLite file backing this buffer."""
        return self._db_path

    @property
    def dropped_count(self) -> int:
        """Number of rows dropped due to queue overflow since process start."""
        with self._dropped_lock:
            return self._dropped_count

    def _setup_schema(self) -> None:
        """Create the schema + WAL mode. Runs once per process."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)
            conn.commit()
        finally:
            conn.close()

    # ── Public write surface ─────────────────────────────────────────────────

    def record(self, row: BufferRow) -> None:
        """Enqueue one row for asynchronous persistence.

        Hot-path-only contract: this method MUST NOT block, MUST NOT raise.
        On queue overflow the row is dropped and a structured warning is
        logged (rate-limited via the dropped-count counter so a sustained
        overflow doesn't spam the log).
        """
        try:
            self._queue.put_nowait(row)
        except queue.Full:
            with self._dropped_lock:
                self._dropped_count += 1
                # Log every 1000 drops so operators see the issue without
                # being flooded.
                if self._dropped_count % 1000 == 1:
                    log.warning(
                        "span_buffer.queue_overflow",
                        dropped_total=self._dropped_count,
                        max_depth=_MAX_QUEUE_DEPTH,
                    )

        # Observer callbacks run AFTER the enqueue, regardless of whether
        # the enqueue succeeded — observers care about the logical event,
        # not the storage layer.
        self._fire_observers(row)

    def add_post_write_observer(self, observer: Callable[[BufferRow], None]) -> None:
        """Register an IoC callback fired after every ``record()`` call.

        Used by ``metrics_endpoint`` to increment Prometheus counters without
        ``span_buffer`` having to import ``prometheus_client`` (preserves the
        lazy-import canary in tests).

        Callbacks fire synchronously on the calling thread. Exceptions are
        caught and logged — one misbehaving observer cannot break the hot
        path or affect siblings.
        """
        with self._observer_lock:
            self._observers.append(observer)

    def _fire_observers(self, row: BufferRow) -> None:
        # Snapshot under the lock so a concurrent add doesn't race.
        with self._observer_lock:
            observers = list(self._observers)
        for obs in observers:
            try:
                obs(row)
            except Exception as exc:  # noqa: BLE001 — never propagate
                log.warning(
                    "span_buffer.observer_error",
                    observer=getattr(obs, "__name__", repr(obs)),
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )

    # ── Drainer loop ─────────────────────────────────────────────────────────

    def _drain_loop(self) -> None:
        """Background thread: pull rows, batch-commit to SQLite."""
        # Open a thread-local SQLite connection — sqlite3.Connection is not
        # threadsafe across thread boundaries.
        conn = sqlite3.connect(str(self._db_path))
        try:
            while not self._stop_event.is_set():
                batch = self._collect_batch()
                if batch:
                    self._write_batch(conn, batch)
            # On stop, drain anything left in the queue so flush() callers
            # observe a consistent state.
            tail = self._drain_all_remaining()
            if tail:
                self._write_batch(conn, tail)
        finally:
            conn.close()

    def _collect_batch(self) -> list[BufferRow]:
        """Wait up to ``_DRAIN_MAX_WAIT_S`` for up to ``_DRAIN_BATCH_SIZE`` rows."""
        batch: list[BufferRow] = []
        try:
            # Block for the first row so an idle bot doesn't spin.
            first = self._queue.get(timeout=_DRAIN_MAX_WAIT_S)
            batch.append(first)
        except queue.Empty:
            return batch
        # Drain up to batch size without blocking — already have at least 1.
        while len(batch) < _DRAIN_BATCH_SIZE:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _drain_all_remaining(self) -> list[BufferRow]:
        """Pull everything currently in the queue, no waiting."""
        rows: list[BufferRow] = []
        while True:
            try:
                rows.append(self._queue.get_nowait())
            except queue.Empty:
                return rows

    def _write_batch(self, conn: sqlite3.Connection, rows: list[BufferRow]) -> None:
        try:
            payload = [self._row_to_tuple(r) for r in rows]
            conn.executemany(_INSERT_SQL, payload)
            conn.commit()
        except sqlite3.DatabaseError as exc:
            log.error(
                "span_buffer.write_error",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
                batch_size=len(rows),
            )

    @staticmethod
    def _row_to_tuple(row: BufferRow) -> tuple[Any, ...]:
        return (
            row.timestamp_utc.isoformat(),
            row.span_name,
            row.monster_id,
            row.channel_id,
            row.combat_round,
            row.driver_path,
            row.latency_ms,
            row.tokens_input,
            row.tokens_output,
            row.fallback_reason,
            row.model,
            row.scenario_id,
            row.overall_score,
            1 if row.refusal else 0,
            row.error,
        )

    # ── Synchronous helpers (tests, KPI computer, cost report) ───────────────

    def flush(self, timeout_s: float = 2.0) -> None:
        """Block until the queue is empty AND committed to SQLite.

        Used by tests and by ``compute_kpis`` / cost-report before reading,
        so that recently recorded rows are visible to ``query()``.
        """
        deadline = datetime.now(UTC) + timedelta(seconds=timeout_s)
        while datetime.now(UTC) < deadline:
            if self._queue.empty():
                # Give the drainer one tick to finish committing the last
                # batch it pulled.
                self._stop_event.wait(timeout=_DRAIN_MAX_WAIT_S + 0.05)
                return
            self._stop_event.wait(timeout=0.01)
        log.warning("span_buffer.flush_timeout", timeout_s=timeout_s)

    def query(
        self,
        since: datetime,
        until: datetime | None = None,
        span_name: str | None = None,
    ) -> list[BufferRow]:
        """Read rows in ``[since, until)``, optionally filtered by span_name.

        Read API for KPI computer + cost report. Opens a short-lived
        thread-local connection so callers from arbitrary threads work.
        """
        until = until or datetime.now(UTC)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            sql = (
                "SELECT " + ", ".join(_BUFFER_COLS) + " FROM spans "
                "WHERE timestamp_utc >= ? AND timestamp_utc < ?"
            )
            params: list[Any] = [since.isoformat(), until.isoformat()]
            if span_name is not None:
                sql += " AND span_name = ?"
                params.append(span_name)
            sql += " ORDER BY timestamp_utc ASC"
            cur = conn.execute(sql, params)
            return [self._tuple_to_row(t) for t in cur.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def _tuple_to_row(t: tuple[Any, ...]) -> BufferRow:
        d = dict(zip(_BUFFER_COLS, t, strict=True))
        d["timestamp_utc"] = datetime.fromisoformat(d["timestamp_utc"])
        d["refusal"] = bool(d["refusal"])
        return BufferRow(**d)

    def prune_older_than(self, days: int = _DEFAULT_RETENTION_DAYS) -> int:
        """Delete rows with ``timestamp_utc`` older than ``days`` ago. Returns row count."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            cur = conn.execute(
                "DELETE FROM spans WHERE timestamp_utc < ?",
                (cutoff.isoformat(),),
            )
            count = cur.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    def close(self) -> None:
        """Signal the drainer to stop and wait for it. Tests + shutdown only."""
        self._stop_event.set()
        self._drainer.join(timeout=5.0)


# ── Module-level singleton (hot-path-cheap) ──────────────────────────────────


#: Module-level singleton + lock. ``init_buffer()`` enters the lock once on
#: first call; subsequent calls return ``_BUFFER`` without acquiring any lock.
_BUFFER: SpanBuffer | None = None
_BUFFER_LOCK = threading.Lock()


def _resolve_path(explicit: Path | None) -> Path:
    """Resolve the buffer SQLite path: explicit > env > ~/.eldritch/spans.sqlite."""
    if explicit is not None:
        return explicit
    env_path = os.environ.get("ELDRITCH_SPAN_BUFFER_PATH")
    if env_path:
        return Path(env_path)
    return Path.home() / ".eldritch" / "spans.sqlite"


def init_buffer(path: Path | None = None) -> SpanBuffer:
    """Return the singleton ``SpanBuffer``. Hot-path-cheap on calls 2..N.

    The first call resolves the path, creates parents, opens SQLite, applies
    WAL + busy-timeout pragmas, creates the schema, and runs a one-time
    retention prune. Subsequent calls return immediately without acquiring a
    lock (the global write happens once under the lock; the read on later
    calls sees the stable value).

    Tests use ``reset_for_tests()`` to clear the singleton.
    """
    # Cheap fast path — no lock acquisition on the hot path.
    global _BUFFER
    if _BUFFER is not None:
        return _BUFFER

    with _BUFFER_LOCK:
        # Double-check under the lock in case another thread won the race.
        if _BUFFER is not None:
            return _BUFFER
        resolved = _resolve_path(path)
        buf = SpanBuffer(resolved)
        # One-time retention prune on startup. Best-effort: a failed prune is
        # logged but does not prevent the buffer from coming up.
        try:
            pruned = buf.prune_older_than(_DEFAULT_RETENTION_DAYS)
            if pruned:
                log.info(
                    "span_buffer.startup_pruned",
                    rows=pruned,
                    retention_days=_DEFAULT_RETENTION_DAYS,
                )
        except sqlite3.DatabaseError as exc:
            log.warning(
                "span_buffer.startup_prune_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
        _BUFFER = buf
        log.info("span_buffer.initialized", path=str(resolved))
        return _BUFFER


def reset_for_tests() -> None:
    """Drop the singleton so the next ``init_buffer()`` opens a fresh DB.

    Test-only: tests that need a tmp_path buffer call this in their setup
    and pass an explicit path. Closes the existing buffer's drainer thread
    cleanly.
    """
    global _BUFFER
    with _BUFFER_LOCK:
        if _BUFFER is not None:
            _BUFFER.close()
        _BUFFER = None
