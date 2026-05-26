# EldritchDM — Security Backlog

Tracks MEDIUM + LOW security findings deferred for future remediation.
CRITICAL + HIGH findings are fixed in the milestone they're discovered.

## How to Use

When a security audit (e.g., v1.11 Phase 31) surfaces MEDIUM or LOW findings:
1. Add an entry below with title, source audit, severity, description, deferred-reason
2. Reference here from REQUIREMENTS.md or the milestone audit document
3. Schedule remediation in a future security-focused milestone

CRITICAL/HIGH findings DO NOT live here — they're fixed in the audit's own milestone.

## Current Entries

### v1.11 Phase 31 (2026-05-26)

**No current findings.** Phase 31's 8-surface audit returned 0 results across all
4 severity tiers. See `.planning/SECURITY-AUDIT-v1.11.md` for the methodology
disclosure that substitutes for findings per the honesty clause (D-239 / SECAUDIT-03).

This backlog file exists as the future-tracking surface; expect entries to
accumulate as the project grows. The empty state for v1.11 is a positive result,
not a placeholder.

---

## Filing Guidelines

Future entries should follow this template:

```markdown
### ENTRY-N: Short title

- **Source audit:** `.planning/SECURITY-AUDIT-vX.Y.md` (link)
- **Severity:** MEDIUM / LOW
- **Description:** What's the issue?
- **Repro:** File + line citation showing the surface
- **Deferred reason:** Why isn't this fixed immediately? (e.g., low operational risk, breaks backwards compat, requires architectural change beyond milestone scope)
- **Target milestone:** v1.X (next security-focused work)
- **Workaround (if any):** Operator action that mitigates today
```
