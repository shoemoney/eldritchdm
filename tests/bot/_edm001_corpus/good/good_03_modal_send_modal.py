"""Good: Modal on_submit whose first stmt is send_modal (D-12 exception)."""
import discord
from discord import app_commands


@app_commands.command(name="open_modal")
async def open_modal(interaction: discord.Interaction) -> None:  # noqa: EDM001 — first response is send_modal
    await interaction.response.send_modal(discord.ui.Modal(title="Test"))
