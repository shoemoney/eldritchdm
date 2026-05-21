"""
eldritch_dm.bot.cogs — Discord cogs subpackage.

Future cogs (lobby, ingest, exploration, combat, riposte) will be added here.
Each cog file must expose an `async def setup(bot) -> None` coroutine that
calls `await bot.add_cog(...)` — this is the discord.py extension loading
convention used by `bot.load_extension(...)`.

Current cogs:
- diagnostics.py  — /ping (MCP health) + /status (channel session readout)
"""
