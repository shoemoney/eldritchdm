"""
SanitizerAuditRepo — append-only insert for sanitizer_audit table.

All writes go through WriterQueue (BEGIN IMMEDIATE).
Reads are minimal (count only) — forensic log data is not paginated in v1.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from eldritch_dm.logging import get_logger
from eldritch_dm.persistence.connection import WriterQueue, open_connection
from eldritch_dm.persistence.models import SanitizerAuditRow


def _row_to_model(row: aiosqlite.Row) -> SanitizerAuditRow:
    d = dict(row)
    # Deserialize stripped_tokens JSON array
    st = d.get("stripped_tokens", "[]")
    d["stripped_tokens"] = json.loads(st) if st else []
    # truncated is stored as INTEGER (0/1)
    d["truncated"] = bool(d.get("truncated", 0))
    # Parse timestamp
    v = d.get("ts")
    if isinstance(v, str):
        d["ts"] = datetime.fromisoformat(v)
    return SanitizerAuditRow(**d)


class SanitizerAuditRepo:
    """Repository for sanitizer_audit table.

    Append-only: rows are written once and never updated.

    Args:
        db_path: Path to the SQLite database file.
        writer_queue: The shared WriterQueue; all mutating operations use it.
    """

    def __init__(self, db_path: str, writer_queue: WriterQueue) -> None:
        self._db_path = db_path
        self._writer_queue = writer_queue
        self._logger = get_logger(__name__).bind(repo="sanitizer_audit")

    # ── Writes ────────────────────────────────────────────────────────────────

    async def insert(self, row: SanitizerAuditRow) -> SanitizerAuditRow:
        """Append a sanitizer audit row to the table.

        Returns the row as read from the DB after insertion (id populated).
        """
        sql = """
            INSERT INTO sanitizer_audit
                (channel_id, user_id, raw_input, stripped_tokens,
                 redacted_output, truncated, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        stripped_json = json.dumps(row.stripped_tokens)
        truncated_int = 1 if row.truncated else 0
        ts_str = row.ts.isoformat()

        async def _do(conn: aiosqlite.Connection) -> dict:
            cursor = await conn.execute(
                sql,
                (
                    row.channel_id,
                    row.user_id,
                    row.raw_input,
                    stripped_json,
                    row.redacted_output,
                    truncated_int,
                    ts_str,
                ),
            )
            row_id = cursor.lastrowid
            cursor2 = await conn.execute(
                "SELECT * FROM sanitizer_audit WHERE id = ?", (row_id,)
            )
            db_row = await cursor2.fetchone()
            assert db_row is not None
            return dict(db_row)

        row_dict = await self._writer_queue.submit(_do)
        # Normalize types
        st = row_dict.get("stripped_tokens", "[]")
        row_dict["stripped_tokens"] = json.loads(st) if st else []
        row_dict["truncated"] = bool(row_dict.get("truncated", 0))
        v = row_dict.get("ts")
        if isinstance(v, str):
            row_dict["ts"] = datetime.fromisoformat(v)
        model = SanitizerAuditRow(**row_dict)
        self._logger.debug("insert_ok", id=model.id, channel_id=row.channel_id)
        return model

    # ── Reads ─────────────────────────────────────────────────────────────────

    async def count(self) -> int:
        """Return the total number of audit rows (used in tests)."""
        async with open_connection(self._db_path) as conn:
            async with conn.execute("SELECT COUNT(*) FROM sanitizer_audit") as cur:
                row = await cur.fetchone()
        return row[0] if row else 0
