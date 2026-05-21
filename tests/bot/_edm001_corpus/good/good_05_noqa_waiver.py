"""Good: App command with # noqa: EDM001 on def line — explicit waiver."""
from discord import app_commands
import discord


@app_commands.command(name="autocomplete_cmd")
async def autocomplete_cmd(interaction: discord.Interaction) -> None:  # noqa: EDM001 — autocomplete handler
    result = await some_helper()
    await interaction.followup.send(result)
