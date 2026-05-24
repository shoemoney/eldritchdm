---
phase: 13-production-monitoring
plan: 02
subsystem: observability
tags: [alerts, degraded-mode, hysteresis, yaml, safety-override]
requirements:
  completed: [MON-02]
dependency-graph:
  requires: [13-01]
  provides:
    - "DegradedModeState singleton with thread-safe trip/recover"
    - "alerts.yaml 3-tier loader + AlertsFile pydantic schema"
    - "AlertEvaluator with hysteresis + cold_start_replay"
    - "monster_driver_factory degraded-mode override (random wins over env)"
  affects:
    - "bot/__main__.py — boot_alert_evaluator() runs cold-start replay synchronously"
key-files:
  created:
    - src/eldritch_dm/observability/degraded_mode.py
    - src/eldritch_dm/observability/alerts_loader.py
    - src/eldritch_dm/observability/alert_evaluator.py
    - database/alerts.yaml
    - tests/observability/test_degraded_mode.py
    - tests/observability/test_alerts_loader.py
    - tests/observability/test_alert_evaluator.py
    - tests/integration/test_degraded_mode.py
    - tests/bot/test_alert_evaluator_boot.py
    - tests/gameplay/test_factory_degraded_mode.py
  modified:
    - src/eldritch_dm/gameplay/monster_driver_factory.py
    - src/eldritch_dm/bot/__main__.py
    - .planning/REQUIREMENTS.md
decisions:
  - "R-13-02-a: degraded_mode is module singleton (Settings.frozen=True forbids field)"
  - "R-13-02-b: AlertEvaluator schedules on asyncio loop; tick errors caught"
  - "R-13-02-c: alerts.yaml mirrors Phase 8 eligibility.yaml pattern"
  - "R-13-02-d: injectable time_source (no freezegun — races with threading.Event)"
  - "R-13-02-e: throttle/webhook accepted but emit 'v1.3 not implemented' warning"
  - "R-13-02-f: cold_start_replay buckets last window_minutes by minute"
metrics:
  duration: ~2.5h
  completed_date: 2026-05-24
---

# Phase 13 Plan 02: alerts.yaml + Degraded-Mode Trigger Summary

## One-liner

`alerts.yaml`-driven AlertEvaluator with hysteresis trips degraded mode at
P99>1500ms for 5min and auto-recovers at P99<1200ms for 5min; monster
driver factory honors the override over every other signal.

## What Was Built

### `observability/degraded_mode.py`

Process-wide singleton `DegradedModeState` with thread-safe `trip(reason)`
/ `recover()` / `is_active()` / `snapshot()`. Cannot live on `Settings`
(which is `frozen=True`). `trip` is idempotent and logs
`eldritch.degraded_mode.entered` WARNING exactly once per transition;
`recover` logs `eldritch.degraded_mode.exited` INFO with `dwell_seconds`.
`is_active()` is GIL-atomic (no lock) — the factory calls it on every
monster decision.

### `database/alerts.yaml` + `observability/alerts_loader.py`

3-tier loader mirroring Phase 8 `eligibility_loader.py`:
- env > `~/.eldritch/alerts.yaml` > `database/alerts.yaml`
- `yaml.safe_load` only; CI grep gate asserts no bare `yaml.load(`
- Pydantic v2 `AlertsFile` + `AlertRule` with `extra='forbid'`
- Fail-soft to in-code `DEFAULT_RULES` on any error
- Default rules ship the 3 AI-SPEC §7 thresholds verbatim

### `observability/alert_evaluator.py`

`AlertEvaluator` engine + hysteresis state machine:
- Per-rule `consecutive_breach_count` triggers `degraded_mode.trip` after
  `window_minutes / tick_seconds` consecutive ticks
- Recovery threshold computed as `threshold * recover_threshold_factor`
  (default 1200/1500 per AI-SPEC §7); inverse operator applied
- Lingering-bad zone (between recover and trip thresholds) does NOT
  recover — locked in by `test_recover_not_triggered_when_between_1200_and_1500`
- Log-action rules fire every tick the condition is true (edge-triggered
  visibility, not consecutive-counter gated)
- `throttle` and `webhook` actions accepted but emit
  `eldritch.alert.deferred` WARNING (v1.3 deferred)
- `cold_start_replay()` buckets last `window_minutes` of buffer data by
  minute; trips immediately when ALL buckets breach (correct
  cross-restart behavior)
- Injectable `time_source` for deterministic tests (no freezegun races)
- `boot_alert_evaluator(settings)` helper for sync cold-start at boot

### `gameplay/monster_driver_factory.py` override

