# Roadmap: EldritchDM

## Milestones

- ✅ **v1.0 MVP — Mechanically Honest AI Dungeon Master** — Phases 1-5 (shipped 2026-05-23) — see [`milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Polish** — Phases 6-10 (shipped 2026-05-24) — see [`milestones/v1.1-ROADMAP.md`](milestones/v1.1-ROADMAP.md)
- 🚧 **v1.2 Quality Flywheel** — Phases 11-13 (in progress) — Phoenix observability + LLM-as-judge tactical scoring + production monitoring for SmartMonsterDriver

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

## 🚧 v1.2 Quality Flywheel (Phases 11-13)

### Phase 11: Phoenix Observability Foundation
**Goal**: Add OpenTelemetry instrumentation to every AsyncOpenAI call from SmartMonsterDriver + the bot's narration path, ship an optional self-hostable Arize Phoenix stack via docker-compose, and seed 3 default dashboards (latency P99, fallback rate by reason, cache hit rate). Closes Phase 10's deferred D-59 observability gap.
**Mode:** mvp (observability infrastructure — no user-visible behavior change)
**Depends on**: Phase 10 (SmartMonsterDriver instrumented surface)
**Requirements**: OBS-01, OBS-02
**Success Criteria**:
  1. `OpenAIInstrumentor` wraps every `AsyncOpenAI` call (SmartMonsterDriver + narration); spans expose `monster.id`, `channel.id`, `combat.round`, `driver.path`, `latency_ms`, `tokens.input`, `tokens.output`, `fallback.reason`
  2. `docker-compose.observability.yml` brings up Phoenix + OTLP collector with `docker compose -f ... up -d`; README "Optional: observability stack" section documents it
  3. 3 default dashboards seeded: smart-driver latency P50/P95/P99, fallback rate by reason, cache hit rate per (channel, round)
  4. Smoke test: spin stack → 5 combat turns → spans visible in Phoenix UI within 30s; integration test asserts span count ≥ 5 and required attributes are non-null
  5. Bot continues to run with NO observability stack (Phoenix is opt-in, off by default — feature-flag via `OBSERVABILITY_ENABLED` env var)
**Plans**:
- [ ] Plan 01: OTel instrumentation + span schema (`feat(obs-01): OpenTelemetry instrumentation for AsyncOpenAI calls + smart-driver span schema`)
- [ ] Plan 02: Phoenix stack + dashboards + smoke (`feat(obs-02): docker-compose Phoenix + 3 default dashboards + integration smoke`)

### Phase 12: LLM-as-Judge Tactical Scoring
**Goal**: Build the eval flywheel — a separate `TacticalJudge` LLM oracle scores SmartMonsterDriver decisions against the 4 AI-SPEC §1b dimensions (Tactical Intent, Meta-knowledge Guardrails, Narrative Fairness, Edge-Case Handling), driven by a 50-scenario hand-curated corpus. Shipped via `eldritch-dm-eval` CLI with baseline diff for regression detection.
**Mode:** mvp (eval infrastructure — enables data-driven SmartMonsterDriver tuning)
**Depends on**: Phase 11 (spans inform judge — sees what monster knew vs what it picked)
**Requirements**: EVAL-01, EVAL-02, EVAL-03
**Success Criteria**:
  1. `TacticalJudge` class returns `JudgeVerdict(overall_score, per_dimension, reasoning, would_a_veteran_dm_approve)`; judge prompt versioned in `src/eldritch_dm/eval/prompts/judge.txt`
  2. `tests/eval/dataset/tactical_corpus.jsonl` ships 50 scenarios across 5 archetypes (10 each: low-INT brute, high-INT spellcaster, swarm, predator, edge-case)
  3. `eldritch-dm-eval` CLI runs corpus + judge + outputs `eval-{ts}-{sha}.json` summary; flags `--dataset`, `--judge-model`, `--driver-model`, `--limit`, `--baseline path`
  4. Exit codes: 0 (passed avg ≥ 0.7), 1 (regression vs baseline), 2 (critical: any dimension avg < 0.5)
  5. Corpus is original Apache-2.0 content (not derivative of "The Monsters Know" or other copyrighted material)
  6. Tests: judge schema validation, corpus schema validation, end-to-end CLI smoke (1 scenario, mocked LLM)
**Plans**:
- [ ] Plan 01: TacticalJudge + judge prompt + corpus loader (`feat(eval-01): TacticalJudge model + versioned prompt + ScenarioEntry pydantic schema`)
- [ ] Plan 02: 50-scenario corpus + eldritch-dm-eval CLI + baseline diff (`feat(eval-02-03): 50-scenario corpus + eldritch-dm-eval CLI with --baseline diff mode`)

### Phase 13: Production Monitoring + Alerting
**Goal**: Operationalize the AI-SPEC §7 KPIs and alert thresholds — degraded-mode auto-trip on latency breach, cost-guard with daily LLM budget, Prometheus `/metrics` endpoint for self-hosters running their own observability. Final piece of the quality flywheel.
**Mode:** mvp (production hardening for the v1.1 + v1.2 LLM surface)
**Depends on**: Phase 11 (spans drive monitors), Phase 12 (judge-derived tactical score feeds MON-01)
**Requirements**: MON-01, MON-02, MON-03
**Success Criteria**:
  1. KPIs tracked from OTel spans: P99 latency (< 1200ms), success rate (> 98%), tactical score (judge-derived, > 0.8), refusal rate (< 0.1%), fallback rate (< 5% weekly)
  2. Prometheus `/metrics` endpoint at `:9090/metrics` toggled by `OBSERVABILITY_METRICS_ENDPOINT=true` (off by default; opt-in for self-hosters)
  3. `database/alerts.yaml` (3-tier loader pattern like Phase 8): critical=P99>1500ms for 5min → degraded mode (force `MONSTER_DRIVER=random`); high=fallback>10% → log + maintainer ping; warning=429 detected → throttle
  4. Degraded mode auto-recovers when P99 returns < 1200ms for 5min; integration test verifies trip + auto-recover
  5. `eldritch-dm-cost-report` CLI emits daily LLM spend from token spans; hard cap via `ELDRITCH_DAILY_LLM_BUDGET_USD` (default $5); breach forces degraded mode
  6. Cost calculator agrees with provider token-pricing within ±5% across 5 sample workloads
**Plans**:
- [ ] Plan 01: KPI monitors + Prometheus metrics endpoint (`feat(mon-01): KPI live monitors from OTel spans + opt-in /metrics endpoint`)
- [ ] Plan 02: alerts.yaml + degraded-mode trigger + auto-recover (`feat(mon-02): alerts.yaml 3-tier loader + degraded-mode latency trigger + auto-recover integration test`)
- [ ] Plan 03: cost guard + budget cap + report CLI (`feat(mon-03): eldritch-dm-cost-report CLI + ELDRITCH_DAILY_LLM_BUDGET_USD enforcement`)

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

---
*Last revised: 2026-05-24 after v1.1 Polish research synthesis (Stack + Features + Architecture + Pitfalls all converged on this 5-phase build order)*
