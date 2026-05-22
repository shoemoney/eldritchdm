---
phase: 05-reactions-self-host-polish
plan: 02
subsystem: combat
tags: [reactions, riposte, sweeper, asyncio-lock, restart-survival, ops-01, combat-11]

# Dependency graph
requires:
  - phase: 05-reactions-self-host-polish
    plan: 01
    provides: gameplay/reactions.py (with PLAN-02-LOCK-SEAM marker), RiposteTimerRepo (list_pending, mark_consumed_with_round), RiposteButton DynamicItem (promoted callback), schema with consumed_in_round + idx_riposte_pending_deadline
  - phase: 04-gameplay-exploration-combat
    provides: PartyModeOrchestrator (concurrent-with-sweeper subsystem), bot.setup_hook structure for OPS-04 chain
  - phase: 02-discord-scaffold-persistent-views
    provides: rehydrate_persistent_views helper (Plan 02 sweeper starts AFTER)
  - phase: 01-mcp-client-local-state
    provides: WriterQueue + RiposteTimer model + bootstrap
provides:
  - SessionLocks — namespaced per-channel asyncio.Lock registry (gameplay/session_locks.py)
  - RiposteSweeper — RESEARCH Pattern 4 background task (gameplay/riposte_sweeper.py)
  - Conditional mark_expired SQL (WHERE status='pending') — belt-and-suspenders idempotence
  - handle_riposte_click wrapped in shared SessionLocks lock — click-vs-sweeper race eliminated
  - EldritchBot.setup_hook starts sweeper AFTER rehydration; close() stops sweeper FIRST in OPS-04 chain
  - OPS-01 resume drill (tests/integration/test_riposte_restart.py) — 6 tests proving COMBAT-11
affects: [05-self-host-polish-and-closure (Plan 03 may now wrap closure work safely)]

# Tech tracking
tech-stack:
  added: []  # zero new pip dependencies — stdlib asyncio, contextlib, datetime
  patterns:
    - "Namespaced asyncio.Lock registry: same (namespace, channel_id) → same Lock identity; concurrent creation safe via internal _guard"
    - "Shared-lock pattern at race seams: both producer (sweeper) and consumer (click) acquire the SAME lock"
    - "Conditional UPDATE WHERE status='pending' as belt-and-suspenders against any lock failure"
    - "Injectable clock+sleep on background tasks for deterministic tests (precedent: Phase 4 test_rate_limit.py)"
    - "OPS-04 chain: sweeper.stop() FIRST (before orchestrator, health, writer_queue, mcp, super.close)"
    - "Per-row sweeper iteration uses lock_for context manager — no manual acquire/release pairs"

key-files:
  created:
    - src/eldritch_dm/gameplay/session_locks.py
    - src/eldritch_dm/gameplay/riposte_sweeper.py
    - tests/gameplay/test_session_locks.py
    - tests/gameplay/test_riposte_sweeper.py
    - tests/integration/test_riposte_restart.py
  modified:
    - src/eldritch_dm/gameplay/reactions.py
    - src/eldritch_dm/bot/bot.py
    - src/eldritch_dm/bot/dynamic_items.py
    - src/eldritch_dm/persistence/riposte_timers_repo.py
    - tests/gameplay/test_reactions.py
    - tests/gameplay/test_riposte_callback.py
    - tests/persistence/test_riposte_timers_repo.py

