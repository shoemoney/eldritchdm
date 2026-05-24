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
from typing import Any

import discord
from discord.ext import commands

from eldritch_dm.bot.coalescer import ChannelEditBudget
from eldritch_dm.bot.dm_offline_debouncer import DMOfflineDebouncer
from eldritch_dm.config import Settings
from eldritch_dm.gameplay.eligibility_loader import load_eligibility
from eldritch_dm.gameplay.exploration_batch import BatchCoordinator
from eldritch_dm.gameplay.party_mode import PartyModeOrchestrator
from eldritch_dm.gameplay.riposte_sweeper import RiposteSweeper
from eldritch_dm.gameplay.session_locks import SessionLocks
from eldritch_dm.logging import get_logger
from eldritch_dm.mcp.client import MCPClient
from eldritch_dm.mcp.health import CircuitBreaker, HealthCheck
from eldritch_dm.mcp.rate_limit import ChannelRateLimiter
from eldritch_dm.persistence import ChannelSessionRepo, WriterQueue
from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.models import ChannelState
from eldritch_dm.persistence.pc_classes_repo import PCClassesRepo
from eldritch_dm.persistence.persistent_views_repo import PersistentViewRepo
from eldritch_dm.persistence.riposte_timers_repo import RiposteTimerRepo
from eldritch_dm.persistence.sanitizer_audit_repo import SanitizerAuditRepo
from eldritch_dm.safety.sanitizer import make_async_audit_callback

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
        # G-2 (v1.0 audit closure): SanitizerAuditRepo wiring. Without this,
        # SAN-05 was unsatisfied at runtime — strips logged via structlog but
        # never persisted to the sanitizer_audit table. Instantiated in
        # setup_hook so the cog wiring at exploration.py:107 can pass it via
        # make_async_audit_callback(...).
        self.sanitizer_audit_repo: SanitizerAuditRepo | None = None
        # SAFETY-01 (G-3 / Phase 7 closure): memoized sync callback that
        # bridges sync sanitize_player_input to the async repo. Set in
        # setup_hook AFTER sanitizer_audit_repo is built. Reused across
        # every modal callback construction (IngestCog modals, exploration
        # DeclareActionModal). None until setup_hook runs.
        self.sanitizer_audit_callback: Any = None
        # SAFETY-02 (G-4 / Phase 7 closure): per-channel debouncer for
        # WarningKind.DM_OFFLINE. Constructed in setup_hook with default
        # debounce=30s and min-open=5s (D-34). The @catch_circuit_open
        # decorator reads this via interaction.client.dm_offline_debouncer.
        self.dm_offline_debouncer: DMOfflineDebouncer | None = None
        # Phase 3 convenience aliases — ReadyButton.callback and LobbyCog read these via
        # interaction.client (cannot use constructor injection with DynamicItem).
        # Named with trailing underscore to avoid collision with discord.Client.persistent_views
        # property. These are set to the same objects as channel_sessions_repo /
        # persistent_views_repo during setup_hook; both names are valid.
        # NOTE: discord.Client has a `persistent_views` property, so we use different names.
        self.channel_sessions: ChannelSessionRepo | None = None
        self.pv_repo: PersistentViewRepo | None = None

        # Phase 4 gameplay subsystems — initialized in setup_hook
        self.rate_limiter: ChannelRateLimiter | None = None
        self.batch_coordinator: BatchCoordinator | None = None
        self.orchestrator: PartyModeOrchestrator | None = None
        # Phase 5 Plan 01 gameplay subsystems — initialized in setup_hook
        self.pc_classes: PCClassesRepo | None = None
        self.riposte_timers: RiposteTimerRepo | None = None
        self.riposte_timers_repo: RiposteTimerRepo | None = None
        self.monster_driver: Any = None
        # Phase 8 (HOMEBREW-01): loader-resolved Riposte eligibility frozenset.
        # Empty until setup_hook runs; populated via load_eligibility(settings).
        self.eligibility_set: frozenset[tuple[str, str]] = frozenset()
        # Phase 5 Plan 02 gameplay subsystems — initialized in setup_hook
        self.session_locks: SessionLocks | None = None
        self.riposte_sweeper: RiposteSweeper | None = None
        # Per-channel edit budget instances — keyed by channel_id string
        self._channel_edit_budgets: dict[str, ChannelEditBudget] = {}

        self._logger = log.bind(component="EldritchBot")

    async def close_exploration_coalescer_for(self, channel_id: str) -> None:
        """Close ExplorationCog's coalescer for *channel_id* (cross-cog handoff).

        Called by CombatCog on EXPLORATION->COMBAT transition so the exploration
        embed coalescer is cleanly closed before the combat embed is posted.

        Delegates to ExplorationCog.on_state_change(EXPLORATION, COMBAT) which
        handles its own coalescer lifecycle. If the cog is not loaded, no-ops.

        Avoids direct cog->cog imports (circular import prevention per D-24).
        """
        exploration_cog = self.get_cog("ExplorationCog")
        if exploration_cog is None:
            return
        # Trigger the EXPLORATION->COMBAT path in ExplorationCog which closes
        # the exploration coalescer for this channel.
        try:
            await exploration_cog.on_state_change(
                channel_id,
                ChannelState.EXPLORATION,
                ChannelState.COMBAT,
            )
        except Exception:  # noqa: BLE001
            log.warning("close_exploration_coalescer_error", channel_id=channel_id)

    async def close_combat_coalescer_for(self, channel_id: str) -> None:
        """Close CombatCog's coalescer for *channel_id* (cross-cog handoff).

        Called externally (e.g. Plan 03 restart drill) to cleanly close the
        combat embed coalescer without triggering the full COMBAT->EXPLORATION
        state change flow.

        Avoids direct cog->cog imports (circular import prevention per D-24).
        """
        combat_cog = self.get_cog("CombatCog")
        if combat_cog is None:
            return
        coalescer = getattr(combat_cog, "_coalescers", {}).pop(channel_id, None)
        if coalescer is not None:
            try:
                await coalescer.close()
            except Exception:  # noqa: BLE001
                log.warning("close_combat_coalescer_error", channel_id=channel_id)

    async def current_round_for_channel(self, channel_id: str) -> int:
        """Return the current dm20 combat round number.

        Phase 5 Plan 01: used by RiposteButton.callback's `handle_riposte_click`
        to label the consumed reaction. No caching in v1 (Riposte clicks are
        rare); Plan 02 may add a tiny LRU/TTL cache if profiling shows a hotspot.

        Returns 0 when no combat is active OR when the parse fails (defensive).
        """
        from eldritch_dm.gameplay.game_state_parser import parse_game_state  # noqa: PLC0415
        from eldritch_dm.mcp import tools as mcp_tools  # noqa: PLC0415

        try:
            raw = await mcp_tools.get_game_state(self.mcp)
            text = raw if isinstance(raw, str) else str(raw)
            return parse_game_state(text).round_number
        except Exception:  # noqa: BLE001
            return 0

    def get_channel_edit_budget(self, channel_id: str) -> ChannelEditBudget:
        """Return (or create) the per-channel ChannelEditBudget.

        Discord rate-limits embed edits to 5 per 5 seconds per channel.
        One budget instance is shared across all EmbedCoalescers for the
        same channel (e.g. room embed + combat embed during a transition).
        """
        if channel_id not in self._channel_edit_budgets:
            self._channel_edit_budgets[channel_id] = ChannelEditBudget(channel_id=channel_id)
        return self._channel_edit_budgets[channel_id]

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
          (e2) Register DynamicItem subclasses + rehydrate persistent views
          (e3) Phase 4: ChannelRateLimiter + BatchCoordinator + PartyModeOrchestrator
          (f) load cogs (Diagnostics, Lobby, Ingest, Exploration)
          (g) Phase 4: start orchestrator tasks for existing EXPLORATION/COMBAT sessions
          (h) sync app command tree
        """
        settings = self.settings

        # (a) Schema bootstrap — idempotent, safe to call multiple times
        await bootstrap(settings.eldritch_db_path)

        # (b) WriterQueue — serializes all DB writes
        self.writer_queue = WriterQueue(settings.eldritch_db_path)
        await self.writer_queue.start()

        # (c) Circuit breaker + MCP client
        self.circuit_breaker = CircuitBreaker(threshold=settings.omlx_circuit_breaker_threshold)
        # SAFETY-02 (G-4 / Phase 7 closure): build the debouncer alongside
        # the circuit breaker so @catch_circuit_open has both available the
        # first time any callback fires.
        self.dm_offline_debouncer = DMOfflineDebouncer()
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
        # G-2 (v1.0 audit closure): SanitizerAuditRepo for SAN-05.
        # ExplorationCog.DeclareActionModal reads this via
        # interaction.client.sanitizer_audit_repo and bridges it to
        # sanitize_player_input via make_async_audit_callback.
        self.sanitizer_audit_repo = SanitizerAuditRepo(
            settings.eldritch_db_path,
            self.writer_queue,
        )
        # SAFETY-01 (G-3 / Phase 7 closure): memoize the sanitizer audit
        # callback once so every modal-construction site reuses the same
        # callable. The callback closes over the running event loop and the
        # repo; per-call construction (the pre-Phase-7 pattern in
        # exploration.py) was redundant.
        self.sanitizer_audit_callback = make_async_audit_callback(
            self.sanitizer_audit_repo
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

        # (e3) Phase 4 gameplay subsystems
        self.rate_limiter = ChannelRateLimiter(
            min_interval_ms=settings.mcp_rate_limit_ms,
        )
        self.batch_coordinator = BatchCoordinator(
            window_seconds=float(settings.explore_batch_window_seconds),
        )

        # (e3b) Phase 5 Plan 01 — pc_classes + riposte_timers repos + MonsterDriver
        # Phase 8 (HOMEBREW-01): resolve homebrew eligibility set ONCE at startup
        # (D-29 / D-38). load_eligibility NEVER raises; on failure falls back to
        # DEFAULT_ELIGIBILITY (v1.0 RAW set). Stored on the bot so cogs/tests can
        # introspect the active set.
        self.eligibility_set = load_eligibility(settings)
        log.info("eligibility_loaded", count=len(self.eligibility_set))

        self.pc_classes = PCClassesRepo(db_path=settings.eldritch_db_path)
        self.riposte_timers_repo = RiposteTimerRepo(
            settings.eldritch_db_path, self.writer_queue
        )
        # Convenience alias used by RiposteButton.callback (interaction.client.riposte_timers)
        self.riposte_timers = self.riposte_timers_repo

        from eldritch_dm.bot.dynamic_items import RiposteButton  # noqa: PLC0415
        from eldritch_dm.gameplay.monster_driver_factory import (  # noqa: PLC0415
            make_monster_driver,
        )

        def _riposte_button_factory(timer_id: int, user_id: int) -> discord.ui.Item:
            return RiposteButton(timer_id=timer_id, user_id=user_id)

        async def _default_monster_state_provider(
            channel_id: str, campaign_name: str
        ) -> dict[str, Any]:
            """Default state provider: parse get_game_state.

            Plan 02 may replace this with the richer CombatCog state. For Plan 01
            we synthesize a minimal dict from the parser plus a roster lookup.
            """
            from eldritch_dm.gameplay.game_state_parser import (  # noqa: PLC0415
                parse_game_state,
            )
            from eldritch_dm.mcp import tools as mcp_tools  # noqa: PLC0415

            raw = await mcp_tools.get_game_state(self.mcp)
            text = raw if isinstance(raw, str) else str(raw)
            parsed = parse_game_state(text)
            # We don't yet have a fast (name → character_id, user_id) lookup;
            # caller (CombatCog) overrides this provider with a richer one.
            # Default: return an empty pcs list — driver will warn + next_turn.
            return {"round_number": parsed.round_number, "pcs": []}

        def _channel_resolver(channel_id: str) -> Any:
            try:
                return self.get_channel(int(channel_id))
            except (TypeError, ValueError):
                return None

        # Phase 10 D-52: factory dispatches between v1.0 random and smart
        # drivers based on MONSTER_DRIVER env var (default "smart"). The
        # smart driver needs an AsyncOpenAI client for the LLM oracle — we
        # build one lazily here using the same resolved ingest config so the
        # smart driver and the ingest pipeline talk to the same oMLX server.
        from openai import AsyncOpenAI  # noqa: PLC0415

        ingest_cfg = settings.resolve_ingest_config()
        # Reuse a pre-set client (test injection) if present, else build one.
        smart_openai_client = getattr(self, "openai_client", None) or AsyncOpenAI(
            base_url=ingest_cfg.endpoint, api_key=ingest_cfg.api_key
        )
        self.openai_client = smart_openai_client  # expose for ingest cog reuse

        self.monster_driver = make_monster_driver(
            mcp=self.mcp,
            rate_limiter=self.rate_limiter,
            pc_classes_repo=self.pc_classes,
            riposte_timers_repo=self.riposte_timers_repo,
            button_factory=_riposte_button_factory,
            state_provider=_default_monster_state_provider,
            channel_resolver=_channel_resolver,
            ttl_seconds=settings.riposte_ttl_seconds,
            eligibility_set=self.eligibility_set,  # Phase 8 D-38
            # Smart-driver-only kwargs — factory pops these for "random" mode
            openai_client=smart_openai_client,
            llm_model=ingest_cfg.model,
        )

        # (e3c) Phase 5 Plan 02 — shared SessionLocks + RiposteSweeper.
        # Order: AFTER rehydrate_persistent_views (e2/e3) so DynamicItems
        # are registered before any sweeper-triggered Discord interactions
        # could route. AFTER riposte_timers_repo construction (above).
        # BEFORE orchestrator (below) is purely organizational — they are
        # independent subsystems.
        self.session_locks = SessionLocks()
        self.riposte_sweeper = RiposteSweeper(
            repo=self.riposte_timers_repo,
            bot=self,
            session_locks=self.session_locks,
            log=get_logger("eldritch_dm.gameplay.riposte_sweeper"),
        )
        await self.riposte_sweeper.start()

        self.orchestrator = PartyModeOrchestrator(
            mcp=self.mcp,
            rate_limiter=self.rate_limiter,
            batch_coordinator=self.batch_coordinator,
            channel_sessions=self.channel_sessions_repo,
            monster_driver=self.monster_driver,
        )

        # (f) Load cogs
        await self.load_extension("eldritch_dm.bot.cogs.diagnostics")
        # Phase 3: LobbyCog (/start_game, /load_adventure, ReadyButton wiring)
        await self.load_extension("eldritch_dm.bot.cogs.lobby")
        # Phase 3: IngestCog — character upload via URL, file, and manual entry
        await self.load_extension("eldritch_dm.bot.cogs.ingest")
        # Phase 4: ExplorationCog — room embed lifecycle, declare-action UI
        await self.load_extension("eldritch_dm.bot.cogs.exploration")
        # Phase 4 Plan 02: CombatCog — combat embed lifecycle + turn-gated buttons
        await self.load_extension("eldritch_dm.bot.cogs.combat")

        # (g) Phase 4: Resume orchestrator tasks for any EXPLORATION/COMBAT sessions
        # that survived a bot restart. ExplorationCog must be loaded first (above)
        # so its callbacks are registered before we begin polling.
        try:
            active_rows = await self.channel_sessions_repo.list_active()
            resumed = 0
            for sess in active_rows:
                if sess.state in (ChannelState.EXPLORATION, ChannelState.COMBAT):
                    await self.orchestrator.start_orchestrator_for_channel(
                        channel_id=str(sess.channel_id),
                        campaign_name=sess.campaign_name,
                        session_id=sess.claudmaster_session_id or "",
                    )
                    resumed += 1
            if resumed:
                self._logger.info("orchestrator_sessions_resumed", count=resumed)
        except Exception:  # noqa: BLE001
            self._logger.exception("orchestrator_resume_error")
            # Non-fatal: bot connects normally; existing channels resume on next action

        # (h) Sync app command tree
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

        # Step 0a: Stop RiposteSweeper FIRST (Plan 02 / OPS-04 chain).
        # Rationale: pending mark_expired calls during shutdown need
        # session_locks alive (they are, while the sweeper drains). Stopping
        # the sweeper first means no half-finished iterations linger; the
        # remaining steps tear down repos + DB without the sweeper poking
        # them mid-shutdown. Plan 02 decision: cancel (not flush) for clean
        # shutdown semantics; pending rows survive across restart and get
        # cleaned up on the next bot's first sweep.
        if self.riposte_sweeper is not None:
            try:
                await self.riposte_sweeper.stop()
                self._logger.debug("riposte_sweeper_stopped")
            except Exception:  # noqa: BLE001
                self._logger.exception("riposte_sweeper_stop_error")

        # Step 0b: Stop PartyModeOrchestrator (cancel all per-channel polling tasks)
        if self.orchestrator is not None:
            try:
                await self.orchestrator.stop_all()
                self._logger.debug("orchestrator_stopped")
            except Exception:  # noqa: BLE001
                self._logger.exception("orchestrator_stop_error")

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
