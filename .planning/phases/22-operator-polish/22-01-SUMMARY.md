---
phase: 22-operator-polish
plan: 22-01
requirements_completed: [OPQOL-01]
milestone: v1.6
requirements: [OPQOL-01]
key-files:
  created:
    - tests/gameplay/test_eligibility_watcher.py
  modified:
    - src/eldritch_dm/gameplay/eligibility_loader.py
    - src/eldritch_dm/bot/bot.py
tags: [phase-22, opqol-01, hot-reload, eligibility-yaml, fail-soft]
completed: 2026-05-25
  - OPQOL-01
---

# Phase 22 Plan 01: Hot-reload eligibility.yaml Summary

Hot-reload Riposte eligibility YAML via background mtime poll (60s),
fail-soft on bad YAML, zero new dependencies.

## What Shipped

- **EligibilityFileWatcher** class (`src/eldritch_dm/gameplay/eligibility_loader.py`)
  - 60s mtime polling via `pathlib.Path.stat().st_mtime_ns`
  - Path resolved ONCE at construction (no mid-run tier switching)
  - `poll_once()` deterministic test seam returning `True` iff a reload occurred
  - On bad YAML: loader-fallback-to-DEFAULT while last-known-good is non-DEFAULT
    is detected and treated as `reload_failed` — keeps last-known-good
  - All exceptions caught + logged; never raises into bot loop
  - `start()` / `stop()` idempotent
- **Bot lifecycle wire** (`src/eldritch_dm/bot/bot.py`)
  - New `self.eligibility_watcher: EligibilityFileWatcher | None` attribute
  - Constructed + started in `setup_hook` AFTER initial `load_eligibility()`
  - `on_reload` callback updates `self.eligibility_set`
  - Stopped first in `bot.close()` (no deps on other subsystems)
- **9 new tests** (`tests/gameplay/test_eligibility_watcher.py`)
  - initial-load baseline; no-mtime-change → no-reload; mtime-change → reload;
    bad-yaml → LKG preserved; file vanishes → no crash; start/stop idempotent;
    no-path-at-init no-ops; on_reload callback errors swallowed; end-to-end
    background-loop reload

## Test Results

- `tests/gameplay/test_eligibility_watcher.py`: 9 passed
- `tests/gameplay/test_eligibility_loader.py` (Phase 8): 19 passed — **zero regression**
- `tests/bot/` (full suite): 373 passed, 5 skipped — **zero regression**
- `ruff check`: clean
- `lint-imports`: 8/8 contracts kept

## v1.6 Scope Cut (documented inline)

A live `MonsterDriver` constructed in `setup_hook` holds a snapshot of the
initial eligibility frozenset (Phase 8 D-38 dependency injection). When the
watcher reloads, `bot.eligibility_set` is updated, but the running driver
keeps the old set until a fresh driver is constructed. Rebuilding a live
driver mid-combat is out of scope for OPQOL-01 — Phase 22 closes the
operator-facing UX gap; deeper rewiring is deferred.

## Deviations from Plan

None. Plan executed exactly as written.

## Self-Check

- [x] `src/eldritch_dm/gameplay/eligibility_loader.py` contains `EligibilityFileWatcher`
- [x] `src/eldritch_dm/bot/bot.py` constructs + starts the watcher in `setup_hook`
- [x] `tests/gameplay/test_eligibility_watcher.py` exists with 9 tests
- [x] 22-01 commits: 7566396 (plan), 0482079 (loader), 9dcb775 (tests), 09f3c38 (bot wire)

## Self-Check: PASSED
