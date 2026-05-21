"""Good: Button callback whose first stmt is await interaction.response.defer(ephemeral=True)."""
import discord


class MyButton(discord.ui.DynamicItem[discord.ui.Button], template=r"mybutton:(?P<id>\d+)"):
    def __init__(self, id: int) -> None:
        super().__init__(discord.ui.Button(custom_id=f"mybutton:{id}"))
        self.id = id

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("clicked")
