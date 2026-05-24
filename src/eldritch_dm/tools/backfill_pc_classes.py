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
import os
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


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Scaffold-only in T-09-01-01.

    T-09-01-02 adds the dm20 fetch loop; T-09-01-03 adds the SQLite write
    path. For now, parse args and emit a placeholder message.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = args.db_path or _default_db_path()
    dm20_url = resolve_dm20_url(args.dm20_url)
    log.info(
        "backfill.scaffold_invoked",
        db_path=db_path,
        dm20_url=dm20_url,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(
        "eldritch-dm-backfill-pc-classes scaffold — fetch loop and "
        "writes land in T-09-01-02 / T-09-01-03",
        file=sys.stderr,
    )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
