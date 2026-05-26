"""MonsterMemoryRepo — opt-in persistence for MonsterMemory snapshots (Phase 21 / MEM-03).

Survives bot restart when ``MONSTER_MEMORY_PERSIST=true``. Mirrors Phase 17's
``CharacterCacheRepo`` pattern:

- Standalone aiosqlite WAL at ``~/.eldritch/monster_memory.sqlite`` (D-160).
  Separate DB from Phase 17's character_cache and Phase 1's main DB.
- Lazy connection — NOT routed through Phase 1's ``WriterQueue`` (that owns
  the main DB).
- Schema (D-161)::

      CREATE TABLE monster_memory_entries (
          channel_id      TEXT NOT NULL,
          session_id      TEXT NOT NULL,
          monster_id      TEXT NOT NULL,
          snapshot_json   TEXT NOT NULL,
          last_updated_ts INTEGER NOT NULL,
          PRIMARY KEY (channel_id, session_id, monster_id)
      );
      CREATE INDEX idx_monster_memory_session
          ON monster_memory_entries(channel_id, session_id);

- ``snapshot_json`` is the output of ``MonsterMemory.snapshot_dict()`` —
  D-57 meta-knowledge guard is enforced upstream (no HP/AC/exact-damage keys
  in the snapshot dict; the band classification stays at the augmentation
  layer in ``smart_monster_driver._augment_with_memory``).

Import-linter discipline: lives in ``persistence/``; cannot import from
``gameplay/`` (gameplay→persistence is allowed; not the reverse). The repo
operates on plain ``dict`` snapshots — Plan 21-01's
``MonsterMemory.snapshot_dict()`` / ``from_snapshot()`` is the gameplay-side
bridge.

Fail-soft (D-58 / D-165 / L-12): every method swallows ``sqlite3.Error`` and
``aiosqlite.Error`` and returns a safe default. Persistence failures NEVER
crash combat.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite
import structlog

if TYPE_CHECKING:
    from eldritch_dm.config import Settings

log = structlog.get_logger().bind(component="monster_memory_repo")


class MonsterMemoryRepo:
    """Opt-in persistence for MonsterMemory snapshots.

    Construction is cheap — the SQLite connection opens lazily on first use
    (``_ensure_conn()``). Callers MUST ``await aclose()`` on shutdown.

    Args:
        settings: Optional ``Settings`` override. Defaults to ``get_settings()``.
        path: Optional path override — primarily used by tests and the CLI.
            When supplied, wins over ``settings.monster_memory_path``.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        path: str | os.PathLike[str] | None = None,
    ) -> None:
        from eldritch_dm.config import get_settings  # local — keep import light

        self._settings = settings if settings is not None else get_settings()
        if path is not None:
            self._db_path = Path(os.fspath(path))
        else:
            self._db_path = Path(
                os.path.expanduser(self._settings.monster_memory_path)
            )
        self._conn: aiosqlite.Connection | None = None
        self._logger = log

    # ── Connection ───────────────────────────────────────────────────────────

    @property
    def db_path(self) -> Path:
        """The on-disk SQLite path this repo manages."""
        return self._db_path

    async def _ensure_conn(self) -> aiosqlite.Connection:
        """Lazily open the SQLite connection + create the schema."""
        if self._conn is not None:
            return self._conn
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(self._db_path))
        conn.row_factory = aiosqlite.Row
        # WAL pragmas — same as character_cache.
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA busy_timeout = 5000")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monster_memory_entries (
                channel_id      TEXT    NOT NULL,
                session_id      TEXT    NOT NULL,
                monster_id      TEXT    NOT NULL,
                snapshot_json   TEXT    NOT NULL,
                last_updated_ts INTEGER NOT NULL,
                PRIMARY KEY (channel_id, session_id, monster_id)
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_monster_memory_session "
            "ON monster_memory_entries(channel_id, session_id)"
        )
        await conn.commit()
        self._conn = conn
        self._logger.debug("monster_memory_repo_opened", path=str(self._db_path))
        return conn

    async def aclose(self) -> None:
        """Close the SQLite connection. Idempotent."""
        if self._conn is None:
            return
        try:
            await self._conn.close()
        except Exception:  # noqa: BLE001 — fail-soft
            pass
        self._conn = None

    # ── Public API (Plan 21-02 / L-12) ───────────────────────────────────────

    async def upsert(
        self,
        channel_id: str,
        session_id: str,
        monster_id: str,
        snapshot: dict[str, Any],
    ) -> None:
        """Insert-or-update a snapshot for the given monster.

        Fail-soft: any sqlite error is logged + swallowed. Combat never crashes.
        """
        try:
            conn = await self._ensure_conn()
            payload = json.dumps(snapshot, sort_keys=True, default=str)
            ts = int(time.time())
            await conn.execute(
                """
                INSERT INTO monster_memory_entries
                    (channel_id, session_id, monster_id, snapshot_json, last_updated_ts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(channel_id, session_id, monster_id)
                DO UPDATE SET
                    snapshot_json   = excluded.snapshot_json,
                    last_updated_ts = excluded.last_updated_ts
                """,
                (channel_id, session_id, monster_id, payload, ts),
            )
            await conn.commit()
        except Exception as exc:  # noqa: BLE001 — fail-soft per D-165
            self._logger.warning(
                "monster_memory_repo_upsert_failed",
                channel_id=channel_id,
                session_id=session_id,
                monster_id=monster_id,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )

    async def load(
        self,
        channel_id: str,
        session_id: str,
        monster_id: str,
    ) -> dict[str, Any] | None:
        """Load a snapshot. Returns None if missing or on any error."""
        try:
            conn = await self._ensure_conn()
            cur = await conn.execute(
                "SELECT snapshot_json FROM monster_memory_entries "
                "WHERE channel_id = ? AND session_id = ? AND monster_id = ?",
                (channel_id, session_id, monster_id),
            )
            row = await cur.fetchone()
            await cur.close()
            if row is None:
                return None
            payload = row["snapshot_json"]
            return json.loads(payload)
        except Exception as exc:  # noqa: BLE001 — fail-soft per D-165
            self._logger.warning(
                "monster_memory_repo_load_failed",
                channel_id=channel_id,
                session_id=session_id,
                monster_id=monster_id,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return None

    async def load_all_for_session(
        self,
        channel_id: str,
        session_id: str,
    ) -> dict[str, dict[str, Any]]:
        """Load every monster's snapshot for one session.

        Returns ``{monster_id: snapshot_dict}``. Returns ``{}`` on any error.
        """
        try:
            conn = await self._ensure_conn()
            cur = await conn.execute(
                "SELECT monster_id, snapshot_json FROM monster_memory_entries "
                "WHERE channel_id = ? AND session_id = ?",
                (channel_id, session_id),
            )
            rows = await cur.fetchall()
            await cur.close()
            out: dict[str, dict[str, Any]] = {}
            for r in rows:
                try:
                    out[r["monster_id"]] = json.loads(r["snapshot_json"])
                except Exception as exc:  # noqa: BLE001 — per-row fail-soft
                    self._logger.warning(
                        "monster_memory_repo_load_row_decode_failed",
                        monster_id=r["monster_id"],
                        error_type=type(exc).__name__,
                    )
            return out
        except Exception as exc:  # noqa: BLE001 — fail-soft per D-165
            self._logger.warning(
                "monster_memory_repo_load_all_failed",
                channel_id=channel_id,
                session_id=session_id,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return {}

    async def purge_session(
        self,
        channel_id: str,
        session_id: str,
    ) -> int:
        """Delete every monster's snapshot for one session.

        Returns the count of rows deleted (best-effort; 0 on error).
        """
        try:
            conn = await self._ensure_conn()
            cur = await conn.execute(
                "DELETE FROM monster_memory_entries "
                "WHERE channel_id = ? AND session_id = ?",
                (channel_id, session_id),
            )
            count = cur.rowcount
            await cur.close()
            await conn.commit()
            return int(count) if count is not None and count >= 0 else 0
        except Exception as exc:  # noqa: BLE001 — fail-soft per D-165
            self._logger.warning(
                "monster_memory_repo_purge_failed",
                channel_id=channel_id,
                session_id=session_id,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return 0
