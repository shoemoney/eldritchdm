---
phase: 26-opsdash-tooling
plan: 26-01
subsystem: observability
tags: [observability, dashboards, phoenix, polish]
requirements_completed: [OPSDASH-01]
dependency_graph:
  requires: [phase-13-degraded-mode, phase-13-cost-calc, phase-12-eval-cli]
  provides: [degraded-mode-dashboard, budget-dashboard, eval-dashboard]
  affects: [operator-visibility]
tech_stack:
  added: []
  patterns: [our-format-v1-dashboard-spec, offline-artifact-dashboard]
key_files:
  created:
    - database/dashboards/degraded_mode.json
    - database/dashboards/budget.json
    - database/dashboards/eval.json
  modified:
    - .planning/REQUIREMENTS.md
decisions:
  - All 3 dashboards use Phase 11 OUR-FORMAT v1 spec for consistency with the
    6 existing dashboards
  - eval.json explicitly documents an OFFLINE data source (eval-CLI JSON-lines
    artifacts) — phoenix_project_name is retained only for seed-script
    consistency; query_recipe directs readers to a notebook/BI tool, not the
    Phoenix UI
  - seed-dashboards.sh was NOT modified — it already globs *.json + checks
    Phoenix /v1/projects for collisions, so new files drop in automatically
    (same "no-op extension" pattern Phase 24 used for the 3 cache dashboards)
metrics:
  duration_minutes: ~5
  completed_date: 2026-05-25
---

# Phase 26 Plan 01: Three more bundled operational dashboards Summary

One-liner: ship `degraded_mode.json`, `budget.json`, and `eval.json` under
`database/dashboards/` — completing the v1.8 operator-visibility set without
touching any production code, and proving the existing idempotent seed script
needed no edit.

## What shipped

- **`database/dashboards/degraded_mode.json`** — Phase 13 fail-soft surface.
  Tracks `eldritch.degraded_mode.{entered,reason_changed,exited}` structured-
  log events, with `dwell_seconds` from exit events feeding p50/p95
  aggregations grouped by `reason`. `query_recipe` documents the 5%-time-in-
  degraded SLO and the trip-frequency baseline.

- **`database/dashboards/budget.json`** — Phase 13 cost surface. Aggregates
  `cost_usd` (derived per row via `PricingTable.lookup(model)` over
  `tokens_input` + `tokens_output`) across all LLM-call spans
  (`eldritch.monster.decision`, `eldritch.translate`, `eldritch.eval`).
  7-day window. `query_recipe` covers daily trend, cap-proximity gauge vs.
  `ELDRITCH_DAILY_LLM_BUDGET_USD`, per-model stacked bar, per-channel table,
  and cross-references the `eldritch.budget.{alert,exceeded}` events emitted
  by `budget_guard.py::tick()`.

- **`database/dashboards/eval.json`** — Phase 12 LLM-as-Judge surface.
  Special case: data source is **offline** JSON-lines artifacts from
  `python -m eldritch_dm.eval.cli`, NOT live Phoenix spans (per CONTEXT
  D-201 lock — "eval is offline"). `query_recipe` documents reading
  `EvalAggregate.{overall_score, per_dimension_mean, per_archetype_mean}`
  from `eval-outputs/<run_id>.jsonl`, and cross-references
  `eldritch.eval` spans for online latency/cost telemetry routed through
  the budget dashboard.

- **OPSDASH-01 ticked `[x]`** in `.planning/REQUIREMENTS.md`.

## Seed-script verification (Task 4 — no edit)

`scripts/observability/seed-dashboards.sh` was inspected and confirmed to
satisfy D-202 structurally without modification:

- Line 47 (`for f in "$DASHBOARDS_DIR"/*.json`) globs every JSON file in
  the dashboards dir — the 3 new files are picked up automatically.
- Lines 56-62 GET `$PHOENIX_BASE_URL/v1/projects` and skip any
  `phoenix_project_name` that already exists, satisfying idempotency.
- The 3 new project names (`eldritch-degraded`, `eldritch-budget`,
  `eldritch-eval`) do not collide with the existing 6, so first-run
  seeding will create them; second-run is a no-op.

This matches the Phase 24 pattern recorded in 24-VERIFICATION.md (criterion 4:
"Script already globs `*.json` and checks Phoenix `/v1/projects` for
collisions — no edit needed").

## Deviations from Plan

None — plan executed exactly as written.

## Verification

```
$ python -c "import json, pathlib; [json.loads(p.read_text()) for p in pathlib.Path('database/dashboards').glob('*.json')]; print('all parse')"
all parse

$ ls database/dashboards/*.json | wc -l
9

$ bash -n scripts/observability/seed-dashboards.sh
(exit 0)
```

## Self-Check: PASSED

- FOUND: database/dashboards/degraded_mode.json (commit d3fd8b4)
- FOUND: database/dashboards/budget.json (commit a605171)
- FOUND: database/dashboards/eval.json (commit 75226ff)
- FOUND: REQUIREMENTS.md OPSDASH-01 ticked [x]
