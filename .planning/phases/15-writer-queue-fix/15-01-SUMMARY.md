---
phase: 15
plan: 01
requirements_completed: [HANG-01, HANG-02, HANG-03]
subsystem: tests/bot
tags: [test-isolation, sys.modules, discord.py, flake-fix]
requires: []
provides: [test-isolation-for-cog-modules]
affects: [tests/conftest.py, tests/bot/conftest.py]
tech_added: []
tech_patterns: [autouse-fixture-snapshot-restore]
key_files_created: []
key_files_modified:
  - tests/conftest.py
  - tests/bot/conftest.py
decisions:
  - "Snapshot/restore sys.modules entries for cog modules around every test via tests/conftest.py autouse fixture (suite-wide), instead of localizing to tests/bot/."
  - "Add bot.unload_extension() to bot_factory teardown for clean cog state, even though it is not strictly required for FLAKE-02 closure (snapshot/restore is what fixes the mock.patch resolution)."
  - "Reject all writer-queue rewrites — Phase 14 already neutralized the suspected hangs; phase 15 brief was based on a stale audit (per prior agent's halt-report)."
metrics:
  duration: ~3h
  tests_added: 0
  tests_modified: 2
also_closes: [FLAKE-02 (from v1.3 milestone, carried partial)]
completed: 2026-05-25
---

# Phase 15 Plan 01: FLAKE-02 Closure via Test-Isolation Patch Summary

Closed FLAKE-02 / HANG-03 by adding a suite-wide autouse fixture that snapshots and restores `sys.modules` entries for the five cog modules around every test, and by giving `bot_factory` an extension-unload + close teardown. The full pytest suite is now green (1244 passed, 17 skipped, 0 failed) across 2 consecutive runs.

## Diagnosis

The prior Phase 15 agent's halt-report (`15-HALT-REPORT.md`) correctly invalidated the v1.4 CONTEXT.md premise: HANG-01 and HANG-02 do not reproduce at HEAD (Phase 14's logging-polluter fix already cleared them). The remaining failure was FLAKE-02 / HANG-03 in `tests/integration/test_phase3_smoke.py`, which is **not a writer-queue bug**.

The actual mechanism (confirmed by inline diagnostic in this worktree):

1. **Collection time.** pytest collects `tests/integration/test_phase3_smoke.py`, which top-level imports `from eldritch_dm.bot.cogs.ingest import IngestCog` (line 40). `sys.modules["eldritch_dm.bot.cogs.ingest"]` points to MODULE_A. The test holds a class reference whose callbacks have `__globals__ → MODULE_A.__dict__`.

2. **A polluter runs.** Any test that constructs an `EldritchBot` and invokes `setup_hook()` triggers `await bot.load_extension("eldritch_dm.bot.cogs.ingest")`. discord.py's `_load_from_module_spec` does:

   ```python
   lib = importlib.util.module_from_spec(spec)
   sys.modules[key] = lib
   spec.loader.exec_module(lib)
   ```

   (`.venv/lib/python3.11/site-packages/discord/ext/commands/bot.py:957-962`)

   This **REPLACES** the existing `sys.modules` entry with a freshly imported MODULE_B. MODULE_A is orphaned, still referenced only by the phase3 test's `IngestCog` class.

3. **The victim runs.** Phase3 calls `mock.patch("eldritch_dm.bot.cogs.ingest.ingest", AsyncMock(...))`. mock.patch resolves the attribute via `sys.modules[...]`, which points to MODULE_B. The mock replaces MODULE_B.ingest. But the test's instantiated `IngestCog` callback resolves `ingest` through its `__globals__ → MODULE_A.__dict__`, where `ingest` is still the original `pipeline.ingest` function. The mock is bypassed, the real ingest runs, and `UnavailableOCRBackend` is raised because `ocrmac` is not installed in the test venv.

The halt-report's `unload_extension`-in-teardown hypothesis is necessary but not sufficient: `unload_extension` does `del sys.modules[name]`, which causes the next `mock.patch` to re-import a fresh MODULE_C — still not MODULE_A. The fix requires explicitly RESTORING MODULE_A.

Polluters confirmed empirically in this worktree:

- Any test calling `bot_factory()` (e.g. `test_setup_hook_initializes_subsystems`, `test_close_cleanly_shuts_down`, `test_writer_queue_drain_timeout`, etc.)
- Tests that bypass `bot_factory` and construct `EldritchBot` inline + call `setup_hook()` directly (e.g. `test_per_guild_sync_when_configured` in `test_bot_lifecycle.py`)

Because polluters exist both inside and outside `tests/bot/`, the fix must live at the suite-wide level.

## Fix

### `tests/conftest.py` — suite-wide autouse snapshot/restore

Added a `_COG_MODULES` tuple listing the five cog modules that `EldritchBot.setup_hook` loads, and an autouse function-scoped fixture `_restore_cog_modules_after_test` that captures their `sys.modules` entries before each test and restores them after. This puts MODULE_A back into `sys.modules` for the next test, so any subsequent `mock.patch("eldritch_dm.bot.cogs.ingest.ingest", ...)` resolves to the same dict the orphaned `IngestCog` class's `__globals__` points to.

