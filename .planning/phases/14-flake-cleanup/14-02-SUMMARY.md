---
phase: 14-flake-cleanup
plan: "02"
requirements_completed: [FLAKE-03]
subsystem: tooling/audit
tags: [planner-hygiene, frontmatter, backfill, ci-gate, requirements-traceability]
requires:
  - 14-01 (in parallel — orthogonal)
provides:
  - scripts/audit/backfill_summary_frontmatter.py
  - scripts/ci/check_summary_frontmatter.sh
affects:
  - 14 plan SUMMARY.md files (v1.1 + v1.2) — added requirements_completed: frontmatter
  - .planning/REQUIREMENTS.md (FLAKE-03 ticked)
tech-stack:
  added: []
  patterns:
    - "embedded-mapping + dry-run/apply CLI for one-shot doc backfills"
    - "shell CI gate using `find ... -print0 | while read -d ''` for safe traversal"
key-files:
  created:
    - scripts/audit/backfill_summary_frontmatter.py
    - scripts/ci/check_summary_frontmatter.sh
  modified:
    - .planning/phases/06-debt-paydown-and-cold-start/06-01-SUMMARY.md (normalised hyphen → underscore)
    - .planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md
    - .planning/phases/07-safety-gap-closure/07-01-SUMMARY.md
    - .planning/phases/08-yaml-riposte-eligibility/08-01-SUMMARY.md
    - .planning/phases/09-pc-classes-backfill/09-01-SUMMARY.md
    - .planning/phases/10-smart-monsterdriver/10-01-SUMMARY.md
    - .planning/phases/10-smart-monsterdriver/10-02-SUMMARY.md
    - .planning/phases/11-phoenix-observability/11-01-SUMMARY.md
    - .planning/phases/11-phoenix-observability/11-02-SUMMARY.md
    - .planning/phases/12-llm-judge-tactical/12-01-SUMMARY.md
    - .planning/phases/12-llm-judge-tactical/12-02-SUMMARY.md
    - .planning/phases/13-production-monitoring/13-01-SUMMARY.md
    - .planning/phases/13-production-monitoring/13-02-SUMMARY.md
    - .planning/phases/13-production-monitoring/13-03-SUMMARY.md
decisions:
  - "D-97 applied: script + embedded mapping (not hand edits)"
  - "D-98 honored: did NOT patch upstream gsd-tools planner template (out of scope for v1.3)"
  - "Normalised legacy `requirements-completed:` (hyphen) form found in 06-01 to underscore form per FLAKE-03 spec"
  - "CI gate ships in scripts/ci/ but is NOT wired into a GitHub Actions workflow this phase (post-v1.3 polish)"
metrics:
  duration: ~30min
  completed: 2026-05-25
---

# Phase 14 Plan 02: SUMMARY.md `requirements_completed:` Frontmatter Backfill Summary

**One-liner:** All 14 v1.1+v1.2 plan SUMMARY.md files now expose
`requirements_completed: [REQ-ID, ...]` in their YAML frontmatter,
back-filled via a reusable script and guarded by a CI check.

## Background

The v1.2 milestone audit observed that planner-emitted SUMMARYs did not
consistently expose `requirements_completed:` in their YAML frontmatter —
some had a prose "Requirements completed" section, one had a non-standard
`requirements-completed:` (hyphen) key, and several had nothing structured
at all. This forced the milestone-audit tool to parse free-form prose and
created bus-factor risk if the prose format drifted. FLAKE-03 closes this
by back-filling a single canonical YAML field across all 14 files.

## Tasks completed

### Task 1 — Backfill script

`scripts/audit/backfill_summary_frontmatter.py` reads each SUMMARY's YAML
frontmatter block (between the first two `---` lines), inserts (or replaces)
the `requirements_completed:` line, and removes any legacy hyphen form.
Mapping is embedded in the script (derived from `.planning/ROADMAP.md`
Traceability table) so re-running is reproducible and a no-op once applied.

Supports `--dry-run` (default; emits unified diff per file) and `--apply`
(rewrites in place).

**Commit:** `494b709` feat(14-02): add SUMMARY.md requirements_completed
backfill script

### Task 2 — Apply backfill across 14 SUMMARYs

`python scripts/audit/backfill_summary_frontmatter.py --apply` →
`APPLIED 14/14 SUMMARY files`. Each SUMMARY now has the
`requirements_completed:` line immediately after the `plan:` line in its
frontmatter, with REQ-IDs sorted alphabetically.

**Commit:** `c339daa` docs(14-02): backfill requirements_completed:
frontmatter on all 14 v1.1+v1.2 SUMMARYs

### Task 3 — CI gate

`scripts/ci/check_summary_frontmatter.sh` walks every `*-SUMMARY.md`
under `.planning/phases/` and asserts:
1. File starts with YAML frontmatter (`---` as first line).
2. Frontmatter contains a `requirements_completed:` key.
3. No legacy `requirements-completed:` (hyphen) keys remain.

Exits 0 on clean, 1 with offender list otherwise. Ships as a script for
v1.3; wiring into a GitHub Actions workflow is post-v1.3 polish (D-98
scope discipline).

**Commit:** `d6a8d13` ci(14-02): add CI gate
scripts/ci/check_summary_frontmatter.sh

### Task 4 — Tick FLAKE-03

`.planning/REQUIREMENTS.md` FLAKE-03 marked `[x]`.

## Verification

| Check | Result |
|---|---|
| `python scripts/audit/backfill_summary_frontmatter.py --apply` | `APPLIED 14/14 SUMMARY files` |
| `grep "^requirements_completed:" .planning/phases/*/*-SUMMARY.md \| wc -l` | `14` (was `0`) |
| `grep "^requirements-completed:" .planning/phases/*/*-SUMMARY.md \| wc -l` | `0` (was `1` — 06-01 hyphen form normalised) |
| `bash scripts/ci/check_summary_frontmatter.sh` | `OK: 14 SUMMARY files have requirements_completed: frontmatter` (exit 0) |
| Re-run script with `--apply` | No-op (idempotent) |

## Deviations from Plan

None — plan executed exactly as written.

## Future Work / TODOs

1. **Wire `scripts/ci/check_summary_frontmatter.sh` into GitHub Actions**
   so a PR that lands a SUMMARY without the field fails CI. Post-v1.3
   polish per D-98 scope discipline.
2. **File upstream issue against gsd-tools** to add
   `requirements_completed:` as a standard planner-template frontmatter
   field. Per D-98, this phase did NOT patch the upstream template — only
   our repo's existing SUMMARYs.
3. **Extend script** to also normalise `key_files:` and `decisions:`
   frontmatter for SUMMARYs that lack them — deferred per D-98 (post-v1.3).
