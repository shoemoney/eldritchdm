"""
EldritchDM SQLite schema bootstrap.

Applies database/schema.sql to the local SQLite DB idempotently.
Every table uses CREATE TABLE IF NOT EXISTS; every index uses CREATE INDEX IF NOT EXISTS.
Running bootstrap() twice is safe and produces no error.

Usage:
    python -m eldritch_dm.persistence.bootstrap

Or from code:
    from eldritch_dm.persistence.bootstrap import bootstrap
    await bootstrap()

TODO: For wheel installs, schema.sql should be bundled via importlib.resources.
      For now (editable install), the package-relative path works correctly.
      Add importlib.resources fallback when packaging for distribution.

Security (T-01-01, T-01-05): schema.sql is treated as trusted (in-repo,
code-reviewed). Its sha256 is logged at every bootstrap run so tampering
is observable in audit logs.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import aiosqlite

from eldritch_dm.config import get_settings
from eldritch_dm.logging import configure_logging, get_logger

log = get_logger(__name__)

# Locate schema.sql relative to this file:
#   src/eldritch_dm/persistence/bootstrap.py  -> parents[3] = project root
#   <project_root>/database/schema.sql
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "database" / "schema.sql"


async def bootstrap(db_path: str | None = None) -> Path:
    """Create (or verify) the EldritchDM SQLite schema at db_path.

    Idempotent: safe to call multiple times.  Uses IF NOT EXISTS DDL so no
    existing data is modified.

    Args:
        db_path: Path to the SQLite file.  Defaults to get_settings().eldritch_db_path.

    Returns:
        The resolved Path of the database file.

    Raises:
        FileNotFoundError: If SCHEMA_PATH does not exist.
        aiosqlite.Error: If the schema cannot be applied.
    """
    if db_path is None:
        db_path = get_settings().eldritch_db_path

    # Use str/Path operations synchronously here — this is a startup task,
    # not a hot path. ASYNC240 does not apply to setup code.
    # (ruff ASYNC240 is about trio/anyio paths in long-running async code.)
    db = Path(db_path).resolve()  # noqa: ASYNC240
    db_dir = db.parent
    db_dir_str = str(db_dir)

    # Create parent directory synchronously (startup-time, not a hot path)
    import os  # noqa: PLC0415

    os.makedirs(db_dir_str, exist_ok=True)

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    schema_sha256 = hashlib.sha256(schema_sql.encode()).hexdigest()

    log.info(
        "bootstrap_start",
        db_path=str(db),
        schema_path=str(SCHEMA_PATH),
        schema_sha256=schema_sha256,
    )

    conn: aiosqlite.Connection = await aiosqlite.connect(str(db))
    try:
        # Apply pragmas first (foreign_keys, WAL, etc.)
        from eldritch_dm.persistence.connection import apply_pragmas  # noqa: PLC0415

        await apply_pragmas(conn)

        # executescript runs the DDL statements idempotently
        await conn.executescript(schema_sql)
        await conn.commit()

        # Phase 5 Plan 01 additive migration: add `consumed_in_round INTEGER` to
        # riposte_timers if missing. Guarded by try/except so re-running bootstrap
        # on an already-migrated DB is a no-op (RESEARCH Q1 shim for reaction
        # budget — dm20 has no native reaction tracking).
        try:
            await conn.execute(
                "ALTER TABLE riposte_timers ADD COLUMN consumed_in_round INTEGER"
            )
            await conn.commit()
            log.info("riposte_timers_migrated_consumed_in_round")
        except aiosqlite.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                pass  # already migrated; do NOT log
            else:
                raise

        # Report which tables were created/verified
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]

        log.info(
            "bootstrap_complete",
            db_path=str(db),
            tables_present=tables,
            schema_sha256=schema_sha256,
        )
    finally:
        await conn.close()

    return db


def main() -> None:
    """Entry point for `python -m eldritch_dm.persistence.bootstrap`."""
    configure_logging(level="INFO", fmt="console")
    db_path = asyncio.run(bootstrap())
    print(f"Bootstrap complete: {db_path}")  # noqa: T201


if __name__ == "__main__":
    main()
