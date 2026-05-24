"""Good: App command whose first body stmt is await interaction.response.defer(thinking=True)."""
import discord
from discord import app_commands


@app_commands.command(name="ping")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True, ephemeral=True)
    await interaction.followup.send("pong")
