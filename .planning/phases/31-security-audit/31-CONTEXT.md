---
phase: 31-security-audit
milestone: v1.11
generated: 2026-05-26
mode: auto-generated (autonomous-flow)
source_requirements:
  - SECAUDIT-01 (8-surface audit)
  - SECAUDIT-02 (4-tier severity categorization)
  - SECAUDIT-03 (Branch B if 0 findings)
---

# Phase 31 — Security audit investigation (CONTEXT)

## Mission

Read-only comprehensive audit covering 11 milestones of accumulated surface. Produces `.planning/SECURITY-AUDIT-v1.11.md` with categorized findings (Critical/High/Medium/Low). NO code changes — pure investigation.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-235** | **Single plan, single output file.** 31-01-PLAN.md writes the audit document directly. Cross-cutting investigation is fundamentally one task. | Investigation phase doesn't decompose cleanly |
| **D-236** | **8 attack surfaces per SECAUDIT-01** explicitly enumerated. Audit walks each in order; finds nothing → notes "no findings" with methodology evidence. | Structured coverage |
| **D-237** | **4-tier severity**: CRITICAL = RCE / secret leak / mechanical-honesty violation. HIGH = path traversal / allow-list bypass. MEDIUM = info disclosure / missing rate-limit. LOW = defense-in-depth gap / doc clarity. | Standard severity taxonomy |
| **D-238** | **Per-finding format**: title, surface (which of 8), repro (concrete code-line citation), severity, suggested fix (high-level — actual fix is Phase 32). | Auditor's report shape |
| **D-239** | **HONESTY CLAUSE active (per SECAUDIT-03)**: 0 findings is a valid result. Don't manufacture vulnerabilities. Document methodology + grep patterns used + files inspected so the audit is auditable itself. | Mirrors Phase 25 CONC-03 / Phase 28 TUNE-01 Branch B pattern |
| **D-240** | **Reference prior security work**: v1.0 Phase 1 sanitizer (SAN-01..06), v1.1 Phase 7 SAFETY-01/02/03, v1.4 Phase 15 isolation work, v1.5 Phase 16-18 allow-lists, v1.6 Phase 22 Discord-DM-to-owner. Don't re-audit what's already covered unless looking for regression. | Build on prior coverage |
| **D-241** | **Investigation toolkit**: grep for `eval(`, `exec(`, `subprocess`, `shell=True`, `open(.*[wa]`, `sql.*format`, `os.system`, `pickle`, `yaml.load(` (without safe). Find env-var reads. Cross-reference with sanitizer call sites. Walk every cache allow-list. | Concrete patterns to grep |
| **D-242** | **NO code changes in Phase 31.** This is pure investigation. Phase 32 owns remediation. | Separation of concerns |

## Success Criteria
1. `.planning/SECURITY-AUDIT-v1.11.md` exists covering all 8 surfaces
2. Each surface has either findings (with repro) or "no findings + methodology" note
3. Findings (if any) categorized into 4 severity tiers
4. ≥1 grep evidence per surface (audit must be auditable)
5. No code changes (read-only phase)
6. No regression in test suite (didn't touch any tests)

## Note on Branch B

If audit finds 0 issues — that is the result. The codebase has been built with security in mind (allow-lists, fail-CLOSED gates, sanitizers, single-writer queues, no eval/exec, safe_yaml CI gate). It is genuinely plausible v1.11 ships with 0 critical findings. Document the methodology thoroughly so the Branch B closure is itself audit-grade.
