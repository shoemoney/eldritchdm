"""Bad: Modal on_submit whose first stmt is a non-send_modal/non-defer call."""
import discord
from discord import app_commands


@app_commands.command(name="modal_bad")
async def modal_bad(interaction: discord.Interaction) -> None:
    data = process_form_data()  # WRONG: neither defer nor send_modal
    await interaction.response.defer()
    await interaction.followup.send(data)
