---
phase: 27-profiling
plan: 27-01
requirements_completed: [PROFILE-01, PROFILE-03]
subsystem: perf
tags: [profiling, baseline, perf, cprofile, hot-paths]
dependency_graph:
  requires: [phase-26-opsdash, phase-25-multi-channel-stress]
  provides: [perf-baseline-v1.9.0, hot-path-profiler]
  affects: [phase-28-tune-cli]
tech_stack:
  added: []
  patterns:
    - two-runs-per-path (wall-clock + cProfile separately)
    - respx-mocked dm20 + AsyncMock LLM/Discord
    - os._exit bypass of non-daemon thread shutdown
key_files:
  created:
    - scripts/perf/__init__.py
    - scripts/perf/_schema.py
    - scripts/perf/profile_hot_paths.py
    - tests/perf/__init__.py
    - tests/perf/test_profiler_self_check.py
    - .planning/perf-baseline-v1.9.0.json
  modified: []
decisions:
  - Two-runs-per-path — cProfile adds 2-10x overhead so percentiles
    derived from a profiled run would be noise. Wall-clock loop (100 iter,
    perf_counter_ns) populates p50/p95/p99; separate cProfile loop
    (20 iter) populates cprofile_top_10. Documented in
    docs/PERFORMANCE.md (plan 27-02).
  - combat-turn-resolution profiles the inner dm20-call sequence
    (party_pop_action → party_thinking → party_resolve_action) rather
    than a full orchestrator tick. The outer _loop adds asyncio
    scheduling overhead unrelated to what players wait on; profiling
    the dm20-call chain captures the actual hot path.
  - mcp-cache-roundtrip.l1-miss-l2-hit measures the L1-miss + L2-cold
    + inner-call slower-branch path. A true "L2 hit but L1 miss" would
    require L1 eviction between calls, which conflates eviction cost
    with lookup cost.
  - os._exit(rc) on completion — the profiler instantiates components
    (aiosqlite WriterQueue, structlog span-buffer sqlite handle,
    httpx connection pool) whose non-daemon shutdown hooks block
    normal interpreter exit. Bypassing them is safe because the JSON
    has already been written and the profiler holds no user-facing
    resources. Without this fix subprocess.run(capture_output=True)
    from the self-check deadlocks on pipe-buffer fill.
metrics:
  duration_minutes: ~75
  completed_date: 2026-05-25
---

# Phase 27 Plan 01: Hot-path profiler + v1.9.0 baseline (PROFILE-01, PROFILE-03) Summary

One-liner: built `scripts/perf/profile_hot_paths.py` — a hermetic profiler
covering all 6 D-206 hot paths (with 3 sub-paths each for mcp-cache and
smart-driver) under respx-mocked dm20 + AsyncMock LLM/Discord, completing
the full 100-iter wall-clock + 20-iter cProfile run in ~1.1s wallclock
(well under the 120s budget), and committed the canonical v1.9.0 baseline
JSON at `.planning/perf-baseline-v1.9.0.json` (10 operations, ~7 KB).

## What shipped

### PROFILE-01 — hot-path profiler script

- **`scripts/perf/_schema.py`** — pydantic v2 `BaselineSchema` + `OperationStats`
  validating the D-209 JSON shape (p50_ms, p95_ms, p99_ms, iterations,
  cprofile_top_10). At-least-one-operation invariant + ≤10 cprofile entries.

- **`scripts/perf/profile_hot_paths.py`** — 6 path-profiler async functions
  + measurement primitives + CLI. Each path uses hermetic mocks:
  - `mcp-cache-roundtrip` — respx dm20; 3 sub-paths via env-var toggles
    + `get_settings.cache_clear()` between sub-paths.
  - `smart-driver-oracle` — `SmartMonsterDriver` with AsyncMock OpenAI
    client; 3 sub-paths exercise smart-success, parse-failure fallback,
    and per-round LRU cache-hit.
  - `character-ingest-fast-path` — respx-mocked LLM returning a valid
    `CharacterSheet` JSON; measures sanitize + JSON parse + pydantic
    validate.
  - `ingest-pipeline-ocr` — monkeypatched `resolve_ocr_backend` + `run_ocrmac`
    returning canned (text, conf); respx-mocked LLM + dm20 verify; PNG
    generated via Pillow (or hand-crafted minimal PNG fallback).
  - `riposte-click-handler` — tmp SQLite + WriterQueue + real
    `SessionLocks` + real `RiposteTimerRepo`. The `riposte_timers` FK
    to `channel_sessions` is satisfied by a one-time
    `ChannelSessionRepo.upsert` at setup. AsyncMock interaction +
    rate_limiter + warning_sender + `mcp_tools.combat_action` patched.
  - `combat-turn-resolution` — respx-mocked dm20 returning realistic
    JSON for `dm20__party_{pop_action,thinking,resolve_action}`; calls
    the three `mcp_tools` wrappers in sequence per iteration.

- **Measurement primitives** — `measure_walltime` (perf_counter_ns +
  nearest-rank percentile) and `measure_cprofile` (cProfile.Profile +
  pstats.Stats; top_10 formatted as `module.func:lineno (cumtime_pct)`,
  pct relative to the top entry so it reads ~100%).

### PROFILE-03 — canonical v1.9.0 baseline

