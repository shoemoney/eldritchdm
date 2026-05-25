---
phase: 24-ci-and-dashboards
milestone: v1.7
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - POLISH-01 (cross-platform CI matrix)
  - POLISH-02 (Phoenix dashboard cache panels)
  - POLISH-03 (atomicity doc-fix + UPSTREAM-ISSUES.md)
---

# Phase 24 — CI matrix + Phoenix cache dashboards + doc-fixes (CONTEXT)

## Mission

Final v1.7 phase: cross-platform CI (verify v1.3 ocrmac skip-gates work on Linux), bundled Phoenix dashboards for the 3 v1.5 caches, and 2 doc-fix items (v1.6 atomicity wording reconciliation + gsd-tools upstream-issues backlog file).

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-186** | **CI matrix at `.github/workflows/ci.yml`**: macos-latest + ubuntu-latest × Python 3.11. Each runs: (1) `uv sync` (dev extras only — `[mac-ocr]` NOT installed by default), (2) `uv run ruff check src/ tests/ run.py`, (3) `uv run lint-imports`, (4) `uv run pytest tests/ -q`. Linux runner ALSO runs (5) `bash scripts/ci/check_safe_yaml.sh` and (6) `bash scripts/ci/check_summary_frontmatter.sh`. | Smoke-tests cross-platform; verifies Phase 14 skip-gates |
| **D-187** | **CI does NOT install `[observability]` or `[mac-ocr]`** in default matrix — testing the off-path behavior is the point. A SEPARATE optional job `extras-mac` installs both extras on macOS to verify the on-path. Marked as `continue-on-error: true` so it's informational, not gating. | Tests both lazy-import zero-cost AND full-stack path |
| **D-188** | **3 cache dashboard JSON files** at `database/dashboards/mcp_cache.json`, `character_cache.json`, `narrcache.json`. Same OUR-FORMAT JSON spec as Phase 11 D-67a (NOT Phoenix-native dashboard JSON — schema unstable). Each has 3 panels: hit_rate (line), size (gauge), invalidations_total (counter). Query recipes reference the span attributes Phase 16/17/18 emit. | Phase 11 pattern preserved |
| **D-189** | **`scripts/observability/seed-dashboards.sh` extended** to seed the 3 new files alongside the existing 3 (latency, fallback, cache). Idempotent (existing dashboards aren't overwritten). | One canonical seed script |
| **D-190** | **Atomicity doc-fix**: edit `.planning/milestones/v1.5-REQUIREMENTS.md` line 62 (Mode Constraints section). Change "atomic — partial wipes are forbidden" → "best-effort wipe; partial-wipe acceptable when caches are independent (log `eldritch.cache.partial_wipe` and continue)". This matches the v1.6 Phase 22 implementation reality. | Reconciles doc with shipped behavior |
| **D-191** | **`.planning/UPSTREAM-ISSUES.md`** — new file tracking gsd-tools issues to file upstream. Initial entry: planner-template doesn't enforce `requirements_completed:` in SUMMARY frontmatter (v1.3 audit gap). Format: `## ISSUE-N: <title>` + repro + evidence + suggested fix. Not a milestone deliverable; a project-wide backlog. | Captures things to file without coupling to the v1.7 ship |
| **D-192** | **2 plans**: 24-01 = CI matrix (POLISH-01). 24-02 = dashboards + doc-fixes (POLISH-02 + POLISH-03). | ROADMAP plans section |

## Success Criteria
1. `.github/workflows/ci.yml` matrix (mac+ubuntu × py3.11) running ruff + lint-imports + pytest
2. Optional `extras-mac` job installs `[mac-ocr]` + `[observability]` and runs full suite (continue-on-error)
3. 3 dashboard JSON files (mcp_cache, character_cache, narrcache) in `database/dashboards/` following Phase 11 OUR-FORMAT spec
4. `scripts/observability/seed-dashboards.sh` extended; idempotent
5. `milestones/v1.5-REQUIREMENTS.md` atomicity wording corrected
6. `.planning/UPSTREAM-ISSUES.md` exists with gsd-tools planner-template gap as first entry
7. ruff + lint-imports clean
8. POLISH-01/02/03 ticked [x]
9. No regression in existing tests

## Deferred (post-v1.7)
- Filing the actual upstream gsd-tools issue — that's a manual GitHub action, not a milestone deliverable
- Adding more dashboards (degraded-mode, budget, eval) — could be v1.8 if operators want them
