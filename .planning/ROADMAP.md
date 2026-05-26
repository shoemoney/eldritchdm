# Roadmap: EldritchDM

## Milestones

- ✅ **v1.0 MVP — Mechanically Honest AI Dungeon Master** — Phases 1-5 (shipped 2026-05-23) — see [`milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Polish** — Phases 6-10 (shipped 2026-05-24) — see [`milestones/v1.1-ROADMAP.md`](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Quality Flywheel** — Phases 11-13 (shipped 2026-05-24) — see [`milestones/v1.2-ROADMAP.md`](milestones/v1.2-ROADMAP.md)
- ⚠️ **v1.3 Hygiene Sweep** — Phase 14 (shipped 2026-05-25, partial) — see [`milestones/v1.3-ROADMAP.md`](milestones/v1.3-ROADMAP.md)
- ✅ **v1.4 Writer-Queue Reliability** — Phase 15 (shipped 2026-05-25) — see [`milestones/v1.4-ROADMAP.md`](milestones/v1.4-ROADMAP.md)
- ✅ **v1.5 Cache Architecture** — Phases 16-18 (shipped 2026-05-25) — see [`milestones/v1.5-ROADMAP.md`](milestones/v1.5-ROADMAP.md)
- ✅ **v1.6 UX/Feature Expansion** — Phases 19-22 (shipped 2026-05-25) — see [`milestones/v1.6-ROADMAP.md`](milestones/v1.6-ROADMAP.md)
- ✅ **v1.7 Integration & Polish** — Phases 23-24 (shipped 2026-05-25) — see [`milestones/v1.7-ROADMAP.md`](milestones/v1.7-ROADMAP.md)
- ✅ **v1.8 Multi-Channel Hardening** — Phases 25-26 (shipped 2026-05-25) — see [`milestones/v1.8-ROADMAP.md`](milestones/v1.8-ROADMAP.md)
- ✅ **v1.9 Performance Baseline + Tuning** — Phases 27-28 (shipped 2026-05-26) — see [`milestones/v1.9-ROADMAP.md`](milestones/v1.9-ROADMAP.md)
- ✅ **v1.10 Operator Deployment Polish** — Phases 29-30 (shipped 2026-05-26) — see [`milestones/v1.10-ROADMAP.md`](milestones/v1.10-ROADMAP.md)
- ✅ **v1.11 Security Audit Refresh** — Phases 31-32 (shipped 2026-05-26 · 0 findings) — see [`milestones/v1.11-ROADMAP.md`](milestones/v1.11-ROADMAP.md)
- ✅ **v1.12 Final Consolidation** — Phase 33 (shipped 2026-05-26) — see [`milestones/v1.12-ROADMAP.md`](milestones/v1.12-ROADMAP.md)
- ✅ **v1.13 Open-Source Hygiene** — Phase 34 (shipped 2026-05-26) — CODE_OF_CONDUCT.md + SPDX headers on 105 src files
- ✅ **v1.14 Test Coverage Audit** — Phase 35 (shipped 2026-05-26, partial — subset 63.7%) — see [`COVERAGE-AUDIT-v1.14.md`](COVERAGE-AUDIT-v1.14.md)

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


<details>
<summary>✅ v1.5 Cache Architecture (Phases 16-18) — SHIPPED 2026-05-25</summary>

- [x] **Phase 16**: dm20 MCP query cache (2/2 plans)
- [x] **Phase 17**: Persistent character cache (2/2 plans)
- [x] **Phase 18**: Narration response cache (2/2 plans)

**Final stats:** 3 phases · 6 plans · ~18 commits · 9/9 requirements satisfied · 276 new tests · 8/8 import-linter contracts kept · honest-report contract delivered 3× (allow-list correction in P16, ETag savings narrative in P17, no-narration-site finding in P18).

**Tag:** `v1.5` · **Archive:** [`milestones/v1.5-ROADMAP.md`](milestones/v1.5-ROADMAP.md)

</details>


<details>
<summary>✅ v1.6 UX/Feature Expansion (Phases 19-22) — SHIPPED 2026-05-25</summary>

- [x] **Phase 19**: Streaming "monster is thinking" embed (2/2 plans)
- [x] **Phase 20**: AOE / multi-target tactic selection (2/2 plans)
- [x] **Phase 21**: Cross-round monster memory (2/2 plans)
- [x] **Phase 22**: Operator quality-of-life bundle (2/2 plans)

**Final stats:** 4 phases · 8 plans · ~24 commits · 12/12 requirements satisfied · 122 new tests · 8/8 import-linter contracts kept · honest-report contract delivered 2 v1.7 follow-ups (cog-side session-close hook + REQUIREMENTS atomicity doc-fix).

**Tag:** `v1.6` · **Archive:** [`milestones/v1.6-ROADMAP.md`](milestones/v1.6-ROADMAP.md)

</details>


<details>
<summary>✅ v1.7 Integration & Polish (Phases 23-24) — SHIPPED 2026-05-25</summary>

- [x] **Phase 23**: Honest-gap closure — cog-wiring + AOE prompt (2/2 plans, WIRE-01 deferred — dm20 event surface)
- [x] **Phase 24**: CI matrix + Phoenix cache dashboards (2/2 plans)

**Final stats:** 2 phases · 4 plans · ~16 commits · 5/6 requirements satisfied (1 deferred) · 14+ new tests · 14 SUMMARY frontmatter backfills · cross-platform CI matrix · 3 bundled cache dashboards · **full suite 1644 passed, 17 skipped, 0 failed**.

**Tag:** `v1.7` · **Archive:** [`milestones/v1.7-ROADMAP.md`](milestones/v1.7-ROADMAP.md)

</details>


<details>
<summary>✅ v1.8 Multi-Channel Hardening (Phases 25-26) — SHIPPED 2026-05-25</summary>

- [x] **Phase 25**: Multi-channel concurrency stress tests (2/2 plans, 3-for-3 GREEN, no bugs surfaced)
- [x] **Phase 26**: Operational dashboards + tooling polish (2/2 plans, 3 new dashboards, backfill auto-discovery)

**Final stats:** 2 phases · 4 plans · ~14 commits · 6/6 requirements satisfied · 4-channel stress 3-for-3 green · 9 total bundled dashboards · UPSTREAM-ISSUES.md → 3 entries · 39 SUMMARY files frontmatter-compliant.

**Tag:** `v1.8` · **Archive:** [`milestones/v1.8-ROADMAP.md`](milestones/v1.8-ROADMAP.md)

</details>


<details>
<summary>✅ v1.9 Performance Baseline + Tuning (Phases 27-28) — SHIPPED 2026-05-26</summary>

- [x] **Phase 27**: Profiling + latency budgets (2/2 plans)
- [x] **Phase 28**: Targeted optimizations + perf CLI (2/2 plans — TUNE-01 Branch B no-targets closure)

**Final stats:** 2 phases · 4 plans · ~16 commits · 6/6 reqs satisfied · `perf-baseline-v1.9.0.json` baseline · `eldritch-dm-perf-baseline` CLI · `.github/workflows/perf.yml` weekly CI · slowest hot-path p99 = 3.573ms (0.12% of budget) · 1662 tests passing.

**Tag:** `v1.9` · **Archive:** [`milestones/v1.9-ROADMAP.md`](milestones/v1.9-ROADMAP.md)

</details>


<details>
<summary>✅ v1.10 Operator Deployment Polish (Phases 29-30) — SHIPPED 2026-05-26</summary>

- [x] **Phase 29**: Bundled docker-compose for full stack (2/2 plans)
- [x] **Phase 30**: INSTALL refresh + troubleshooting runbook (2/2 plans)

**Final stats:** 2 phases · 4 plans · ~17 commits · 6/6 reqs satisfied · single-command Docker setup · 14-FAQ TROUBLESHOOTING.md · 11-version UPGRADE.md · bidirectional cross-links.

**Tag:** `v1.10` · **Archive:** [`milestones/v1.10-ROADMAP.md`](milestones/v1.10-ROADMAP.md)

</details>


<details>
<summary>✅ v1.11 Security Audit Refresh (Phases 31-32) — SHIPPED 2026-05-26 (0 findings · Branch B)</summary>

- [x] **Phase 31**: Security audit investigation (1/1 plan · 0 findings across 4 severity tiers)
- [x] **Phase 32**: Security remediation (1/1 plan · Branch B — nothing to fix)

**Final stats:** 2 phases · 2 plans · ~6 commits · 6/6 reqs satisfied · 8 attack surfaces audited · 289-line audit document · SECURITY-BACKLOG.md future-tracking surface created · 0 CRITICAL/HIGH/MEDIUM/LOW findings.

**Tag:** `v1.11` · **Archive:** [`milestones/v1.11-ROADMAP.md`](milestones/v1.11-ROADMAP.md)

</details>

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
| STREAM-01 | 19 | 19-01-PLAN-thinking-embed |
| STREAM-02 | 19 | 19-02-PLAN-fallback-optout |
| STREAM-03 | 19 | 19-02-PLAN-fallback-optout |
| AOE-01 | 20 | 20-01-PLAN-multi-target-schema |
| AOE-02 | 20 | 20-02-PLAN-prompt-corpus |
| AOE-03 | 20 | 20-02-PLAN-prompt-corpus |
| MEM-01 | 21 | 21-01-PLAN-memory-class |
| MEM-02 | 21 | 21-01-PLAN-memory-class |
| MEM-03 | 21 | 21-02-PLAN-persistence |
| OPQOL-01 | 22 | 22-01-PLAN-hot-reload |
| OPQOL-02 | 22 | 22-02-PLAN-dm-and-invalidation |
| OPQOL-03 | 22 | 22-02-PLAN-dm-and-invalidation |
| WIRE-01 | 23 | 23-01-PLAN-cog-wiring |
| WIRE-02 | 23 | 23-01-PLAN-cog-wiring |
| WIRE-03 | 23 | 23-02-PLAN-aoe-prompt-integration |
| POLISH-01 | 24 | 24-01-PLAN-ci-matrix |
| POLISH-02 | 24 | 24-02-PLAN-cache-dashboards-docfix |
| POLISH-03 | 24 | 24-02-PLAN-cache-dashboards-docfix |
| CONC-01 | 25 | 25-01-PLAN-stress-test |
| CONC-02 | 25 | 25-01-PLAN-stress-test |
| CONC-03 | 25 | 25-02-PLAN-fix-or-escalate |
| OPSDASH-01 | 26 | 26-01-PLAN-3-more-dashboards |
| OPSDASH-02 | 26 | 26-02-PLAN-auto-discover-backfill |
| OPSDASH-03 | 26 | 26-02-PLAN-auto-discover-backfill |
| PROFILE-01 | 27 | 27-01-PLAN-profiler |
| PROFILE-02 | 27 | 27-02-PLAN-perf-docs |
| PROFILE-03 | 27 | 27-01-PLAN-profiler |
| TUNE-01 | 28 | 28-01-PLAN-top3-optimizations |
| TUNE-02 | 28 | 28-02-PLAN-perf-cli-ci |
| TUNE-03 | 28 | 28-02-PLAN-perf-cli-ci |
| DEPLOY-01 | 29 | 29-01-PLAN-docker-compose |
| DEPLOY-02 | 29 | 29-01-PLAN-docker-compose |
| DEPLOY-03 | 29 | 29-02-PLAN-docker-smoke |
| DOCS-01 | 30 | 30-01-PLAN-install-refresh |
| DOCS-02 | 30 | 30-02-PLAN-troubleshooting-upgrade |
| DOCS-03 | 30 | 30-02-PLAN-troubleshooting-upgrade |
| SECAUDIT-01 | 31 | 31-01-PLAN-audit |
| SECAUDIT-02 | 31 | 31-01-PLAN-audit |
| SECAUDIT-03 | 31 | 31-01-PLAN-audit |
| SECFIX-01 | 32 | 32-01-PLAN-remediation |
| SECFIX-02 | 32 | 32-01-PLAN-remediation |
| SECFIX-03 | 32 | 32-02-PLAN-backlog |

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
