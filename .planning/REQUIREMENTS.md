# EldritchDM — Requirements (v1.2 Quality Flywheel)

**Milestone:** v1.2 Quality Flywheel
**Goal:** Close the loop on SmartMonsterDriver — add Arize Phoenix observability, an LLM-as-judge tactical scoring rubric with curated eval dataset, and production monitoring/alerting. Answers "are monsters fair AND smart" with data, not just compiles.
**Total v1.2 requirements:** 8 across 3 categories.
**Driven by:** v1.1 Phase 10's CONTEXT D-59 deferral + AI-SPEC §5 (Evaluation Strategy) + §7 (Production Monitoring).

---

## v1.2 Requirements

### OBS — Phoenix Observability Foundation (Phase 11)

- [x] **OBS-01**: OpenTelemetry instrumentation wraps every `AsyncOpenAI` call from `SmartMonsterDriver` and the bot's narration path. Spans expose: `monster.id`, `channel.id`, `combat.round`, `driver.path` (smart|random|cache), `latency_ms`, `tokens.input`, `tokens.output`, `fallback.reason` (timeout|json_parse|hallucinated_id|refusal|generic). OTLP exporter targets `OTEL_EXPORTER_OTLP_ENDPOINT` env var; defaults to local Phoenix at `http://localhost:6006/v1/traces`. NO change to combat-orchestrator behavior — pure observation layer.
- [x] **OBS-02**: `docker-compose.observability.yml` ships Arize Phoenix + OTLP collector for self-hosters. README section "Optional: observability stack" documents `docker compose -f docker-compose.observability.yml up -d`. Three default Phoenix dashboards seeded via the bundled dataset bootstrap: (1) Smart-driver latency P50/P95/P99, (2) Fallback rate by reason, (3) Cache hit rate per (channel, round). Smoke test: spinning up the stack, running 5 combat turns, confirming spans land in Phoenix UI within 30s.

### EVAL — LLM-as-Judge Tactical Scoring (Phase 12)

- [x] **EVAL-01**: `src/eldritch_dm/eval/judge.py` exports `TacticalJudge` — a separate LLM oracle (model selectable, default ShoeGPT) that scores a `(scenario, smart_decision)` pair on the 4 AI-SPEC §1b dimensions: Tactical Intent (INT-appropriate), Meta-knowledge Guardrails, Narrative Fairness (anti-griefing), Edge-Case Handling (visibility/cover). Returns `JudgeVerdict` pydantic model: `overall_score: float [0,1]`, `per_dimension: dict[str, float]`, `reasoning: str`, `would_a_veteran_dm_approve: bool`. Judge prompt is in `src/eldritch_dm/eval/prompts/judge.txt` (versioned with semantic-version header so eval runs are reproducible).
- [x] **EVAL-02**: `tests/eval/dataset/tactical_corpus.jsonl` ships with 50 hand-curated combat scenarios across 5 archetypes (10 each): low-INT brute, high-INT spellcaster, swarm tactician, predator (anti-griefing bait), edge-case (invisible/cover). Each entry: `{scenario_id, monster_stats, pc_list, environment, expected_target_pool, expected_avoidance, rationale}`. Schema validated by pydantic `ScenarioEntry` at load time; corruption fails loud.
- [x] **EVAL-03**: `eldritch-dm-eval` CLI (new `[project.scripts]`) runs the corpus: for each scenario, invokes `SmartMonsterDriver` directly (NO Discord; bypasses combat orchestrator), captures the choice, feeds `(scenario, choice)` into `TacticalJudge`, aggregates results. Outputs `eval-{timestamp}-{git-sha}.json` summary + Markdown report. Flags: `--dataset`, `--judge-model`, `--driver-model`, `--limit N`, `--baseline path/to/prior-eval.json` (diff mode). Exit codes: 0=passed (avg ≥ 0.7), 1=regression (avg dropped vs baseline), 2=critical (any dimension < 0.5 average).

### MON — Production Monitoring + Alerting (Phase 13)

- [x] **MON-01**: KPI thresholds from AI-SPEC §7 implemented as live monitors driven by the OTel spans (OBS-01). Tracked: P99 latency (target < 1200ms), success rate (target > 98% smart without fallback), tactical score (judge-derived, target > 0.8), refusal rate (target < 0.1%), fallback rate (target < 5% weekly). Per-channel and global aggregations. Phoenix dashboard + Prometheus-compatible `/metrics` endpoint at `:9090/metrics` (toggled by `OBSERVABILITY_METRICS_ENDPOINT=true`).
- [x] **MON-02**: Alert config via `database/alerts.yaml` (3-tier YAML loader like Phase 8): critical/high/warning thresholds + routing (file/syslog/webhook). Default rules: critical=latency P99 > 1500ms for 5min → degraded mode (force `MONSTER_DRIVER=random`), high=fallback rate > 10% → log + maintainer ping, warning=OpenAI 429 detected → throttle. Degraded mode auto-recovers when P99 returns < 1200ms for 5min.
- [x] **MON-03**: Cost guard — `eldritch-dm-cost-report` CLI emits daily LLM-spend estimate from token-count spans. Hard cap: env `ELDRITCH_DAILY_LLM_BUDGET_USD` (default $5); when breached, force degraded mode + structured log. Alert on $2/day threshold (AI-SPEC §6 Offline Flywheel). Tests assert the cost calculator agrees with OpenAI token-pricing within ±5%.

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| OBS-01 | 11 | AI-SPEC §7 Tracing Configuration |
| OBS-02 | 11 | AI-SPEC §7 + self-hoster bundling pattern (mirrors Phase 8 YAML) |
| EVAL-01 | 12 | AI-SPEC §1b Domain Expert dimensions + §5 Judge pattern |
| EVAL-02 | 12 | AI-SPEC §1b Known Failure Modes (need scenarios to detect each) |
| EVAL-03 | 12 | AI-SPEC §6 Offline Flywheel (weekly fallback review needs CLI) |
| MON-01 | 13 | AI-SPEC §7 KPIs |
| MON-02 | 13 | AI-SPEC §7 Alert Thresholds |
| MON-03 | 13 | AI-SPEC §7 Cost Monitor + §6 Offline Flywheel |

## Mode Constraints

- All work respects v1.1's PROJECT.md constraint: local-first, self-hostable, Apple Silicon primary. Phoenix stack is OPTIONAL (off by default); core bot must continue running without it.
- No new MCP dependencies (same constraint as Phase 10).
- All new LLM calls (judge) use the existing AsyncOpenAI/oMLX client pattern.
- Eval dataset is open-source-license-compatible: scenarios are original Apache-2.0 content, NOT derivatives of *The Monsters Know What They're Doing* or other copyrighted material.
