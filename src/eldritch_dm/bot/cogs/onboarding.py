"""Onboarding cog — /help command + on_guild_join welcome embed.

When EldritchDM is added to a server, players have no idea what commands exist.
This cog gives them a landing pad:

  - `/help` (ephemeral) — lists every slash command grouped by phase.
  - `on_guild_join` listener — posts a public welcome embed to the server's
    system channel (or the first writable text channel) the moment the bot
    is invited.

Both surfaces fail-soft: if the bot lacks Send Messages / Embed Links in the
target channel, the listener swallows the Forbidden and logs it. /help is
ephemeral so it cannot leak session state.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from eldritch_dm.bot.embeds import EmbedColor
from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from eldritch_dm.bot.bot import EldritchBot

log = get_logger(__name__)


def _build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎲 EldritchDM — Command Guide",
        description=(
            "I'm your mechanically-honest AI Dungeon Master. "
            "Narration is AI; every die roll, HP change, and turn boundary "
            "is enforced by a deterministic rules engine — I can't cheat."
        ),
        color=int(EmbedColor.LOBBY),
    )
    embed.add_field(
        name="🛠️ Setup — start here",
        value=(
            "`/start_game` — Open a campaign lobby in this channel\n"
            "`/upload_character_file` — Upload a character sheet image or PDF\n"
            "`/upload_character_url` — Import from D&D Beyond\n"
            "`/upload_character_manual` — Type the sheet in by hand\n"
            "`/load_adventure` — Load an official 5e module"
        ),
        inline=False,
    )
    embed.add_field(
        name="🎮 Session",
        value=(
            "`/status` — Show this channel's active session\n"
            "`/end_game` — End the campaign and clear session memory"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔧 Diagnostics",
        value="`/ping` — Check ShoeGPT (AI) and rules-engine health",
        inline=False,
    )
    embed.add_field(
        name="📜 Typical flow",
        value=(
            "1. `/start_game` to open a lobby\n"
            "2. Each player runs `/upload_character_file`\n"
            "3. Everyone clicks **Ready** in the lobby\n"
            "4. The story begins — declare actions via the buttons that appear"
        ),
        inline=False,
    )
    embed.set_footer(text="The dice decide. I just describe.")
    return embed


def _build_welcome_embed() -> discord.Embed:
    embed = discord.Embed(
        title="👋 EldritchDM has joined the table",
        description=(
            "Hi! I'm your AI Dungeon Master for Dungeons & Dragons 5e.\n\n"
            "**To get started:**\n"
            "• Run `/start_game` in the channel you want to play in\n"
            "• Players upload sheets with `/upload_character_file`\n"
            "• Use `/help` any time to see every command"
        ),
        color=int(EmbedColor.LOBBY),
    )
    embed.add_field(
        name="Mechanically honest",
        value=(
            "I narrate the story, but a deterministic rules engine handles "
            "every roll, HP change, AC check, and turn boundary. I literally "
            "can't fudge the math."
        ),
        inline=False,
    )
    embed.set_footer(text="Roll initiative when you're ready.")
    return embed


def _pick_welcome_channel(guild: discord.Guild) -> discord.TextChannel | None:
    """Pick the best channel to post the welcome embed in.

    Preference order:
      1. guild.system_channel if writable
      2. First TextChannel where bot can send messages + embed links
      3. None (caller should skip)
    """
    me = guild.me
    if me is None:
        return None

    def _ok(ch: discord.TextChannel) -> bool:
        perms = ch.permissions_for(me)
        return perms.send_messages and perms.embed_links

    sys_ch = guild.system_channel
    if sys_ch is not None and _ok(sys_ch):
        return sys_ch

    for ch in guild.text_channels:
        if _ok(ch):
            return ch
    return None


class Onboarding(commands.Cog):
    """Onboarding cog: /help command + on_guild_join welcome."""

    def __init__(self, bot: EldritchBot) -> None:
        self.bot = bot
        self._logger = log.bind(cog="Onboarding")

    @app_commands.command(
        name="help",
        description="Show every EldritchDM command grouped by phase",
    )
    async def help_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        self._logger.info(
            "help_invoked",
            channel_id=interaction.channel_id,
            user_id=interaction.user.id,
        )
        await interaction.followup.send(embed=_build_help_embed(), ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        bound = self._logger.bind(guild_id=guild.id, guild_name=guild.name)
        channel = _pick_welcome_channel(guild)
        if channel is None:
            bound.warning("welcome_skipped_no_writable_channel")
            return
        try:
            await channel.send(embed=_build_welcome_embed())
            bound.info("welcome_posted", channel_id=channel.id)
        except discord.Forbidden:
            bound.warning("welcome_forbidden", channel_id=channel.id)
        except discord.HTTPException as exc:
            bound.warning("welcome_http_error", channel_id=channel.id, error=str(exc))


async def setup(bot: EldritchBot) -> None:
    await bot.add_cog(Onboarding(bot))
