"""eldritch-dm-backfill-pc-classes — v1.0 → v1.1 upgrade CLI (Phase 9 / TD-3).

Populates the local ``pc_classes`` SQLite table from an operator's existing
dm20 characters so Phase 5 Riposte eligibility starts firing for legacy PCs.

Design decisions (see .planning/phases/09-pc-classes-backfill/09-CONTEXT.md):
  D-41  CLI registered via [project.scripts]
  D-42  Reuses MCPClient + circuit breaker (no new HTTP code)
  D-43  ``--dry-run`` opens SQLite in ``mode=ro`` (writes driver-impossible)
  D-44  Exit codes: 0=ok, 1=user/dm20-unreachable, 2=partial, 3=fatal (db lock)
  D-45  Idempotent by default; ``--force`` re-processes already-populated rows
  D-46  Structured logging via structlog
  D-47  Lives under src/eldritch_dm/tools/ (new package; no bot coupling)
  D-48  ``$DM20_MCP_URL`` env override; fallback to OMLX_ENDPOINT then 8765

Scaffold for T-09-01-01 — argparse + console-script entry only. The fetch
loop (T-09-01-02) and SQLite write path (T-09-01-03) land in later commits.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from typing import Any

import aiosqlite
from pydantic import BaseModel, ConfigDict

from eldritch_dm.gameplay.normalize import normalize
from eldritch_dm.logging import get_logger
from eldritch_dm.mcp.client import MCPClient
from eldritch_dm.mcp.errors import (
    MCPCircuitOpen,
    MCPNetworkError,
    MCPTimeoutError,
    MCPToolError,
)
from eldritch_dm.persistence.pc_classes_repo import PCClassesRepo

log = get_logger(__name__)

# ── Exit codes (D-44) ────────────────────────────────────────────────────────
EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_PARTIAL = 2
EXIT_FATAL = 3

# ── Defaults ─────────────────────────────────────────────────────────────────
_DEFAULT_DM20_URL = "http://localhost:8765"


# ── DM20 URL resolution (D-48 + C-5) ─────────────────────────────────────────


def resolve_dm20_url(cli_value: str | None) -> str:
    """Return the dm20 base URL.

    Order (highest precedence first):
      1. ``--dm20-url`` CLI value (if non-empty)
      2. ``$DM20_MCP_URL`` environment variable
      3. ``$OMLX_ENDPOINT`` with a trailing ``/v1`` stripped (matches bot)
      4. ``http://localhost:8765``
    """
    if cli_value:
        return cli_value.rstrip("/")
    env_dm20 = os.environ.get("DM20_MCP_URL")
    if env_dm20:
        return env_dm20.rstrip("/")
    env_omlx = os.environ.get("OMLX_ENDPOINT")
    if env_omlx:
        base = env_omlx.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return base
    return _DEFAULT_DM20_URL


def _default_db_path() -> str:
    """Defer Settings() construction so tests can monkeypatch env vars."""
    try:
        from eldritch_dm.config import Settings

        return Settings().eldritch_db_path
    except Exception:  # pragma: no cover — fall back if env is half-set
        return "./eldritch.sqlite3"


# ── Models (T-09-01-02) ──────────────────────────────────────────────────────


class BackfillRow(BaseModel):
    """One (channel_id, character_id) row pending insertion into pc_classes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel_id: str
    character_id: str
    class_name: str
    subclass: str  # always "" in v1.1 (dm20 schema omits subclass — C-1)


