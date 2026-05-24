---
phase: 11-phoenix-observability
plan: "02"
subsystem: observability
tags: [phoenix, docker, dashboards, smoke-test, self-host]
requires:
  - 11-01 (Plan 01 — instrumentation must be in place first)
provides:
  - docker-compose.observability.yml
  - database/dashboards/{latency,fallback,cache}.json
  - scripts/observability/seed-dashboards.sh
  - README "Optional: observability stack" recipe
  - bot setup_hook init_tracing() wire-in
  - tests/integration/test_observability_smoke.py
affects:
  - src/eldritch_dm/bot/bot.py (setup_hook calls init_tracing)
  - README.md (new section)
  - .planning/REQUIREMENTS.md (OBS-01 and OBS-02 ticked)
tech-stack:
  added:
    - arizephoenix/phoenix Docker image (operator-side, not a Python dep)
  patterns:
    - "Spec, not import": dashboard JSON is OUR-format spec describing query intent, not Phoenix-importable format (Phoenix's dashboard schema is not stable for v1.2)
    - Idempotent seed: GET /v1/projects -> POST {name, description} if absent
    - Best-effort seeding: WARN on Phoenix HTTP API drift, never fail bot startup
key-files:
  created:
    - docker-compose.observability.yml
    - database/dashboards/latency.json
    - database/dashboards/fallback.json
    - database/dashboards/cache.json
    - scripts/observability/seed-dashboards.sh (executable)
    - tests/integration/test_observability_smoke.py
  modified:
    - src/eldritch_dm/bot/bot.py (setup_hook init_tracing() call)
    - README.md (new "Optional: observability stack" section)
    - .planning/REQUIREMENTS.md (OBS-01 and OBS-02 ticked [x])
decisions:
  - D-67a (sub): Dashboards ship as OUR-format spec JSON (schema_version=1) plus query_recipe field. Phoenix has no stable importable dashboard JSON schema; seed script creates Phoenix projects, operator reconstructs views in the UI (or pastes the documented query_recipe).
  - D-69a (sub): docker-compose simplified to Phoenix-only (no separate otel-collector sidecar). Phoenix natively accepts OTLP HTTP at :6006 and :4318. Operators wanting a collector hop add the service themselves; documented in compose header.
  - D-68a (sub): Smoke test asserts BatchSpanProcessor.force_flush() returns True (validates wire end-to-end of OUR side). Does NOT poll Phoenix's HTTP query API — that surface has drifted across versions; operator opens the UI for query verification.
  - Port discriminator: code default OTEL_EXPORTER_OTLP_ENDPOINT remains http://localhost:6006/v1/traces (Phoenix unified port). README documents :4318 fallback for operators on Phoenix images that disable the unified port.
metrics:
  duration: ~20 minutes
  completed: 2026-05-24
---

# Phase 11 Plan 02: Phoenix stack + dashboards + smoke test — Summary

## One-liner

Ships the operator-facing pieces — docker-compose Phoenix stack, three dashboard spec JSONs with `query_recipe` documentation, idempotent best-effort seed script, README setup recipe, and a smoke test that validates `force_flush()` end-to-end and skips cleanly without docker.

## What landed

- `docker-compose.observability.yml` brings up Phoenix (`arizephoenix/phoenix:latest`) exposing ports 6006 (UI + unified OTLP HTTP), 4317 (OTLP gRPC), 4318 (standard OTLP HTTP fallback). Healthchecked. Trace persistence via `phoenix-data` volume. Single-service — separate `otel-collector` deferred (defensible per D-69a).
- Three dashboard spec JSONs in `database/dashboards/`:
  - `latency.json` — P50/P95/P99 of `eldritch.latency_ms` grouped by `eldritch.driver.path`.
  - `fallback.json` — count grouped by `eldritch.fallback.reason` enum.
  - `cache.json` — hit_rate of `eldritch.driver.path=cache` per (channel_id, combat_round).
  Each has a `query_recipe` field documenting the manual Phoenix UI recipe in case seeding fails.
- `scripts/observability/seed-dashboards.sh` — POSIX shell, idempotent. Probes Phoenix reachability (warn-only). For each dashboard JSON: GETs `/v1/projects`, skips if `phoenix_project_name` exists, POSTs `{name, description}` otherwise. Best-effort — Phoenix HTTP API drift produces WARN messages, not failures.
- Bot setup_hook calls `init_tracing()` unconditionally (no-op when env is unset).
- README has a new "Optional: observability stack" section with five-step recipe and per-dashboard query reference table.
- Integration smoke test at `tests/integration/test_observability_smoke.py` — skips when docker, Phoenix, or opentelemetry SDK is unavailable; when all present, emits 5 spans via `traced_decision` and asserts `BatchSpanProcessor.force_flush()` returns True within 10s.
- REQUIREMENTS.md: OBS-01 and OBS-02 both ticked `[x]`.

## Deviations from Plan

### Auto-fixed Issues

1. **[Rule 3 — blocking issue] .env example file blocked by .gitignore**
   - **Found during:** Task 1 (docker-compose + .env.observability.example)
   - **Issue:** Repository `.gitignore` excludes `.env.*` (with allow-list `!.env.example`). The intended `.env.observability.example` was not on the allow-list, so `git add` refused it.
   - **Fix:** Deleted the standalone `.env.observability.example` file. The recipe content now lives entirely in the README "Optional: observability stack" section (which is more discoverable for self-hosters anyway).
   - **Files modified:** removed `.env.observability.example`; README already had the content from Task 5.
   - **Commit:** `3231243` (initial Task 1 commit covers this — no separate commit needed)

### Sub-decisions documented in the plan

The four D-67a/D-69a/D-68a/port-discriminator sub-decisions were derived during plan reconciliation with the advisor and locked into PLAN.md before code was written.

## Verification

- ruff: clean across all new/modified files.
- import-linter: 7/7 contracts kept (verified end-to-end after Plan 02 modifications).
- pytest tests/observability/: 8/8 passed (unchanged from Plan 01 — confirming setup_hook wire-in doesn't break the lazy-import canary).
- pytest tests/integration/test_observability_smoke.py: 1 skipped (no docker daemon active in this environment — expected default behavior).
- `docker compose -f docker-compose.observability.yml config` not run here (no docker CLI in env), but `python -c "import yaml; yaml.safe_load(...)"` confirms valid YAML with 3 services-ports declared.
- `./scripts/observability/seed-dashboards.sh` exits 0 with WARN when Phoenix unreachable (confirmed manually).
- `grep -c '\- \[x\] \*\*OBS' .planning/REQUIREMENTS.md` returns 2; `grep -c '\- \[ \] \*\*OBS' ...` returns 0.

## Threat Flags

None — observability remains a pure read-only telemetry export. Docker stack is opt-in, runs on localhost by default, no auth/TLS in v1.2 (deferred per CONTEXT.md, acceptable for self-hoster's local box per the "Deferred (post-v1.2)" section).

## Self-Check: PASSED

- Created files exist:
  - docker-compose.observability.yml — FOUND
  - database/dashboards/latency.json — FOUND
  - database/dashboards/fallback.json — FOUND
  - database/dashboards/cache.json — FOUND
  - scripts/observability/seed-dashboards.sh — FOUND (executable)
  - tests/integration/test_observability_smoke.py — FOUND
- Commits exist on this branch:
  - 3231243 (docker-compose) — FOUND
  - 7fb7014 (dashboards) — FOUND
  - 0682c78 (seed script) — FOUND
  - 3cfc4ef (setup_hook wire-in) — FOUND
  - 7e64b5b (README) — FOUND
  - f831812 (smoke test) — FOUND
  - 2d85690 (REQUIREMENTS tick) — FOUND
