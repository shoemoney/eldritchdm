"""
ChannelSessionRepo — CRUD for channel_sessions table.

All writes go through WriterQueue (BEGIN IMMEDIATE).
All reads use lock-free open_connection (WAL allows concurrent readers).

Returned values are always frozen pydantic ChannelSession instances.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import aiosqlite

from eldritch_dm.logging import get_logger
from eldritch_dm.persistence.connection import WriterQueue, open_connection
from eldritch_dm.persistence.models import ChannelSession, ChannelState


def _row_to_model(row: aiosqlite.Row) -> ChannelSession:
    """Convert an aiosqlite.Row (with row_factory=Row) to a ChannelSession."""
    d = dict(row)
    # Timestamps may come back as strings; parse to datetime
    for col in ("created_at", "updated_at"):
        v = d.get(col)
        if isinstance(v, str):
            d[col] = datetime.fromisoformat(v)
    return ChannelSession(**d)


class ChannelSessionRepo:
    """Repository for channel_sessions table.

    Args:
        db_path: Path to the SQLite database file.
        writer_queue: The shared WriterQueue; all mutating operations use it.
    """

    def __init__(self, db_path: str, writer_queue: WriterQueue) -> None:
        self._db_path = db_path
        self._writer_queue = writer_queue
        self._logger = get_logger(__name__).bind(repo="channel_sessions")

    # ── Writes (via WriterQueue) ──────────────────────────────────────────────

    async def upsert(
        self,
        *,
        channel_id: str,
        campaign_name: str,
        claudmaster_session_id: str | None = None,
        dm20_party_token: str | None = None,
        state: ChannelState = ChannelState.LOBBY,
    ) -> ChannelSession:
        """Insert or update a channel session row.

        On conflict (channel_id already exists), updates all fields and bumps
        updated_at to CURRENT_TIMESTAMP.

        Returns the freshly read ChannelSession after upsert.
        """
        sql = """
            INSERT INTO channel_sessions
                (channel_id, campaign_name, claudmaster_session_id, dm20_party_token,
                 state, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(channel_id) DO UPDATE SET
                campaign_name          = excluded.campaign_name,
                claudmaster_session_id = excluded.claudmaster_session_id,
                dm20_party_token       = excluded.dm20_party_token,
                state                  = excluded.state,
                updated_at             = datetime('now')
        """
        params = (channel_id, campaign_name, claudmaster_session_id, dm20_party_token, state)

        async def _do(conn: aiosqlite.Connection) -> dict[str, Any]:
            await conn.execute(sql, params)
            cursor = await conn.execute(
                "SELECT * FROM channel_sessions WHERE channel_id = ?", (channel_id,)
            )
            row = await cursor.fetchone()
            assert row is not None
            return dict(row)

        row_dict = await self._writer_queue.submit(_do)
        # Parse timestamps from the dict returned inside the transaction
        for col in ("created_at", "updated_at"):
            v = row_dict.get(col)
            if isinstance(v, str):
                row_dict[col] = datetime.fromisoformat(v)
        model = ChannelSession(**row_dict)
        self._logger.debug("upsert_ok", channel_id=channel_id, state=str(state))
        return model

    async def set_state(self, channel_id: str, state: ChannelState) -> ChannelSession:
        """Update the state of a channel session.

        Raises:
            KeyError: If no row with the given channel_id exists.
        """
        sql = """
            UPDATE channel_sessions
               SET state = ?, updated_at = datetime('now')
             WHERE channel_id = ?
        """

        async def _do(conn: aiosqlite.Connection) -> dict[str, Any] | None:
            await conn.execute(sql, (state, channel_id))
            cursor = await conn.execute(
                "SELECT * FROM channel_sessions WHERE channel_id = ?", (channel_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

        row_dict = await self._writer_queue.submit(_do)
        if row_dict is None:
            raise KeyError(f"No channel_sessions row with channel_id={channel_id!r}")

        for col in ("created_at", "updated_at"):
            v = row_dict.get(col)
            if isinstance(v, str):
                row_dict[col] = datetime.fromisoformat(v)
        model = ChannelSession(**row_dict)
        self._logger.debug("set_state_ok", channel_id=channel_id, state=str(state))
        return model

    async def delete(self, channel_id: str) -> None:
        """Delete a channel session (cascades to persistent_views and riposte_timers)."""

        async def _do(conn: aiosqlite.Connection) -> None:
            await conn.execute(
                "DELETE FROM channel_sessions WHERE channel_id = ?", (channel_id,)
            )

        await self._writer_queue.submit(_do)
        self._logger.debug("delete_ok", channel_id=channel_id)

    # ── Reads (lock-free via open_connection) ─────────────────────────────────

    async def get(self, channel_id: str) -> ChannelSession | None:
        """Return the ChannelSession for the given channel_id, or None if absent."""
        async with open_connection(self._db_path) as conn:
            async with conn.execute(
                "SELECT * FROM channel_sessions WHERE channel_id = ?", (channel_id,)
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_model(row)

    async def list_active(self) -> list[ChannelSession]:
        """Return all sessions not in PAUSED state, ordered by updated_at DESC."""
        async with open_connection(self._db_path) as conn:
            async with conn.execute(
                "SELECT * FROM channel_sessions WHERE state != 'PAUSED' ORDER BY updated_at DESC"
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_model(r) for r in rows]