# Key decisions
decisions:
  - D-A: SessionLocks lives under gameplay/ (NOT bot/) — import-linter "gameplay must not import bot" forbids the bot-located alternative. Plan frontmatter recommended this in the verification.risks section; adopted. Frontmatter still lists src/eldritch_dm/bot/session_locks.py — semantically a gameplay primitive lives in gameplay/.
  - D-B: Sweeper.stop() CANCELS, does not flush in-flight mark_expired calls. Rationale: clean shutdown semantics; pending rows survive across restart and get cleaned up on the next bot's first sweep (proven by test_expired_timer_cleaned_on_restart). Module docstring documents.
  - D-C: mark_expired SQL is now conditional (WHERE id=? AND status='pending'). Belt-and-suspenders correctness against any lock failure — race-loser's UPDATE becomes a 0-row no-op. Persistence-level test confirms (test_mark_expired_conditional_on_pending).
  - D-D: handle_riposte_click does TWO repo.get() calls — pre-lock (to discover channel_id, since the lock key is per-channel) and under-lock (authoritative status read). The under-lock re-read catches the case where the sweeper flipped status between our initial read and acquiring the lock. Updated Plan 01's test fixture to provide 4 .get() returns for 2 concurrent clicks.
  - D-E: Discord message delete moved OUTSIDE the lock (post-lock) on the success path. HTTP latency must not stall click-vs-sweeper serialization. Lock window: 1× DB read + 1× DB write. Discord HTTP: outside lock. Late-click delete kept inside lock for simplicity (rare path).
  - D-F: setup_hook ordering — sweeper.start() comes AFTER rehydrate_persistent_views in bot.py (DynamicItems registered first, so any sweeper-routed Discord interactions have somewhere to dispatch). Asserted by test_setup_hook_orders_sweeper_after_rehydration via source-inspection.
  - D-G: Sweeper wake-up logs at INFO level on start/stop only — per-iteration "woken" is DEBUG. Avoids log spam in long-running self-host. Documented in riposte_sweeper.py module docstring.

# Metrics
metrics:
  duration_minutes: 35  # commit-to-commit
  tasks: 2
  files_created: 5
  files_modified: 7
  tests_added: 28  # 7 session_locks + 11 sweeper + 2 reactions marker + 2 callback Plan-02 + 1 persistence + 6 OPS-01 = 29 net (-1 from old marker test replaced)
  tests_total: 826  # was 798 at start of Plan 02
  completed: "2026-05-22"
---

# Phase 5 Plan 02: Sweeper + Restart-Survival Summary

Close the restart-survival half of COMBAT-09/10/11 by shipping a deadline-driven RiposteSweeper background task, a shared per-channel asyncio.Lock registry that eliminates the click-vs-sweeper race, and the OPS-01 resume drill that proves the reaction system survives bot kill.

## What Shipped

**Two atomic tasks**, two commits, 28 new net tests, zero new pip dependencies.

### Task 1 — SessionLocks + RiposteSweeper + lock-seam plug-in
`7dd1bcc feat(05-02): SessionLocks + RiposteSweeper + replace PLAN-02-LOCK-SEAM`

- **`src/eldritch_dm/gameplay/session_locks.py`** (95 LOC) — Namespaced per-channel asyncio.Lock registry. `SessionLocks().acquire("riposte", channel_id)` returns the same Lock instance for the same key (identity check via `is`). `lock_for(...)` is the context-manager helper. 100 concurrent `acquire()` calls for the same key yield exactly one Lock (verified). Internal `_guard` serializes dict mutation.
- **`src/eldritch_dm/gameplay/riposte_sweeper.py`** (185 LOC) — RESEARCH Pattern 4 implementation. Loops on `repo.list_pending()`; for each past-deadline row: `async with session_locks.lock_for("riposte", row.channel_id)` → `repo.mark_expired(row.id)` → best-effort `bot.get_channel().fetch_message().delete()`. Sleeps `max(min_sleep_s, min(default_sleep_s, next_deadline - now))`. Injectable clock+sleep for deterministic tests. `discord.NotFound | Forbidden | HTTPException` caught + logged. `start()` / `stop()` lifecycle suppresses `CancelledError` cleanly.
- **`src/eldritch_dm/gameplay/reactions.py`** — PLAN-02-LOCK-SEAM marker REPLACED. `handle_riposte_click` now takes `session_locks: SessionLocks` kwarg and wraps the read-then-mark-consumed sequence in `async with session_locks.lock_for("riposte", row.channel_id):` at line **345**. Critical section: re-read row under lock → mutate. Discord HTTP delete moved OUTSIDE the lock on the success path.
- **`src/eldritch_dm/persistence/riposte_timers_repo.py`** — `mark_expired` SQL now `WHERE id=? AND status='pending'` (idempotent under race).
- **`src/eldritch_dm/bot/bot.py`** — `setup_hook` constructs `SessionLocks()` + `RiposteSweeper(...)` AFTER `rehydrate_persistent_views` and calls `await self.riposte_sweeper.start()`. `close()` calls `await self.riposte_sweeper.stop()` FIRST in the OPS-04 chain.
- **`src/eldritch_dm/bot/dynamic_items.py`** — `RiposteButton.callback` resolves `bot.session_locks` and passes it to `handle_riposte_click` (falls back to fresh empty registry for tests/edge cases).

