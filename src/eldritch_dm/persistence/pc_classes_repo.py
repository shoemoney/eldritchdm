"""
PCClassesRepo — per-character class + subclass storage for Riposte eligibility.

dm20's `get_character` text response OMITS subclass (Phase 5 RESEARCH Q2). We
persist (class_name, subclass) at character-ingest time so the Phase 5
eligibility check can decide whether a PC is a Battle Master Fighter (RAW
Riposte) without parsing inconsistent dm20 text.

Storage shape (database/schema.sql):
    pc_classes(channel_id TEXT, character_id TEXT,
               class_name TEXT, subclass TEXT NOT NULL DEFAULT '',
               PRIMARY KEY(channel_id, character_id),
               FOREIGN KEY(channel_id) REFERENCES channel_sessions(channel_id)
               ON DELETE CASCADE)

Normalization: `class_name` and `subclass` are stored lowercased and
whitespace-collapsed (e.g. "Battle  Master" → "battle master") via a pydantic
field_validator on PCClassInfo. The repo accepts arbitrary casing from
ingest-time callers and normalizes on the way in.

Repo construction follows the Phase 4 CombatConditionsRepo pattern:
  - `_connect()` returns an unstarted aiosqlite.Connection.
  - Callers wrap with `async with self._connect() as conn:`.
  - `_configure(conn)` applies row_factory + pragmas.
This avoids the "threads can only be started once" RuntimeError that bit Phase 4
Plan 03 (see combat_conditions_repo.py module docstring for context).

Phase 5 Plan 01.
"""

from __future__ import annotations

import aiosqlite
from pydantic import BaseModel, ConfigDict, field_validator

from eldritch_dm.gameplay.normalize import normalize
from eldritch_dm.logging import get_logger
from eldritch_dm.persistence.connection import apply_pragmas

log = get_logger(__name__)


# ── Model ─────────────────────────────────────────────────────────────────────


class PCClassInfo(BaseModel):
    """Class + subclass for a single PC, normalized.

    Both fields are lowercased + whitespace-collapsed at construction so
    eligibility comparisons against ``ELIGIBLE_CLASS_SUBCLASSES`` (which is also
    lowercase) are stable.

    Frozen so callers can hash / cache safely.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    class_name: str
    subclass: str

    @field_validator("class_name", "subclass", mode="before")
    @classmethod
    def _norm(cls, v: object) -> str:
        if v is None:
            return ""
        return normalize(str(v))


# ── Repo ──────────────────────────────────────────────────────────────────────


class PCClassesRepo:
    """Read/write operations for the pc_classes table.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _connect(self) -> aiosqlite.Connection:
        """Return an unstarted aiosqlite.Connection.

        Callers MUST enter it via ``async with``. Returning an unstarted
        Connection (not awaited) is intentional — the ``async with`` performs
        the single start. See combat_conditions_repo._connect for rationale.
        """
        return aiosqlite.connect(self._db_path)

    async def _configure(self, conn: aiosqlite.Connection) -> None:
        """Apply row_factory + pragmas to a freshly-entered connection."""
        conn.row_factory = aiosqlite.Row
        await apply_pragmas(conn)

    async def upsert(
        self,
        *,
        channel_id: str,
        character_id: str,
        class_name: str,
        subclass: str,
    ) -> None:
        """Insert or update the (channel_id, character_id) row.

        class_name and subclass are normalized (lowercased + whitespace-collapsed)
        before storage. Calling upsert a second time for the same key updates
        the existing row in place — no duplicates.

        Args:
            channel_id: Discord channel snowflake string.
            character_id: dm20 character UUID.
            class_name: Class name; will be lowercased + whitespace-collapsed.
            subclass: Subclass name (empty string allowed for level 1-2 PCs).
        """
        norm_class = normalize(class_name)
        norm_subclass = normalize(subclass)

        sql = """
            INSERT INTO pc_classes (channel_id, character_id, class_name, subclass)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(channel_id, character_id) DO UPDATE SET
                class_name = excluded.class_name,
                subclass   = excluded.subclass
        """
        async with self._connect() as conn:
            await self._configure(conn)
            await conn.execute(
                sql, (channel_id, character_id, norm_class, norm_subclass)
            )
            await conn.commit()
        log.info(
            "pc_classes_upserted",
            channel_id=channel_id,
            character_id=character_id,
            class_name=norm_class,
            subclass=norm_subclass,
        )

    async def get(
        self,
        channel_id: str,
        character_id: str,
    ) -> PCClassInfo | None:
        """Return the PCClassInfo for the given key, or None if missing.

        Args:
            channel_id: Discord channel snowflake string.
            character_id: dm20 character UUID.

        Returns:
            PCClassInfo(class_name, subclass) or None.
        """
        async with self._connect() as conn:
            await self._configure(conn)
            cursor = await conn.execute(
                "SELECT class_name, subclass FROM pc_classes "
                "WHERE channel_id = ? AND character_id = ?",
                (channel_id, character_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return PCClassInfo(
            class_name=row["class_name"], subclass=row["subclass"]
        )
