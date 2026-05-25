"""eldritch-dm-cache-disable — runtime cache-toggle CLI (Phase 18 / NARRCACHE-03).

Operator emergency-disable / re-enable of the narration cache for the
CURRENT bot process. State resets to "enabled" on bot restart —
orchestration that survives restart belongs in ``.env`` (set
``NARRCACHE_ENABLED=false``).

v1.5 ships a single scope: ``--narration``. Future versions can add
``--mcp`` (Phase 16) or ``--characters`` (Phase 17) without a breaking
change to the CLI shape.

Exit codes:
  0 = ok
  1 = user error (bad / missing scope)
"""

from __future__ import annotations

import argparse
import sys

from eldritch_dm.logging import get_logger
from eldritch_dm.observability.narrcache_runtime import get_narrcache_override

log = get_logger(__name__)

EXIT_OK = 0
EXIT_USER_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eldritch-dm-cache-disable",
        description=(
            "Flip a runtime override on a local cache without restarting the "
            "bot. Process-local — state resets to 'enabled' on restart. For "
            "persistent disable, set the corresponding env var (e.g. "
            "NARRCACHE_ENABLED=false) in .env."
        ),
    )
    scope = parser.add_argument_group("scope (exactly one required)")
    scope.add_argument(
        "--narration",
        action="store_true",
        help="Target the Phase 18 narration cache.",
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Re-enable the cache (default action is disable).",
    )
    parser.add_argument(
        "--reason",
        default=None,
        help="Optional free-form reason logged with the override change.",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    if not args.narration:
        print(
            "ERROR: must specify a scope. Use --narration.",
            file=sys.stderr,
        )
        return EXIT_USER_ERROR

    override = get_narrcache_override()
    if args.enable:
        override.enable()
        snap = override.snapshot()
        print(f"narration cache: ENABLED (was {'disabled' if not snap.disabled else 'enabled'})")
        log.info("cache_disable.narration_enabled")
    else:
        override.disable(reason=args.reason)
        snap = override.snapshot()
        print("narration cache: DISABLED" + (f" (reason: {snap.reason})" if snap.reason else ""))
        log.info("cache_disable.narration_disabled", reason=args.reason)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return _run(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
