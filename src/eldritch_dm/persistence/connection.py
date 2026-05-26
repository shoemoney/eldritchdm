"""
EldritchDM SQLite connection management.

Provides:
  - apply_pragmas: issues the four required PRAGMAs on any connection
  - open_connection: asynccontextmanager yielding a connection with pragmas applied
  - WriterQueue: single long-lived writer connection + asyncio queue for serialized writes

All write operations MUST go through WriterQueue to avoid writer/writer contention.
Read operations may use open_connection directly (WAL allows concurrent readers).

Key invariant (D-17): every write uses BEGIN IMMEDIATE (never a bare transaction).
No await between BEGIN IMMEDIATE and COMMIT except the user-supplied fn.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import aiosqlite

from eldritch_dm.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")


# ── Pragmas ───────────────────────────────────────────────────────────────────


async def apply_pragmas(
    conn: aiosqlite.Connection,
    busy_timeout_ms: int = 5000,
) -> None:
    """Apply the four required PRAGMAs to a connection in the mandated order (D-15).

    Order matters:
        1. foreign_keys=ON   — enforce FK constraints
        2. journal_mode=WAL  — enable WAL mode (idempotent; returns current mode)
        3. busy_timeout      — milliseconds to wait on a locked DB before raising
        4. synchronous=NORMAL — balance durability / performance for WAL

    Logs at DEBUG with the applied settings.
    """
    await conn.execute("PRAGMA foreign_keys = ON")
    cursor = await conn.execute("PRAGMA journal_mode = WAL")
    jm_row = await cursor.fetchone()
    journal_mode = jm_row[0] if jm_row else "unknown"
    await conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    await conn.execute("PRAGMA synchronous = NORMAL")
    await conn.commit()

    log.debug(
        "pragmas_applied",
        journal_mode=journal_mode,
        busy_timeout_ms=busy_timeout_ms,
        synchronous="NORMAL",
        foreign_keys="ON",
    )


# ── Read connections ──────────────────────────────────────────────────────────


@asynccontextmanager
async def open_connection(
    db_path: str | os.PathLike[str],
    busy_timeout_ms: int = 5000,
) -> AsyncIterator[aiosqlite.Connection]:
    """Open a read-capable aiosqlite connection with pragmas applied.

    WAL mode allows concurrent readers while the WriterQueue holds the writer.
    Use for reads only; writes must go through WriterQueue.

    Usage::

        async with open_connection("./eldritch.sqlite3") as conn:
            cursor = await conn.execute("SELECT ...")
            rows = await cursor.fetchall()
    """
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    try:
        await apply_pragmas(conn, busy_timeout_ms=busy_timeout_ms)
        yield conn
    finally:
        await conn.close()


# ── WriterQueue ───────────────────────────────────────────────────────────────


class WriterQueue:
    """Single-writer asyncio queue serializing all SQLite write operations.

    Architecture (D-14, D-16):
    - Owns one long-lived aiosqlite connection (the writer connection).
    - Accepts write coroutines via submit().
    - Drains them in FIFO order on a single background asyncio task.
    - Each write runs under BEGIN IMMEDIATE -> user fn -> COMMIT (D-17).

    Lifecycle::

        wq = WriterQueue(db_path="./eldritch.sqlite3")
        await wq.start()
        # ... use wq.submit(fn) throughout the process lifetime ...
        await wq.stop()   # drains pending writes, closes connection

    Thread safety: WriterQueue is NOT thread-safe. Use from the asyncio event loop only.
    """

    def __init__(
        self,
        db_path: str,
        busy_timeout_ms: int = 5000,
        drain_timeout: float = 5.0,
    ) -> None:
        self._db_path = db_path
        self._busy_timeout_ms = busy_timeout_ms
        self._drain_timeout = drain_timeout

        self._queue: asyncio.Queue[
            tuple[Callable[[aiosqlite.Connection], Awaitable[Any]], asyncio.Future[Any]] | None
        ] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._conn: aiosqlite.Connection | None = None
        self._closed: bool = False

    async def start(self) -> None:
        """Open the writer connection, apply pragmas, and start the drain task."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await apply_pragmas(self._conn, busy_timeout_ms=self._busy_timeout_ms)
        self._task = asyncio.get_event_loop().create_task(self._run(), name="WriterQueue._run")
        log.debug("writer_queue_started", db_path=self._db_path)

    async def _run(self) -> None:
        """Drain loop: consume (fn, future) pairs from the queue and execute them."""
        assert self._conn is not None, "WriterQueue._run called before start()"

        while True:
            item = await self._queue.get()
            if item is None:
                # Sentinel: graceful shutdown
                self._queue.task_done()
                break

            fn, fut = item
            q_depth = self._queue.qsize()
            log.debug("writer_queue_dequeue", q_depth=q_depth)

            try:
                # BEGIN IMMEDIATE: acquire write lock immediately; no bare transaction.
                await self._conn.execute("BEGIN IMMEDIATE")
                result = await fn(self._conn)
                await self._conn.commit()
                fut.set_result(result)
            except Exception as exc:  # noqa: BLE001
                try:
                    await self._conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
                fut.set_exception(exc)
            finally:
                self._queue.task_done()

    async def submit(
        self,
        fn: Callable[[aiosqlite.Connection], Awaitable[T]],
    ) -> T:
        """Schedule a write coroutine and await its result.

        The coroutine receives the writer connection inside an active
        BEGIN IMMEDIATE transaction.  It must NOT commit or rollback;
        WriterQueue does that after fn returns.

        Args:
            fn: An async callable that takes an aiosqlite.Connection and
                returns a result.  It runs inside BEGIN IMMEDIATE.

        Returns:
            Whatever fn returns.

        Raises:
            RuntimeError: if stop() has already been called.
            Any exception raised by fn.
        """
        if self._closed:
            raise RuntimeError("WriterQueue has been stopped; cannot accept new submissions")

        loop = asyncio.get_event_loop()
        fut: asyncio.Future[T] = loop.create_future()
        q_depth = self._queue.qsize()
        log.debug("writer_queue_submit", q_depth=q_depth)
        await self._queue.put((fn, fut))  # type: ignore[arg-type]
        return await fut

    async def stop(self) -> None:
        """Stop the writer queue, draining pending writes, then close the connection.

        Puts a sentinel (None) onto the queue so _run() exits cleanly.
        Waits up to self._drain_timeout seconds for the queue to drain.
        Runs a final connection close regardless.
        """
        self._closed = True
        await self._queue.put(None)  # sentinel

        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self._drain_timeout)
            except TimeoutError:
                log.warning("writer_queue_drain_timeout", drain_timeout=self._drain_timeout)
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None

        log.debug("writer_queue_stopped", db_path=self._db_path)

    def qsize(self) -> int:
        """Return the number of pending items in the queue (excluding the sentinel)."""
        return self._queue.qsize()