class ApplyReport(BaseModel):
    """Outcome of an apply_rows() invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inserted: int = 0
    updated: int = 0
    skipped_existing: int = 0
    would_insert: int = 0
    would_skip: int = 0
    would_update: int = 0
    errors: list[str] = []


# ── Fetch helpers (T-09-01-02) ───────────────────────────────────────────────


async def _list_channel_sessions_readonly(db_path: str) -> list[tuple[str, str]]:
    """Read (channel_id, campaign_name) tuples from channel_sessions, read-only.

    Always opens with ``mode=ro`` URI so this stage is safe regardless of
    --dry-run.
    """
    uri = f"file:{db_path}?mode=ro"
    async with aiosqlite.connect(uri, uri=True) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT channel_id, campaign_name FROM channel_sessions"
        )
        rows = await cur.fetchall()
    return [(r["channel_id"], r["campaign_name"]) for r in rows]


def _extract_characters(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """dm20 wraps list responses inconsistently; accept either shape."""
    if isinstance(payload, dict):
        chars = payload.get("characters")
        if isinstance(chars, list):
            return chars
        result = payload.get("result")
        if isinstance(result, dict):
            chars = result.get("characters")
            if isinstance(chars, list):
                return chars
    return []


async def collect_rows(
    *,
    db_path: str,
    dm20_url: str,
    client: MCPClient | None = None,
) -> tuple[list[BackfillRow], list[tuple[str, str]]]:
    """Walk channel_sessions, ask dm20 for characters, build BackfillRows.

    Returns ``(rows, failures)`` where each failure is
    ``(channel_id, error_message)``. The function never raises on dm20
    errors — they're bucketed into ``failures`` so main() can compute the
    correct exit code (D-44: all-fail → 1, some-fail → 2).

    Args:
        db_path: SQLite database path (read-only access only here).
        dm20_url: dm20 MCP base URL (used if ``client`` is None).
        client: Optional pre-built MCPClient. When supplied, the caller owns
            its lifecycle (used by tests that share a respx-mocked client).
            When None, this function creates and closes a client internally.
    """
    sessions = await _list_channel_sessions_readonly(db_path)
    if not sessions:
        return [], []

    owns_client = client is None
    if client is None:
        client = MCPClient(dm20_url)

    rows: list[BackfillRow] = []
    failures: list[tuple[str, str]] = []
    try:
        for channel_id, campaign_name in sessions:
            bound = log.bind(channel_id=channel_id, campaign_name=campaign_name)
            try:
                payload = await client.call(
                    "dm20__list_characters", campaign_name=campaign_name
                )
            except (
                MCPCircuitOpen,
                MCPTimeoutError,
                MCPNetworkError,
                MCPToolError,
            ) as exc:
                bound.warning("backfill.dm20_error", error=str(exc))
                failures.append((channel_id, str(exc)))
                continue

            characters = _extract_characters(payload)
            for char in characters:
                character_id = str(char.get("character_id") or char.get("id") or "")
                class_name_raw = (
                    char.get("character_class") or char.get("class") or ""
                )
                if not character_id or not class_name_raw:
                    bound.warning(
                        "backfill.skipping_malformed_char",
                        character_id=character_id,
                        class_name_raw=class_name_raw,
                    )
                    continue
                # C-1: dm20 schema does not expose subclass — best-effort.
                bound.warning(
                    "backfill.subclass_unknown",
                    character_id=character_id,
                    class_name=class_name_raw,
                )
                rows.append(
                    BackfillRow(
                        channel_id=channel_id,
                        character_id=character_id,
                        class_name=normalize(class_name_raw),
                        subclass="",
                    )
                )
    finally:
        if owns_client:
            await client.aclose()

    return rows, failures


def build_parser() -> argparse.ArgumentParser:
    """Return the argparse parser used by main().

    Exposed as a separate function so tests can introspect the parser
    without invoking the full CLI.
    """
    parser = argparse.ArgumentParser(
        prog="eldritch-dm-backfill-pc-classes",
        description=(
            "Populate the local pc_classes table from existing dm20 "
            "characters. Run once after upgrading v1.0 → v1.1 to close "
            "TD-3 (silent no-Riposte-fires gap)."
        ),
        epilog=(
            "Exit codes: 0=success, 1=dm20 unreachable / bad args, "
            "2=partial (some channels failed), 3=fatal (database is locked). "
            "Subclass is left empty — dm20 omits subclass; operators must "
            "hand-edit pc_classes for Battle Master Riposte. See INSTALL.md."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Open SQLite read-only (mode=ro URI); report what WOULD change "
            "and exit without writing. Driver-level write prohibition."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Re-process already-populated rows (default behavior skips "
            "characters already in pc_classes). Idempotent without --force."
        ),
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=(
            "Path to the eldritch SQLite database. Defaults to "
            "Settings().eldritch_db_path (./eldritch.sqlite3)."
        ),
    )
    parser.add_argument(
        "--dm20-url",
        default=None,
        help=(
            "Base URL of the dm20 MCP server. Falls back to $DM20_MCP_URL, "
            "$OMLX_ENDPOINT (minus /v1), then http://localhost:8765."
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Emit per-character structlog DEBUG events.",
    )
    return parser


# ── Apply (T-09-01-03) ───────────────────────────────────────────────────────


async def _apply_rows_dry_run(
    rows: list[BackfillRow], *, db_path: str, force: bool
) -> ApplyReport:
    """Dry-run path: open SQLite read-only, count what WOULD happen.

    D-43 / C-4: ``mode=ro`` URI makes writes driver-impossible. We never
    construct PCClassesRepo here.
    """
    uri = f"file:{db_path}?mode=ro"
    would_insert = 0
    would_skip = 0
    would_update = 0
    async with aiosqlite.connect(uri, uri=True) as conn:
        conn.row_factory = aiosqlite.Row
        for row in rows:
            cur = await conn.execute(
                "SELECT 1 FROM pc_classes "
                "WHERE channel_id = ? AND character_id = ?",
                (row.channel_id, row.character_id),
            )
            existing = await cur.fetchone()
            if existing is None:
                would_insert += 1
            elif force:
                would_update += 1
            else:
                would_skip += 1
    return ApplyReport(
        would_insert=would_insert,
        would_skip=would_skip,
        would_update=would_update,
    )


async def _apply_rows_real(
    rows: list[BackfillRow], *, db_path: str, force: bool
) -> ApplyReport:
    """Real write path. Idempotency gated at the CLI (C-3) — repo SQL unchanged."""
    repo = PCClassesRepo(db_path)
    inserted = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    for row in rows:
        bound = log.bind(
            channel_id=row.channel_id, character_id=row.character_id
        )
        try:
            existing = await repo.get(row.channel_id, row.character_id)
            if existing is not None and not force:
                skipped += 1
                bound.debug("backfill.skip_existing")
                continue
            await repo.upsert(
                channel_id=row.channel_id,
                character_id=row.character_id,
                class_name=row.class_name,
                subclass=row.subclass,
            )
            if existing is None:
                inserted += 1
            else:
                updated += 1
        except sqlite3.OperationalError as exc:
            # C-2: "database is locked" surfaces as EXIT_FATAL upstream.
            if "locked" in str(exc).lower():
                raise
            errors.append(f"{row.channel_id}:{row.character_id}: {exc}")
            bound.error("backfill.sqlite_error", error=str(exc))
    return ApplyReport(
        inserted=inserted,
        updated=updated,
        skipped_existing=skipped,
        errors=errors,
    )


async def apply_rows(
    rows: list[BackfillRow],
    *,
    db_path: str,
    dry_run: bool,
    force: bool,
) -> ApplyReport:
    """Apply rows to pc_classes (or simulate, under --dry-run).

    Dry-run path NEVER constructs PCClassesRepo (D-43 / C-4): it opens
    aiosqlite with ``mode=ro`` URI and emits would_* counters.

    Real path uses PCClassesRepo with a CLI-level idempotency gate
    (C-3): pre-check via ``repo.get`` and skip if non-None unless ``force``
    is set, in which case ``repo.upsert`` re-applies (DO UPDATE).
    """
    if dry_run:
        return await _apply_rows_dry_run(rows, db_path=db_path, force=force)
    return await _apply_rows_real(rows, db_path=db_path, force=force)


# ── Summary printer ──────────────────────────────────────────────────────────


def _print_summary(
    *,
    args: argparse.Namespace,
    dm20_url: str,
    db_path: str,
    rows: list[BackfillRow],
    failures: list[tuple[str, str]],
    report: ApplyReport,
) -> None:
    """Write a plain-text summary table to stdout."""
    print("=" * 60)
    print("eldritch-dm-backfill-pc-classes — summary")
    print("=" * 60)
    print(f"  db_path        : {db_path}")
    print(f"  dm20_url       : {dm20_url}")
    print(f"  mode           : {'DRY-RUN (read-only)' if args.dry_run else 'WRITE'}")
    print(f"  force          : {args.force}")
    print(f"  rows discovered: {len(rows)}")
    print(f"  dm20 failures  : {len(failures)}")
    if args.dry_run:
        print(f"  would_insert   : {report.would_insert}")
        print(f"  would_skip     : {report.would_skip}")
        print(f"  would_update   : {report.would_update}")
    else:
        print(f"  inserted       : {report.inserted}")
        print(f"  updated        : {report.updated}")
        print(f"  skipped        : {report.skipped_existing}")
        if report.errors:
            print(f"  errors         : {len(report.errors)}")
            for line in report.errors:
                print(f"    - {line}")
    print("=" * 60)


# ── Entry point ──────────────────────────────────────────────────────────────


async def _run(args: argparse.Namespace) -> int:
    db_path = args.db_path or _default_db_path()
    dm20_url = resolve_dm20_url(args.dm20_url)
    log.info(
        "backfill.start",
        db_path=db_path,
        dm20_url=dm20_url,
        dry_run=args.dry_run,
        force=args.force,
    )

    try:
        rows, failures = await collect_rows(db_path=db_path, dm20_url=dm20_url)
    except sqlite3.OperationalError as exc:
        log.error("backfill.db_open_failed", error=str(exc))
        print(f"ERROR: cannot open {db_path}: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    all_failed = bool(failures) and not rows
    partial = bool(failures) and bool(rows)

    if not rows and not failures:
        print(
            "No channel_sessions / characters found — nothing to backfill.",
            file=sys.stderr,
        )
        _print_summary(
            args=args,
            dm20_url=dm20_url,
            db_path=db_path,
            rows=[],
            failures=[],
            report=ApplyReport(),
        )
        return EXIT_OK

    try:
        report = await apply_rows(
            rows, db_path=db_path, dry_run=args.dry_run, force=args.force
        )
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            log.error("backfill.db_locked", error=str(exc))
            print(
                "FATAL: database is locked. Stop the bot before running "
                "the backfill tool.",
                file=sys.stderr,
            )
            return EXIT_FATAL
        log.error("backfill.db_error", error=str(exc))
        print(f"ERROR: SQLite error: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    _print_summary(
        args=args,
        dm20_url=dm20_url,
        db_path=db_path,
        rows=rows,
        failures=failures,
        report=report,
    )

    if all_failed:
        return EXIT_USER_ERROR
    if partial:
        return EXIT_PARTIAL
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