`.planning/perf-baseline-v1.9.0.json` — 10 operations (6 hot paths,
3 of which expand into 3 sub-paths each = 4 paths × 1 + 2 paths × 3 = 10).
Snapshot p99 values (M3 Ultra, oMLX idle, omlx not actually called):

| Operation                                       | p50 (ms) | p99 (ms) |
|-------------------------------------------------|---------:|---------:|
| character-ingest-fast-path                      |    0.565 |    1.084 |
| combat-turn-resolution                          |    0.437 |    0.606 |
| ingest-pipeline-ocr                             |    1.061 |    1.446 |
| mcp-cache-roundtrip.l1-hit                      |    0.007 |    0.020 |
| mcp-cache-roundtrip.l1-l2-miss                  |    0.170 |    0.332 |
| mcp-cache-roundtrip.l1-miss-l2-hit              |    0.007 |    0.085 |
| riposte-click-handler                           |    2.481 |    3.573 |
| smart-driver-oracle.cache-hit                   |    0.012 |    0.014 |
| smart-driver-oracle.smart-fallback-to-random    |    0.087 |    0.130 |
| smart-driver-oracle.smart-success               |    0.091 |    0.118 |

Sanity checks all hold:
- `l1-hit < l1-l2-miss` (cache hit faster than full miss)
- `cache-hit < smart-success` (per-round LRU faster than re-parse)
- `riposte-click-handler` is the slowest (real SQLite I/O via WriterQueue)
- `ingest-pipeline-ocr` is second-slowest (executor + OCR stub + LLM mock
  + 2× dm20 verify calls)

### Self-check tests

- `tests/perf/test_profiler_self_check.py`:
  - `test_profiler_runs_clean_5_iterations` — subprocess invocation with
    `--iterations 5 --skip-cprofile`, asserts exit 0 + JSON validates +
    all 6 required hot-path prefixes present + percentile ordering
    invariant (p99 ≥ p95 ≥ p50) + wallclock <30 s.
  - `test_committed_baseline_validates` — re-validates the committed
    `.planning/perf-baseline-v1.9.0.json` against `BaselineSchema`; skips
    when the file is missing.
- Both gated behind `pytest.mark.slow` + `RUN_STRESS=1` env-var (same
  pattern as Phase 25 stress test). Run with
  `RUN_STRESS=1 pytest tests/perf/ -v` → 2 passed in 0.51 s.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `riposte_timers` foreign-key constraint failed**
- **Found during:** Task 7 (riposte-click-handler smoke run)
- **Issue:** `riposte_timers.channel_id REFERENCES channel_sessions(channel_id)`
  → bare `repo.insert(...)` against a fresh-bootstrapped DB failed with
  `sqlite3.IntegrityError: FOREIGN KEY constraint failed`.
- **Fix:** Insert the parent `channel_sessions` row via `ChannelSessionRepo.upsert`
  before populating riposte_timers (mirrors the Phase 25 stress test pattern).
- **Files modified:** `scripts/perf/profile_hot_paths.py`
- **Commit:** 90aa613

**2. [Rule 3 - Blocking] subprocess.run(capture_output=True) deadlock**
- **Found during:** Task 10 (self-check test smoke)
- **Issue:** The profiler emits ~23 KB of structlog INFO output during a
  5-iter run. With `capture_output=True`, the kernel pipe buffer fills
  at ~64 KB during the full 100-iter run and the writer blocks
  indefinitely. Worse, even with `stdout=open(...)` the script hung at
  end because `aiosqlite.WriterQueue` + `structlog` span-buffer sqlite
  install non-daemon shutdown hooks that block normal interpreter exit.
- **Fix:** (a) Switch the self-check test to file-backed stdout/stderr
  redirection (no pipe). (b) `os._exit(rc)` after `main()` writes JSON
  — safe because all measurements + JSON write have already completed
  and the script holds no user-facing resources.
- **Files modified:** `scripts/perf/profile_hot_paths.py`,
  `tests/perf/test_profiler_self_check.py`
- **Commit:** 90aa613

## Auth gates

None — fully hermetic, no real network calls, no credentials touched.

## Known Stubs

None — the profiler measures real code paths; mocks are at the
network/Discord/LLM boundary only.

## Verification

- `ruff check .` — All checks passed.
- `ruff format scripts/perf tests/perf` — clean (applied once).
- `lint-imports` — 8 contracts kept, 0 broken.
- `pytest -q -x` — **1655 passed, 13 skipped** (zero regression).
- `RUN_STRESS=1 pytest tests/perf/ -v` — 2 passed in 0.51 s.
- Profiler wallclock — 1.1 s (full 100-iter + 20-iter cProfile, all 10
  operations). Budget was 120 s.

## Self-Check: PASSED

- FOUND: `scripts/perf/profile_hot_paths.py`
- FOUND: `scripts/perf/_schema.py`
- FOUND: `tests/perf/test_profiler_self_check.py`
- FOUND: `.planning/perf-baseline-v1.9.0.json`
- FOUND commit `fffb95a`: docs(27): plans 27-01 and 27-02 …
- FOUND commit `f7818a4`: feat(27-01): hot-path profiler script + JSON schema
- FOUND commit `90aa613`: feat(27-01): commit v1.9.0 baseline + self-check
