# EldritchDM — Requirements (v1.9 Performance Baseline + Tuning)

**Milestone:** v1.9 Performance Baseline + Tuning
**Goal:** Profile the hot paths (combat resolution, cache lookups, smart driver oracle, character ingest), establish per-operation latency budgets, optimize the top 3-5 slowest operations, and ship `eldritch-dm-perf-baseline` CLI for regression-detection (mirrors Phase 12's eval-baseline-diff pattern). Concrete answer to "is this fast enough?" with data.
**Total v1.9 requirements:** 6 across 2 categories.

---

## v1.9 Requirements

### PROFILE — Profiling + latency budget documentation (Phase 27)

- [x] **PROFILE-01**: Hot-path profiler at `scripts/perf/profile_hot_paths.py` — runs each named hot path (combat-turn-resolution, mcp-cache-roundtrip, smart-driver-oracle, character-ingest-fast-path, riposte-click-handler, ingest-pipeline-ocr) under `cProfile` + wall-clock measurement. Outputs `perf-baseline-{ISO ts}-{git sha}.json` with per-operation: `p50_ms`, `p95_ms`, `p99_ms`, `cprofile_top_10` (functions by cumulative time). Uses mocked dm20 (respx) so the profile measures OUR code, not dm20 latency.
- [x] **PROFILE-02**: Per-operation latency budgets documented at `docs/PERFORMANCE.md` (NEW). Each hot path gets: target p99 (from PROJECT.md performance section's existing constraints: character ingest <6s, narration <150 words/1500ms via D-54, Discord ack <3s, embed updates ≤1/sec/message), measurement methodology, and "OK / WARN / FAIL" thresholds. Builds a regression-detection table the CLI uses.
- [x] **PROFILE-03**: Baseline JSON committed at `.planning/perf-baseline-v1.9.0.json` — the canonical baseline subsequent runs compare against. Updated whenever a deliberate perf regression is accepted (e.g., correctness fix that costs latency).

### TUNE — Targeted optimizations + regression-detection CLI (Phase 28)

- [x] **TUNE-01**: Optimize the TOP 3 slowest operations identified by Phase 27's baseline. Each optimization gets: (a) a benchmark BEFORE the fix, (b) the actual change, (c) a benchmark AFTER showing the improvement, (d) a test that wasn't passing before now passes (regression guard). NO speculative optimization — only fix what profiling identifies. **Shipped as Branch B no-targets closure (Phase 28 / Plan 28-01): per-op budget analysis confirmed every operation is ≥45× under target with no WARN/FAIL — empirical bar from D-216 cannot be satisfied. See `docs/PERFORMANCE.md` § "Phase 28 TUNE-01 closure".**
- [ ] **TUNE-02**: `eldritch-dm-perf-baseline` CLI (new `[project.scripts]`) — runs the hot-path profiler from PROFILE-01 + diffs against `--baseline path/to/baseline.json` (default: the v1.9.0 baseline). Exit codes: 0 (within ±10% of baseline), 1 (regression > 10% on any p99), 2 (regression > 25% on any p99 — critical). Mirrors Phase 12 `eldritch-dm-eval` exit-code pattern.
- [ ] **TUNE-03**: CI integration — `.github/workflows/perf.yml` (separate from main CI matrix) runs the perf CLI weekly + on tagged releases against the current baseline. Failure → opens an issue (informational, not blocking releases — perf is operator-tunable, not a hard ship gate).

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| PROFILE-01 | 27 | PROJECT.md performance constraints — needs measurement, not just hope |
| PROFILE-02 | 27 | docs/PERFORMANCE.md establishes per-operation budgets |
| PROFILE-03 | 27 | Canonical baseline JSON for v1.9.0 |
| TUNE-01 | 28 | Top 3 slowest ops from profile output |
| TUNE-02 | 28 | Phase 12 eval-baseline pattern adapted to perf |
| TUNE-03 | 28 | CI perf-regression alerting |

## Mode Constraints

- Profiler uses mocked dm20 (respx) — measures OUR code, not network/dm20 latency. Real dm20 RTT is documented separately as "network budget" (operator-tunable).
- Latency budgets respect EXISTING PROJECT.md constraints: character ingest <6s, narration <150 words (Phase 10 D-54 sets 1500ms LLM timeout), Discord ack <3s, embed updates ≤1/sec/message.
- Phase 28 NO SPECULATIVE OPTIMIZATION — only fix the top 3 identified by profile data. Empirical, not vibes.
- Each TUNE-01 optimization needs before/after benchmark + regression-guard test.
- TUNE-02 CLI mirrors Phase 12 `eldritch-dm-eval` --baseline diff pattern + exit codes.
- TUNE-03 CI is informational (not release-blocking) — perf is operator-tunable, not a correctness contract.
