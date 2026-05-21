"""Bad: Button callback that defers in an if branch but not unconditionally first."""
import discord


class ConditionalButton(discord.ui.DynamicItem[discord.ui.Button], template=r"cond:(?P<id>\d+)"):
    def __init__(self, id: int) -> None:
        super().__init__(discord.ui.Button(custom_id=f"cond:{id}"))
        self.id = id

    async def callback(self, interaction: discord.Interaction) -> None:
        if some_condition():  # WRONG: defer must be first, unconditionally
            await interaction.response.defer()
        else:
            await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("conditional")