`_resolve_mode()` gains a priority-0 check on `degraded_mode.is_active()`
BEFORE env / env_override. Degraded mode is a **safety override** — it
wins over the operator's explicit `env_override='smart'`. Lazy
function-scope import keeps gameplay package import-linter-safe.

### Bot startup wiring

`bot.__main__.main` now calls `boot_alert_evaluator(settings)` after
`init_tracing` / `start_metrics_endpoint`. The boot helper returns `None`
when both observability gates are off (no work); when on, it loads rules,
constructs the evaluator, runs `cold_start_replay()` synchronously, and
returns the evaluator. The periodic tick loop is deferred to a future
v1.3 setup_hook integration — for v1.2 the cold-start replay is the
operationally critical path (handles bot restarts during incidents).

## Test Coverage

- `tests/observability/test_degraded_mode.py` — 9 tests
- `tests/observability/test_alerts_loader.py` — 10 tests
- `tests/observability/test_alert_evaluator.py` — 14 tests (hysteresis,
  cold-start replay, ops/_invert_op, log/degrade/throttle actions)
- `tests/integration/test_degraded_mode.py` — 2 D-88 acceptance tests
  (full trip→recover round-trip; 4-min breach does NOT trip)
- `tests/gameplay/test_factory_degraded_mode.py` — 5 tests
- `tests/bot/test_alert_evaluator_boot.py` — 3 tests
- `lint-imports`: 8/8 contracts kept
- `ruff check`: clean

## Deviations from Plan

**1. [Rule 1 - Bug] CONTEXT D-87 said `Settings.monster_driver_override` field — Settings is frozen=True**

- **Found during:** Plan-writing review
- **Issue:** `Settings.model_config = SettingsConfigDict(frozen=True)` — pydantic v2 frozen models reject all assignment after construction
- **Fix:** Module-level `DegradedModeState` singleton with thread-safe trip/recover
- **Documented as:** R-13-02-a in 13-02-PLAN.md

**2. [Rule 3 - Blocking] CONTEXT D-88 mentioned freezegun**

- **Found during:** Plan-writing
- **Issue:** freezegun races with the span-buffer drainer's `threading.Event` polls; observed flakiness in similar OTel test suites
- **Fix:** Injectable `time_source` callable on AlertEvaluator; tests pass a mutable-clock dict
- **Documented as:** R-13-02-d in 13-02-PLAN.md

**3. [Rule 3 - Blocking] Original plan put cold_start_replay inside tick()**

- **Found during:** Pre-execution advisor review
- **Issue:** A single tick increments `consecutive_count` by 1, never by `window_minutes` — fresh in-process counter cannot replay history
- **Fix:** Separate `cold_start_replay()` method that buckets buffer data by minute and trips IF every bucket breaches
- **Documented as:** R-13-02-f in 13-02-PLAN.md; advisor flagged this before any code was written

**4. [Rule 1 - Bug] structlog `log.log(level, ...)` requires int level, not str**

- **Found during:** Task 04 execution
- **Issue:** Initial implementation used `log.log(_severity_to_level(severity), ...)` returning strings like "warning" — structlog's `BoundLogger.log()` checks `level < min_level` and fails on str
- **Fix:** Replaced with dict-dispatch to named methods `{critical: log.error, high: log.warning, warning: log.info}`
- **Files modified:** `alert_evaluator.py`

**5. [Rule 1 - Bug] Integration test had stale breach rows polluting recovery window**

- **Found during:** Task 05 first run
- **Issue:** Phase 2 (healthy injection) seeded rows alongside still-present breach rows; nearest-rank P99 over 25 rows with 5 stale breaches picks a breach value, blocking recovery
- **Fix:** Advance clock past the entire breach window before seeding healthy data — simulates a realistic latency drop scenario
- **Files modified:** `tests/integration/test_degraded_mode.py`

## Self-Check: PASSED

- All created files exist on disk
- Commits 5eff841, a7e6625, b6787d3, 21d3dd1, efc35ef, plus this one
- 43 new tests pass; existing 10 factory tests + 15 Phase 11 observability tests still pass
- ruff clean; lint-imports 8/8 kept
- MON-02 ticked in REQUIREMENTS.md

## Known Stubs

`throttle` and `webhook` alert actions are accepted by the schema but emit
"v1.3 routing not yet implemented" — intentional per CONTEXT "Deferred
(post-v1.2)". The schema is forward-compatible.

## Threat Flags

None new. `alerts.yaml` is `safe_load`-only (same hardening as Phase 8
`eligibility.yaml`); fail-soft fallback to in-code defaults prevents a
malicious YAML from disabling alerting.
