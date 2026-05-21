---
phase: 02-discord-scaffold-persistent-views
subsystem: discord-bot
tags: [discord.py, persistent-views, DynamicItem, embed-coalescer, lint, ast, restart-drill, graceful-shutdown]

# Dependency graph
requires:
  - phase: 01-mcp-client-local-state
    provides: WriterQueue, ChannelSessionRepo, PersistentViewRepo, MCPClient, CircuitBreaker, HealthCheck, bootstrap, Settings

provides:
  - "EldritchBot(commands.Bot) with ordered setup_hook + OPS-04 graceful shutdown"
  - "/ping + /status diagnostics cog (ephemeral, defer-first)"
  - "4 embed renderers: lobby_embed, room_embed, combat_embed, character_confirm_embed"
  - "4 DynamicItem subclasses: ReadyButton, DeclareActionButton, EndTurnButton, RiposteButton"
  - "EmbedCoalescer: ≤1 edit/sec/message with latest-value semantics"
  - "setup_hook.py: rehydrate_persistent_views wired; add_dynamic_items registered"
  - "EDM001: AST-based defer-discipline lint rule + pre-commit hook"
  - "Kill-and-restart drill test: proves BOT-08 end-to-end"
  - "send_warning helper with WarningKind enum"

affects: [phase-03-lobby-character-ingest, phase-04-exploration-combat, phase-05-reactions-ops]

# Tech tracking
tech-stack:
  added:
    - discord.py 2.7.1 (integration layer now live)
    - pytest-mock>=3.12,<4.0 (mocker fixture)
    - syrupy>=4.6,<5.0 (snapshot tests)
  patterns:
    - "EldritchBot(commands.Bot): Settings-driven ctor (no I/O), setup_hook (fatal on error), close (ordered teardown)"
    - "Defer-first discipline (D-09): every callback's first line is await interaction.response.defer(...)"
    - "discord.ui.DynamicItem[discord.ui.Button] with class-level template= regex for persistent buttons"
    - "asyncio.Event + latest-value slot for EmbedCoalescer (not Queue maxsize=1)"
    - "Pure-function embed renderers returning discord.Embed"
    - "AST-based pre-commit lint hook (no Rust toolchain)"
    - "RUN_INTEGRATION=1 gate for slow integration tests"
    - "ChannelEditBudget stub for Phase 4 per-channel rate limiting"

