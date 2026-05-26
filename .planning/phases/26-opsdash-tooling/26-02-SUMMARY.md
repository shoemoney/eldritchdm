---
phase: 26-opsdash-tooling
plan: 26-02
requirements_completed: [OPSDASH-02, OPSDASH-03]
subsystem: tooling
tags: [audit, traceability, upstream-issues, polish]
dependency_graph:
  requires: [phase-14-flake-03-backfill, phase-24-traceability-gap-finding]
  provides: [auto-discovery-backfill, upstream-issues-issue-2, upstream-issues-issue-3]
  affects: [traceability-ci-gate]
tech_stack:
  added: []
  patterns: [pathlib-rglob-discovery, sibling-plan-frontmatter-source-of-truth]
key_files:
  created: []
  modified:
    - scripts/audit/backfill_summary_frontmatter.py
    - .planning/UPSTREAM-ISSUES.md
    - .planning/REQUIREMENTS.md
    # Plus 23 SUMMARY files backfilled by the rewritten script.
decisions:
  - PLAN frontmatter `requirements:` field is the source of truth for the
    per-SUMMARY req list — it is exactly what the executor uses to call
    `gsd-sdk query requirements.mark-complete`, so SUMMARY frontmatter and
    REQUIREMENTS.md state can never disagree by construction.
  - Phases 6-9 PLANs (legacy template, no flow-style `requirements:` field)
    are skipped with a WARN — their existing SUMMARY frontmatter is already
    correct via the legacy hardcoded apply, and rewriting that history would
    be cosmetic at best, destructive at worst.
  - ISSUE-2 stays in UPSTREAM-ISSUES.md as RESOLVED IN-REPO — the entry
    serves as a proof-of-fix + template for any similar audit-script
    regression that surfaces in other gsd-tools projects.
metrics:
  duration_minutes: ~7
  completed_date: 2026-05-25
---

# Phase 26 Plan 02: Backfill auto-discovery + UPSTREAM-ISSUES expansion Summary

One-liner: kill the hardcoded path-table in
`scripts/audit/backfill_summary_frontmatter.py` (auto-discover via `rglob` +
infer requirements from sibling PLAN frontmatter), backfill the 14 empty
`requirements_completed:` values phases 16-22 had been carrying since Phase
14, and extend UPSTREAM-ISSUES.md with ISSUE-2 (RESOLVED in-repo) +
ISSUE-3 (dm20 damage-event surface, OPEN).

## What shipped

### OPSDASH-02 — backfill auto-discovery

- **`scripts/audit/backfill_summary_frontmatter.py` rewritten.** The
  hardcoded `MAPPING` constant (covering only phases 6-13) is gone.
  Discovery is `pathlib.Path(".planning/phases").rglob("*-SUMMARY.md")`.
  Per-SUMMARY REQ-ID list is parsed from the sibling PLAN.md frontmatter
  `requirements:` flow-list. Helpers (`_split_frontmatter`,
  `_backfill_frontmatter`, `_format_value`, `_process_file`) are preserved
  verbatim — only the driver and per-SUMMARY mapping derivation changed.

- **`--dry-run` against the v1.7 working tree reported 23 SUMMARYs that
  would change** (14 with empty `requirements_completed:`, 9 with the
  key in a non-canonical frontmatter position; 5 skipped — phases 6-9
  legacy template).

- **`--apply` closed all 23 gaps in one pass.** A follow-up `--dry-run`
  reports `WOULD CHANGE 0/38 SUMMARY files (skipped 5)` — the OPSDASH-02
  "0 gaps to apply" validation gate passes.

- **`scripts/ci/check_summary_frontmatter.sh` still passes**: `OK: 38
  SUMMARY files have requirements_completed: frontmatter`. (Count is 38
  after the Phase 26 plan 01 SUMMARY was added; will become 39 once this
  SUMMARY is committed — both will be tracked on subsequent runs.)

### OPSDASH-03 — UPSTREAM-ISSUES.md expansion

- **ISSUE-2** added (RESOLVED IN-REPO). Documents the hardcoded-paths bug
  Phase 24 caught, the 14-SUMMARY gap that resulted, the rewrite that
  closed it, and the suggested upstream fix for any future gsd-tools
  audit-script generator.

- **ISSUE-3** added (OPEN). Documents dm20's missing
  `post_resolve_damage_events` surface, the EldritchDM narration impact
  (WIRE-01 + Phase 23 concentration-check deferral), and a proposed
  upstream event schema with replay-order contract.

- Existing ISSUE-1 (planner-template `requirements_completed:` enforcement)
  unchanged.

### REQUIREMENTS.md ticks

- **OPSDASH-02** ticked `[x]`.
- **OPSDASH-03** ticked `[x]`.
- (OPSDASH-01 was ticked at the end of Plan 26-01.)

## Deviations from Plan

None — plan executed exactly as written. The "23 SUMMARYs proposed" finding
during `--dry-run` was higher than the 14 anticipated in 26-CONTEXT.md
because the rewritten script also canonicalises the `requirements_completed:`
**position** within the frontmatter (immediately after `plan:`). Plans 14, 15,
23-25 already had correct values but with the key in a different position; the
rewrite normalized them. This is cosmetic-only for those 9 — content is
identical to what was already committed.

## Verification

```
$ python scripts/audit/backfill_summary_frontmatter.py --apply
APPLIED 23/38 SUMMARY files (skipped 5)

$ python scripts/audit/backfill_summary_frontmatter.py --dry-run
WOULD CHANGE 0/38 SUMMARY files (skipped 5)

$ bash scripts/ci/check_summary_frontmatter.sh
OK: 38 SUMMARY files have requirements_completed: frontmatter

$ grep -c '^## ISSUE-' .planning/UPSTREAM-ISSUES.md
3

$ grep -E '^- \[x\] \*\*OPSDASH-0[23]\*\*' .planning/REQUIREMENTS.md
- [x] **OPSDASH-02**: ...
- [x] **OPSDASH-03**: ...

$ uv run ruff check scripts/ src/ tests/
All checks passed!
```

## Self-Check: PASSED

- FOUND: scripts/audit/backfill_summary_frontmatter.py (commit 73e7eff — auto-discovery)
- FOUND: 23 SUMMARYs backfilled (commit 1914eab)
- FOUND: UPSTREAM-ISSUES.md ISSUE-2 + ISSUE-3 (commit a537f1e — 3 ISSUE-* sections total)
- FOUND: REQUIREMENTS.md OPSDASH-02/03 ticked [x]
- FOUND: CI gate passes (38 SUMMARYs, all have requirements_completed)
- FOUND: ruff clean across scripts/ src/ tests/
