# EldritchDM — Requirements (v1.8 Multi-Channel Hardening)

**Milestone:** v1.8 Multi-Channel Hardening
**Goal:** Stress-test concurrent multi-channel scenarios (the original v1.0 Blockers/Concerns item: "Verify dm20 supports concurrent multi-campaign sessions in one process"). Surface + fix any observed concurrency bugs. Bundle 3 more operational dashboards (degraded-mode, budget, eval). Tooling polish (auto-discovery for backfill script, UPSTREAM-ISSUES expansion).
**Total v1.8 requirements:** 6 across 2 categories.

---

## v1.8 Requirements

### CONC — Multi-channel concurrency (Phase 25)

- [x] **CONC-01**: Concurrent-session stress test — `tests/integration/test_multi_channel_stress.py` simulates 4 channels with active sessions running simultaneously (same bot process, shared MCPClient, shared WriterQueue from v1.4, shared MonsterMemoryRegistry from v1.6). Asserts: no database-is-locked errors, no cross-channel state leakage in MonsterMemory, no SmartMonsterDriver per-round cache collisions across channels.
- [x] **CONC-02**: MCP query cache (Phase 16) under concurrent load — same stress test extends to verify L1 LRU + L2 SQLite handle 4-channel concurrent reads/writes without race conditions. Asserts L1 hit/miss accounting stays consistent; L2 SQLite WAL handles concurrent writers (single-writer pattern from Phase 1).
- [x] **CONC-03**: Any concurrency bug surfaced by CONC-01/02 is FIXED at source (not masked by test ordering or skip-marks). Honest-report if a real bug is found that requires architectural changes beyond v1.8 scope — halt + escalate to v1.9. _(Branch B: no-op closure — 3-run stress test 3-for-3 green, no bug surfaced.)_

### OPSDASH — Operational dashboards + tooling polish (Phase 26)

- [x] **OPSDASH-01**: 3 bundled dashboards added to `database/dashboards/`:
  - `degraded_mode.json` — degraded-mode entry/exit events + duration; consumes Phase 13 span attrs
  - `budget.json` — daily LLM spend trend + cap proximity; consumes Phase 13 cost calculator outputs
  - `eval.json` — TacticalJudge scores over time + per-archetype breakdown; consumes Phase 12 eval-CLI outputs
  All 3 use Phase 11 OUR-FORMAT spec (NOT Phoenix-native).
- [x] **OPSDASH-02**: `scripts/audit/backfill_summary_frontmatter.py` rewritten to auto-discover ALL `*-SUMMARY.md` files under `.planning/phases/`; no hardcoded path list. Mapping inference: phase number → REQUIREMENTS.md traceability table → plan-suffix-aware split. The Phase 24 finding (14 SUMMARYs missed) should be impossible after this rewrite.
- [x] **OPSDASH-03**: `.planning/UPSTREAM-ISSUES.md` extended with 2 more entries:
  - ISSUE-2: backfill_summary_frontmatter hardcoded paths (now fixed by OPSDASH-02 — entry serves as proof + log)
  - ISSUE-3: dm20 lacks structured post-resolve damage events (blocks v1.7 WIRE-01)

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| CONC-01 | 25 | v1.0 Blockers/Concerns line 49: "Verify dm20 supports concurrent multi-campaign sessions in one process (Phase 1 spike)" |
| CONC-02 | 25 | v1.5 Phase 16 — cache layer under concurrent load |
| CONC-03 | 25 | Honest-report contract — fix at source or escalate |
| OPSDASH-01 | 26 | v1.7 PROJECT.md candidate list — "Phase 24 ships 3 cache dashboards; 3 more operational dashboards remain" |
| OPSDASH-02 | 26 | v1.7 audit tech-debt item: "backfill_summary_frontmatter.py hardcoded paths" |
| OPSDASH-03 | 26 | v1.7 UPSTREAM-ISSUES.md backlog expansion |

## Mode Constraints

- CONC-01: 4-channel stress test runs in <60s; gated behind `RUN_STRESS=1` env var (Phase 1 convention preserved); not in default pytest run.
- CONC-02: L1 LRU concurrent-access via existing asyncio.Lock (Phase 16 D-110); L2 WAL pattern (Phase 1 / v1.4).
- CONC-03: any architectural surprise → halt-and-report, don't paper over with reordering.
- OPSDASH-01: dashboards consume EXISTING span attributes; no new instrumentation required.
- OPSDASH-02: auto-discovery uses `pathlib.Path("..planning/phases").rglob("*-SUMMARY.md")`; mapping from REQUIREMENTS.md traceability table is parsed via simple regex.
- OPSDASH-03: documentation-only; no code changes.
