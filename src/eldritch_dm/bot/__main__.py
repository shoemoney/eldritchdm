"""
EldritchDM bot process entrypoint.

Usage:
    python -m eldritch_dm.bot

Environment:
    DISCORD_TOKEN  — required Discord bot token
    DISCORD_GUILD_IDS — optional CSV of guild snowflake IDs (dev mode: syncs commands instantly)
    All other Settings fields — see src/eldritch_dm/config.py and .env.example

Exit codes:
    0 — clean shutdown (SIGINT / SIGTERM / KeyboardInterrupt)
    2 — fatal startup failure (setup_hook raised, never connected to Discord)
"""

from __future__ import annotations

import sys


def main() -> int:
    """Start EldritchDM bot. Returns exit code."""
    # Inline imports to avoid module-level side effects when imported as a library
    from eldritch_dm.bot.bot import EldritchBot
    from eldritch_dm.config import Settings
    from eldritch_dm.logging import configure_logging

    # Load settings first (may raise ValidationError if required vars missing)
    settings = Settings()

    # Configure structlog before any other output
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        log_file=settings.log_file,
    )

    bot = EldritchBot(settings)

    try:
        # bot.run is synchronous; it owns the asyncio event loop.
        # setup_hook failures propagate out here as exceptions → exit code 2.
        bot.run(settings.discord_token, log_handler=None)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        from eldritch_dm.logging import get_logger

        log = get_logger(__name__)
        log.exception("bot_startup_failed")
        return 2


if __name__ == "__main__":
    sys.exit(main())
