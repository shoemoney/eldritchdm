---
phase: 14-flake-cleanup
milestone: v1.3
generated: 2026-05-24
mode: auto-generated (autonomous-flow, discuss skipped per 'go with recommendations')
source_requirements:
  - FLAKE-01 (OCR backend env-gate)
  - FLAKE-02 (test_phase3_smoke pollution root-cause + fix)
  - FLAKE-03 (SUMMARY.md frontmatter backfill)
---

# Phase 14 — Flake cleanup + planner template hardening (CONTEXT)

## Mission

Close the carried-since-v1.1 test flakes that have been documented as
"orthogonal" through 2 milestones (v1.1, v1.2). Time to stop treating
them as orthogonal and actually fix them. Plus bring SUMMARY.md
frontmatter into spec compliance so the milestone-audit tool can trust
the frontmatter rather than parsing prose.

## Locked Decisions (autonomous)

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-95** | **OCR resolution path = skip-gate, NOT install ocrmac in dev**. Reason: `ocrmac` is macOS-only (Linux CI would fail); adding to default dev deps breaks `pip install -e ".[dev]"` on Linux self-hosters. Add `pytest.importorskip("ocrmac")` to tests that need real ocrmac OR `@pytest.mark.skipif(not _ocrmac_available(), reason="ocrmac not installed (mac-ocr extra)")`. Print clear message about installing `pip install -e ".[mac-ocr]"` if developer wants the full suite. | Cross-platform; CLAUDE.md says `ocrmac` is primary on macOS but the test suite must run cleanly on Linux too |
| **D-96** | **`test_phase3_smoke` root-cause discovery via `pytest --lf` + bisection**, NOT brute-force isolation (no pytest-randomly, no pytest-xdist). Identify which prior test corrupts which shared state. Common suspects: `os.environ` mutations not undone, sys.path appends, module-level singletons (e.g., `Settings()` global), aiosqlite connection pool state, DegradedModeState singleton (Phase 13!). Fix at SOURCE via proper teardown. | Brute-force shuffling masks root cause; we want to actually fix it |
| **D-97** | **SUMMARY.md backfill is automated**: write a small script `scripts/audit/backfill_summary_frontmatter.py` that reads each SUMMARY.md, parses the "Requirements completed" textual section (or REQUIREMENTS.md traceability table), emits the `requirements_completed:` YAML field, and commits per-summary edits. Don't hand-edit 14 files — script makes it reproducible. | Phase 12 already shows the executor can produce these; backfill ensures historical consistency without bus-factor on hand edits |
| **D-98** | **Don't update the planner template in v1.3**. The template lives in `~/.claude/get-shit-done/templates/` — outside this repo. Filing an issue against gsd-tools is the right move; the backfill ensures EldritchDM's own SUMMARYs are correct, but we're not in the business of patching the upstream tool here. | Scope discipline — backfill what's in our repo, file upstream issue for the tool |
| **D-99** | **2 plans** matching ROADMAP:<br>14-01: OCR env-gate + phase3_smoke pollution root-cause + fix (FLAKE-01, FLAKE-02)<br>14-02: SUMMARY frontmatter backfill across v1.1+v1.2 phases (FLAKE-03) | ROADMAP plans section |
| **D-100** | **Success measure**: after this phase ships, `uv run pytest tests/` returns FULL SUITE green (no orthogonal flakes), AND `grep "^requirements_completed:" .planning/phases/*/*-SUMMARY.md \| wc -l` equals 14 (one per plan SUMMARY across v1.1+v1.2). | Concrete success criteria — easy to verify post-merge |

## Investigation Notes (from quick inspection during this CONTEXT write)

- `tests/integration/test_phase3_smoke.py` passes 3/3 in isolation (just verified). The flake only manifests in full-suite runs → confirms it's pollution, not the test itself.
- OCR usage: `tests/ingest/test_ocr.py` mocks `ocrmac` and `easyocr` via `conftest.py`. The "ocrmac not installed" failure likely comes from a different test that tries `import ocrmac` for type-checking or real usage without a skip-gate.
- Phase 13 added `DegradedModeState` as a module-level singleton (per its SUMMARY). That's a prime suspect for pollution — if a prior test puts the bot in degraded mode and doesn't reset, the smoke test runs against a degraded factory.
- 14 SUMMARY files to backfill: 06-01, 06-02, 07-01, 08-01, 09-01, 10-01, 10-02, 11-01, 11-02, 12-01, 12-02, 13-01, 13-02, 13-03.

## Implementation Sketch

**Plan 01 (14-01-PLAN.md) — Flake fixes:**
1. OCR skip-gate (FLAKE-01)
   - Find tests importing `ocrmac` directly (without mock or skip)
   - Add `pytest.importorskip("ocrmac")` or `@pytest.mark.skipif(...)` per D-95
   - Verify clean skip message
2. Reproduce phase3_smoke flake (FLAKE-02)
   - Run full suite, capture which test ordering triggers the failure
   - Use `pytest --lf -x` + bisection to narrow to specific polluter
   - Identify shared mutable state (env var, singleton, file)
   - Fix with proper fixture teardown / `monkeypatch` / context manager
3. Verify: full suite green, phase3_smoke deterministic across 3 consecutive runs

**Plan 02 (14-02-PLAN.md) — SUMMARY frontmatter backfill:**
1. Write `scripts/audit/backfill_summary_frontmatter.py` (read SUMMARY, parse "Requirements completed" section, emit YAML field, dry-run + apply modes)
2. Run against all 14 SUMMARYs; commit per-summary changes in one batch
3. Verify: `grep "^requirements_completed:" .planning/phases/*/*-SUMMARY.md` returns 14 lines
4. Add a one-shot CI check (`scripts/ci/check_summary_frontmatter.sh`) to prevent future drift

## Success Criteria (from ROADMAP)

1. Full `uv run pytest tests/` returns 0 ocrmac-related failures
2. test_phase3_smoke.py passes deterministically in full-suite run
3. All 14 v1.1+v1.2 SUMMARY.md files have `requirements_completed:` frontmatter
4. ruff + lint-imports clean; no new test failures

## Deferred (post-v1.3)

- Patching upstream gsd-tools planner template (file as issue; not in v1.3 scope)
- Auto-generating `key_files` and `decisions` frontmatter for SUMMARYs (only doing requirements_completed in v1.3)
- pytest-xdist parallelization (separate concern)
- Cross-platform CI matrix expansion (Linux runner — would surface ocrmac issue more loudly)
