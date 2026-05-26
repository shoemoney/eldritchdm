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

## ISSUE-2: `backfill_summary_frontmatter.py` hardcoded path table (RESOLVED in-repo)

**Target project:** gsd-tools (executor / audit-script template — if/when a
generator for this audit script ships there)

**Severity:** medium (silent traceability drift as new phases ship)

**Repro:**

1. An executor writes a plan SUMMARY without populating
   `requirements_completed:` (or with an empty list).
2. The project's audit-script (`scripts/audit/backfill_summary_frontmatter.py`
   in EldritchDM, but the pattern is generic) carries a **hardcoded
   {SUMMARY-relative-path → REQ-ID-list} mapping** seeded at the script's
   creation time.
3. New phases land. The hardcoded mapping isn't updated. The audit script
   reports "0 changes" because the SUMMARYs it knows about are fine — but
   it never inspected the new SUMMARYs at all.
4. Result: real traceability gap, invisible because the audit's success
   condition is "nothing in the hardcoded list needs changing", not
   "every SUMMARY has correct frontmatter".

**Evidence (EldritchDM):**

- v1.7 Phase 24 milestone audit found **14 SUMMARYs (phases 16-22)** with
  `requirements_completed:` set to an empty value because the hardcoded
  `MAPPING` constant in `scripts/audit/backfill_summary_frontmatter.py`
  only covered phases 6-13.
- The companion CI gate `scripts/ci/check_summary_frontmatter.sh` was
  satisfied because the key was *present* — just empty. The check didn't
  validate the value content.
- See `.planning/phases/24-ci-and-dashboards/24-02-SUMMARY.md` for the
  audit narrative.

**Resolution (in-repo):**

OPSDASH-02 / Phase 26 Plan 02 rewrote the script:

- Discovery is `pathlib.Path(".planning/phases").rglob("*-SUMMARY.md")`.
- Per-SUMMARY REQ-ID list is inferred from the **sibling PLAN**'s
  frontmatter `requirements:` field (same canonical source the executor
  uses to call `gsd-sdk query requirements.mark-complete`).
- The hardcoded MAPPING constant is removed entirely.
- Running the rewritten script with `--apply` against the v1.7 working
  tree closed all 14 gaps; a follow-up `--dry-run` returns 0 changes.

**Suggested fix (upstream, if gsd-tools ever ships a generator for this
audit pattern):**

1. Default the audit script's discovery to `rglob` rather than emitting a
   hardcoded table the user must maintain.
2. Default the per-SUMMARY REQ-ID source to the sibling PLAN's
   `requirements:` field — it is already the executor's source-of-truth.
3. Optionally: strengthen the CI gate so an empty `requirements_completed:`
   value also fails (not just missing key).

**Status:** **RESOLVED IN-REPO** (Phase 26 / OPSDASH-02). Entry retained as
proof-of-fix and as a template for any similar audit-script regressions
that surface in other projects using gsd-tools.

---

## ISSUE-3: dm20 MCP server lacks structured post-resolve damage events

**Target project:** dm20 (the upstream D&D-rules MCP server EldritchDM
delegates combat resolution to)

**Severity:** high (blocks v1.7 WIRE-01 narration-quality work + the
deferred half of Phase 23)

**Repro:**

1. Call any dm20 combat-resolution tool that mutates HP — `apply_damage`,
   `resolve_attack`, the area-of-effect resolver, etc.
2. The tool returns the post-state (new HP values, conditions applied).
3. **No structured event list describes the deltas** — caller cannot tell
   what damage type was applied, whether resistance/immunity halved or
   nullified the hit, who the source actor was for the bookkeeping, or
   which action triggered each delta.
4. Consumers (EldritchDM's narrator) reconstruct events by diffing
   pre-call and post-call snapshots. The diff loses damage-type fidelity
   (you see "HP went from 30 to 18" but not "12 fire damage halved by
   fire resistance").

**Evidence (EldritchDM):**

- v1.7 Phase 23 (WIRE-01) needed `post_resolve_damage_events` to feed the
  ShoeGPT narration prompt — the narrator must describe damage types,
  resistances, and sources to be evocative. The workaround was a Python-
  side state-diff that loses the resist/immunity story.
- The deferred half of Phase 23 (concentration-check on damage) hit the
  same gap: dm20 applies the rule internally but emits no event the
  caller can intercept.
- See `.planning/phases/23-cog-wiring/23-HALT-REPORT.md` for the
  concentration-check deferral discussion.

**Suggested fix (upstream):**

1. dm20's combat-resolution tools return, alongside the resolved state,
   a structured event list:
   ```jsonc
   "events": [
     {
       "type": "damage_applied",
       "target_actor_id": "...",
       "source_actor_id": "...",
       "source_action": "fireball",
       "damage_type": "fire",
       "raw_amount": 24,
       "applied_amount": 12,
       "modifiers": ["resistance:fire"]
     },
     {
       "type": "concentration_check_triggered",
       "target_actor_id": "...",
       "dc": 10,
       "result": "passed",
       "saved_spell_id": "..."
     }
   ]
   ```
2. Order events by application order so callers can replay them.
3. Document the event schema in dm20's tool-result schema (caller-visible
   contract, not an internal log).

**Status:** **OPEN** — requires upstream dm20 work; tracked here so we
re-evaluate at the next dm20 version bump and unblock v1.9 narration
polish if the events ship upstream.

---
