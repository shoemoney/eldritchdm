"""
EldritchDM ephemeral warning helper.

Provides a single entry point — ``send_warning`` — for dispatching
standardized ephemeral error/feedback messages to Discord players.

Design notes:
  - All warnings are ephemeral (D-32 / T-02-11): never broadcast to channel.
  - Caller must have already deferred the interaction (D-09). This helper
    does NOT check ``interaction.response.is_done()`` defensively — the EDM001
    lint rule (landing in Plan 03) enforces the defer contract at CI time.
  - Missing context keys raise ``ValueError`` with a clear message naming the
    absent keys, rather than silently swallowing a ``KeyError``.
  - Logs ``warning_sent`` with kind + ctx on every dispatch (D-38).

Usage::

    # Caller has already deferred:
    await send_warning(interaction, WarningKind.NOT_YOUR_TURN, actor_name="Thorin")
    await send_warning(interaction, WarningKind.DM_OFFLINE, failure_count=5)
"""

from __future__ import annotations

import string
from enum import StrEnum

import discord

from eldritch_dm.logging import get_logger

log = get_logger(__name__)


# ── WarningKind ────────────────────────────────────────────────────────────────


class WarningKind(StrEnum):
    """Enumeration of standardized player-facing warning kinds."""

    NOT_YOUR_TURN = "not_your_turn"
    RIPOSTE_EXPIRED = "riposte_expired"
    DM_OFFLINE = "dm_offline"
    INVALID_ACTION = "invalid_action"
    RATE_LIMITED = "rate_limited"


# ── Copy table ─────────────────────────────────────────────────────────────────

_COPY: dict[WarningKind, str] = {
    WarningKind.NOT_YOUR_TURN: (
        "❌ It is not your turn, **{actor_name}**. Sit tight!"
    ),
    WarningKind.RIPOSTE_EXPIRED: (
        "⌛ The riposte window has closed."
    ),
    WarningKind.DM_OFFLINE: (
        "🔌 ShoeGPT is offline. Health check failed {failure_count} times in a row."
        " Try again in a moment."
    ),
    WarningKind.INVALID_ACTION: (
        "❌ Invalid action: {reason}"
    ),
    WarningKind.RATE_LIMITED: (
        "🐌 Slow down — try again in {retry_after}s."
    ),
}


# ── Helper ─────────────────────────────────────────────────────────────────────


def _missing_keys(template: str, ctx: dict) -> list[str]:
    """Return the format-key names present in *template* but absent from *ctx*."""
    formatter = string.Formatter()
    required = {
        field_name
        for _, field_name, _, _ in formatter.parse(template)
        if field_name is not None and field_name != ""
    }
    return sorted(required - ctx.keys())


async def send_warning(
    interaction: discord.Interaction,
    kind: WarningKind,
    **ctx,
) -> None:
    """Send a standardized ephemeral warning to the player.

    Args:
        interaction: The Discord interaction (must already be deferred — D-09).
        kind: Which warning to send.
        **ctx: Format keys required by the warning template (e.g. ``actor_name``
            for ``NOT_YOUR_TURN``).

    Raises:
        ValueError: If a format key required by the template is absent from *ctx*.
    """
    template = _COPY[kind]

    missing = _missing_keys(template, ctx)
    if missing:
        raise ValueError(
            f"Missing context for warning {kind!r}: needs {missing!r}. "
            f"Provide these as keyword arguments to send_warning()."
        )

    content = template.format(**ctx)

    # D-38: log warning dispatch
    log.bind(warning_kind=kind, **ctx).info("warning_sent")

    await interaction.followup.send(content=content, ephemeral=True)
