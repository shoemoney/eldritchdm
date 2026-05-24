"""
EldritchDM bot process entrypoint.

Usage:
    python -m eldritch_dm.bot

Environment:
    DISCORD_TOKEN  — required Discord bot token
    DISCORD_GUILD_IDS — optional CSV of guild snowflake IDs (dev mode: syncs commands instantly)
    All other Settings fields — see src/eldritch_dm/config/__init__.py and .env.example

Exit codes:
    0 — clean shutdown (SIGINT / SIGTERM / KeyboardInterrupt)
    2 — fatal startup failure (setup_hook raised, never connected to Discord)
    4 — missing DISCORD_TOKEN (see eldritch_dm.bootstrap.EXIT_MISSING_TOKEN);
        emitted by require_token_or_exit before bot.run is attempted — SAFETY-03 /
        TD-1 closure. Previously this path raised discord.errors.LoginFailure with
        a traceback; v1.1 surfaces a friendly stderr message instead.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Start EldritchDM bot. Returns exit code."""
    # Inline imports to avoid module-level side effects when imported as a library
    from eldritch_dm.bootstrap import EXIT_MISSING_TOKEN
    from eldritch_dm.bot.bot import EldritchBot
    from eldritch_dm.config import Settings
    from eldritch_dm.config.token_guard import require_token_or_exit
    from eldritch_dm.logging import configure_logging, get_logger

    # Load settings first (may raise ValidationError if required vars missing).
    # DISCORD_TOKEN itself is Optional in Settings since D-26 — we validate it
    # ourselves via require_token_or_exit so we can emit a friendly stderr
    # message instead of a pydantic ValidationError traceback.
    settings = Settings()

    # Configure structlog before any other output
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        log_file=settings.log_file,
    )
    log = get_logger("eldritch_dm.bot.__main__")

    # SAFETY-03 / TD-1: validate DISCORD_TOKEN at the bot-launch boundary
    # with the same friendly error that run.py emits. Helper handles the
    # structured-log + stderr message; we just propagate the exit code.
    token = require_token_or_exit(settings, log)
    if token is None:
        return EXIT_MISSING_TOKEN

    bot = EldritchBot(settings)

    try:
        # bot.run is synchronous; it owns the asyncio event loop.
        # setup_hook failures propagate out here as exceptions → exit code 2.
        bot.run(token, log_handler=None)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        log.exception("bot_startup_failed")
        return 2


if __name__ == "__main__":
    sys.exit(main())
