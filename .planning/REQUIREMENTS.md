# EldritchDM — Requirements (v1.3 Hygiene Sweep)

**Milestone:** v1.3 Hygiene Sweep
**Goal:** Close the carried-since-v1.1 test flakes (OCR backend env + phase3_smoke pollution) and bring SUMMARY.md frontmatter into spec compliance (planner-template gap). One focused phase of low-risk hygiene work — sets up a green-on-green-on-green test suite for v1.4 feature work.
**Total v1.3 requirements:** 3 across 1 category.

---

## v1.3 Requirements

### FLAKE — Test reliability + planner template hardening (Phase 14)

- [x] **FLAKE-01**: OCR backend env tests no longer report "ocrmac not installed" failures in dev venv. Resolution path is investigated and committed: EITHER `ocrmac` is added to default dev deps (with macOS-only skip-gate for Linux CI) OR each ocrmac-dependent test gets `@pytest.mark.skipif(not _has_ocrmac())` with a clear marker. Either way: full `uv run pytest tests/` returns 0 ocrmac-related failures.
- [ ] **FLAKE-02** *(partial — see `.planning/phases/14-flake-cleanup/14-01-SUMMARY.md` Known Limitations)*: `tests/integration/test_phase3_smoke.py` passes deterministically in the full-suite run, not just in isolation. Root cause of the test-pollution flake identified (which other test corrupts which shared resource), documented in the SUMMARY, and fixed at the source (proper teardown, fixture isolation, or sentinel-value cleanup — NOT by adding `pytest-randomly`-style brute force).
- [x] **FLAKE-03**: All v1.1 + v1.2 phase SUMMARY.md files (`06-01`, `06-02`, `07-01`, `08-01`, `09-01`, `10-01`, `10-02`, `11-01`, `11-02`, `12-01`, `12-02`, `13-01`, `13-02`, `13-03`) have `requirements_completed:` YAML frontmatter field listing the REQ-IDs each plan satisfied. Where the field is missing, it's back-filled from the SUMMARY body's textual list. Audit milestone tool can then trust the frontmatter as the single source of truth.

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| FLAKE-01 | 14 | v1.1 milestone audit tech debt item (carried across v1.1, v1.2) |
| FLAKE-02 | 14 | v1.1 milestone audit tech debt item (carried across v1.1, v1.2) |
| FLAKE-03 | 14 | v1.2 milestone audit "planner template gap" — SUMMARYs don't consistently emit requirements_completed in frontmatter |

## Mode Constraints

- No new dependencies unless investigation reveals one is genuinely necessary (e.g., a pytest plugin for test isolation).
- No mass test refactor — fix the specific flakes only.
- Don't add `pytest-randomly` or `pytest-xdist` to "shake out" flakes — that masks pollution, doesn't fix it.
- SUMMARY.md backfill is read-only against existing SUMMARY bodies; no commit-message rewrites needed.
