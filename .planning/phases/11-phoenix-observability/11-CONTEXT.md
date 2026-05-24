---
phase: 11-phoenix-observability
milestone: v1.2
generated: 2026-05-24
mode: auto-generated (autonomous-flow, discuss skipped per 'go with recommendations')
source_requirements:
  - OBS-01 (OpenTelemetry instrumentation)
  - OBS-02 (Phoenix stack + dashboards)
source_design:
  - .planning/phases/10-smart-monsterdriver/10-AI-SPEC.md §7 Production Monitoring (the spec deferred from v1.1)
---

# Phase 11 — Phoenix Observability Foundation (CONTEXT)

## Mission

Add OpenTelemetry instrumentation to every AsyncOpenAI call from
`SmartMonsterDriver` and the bot's narration path, ship an optional
self-hostable Arize Phoenix stack via docker-compose, and seed three
default dashboards. Pure observation layer — combat-orchestrator behavior
is unchanged.

## Locked Decisions (autonomous)

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-62** | **Observability is OPT-IN**, gated by `OBSERVABILITY_ENABLED` env (default `false`). When unset/false, NO OTel SDK imports happen at bot startup (lazy import inside `if obs_enabled` block). | Self-hosters without observability needs must not pay startup cost; AI-SPEC's "local-first" constraint extends here |
| **D-63** | **OpenTelemetry SDK is a `[project.optional-dependencies] observability`** group, NOT core. Install via `pip install -e ".[observability]"`. | Honors "Phoenix stack OPTIONAL" PROJECT.md constraint and v1.1's "no new MCP deps" extension |
| **D-64** | **OTLP exporter targets `OTEL_EXPORTER_OTLP_ENDPOINT`**, defaults to `http://localhost:6006/v1/traces` (local Phoenix default port). | Phoenix default; mirrors Phase 8's env-driven config pattern |
| **D-65** | **Span schema** (required attributes on EVERY span emitted by smart-driver path):<br>- `eldritch.monster.id` (str)<br>- `eldritch.channel.id` (str)<br>- `eldritch.combat.round` (int)<br>- `eldritch.driver.path` (Literal["smart", "random", "cache", "mixed"])<br>- `eldritch.latency_ms` (int)<br>- `eldritch.tokens.input` (int, 0 if cache/random)<br>- `eldritch.tokens.output` (int, 0 if cache/random)<br>- `eldritch.fallback.reason` (Optional[Literal["timeout","json_parse","hallucinated_id","refusal","generic","rate_limit"]]) | AI-SPEC §7 KPIs need these for P99 latency, fallback-rate-by-reason, and cache-hit dashboards |
| **D-66** | **Instrument at the `SmartMonsterDriver._pick_target` boundary**, NOT inside `AsyncOpenAI` itself. Reason: we already wrap retries/fallback at the driver layer; one span per `_pick_target` invocation gives a clean "tactical decision" trace, with sub-spans for `oracle.call`, `validate`, `fallback`. | Avoids double-counting from `OpenAIInstrumentor` if user also enables it; keeps the span hierarchy aligned with what dashboards care about |
| **D-67** | **Three default dashboards (Phoenix JSON exports in `database/dashboards/`)**: (1) `latency.json` — P50/P95/P99 from `eldritch.latency_ms` split by `eldritch.driver.path`; (2) `fallback.json` — count by `eldritch.fallback.reason` over time; (3) `cache.json` — cache hit rate per `(eldritch.channel.id, eldritch.combat.round)`. Loaded via Phoenix's dataset bootstrap helper at container startup. | Match the 3 KPIs MON-01 will live-monitor; gives operators something to look at on day 1 |
| **D-68** | **Smoke test via integration test** (`tests/integration/test_observability_smoke.py`): boot bot with `OBSERVABILITY_ENABLED=true`, run 5 mocked combat turns, assert ≥ 5 spans landed at Phoenix UI's HTTP API within 30s (HTTP poll with backoff). Skip when CI doesn't have docker. | Detects regressions in instrumentation wiring without requiring full Phoenix stack in CI |
| **D-69** | **docker-compose.observability.yml shape**: 2 services — `phoenix` (arizephoenix/phoenix:latest) + `otel-collector` (otel/opentelemetry-collector-contrib:latest). Network: `eldritch_obs` bridge. Volumes: `phoenix-data` for trace persistence across restarts. Port mappings: `:6006` Phoenix UI, `:4317` OTLP gRPC, `:4318` OTLP HTTP. | Phoenix official quickstart; v1.2-grade simplicity (no auth, no TLS — self-hoster's local box) |
| **D-70** | **Module location**: `src/eldritch_dm/observability/__init__.py` (new package), `src/eldritch_dm/observability/tracer.py` (TracerProvider setup), `src/eldritch_dm/observability/instrumentation.py` (helper to wrap a callable in a span). Tests at `tests/observability/`. | New concern; deserves its own package; mirrors `tools/` from Phase 9 |

## Implementation Plan Sketch

**Plan 01 (11-01-PLAN.md) — OTel instrumentation + span schema:**
1. Add `[project.optional-dependencies] observability` group: `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-openai` (or hand-rolled)
2. `eldritch_dm.observability.tracer.init_tracing()` reads `OBSERVABILITY_ENABLED` env; sets up `TracerProvider` + `OTLPSpanExporter` if enabled (no-op otherwise)
3. `eldritch_dm.observability.instrumentation.traced_decision(name)` decorator/context-manager that creates a span with the D-65 attribute schema; SmartMonsterDriver wraps `_pick_target` with it
4. Bot's narration path also wrapped (`narration.respond` or wherever the AsyncOpenAI client is called for narrative text)
5. Unit tests: span attributes correct, lazy import works (no SDK imports when disabled), schema validation

**Plan 02 (11-02-PLAN.md) — Phoenix stack + dashboards + smoke:**
1. `docker-compose.observability.yml` per D-69
2. `database/dashboards/{latency,fallback,cache}.json` — Phoenix dashboard exports per D-67
3. Phoenix bootstrap script (`scripts/observability/seed-dashboards.sh`) that POSTs the 3 dashboards to Phoenix HTTP API on first container startup (idempotent — skip if already present)
4. README "Optional: observability stack" section with `docker compose -f docker-compose.observability.yml up -d` recipe + a 5-line snippet showing how to set `OBSERVABILITY_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT`
5. Integration smoke test per D-68

## Success Criteria (from ROADMAP)

1. OTel instrumentation wraps every AsyncOpenAI call (SmartMonsterDriver + narration)
2. docker-compose.observability.yml brings up Phoenix + OTLP collector
3. 3 default dashboards seeded (latency P50/P95/P99, fallback rate by reason, cache hit rate)
4. Smoke test: 5 combat turns → spans in Phoenix UI within 30s
5. Bot runs WITHOUT observability stack (opt-in, default off)

## Deferred (post-v1.2)

- Authentication on Phoenix UI (self-hosters' local box, low risk for v1.2)
- TLS for OTLP traffic (intra-localhost in v1.2)
- Multi-tenant Phoenix (one Phoenix per self-hoster — single-tenant assumption)
- Trace sampling above 100% (volume small enough to log everything in v1.2)
