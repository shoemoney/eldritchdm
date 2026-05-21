"""Bad: Button callback whose first stmt is print(...)."""
import discord


class BadButton(discord.ui.DynamicItem[discord.ui.Button], template=r"bad:(?P<id>\d+)"):
    def __init__(self, id: int) -> None:
        super().__init__(discord.ui.Button(custom_id=f"bad:{id}"))
        self.id = id

    async def callback(self, interaction: discord.Interaction) -> None:
        print("clicked!")  # WRONG: should defer first
        await interaction.response.defer()
