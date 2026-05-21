"""Bad: App command whose first await is a helper, not defer."""
from discord import app_commands
import discord


@app_commands.command(name="wrong_order")
async def wrong_order(interaction: discord.Interaction) -> None:
    await some_helper()  # WRONG: should defer first
    await interaction.response.defer(thinking=True)
    await interaction.followup.send("done")
