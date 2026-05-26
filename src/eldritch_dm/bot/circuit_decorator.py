"""@catch_circuit_open decorator (SAFETY-02 / Phase 7 / D-31).

Wraps async Discord callbacks (cog methods, DynamicItem button callbacks) so
that ``MCPCircuitOpen`` exceptions are caught and surfaced as ephemeral
``WarningKind.DM_OFFLINE`` warnings instead of bubbling up to discord.py's
default unhandled-error UI noise.

Per D-31, v1.1 ships **warning only** — queue-replay of combat-critical
button intents is deferred to v1.2. Per OPS-02 the decorator ALWAYS swallows
``MCPCircuitOpen`` (re-raising would leak the traceback to discord.py); other
exception types propagate unchanged so genuine bugs remain visible.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any

from eldritch_dm.bot.warnings import WarningKind, send_warning
from eldritch_dm.logging import get_logger
from eldritch_dm.mcp.errors import MCPCircuitOpen

_log = get_logger(__name__)


def catch_circuit_open(
    fn: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Wrap an async Discord callback to surface MCPCircuitOpen as DM_OFFLINE.

    Required surface on ``interaction.client`` (the bot):
      * ``dm_offline_debouncer``: a :class:`DMOfflineDebouncer` instance.
      * ``circuit_breaker``: the MCP :class:`CircuitBreaker`.

    If either attribute is missing (should never happen in production — both
    are set in ``EldritchBot.setup_hook``), the decorator logs a warning and
    re-raises ``MCPCircuitOpen`` so the failure is visible during development.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except MCPCircuitOpen:
            # Discover the interaction in the call args. For both cog methods
            # (self, interaction, ...) and DynamicItem callbacks
            # (self, interaction) the interaction is the first non-self arg.
            interaction = None
            for a in args:
                # Discord interactions expose .client and .channel_id; that's
                # the duck-type we need.
                if hasattr(a, "client") and hasattr(a, "channel_id"):
                    interaction = a
                    break
            if interaction is None:
                _log.warning("circuit_decorator_no_interaction_in_args")
                # Without an interaction we cannot surface a warning; swallow
                # to honor OPS-02 "never let MCPCircuitOpen reach discord.py".
                return None

            bot = getattr(interaction, "client", None)
            debouncer = getattr(bot, "dm_offline_debouncer", None)
            circuit = getattr(bot, "circuit_breaker", None)
            channel_id = str(getattr(interaction, "channel_id", "") or "")

            if debouncer is None or circuit is None:
                _log.warning(
                    "circuit_decorator_missing_infra",
                    has_debouncer=debouncer is not None,
                    has_circuit=circuit is not None,
                )
                # Re-raise so the missing wiring is visible during dev — in
                # production setup_hook guarantees both attributes are set.
                raise

            if debouncer.maybe_warn(channel_id, circuit):
                await send_warning(
                    interaction,
                    WarningKind.DM_OFFLINE,
                    failure_count=getattr(circuit, "failure_count", 0),
                )
            # OPS-02: always swallow MCPCircuitOpen — never let it reach
            # discord.py's default unhandled-error handler.
            return None

    return wrapper
