# Roadmap: EldritchDM

## Milestones

- ✅ **v1.0 MVP — Mechanically Honest AI Dungeon Master** — Phases 1-5 (shipped 2026-05-23) — see [`milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Polish** — Phases 6-10 (shipped 2026-05-24) — see [`milestones/v1.1-ROADMAP.md`](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Quality Flywheel** — Phases 11-13 (shipped 2026-05-24) — see [`milestones/v1.2-ROADMAP.md`](milestones/v1.2-ROADMAP.md)
- 🚧 **v1.3 Hygiene Sweep** — Phase 14 (in progress) — close carried-since-v1.1 test flakes + SUMMARY frontmatter compliance

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-5) — SHIPPED 2026-05-23</summary>

- [x] **Phase 1**: MCP Client + Local State (3/3 plans)
- [x] **Phase 2**: Discord Scaffold + Persistent Views (3/3 plans)
- [x] **Phase 3**: Lobby + Character Ingest (3/3 plans)
- [x] **Phase 4**: Gameplay — Exploration + Combat (3/3 plans)
- [x] **Phase 5**: Reactions + Self-Host Polish (3/3 plans)

**Final stats:** 5 phases · 15 plans · 110 commits · 864 tests passing / 873 collected · 7/7 import-linter contracts kept · 71/73 requirements satisfied (97%).

**Tag:** `v1.0` · **Repo:** https://github.com/shoemoney/eldritchdm

</details>

<details>
<summary>✅ v1.1 Polish (Phases 6-10) — SHIPPED 2026-05-24</summary>

- [x] **Phase 6**: Debt Paydown + Cold-Start Smoke (2/2 plans)
- [x] **Phase 7**: Safety Gap Closure (1/1 plan)
- [x] **Phase 8**: YAML Riposte Eligibility (1/1 plan)
- [x] **Phase 9**: pc_classes Ingest-Backfill Script (1/1 plan)
- [x] **Phase 10**: Smart MonsterDriver (Claudmaster-Routed Targeting) (2/2 plans)

**Final stats:** 5 phases · 7 plans · ~64 commits · 10/10 requirements satisfied · ruff 79→0 errors · 7/7 import-linter contracts kept · 51 smart-driver + 21 backfill + 30 eligibility + 111 safety + 1 cold-start tests added.

**Tag:** `v1.1` · **Archive:** [`milestones/v1.1-ROADMAP.md`](milestones/v1.1-ROADMAP.md)

</details>

<details>
<summary>✅ v1.2 Quality Flywheel (Phases 11-13) — SHIPPED 2026-05-24</summary>

- [x] **Phase 11**: Phoenix Observability Foundation (2/2 plans)
- [x] **Phase 12**: LLM-as-Judge Tactical Scoring (2/2 plans)
- [x] **Phase 13**: Production Monitoring + Alerting (3/3 plans)

**Final stats:** 3 phases · 7 plans · ~53 commits · 8/8 requirements satisfied · 8/8 import-linter contracts kept · 8 obs + 78 eval + 113 monitoring tests added (~199 new) · ruff clean throughout.

**Tag:** `v1.2` · **Archive:** [`milestones/v1.2-ROADMAP.md`](milestones/v1.2-ROADMAP.md)

</details>

## 🚧 v1.3 Hygiene Sweep (Phase 14)

### Phase 14: Flake cleanup + planner template hardening
**Goal**: Close the carried-since-v1.1 test flakes (OCR backend env failures + phase3_smoke test-pollution flake) and backfill `requirements_completed:` frontmatter across all v1.1+v1.2 SUMMARYs. Sets up a green-on-green test suite for v1.4 feature work.
**Mode:** mvp (hygiene — no user-visible behavior change)
**Depends on**: Phase 13 (v1.2 final state — full corpus to audit)
**Requirements**: FLAKE-01, FLAKE-02, FLAKE-03
**Success Criteria**:
  1. Full `uv run pytest tests/` returns 0 ocrmac-related failures (skip-gated cleanly OR ocrmac installed in dev venv)
  2. `tests/integration/test_phase3_smoke.py` passes deterministically in full-suite run; root-cause polluter identified and fixed at source
  3. All 14 v1.1+v1.2 SUMMARY.md files have `requirements_completed:` YAML frontmatter field listing the REQ-IDs each plan satisfied
  4. ruff + lint-imports clean; no new test failures introduced
**Plans**:
- [ ] Plan 01: OCR env-gate + phase3_smoke pollution root-cause + fix (`fix(14-01): OCR env-gate + phase3_smoke pollution root-cause fix (FLAKE-01, FLAKE-02)`)
- [ ] Plan 02: SUMMARY frontmatter backfill across v1.1+v1.2 phases (`docs(14-02): backfill requirements_completed: frontmatter across all v1.1+v1.2 SUMMARYs (FLAKE-03)`)

## Traceability

| REQ-ID | Phase | Source Plan |
|---|---|---|
| DEBT-01 | 6 | 6-01-PLAN-ruff-cleanup |
| DEBT-02 | 6 | 6-02-PLAN-cold-start-e2e |
| SAFETY-01 | 7 | 7-01-PLAN-safety-bundle |
| SAFETY-02 | 7 | 7-01-PLAN-safety-bundle |
| SAFETY-03 | 7 | 7-01-PLAN-safety-bundle |
| HOMEBREW-01 | 8 | 8-01-PLAN-yaml-eligibility |
| HOMEBREW-02 | 8 | 8-01-PLAN-yaml-eligibility |
| UPGRADE-01 | 9 | 9-01-PLAN-pc-classes-backfill |
| COMBAT-13 | 10 | 10-01-PLAN-smart-monster-driver |
| COMBAT-14 | 10 | 10-02-PLAN-smart-driver-corpus |
| OBS-01 | 11 | 11-01-PLAN-otel-instrumentation |
| OBS-02 | 11 | 11-02-PLAN-phoenix-stack |
| EVAL-01 | 12 | 12-01-PLAN-judge-and-schema |
| EVAL-02 | 12 | 12-02-PLAN-corpus-and-cli |
| EVAL-03 | 12 | 12-02-PLAN-corpus-and-cli |
| MON-01 | 13 | 13-01-PLAN-kpi-monitors |
| MON-02 | 13 | 13-02-PLAN-alerts-degraded-mode |
| MON-03 | 13 | 13-03-PLAN-cost-guard |
| FLAKE-01 | 14 | 14-01-PLAN-flake-fix |
| FLAKE-02 | 14 | 14-01-PLAN-flake-fix |
| FLAKE-03 | 14 | 14-02-PLAN-summary-frontmatter |

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|---|---|---|---|---|
| 1. MCP Client + Local State | v1.0 | 3/3 | ✅ Complete | 2026-05-21 |
| 2. Discord Scaffold + Persistent Views | v1.0 | 3/3 | ✅ Complete | 2026-05-21 |
| 3. Lobby + Character Ingest | v1.0 | 3/3 | ✅ Complete | 2026-05-21 |
| 4. Gameplay — Exploration + Combat | v1.0 | 3/3 | ✅ Complete | 2026-05-22 |
| 5. Reactions + Self-Host Polish | v1.0 | 3/3 | ✅ Complete | 2026-05-23 |
| 6. Debt Paydown + Cold-Start Smoke | v1.1 | 2/2 | Complete   | 2026-05-24 |
| 7. Safety Gap Closure | v1.1 | 1/1 | Complete   | 2026-05-24 |
| 8. YAML Riposte Eligibility | v1.1 | 1/1 | Complete   | 2026-05-24 |
| 9. pc_classes Ingest-Backfill Script | v1.1 | 1/1 | Complete   | 2026-05-24 |
| 10. Smart MonsterDriver | v1.1 | 2/2 | Complete   | 2026-05-24 |
| 11. Phoenix Observability Foundation | v1.2 | 2/2 | Complete   | 2026-05-24 |
| 12. LLM-as-Judge Tactical Scoring | v1.2 | 2/2 | Complete   | 2026-05-24 |
| 13. Production Monitoring + Alerting | v1.2 | 3/3 | Complete   | 2026-05-24 |
| 14. Flake cleanup + planner template hardening | v1.3 | 0/2 | Not started | — |

---
*Last revised: 2026-05-24 after v1.1 Polish research synthesis (Stack + Features + Architecture + Pitfalls all converged on this 5-phase build order)*
