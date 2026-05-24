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
import sys

from eldritch_dm.logging import get_logger

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
    import os

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
