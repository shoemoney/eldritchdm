"""eldritch-dm-cache-clear — operator cache-purge CLI (Phase 17 / CHARCACHE-03).

Mirrors the Phase 9 ``eldritch-dm-backfill-pc-classes`` shape (argparse + exit
codes + structured logging). v1.5 ships with a single scope: ``--characters``.
Future versions will add ``--mcp`` (Phase 16's MCPCache invalidation).

Design decisions:
  D-124  CLI registered via ``[project.scripts]``
  D-43-equiv  ``--dry-run`` opens SQLite read-only via ``file:...?mode=ro``

Exit codes:
  0 = ok
  1 = user error (bad args / missing cache file)
  3 = fatal (DB locked / IO error)
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

import aiosqlite

from eldritch_dm.logging import get_logger

log = get_logger(__name__)

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_FATAL = 3


def _default_cache_path() -> str:
    """Defer Settings() so tests can monkeypatch env."""
    try:
        from eldritch_dm.config import Settings

        return Settings().charcache_path
    except Exception:  # pragma: no cover
        return "~/.eldritch/character_cache.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eldritch-dm-cache-clear",
        description=(
            "Purge entries from local eldritch cache databases. v1.5 supports "
            "the character cache (Phase 17 CHARCACHE-03)."
        ),
        epilog=(
            "Exit codes: 0=success, 1=user error (missing file / bad args), "
            "3=fatal (database is locked — stop the bot first)."
        ),
    )
    scope = parser.add_argument_group("scope (exactly one required)")
    scope.add_argument(
        "--characters",
        action="store_true",
        help="Purge entries from the Phase 17 character snapshot cache.",
    )
    parser.add_argument(
        "--character-id",
        default=None,
        help=(
            "When used with --characters, purge only this character_id. "
            "Without it, purges all rows."
        ),
    )
    parser.add_argument(
        "--cache-path",
        default=None,
        help=(
            "Override the cache SQLite path. Default = "
            "Settings().charcache_path (~/.eldritch/character_cache.sqlite)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Open SQLite read-only (mode=ro URI); report what WOULD be "
            "removed and exit 0 without writing."
        ),
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose structlog output.")
    return parser


# ── Action helpers ───────────────────────────────────────────────────────────


async def _count_chars(
    db_path: str,
    *,
    character_id: str | None,
    read_only: bool,
) -> int:
    """Return the row count that matches the (optional) character_id filter.

    When ``read_only`` is True, opens via ``file:...?mode=ro`` URI so writes
    are driver-impossible (dry-run safety).
    """
    if read_only:
        dsn = f"file:{db_path}?mode=ro"
        conn = await aiosqlite.connect(dsn, uri=True)
    else:
        conn = await aiosqlite.connect(db_path)
    try:
        if character_id is None:
            cur = await conn.execute("SELECT COUNT(*) FROM character_cache_entries")
        else:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM character_cache_entries WHERE character_id = ?",
                (character_id,),
            )
        row = await cur.fetchone()
        await cur.close()
        return int(row[0]) if row else 0
    finally:
        await conn.close()


async def _delete_chars(db_path: str, *, character_id: str | None) -> int:
    """Run the DELETE and return the affected row count."""
    conn = await aiosqlite.connect(db_path)
    try:
        if character_id is None:
            cur = await conn.execute("DELETE FROM character_cache_entries")
        else:
            cur = await conn.execute(
                "DELETE FROM character_cache_entries WHERE character_id = ?",
                (character_id,),
            )
        await conn.commit()
        return cur.rowcount if cur.rowcount > 0 else 0
    finally:
        await conn.close()


# ── Entry point ──────────────────────────────────────────────────────────────


async def _run(args: argparse.Namespace) -> int:
    if not args.characters:
        print(
            "ERROR: must specify a scope. Use --characters.",
            file=sys.stderr,
        )
        return EXIT_USER_ERROR

    raw_path = args.cache_path or _default_cache_path()
    db_path = os.path.expanduser(raw_path)
    log.info(
        "cache_clear.start",
        db_path=db_path,
        character_id=args.character_id,
        dry_run=args.dry_run,
    )

    if not Path(db_path).exists():
        print(f"ERROR: cache file not found: {db_path}", file=sys.stderr)
        return EXIT_USER_ERROR

    try:
        if args.dry_run:
            n = await _count_chars(db_path, character_id=args.character_id, read_only=True)
            print(
                f"DRY-RUN: would remove {n} row(s) from {db_path}"
                + (f" matching character_id={args.character_id}" if args.character_id else "")
            )
            return EXIT_OK

        removed = await _delete_chars(db_path, character_id=args.character_id)
        print(
            f"Removed {removed} row(s) from {db_path}"
            + (f" matching character_id={args.character_id}" if args.character_id else "")
        )
        return EXIT_OK
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            log.error("cache_clear.db_locked", error=str(exc))
            print(
                "FATAL: database is locked. Stop the bot before running this tool.",
                file=sys.stderr,
            )
            return EXIT_FATAL
        log.error("cache_clear.db_error", error=str(exc))
        print(f"ERROR: SQLite error: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
