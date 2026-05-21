"""Good: App command with a docstring THEN defer — docstring ignored."""
from discord import app_commands
import discord


@app_commands.command(name="status")
async def status(interaction: discord.Interaction) -> None:
    """Reply with current channel session state."""
    await interaction.response.defer(thinking=True, ephemeral=True)
    await interaction.followup.send("status OK")
