---
phase: 24-ci-and-dashboards
plan: 24-02
requirements_completed: [POLISH-02, POLISH-03]
subsystem: observability
tags: [dashboards, phoenix, polish, doc-fix, upstream]
dependency_graph:
  requires: [phase-11-observability, phase-16-mcp-cache, phase-17-character-cache, phase-18-narrcache, phase-22-operator-polish]
  provides: [cache-observability-dashboards, upstream-backlog]
  affects: [operator-monitoring]
tech_stack:
  added: []
  patterns: [our-format-dashboard-json, phoenix-project-seed-idempotent]
key_files:
  created:
    - database/dashboards/mcp_cache.json
    - database/dashboards/character_cache.json
    - database/dashboards/narrcache.json
    - .planning/UPSTREAM-ISSUES.md
    - .planning/phases/24-ci-and-dashboards/deferred-items.md
  modified:
    - .planning/milestones/v1.6-REQUIREMENTS.md
    - .planning/REQUIREMENTS.md
decisions:
  - Used OUR-FORMAT spec, NOT Phoenix-native dashboard JSON (Phase 11 D-67a deviation preserved)
  - Did NOT modify seed-dashboards.sh — already idempotent (globs *.json, checks Phoenix for existing names)
  - Atomicity doc-fix applied to v1.6-REQUIREMENTS.md NOT v1.5 (CONTEXT.md typo)
metrics:
  duration_minutes: ~10
  completed_date: 2026-05-25
---

# Phase 24 Plan 02: Cache dashboards + atomicity doc-fix + UPSTREAM-ISSUES Summary

One-liner: ship 3 Phoenix cache dashboards (mcp_cache, character_cache, narrcache)
in OUR-FORMAT JSON, reconcile the v1.6 atomicity wording with shipped Phase 22
behavior, and seed `.planning/UPSTREAM-ISSUES.md` with the gsd-tools
planner-template gap as ISSUE-1.

## What shipped

- **`database/dashboards/mcp_cache.json`** — 3 metric blocks (hit_rate line by
  `eldritch.mcp.tool_name`, size gauge for L1+L2, invalidations_total counter
  by scope). Span filter: `eldritch.mcp.cache` + `eldritch.mcp.cache.invalidation`.
- **`database/dashboards/character_cache.json`** — 3 metric blocks (hit_rate
  line distinguishing hits_ttl/hits_etag/misses, size gauge, invalidations
  counter). Span filter: `eldritch.character_cache.lookup` +
  `eldritch.character_cache.invalidation`.
- **`database/dashboards/narrcache.json`** — 3 metric blocks (hit_rate line
  with hit/miss/bypass layers, size gauge, savings_usd counter). Span filter:
  `eldritch.narrcache.call`. `bypass` visibility is a feature — proves
  NarrCacheGate is firing.
- **`v1.6-REQUIREMENTS.md` line 64** rewritten from atomic-or-nothing to
  best-effort + log + continue, matching the D-171/172 Phase 22 implementation.
- **`.planning/UPSTREAM-ISSUES.md`** new backlog file. ISSUE-1 documents the
  gsd-tools planner-template gap (SUMMARYs not enforcing
  `requirements_completed:` frontmatter) with repro, evidence
  (`scripts/ci/check_summary_frontmatter.sh` local mitigation), and suggested
  fix (template + executor + optional SDK verb).
- **`REQUIREMENTS.md`** — POLISH-01/02/03 ticked [x] with closure pointers.

## Verification

- All 3 dashboard JSON files parse via `python -c "import json; json.load(...)"`.
- Span attribute names cross-checked against
  `src/eldritch_dm/observability/instrumentation.py` lines 359-541.
- `uv run ruff check` → All checks passed.
- `uv run lint-imports` → Contracts: 8 kept, 0 broken.
- `bash scripts/ci/check_safe_yaml.sh` → safe_load-only check passed.
- `seed-dashboards.sh` not modified — traced manually: globs `*.json`, queries
  Phoenix for existing project names, skips collisions. New project names
  (`eldritch-mcp-cache`, `eldritch-character-cache`, `eldritch-narrcache`)
  don't collide with existing 3 (`eldritch-latency`, `eldritch-fallback`,
  `eldritch-cache`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Atomicity doc-fix target file was misidentified upstream**

- **Found during:** Task 5 of 24-02
- **Issue:** CONTEXT.md D-190, REQUIREMENTS.md POLISH-03, v1.6-MILESTONE-AUDIT.md,
  and Phase 22 SUMMARY all reference `milestones/v1.5-REQUIREMENTS.md line 62` as
  the atomicity-wording target. `grep -rn "atomic"` across `.planning/` shows the
  actual text "atomic — partial wipes are forbidden" lives in
  `milestones/v1.6-REQUIREMENTS.md` line 64. v1.5 has no atomic wording at all
  (OPQOL-03 is a v1.6 phase requirement, not v1.5).
- **Fix:** Edited `v1.6-REQUIREMENTS.md` line 64 (the actual file). Updated
  POLISH-03 in `REQUIREMENTS.md` to point to the correct path with a note
  explaining the upstream typo.
- **Files modified:** `.planning/milestones/v1.6-REQUIREMENTS.md`,
  `.planning/REQUIREMENTS.md`
- **Commit:** (this commit's doc-fix hash)

## Deferred Issues

14 pre-existing SUMMARYs (Phases 16-22) fail
`scripts/ci/check_summary_frontmatter.sh` because they lack
`requirements_completed:` frontmatter. Out of scope for Phase 24 per SCOPE
BOUNDARY rule. Tracked in `.planning/phases/24-ci-and-dashboards/deferred-items.md`
and constitutes the canonical evidence for `UPSTREAM-ISSUES.md` ISSUE-1.

**Pre-merge action recommended:** run
`scripts/audit/backfill_summary_frontmatter.py --apply` and commit as a single
chore before the v1.7 tag, otherwise the new CI Linux runner will fail on this
gate.

## Self-Check: PASSED

- `database/dashboards/mcp_cache.json` — FOUND
- `database/dashboards/character_cache.json` — FOUND
- `database/dashboards/narrcache.json` — FOUND
- `.planning/UPSTREAM-ISSUES.md` — FOUND
- `.planning/milestones/v1.6-REQUIREMENTS.md` atomicity wording — VERIFIED (grep
  confirms new "best-effort" text present, old "atomic — partial wipes are
  forbidden" text absent)
- Dashboard commit + doc-fix commit — both present in git log
