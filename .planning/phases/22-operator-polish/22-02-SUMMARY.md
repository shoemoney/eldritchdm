---
phase: 22-operator-polish
plan: 22-02
requirements_completed: [OPQOL-02, OPQOL-03]
milestone: v1.6
requirements: [OPQOL-02, OPQOL-03]
key-files:
  created:
    - src/eldritch_dm/observability/budget_dm.py
    - tests/observability/test_budget_dm.py
    - tests/mcp/test_cache_invalidation_wire.py
  modified:
    - src/eldritch_dm/observability/degraded_mode.py
    - src/eldritch_dm/persistence/character_cache.py
    - src/eldritch_dm/mcp/cache.py
    - src/eldritch_dm/config/__init__.py
tags: [phase-22, opqol-02, opqol-03, budget-dm, schema-invalidation, fail-soft]
completed: 2026-05-25
  - OPQOL-02
  - OPQOL-03
---

# Phase 22 Plan 02: Discord DM-to-owner + Phase 16↔17 invalidation wire Summary

Discord DM-to-owner notifier (opt-in via `DISCORD_OWNER_ID`) wired to
budget breach + degraded-mode transitions; schema-version poller now wipes
both the MCP cache AND the character cache atomically, with partial-wipe
gracefully logged and continuing.

## What Shipped

### OPQOL-02 — Discord DM-to-owner

- **`DegradedModeState.add_notify_callback` / `remove_notify_callback`**
  - Callbacks fire on FIRST-trip and on recover (not on reason-change re-trips)
  - Dispatched OUTSIDE the state lock; per-callback try/except so one bad
    listener cannot break others or escape into the trip/recover path
- **`BudgetOwnerNotifier`** (`src/eldritch_dm/observability/budget_dm.py`)
  - `notify(event, reason)` sync + thread-safe (cross-thread schedule via
    `loop.call_soon_threadsafe`)
  - `notify_async(event, reason)` direct async send
  - `attach_to_degraded_mode()` / `detach_from_degraded_mode()` for state wiring
  - **`owner_id=None` → 100% no-op** (zero behavior change for non-opt-in)
  - **Per-event-type rate limit, default 1 DM/hr** (in-memory dict)
  - `discord.Forbidden` / `NotFound` / `HTTPException` / any `Exception`
    caught + logged; last-sent timestamp ONLY updated on successful send
- **`DISCORD_OWNER_ID` setting** (`src/eldritch_dm/config/__init__.py`)
  - Optional `int | None`, defaults to None
  - Aliased to `DISCORD_OWNER_ID` env var

### OPQOL-03 — Phase 16↔17 invalidation wire

- **`CharacterCacheRepo.purge_all()`** (`src/eldritch_dm/persistence/character_cache.py`)
  - Two-line alias for `invalidate(None)`; self-documenting callsite
- **`MCPCache.start_schema_version_poller(on_schema_change=...)`**
  - New optional async callback kwarg; invoked AFTER the MCP wipe on each
    detected version bump
  - **MCP wipe try/except**: if it fails, the callback STILL runs; logs
    `eldritch.cache.partial_wipe` with `mcp_cleared=False` + `primary_error_type`
  - **Callback try/except**: if it fails, logs `partial_wipe` with
    `mcp_cleared=True` + `secondary_error_type`
  - **Version tracking always advances** so a transient failure doesn't
    re-fire forever
  - Backward compatible: default `on_schema_change=None` preserves existing
    behavior; pre-existing Phase 16 tests pass unchanged

### Test Surface

- **10 BudgetOwnerNotifier tests** (`tests/observability/test_budget_dm.py`)
  - owner-id=None no-op, DM-per-event-type, per-event rate limit,
    bucket isolation, clock-advance unblocks, Forbidden swallowed
    (bucket NOT burned on failure), generic Exception swallowed,
    attach/detach degraded-mode wiring
