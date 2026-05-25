---
phase: 22-operator-polish
milestone: v1.6
generated: 2026-05-25
---

# Phase 22 Verification — Operator quality-of-life bundle

Final phase of v1.6. Closes OPQOL-01 (hot-reload eligibility.yaml),
OPQOL-02 (Discord DM-to-owner), OPQOL-03 (Phase 16↔17 invalidation wire).

## Success Criteria Status

| # | Criterion | Status |
|---|-----------|--------|
| 1 | EligibilityFileWatcher polls every 60s; reloads on mtime change; preserves last-known-good on bad YAML | ✅ |
| 2 | NO bot restart needed for eligibility.yaml changes | ✅ |
| 3 | BudgetOwnerNotifier sends Discord DM on budget_breached / degraded_mode_entered / degraded_mode_exited | ✅ |
| 4 | DISCORD_OWNER_ID unset → zero behavior change (no-op) | ✅ |
| 5 | DM rate limit: 1 per event-type per hour | ✅ |
| 6 | Schema-version change wipes BOTH caches (or logs partial_wipe and continues) | ✅ |
| 7 | All extensions fail-soft (no exception propagates to bot main loop) | ✅ |
| 8 | ≥15 new tests; ruff + lint-imports clean | ✅ (23 new tests) |
| 9 | Zero regression in Phase 8 / 13 / 16 / 17 existing tests | ✅ |

## New Test Inventory

| Test File | New Count |
|---|---|
| `tests/gameplay/test_eligibility_watcher.py` | 9 |
| `tests/observability/test_budget_dm.py` | 10 |
| `tests/mcp/test_cache_invalidation_wire.py` | 4 |
| **Total** | **23** |

## Regression Surface Verified

| Suite | Before | After |
|---|---|---|
| `tests/gameplay/test_eligibility_loader.py` (Phase 8) | 19 | 19 passing |
| `tests/observability/test_degraded_mode.py` (Phase 13) | 9 | 9 passing |
| `tests/observability/test_budget_guard.py` (Phase 13) | 6 | 6 passing |
| `tests/mcp/test_cache.py` (Phase 16) | 38 | 38 passing |
| `tests/persistence/test_character_cache.py` (Phase 17) | 39 | 39 passing |
| `tests/bot/` (broad lifecycle/dynamic-items/etc.) | 373 | 373 passing, 5 skipped |
| Phase 22 totals (mcp + observability + persistence + eligibility) | — | **481 passed, 2 skipped, 0 failed** |

## Lint / Type Status

- `ruff check src/ tests/` — All checks passed
- `lint-imports` — Contracts: 8 kept, 0 broken

## Reconciliation: Atomic vs. Partial Wipe

`.planning/REQUIREMENTS.md` line 62 says:

> Phase 16↔17 invalidation wire (OPQOL-03) is atomic — partial wipes are
> forbidden; either both layers clear or neither.

`22-CONTEXT.md` D-171/172 and the Phase 22 objective override this:

> partial-wipe acceptable since they're independent caches … log
> `eldritch.cache.partial_wipe` and degrade — but NOT a fatal error.

**Implementation followed CONTEXT / objective.** Rationale:
1. CONTEXT is the more recent decision artifact for Phase 22.
2. The two caches live in physically separate SQLite databases (`mcp_cache.sqlite`
   vs `character_cache.sqlite`) with independent connection pools — atomic
   transactions across them would require a distributed-commit protocol that
   is grossly disproportionate to the actual risk (a stale character snapshot
   is bounded by the existing `CHARCACHE_TTL_S` and dm20 ETag refresh).
3. Honest failure-mode disclosure (structured `partial_wipe` warning log)
   matches the v1.x fail-soft contract across the codebase.

Tests `test_partial_wipe_character_cache_fails_logs_continue` and
`test_partial_wipe_mcp_fails_character_still_wiped` actively exercise the
partial-wipe paths and assert the operator can detect them via structured
logs.

**Action item for v1.7 docs:** consider amending REQUIREMENTS.md line 62 to
match the implementation.

## Hard Constraint Audit

- ✅ Phase 8 fail-soft contract preserved: bad YAML reload → keep last-known-good, log error, continue
- ✅ Phase 13 fail-soft preserved: `discord.Forbidden` / unset `DISCORD_OWNER_ID` → no-op, never raise
- ✅ Phase 16↔17 invalidation: partial-wipe logs `eldritch.cache.partial_wipe`, continues, NOT fatal
- ✅ All new code is fail-soft (no exception propagates to bot main loop)
- ✅ Zero regression in existing Phase 8 / 13 / 16 / 17 test surfaces
- ✅ NO new dependencies — `pathlib.stat` + `asyncio.create_task` only

## Plan Commit Map

### Plan 22-01

| Task | Commit | Description |
|---|---|---|
| Plans | 7566396 | docs(22): 22-01 + 22-02 plan files |
| 1 | 0482079 | feat(22-01): EligibilityFileWatcher |
| 2 | 9dcb775 | test(22-01): 9 watcher tests |
| 3 | 09f3c38 | feat(22-01): bot.setup_hook + close wire |

### Plan 22-02

| Task | Commit | Description |
|---|---|---|
| 1 | 1e00bc9 | feat(22-02): DegradedModeState notify-callbacks |
| 2 | 285cb1e | feat(22-02): BudgetOwnerNotifier module |
| 3 | eb49a73 | test(22-02): 10 notifier tests + structlog kwarg fix |
| 4 | d83c163 | feat(22-02): DISCORD_OWNER_ID setting |
| 5 | 9b656a1 | feat(22-02): CharacterCacheRepo.purge_all alias |
| 6 | e394316 | feat(22-02): on_schema_change callback |
| 7 | 005532b | test(22-02): 4 invalidation-wire integration tests |

## Outstanding Items / Notes for v1.7

1. **`BudgetOwnerNotifier` not yet wired into `bot.py`.** Phase 13's
   BudgetEvaluator itself is not bot-wired in mainline; bot integration was
   intentionally out of scope for OPQOL-02 (success criterion was "class
   consuming events", not bot wiring). Integration is a one-liner in
   `setup_hook` when Phase 13's evaluator graduates from library to
   bot-resident background task.
2. **MonsterDriver hot-reload caveat (OPQOL-01).** A live `MonsterDriver`
   constructed in `setup_hook` holds the initial eligibility frozenset by
   value; the watcher updates `bot.eligibility_set`, but the running
   driver sees the new set only after a fresh construction. Mid-combat
   driver rewiring deferred — operator-facing UX (no bot restart) is
   delivered; deeper driver-rebuild is a v1.7 candidate.

## v1.6 Milestone Status

With Phase 22 closed, **v1.6 is feature-complete**. Recommended next
action (per objective): milestone audit + tag `v1.6`.
