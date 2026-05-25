# Upstream Issues Backlog

Issues to file against external dependencies (gsd-tools, etc.) once we're ready to
contribute upstream. Each entry follows: title, repro, evidence, suggested fix.

Adding an entry here is **not** a commitment to file — it captures friction we hit
during EldritchDM development so we don't lose the repro context. File when the
backlog item becomes a recurring pain or when we have bandwidth to upstream a PR.

---

## ISSUE-1: planner-template doesn't enforce `requirements_completed:` in SUMMARY frontmatter

**Target project:** gsd-tools (planner / executor templates)

**Severity:** medium (silent traceability gap)

**Repro:**

1. Use `/gsd-plan-phase` to generate a PLAN.md with a `requirements:` frontmatter
   field (e.g. `requirements: [AUTH-01, AUTH-02]`).
2. Execute the plan via `/gsd-execute-phase`. The executor calls
   `gsd-sdk query requirements.mark-complete` correctly.
3. Inspect the generated `XX-YY-SUMMARY.md`. The SUMMARY frontmatter has no
   required `requirements_completed:` field — the template renders whatever the
   executor decides to emit, and on lazy days the field is omitted entirely.
4. Result: `REQUIREMENTS.md` traceability is correct (checked via SDK), but a
   reviewer browsing SUMMARYs directly cannot tell which requirements a plan
   satisfied without cross-referencing REQUIREMENTS.md and the SDK output.

**Evidence (EldritchDM):**

- v1.3 milestone audit caught ~6 SUMMARYs missing the field across Phases 8-12.
- We mitigated locally by writing `scripts/ci/check_summary_frontmatter.sh`
  which fails CI if any committed SUMMARY in `.planning/phases/` lacks
  `requirements_completed:`. This is a project-local band-aid; the proper fix
  is upstream.
- See `.planning/v1.3-MILESTONE-AUDIT.md` for the audit gap discussion.

**Suggested fix:**

1. In the planner-template's SUMMARY scaffold, make `requirements_completed:` a
   required frontmatter key (render as `requirements_completed: []` when empty
   so downstream tooling can still parse).
2. In the executor's SUMMARY-write step, populate `requirements_completed:`
   from the same source the SDK uses for `requirements mark-complete` (i.e.
   the PLAN's `requirements:` frontmatter).
3. Optionally: add a SDK verb `summary.validate-frontmatter` that the executor
   self-check can call before final commit, mirroring our shell gate.

**Status:** not filed (backlog only).

---