- **4 invalidation-wire tests** (`tests/mcp/test_cache_invalidation_wire.py`)
  - both wiped on schema change; character-cache fails → MCP cleared + log;
    MCP fails → character cleared + log; no-callback default unchanged
- Total: **14 new tests** (Plan 22-02 alone) — combined with Plan 22-01's
  9 tests = **23 new tests for Phase 22**

## Test Results

- New: `tests/observability/test_budget_dm.py` 10 passed
- New: `tests/mcp/test_cache_invalidation_wire.py` 4 passed
- Regression: full `tests/mcp + tests/observability + tests/persistence +
  tests/gameplay/test_eligibility_*` — **481 passed, 2 skipped, 0 failed**
- `ruff check`: clean across all modified + new files
- `lint-imports`: 8/8 contracts kept

## Deviations from Plan

### 1. [Rule 1 - Bug] structlog `event` kwarg collision

- **Found during:** Task 3 test run
- **Issue:** structlog's `_make_filtering_bound_logger.make_method` reserves
  the kwarg `event` as the event-name positional. Passing `event=event` from
  both budget_dm.py and degraded_mode.py raised
  `TypeError: meth() got multiple values for argument 'event'`.
- **Fix:** Renamed structlog field to `event_type=` in all affected log
  calls in `src/eldritch_dm/observability/budget_dm.py` and
  `src/eldritch_dm/observability/degraded_mode.py`. The semantic event-name
  string is still embedded in the message itself.
- **Files modified:** budget_dm.py, degraded_mode.py
- **Commit:** eb49a73

### 2. Reconciliation: partial-wipe acceptance

- **Found during:** Plan-write time
- **Issue:** `.planning/REQUIREMENTS.md` line 62 says "atomic — partial wipes
  are forbidden", but `22-CONTEXT.md` D-171/172 + the objective explicitly
  allow partial-wipe with `eldritch.cache.partial_wipe` log + continue.
- **Resolution:** Followed the newer CONTEXT / objective decision (caches
  are independent; partial-wipe is honest failure-mode disclosure, not a
  catastrophic invariant violation). Surfaced in `22-VERIFICATION.md`.
- **No code change required** — flagged for human review.

### 3. Caplog → capsys for structlog assertions

- **Found during:** Test 7
- **Issue:** structlog routes through stdout, not stdlib logging — `caplog`
  never captures it.
- **Fix:** Tests use `capsys.readouterr()` and assert against `captured.out`.
- **Commit:** 005532b

## v1.6 Scope Notes

`BudgetOwnerNotifier` is NOT wired into `bot.py`. The notifier is a
self-contained library that BudgetEvaluator / DegradedModeState consumers
can compose; bot integration is intentionally out of scope for OPQOL-02
because (a) BudgetEvaluator itself is not yet bot-wired in Phase 13
(separate deferral), and (b) the success criterion specifies a "class
consuming events", not bot wiring. Future integration: instantiate
`BudgetOwnerNotifier(bot=bot, owner_id=settings.discord_owner_id)` once in
`setup_hook` and call `.attach_to_degraded_mode()`.

## Self-Check

- [x] `src/eldritch_dm/observability/budget_dm.py` created
- [x] `src/eldritch_dm/observability/degraded_mode.py` has notify-callback API
- [x] `src/eldritch_dm/mcp/cache.py` accepts `on_schema_change` kwarg
- [x] `src/eldritch_dm/persistence/character_cache.py` has `purge_all`
- [x] `src/eldritch_dm/config/__init__.py` exposes `DISCORD_OWNER_ID`
- [x] `tests/observability/test_budget_dm.py` exists with 10 tests
- [x] `tests/mcp/test_cache_invalidation_wire.py` exists with 4 tests
- [x] 22-02 commits: 1e00bc9 (degraded_mode callbacks), 285cb1e (budget_dm),
  eb49a73 (tests + structlog fix), d83c163 (settings), 9b656a1 (purge_all),
  e394316 (schema-poller callback), 005532b (wire tests)

## Self-Check: PASSED
