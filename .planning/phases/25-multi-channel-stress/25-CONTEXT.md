---
phase: 25-multi-channel-stress
milestone: v1.8
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - CONC-01 (concurrent-session stress test)
  - CONC-02 (cache layer under concurrent load)
  - CONC-03 (fix at source or honest-report escalate)
---

# Phase 25 — Multi-channel concurrency stress tests (CONTEXT)

## Mission

Close v1.0's longest-open Blockers/Concerns item: "Verify dm20 supports
concurrent multi-campaign sessions in one process." Build a 4-channel
concurrent stress test that exercises every shared resource (MCPClient,
WriterQueue, MonsterMemoryRegistry, MCP cache L1/L2, character cache,
narration cache). Fix any surfaced bug at source — or honest-report and
escalate to v1.9 if architectural.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-193** | **Test file**: `tests/integration/test_multi_channel_stress.py`. Gated behind `RUN_STRESS=1` env var (Phase 1 convention preserved — excluded from default pytest run; opt-in only). | Heavy test, doesn't belong in default CI loop |
| **D-194** | **4-channel scenario**: spin up 4 bot-like coroutines, each "owns" a distinct channel_id. Each runs a 5-round combat session simultaneously against a mocked dm20 (respx). All 4 share the SAME MCPClient + MCPCache + WriterQueue + MonsterMemoryRegistry instances. Total ~120 dm20 calls + ~20 cache writes + ~20 memory observations across the 4-channel run. | Realistic enough to surface races; bounded enough to run in <60s |
| **D-195** | **Assertions** (must ALL hold):<br>(a) Zero `database is locked` errors from any aiosqlite operation<br>(b) Per-channel state isolation: MonsterMemory for ch_1 NEVER contains data from ch_2 (cross-channel leak = test fail)<br>(c) SmartMonsterDriver per-round cache: same (channel, round, monster) → same choice (no race on cache key)<br>(d) MCPCache L1+L2 internal consistency: hit/miss counters match span emission count; no double-charges<br>(e) WriterQueue (v1.4 cancellable shutdown) handles `stop()` cleanly while writes are in-flight from 4 channels | Each one targets a specific shared resource |
| **D-196** | **Mock dm20 with respx** (Phase 12 pattern): deterministic latency variance (0-50ms random per call) to give the scheduler a chance to interleave. NO real dm20 (test must run anywhere, including CI). | Hermetic stress test |
| **D-197** | **Plan 01 = test infrastructure + 4-channel scenario**. Plan 02 = fix any surfaced bug (or escalate honestly if architectural). | ROADMAP plans section |
| **D-198** | **If Plan 02 finds a bug that needs >2 hours of investigation**, halt-and-report (matches Phase 15/23 pattern). Document the bug + minimal repro + suggested fix path. | Honest-report contract preserved |
| **D-199** | **Success measure**: stress test runs 3 consecutive times with 0 failures. If even 1 of 3 fails → architectural bug exists; escalate. | Determinism is the bar |
| **D-200** | **Module location**: just `tests/integration/test_multi_channel_stress.py`. No new src/ modules expected (this is a test phase + potential fix); if fix requires src/ changes, document in Plan 02. | Scope discipline |

## Success Criteria
1. test_multi_channel_stress.py runs 3 consecutive times with 0 failures (RUN_STRESS=1)
2. All 5 assertions (D-195 a-e) pass under stress
3. Any surfaced bug fixed at source OR escalated honestly
4. Test wallclock ≤60s per run
5. ruff + lint-imports clean
6. Existing 1644-test suite still green (zero regression)
