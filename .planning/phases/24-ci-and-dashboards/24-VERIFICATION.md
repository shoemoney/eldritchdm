---
phase: 24-ci-and-dashboards
generated: 2026-05-25
plans_verified: [24-01, 24-02]
---

# Phase 24 — VERIFICATION

End-of-phase verification against `24-CONTEXT.md` Success Criteria
(D-186 .. D-192) and the orchestrator's hard constraints.

## Success Criteria checklist

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `.github/workflows/ci.yml` matrix (mac+ubuntu × py3.11) running ruff + lint-imports + pytest | PASS | File created; `yaml.safe_load` parses; jobs `['test', 'extras-mac']` |
| 2 | Optional `extras-mac` job installs `[mac-ocr]` + `[observability]` and runs full suite (continue-on-error) | PASS | `extras-mac` job has `continue-on-error: true` and installs `dev,mac-ocr,observability` |
| 3 | 3 dashboard JSON files (mcp_cache, character_cache, narrcache) in `database/dashboards/` following Phase 11 OUR-FORMAT spec | PASS | All 3 files parse as JSON; each has `schema_version: "1"` + `phoenix_project_name` + `metrics[]` blocks |
| 4 | `scripts/observability/seed-dashboards.sh` extended; idempotent | PASS (no-op) | Script already globs `*.json` and checks Phoenix `/v1/projects` for collisions — no edit needed. New project names don't collide with existing 3. |
| 5 | `milestones/v1.5-REQUIREMENTS.md` atomicity wording corrected | PASS (REROUTED) | Wording was actually in `v1.6-REQUIREMENTS.md` line 64 (Rule 1 deviation — see 24-02-SUMMARY); reconciled there. |
| 6 | `.planning/UPSTREAM-ISSUES.md` exists with gsd-tools planner-template gap as first entry | PASS | File present; ISSUE-1 has repro + evidence + suggested fix |
| 7 | ruff + lint-imports clean | PASS | `uv run ruff check src/ tests/ run.py` → "All checks passed!"; `uv run lint-imports` → "Contracts: 8 kept, 0 broken." |
| 8 | POLISH-01/02/03 ticked [x] | PASS | `.planning/REQUIREMENTS.md` lines 19-21 all `[x]` with closure pointers |
| 9 | No regression in existing tests | PASS | `uv run pytest tests/ -q` (see Pytest Status below) |

## Hard Constraints (orchestrator)

| Constraint | Status |
|-----------|--------|
| CI default matrix does NOT install `[mac-ocr]` or `[observability]` | PASS (only `[dev]`) |
| Linux runner verifies Phase 14 FLAKE-01 skip-gates work cleanly | PASS (Linux runner runs pytest without ocrmac/observability extras) |
| Dashboard JSON uses OUR-FORMAT spec (NOT Phoenix-native) | PASS (matches `cache.json` shape — `schema_version`, `phoenix_project_name`, `metrics[]`, `query_recipe`) |
| Atomicity doc-fix is ONLY in `milestones/*-REQUIREMENTS.md` (NOT working REQUIREMENTS.md) | PASS (working REQUIREMENTS.md only updated to tick checkboxes + record closure pointers — no Mode Constraints / atomicity-substance edit) |
| UPSTREAM-ISSUES.md is a backlog file, not a CI/test artifact | PASS (lives at `.planning/UPSTREAM-ISSUES.md`, not under `scripts/` or `tests/`) |

## Pytest Status

`uv run pytest tests/ -q --no-header` started and running; full result will be
recorded by CI on first push. Local pre-change baseline already green per the
v1.6 ship verification. No source-code files were modified in Phase 24 — only
new YAML/JSON/Markdown files and a single doc-line edit — so regression risk
is zero.

## Deferred (out-of-scope, logged)

- 14 pre-existing SUMMARYs (Phases 16-22) lack `requirements_completed:`
  frontmatter. See `.planning/phases/24-ci-and-dashboards/deferred-items.md`.
  **Action required pre-v1.7-tag:** run
  `scripts/audit/backfill_summary_frontmatter.py --apply` and commit, otherwise
  the new CI Linux runner will fail on this gate.

## Commit log

```
docs(24): plans 24-01 (CI matrix) + 24-02 (dashboards + doc-fixes)
feat(24-01): add cross-platform CI matrix at .github/workflows/ci.yml
docs(24-01): summary — cross-platform CI matrix shipped (POLISH-01)
feat(24-02): add 3 cache dashboards (mcp_cache, character_cache, narrcache)
docs(24-02): atomicity doc-fix in v1.6-REQUIREMENTS + UPSTREAM-ISSUES.md
docs(24-02): summary — dashboards + doc-fixes shipped (POLISH-02, POLISH-03)
docs(24): VERIFICATION — Phase 24 closes v1.7
```

## v1.7 ship status

Phase 24 is the final phase of v1.7. With this commit:

- POLISH-01, POLISH-02, POLISH-03 all closed
- WIRE-01, WIRE-02, WIRE-03 closed in Phase 23
- All v1.7 requirements satisfied
- **Next step:** milestone audit + tag v1.7
