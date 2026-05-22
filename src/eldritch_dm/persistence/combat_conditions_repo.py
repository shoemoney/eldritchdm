"""
CombatConditionsRepo -- bot-side storage for dm20-shimmed combat conditions.

dm20 has no built-in "dodging" condition (04-RESEARCH.md Q2). We shim it:
  1. Write a row here when a player clicks DodgeButton.
  2. Call dm20__apply_effect(target=actor_id, effect="custom:dodging") to let
     ShoeGPT know the character is dodging (narrative-only in v1).
  3. On the dodger next turn start, clear the row (expires_round check).

v1: mechanical disadvantage on incoming attacks is narrative-only. The combat
embed shows "dodging" in the conditions column, and the narrative context
passed to ShoeGPT includes "X is dodging". We do NOT modify the combat_action
to-hit math because dm20__combat_action has no advantage/disadvantage arg.
Phase 5 will add the mechanical enforcement when dm20 supports it.

Phase 4 Plan 02.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from eldritch_dm.logging import get_logger
from eldritch_dm.persistence.connection import apply_pragmas

log = get_logger(__name__)

# ── Model ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CombatCondition:
    """Row from the combat_conditions table.

    Attributes:
        id: Auto-incremented primary key.
        channel_id: Discord channel snowflake string.
        character_id: dm20 character UUID.
        condition_kind: "dodging" for v1; extensible for future conditions.
        expires_round: Round number at which this condition expires (cleared
                       at the start of the affected character next turn).
        applied_round: Round number when the condition was applied.
        applied_at: UTC timestamp when the row was inserted.
    """

    id: int | None
    channel_id: str
    character_id: str
    condition_kind: str
    expires_round: int
    applied_round: int
    applied_at: datetime


# ── Repo ──────────────────────────────────────────────────────────────────────


class CombatConditionsRepo:
    """Read/write operations for the combat_conditions table.

    Uses aiosqlite directly (no WriterQueue) since combat conditions are
    high-frequency, short-lived rows that need immediate read-back.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        await apply_pragmas(conn)
        return conn

    async def insert(
        self,
        channel_id: str,
        character_id: str,
        condition_kind: str,
        applied_round: int,
        expires_round: int,
    ) -> int:
        """Insert a new combat condition row.

        Idempotent per (channel_id, character_id, condition_kind): if a row
        already exists for this triple, it is replaced (handles re-dodge).

        Args:
            channel_id: Discord channel snowflake string.
            character_id: dm20 character UUID.
            condition_kind: "dodging" etc.
            applied_round: Combat round when condition was applied.
            expires_round: Combat round when condition expires.

        Returns:
            The new row id.
        """
        now = datetime.now(UTC).isoformat()
        async with await self._connect() as conn:
            # Replace existing condition for same (channel, character, kind)
            await conn.execute(
                """
                INSERT INTO combat_conditions
                    (channel_id, character_id, condition_kind,
                     expires_round, applied_round, applied_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (channel_id, character_id, condition_kind,
                 expires_round, applied_round, now),
            )
            # Delete any older row for same triple and insert fresh
            await conn.execute(
                """
                DELETE FROM combat_conditions
                WHERE channel_id = ? AND character_id = ? AND condition_kind = ?
                  AND applied_round < ?
                """,
                (channel_id, character_id, condition_kind, applied_round),
            )
            cursor = await conn.execute(
                """
                INSERT OR REPLACE INTO combat_conditions
                    (channel_id, character_id, condition_kind,
                     expires_round, applied_round, applied_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (channel_id, character_id, condition_kind,
                 expires_round, applied_round, now),
            )
            await conn.commit()
            row_id = cursor.lastrowid
            log.info(
                "combat_condition_inserted",
                channel_id=channel_id,
                character_id=character_id,
                condition_kind=condition_kind,
                applied_round=applied_round,
                expires_round=expires_round,
                row_id=row_id,
            )
            return row_id or 0

    async def get_active_for_character(
        self,
        channel_id: str,
        character_id: str,
        current_round: int,
    ) -> list[CombatCondition]:
        """Return active conditions for a character in the given channel.

        A condition is active if current_round < expires_round.

        Args:
            channel_id: Discord channel snowflake string.
            character_id: dm20 character UUID.
            current_round: Current combat round number.

        Returns:
            List of active CombatCondition rows.
        """
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, channel_id, character_id, condition_kind,
                       expires_round, applied_round, applied_at
                FROM combat_conditions
                WHERE channel_id = ? AND character_id = ? AND expires_round > ?
                ORDER BY applied_at DESC
                """,
                (channel_id, character_id, current_round),
            )
            rows = await cursor.fetchall()
        return [
            CombatCondition(
                id=row["id"],
                channel_id=row["channel_id"],
                character_id=row["character_id"],
                condition_kind=row["condition_kind"],
                expires_round=row["expires_round"],
                applied_round=row["applied_round"],
                applied_at=datetime.fromisoformat(row["applied_at"]),
            )
            for row in rows
        ]

    async def has_condition(
        self,
        channel_id: str,
        character_id: str,
        condition_kind: str,
        current_round: int,
    ) -> bool:
        """Return True if character has an active condition of the given kind.

        Args:
            channel_id: Discord channel snowflake string.
            character_id: dm20 character UUID.
            condition_kind: e.g. "dodging".
            current_round: Current combat round (used to check expiry).

        Returns:
            True if a matching active row exists.
        """
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT 1 FROM combat_conditions
                WHERE channel_id = ? AND character_id = ?
                  AND condition_kind = ? AND expires_round > ?
                LIMIT 1
                """,
                (channel_id, character_id, condition_kind, current_round),
            )
            row = await cursor.fetchone()
        return row is not None

    async def clear_expired(self, channel_id: str, current_round: int) -> int:
        """Delete all expired conditions for a channel.

        Called at the start of each round (or on character turn start).

        Args:
            channel_id: Discord channel snowflake string.
            current_round: Round number; rows with expires_round <= this are deleted.

        Returns:
            Number of rows deleted.
        """
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM combat_conditions
                WHERE channel_id = ? AND expires_round <= ?
                """,
                (channel_id, current_round),
            )
            await conn.commit()
            deleted = cursor.rowcount or 0
        if deleted:
            log.info(
                "combat_conditions_expired_cleared",
                channel_id=channel_id,
                current_round=current_round,
                deleted=deleted,
            )
        return deleted

    async def clear_all_for_channel(self, channel_id: str) -> None:
        """Delete all combat conditions for a channel (combat end cleanup).

        Args:
            channel_id: Discord channel snowflake string.
        """
        async with await self._connect() as conn:
            await conn.execute(
                "DELETE FROM combat_conditions WHERE channel_id = ?",
                (channel_id,),
            )
            await conn.commit()
        log.info("combat_conditions_channel_cleared", channel_id=channel_id)

    def build_conditions_narrative(
        self,
        conditions: list[CombatCondition],
    ) -> str | None:
        """Build a narrative-hint string for active conditions (passed to ShoeGPT).

        v1 narrative-only dodge: "X is dodging" is injected into the LLM context
        so ShoeGPT describes the dodge. No mechanical modification of attack rolls.

        Args:
            conditions: List of active CombatCondition rows for a character.

        Returns:
            Human-readable condition string, or None if no conditions.

        Example::
            "dodging"
        """
        if not conditions:
            return None
        kinds = [c.condition_kind for c in conditions]
        return ", ".join(kinds)

    def build_conditions_list(
        self,
        conditions: list[CombatCondition],
    ) -> list[str]:
        """Build a list of condition kind strings for embed rendering.

        Args:
            conditions: List of active CombatCondition rows.

        Returns:
            List of condition kind strings (e.g. ["dodging"]).
        """
        return [c.condition_kind for c in conditions]


def _row_to_model(row: Any) -> CombatCondition:
    """Convert an aiosqlite Row to a CombatCondition."""
    return CombatCondition(
        id=row["id"],
        channel_id=row["channel_id"],
        character_id=row["character_id"],
        condition_kind=row["condition_kind"],
        expires_round=row["expires_round"],
        applied_round=row["applied_round"],
        applied_at=datetime.fromisoformat(row["applied_at"]),
    )
