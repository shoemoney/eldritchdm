---
phase: 02-discord-scaffold-persistent-views
plan: "03"
subsystem: discord-bot
tags: [asyncio, discord.py, persistent-views, rate-limiting, lint, ast, restart-drill, graceful-shutdown]

# Dependency graph
requires:
  - phase: 02-discord-scaffold-persistent-views/01
    provides: EldritchBot, /ping, /status, __main__ entrypoint
  - phase: 02-discord-scaffold-persistent-views/02
    provides: embed renderers, DynamicItem subclasses (4 classes), DYNAMIC_ITEM_CLASSES tuple, warnings helper

provides:
  - "EmbedCoalescer: per-message rate-limited update queue (asyncio.Event + latest-value slot)"
  - "setup_hook.py: rehydrate_persistent_views + build_view_for_row helpers (testable in isolation)"
  - "bot.close() OPS-04: cancels health, drains WriterQueue (5s timeout), closes MCP, closes gateway"
  - "EDM001: AST-based defer-discipline lint rule for Discord interaction callbacks"
  - "EDM001 wired into .pre-commit-config.yaml"
  - "Restart drill test (BOT-08): proves persistent buttons survive kill-and-restart"

affects: [phase-03-lobby-character-ingest, phase-04-exploration-combat, phase-05-reactions-ops]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "asyncio.Event + latest-value slot for coalescer (not Queue maxsize=1)"
    - "setup_hook extracted into testable module (setup_hook.py)"
    - "AST-based pre-commit lint hook (no Rust toolchain required)"
    - "RUN_INTEGRATION=1 gate for restart-drill integration tests"
    - "asyncio.wait_for(stop(), timeout=5.0) for graceful shutdown with bounded timeout"

