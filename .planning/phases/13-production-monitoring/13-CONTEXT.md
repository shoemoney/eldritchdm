---
phase: 13-production-monitoring
milestone: v1.2
generated: 2026-05-24
mode: auto-generated (autonomous-flow, discuss skipped per 'go with recommendations')
source_requirements:
  - MON-01 (KPI live monitors + Prometheus /metrics endpoint)
  - MON-02 (alerts.yaml + degraded-mode trigger + auto-recover)
  - MON-03 (cost guard + budget cap + report CLI)
source_design:
  - .planning/phases/10-smart-monsterdriver/10-AI-SPEC.md §7 (KPIs + Alert Thresholds + Cost Monitor)
  - .planning/phases/10-smart-monsterdriver/10-AI-SPEC.md §6 (Offline Flywheel)
---

# Phase 13 — Production Monitoring + Alerting (CONTEXT)

## Mission

Final piece of the quality flywheel. Operationalize the AI-SPEC §7 KPIs and
alert thresholds: KPI monitors driven by Phase 11's OTel spans, opt-in
Prometheus `/metrics` endpoint, alerts.yaml-driven degraded-mode auto-trip
on latency breach with auto-recovery, and a cost guard with daily LLM
budget cap. After Phase 13, the SmartMonsterDriver has full
data-driven feedback: span → monitor → judge score → cost → alert.