### `tests/bot/conftest.py` — bot_factory teardown

Converted `bot_factory` from a sync fixture returning an async callable into a `@pytest_asyncio.fixture async` fixture that tracks every bot it constructs. In teardown it calls `await bot.unload_extension(name)` for every loaded extension and then `await bot.close()` if not already closed. This is best-effort cleanup of live cog state — strictly speaking the autouse module-restore is sufficient for FLAKE-02, but unloading is the correct discord.py contract and keeps cog `cog_unload` hooks running before the test teardown disposes of the loop.

## Verification

See `15-VERIFICATION.md` for full evidence. Headlines:

- **Polluter→victim** (`tests/bot/test_setup_hook.py` + `tests/bot/test_bot_lifecycle.py` + `tests/integration/test_phase3_smoke.py`): **23 passed in 5.5s.**
- **tests/bot/** in isolation: **373 passed, 5 skipped, 0 failed in 10.2s.**
- **Full suite** (`uv run pytest tests/ -q`): **1244 passed, 17 skipped, 0 failed in ~100s.** Run twice consecutively, both green.
- **Ruff:** `uv run ruff check tests/bot/conftest.py tests/conftest.py` → All checks passed.

## Decisions Made

1. **Snapshot/restore suite-wide, not tests/bot/-only.** Initial implementation localized the autouse fixture to `tests/bot/conftest.py`, but the full-suite run still failed because `test_per_guild_sync_when_configured` (in `tests/bot/test_bot_lifecycle.py`) constructs `EldritchBot` inline without `bot_factory`. Even when that fixture was caught by the tests/bot/-scoped autouse, OTHER test trees (integration, gameplay) also instantiate bots. Moving the autouse to `tests/conftest.py` covers the whole project at zero per-test cost.

2. **No writer-queue changes.** The prior agent's halt-report (`15-HALT-REPORT.md`) correctly identified the v1.4 CONTEXT.md premise as stale. WriterQueue at `src/eldritch_dm/persistence/connection.py:142-222` already has the sentinel + `asyncio.wait_for(timeout=5.0)` + cancel-fallback pattern the CONTEXT.md asked for; rewriting it would have risked regressing 177 passing tests for zero benefit.

3. **Keep `unload_extension` in `bot_factory` teardown** even though the autouse snapshot/restore is sufficient for FLAKE-02 closure. Reason: leaking cog instances across tests with live `cog_unload` hooks unattended can stack background tasks and confuse downstream debugging. Cheap insurance.

## Deviations from Plan

### Rule 1/3 — auto-fixes during implementation

**1. [Rule 3 — Blocker] Snapshot/restore initially missed the inline-bot polluter case.**

- **Found during:** Verification — full-suite run #1.
- **Issue:** Snapshot/restore as a fixture local to `bot_factory` only fired when a test used `bot_factory`. `test_per_guild_sync_when_configured` constructs `EldritchBot` inline without the fixture, so its `setup_hook` call swapped `sys.modules` and the restore never ran.
- **Fix:** Promoted the snapshot/restore to an autouse function-scope fixture in `tests/conftest.py`. Removed the duplicate inline implementation from `tests/bot/conftest.py`.

### Rule-4 candidates considered and rejected

- **Rewriting `IngestCog` to lazy-resolve `ingest`** (e.g., `from eldritch_dm.ingest import ingest as _ingest_factory` and call `_ingest_factory()` in the callback). Rejected: structural change to production code to work around a test-isolation issue; would not actually fix the underlying mechanism (mock.patch on the cog module would still hit a different dict).

- **Switching `mock.patch` target to `eldritch_dm.ingest.pipeline.ingest`.** Rejected by prior agent (see halt-report §"Hypothesis"). Empirically broke isolation tests because `eldritch_dm.ingest.__init__` re-exports `ingest` and the cog binds to the package-level name.

## Files Modified

- `tests/conftest.py` — added `_COG_MODULES` and `_restore_cog_modules_after_test` autouse fixture.
- `tests/bot/conftest.py` — converted `bot_factory` to `@pytest_asyncio.fixture async` with extension-unload + close teardown; removed unused `sys` import and duplicated `_COG_MODULES` constant.

## Known Stubs

None.

## Self-Check: PASSED

- `tests/conftest.py` contains `_restore_cog_modules_after_test` autouse fixture ✓
- `tests/bot/conftest.py` contains `unload_extension` teardown call ✓
- `.planning/REQUIREMENTS.md`: HANG-01/02/03 all ticked `[x]` ✓
- `.planning/milestones/v1.3-REQUIREMENTS.md`: FLAKE-02 back-ticked `[x]` with closure annotation ✓
- `.planning/phases/15-writer-queue-fix/15-01-PLAN.md`, `15-01-SUMMARY.md`, `15-VERIFICATION.md` all present ✓
- All commits will be recorded in the final completion message ✓
