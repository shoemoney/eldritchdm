"""
EldritchDM top-level bootstrap & preflight (HOST-03 / Phase 5 Plan 03).

This module is the canonical entrypoint referenced from the README and
docs/CONFIGURATION.md as ``python -m eldritch_dm.bootstrap``. It wraps the
lower-level schema bootstrap in :mod:`eldritch_dm.persistence.bootstrap`
and runs a 3-stage preflight check against the operator's local
infrastructure (oMLX + dm20 + SQLite schema).

Exit codes (per RESEARCH Pattern 5):

* ``0`` (``EXIT_OK``)              — every stage passed
* ``1`` (``EXIT_OMLX_UNREACHABLE``) — oMLX `/v1/models` HTTP call failed
* ``2`` (``EXIT_DM20_NOT_LOADED``) — MCP tools list returned 0 dm20__* entries
* ``3`` (``EXIT_SCHEMA_FAIL``)     — local SQLite schema apply raised

Schema check runs FIRST so that schema failures short-circuit before any
network I/O. Missing OMLX_MODEL is a soft WARNING (not a fatal error)
per RESEARCH A5 — operators may load a non-ShoeGPT model intentionally.

Re-exports ``bootstrap`` from :mod:`eldritch_dm.persistence.bootstrap` so
``from eldritch_dm.bootstrap import bootstrap`` continues to work for any
legacy callers that followed the older README guidance.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import httpx

# Re-export so legacy `from eldritch_dm.bootstrap import bootstrap` works
# (README + docs/CONFIGURATION.md historically reference this path).
from eldritch_dm.persistence.bootstrap import bootstrap

__all__ = [
    "EXIT_DM20_NOT_LOADED",
    "EXIT_OK",
    "EXIT_OMLX_UNREACHABLE",
    "EXIT_SCHEMA_FAIL",
    "bootstrap",
    "main",
    "preflight",
]

# Exit-code constants — also useful for tests and run.py
EXIT_OK = 0
EXIT_OMLX_UNREACHABLE = 1
EXIT_DM20_NOT_LOADED = 2
EXIT_SCHEMA_FAIL = 3


def _eprint(msg: str) -> None:
    """User-friendly stderr line — kept separate from structured logging so
    self-hosters debugging launchd see *something* readable without parsing JSON.
    """
    print(msg, file=sys.stderr)  # noqa: T201


async def preflight() -> int:
    """Run the 3-stage preflight and return an exit code.

    Order is deliberate: schema → oMLX → MCP. Schema goes first so a
    permissions / disk-full failure surfaces before any network I/O.
    """
    # Import lazily so the module is import-safe even when settings are
    # incomplete (e.g. `python -c "import eldritch_dm.bootstrap"`).
    from eldritch_dm.config import get_settings
    from eldritch_dm.logging import get_logger

    log = get_logger("eldritch_dm.bootstrap")
    settings = get_settings()

    # ── 1. Local schema ───────────────────────────────────────────────────────
    try:
        await bootstrap(settings.eldritch_db_path)
        log.info("preflight_schema_ok", path=settings.eldritch_db_path)
    except Exception as exc:  # noqa: BLE001 — preflight must catch everything
        log.error("preflight_schema_failed", error=str(exc))
        _eprint(
            f"❌ Schema bootstrap failed at {settings.eldritch_db_path!s}: {exc}"
        )
        return EXIT_SCHEMA_FAIL

    # ── 2. oMLX /v1/models ────────────────────────────────────────────────────
    omlx_models_url = f"{str(settings.omlx_endpoint).rstrip('/')}/models"
    timeout = httpx.Timeout(5.0, connect=2.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(omlx_models_url)
            r.raise_for_status()
            payload: Any = r.json()
            models = payload.get("data", []) if isinstance(payload, dict) else []
            loaded_ids = {m.get("id") for m in models if isinstance(m, dict)}
            log.info(
                "preflight_omlx_ok",
                endpoint=str(settings.omlx_endpoint),
                model_count=len(models),
                loaded=sorted(i for i in loaded_ids if i),
            )
            if settings.omlx_model not in loaded_ids:
                # Soft warning per RESEARCH A5 — operator may load a different
                # model intentionally; preflight does not fail on this.
                log.warning(
                    "preflight_omlx_model_missing",
                    expected=settings.omlx_model,
                    loaded=sorted(i for i in loaded_ids if i),
                )
                _eprint(
                    "⚠️  Configured OMLX_MODEL "
                    f"{settings.omlx_model!r} is not currently loaded "
                    f"in oMLX. Loaded: {sorted(i for i in loaded_ids if i)}. "
                    "(Continuing — flip OMLX_MODEL or `omlx serve --model "
                    f"{settings.omlx_model}` to silence this.)"
                )
    except httpx.HTTPError as exc:
        log.error(
            "preflight_omlx_unreachable",
            endpoint=str(settings.omlx_endpoint),
            error=str(exc),
        )
        _eprint(
            f"❌ oMLX unreachable at {omlx_models_url}: {exc}\n"
            "   Is oMLX running? Try: "
            f"`curl -s {str(settings.omlx_endpoint).rstrip('/')}/models | jq .`"
        )
        return EXIT_OMLX_UNREACHABLE
    except Exception as exc:  # noqa: BLE001 — any non-HTTP error is also a fail
        log.error("preflight_omlx_unreachable", error=str(exc))
        _eprint(f"❌ oMLX preflight failed: {exc}")
        return EXIT_OMLX_UNREACHABLE

    # ── 3. dm20 MCP tools list ────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(str(settings.mcp_tools_url))
            r.raise_for_status()
            tools_payload: Any = r.json()
            # dm20's MCP gateway may return either a bare list or {"tools": [...]}
            if isinstance(tools_payload, list):
                tools = tools_payload
            elif isinstance(tools_payload, dict):
                tools = tools_payload.get("tools") or tools_payload.get("data") or []
            else:
                tools = []
            dm20_count = sum(
                1
                for t in tools
                if isinstance(t, dict)
                and isinstance(t.get("name"), str)
                and t["name"].startswith("dm20__")
            )
            log.info(
                "preflight_dm20_ok",
                mcp_tools_url=str(settings.mcp_tools_url),
                tool_count=len(tools),
                dm20_count=dm20_count,
            )
            if dm20_count == 0:
                log.error(
                    "preflight_dm20_not_loaded",
                    tool_count=len(tools),
                    mcp_tools_url=str(settings.mcp_tools_url),
                )
                _eprint(
                    "❌ dm20 MCP tools are not loaded in oMLX "
                    f"({settings.mcp_tools_url!s} returned "
                    f"{len(tools)} tools, 0 dm20__*). See "
                    "docs/dm20-troubleshooting.md for the fix."
                )
                return EXIT_DM20_NOT_LOADED
    except httpx.HTTPError as exc:
        log.error(
            "preflight_dm20_unreachable",
            mcp_tools_url=str(settings.mcp_tools_url),
            error=str(exc),
        )
        _eprint(
            f"❌ MCP tools endpoint unreachable at {settings.mcp_tools_url!s}: "
            f"{exc}"
        )
        return EXIT_DM20_NOT_LOADED
    except Exception as exc:  # noqa: BLE001 — JSON parse, etc.
        log.error("preflight_dm20_not_loaded", error=str(exc))
        _eprint(f"❌ MCP tools preflight failed: {exc}")
        return EXIT_DM20_NOT_LOADED

    log.info("preflight_ok")
    return EXIT_OK


def main() -> None:
    """Entry point for ``python -m eldritch_dm.bootstrap``.

    Configures logging in console mode (self-hosters running this command
    interactively expect colored output), runs the preflight, and exits
    with the preflight's return code so the operator's shell sees the
    correct status.
    """
    from eldritch_dm.logging import configure_logging

    configure_logging(level="INFO", fmt="console")
    code = asyncio.run(preflight())
    sys.exit(code)


if __name__ == "__main__":
    main()
