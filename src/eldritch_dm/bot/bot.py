"""
EldritchBot — discord.py bot subclass for EldritchDM.

Lifecycle:
  1. __init__: construct with Settings, set intents, no I/O.
  2. setup_hook: boot persistence + MCP health + cogs; fatal on failure (D-25).
  3. close: graceful shutdown — cancel tasks, drain queue, close MCP client.

Scope wall: Phase 2 ships /ping and /status via the Diagnostics cog.
Gameplay commands (/start_game, /upload_character_*, /declare_action, etc.)
land in Phases 3-5 in their own cogs.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from eldritch_dm.config import Settings
from eldritch_dm.logging import get_logger
from eldritch_dm.mcp.client import MCPClient
from eldritch_dm.mcp.health import CircuitBreaker, HealthCheck
from eldritch_dm.persistence import ChannelSessionRepo, WriterQueue
from eldritch_dm.persistence.bootstrap import bootstrap

log = get_logger(__name__)


class EldritchBot(commands.Bot):
    """EldritchDM Discord bot.

    Args:
        settings: Loaded Settings instance.
    """

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = False  # D-04: security choice — bot never reads raw messages

        super().__init__(
            command_prefix="!",  # unused; required by commands.Bot base class
            intents=intents,
            application_id=settings.discord_application_id,
        )

        self.settings = settings

        # Subsystem handles — initialized in setup_hook, None until then
        self.writer_queue: WriterQueue | None = None
        self.circuit_breaker: CircuitBreaker | None = None
        self.mcp: MCPClient | None = None
        self.health: HealthCheck | None = None
        self.channel_sessions_repo: ChannelSessionRepo | None = None

        self._logger = log.bind(component="EldritchBot")

    async def setup_hook(self) -> None:
        """Boot persistence, MCP health, and cogs.

        Runs BEFORE the gateway connection is established (discord.py guarantee).
        Any exception here is fatal — bot does NOT connect to Discord (D-25).
        Per issue #8210: raise, do NOT call bot.close() from here.

        Order (D-24):
          (a) ensure_schema (idempotent DDL)
          (b) WriterQueue.start()
          (c) CircuitBreaker + MCPClient
          (d) HealthCheck.start()
          (e) ChannelSessionRepo
          (f) load Diagnostics cog
          (g) sync app command tree
        """
        settings = self.settings

        # (a) Schema bootstrap — idempotent, safe to call multiple times
        await bootstrap(settings.eldritch_db_path)

        # (b) WriterQueue — serializes all DB writes
        self.writer_queue = WriterQueue(settings.eldritch_db_path)
        await self.writer_queue.start()

        # (c) Circuit breaker + MCP client
        self.circuit_breaker = CircuitBreaker(threshold=settings.omlx_circuit_breaker_threshold)
        # MCPClient expects the base URL without trailing /v1
        mcp_base = str(settings.omlx_endpoint).rstrip("/")
        if mcp_base.endswith("/v1"):
            mcp_base = mcp_base[: -len("/v1")]
        self.mcp = MCPClient(mcp_base, circuit_breaker=self.circuit_breaker)

        # (d) Health check background task
        self.health = HealthCheck(
            str(settings.omlx_endpoint),
            interval=settings.omlx_health_interval,
            breaker=self.circuit_breaker,
        )
        await self.health.start()

        # (e) Channel sessions repository
        self.channel_sessions_repo = ChannelSessionRepo(
            settings.eldritch_db_path,
            self.writer_queue,
        )

        # Plan 03: rehydrate persistent_views here
        # (register DynamicItem subclasses via self.add_dynamic_items(...) and
        #  optionally log count from PersistentViewRepo.list_all())

        # (f) Load cogs
        await self.load_extension("eldritch_dm.bot.cogs.diagnostics")

        # (g) Sync app command tree
        guild_ids = settings.guild_ids_list
        if guild_ids:
            synced_total: list[discord.app_commands.AppCommand] = []
            for gid in guild_ids:
                synced = await self.tree.sync(guild=discord.Object(id=gid))
                synced_total.extend(synced)
            cmd_count = len(synced_total)
        else:
            synced_global = await self.tree.sync()
            cmd_count = len(synced_global)

        self._logger.info(
            "setup_hook_ok",
            cmd_count=cmd_count,
            guild_ids=guild_ids,
            db_path=settings.eldritch_db_path,
        )

    async def close(self) -> None:
        """Graceful shutdown (D-26).

        Order:
          1. Stop HealthCheck (cancel background ping task)
          2. Stop WriterQueue (best-effort drain; full timeout wired in Plan 03)
          3. Close MCPClient httpx pool
          4. super().close() — disconnects gateway
        """
        self._logger.info("bot_closing")

        if self.health is not None:
            await self.health.stop()

        if self.writer_queue is not None:
            await self.writer_queue.stop()

        if self.mcp is not None:
            await self.mcp.aclose()

        await super().close()
        self._logger.info("bot_closed")
