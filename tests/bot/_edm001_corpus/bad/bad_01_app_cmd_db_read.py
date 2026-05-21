"""Bad: App command whose first stmt is a DB read, not defer."""
from discord import app_commands
import discord


@app_commands.command(name="broken")
async def broken(interaction: discord.Interaction) -> None:
    result = await some_db_read()  # WRONG: should defer first
    await interaction.response.defer(thinking=True)
    await interaction.followup.send(result)
