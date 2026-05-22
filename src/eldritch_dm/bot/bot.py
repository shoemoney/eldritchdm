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

import asyncio

import discord
from discord.ext import commands

from eldritch_dm.config import Settings
from eldritch_dm.logging import get_logger
from eldritch_dm.mcp.client import MCPClient
from eldritch_dm.mcp.health import CircuitBreaker, HealthCheck
from eldritch_dm.persistence import ChannelSessionRepo, WriterQueue
from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.persistent_views_repo import PersistentViewRepo

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
        self.persistent_views_repo: PersistentViewRepo | None = None
        # Phase 3 convenience aliases — ReadyButton.callback and LobbyCog read these via
        # interaction.client (cannot use constructor injection with DynamicItem).
        # Named with trailing underscore to avoid collision with discord.Client.persistent_views
        # property. These are set to the same objects as channel_sessions_repo /
        # persistent_views_repo during setup_hook; both names are valid.
        # NOTE: discord.Client has a `persistent_views` property, so we use different names.
        self.channel_sessions: ChannelSessionRepo | None = None
        self.pv_repo: PersistentViewRepo | None = None

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

        # (e) Channel sessions repository + persistent views repository
        self.channel_sessions_repo = ChannelSessionRepo(
            settings.eldritch_db_path,
            self.writer_queue,
        )
        self.persistent_views_repo = PersistentViewRepo(
            settings.eldritch_db_path,
            self.writer_queue,
        )
        # Phase 3 convenience aliases for ReadyButton.callback + LobbyCog
        # (discord.Client has a `persistent_views` property; use pv_repo instead)
        self.channel_sessions = self.channel_sessions_repo
        self.pv_repo = self.persistent_views_repo

        # (e2) Register DynamicItem subclasses — the primary dispatch mechanism.
        # add_dynamic_items is sufficient for persistent buttons per RESEARCH.md Pitfall 1.
        from eldritch_dm.bot.dynamic_items import DYNAMIC_ITEM_CLASSES
        from eldritch_dm.bot.setup_hook import rehydrate_persistent_views

        self.add_dynamic_items(*DYNAMIC_ITEM_CLASSES)

        # (e3) Rehydrate persistent_views: call bot.add_view for each DB row
        # (audit layer; dispatch still works via add_dynamic_items above)
        rehydrated_count = await rehydrate_persistent_views(
            self,
            self.persistent_views_repo,
            self.channel_sessions_repo,
        )

        # (f) Load cogs
        await self.load_extension("eldritch_dm.bot.cogs.diagnostics")
        # Phase 3: LobbyCog (/start_game, /load_adventure, ReadyButton wiring)
        await self.load_extension("eldritch_dm.bot.cogs.lobby")
        # Phase 3: IngestCog (/upload_character_url, /upload_character_file, /upload_character_manual)
        await self.load_extension("eldritch_dm.bot.cogs.ingest")

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
            rehydrated_views=rehydrated_count,
            cmd_count=cmd_count,
            guild_ids=guild_ids,
            db_path=settings.eldritch_db_path,
        )

    async def close(self) -> None:
        """Graceful shutdown (D-26 / OPS-04).

        Order (T-02-16 mitigated by 5s timeout on writer_queue drain):
          1. Stop HealthCheck (cancel background ping task)
          2. Stop WriterQueue (drain with 5s timeout; log timeout, continue)
          3. Close MCPClient httpx pool
          4. super().close() — disconnects gateway

        Each step is wrapped in try/except so subsequent steps always run,
        even if an earlier step raises an unexpected error.
        """
        self._logger.info("bot_closing")

        # Step 1: Stop HealthCheck
        if self.health is not None:
            try:
                await self.health.stop()
                self._logger.debug("health_stopped")
            except Exception:  # noqa: BLE001
                self._logger.exception("health_stop_error")

        # Step 2: Drain WriterQueue with 5s timeout (T-02-16)
        if self.writer_queue is not None:
            try:
                await asyncio.wait_for(self.writer_queue.stop(), timeout=5.0)
                self._logger.debug("writer_queue_stopped")
            except TimeoutError:
                self._logger.warning("writer_queue_drain_timeout")
            except Exception:  # noqa: BLE001
                self._logger.exception("writer_queue_stop_error")

        # Step 3: Close MCP httpx connection pool
        if self.mcp is not None:
            try:
                await self.mcp.aclose()
                self._logger.debug("mcp_closed")
            except Exception:  # noqa: BLE001
                self._logger.exception("mcp_close_error")

        # Step 4: Disconnect gateway
        await super().close()
        self._logger.info("bot_closed")