## Locked Decisions (autonomous)

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-83** | **KPI monitors are computed in-process from a rolling 5-minute span buffer**, NOT polled from Phoenix. Phoenix is the visualization backend; the monitors must run even without Phoenix (self-hoster choice). | AI-SPEC §7 alerts must fire even when observability stack is off |
| **D-84** | **Prometheus `/metrics` endpoint at `:9090/metrics`**, served by an `aiohttp` (already in deps via httpx? — verify) or stdlib `aiohttp.web` mini-server, gated by `OBSERVABILITY_METRICS_ENDPOINT=true`. Off by default. Exposes the 5 KPIs as Prometheus gauges + counters. | Industry-standard scrape target; self-hosters with their own Prometheus can scrape |
| **D-85** | **5 KPIs tracked**:<br>1. `eldritch_smart_driver_latency_p99_ms` (gauge, 5min rolling)<br>2. `eldritch_smart_driver_success_rate` (gauge, smart-path-without-fallback / total over 5min)<br>3. `eldritch_smart_driver_tactical_score` (gauge, fed by Phase 12's TacticalJudge IF eval has been run; else `nan`)<br>4. `eldritch_smart_driver_refusal_rate` (gauge, 5min)<br>5. `eldritch_smart_driver_fallback_rate` (gauge, 5min) | AI-SPEC §7 Key Performance Indicators verbatim |
| **D-86** | **alerts.yaml ships at `database/alerts.yaml`**, parsed with the same 3-tier loader pattern from Phase 8 (env > user > repo default). Schema: `rules: [{name, severity (critical|high|warning), condition (kpi + op + threshold + window_minutes), action (degrade|log|throttle|webhook), routing}]`. Pydantic-validated; safe_load only. | Phase 8 pattern proven; extensible without code edits |
| **D-87** | **Degraded mode trigger**: when `eldritch_smart_driver_latency_p99_ms > 1500` for 5 consecutive minutes → set `MONSTER_DRIVER=random` at runtime via a process-wide mutable `Settings.monster_driver_override` field. Smart driver factory consults the override BEFORE the env. Auto-recovers when P99 returns < 1200ms for 5min. Logged with `eldritch.degraded_mode.entered` / `eldritch.degraded_mode.exited` structlog events. | AI-SPEC §7 "Critical: Latency P99 > 1500ms for 5 consecutive minutes (Triggers Degraded Mode)" |
| **D-88** | **Integration test for degraded mode**: synthetic latency injection → assert factory returns `MonsterDriver` (random) instead of `SmartMonsterDriver`; reset latency → assert recovery after 5min hits 1200ms threshold. Use freezegun or asyncio.sleep skipped via clock-monkey-patch. | Phase 10 used `asyncio.wait_for` mocks; same pattern |
| **D-89** | **Cost calculator** at `src/eldritch_dm/observability/cost.py`: maps `(model_name, tokens_input, tokens_output)` → USD. Token pricing table at `database/pricing.yaml` (3-tier loader). Default table covers: ShoeGPT (local — $0.00/tok), `gpt-4o`, `gpt-4o-mini`, `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-7` with current public pricing (sourced via Brave/Tavily research). Calculator includes a unit-test budget of ±5% drift vs known-good values for 5 sample workloads. | AI-SPEC §7 Cost Monitor — practical implementation needs a pricing source-of-truth |
| **D-90** | **`eldritch-dm-cost-report` CLI**: new `[project.scripts]` entry. Flags: `--since DATE` (default 24h ago), `--by-model` (group by model name), `--by-channel` (group by Discord channel), `--format json|markdown` (default markdown), `--budget USD` (override $ELDRITCH_DAILY_LLM_BUDGET_USD). Reads spans from local SQLite-backed span buffer (NOT Phoenix — must work without Phoenix). | Self-hosters get a daily-spend tool that works offline |
| **D-91** | **Daily LLM budget cap**: `ELDRITCH_DAILY_LLM_BUDGET_USD` env (default `5.00`). When breach detected: (a) structured-log `eldritch.budget.exceeded` with `spent_usd`, `cap_usd`, `over_by_usd`; (b) force degraded mode (D-87 mechanism); (c) opt: emit Discord DM to bot owner via existing warning channel (deferred to v1.3 if Phase 13 runs long). Alert at $2/day threshold per AI-SPEC §6 Offline Flywheel. | Operator safety net — keeps a runaway prompt loop from billing $100 overnight |
| **D-92** | **Span buffer storage**: lightweight SQLite at `~/.eldritch/spans.sqlite` (created lazily on first observability boot). Schema: rolling 7-day buffer; older spans auto-pruned. Indexed by `(timestamp, monster.id, channel.id)`. Cost report + KPI monitors read from this; Phoenix gets the SAME spans via OTLP (dual sink: OTLP + local SQLite). | Need queryable storage when Phoenix is off; SQLite is already a stack dep |
| **D-93** | **Module location**: `src/eldritch_dm/observability/{kpi.py, alerts.py, cost.py, metrics_endpoint.py, span_buffer.py}` + `src/eldritch_dm/tools/cost_report.py` (CLI entry). Tests at `tests/observability/test_{kpi,alerts,cost,metrics,buffer}.py` + `tests/integration/test_degraded_mode.py` + `tests/tools/test_cost_report.py`. | Extends Phase 11's observability package; CLI mirrors Phase 9 tools pattern |
| **D-94** | **Three plans (matches ROADMAP)**:<br>13-01: KPI monitors + span buffer + Prometheus /metrics endpoint<br>13-02: alerts.yaml loader + degraded-mode trigger + auto-recover integration test<br>13-03: cost guard + budget cap + eldritch-dm-cost-report CLI | ROADMAP plans section |

## Success Criteria (from ROADMAP)

1. KPIs tracked from OTel spans: 5 KPIs per D-85
2. Prometheus `/metrics` endpoint at :9090/metrics, opt-in via env (off by default)
3. `database/alerts.yaml` with critical/high/warning routing per D-86
4. Degraded mode auto-trip + auto-recover (integration test verifies trip → recover)
5. `eldritch-dm-cost-report` CLI emits daily spend from token spans; hard cap via env
6. Cost calculator within ±5% of provider pricing across 5 sample workloads

## Deferred (post-v1.2)

- Discord DM-to-owner on budget breach (v1.3 — needs owner-id config flow)
- Multi-day aggregation in cost-report (v1.2 just does daily; weekly/monthly later)
- Webhook routing in alerts.yaml (v1.2 just does file/syslog; webhooks v1.3)
- Cost drift detection (compare actual provider invoice vs calculated — needs provider API)
- Grafana dashboards alternative to Phoenix (Prom endpoint enables this — operators can self-build)
