"""
EldritchDM project-root entrypoint (Phase 5 Plan 03 — HOST-04 / RESEARCH Pattern 6).

Usage::

    python run.py                  # interactive — runs preflight then starts bot
    python run.py --check-only     # runs preflight then exits (CI / launchd smoke)
    python run.py --no-preflight   # skips preflight (dev convenience)
    ELDRITCH_ALLOW_OFFLINE_START=1 python run.py  # production escape hatch

The module entrypoint ``python -m eldritch_dm.bot`` remains valid for backwards
compat with Phase 1-4 muscle memory. ``run.py`` adds:

* :func:`eldritch_dm.bootstrap.preflight` before launching the bot
* graceful ``SIGTERM`` handling (delegates to OPS-04 shutdown chain)
* exit-code propagation to the supervisor (launchd / systemd)

This file lives at the *project root* on purpose — launchd plists and the
README invocation hard-code ``python3 /path/to/run.py``. Keeping it
importable as ``import run`` (rather than a package module) means the file
must NOT execute the bot at import time — only when invoked as ``__main__``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys


def _allow_offline_start() -> bool:
    """``ELDRITCH_ALLOW_OFFLINE_START=1`` → skip preflight (Pattern 6 / D-15).

    Used by launchd-supervised deploys where oMLX may not yet be up when
    EldritchDM starts (race at boot). The OPS-02 circuit breaker handles
    *runtime* oMLX loss; this env var is for the cold-start gap.
    """
    return os.environ.get("ELDRITCH_ALLOW_OFFLINE_START", "0") == "1"


def _install_sigterm_handler() -> None:
    """Convert SIGTERM into KeyboardInterrupt so discord.py's shutdown path runs.

    discord.py's ``bot.run`` installs its own SIGINT handler. We install a
    SIGTERM handler that raises KeyboardInterrupt — same effect, clean
    shutdown via the OPS-04 chain (riposte sweeper stop → coalescer flush →
    DB writer queue drain → ``bot.close``).
    """

    def _on_sigterm(signum: int, frame: object) -> None:  # noqa: ARG001 — POSIX signature
        raise KeyboardInterrupt("SIGTERM received")

    signal.signal(signal.SIGTERM, _on_sigterm)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="EldritchDM entrypoint (HOST-04).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Run preflight checks and exit (do not start the bot).",
    )
    parser.add_argument(
        "--no-preflight",
        action="store_true",
        help="Skip the preflight checks before starting the bot.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Validate env, run preflight, start the bot. Return process exit code."""
    args = _parse_args(argv)

    # Inline imports so `python run.py --help` doesn't pay full startup cost.
    from eldritch_dm import bootstrap as preflight_mod
    from eldritch_dm.config import Settings
    from eldritch_dm.logging import configure_logging, get_logger

    # Settings() may raise pydantic.ValidationError on missing DISCORD_TOKEN.
    # We let that propagate — Python's traceback names the missing field
    # clearly, and the exit code from an uncaught ValidationError is non-zero.
    settings = Settings()

    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        log_file=settings.log_file,
    )
    log = get_logger("eldritch_dm.run")

    # Preflight gate -----------------------------------------------------------
    skip_preflight = args.no_preflight or _allow_offline_start()
    if args.check_only:
        log.info("run_check_only_mode")
        code = asyncio.run(preflight_mod.preflight())
        log.info("run_check_only_complete", exit_code=code)
        return code

    if not skip_preflight:
        code = asyncio.run(preflight_mod.preflight())
        if code != preflight_mod.EXIT_OK:
            log.error("run_preflight_failed", exit_code=code)
            return code
    else:
        log.warning(
            "run_preflight_skipped",
            reason=(
                "--no-preflight CLI flag"
                if args.no_preflight
                else "ELDRITCH_ALLOW_OFFLINE_START=1"
            ),
        )

    # SIGTERM → clean shutdown -------------------------------------------------
    _install_sigterm_handler()

    # Start the bot ------------------------------------------------------------
    from eldritch_dm.bot.bot import EldritchBot

    bot = EldritchBot(settings)
    try:
        bot.run(settings.discord_token, log_handler=None)
        return 0
    except KeyboardInterrupt:
        log.info("run_keyboard_interrupt")
        return 0
    except Exception:
        log.exception("run_bot_failed")
        return 2


if __name__ == "__main__":
    sys.exit(main())
