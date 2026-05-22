"""
RiposteTimerRepo — CRUD for riposte_timers table.

All writes go through WriterQueue (BEGIN IMMEDIATE).
All reads use lock-free open_connection.
"""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from eldritch_dm.logging import get_logger
from eldritch_dm.persistence.connection import WriterQueue, open_connection
from eldritch_dm.persistence.models import RiposteTimer


def _row_to_model(row: aiosqlite.Row) -> RiposteTimer:
    d = dict(row)
    for col in ("deadline_ts", "created_at"):
        v = d.get(col)
        if isinstance(v, str):
            d[col] = datetime.fromisoformat(v)
    return RiposteTimer(**d)


class RiposteTimerRepo:
    """Repository for riposte_timers table.

    Args:
        db_path: Path to the SQLite database file.
        writer_queue: The shared WriterQueue; all mutating operations use it.
    """

    def __init__(self, db_path: str, writer_queue: WriterQueue) -> None:
        self._db_path = db_path
        self._writer_queue = writer_queue
        self._logger = get_logger(__name__).bind(repo="riposte_timers")

    # ── Writes ────────────────────────────────────────────────────────────────

    async def insert(self, timer: RiposteTimer) -> RiposteTimer:
        """Insert a new RiposteTimer row.

        The DB assigns the AUTOINCREMENT id; returns the model with id populated.
        Includes the Phase 5 `consumed_in_round` column (None on insert).
        """
        sql = """
            INSERT INTO riposte_timers
                (channel_id, character_id, user_id, monster_uuid, weapon_used,
                 message_id, custom_id, deadline_ts, status, consumed_in_round,
                 created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """

        async def _do(conn: aiosqlite.Connection) -> dict:
            cursor = await conn.execute(
                sql,
                (
                    timer.channel_id,
                    timer.character_id,
                    timer.user_id,
                    timer.monster_uuid,
                    timer.weapon_used,
                    timer.message_id,
                    timer.custom_id,
                    timer.deadline_ts.isoformat(),
                    timer.status,
                    timer.consumed_in_round,
                ),
            )
            row_id = cursor.lastrowid
            cursor2 = await conn.execute(
                "SELECT * FROM riposte_timers WHERE id = ?", (row_id,)
            )
            row = await cursor2.fetchone()
            assert row is not None
            return dict(row)

        row_dict = await self._writer_queue.submit(_do)
        for col in ("deadline_ts", "created_at"):
            v = row_dict.get(col)
            if isinstance(v, str):
                row_dict[col] = datetime.fromisoformat(v)
        model = RiposteTimer(**row_dict)
        self._logger.debug("insert_ok", id=model.id, channel_id=timer.channel_id)
        return model

    async def mark_consumed(self, id_: int) -> None:
        """Set status='consumed' for a timer."""
        async def _do(conn: aiosqlite.Connection) -> None:
            await conn.execute(
                "UPDATE riposte_timers SET status = 'consumed' WHERE id = ?", (id_,)
            )

        await self._writer_queue.submit(_do)
        self._logger.debug("mark_consumed_ok", id=id_)

    async def mark_expired(self, id_: int) -> None:
        """Set status='expired' for a timer, conditional on still-pending.

        Phase 5 Plan 02: the SQL is ``WHERE id=? AND status='pending'`` so that
        a sweeper-vs-click race produces a no-op on the loser (correct
        behavior + idempotent). The shared ``SessionLocks`` lock in
        ``RiposteSweeper._expire_row`` and ``handle_riposte_click`` serializes
        the two paths; this conditional UPDATE is the belt-and-suspenders.
        """
        async def _do(conn: aiosqlite.Connection) -> None:
            await conn.execute(
                "UPDATE riposte_timers SET status = 'expired' "
                "WHERE id = ? AND status = 'pending'",
                (id_,),
            )

        await self._writer_queue.submit(_do)
        self._logger.debug("mark_expired_ok", id=id_)

    async def mark_cancelled(self, id_: int) -> None:
        """Set status='cancelled' for a timer.

        Idempotent — does NOT overwrite a row already in 'consumed' state (a
        consumed riposte is final). Calling twice on a pending row is safe.
        """
        async def _do(conn: aiosqlite.Connection) -> None:
            await conn.execute(
                "UPDATE riposte_timers SET status = 'cancelled' "
                "WHERE id = ? AND status != 'consumed'",
                (id_,),
            )

        await self._writer_queue.submit(_do)
        self._logger.debug("mark_cancelled_ok", id=id_)

    async def update_message_ref(
        self,
        id_: int,
        *,
        message_id: str,
        custom_id: str,
        deadline_ts: datetime,
    ) -> None:
        """Atomically backfill message_id, custom_id, and deadline_ts.

        Phase 5 Plan 01 RESEARCH Pitfall 1: callers insert a riposte row BEFORE
        sending the public channel message (we need the row id for custom_id),
        then send the channel message, then call this to write the real
        message_id and recompute the deadline AFTER channel.send returns. This
        keeps the TTL accurate even if Discord's API was slow.
        """
        async def _do(conn: aiosqlite.Connection) -> None:
            await conn.execute(
                "UPDATE riposte_timers SET message_id = ?, custom_id = ?, "
                "deadline_ts = ? WHERE id = ?",
                (message_id, custom_id, deadline_ts.isoformat(), id_),
            )

        await self._writer_queue.submit(_do)
        self._logger.debug("update_message_ref_ok", id=id_, message_id=message_id)

    async def mark_consumed_with_round(self, id_: int, round_n: int) -> None:
        """Set status='consumed' AND consumed_in_round=round_n atomically.

        Phase 5 Plan 01 reaction-budget shim: the round number is the basis for
        ``check_riposte_eligibility``'s "one reaction per round" enforcement.
        """
        async def _do(conn: aiosqlite.Connection) -> None:
            await conn.execute(
                "UPDATE riposte_timers SET status = 'consumed', "
                "consumed_in_round = ? WHERE id = ?",
                (round_n, id_),
            )

        await self._writer_queue.submit(_do)
        self._logger.debug(
            "mark_consumed_with_round_ok", id=id_, round_n=round_n
        )

    # ── Reads ─────────────────────────────────────────────────────────────────

    async def get(self, id_: int) -> RiposteTimer | None:
        """Return the RiposteTimer for the given id, or None."""
        async with open_connection(self._db_path) as conn:
            async with conn.execute(
                "SELECT * FROM riposte_timers WHERE id = ?", (id_,)
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_model(row)

    async def list_pending(self) -> list[RiposteTimer]:
        """Return all timers with status='pending', ordered by deadline_ts ASC."""
        async with open_connection(self._db_path) as conn:
            async with conn.execute(
                "SELECT * FROM riposte_timers WHERE status = 'pending' ORDER BY deadline_ts ASC"
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_model(r) for r in rows]

    async def list_for_character(
        self,
        channel_id: str,
        character_id: str,
    ) -> list[RiposteTimer]:
        """Return ALL timer rows for (channel_id, character_id), ordered by id ASC.

        Includes every status (pending/consumed/expired/cancelled). Used by
        ``check_riposte_eligibility`` to enforce per-round reaction budget
        against the bot-side shim (RESEARCH Q1).
        """
        async with open_connection(self._db_path) as conn:
            async with conn.execute(
                "SELECT * FROM riposte_timers "
                "WHERE channel_id = ? AND character_id = ? "
                "ORDER BY id ASC",
                (channel_id, character_id),
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_model(r) for r in rows]
