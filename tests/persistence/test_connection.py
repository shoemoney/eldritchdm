"""
Tests for eldritch_dm.persistence.connection — pragmas, open_connection, WriterQueue.
"""

from __future__ import annotations

import asyncio
import re

import aiosqlite
import pytest

from eldritch_dm.persistence.connection import (
    WriterQueue,
    apply_pragmas,
    open_connection,
)


class TestPragmasSet:
    """apply_pragmas sets all four PRAGMAs correctly."""

    async def test_pragmas_set(self, tmp_path: pytest.TempPathFactory) -> None:
        db_path = tmp_path / "test.sqlite3"
        conn = await aiosqlite.connect(str(db_path))
        try:
            await apply_pragmas(conn, busy_timeout_ms=5000)

            # journal_mode
            cursor = await conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            assert row[0] == "wal", f"Expected 'wal', got {row[0]!r}"

            # foreign_keys: 1 = ON
            cursor = await conn.execute("PRAGMA foreign_keys")
            row = await cursor.fetchone()
            assert row[0] == 1, f"Expected 1 (ON), got {row[0]!r}"

            # busy_timeout: 5000ms
            cursor = await conn.execute("PRAGMA busy_timeout")
            row = await cursor.fetchone()
            assert row[0] == 5000, f"Expected 5000, got {row[0]!r}"

            # synchronous: 1 = NORMAL
            cursor = await conn.execute("PRAGMA synchronous")
            row = await cursor.fetchone()
            assert row[0] == 1, f"Expected 1 (NORMAL), got {row[0]!r}"
        finally:
            await conn.close()


class TestOpenConnection:
    """open_connection yields a pragmas-applied connection and closes cleanly."""

    async def test_open_connection_closes_on_exit(self, tmp_path: pytest.TempPathFactory) -> None:
        db_path = tmp_path / "test_close.sqlite3"

        conn_ref: aiosqlite.Connection | None = None
        async with open_connection(db_path) as conn:
            conn_ref = conn
            # Connection should be open inside the context
            cursor = await conn.execute("SELECT 1")
            row = await cursor.fetchone()
            assert row[0] == 1

        # After context exit, connection should be closed
        # aiosqlite stores the underlying connection in _connection
        assert conn_ref is not None
        # The internal connection should be None or closed
        assert (
            conn_ref._connection is None
        ), "Connection should be closed after context manager exit"

    async def test_open_connection_has_pragmas(self, tmp_path: pytest.TempPathFactory) -> None:
        db_path = tmp_path / "test_pragmas.sqlite3"
        async with open_connection(db_path, busy_timeout_ms=3000) as conn:
            cursor = await conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            assert row[0] == "wal"

            cursor = await conn.execute("PRAGMA foreign_keys")
            row = await cursor.fetchone()
            assert row[0] == 1


class TestWriterQueueSerializes:
    """WriterQueue serializes writes; 50 concurrent submits all succeed."""

    async def test_writer_queue_serializes(self, tmp_path: pytest.TempPathFactory) -> None:
        db_path = str(tmp_path / "test_writer.sqlite3")
        wq = WriterQueue(db_path=db_path)
        await wq.start()

        try:
            # Create table first (via submit so it's through the writer connection)
            async def create_table(conn: aiosqlite.Connection) -> None:
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS _kv (k TEXT PRIMARY KEY, v INTEGER)"
                )

            await wq.submit(create_table)

            # Submit 50 concurrent inserts
            async def insert(k: str, v: int) -> None:
                async def _fn(conn: aiosqlite.Connection) -> None:
                    await conn.execute("INSERT INTO _kv VALUES (?, ?)", (k, v))

                await wq.submit(_fn)

            await asyncio.gather(*[insert(f"key-{i}", i) for i in range(50)])

            # Verify all 50 rows exist
            async with open_connection(db_path) as conn:
                cursor = await conn.execute("SELECT COUNT(*) FROM _kv")
                row = await cursor.fetchone()
                assert row[0] == 50, f"Expected 50 rows, got {row[0]}"
        finally:
            await wq.stop()


class TestWriterQueueUsesBeginImmediate:
    """Static source check: connection.py uses BEGIN IMMEDIATE, not plain BEGIN."""

    def test_writer_queue_uses_begin_immediate(self) -> None:
        import pathlib

        source_path = (
            pathlib.Path(__file__).parents[2]
            / "src"
            / "eldritch_dm"
            / "persistence"
            / "connection.py"
        )
        source = source_path.read_text()

        # Must contain BEGIN IMMEDIATE
        assert "BEGIN IMMEDIATE" in source, "connection.py must use BEGIN IMMEDIATE for writes"

        # Must NOT have plain BEGIN outside comments
        lines = source.splitlines()
        plain_begin_pattern = re.compile(r"\bBEGIN(?!\s+IMMEDIATE)\b")
        comment_pattern = re.compile(r"^\s*#")

        violations = []
        in_docstring = False
        for lineno, line in enumerate(lines, 1):
            # Skip full-line comments
            if comment_pattern.match(line):
                continue
            # Track triple-quoted docstrings (simple heuristic)
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            # Strip inline comments
            code_part = line.split("#")[0]
            if plain_begin_pattern.search(code_part):
                violations.append(f"  Line {lineno}: {line!r}")

        assert not violations, (
            "Found plain BEGIN (without IMMEDIATE) in non-comment code:\n"
            + "\n".join(violations)
        )


class TestWriterQueueStopDrains:
    """stop() drains pending submissions before closing."""

    async def test_writer_queue_stop_drains(self, tmp_path: pytest.TempPathFactory) -> None:
        db_path = str(tmp_path / "test_drain.sqlite3")
        wq = WriterQueue(db_path=db_path)
        await wq.start()

        # Create table
        async def create_table(conn: aiosqlite.Connection) -> None:
            await conn.execute("CREATE TABLE IF NOT EXISTS _drain (v INTEGER)")

        await wq.submit(create_table)

        completed = []

        async def slow_write(v: int) -> None:
            async def _fn(conn: aiosqlite.Connection) -> None:
                await asyncio.sleep(0.05)
                await conn.execute("INSERT INTO _drain VALUES (?)", (v,))

            await wq.submit(_fn)
            completed.append(v)

        # Start two slow writes as tasks (they'll be queued but not yet awaited fully)
        task1 = asyncio.create_task(slow_write(1))
        task2 = asyncio.create_task(slow_write(2))

        # Give the tasks a moment to submit to the queue
        await asyncio.sleep(0.01)

        # Stop drains the queue — both writes should complete
        await wq.stop()

        # Now gather: tasks should already be done or complete quickly
        await asyncio.gather(task1, task2, return_exceptions=True)

        assert len(completed) == 2
        assert set(completed) == {1, 2}


class TestWriterQueueRaisesAfterStop:
    """submit() raises RuntimeError after stop() is called."""

    async def test_writer_queue_raises_after_stop(self, tmp_path: pytest.TempPathFactory) -> None:
        db_path = str(tmp_path / "test_stopped.sqlite3")
        wq = WriterQueue(db_path=db_path)
        await wq.start()
        await wq.stop()

        with pytest.raises(RuntimeError, match="stopped"):
            await wq.submit(lambda conn: asyncio.coroutine(lambda: None)())
