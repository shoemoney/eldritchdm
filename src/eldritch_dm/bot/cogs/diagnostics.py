"""
Diagnostics cog — /ping and /status slash commands.

SCOPE WALL: Phase 2 only ships /ping and /status. Gameplay commands
(/start_game, /upload_character_*, /declare_action, etc.) land in Phases 3-5
in their own cogs.

Security notes (STRIDE threat register):
- T-02-01: /ping response is ephemeral (circuit state not broadcast)
- T-02-02: /status response is ephemeral (no dm20_party_token included)
- T-02-05: Every callback binds structlog context (channel_id, user_id, command) — audit trail
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from eldritch_dm.logging import get_logger
from eldritch_dm.mcp.health import get_circuit_state

if TYPE_CHECKING:
    from eldritch_dm.bot.bot import EldritchBot

log = get_logger(__name__)


class Diagnostics(commands.Cog):
    """Diagnostics cog: /ping (MCP health) + /status (channel session readout)."""

    def __init__(self, bot: "EldritchBot") -> None:
        self.bot = bot
        self._logger = log.bind(cog="Diagnostics")

    # ── /ping ────────────────────────────────────────────────────────────────

    @app_commands.command(name="ping", description="Check ShoeGPT / MCP health status")
    async def ping(self, interaction: discord.Interaction) -> None:
        """Reply with MCP circuit state + endpoint URL (ephemeral)."""
        # D-09: defer FIRST — gives 15-minute follow-up budget; prevents 3-second cliff
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = self._logger.bind(
            command="ping",
            channel_id=interaction.channel_id,
            user_id=interaction.user.id,
        )
        bound_log.info("ping_invoked")

        state = get_circuit_state(self.bot.circuit_breaker)
        endpoint = str(self.bot.settings.omlx_endpoint)

        status_icon = "✅" if str(state) == "CLOSED" else "❌"
        content = (
            f"{status_icon} **ShoeGPT Status**\n"
            f"Circuit: `{state}`\n"
            f"Endpoint: `{endpoint}`"
        )

        await interaction.followup.send(content=content, ephemeral=True)
        bound_log.info("ping_responded", circuit_state=str(state))

    # ── /status ──────────────────────────────────────────────────────────────

    @app_commands.command(name="status", description="Show the active D&D session in this channel")
    async def status(self, interaction: discord.Interaction) -> None:
        """Reply with channel session details or 'No active session' (ephemeral)."""
        # D-09: defer FIRST
        await interaction.response.defer(thinking=True, ephemeral=True)

        bound_log = self._logger.bind(
            command="status",
            channel_id=interaction.channel_id,
            user_id=interaction.user.id,
        )
        bound_log.info("status_invoked")

        # channel_id on Interaction is int; repo expects str
        session = await self.bot.channel_sessions_repo.get(str(interaction.channel_id))

        if session is None:
            content = "No active session in this channel."
        else:
            content = (
                f"**Active Session**\n"
                f"State: `{session.state}`\n"
                f"Campaign: **{session.campaign_name}**\n"
                f"Started: `{session.created_at.strftime('%Y-%m-%d %H:%M UTC')}`"
            )

        await interaction.followup.send(content=content, ephemeral=True)
        bound_log.info(
            "status_responded",
            has_session=session is not None,
            state=str(session.state) if session else None,
        )


async def setup(bot: "EldritchBot") -> None:
    """discord.py extension entry point — called by bot.load_extension(...)."""
    await bot.add_cog(Diagnostics(bot))
