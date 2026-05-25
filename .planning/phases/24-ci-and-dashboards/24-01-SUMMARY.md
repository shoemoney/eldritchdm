---
phase: 24-ci-and-dashboards
plan: 24-01
subsystem: ci
tags: [ci, github-actions, polish]
requirements_completed: [POLISH-01]
dependency_graph:
  requires: []
  provides: [cross-platform-ci]
  affects: [release-gating]
tech_stack:
  added: [github-actions, astral-sh/setup-uv@v3, actions/setup-python@v5]
  patterns: [matrix-build, continue-on-error-informational-job, concurrency-cancel]
key_files:
  created:
    - .github/workflows/ci.yml
  modified: []
decisions:
  - Default matrix installs only [dev] — verifies skip-gates on the off-path
  - extras-mac is non-gating (continue-on-error) — native extras flakiness must not block merges
  - Linux runner is the canonical home for the YAML+frontmatter shell gates
metrics:
  duration_minutes: ~5
  completed_date: 2026-05-25
---

# Phase 24 Plan 01: GitHub Actions CI matrix Summary

One-liner: cross-platform CI (macOS + Ubuntu × Python 3.11) installing `[dev]` only
by default to verify Phase 14 skip-gates, with an optional `extras-mac` job for
the full-stack on-path.

## What shipped

- `.github/workflows/ci.yml` with two jobs:
  - **`test`** matrix: macos-latest + ubuntu-latest × Python 3.11. Steps: checkout
    → setup-python → setup-uv → `uv venv && uv pip install -e ".[dev]"` → ruff →
    lint-imports → pytest. Linux-only extra steps: `check_safe_yaml.sh` +
    `check_summary_frontmatter.sh`.
  - **`extras-mac`** (informational, `continue-on-error: true`): macos-latest with
    `[dev,mac-ocr,observability]` installed, runs pytest.
- Concurrency group `${{ github.workflow }}-${{ github.ref }}` with
  `cancel-in-progress: true` so stacked pushes don't pile up runs.

## Verification

- `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` → OK,
  jobs `['test', 'extras-mac']` parsed.
- Workflow does NOT pass `--extra mac-ocr` or `--extra observability` in the default
  matrix (grep-verified).
- Linux-only steps gated by `if: matrix.os == 'ubuntu-latest'`.

## Deviations from Plan

None — plan executed as written.

## Self-Check: PASSED

- `.github/workflows/ci.yml` — FOUND
- Commit `f29800d` — FOUND
