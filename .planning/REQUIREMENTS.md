# EldritchDM — Requirements (v1.11 Security Audit Refresh)

**Milestone:** v1.11 Security Audit Refresh
**Goal:** Comprehensive cross-cutting security audit covering 11 milestones of accumulated surface. Fix any critical/high findings; document low-severity items for future tracking. v1.1 SAFETY-01/02/03 was scoped — this is the wider sweep.
**Total v1.11 requirements:** 6 across 2 categories.

---

## v1.11 Requirements

### SECAUDIT — Security investigation (Phase 31)

- [x] **SECAUDIT-01**: Read-only audit produces `.planning/SECURITY-AUDIT-v1.11.md` covering 8 attack surfaces:
  1. **Secret/token leak vectors** — DISCORD_TOKEN, MCPCACHE_L2_PATH, structured-log fields, error responses, sanitizer_audit table
  2. **Allow-list bypass paths** — MCPCache (6 tools, Phase 16), CharacterSnapshot (14 fields, Phase 17), NarrCacheGate (regex, Phase 18); attempt to find paths that bypass each
  3. **Cache-poisoning vectors** — what if an attacker controls a dm20 response cached in L2? Does invalidation cover it? (Phase 16-17)
  4. **Sanitizer regression** — verify Phase 7's sanitize_player_input across all 3 modals (SAFETY-01) still works; new code paths added since v1.1 don't bypass it
  5. **Mechanical-honesty contract verification** — LLM outputs NEVER mutate game state directly. Verify SmartMonsterDriver (Phase 10), TacticalJudge (Phase 12), NarrCache (Phase 18) don't have write paths
  6. **Discord permission scope** — bot intents check (Phase 2 D-04: message_content=False); verify no later phase escalated unnecessarily
  7. **File-system path traversal** — config YAMLs (eligibility, alerts, pricing), pc_classes backfill --db-path, character_cache.sqlite path — any operator-controlled paths sanitized?
  8. **Discord DM-to-owner (Phase 22 OPQOL-02)** — verify DM content doesn't leak secrets (tokens, paths, internal IDs)
- [x] **SECAUDIT-02**: Each finding categorized: **CRITICAL** (RCE, secret leak, mechanical-honesty violation), **HIGH** (path traversal, allow-list bypass), **MEDIUM** (info disclosure, missing rate-limit), **LOW** (defense-in-depth gap, doc clarity). Each entry has: title, surface, repro, severity, suggested fix.
- [x] **SECAUDIT-03**: Even if 0 findings — produce a "no findings + audit evidence" report showing the methodology was thorough. Branch B closure permitted (mirrors Phase 25 / Phase 28 pattern). Honesty contract: don't manufacture findings to justify the audit.

### SECFIX — Remediation + regression guards (Phase 32)

- [ ] **SECFIX-01**: Fix all CRITICAL findings from Phase 31. Each fix gets: (a) repro test that FAILS before the fix, (b) the change, (c) test PASSES after, (d) cross-link in SECURITY-AUDIT.md to commit SHA. If 0 CRITICAL findings, Branch B closure.
- [ ] **SECFIX-02**: Fix all HIGH findings from Phase 31. Same evidence chain. Branch B if 0 HIGH.
- [ ] **SECFIX-03**: MEDIUM + LOW findings deferred to v1.12 backlog with explicit entries in `.planning/UPSTREAM-ISSUES.md` OR `.planning/SECURITY-BACKLOG.md` (new). Document why each was deferred (low operational risk, breaks backwards compat, etc.).

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| SECAUDIT-01 | 31 | 11 milestones of accumulated surface |
| SECAUDIT-02 | 31 | Standard 4-tier severity (Critical/High/Medium/Low) |
| SECAUDIT-03 | 31 | Honesty clause — Branch B if 0 findings |
| SECFIX-01 | 32 | Fix all CRITICAL or document Branch B |
| SECFIX-02 | 32 | Fix all HIGH or document Branch B |
| SECFIX-03 | 32 | MEDIUM/LOW deferred to v1.12 backlog |

## Mode Constraints

- SECAUDIT-01: this is a READ-ONLY investigation in Phase 31. No code changes. Investigation may use grep/Read freely. Output is documentation.
- SECAUDIT-03: HONESTY CLAUSE active — if audit finds nothing material, that's a valid result. Branch B closure with full methodology disclosure (mirrors Phase 25 CONC-03 + Phase 28 TUNE-01).
- SECFIX-01/02: each fix needs a repro test (FAIL → fix → PASS). No silent fixes.
- SECFIX-03: MEDIUM/LOW are NOT mandatory v1.11 fixes — deferred with explicit backlog entries.
- All fixes preserve v1.0 mechanical-honesty contract (bot never invents math; LLM never bypasses dm20).
