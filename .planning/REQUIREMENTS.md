# EldritchDM — Requirements (v1.14 Test Coverage Audit)

**Milestone:** v1.14 Test Coverage Audit
**Goal:** Measure test coverage across src/ to surface genuine gaps (vs. environmental — bot/ cog code requires integration tests that hang in this orchestrator session, but should work in CI). If real gaps surface beyond integration-test surfaces, document for v1.15 work.
**Total v1.14 requirements:** 2.

---

## v1.14 Requirements

- [x] **COVERAGE-01**: Coverage run against full test suite (excluding `tests/integration` due to known orchestrator-session hangs documented since v1.3). Output coverage.json + write `.planning/COVERAGE-AUDIT-v1.14.md` with per-module breakdown.
- [x] **COVERAGE-02**: Categorize gaps: (a) **GENUINE** — production code without unit tests despite being unit-testable, (b) **ENVIRONMENTAL** — needs integration test we can't run in this session, (c) **DEFENSIBLY-UNCOVERED** — defensive branches that are hard to exercise (e.g., `except` blocks for impossible-in-practice failures). Document each.

## Mode Constraints
- Documentation-only — no source changes.
- Single phase (35), single plan (35-01).
- Branch B (zero genuine gaps) is a valid result.
