---
phase: 02-discord-scaffold-persistent-views
plan: 01
subsystem: discord-bot
tags: [discord.py, commands.Bot, app_commands, structlog, sqlite, import-linter, asyncio]

# Dependency graph
requires:
  - phase: 01-mcp-client-local-state
    provides: WriterQueue, ChannelSessionRepo, MCPClient, CircuitBreaker, HealthCheck, bootstrap, configure_logging, Settings

provides:
  - EldritchBot(commands.Bot) subclass with setup_hook + close override
  - Process entrypoint: python -m eldritch_dm.bot
  - Diagnostics cog: /ping (MCP circuit state + endpoint) + /status (channel session readout), both ephemeral
  - conftest fixtures: bot_factory, running_bot, interaction_factory for downstream plans
  - import-linter contract: nothing outside bot/ may import from bot/

affects:
  - 02-02 (embeds + dynamic items use EldritchBot from this plan)
  - 02-03 (coalescer + rehydration extends setup_hook from this plan)
  - Phase 3-5 (all add cogs to EldritchBot; all tests use conftest fixtures)

# Tech tracking
tech-stack:
  added:
    - discord.py 2.7.1 (already pinned Phase 1; bot integration layer now live)
    - pytest-mock>=3.12,<4.0 (dev dep — mocker fixture for spy patterns)
    - syrupy>=4.6,<5.0 (dev dep — snapshot tests for Plan 02 embeds)
  patterns:
    - EldritchBot(commands.Bot) with Settings-injected ctor (no I/O in __init__)
    - setup_hook = boot subsystems sequentially; any exception is fatal (D-25 + issue #8210)
    - Defer-first discipline: every callback's first line is await interaction.response.defer(thinking=True, ephemeral=True)
    - Close override drains WriterQueue before super().close() (OPS-04 scaffolding)
    - MagicMock(spec=discord.Interaction) with explicit AsyncMock for nested attrs (RESEARCH Q2 recipe)

key-files:
  created:
    - src/eldritch_dm/bot/__init__.py
    - src/eldritch_dm/bot/__main__.py
    - src/eldritch_dm/bot/bot.py
    - src/eldritch_dm/bot/cogs/__init__.py
    - src/eldritch_dm/bot/cogs/diagnostics.py
    - tests/bot/conftest.py
    - tests/bot/test_cog_diagnostics.py
    - tests/bot/test_bot_lifecycle.py
  modified:
    - pyproject.toml (pytest-mock + syrupy dev deps; bot import-linter contract)

key-decisions:
  - "bootstrap() (async) is used in setup_hook rather than ensure_schema() — Phase 1 shipped bootstrap(), not ensure_schema()"
  - "setup_hook raises on failure — do NOT call bot.close() (issue #8210 pattern)"
  - "Intents.default() + message_content=False: security decision, bot cannot read raw messages/DMs (D-04)"
  - "dpytest deferred: officially caps at discord.py 2.6; unit tests use direct MagicMock/AsyncMock recipes (RESEARCH Q2)"
  - "syrupy added to dev deps now (declared for Plan 02 embed snapshots — avoid churn)"
  - "MCPClient base URL derived by stripping trailing /v1 from omlx_endpoint"
  - "Plan 03 TODOs: persistent_views rehydration placeholder, WriterQueue full drain timeout"

patterns-established:
  - "Bot lifecycle: __init__ (no I/O) -> setup_hook (boot all subsystems) -> close (ordered teardown)"
  - "Test isolation: bot_factory fixture wires real tmp DB + mocked tree.sync; no real Discord API"
  - "Cog structure: class Diagnostics(commands.Cog) + async def setup(bot) for load_extension compatibility"

requirements-completed: [BOT-01, OPS-04]

# Metrics
duration: 15min
completed: 2026-05-21
---

# Phase 2 Plan 01: Bot Scaffold Summary

**EldritchBot(commands.Bot) with Settings-driven setup_hook, /ping+/status diagnostics cog, process entrypoint, and lifecycle test harness wired to real SQLite**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-21T22:58:00Z
- **Completed:** 2026-05-21T23:13:00Z
- **Tasks:** 3 (Task 1: config; Task 2: TDD bot + cogs; Task 3: TDD lifecycle tests)
- **Files modified:** 9

## Accomplishments

- EldritchBot subclass with ordered setup_hook: schema bootstrap -> WriterQueue -> CircuitBreaker -> MCPClient -> HealthCheck -> ChannelSessionRepo -> load_extension -> tree.sync
- /ping: ephemeral circuit state + endpoint URL; /status: ephemeral channel session readout (D-09 defer-first on both)
- Graceful close(): stop health -> stop writer_queue -> aclose mcp -> super().close() (OPS-04 scaffolding; full drain timeout deferred to Plan 03)
- Conftest fixtures (bot_factory, running_bot, interaction_factory) ready for Plans 02/03 and Phases 3-5
- import-linter contract enforcing that nothing outside bot/ imports from bot/ — 5 contracts all KEPT

## Task Commits

1. **Task 1: Add dev deps + bot/ import-linter contract** - `dbe2884` (chore)
2. **Task 2 RED: Failing diagnostics cog tests** - `5019d1f` (test)
3. **Task 2 GREEN: EldritchBot + Diagnostics cog** - `71574e8` (feat)
4. **Task 2 CHORE: Process entrypoint** - `677c67d` (feat)
5. **Task 3: Bot lifecycle tests + conftest** - `15ea75b` (included in Phase 3 docs commit)

## Files Created/Modified

- `pyproject.toml` - Added pytest-mock + syrupy dev deps; added bot import-linter contract
- `src/eldritch_dm/bot/__init__.py` - Re-exports EldritchBot; __all__ = ["EldritchBot"]
- `src/eldritch_dm/bot/__main__.py` - Process entrypoint: configure_logging -> Settings -> EldritchBot -> bot.run(); exit code 2 on fatal failure
- `src/eldritch_dm/bot/bot.py` - EldritchBot class: Settings-driven ctor, setup_hook with ordered subsystem init, close() override
- `src/eldritch_dm/bot/cogs/__init__.py` - Empty module marking cogs as extensible subpackage
- `src/eldritch_dm/bot/cogs/diagnostics.py` - Diagnostics cog with /ping (circuit state, ephemeral) and /status (channel session, ephemeral)
- `tests/bot/conftest.py` - tmp_db_path, bot_settings, bot_factory, running_bot, interaction_factory fixtures
- `tests/bot/test_cog_diagnostics.py` - 5 tests: CLOSED/OPEN ping, no-session/active-session status, defer-first ordering
- `tests/bot/test_bot_lifecycle.py` - 6 tests: subsystems init, clean shutdown, fatal failure propagation, minimal intents, global/per-guild sync

## Decisions Made

- **bootstrap() not ensure_schema()**: Phase 1 shipped `bootstrap(db_path: str)` (async), not `ensure_schema`. Used as-is.
- **setup_hook failure pattern**: Raise, never call bot.close() from setup_hook (Discord.py issue #8210 anti-pattern documented in RESEARCH.md).
- **dpytest skipped**: dpytest officially caps at discord.py 2.6; mock-based testing is sufficient and more maintainable.
- **syrupy declared now**: Added to dev deps in Task 1 to avoid pyproject.toml churn when Plan 02 needs it.
- **MCPClient URL stripping**: omlx_endpoint includes /v1 suffix; MCPClient needs the base URL without it — strip /v1 in setup_hook.

## Deviations from Plan

### Auto-fixed Issues

None - plan executed with one minor interface adaptation (bootstrap() vs ensure_schema() — same function, different name).

## Known Stubs

- `bot.py:104` — `# Plan 03: rehydrate persistent_views here` — placeholder for DynamicItem registration; intentional per RESEARCH.md (add_dynamic_items alone is sufficient for restart correctness; no add_view needed)
- `bot.py:135` — `best-effort .stop()` for WriterQueue — full drain timeout (5s) deferred to Plan 03 per plan spec

Both stubs are documented deferred items, not implementation gaps. The bot's startup and shutdown are correct for Phase 2 scope.

## Issues Encountered

None — all 11 bot tests pass; all 177 Phase 1 tests still pass; lint-imports 5 contracts KEPT.

## Threat Surface Scan

All threat mitigations from the threat model applied:
- T-02-01: /ping ephemeral (thinking=True, ephemeral=True in defer + followup)
- T-02-02: /status ephemeral; dm20_party_token never included in output
- T-02-03: Intents.message_content=False confirmed in test_intents_are_minimal
- T-02-04: setup_hook failure is fatal — tested in test_setup_hook_failure_is_fatal
- T-02-05: structlog bound context (channel_id, user_id, command) on entry + exit in every callback

No new threat surface introduced beyond what was in the threat model.

## Next Phase Readiness

- Plan 02 (embeds + dynamic items) can proceed: EldritchBot is importable, bot_factory fixture available
- Plan 03 (coalescer + rehydration) needs bot.py to add DynamicItem registration + WriterQueue drain timeout — both marked with TODOs
- Phase 3 cog architecture is ready: `cogs/` is an extensible subpackage; load_extension pattern proven

---
*Phase: 02-discord-scaffold-persistent-views*
*Completed: 2026-05-21*
