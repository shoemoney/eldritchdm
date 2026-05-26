---
phase: 27-profiling
milestone: v1.9
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - PROFILE-01 (hot-path profiler script)
  - PROFILE-02 (docs/PERFORMANCE.md budgets)
  - PROFILE-03 (canonical baseline JSON)
---

# Phase 27 — Profiling + latency budget documentation (CONTEXT)

## Mission

Build the profiling infrastructure that establishes the v1.9.0 perf baseline. 6 hot paths get cProfile + wall-clock measurement under mocked dm20. Outputs JSON consumed by Phase 28's CLI for regression-detection.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-206** | **6 hot paths to profile**:<br>1. `combat-turn-resolution` — end-to-end turn (player intent → dm20 mock → resolution → embed update)<br>2. `mcp-cache-roundtrip` — Phase 16 L1 hit, L1 miss/L2 hit, L1+L2 miss (3 sub-paths)<br>3. `smart-driver-oracle` — SmartMonsterDriver._pick_target full path (mocked LLM, fail-soft fallback) — 3 sub-paths: smart success, smart-fallback-to-random, cache-hit<br>4. `character-ingest-fast-path` — D&D Beyond JSON → normalize → repo write<br>5. `riposte-click-handler` — Phase 5 click → session-lock → resolve → embed update<br>6. `ingest-pipeline-ocr` — pypdf/PIL pipeline with mocked ocrmac (Phase 14 skip-gate already excludes real ocrmac) | Comprehensive but bounded — these are the operations players actually wait on |
| **D-207** | **Mocked dm20 via respx** (Phase 12 pattern). Profile OUR CODE, not network. dm20 RTT documented separately as "operator-tunable network budget" in PERFORMANCE.md. | Hermetic perf measurement |
| **D-208** | **Per-operation: p50_ms, p95_ms, p99_ms** (from 100 iterations) + `cprofile_top_10` (functions by cumulative time). NOT mean — mean hides tail latency which is what users feel. | Tail latency is the truth |
| **D-209** | **Baseline JSON schema**:<br>```json<br>{<br>  "version": "1.9.0",<br>  "git_sha": "...",<br>  "generated_at": "ISO",<br>  "operations": {<br>    "combat-turn-resolution": {<br>      "p50_ms": 12.3, "p95_ms": 45.6, "p99_ms": 89.0,<br>      "iterations": 100,<br>      "cprofile_top_10": ["mcp_cache.execute:142 (15.2%)", ...]<br>    },<br>    ...<br>  }<br>}<br>``` | Compact + diff-friendly |
| **D-210** | **docs/PERFORMANCE.md (NEW)**: table of operations × {target p99, measurement methodology, OK/WARN/FAIL thresholds}. Targets derived from PROJECT.md existing constraints. WARN = 110% of target, FAIL = 125% (matches Phase 28's CLI exit-code thresholds). | Single doc operators read |
| **D-211** | **Module location**: `scripts/perf/profile_hot_paths.py` (executable script, NOT a package import — runs standalone). `tests/perf/test_profiler_self_check.py` verifies the profiler runs without error against each path (NOT runs against full data — just smokes that the profiler itself works). | Scripts-style, not lib-style |
| **D-212** | **Baseline at `.planning/perf-baseline-v1.9.0.json`** (committed). Future baselines: `.planning/perf-baseline-v1.10.0.json`, etc. NOT auto-rotated — operators commit a new baseline deliberately when accepting a perf regression. | Manual commit = deliberate acceptance |
| **D-213** | **NO LLM CALLS in profiler** — even mocked. Profile measures the slim-context construction + JSON parse + validation paths. Real LLM latency is dominated by network + model inference, both out-of-scope for OUR perf budget. | Same reasoning as D-207 dm20 |
| **D-214** | **2 plans**: 27-01 = profiler script + baseline JSON. 27-02 = docs/PERFORMANCE.md budget table. | ROADMAP plans section |

## Success Criteria
1. `scripts/perf/profile_hot_paths.py` runs all 6 hot paths (with sub-paths where applicable) under cProfile + wall-clock
2. Output JSON validates against the D-209 schema
3. `tests/perf/test_profiler_self_check.py` smoke-tests profiler runs cleanly
4. `.planning/perf-baseline-v1.9.0.json` committed as the canonical baseline
5. `docs/PERFORMANCE.md` documents per-operation budget table + WARN/FAIL thresholds
6. Profiler completes in <120s wallclock (operator can run it iteratively)
7. ruff + lint-imports clean