### Task 2 — OPS-01 resume drill
`7249a03 test(05-02): OPS-01 resume drill — Riposte timer survives bot restart`

Six tests in `tests/integration/test_riposte_restart.py` (550 LOC, 0.20s combined wall-clock):

| Test | OPS-01 sub-claim |
|------|------------------|
| `test_pending_riposte_survives_restart` | kill bot → sweeper picks up → callback works |
| `test_expired_timer_cleaned_on_restart` | expired auto-cleaned on first sweep |
| `test_setup_hook_orders_sweeper_after_rehydration` | DynamicItems registered before sweeper starts |
| `test_consumed_in_round_survives_restart` | reaction-budget restart-stable |
| `test_graceful_shutdown_cancels_sweeper` | OPS-04: clean shutdown < 2s |
| `test_sweeper_handles_orphaned_message` | discord.NotFound on delete is non-fatal |

## Verification gates (all green)

| Gate | Result |
|------|--------|
| `grep -v '^#' src/eldritch_dm/gameplay/reactions.py \| grep -c 'PLAN-02-LOCK-SEAM'` | **0** ✓ |
| `grep -c 'await self.riposte_sweeper.start()' src/eldritch_dm/bot/bot.py` | **1** ✓ |
| `grep -c 'await self.riposte_sweeper.stop()' src/eldritch_dm/bot/bot.py` | **1** ✓ |
| `uv run ruff check src/eldritch_dm/gameplay/riposte_sweeper.py src/eldritch_dm/gameplay/session_locks.py` | clean ✓ |
| `uv run lint-imports` | **7/7 contracts KEPT** ✓ |
| `uv run pytest tests/gameplay/test_session_locks.py tests/gameplay/test_riposte_sweeper.py tests/integration/test_riposte_restart.py -v` | **24/24 passed** ✓ |
| Full suite (no load): `uv run pytest -q --deselect tests/integration/test_8player_load.py` | **826 passed, 7 skipped** ✓ |
| Phase 4 restart drill no regression | **6/6 passed** ✓ |

## Test count delta

| Snapshot | Tests |
|----------|-------|
| Plan 01 final (commit `8c15bf1`) | 798 |
| Plan 02 final (commit `7249a03`) | **826** |
| Net | **+28** |

Breakdown: +7 session_locks · +11 sweeper · +1 reactions (marker-absent + lock_for_called pair; -1 old marker-present test removed) · +2 reactions concurrent/race · +1 persistence conditional mark_expired · +6 OPS-01 drill = 28 net.

## Requirements progress

- **COMBAT-11** — Riposte timer survives bot restart → **functionally complete** (final [x] mark goes in Plan 03's closure step).
- **OPS-01** — Resume drill → **functionally complete** for the reaction subsystem.

Plan 03 may now wrap the Phase 5 closure work — README, run.py, launchd plist, env audit, REQUIREMENTS/ROADMAP/STATE finalize marks — with full confidence that the reaction system is correct AND restart-safe.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] SessionLocks moved from `bot/` to `gameplay/`**
- **Found during:** Task 1 setup
- **Issue:** Plan frontmatter listed `src/eldritch_dm/bot/session_locks.py`. The import-linter contract `"gameplay must not import bot"` forbids `gameplay.reactions` importing `bot.session_locks`. Putting SessionLocks in `bot/` would have broken the contract.
- **Fix:** Placed under `src/eldritch_dm/gameplay/session_locks.py` per the plan's `verification.risks` recommendation. The plan explicitly anticipated this and pre-approved either option (a) carve an exception OR (b) move under gameplay/ — we took option (b) as cleaner.
- **Files modified:** `src/eldritch_dm/gameplay/session_locks.py` (new), all imports updated accordingly.
- **Commit:** 7dd1bcc

