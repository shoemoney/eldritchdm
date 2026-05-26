---
phase: 26-opsdash-tooling
milestone: v1.8
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - OPSDASH-01 (3 more bundled dashboards)
  - OPSDASH-02 (backfill auto-discovery)
  - OPSDASH-03 (UPSTREAM-ISSUES.md expansion)
---

# Phase 26 — Operational dashboards + tooling polish (CONTEXT)

## Mission

Final v1.8 phase. Bundle 3 more operational dashboards (degraded-mode, budget, eval). Kill the backfill_summary_frontmatter hardcoded paths by auto-discovering all SUMMARY files. Extend UPSTREAM-ISSUES.md with 2 more entries.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-201** | **3 new dashboards** at `database/dashboards/`:<br>- `degraded_mode.json` — entries: trip events (count over time), exit events, current state gauge, total duration in degraded; consumes Phase 13 DegradedModeState span attrs<br>- `budget.json` — daily spend (line over 7d), cap proximity (gauge as % of ELDRITCH_DAILY_LLM_BUDGET_USD), per-model spend breakdown; consumes Phase 13 cost calculator span attrs<br>- `eval.json` — TacticalJudge overall_score (line over time), per-dimension breakdown, per-archetype scoreboard; consumes Phase 12 eval-CLI JSON outputs (NOT spans — eval is offline)<br>All 3 use Phase 11 OUR-FORMAT spec (matches Phase 24's pattern). | Three independent operational concerns, each with established data source |
| **D-202** | **seed-dashboards.sh extended** to include the 3 new files (idempotent — skip if already seeded). | One canonical seed |
| **D-203** | **backfill auto-discovery (OPSDASH-02)**: rewrite `scripts/audit/backfill_summary_frontmatter.py` to use `pathlib.Path(".planning/phases").rglob("*-SUMMARY.md")` for discovery. Mapping inference: read `.planning/ROADMAP.md` Traceability table to build {phase: [req_id, ...]}; split per-plan by SUMMARY filename (e.g., `16-01-SUMMARY.md` → plan 01 reqs from ROADMAP). Hand-fallback for SUMMARYs that span multiple plans. | Self-discovering — Phase 24 finding becomes structurally impossible |
| **D-204** | **UPSTREAM-ISSUES.md expansion (OPSDASH-03)**: add 2 entries:<br>- ISSUE-2: backfill_summary_frontmatter hardcoded paths (now fixed by OPSDASH-02 — entry stands as proof + log; status: RESOLVED IN-REPO)<br>- ISSUE-3: dm20 lacks structured post-resolve damage events (blocks v1.7 WIRE-01; status: OPEN — requires upstream dm20 work) | Two real backlog items |
| **D-205** | **2 plans**: 26-01 = 3 dashboards. 26-02 = backfill auto-discovery + UPSTREAM-ISSUES expansion. | ROADMAP plans section |

## Success Criteria
1. `database/dashboards/{degraded_mode,budget,eval}.json` exist with OUR-FORMAT spec
2. `scripts/observability/seed-dashboards.sh` extended (idempotent)
3. `scripts/audit/backfill_summary_frontmatter.py` rewritten to auto-discover (no hardcoded path list)
4. backfill script run against current state finds 0 gaps (validate CI gate still says "OK: 35 SUMMARY files")
5. `.planning/UPSTREAM-ISSUES.md` has 3 total entries (ISSUE-1 from v1.7 + ISSUE-2 + ISSUE-3 new)
6. ruff + lint-imports clean
7. Existing 1655-test suite still passes (zero regression)
