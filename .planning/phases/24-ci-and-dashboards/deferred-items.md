# Phase 24 — Deferred Items

Out-of-scope discoveries surfaced during Phase 24 execution. Pre-existing issues
not caused by this phase's changes — logged here per SCOPE BOUNDARY rule.

## 14 pre-existing SUMMARYs missing `requirements_completed:` frontmatter

`scripts/ci/check_summary_frontmatter.sh` fails locally against 14 SUMMARYs
across Phases 16-22 (none from Phase 24). The fixer script
`scripts/audit/backfill_summary_frontmatter.py --apply` is documented as the
remediation but was not run in Phase 24 to keep the diff atomic.

Offenders (as of 2026-05-25):
- `phases/16-mcp-cache/16-01-SUMMARY.md`
- `phases/16-mcp-cache/16-02-SUMMARY.md`
- `phases/17-character-cache/17-01-SUMMARY.md`
- `phases/17-character-cache/17-02-SUMMARY.md`
- `phases/18-narration-cache/18-01-SUMMARY.md`
- `phases/18-narration-cache/18-02-SUMMARY.md`
- `phases/19-streaming-embed/19-01-SUMMARY.md`
- `phases/19-streaming-embed/19-02-SUMMARY.md`
- `phases/20-aoe-targeting/20-01-SUMMARY.md`
- `phases/20-aoe-targeting/20-02-SUMMARY.md`
- `phases/21-monster-memory/21-01-SUMMARY.md`
- `phases/21-monster-memory/21-02-SUMMARY.md`
- `phases/22-operator-polish/22-01-SUMMARY.md`
- `phases/22-operator-polish/22-02-SUMMARY.md`

**Impact on CI:** The Linux runner of `.github/workflows/ci.yml` will FAIL on
the SUMMARY frontmatter gate until these are backfilled. Recommended pre-merge
action: run the backfill script and commit as a single chore. Tracked but NOT
fixed in Phase 24 to maintain commit atomicity for the v1.7 ship.

This is the exact gap captured by `UPSTREAM-ISSUES.md` ISSUE-1.