key-files:
  created:
    - src/eldritch_dm/bot/__init__.py
    - src/eldritch_dm/bot/__main__.py
    - src/eldritch_dm/bot/bot.py
    - src/eldritch_dm/bot/cogs/__init__.py
    - src/eldritch_dm/bot/cogs/diagnostics.py
    - src/eldritch_dm/bot/embeds.py
    - src/eldritch_dm/bot/dynamic_items.py
    - src/eldritch_dm/bot/warnings.py
    - src/eldritch_dm/bot/coalescer.py
    - src/eldritch_dm/bot/setup_hook.py
    - src/eldritch_dm/lint/__init__.py
    - src/eldritch_dm/lint/edm001.py
    - tools/lint_defer_discipline.py
    - tests/bot/conftest.py (+ extended bot_factory)
    - tests/bot/test_bot_lifecycle.py
    - tests/bot/test_cog_diagnostics.py
    - tests/bot/test_embeds.py
    - tests/bot/test_dynamic_items.py
    - tests/bot/test_warnings.py
    - tests/bot/test_coalescer.py
    - tests/bot/test_setup_hook.py
    - tests/bot/test_defer_discipline.py
    - tests/bot/test_restart_drill.py
    - tests/bot/_edm001_corpus/good/*.py (6 files)
    - tests/bot/_edm001_corpus/bad/*.py (5 files)
  modified:
    - pyproject.toml
    - .pre-commit-config.yaml

key-decisions:
  - "add_dynamic_items alone is sufficient for DynamicItem dispatch; add_view calls are audit-layer only (RESEARCH.md Pitfall 1)"
  - "setup_hook raises on failure — never bot.close() from setup_hook (issue #8210 anti-pattern)"
  - "asyncio.Event + latest-value slot over Queue(maxsize=1) for coalescer"
  - "AST-based EDM001 hook over ruff Rust plugin — 160 lines Python vs entire Rust toolchain"
  - "dpytest deferred: officially caps at discord.py 2.6; mock-based testing used throughout"
  - "ChannelEditBudget stub in coalescer.py for Phase 4 channel-scoped rate limiting"
  - "RUN_INTEGRATION=1 gate for restart-drill (slow I/O tests)"

requirements-completed: [BOT-01, BOT-02, BOT-03, BOT-04, BOT-05, BOT-06, BOT-07, BOT-08, OPS-04]

# Metrics
duration: 120min (across 3 plans)
completed: 2026-05-21
---

# Phase 2: Discord Scaffold + Persistent Views — SUMMARY

**Complete discord.py 2.7.1 bot with DynamicItem persistent buttons, embed coalescer, defer-discipline lint, kill-and-restart drill, and OPS-04 graceful shutdown — 9 requirements satisfied across 3 plans.**

## Phase Success Criteria (from ROADMAP.md)

- [x] BOT-01: discord.py 2.7.1 EldritchBot with /ping + /status slash command tree
- [x] BOT-02: EDM001 lint rule enforced in pre-commit + CI; violations fail build
- [x] BOT-03: 4 embed renderers (lobby, room, combat, character_confirm) with snapshot tests
- [x] BOT-04: DynamicItem subclasses (4 kinds) with regex custom_id templates
- [x] BOT-05: setup_hook rehydrates persistent_views; add_dynamic_items registered
- [x] BOT-06: EmbedCoalescer enforces ≤1 edit/sec/message with latest-value semantics
- [x] BOT-07: send_warning helper with WarningKind enum (5 kinds, ephemeral)
- [x] BOT-08: Kill-and-restart drill passes; persistent buttons functional after restart
- [x] OPS-04: bot.close() cancels health, drains WriterQueue (5s timeout), closes MCP, closes gateway

## Performance

- **Duration:** ~120 min (all 3 plans combined)
- **Plans:** 3/3 complete
- **Total tasks:** 9
- **Total files created:** 28+
- **Total files modified:** 4

## Plan Summaries

### Plan 01: Bot Scaffold
- EldritchBot(commands.Bot) with ordered setup_hook
- /ping (MCP circuit state) + /status (channel session)
- Process entrypoint __main__.py
- conftest fixtures (bot_factory, running_bot, interaction_factory)
- import-linter contract: nothing outside bot/ imports from bot/
- Requirements: BOT-01, OPS-04 (scaffolding)

### Plan 02: Embeds and Views
- 4 pure-function embed renderers with snapshot tests
- 4 DynamicItem subclasses with regex custom_id templates
- DYNAMIC_ITEM_CLASSES tuple for setup_hook
- send_warning helper with WarningKind enum (5 kinds)
- Requirements: BOT-03, BOT-04, BOT-07

### Plan 03: Coalescer + Rehydration + Restart Drill (this plan)
- EmbedCoalescer: asyncio.Event + latest-value slot, rate_limit_seconds injectable
- setup_hook.py: rehydrate_persistent_views, build_view_for_row (testable in isolation)
- OPS-04 tightened: asyncio.wait_for(writer_queue.stop(), timeout=5.0)
- EDM001: 160-line AST checker, pre-commit hook wired
- Kill-and-restart drill: bot_a seeds DB, bot_b reboots same DB, both dispatch correctly
- Requirements: BOT-02, BOT-05, BOT-06, BOT-08, OPS-04

## Test Counts

Phase 2 added 107 new tests to Phase 1's 177-test baseline:
- Plan 01: 11 bot tests (6 lifecycle + 5 diagnostics cog)
- Plan 02: 34 bot tests (16 embeds + 10 dynamic items + 8 warnings)
- Plan 03: 31 bot tests (8 coalescer + 9 setup_hook + 12 EDM001 + 2 restart drill)
- Plus 2 integration tests gated behind RUN_INTEGRATION=1

**Total suite: 284 passed, 4 skipped** (without RUN_INTEGRATION; RUN_INTEGRATION=1 adds 1 pass + 1 xfail)

## Patterns Established for Phases 3-5

| Pattern | Established In | Used By |
|---------|---------------|---------|
| `EldritchBot(commands.Bot)` + `cogs/<name>.py` with `setup(bot)` | Plan 01 | Phases 3-5 (lobby, combat, riposte cogs) |
| `DynamicItem[Button]` with `template=re.compile(...)` | Plan 02 | Phase 3 (ReadyButton real handler), Phase 4 (Declare/EndTurn), Phase 5 (Riposte) |
| `EmbedCoalescer(message)` per-message usage | Plan 03 | Phase 4 (combat embeds), Phase 5 (riposte timer embeds) |
| `send_warning(interaction, WarningKind.*, **ctx)` | Plan 02 | Phase 4 (NOT_YOUR_TURN, DM_OFFLINE), Phase 5 (RIPOSTE_EXPIRED) |
| `EDM001` lint + `# noqa: EDM001 — <reason>` waiver | Plan 03 | Every Phase 3-5 cog |
| `RUN_INTEGRATION=1` gate for slow integration tests | Plan 03 | Phase 4/5 multi-session drill tests |

## Open Items for Phases 3-5

| Item | Phase | Notes |
|------|-------|-------|
| ReadyButton.callback: real lobby logic | Phase 3 | Currently Phase 2 stub (D-23) |
| DeclareActionButton.callback: exploration intent | Phase 4 | Currently Phase 2 stub (D-23) |
| EndTurnButton.callback: advance turn order | Phase 4 | Currently Phase 2 stub (D-23) |
| RiposteButton.callback: process riposte | Phase 5 | Currently Phase 2 stub (D-23) |
| ChannelEditBudget: per-channel rate limiter | Phase 4 | Stub class in coalescer.py; Phase 4 implements token-bucket |
| Riposte cleanup on restart: expired timer sweep | Phase 5 | test_expired_riposte_cleanup_on_restart xfail guards this |

## Deviations from Plan

**Plan 01:**
- `bootstrap()` used instead of `ensure_schema()` (same function, different name)
- WriterQueue full drain timeout deferred to Plan 03 per plan spec (no actual deviation)

**Plan 02:**
- syrupy declared in Plan 01 to avoid churn; hand-rolled JSON compare for embed snapshots
- dpytest skipped (officially caps at discord.py 2.6)

**Plan 03:**
- [Rule 1 - Bug] Test rate-limit expected sleep value fixed (clock sequence mismatch)
- [Rule 1 - Bug] Test happy-path channel IDs fixed from "ch-A"/"ch-B" to numeric "111"/"222"

## Security Notes

All threat model mitigations applied across Phase 2:
- T-02-12: build_view_for_row returns None on unknown view_class (never executes arbitrary class names)
- T-02-13: EmbedCoalescer rate-limit at 1.0s/edit per message; transient 429 loops without abandon
- T-02-14: setup_hook propagates DB errors (D-25 — bot never connects half-rehydrated)
- T-02-15: EDM001 enforced in pre-commit + CI — violations cannot reach main
- T-02-16: asyncio.wait_for(timeout=5.0) on writer_queue.stop — bot.close() always returns
- T-02-17: Accepted for Phase 2 — stub callbacks have no authorization; Phase 4 will add user_id gating

---

*Phase 2 Completed: 2026-05-21*
*Plans: 3/3*
*Requirements: BOT-01..BOT-08, OPS-04 all satisfied*
