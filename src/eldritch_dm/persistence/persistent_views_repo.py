"""
PersistentViewRepo — CRUD for persistent_views table.

All writes go through WriterQueue (BEGIN IMMEDIATE).
All reads use lock-free open_connection.

The payload column is stored as JSON text in the DB; the repo handles
serialization/deserialization transparently.
"""

from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from eldritch_dm.logging import get_logger
from eldritch_dm.persistence.connection import WriterQueue, open_connection
from eldritch_dm.persistence.models import PersistentView


def _row_to_model(row: aiosqlite.Row) -> PersistentView:
    d = dict(row)
    # Deserialize payload_json → payload dict
    payload_json = d.pop("payload_json", "{}")
    d["payload"] = json.loads(payload_json) if payload_json else {}
    # Parse timestamps
    v = d.get("created_at")
    if isinstance(v, str):
        d["created_at"] = datetime.fromisoformat(v)
    return PersistentView(**d)


class PersistentViewRepo:
    """Repository for persistent_views table.

    Args:
        db_path: Path to the SQLite database file.
        writer_queue: The shared WriterQueue; all mutating operations use it.
    """

    def __init__(self, db_path: str, writer_queue: WriterQueue) -> None:
        self._db_path = db_path
        self._writer_queue = writer_queue
        self._logger = get_logger(__name__).bind(repo="persistent_views")

    # ── Writes ────────────────────────────────────────────────────────────────

    async def insert(self, view: PersistentView) -> PersistentView:
        """Insert a new PersistentView row.

        Returns the row as read from the DB after insertion.
        """
        sql = """
            INSERT INTO persistent_views
                (custom_id, view_class, message_id, channel_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """
        payload_json = json.dumps(view.payload)

        async def _do(conn: aiosqlite.Connection) -> dict:
            await conn.execute(
                sql,
                (view.custom_id, view.view_class, view.message_id, view.channel_id, payload_json),
            )
            cursor = await conn.execute(
                "SELECT * FROM persistent_views WHERE custom_id = ?", (view.custom_id,)
            )
            row = await cursor.fetchone()
            assert row is not None
            return dict(row)

        row_dict = await self._writer_queue.submit(_do)
        # Normalize payload_json → payload
        payload_json_val = row_dict.pop("payload_json", "{}")
        row_dict["payload"] = json.loads(payload_json_val) if payload_json_val else {}
        for col in ("created_at",):
            v = row_dict.get(col)
            if isinstance(v, str):
                row_dict[col] = datetime.fromisoformat(v)
        model = PersistentView(**row_dict)
        self._logger.debug("insert_ok", custom_id=view.custom_id)
        return model

    async def delete_for_message(self, message_id: str) -> int:
        """Delete all views associated with a given message_id.

        Returns the number of rows deleted.
        """
        async def _do(conn: aiosqlite.Connection) -> int:
            cursor = await conn.execute(
                "DELETE FROM persistent_views WHERE message_id = ?", (message_id,)
            )
            return cursor.rowcount

        deleted = await self._writer_queue.submit(_do)
        self._logger.debug("delete_for_message_ok", message_id=message_id, deleted=deleted)
        return deleted

    # ── Reads ─────────────────────────────────────────────────────────────────

    async def get(self, custom_id: str) -> PersistentView | None:
        """Return the PersistentView for the given custom_id, or None."""
        async with open_connection(self._db_path) as conn:
            async with conn.execute(
                "SELECT * FROM persistent_views WHERE custom_id = ?", (custom_id,)
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_model(row)

    async def list_by_channel(self, channel_id: str) -> list[PersistentView]:
        """Return all views for a channel, ordered by created_at ASC."""
        async with open_connection(self._db_path) as conn:
            async with conn.execute(
                "SELECT * FROM persistent_views WHERE channel_id = ? ORDER BY created_at ASC",
                (channel_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_model(r) for r in rows]