**2. [Rule 2 - Critical functionality] mark_expired now conditional on status='pending'**
- **Found during:** Task 1 implementation review
- **Issue:** The plan called for the conditional SQL ("if Phase 1 shipped it as unconditional `WHERE id=?`, update it to be conditional"). Phase 1 had indeed shipped the unconditional form.
- **Fix:** Changed `UPDATE riposte_timers SET status='expired' WHERE id=?` → `UPDATE ... WHERE id=? AND status='pending'`. Added `test_mark_expired_conditional_on_pending` to the repo test file.
- **Files modified:** `src/eldritch_dm/persistence/riposte_timers_repo.py`, `tests/persistence/test_riposte_timers_repo.py`
- **Commit:** 7dd1bcc

**3. [Rule 3 - Blocker] Plan 01's TestConcurrentClicks fixture had wrong .get() side_effect length**
- **Found during:** Task 1 GREEN (re-running existing reaction tests)
- **Issue:** Plan 01's `TestConcurrentClicks::test_second_concurrent_click_sees_consumed_status` had `repo.get = AsyncMock(side_effect=[timer, consumed_timer])` (2 entries). Plan 02's lock pattern requires TWO `.get()` per click (pre-lock + under-lock) → 2 clicks × 2 reads = 4 entries needed. AsyncMock raised `StopAsyncIteration`.
- **Fix:** Updated to `side_effect=[timer, timer, consumed_timer, consumed_timer]` with explanatory comment. The Plan 01 test still validates the same correctness invariant.
- **Files modified:** `tests/gameplay/test_riposte_callback.py`
- **Commit:** 7dd1bcc

### Architectural changes
None. The plan's design — shared SessionLocks + RESEARCH Pattern 4 sweeper — held up exactly as written. No Rule 4 escalations.

### Auth gates
None.

## Threat Flags

None new. Plan 02's `<threat_model>` register fully addressed:

| Threat ID | Disposition | Mitigation |
|-----------|-------------|------------|
| T-05-10 (click-vs-sweeper race) | mitigate | SessionLocks shared lock + conditional mark_expired SQL. Test 17 proves under load. |
| T-05-11 (sweeper busy-loop) | mitigate | `max(min_sleep_s, ...)` floor 0.1s; loop always advances state. |
| T-05-12 (info disclosure in logs) | accept | Structured log binds row fields; self-host operator-controlled. |
| T-05-13 (Discord HTTP cascade DoS) | mitigate | `try/except (discord.NotFound, Forbidden, HTTPException, ValueError)` per RESEARCH Pattern 4. Tests 11 + drill Test 6 prove. |
| T-05-14 (cross-bot row corruption) | accept | Plan 01 repo tests prove writes are well-formed. Out of v1 scope. |
| T-05-15 (sweeper delete on inaccessible channel) | mitigate | `discord.Forbidden` caught + logged; row still marked expired so it doesn't loop. |
| T-05-SC (supply chain) | accept | Zero new pip deps. |

## Self-Check: PASSED

Files exist:
- `src/eldritch_dm/gameplay/session_locks.py` — FOUND
- `src/eldritch_dm/gameplay/riposte_sweeper.py` — FOUND
- `tests/gameplay/test_session_locks.py` — FOUND
- `tests/gameplay/test_riposte_sweeper.py` — FOUND
- `tests/integration/test_riposte_restart.py` — FOUND

Commits exist:
- `7dd1bcc` — FOUND
- `7249a03` — FOUND

Marker absent:
- `grep -v '^#' src/eldritch_dm/gameplay/reactions.py | grep -c PLAN-02-LOCK-SEAM` returned 0 — VERIFIED

Lock invocation present at `src/eldritch_dm/gameplay/reactions.py:345` — VERIFIED via `grep -n 'session_locks.lock_for' src/eldritch_dm/gameplay/reactions.py`.