key-files:
  created:
    - src/eldritch_dm/bot/coalescer.py
    - src/eldritch_dm/bot/setup_hook.py
    - src/eldritch_dm/lint/__init__.py
    - src/eldritch_dm/lint/edm001.py
    - tools/lint_defer_discipline.py
    - tests/bot/test_coalescer.py
    - tests/bot/test_setup_hook.py
    - tests/bot/test_defer_discipline.py
    - tests/bot/test_restart_drill.py
    - tests/bot/_edm001_corpus/good/*.py (6 files)
    - tests/bot/_edm001_corpus/bad/*.py (5 files)
  modified:
    - src/eldritch_dm/bot/bot.py
    - tests/bot/conftest.py
    - .pre-commit-config.yaml

key-decisions:
  - "asyncio.Event + latest-value slot over Queue(maxsize=1) — race-free, non-blocking for producers (RESEARCH.md Pattern 4)"
  - "AST-based EDM001 hook over ruff Rust plugin — 160 lines Python vs entire Rust toolchain setup"
  - "setup_hook.py extracted separately for testability — rehydrate_persistent_views callable standalone"
  - "add_dynamic_items is sufficient for DynamicItem dispatch; add_view calls are audit-layer only (RESEARCH.md Pitfall 1)"
  - "bot.close() uses asyncio.wait_for(timeout=5.0) — T-02-16 timeout guard; shutdown always continues"
  - "Restart drill gated behind RUN_INTEGRATION=1 — avoids slow I/O in fast unit test runs"

requirements-completed: [BOT-02, BOT-05, BOT-06, BOT-08, OPS-04]

# Metrics
duration: 90min
completed: 2026-05-21
---

# Phase 02, Plan 03: Coalescer + Rehydration + Restart Drill Summary

**EmbedCoalescer (≤1 edit/sec/message), persistent-view rehydration wired into setup_hook, EDM001 defer-discipline AST lint rule, kill-and-restart drill, and OPS-04 graceful shutdown — closing out Phase 2.**

## Performance

- **Duration:** ~90 min
- **Started:** 2026-05-21
- **Completed:** 2026-05-21
- **Tasks:** 4/4
- **Files modified:** 13 (3 modified, 10 new)

## Accomplishments

- EmbedCoalescer: prevents Phase 4 combat from 429-rate-limiting Discord; asyncio.Event + latest-value slot pattern is race-free and non-blocking; 8 deterministic tests with fake clock/sleep
- setup_hook.py: rehydrate_persistent_views + build_view_for_row are fully testable in isolation; bot.close() drains WriterQueue with 5s timeout (OPS-04 / T-02-16)
- EDM001 lint: AST-based pre-commit hook; 11-item corpus (6 good, 5 bad); wired into .pre-commit-config.yaml; `python -m eldritch_dm.lint.edm001 src/eldritch_dm/bot` exits 0 on live codebase
- Restart drill: EndTurnButton dispatches correctly after bot_a kill + bot_b fresh start from same DB; gated behind RUN_INTEGRATION=1

## Task Commits

1. **Task 1: EmbedCoalescer RED** - `e771c66` (test)
2. **Task 1: EmbedCoalescer GREEN** - `202b39b` (feat)
3. **Task 2: setup_hook RED** - `9602d59` (test)
4. **Task 2: setup_hook GREEN** - `74e1c47` (feat)
5. **Task 3: EDM001 corpus RED** - `0ff03e5` (test)
6. **Task 3: EDM001 GREEN** - `33af2b8` (feat)
7. **Task 3: pre-commit CHORE** - `d9b0de6` (chore)
8. **Task 4: Restart drill** - `266cf4b` (test)

## Files Created/Modified

- `src/eldritch_dm/bot/coalescer.py` - EmbedCoalescer + ChannelEditBudget stub for Phase 4
- `src/eldritch_dm/bot/setup_hook.py` - build_view_for_row + rehydrate_persistent_views
- `src/eldritch_dm/bot/bot.py` - wired add_dynamic_items, rehydrate, OPS-04 shutdown
- `src/eldritch_dm/lint/__init__.py` - lint package
- `src/eldritch_dm/lint/edm001.py` - 160-line AST checker for defer-discipline
- `tools/lint_defer_discipline.py` - thin wrapper script
- `tests/bot/test_coalescer.py` - 8 coalescer tests with fake clock/sleep
- `tests/bot/test_setup_hook.py` - 9 setup_hook + shutdown tests
- `tests/bot/test_defer_discipline.py` - 12 EDM001 corpus + real-codebase tests
- `tests/bot/test_restart_drill.py` - 2 integration tests (gated RUN_INTEGRATION=1)
- `tests/bot/conftest.py` - extended bot_factory with eldritch_db_path override
- `tests/bot/_edm001_corpus/good/*.py` - 6 good corpus fixtures
- `tests/bot/_edm001_corpus/bad/*.py` - 5 bad corpus fixtures
- `.pre-commit-config.yaml` - added EDM001 local hook

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test 2 (rate-limit) had incorrect expected sleep value**
- **Found during:** Task 1 GREEN
- **Issue:** Test expected `sleep(0.5)` but implementation correctly computed `sleep(0.7)` because `_last_edit_t` was set to clock value at first edit time. The test's clock wasn't advancing between first and second call.
- **Fix:** Fixed the fake clock to return different values at different call counts, correcting the expected sleep to 0.7s
- **Files modified:** `tests/bot/test_coalescer.py`

**2. [Rule 1 - Bug] Test 3 (happy path rehydration) used non-numeric channel IDs**
- **Found during:** Task 2 GREEN
- **Issue:** Test used `"ch-A"`, `"ch-B"` as channel_ids, which don't match `\d+` in DynamicItem regex patterns
- **Fix:** Changed to numeric `"111"`, `"222"` channel IDs matching real Discord snowflake format
- **Files modified:** `tests/bot/test_setup_hook.py`

## Known Stubs

- `ChannelEditBudget` in `coalescer.py`: stub class (line 50); Phase 4 will implement token-bucket semaphore for per-channel rate limiting (RESEARCH.md Pitfall 4)
- All 4 DynamicItem callbacks (`ReadyButton.callback`, etc.) in `dynamic_items.py`: Phase 2 stubs (D-23); real handlers in Phases 3-5

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced in this plan. EDM001 lint rule runs read-only AST analysis.

## Self-Check: PASSED

Files exist:
- src/eldritch_dm/bot/coalescer.py — FOUND
- src/eldritch_dm/bot/setup_hook.py — FOUND
- src/eldritch_dm/lint/edm001.py — FOUND
- tests/bot/test_coalescer.py — FOUND
- tests/bot/test_setup_hook.py — FOUND
- tests/bot/test_defer_discipline.py — FOUND
- tests/bot/test_restart_drill.py — FOUND

Commits exist: e771c66, 202b39b, 9602d59, 74e1c47, 0ff03e5, 33af2b8, d9b0de6, 266cf4b — FOUND

Test counts: 284 passed, 4 skipped (RUN_INTEGRATION and RUN_STRESS gated) — GREEN
