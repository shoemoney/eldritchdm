# Roadmap: EldritchDM

## Milestones

- ✅ **v1.0 MVP — Mechanically Honest AI Dungeon Master** — Phases 1-5 (shipped 2026-05-23) — see [`milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Polish** — Phases 6-10 (shipped 2026-05-24) — see [`milestones/v1.1-ROADMAP.md`](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Quality Flywheel** — Phases 11-13 (shipped 2026-05-24) — see [`milestones/v1.2-ROADMAP.md`](milestones/v1.2-ROADMAP.md)
- ⚠️ **v1.3 Hygiene Sweep** — Phase 14 (shipped 2026-05-25, partial) — see [`milestones/v1.3-ROADMAP.md`](milestones/v1.3-ROADMAP.md)
- ✅ **v1.4 Writer-Queue Reliability** — Phase 15 (shipped 2026-05-25) — see [`milestones/v1.4-ROADMAP.md`](milestones/v1.4-ROADMAP.md)
- 🚧 **v1.5 Cache Architecture** — Phases 16-18 (in progress) — dm20 MCP cache + persistent character cache + opt-in narration cache (mechanical-honesty guarded)

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

<details>
<summary>⚠️ v1.3 Hygiene Sweep (Phase 14) — SHIPPED 2026-05-25 (partial)</summary>

- [x] **Phase 14**: Flake cleanup + planner template hardening (2/2 plans, partial closure on FLAKE-02)

**Final stats:** 1 phase · 2 plans · 8 commits · 2.5/3 requirements (FLAKE-02 accepted-partial). Test failures −75% (8→2). Surfaced WRITER-QUEUE-HANG-01 as v1.4 follow-up.

**Tag:** `v1.3` · **Archive:** [`milestones/v1.3-ROADMAP.md`](milestones/v1.3-ROADMAP.md)

</details>

<details>
<summary>✅ v1.4 Writer-Queue Reliability (Phase 15) — SHIPPED 2026-05-25</summary>

- [x] **Phase 15**: Writer-queue shutdown rewrite + FLAKE-02 closure (1/1 ship plan + halt-report artifact)

**Final stats:** 1 phase · 1 ship plan + 1 halt artifact · ~6 commits · 3/3 requirements satisfied. Closed v1.3's carried FLAKE-02 partial. FIRST FULL-SUITE GREEN since v1.1 — 1244 passed, 17 skipped, 0 failed in 2 consecutive runs. Halt-and-rescope cycle preserved as honest-report artifact.

**Tag:** `v1.4` · **Archive:** [`milestones/v1.4-ROADMAP.md`](milestones/v1.4-ROADMAP.md)

</details>


## 🚧 v1.5 Cache Architecture (Phases 16-18)

### Phase 16: dm20 MCP query cache
**Goal**: Multi-level cache (L1 in-process LRU + L2 SQLite) wrapping `MCPClient` for dm20 rules-lookup hot path. Auto-invalidation on schema version change. KPIs via Phase 11 OTel.
**Mode:** mvp (perf infrastructure)
**Depends on**: Phase 15 (clean test baseline)
**Requirements**: MCPCACHE-01, MCPCACHE-02, MCPCACHE-03
**Plans**:
- [ ] Plan 01: L1 LRU + L2 SQLite scaffolding (`feat(16-01): MCPCache L1+L2 with TTL + opt-out env gates`)
- [ ] Plan 02: Invalidation hook + KPI integration (`feat(16-02): cache invalidation on schema bump + Phase 11 OTel KPI integration`)

### Phase 17: Persistent character cache
**Goal**: Cache character snapshots across bot restarts; ETag-based lazy refresh with TTL fallback. Eliminates first-turn UX latency.
**Mode:** mvp (UX perf)
**Depends on**: Phase 16 (cache patterns established)
**Requirements**: CHARCACHE-01, CHARCACHE-02, CHARCACHE-03
**Plans**:
- [ ] Plan 01: Snapshot SQLite + ETag refresh path (`feat(17-01): character snapshot cache with ETag-based lazy refresh`)
- [ ] Plan 02: TTL fallback + cache-clear CLI (`feat(17-02): TTL fallback + eldritch-dm-cache-clear --characters`)

### Phase 18: Narration response cache
**Goal**: Opt-in narration cache with HARD mechanical-honesty gate — only pure narrative text is cacheable; any response with HP/AC/damage/effect tokens bypasses. Operator off-switch + cost-savings observability.
**Mode:** mvp (cost reduction with safety guardrails)
**Depends on**: Phase 16 (cache patterns), Phase 13 (cost calculator for savings reports)
**Requirements**: NARRCACHE-01, NARRCACHE-02, NARRCACHE-03
**Plans**:
- [ ] Plan 01: Narration cache + NarrCacheGate fail-closed classifier (`feat(18-01): opt-in narration cache + mechanical-honesty gate`)
- [ ] Plan 02: Operator off-switch + savings observability (`feat(18-02): runtime cache-disable + cost-savings KPI + cache-stats CLI`)


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
| HANG-01 | 15 | 15-01-PLAN-reproduce-hang |
| HANG-02 | 15 | 15-02-PLAN-cancellable-shutdown |
| HANG-03 | 15 | 15-03-PLAN-flake02-closure |
| MCPCACHE-01 | 16 | 16-01-PLAN-mcp-cache-scaffolding |
| MCPCACHE-02 | 16 | 16-01-PLAN-mcp-cache-scaffolding |
| MCPCACHE-03 | 16 | 16-02-PLAN-invalidation-kpis |
| CHARCACHE-01 | 17 | 17-01-PLAN-snapshot-etag |
| CHARCACHE-02 | 17 | 17-01-PLAN-snapshot-etag |
| CHARCACHE-03 | 17 | 17-02-PLAN-ttl-cli |
| NARRCACHE-01 | 18 | 18-01-PLAN-narr-cache-gate |
| NARRCACHE-02 | 18 | 18-01-PLAN-narr-cache-gate |
| NARRCACHE-03 | 18 | 18-02-PLAN-offswitch-observability |

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
| 14. Flake cleanup + planner template hardening | v1.3 | 2/2 | Complete   | 2026-05-25 |
| 15. Writer-queue shutdown rewrite + FLAKE-02 closure | v1.4 | 1/1 | Complete   | 2026-05-25 |

---
*Last revised: 2026-05-24 after v1.1 Polish research synthesis (Stack + Features + Architecture + Pitfalls all converged on this 5-phase build order)*
