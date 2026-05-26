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
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
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

    # Phase 13 / MON-01: initialize observability sinks BEFORE Discord login.
    # Both are no-ops when their respective env gates are off:
    #   OBSERVABILITY_ENABLED=true          → OTel TracerProvider + OTLP export
    #   OBSERVABILITY_METRICS_ENDPOINT=true → Prometheus /metrics @ :9090
    # Discovery (Phase 13): Phase 11 defined ``init_tracing`` but no production
    # code path ever called it. Wiring it here is a Rule-3 deviation from the
    # Phase 11 plan that the executor identified and fixed.
    try:
        from eldritch_dm.observability import init_tracing
        from eldritch_dm.observability.metrics_endpoint import start_metrics_endpoint

        init_tracing()
        start_metrics_endpoint()
        # Phase 13 / MON-02: synchronous cold-start replay so a restart
        # during an ongoing breach lands in degraded mode immediately,
        # before the bot accepts the first Discord command.
        from eldritch_dm.observability.alert_evaluator import (
            boot_alert_evaluator,
        )

        boot_alert_evaluator(settings=settings)

        # Phase 13 / MON-03: budget guard. Single sync tick at boot — picks
        # up budget breaches that started before the restart and trips
        # degraded mode immediately. Periodic ticking deferred to v1.3
        # setup_hook (same pattern as AlertEvaluator).
        from decimal import Decimal as _D

        from eldritch_dm.observability.budget_guard import BudgetEvaluator
        from eldritch_dm.observability.cost import load_pricing
        from eldritch_dm.observability.metrics_endpoint import (
            is_metrics_endpoint_enabled,
        )
        from eldritch_dm.observability.tracer import is_enabled

        if is_enabled() or is_metrics_endpoint_enabled():
            try:
                cap = _D(os.environ.get("ELDRITCH_DAILY_LLM_BUDGET_USD", "5.00"))
            except Exception:  # noqa: BLE001
                log.warning("budget_guard.invalid_cap_env_falling_back_to_5_00")
                cap = _D("5.00")
            BudgetEvaluator(cap_usd=cap, table=load_pricing(settings)).tick()
    except Exception:  # noqa: BLE001 — observability is opt-in; never block boot
        log.exception("observability_init_failed")

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
