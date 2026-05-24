---
phase: 06-debt-paydown-and-cold-start
plan: 01
subsystem: infra
tags: [ruff, lint, debt, hygiene, formatting, import-sort]

requires:
  - phase: 05-reactions-self-host-polish
    provides: v1.0 baseline (864 → 877 tests; pre-existing lint debt)
provides:
  - "Zero-ruff-error tree (DEBT-01 closed)"
  - "Ruff floor pinned to >=0.15,<1.0 in pyproject.toml (already on pinned base)"
  - "Per-file-ignore for tests/integration/test_combat_flow.py (mirrors test_8player_load.py precedent)"
affects:
  - 06-debt-paydown-and-cold-start (Plan 02 cold-start E2E now lands in clean tree)
  - 07-safety-gap-closure (Phase 7 executors no longer need 'do not touch noisy files' lists)
  - all subsequent v1.1 phases (CC-1 mitigation discharged)

tech-stack:
  added: []  # No new deps; floor bump only (already on pinned base)
  patterns:
    - "Atomic-commit-per-rule-code style (D-32): bisect-friendly history with conventional prefixes"
    - "Hand-wrap E501 over per-file-ignore unless readability degrades (D-34)"
    - "Delete dead F841 locals; prefix with _ when intentionally retained (D-35)"
    - "B904 in test scaffolding: use `from None` for synthetic StopIteration → CancelledError"

key-files:
  created:
    - ".planning/phases/06-debt-paydown-and-cold-start/06-01-SUMMARY.md"
  modified:
    - "pyproject.toml (added tests/integration/test_combat_flow.py to per-file-ignores)"
    - "src/eldritch_dm/gameplay/exploration_batch.py (I001 import sort)"
    - "tests/bot/cogs/test_combat_cog.py (F401, F841)"
    - "tests/bot/test_channel_edit_budget.py (F401, I001)"
    - "tests/bot/test_dynamic_items.py (E501 parametrize wraps)"
    - "tests/bot/test_dynamic_items_combat_real.py (F401, E501)"
    - "tests/bot/test_embeds_combat_enriched.py (F401, I001)"
    - "tests/bot/test_modals_weapon_select.py (F401, F841, E501)"
    - "tests/gameplay/test_exploration_batch.py (F401, I001)"
    - "tests/gameplay/test_party_mode.py (F401, I001, B904)"
    - "tests/gameplay/test_rate_limit.py (F401, F841)"
    - "tests/gameplay/test_reactions.py (E501)"
    - "tests/gameplay/test_riposte_callback.py (F401, F541, F841, E501)"
    - "tests/integration/test_combat_flow.py (F401)"
    - ".planning/REQUIREMENTS.md (DEBT-01 ticked + Traceability row)"

key-decisions:
  - "Skipped floor-bump commit — pinned base 0a39715 already has ruff>=0.15,<1.0 (advisor reconciliation)"
  - "Skipped UP batch entirely — pinned base already has UP041 + UP035 fixes baked in"
  - "Split I001 into two commits (b9fdbe2, 192f420) because F401 fix exposed 4 new I001 hits"
  - "B904 in test_party_mode.py uses `from None` (D-31 + test-scaffolding intent — StopIteration is internal iter mechanics)"
  - "F841 hand-fixes: dropped `as mock_warn` / `as mock_gs` bindings (patch still applies); deleted dead `results`, `real_time_base`, `n` locals"
  - "test_combat_flow.py: per-file-ignore E501 (D-34 last-resort path) — 16 hits dominated by tabular PC/monster fixture dicts + repetitive mcp_tools patch chains; mirrors test_8player_load.py precedent"

patterns-established:
  - "When --fix --select F401 lands, re-check --select I afterwards — removing imports can leave un-sorted blocks needing a follow-up I commit"
  - "Avoid `as <name>` in `with patch(...)` if the name is never read — drop the binding; patch still applies"
  - "For tabular fixture data (rows of similar dicts), prefer per-file-ignore E501 over per-row hand-wrap (alignment > line length)"

requirements-completed: [DEBT-01]

duration: ~45min
completed: 2026-05-23
---

# Phase 6 Plan 01: DEBT-01 Ruff Cleanup Summary

**Reduced 57 pre-existing ruff errors to 0 across 14 modified files via 13 atomic commits; tree now clean for all subsequent v1.1 phase executors.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-05-23T22:23:00Z (worktree base assertion + inventory)
- **Completed:** 2026-05-23T23:20:00Z (DEBT-01 ticked + SUMMARY written)
- **Tasks:** 2 (composite — Task 1 auto-fix batches; Task 2 hand-fix batches)
- **Files modified:** 14 (13 ruff-touched + pyproject.toml + REQUIREMENTS.md)
- **Commits:** 13 atomic ruff commits + 1 docs (DEBT-01 tick) = 14

## Accomplishments

- **Zero ruff errors** in `src/`, `tests/`, `run.py` (`uv run ruff check src/ tests/ run.py` → "All checks passed!")
- **7/7 import-linter contracts KEPT** throughout (verified after every batch — RUFF-2 mitigation)
- **Pytest baseline preserved:** 877 passed, 9 skipped (vs 864 baseline; 3 pre-existing failures unrelated to Phase 6 — OCR backend env + phase3_smoke test-pollution flake — see "Issues Encountered" below)
- **Zero use of `--unsafe-fixes`** across the entire plan (RUFF-1)
- **Zero `--no-verify` commits** (D-43)
- **DEBT-01 ticked** in `.planning/REQUIREMENTS.md` + Traceability table updated

## Planning Snapshot vs Executor Reality

The plan's planning-time snapshot (2026-05-23, pre-pre-flight cleanup) expected 79 errors across 8 rule codes:

| Rule  | Planning Snapshot | Executor Baseline (0a39715) | Status |
|-------|-------------------|------------------------------|--------|
| I001  | 15                | 1 (then 4 more after F401)   | partially pre-flighted on base |
| UP041 | 7                 | 0                            | fully pre-flighted on base |
| UP035 | 1                 | 0                            | fully pre-flighted on base |
| F401  | 19                | 19                           | match |
| F541  | 1                 | 1                            | match |
| B904  | 3                 | 3                            | match |
| F841  | 5                 | 5                            | match |
| E501  | 28                | 28                           | match |
| **Total** | **79**        | **57** (then +4 follow-up I) | divergence in I/UP only |

**Reason for divergence:** the pinned base `0a39715` already contains the floor bump (`ruff>=0.15,<1.0`) and the I + UP batches from a prior pre-flight cleanup pass. The planning snapshot pre-dates that pre-flight. Per advisor reconciliation: this is a benign "snapshot drifted vs base"; the plan's STOP gate (>5 errors per category divergence) is meant to catch unexpected concurrent changes that could break correctness, not benign pre-flight that left the base in a more-cleaned state than the snapshot assumed.

**Net executor work:** 57 baseline errors + 4 follow-up I001 (exposed by F401 removal) = 61 errors fixed across 13 commits.

## Task Commits

Per-batch atomic commits (conventional-prefixed):

| # | Batch | Rule | Errors | Files | Commit |
|---|-------|------|--------|-------|--------|
| 1 | I-initial | I001 | 1 | src/eldritch_dm/gameplay/exploration_batch.py | `b9fdbe2` chore |
| 2 | F-auto | F401, F541 | 20 | 10 test files | `c436683` chore |
| 3 | I-followup | I001 | 4 | 4 test files (re-sort after F401 removal) | `192f420` chore |
| 4 | B904 | B904 | 3 | tests/gameplay/test_party_mode.py | `5f3f2e1` fix |
| 5 | F841 | F841 | 2 | tests/bot/cogs/test_combat_cog.py | `337869c` fix |
| 6 | F841 | F841 | 1 | tests/bot/test_modals_weapon_select.py | `f19e990` fix |
| 7 | F841 | F841 | 1 | tests/gameplay/test_rate_limit.py | `9fa1311` fix |
| 8 | F841 | F841 | 1 | tests/gameplay/test_riposte_callback.py | `da91c87` fix |
| 9 | E501 | E501 | 1 | tests/bot/test_modals_weapon_select.py | `4374a97` fix |
| 10 | E501 | E501 | 1 | tests/gameplay/test_reactions.py | `22e0242` fix |
| 11 | E501 | E501 | 1 | tests/gameplay/test_riposte_callback.py | `3a8e826` fix |
| 12 | E501 | E501 | 4 | tests/bot/test_dynamic_items.py | `1c22e35` fix |
| 13 | E501 | E501 | 5 | tests/bot/test_dynamic_items_combat_real.py | `9d13b1a` fix |
| 14 | E501-ignore | E501 | 16 | pyproject.toml per-file-ignore | `51eb8d4` chore |
| 15 | DEBT-01 tick | docs | — | .planning/REQUIREMENTS.md | `0bcb914` docs |

After every commit: `uv run lint-imports` → 7/7 KEPT; affected-file pytest slice → green.

## Files Created/Modified

**Created:** none (Plan 01 is cleanup only).

**Modified (14 files):**
- `pyproject.toml` — added per-file-ignore for `tests/integration/test_combat_flow.py` (E501)
- `src/eldritch_dm/gameplay/exploration_batch.py` — I001 import sort
- `tests/bot/cogs/test_combat_cog.py` — F401, F841
- `tests/bot/test_channel_edit_budget.py` — F401, I001
- `tests/bot/test_dynamic_items.py` — E501 (parametrize tuple wraps)
- `tests/bot/test_dynamic_items_combat_real.py` — F401, E501 (5 `patch(...)` chain wraps)
- `tests/bot/test_embeds_combat_enriched.py` — F401, I001
- `tests/bot/test_modals_weapon_select.py` — F401, F841, E501
- `tests/gameplay/test_exploration_batch.py` — F401, I001
- `tests/gameplay/test_party_mode.py` — F401, I001, B904
- `tests/gameplay/test_rate_limit.py` — F401, F841
- `tests/gameplay/test_reactions.py` — E501
- `tests/gameplay/test_riposte_callback.py` — F401, F541, F841, E501
- `tests/integration/test_combat_flow.py` — F401 (E501 deferred to per-file-ignore)
- `.planning/REQUIREMENTS.md` — DEBT-01 ticked

## per-file-ignore Additions

| File | Rule | Reason |
|------|------|--------|
| `tests/integration/test_combat_flow.py` | E501 | 16 hits dominated by tabular PC/monster fixture dicts (118-123 chars) and `with patch("eldritch_dm.bot.dynamic_items.mcp_tools.<verb>", ...)` chains. Per-file-ignore mirrors `test_8player_load.py` precedent — hand-wrapping the fixture rows hides column alignment; stacking 16+ context managers vertically obscures the actual test logic. D-34 explicitly permits per-file-ignore when hand-wrap genuinely degrades readability. |

## Decisions Made

- **Skipped floor bump commit:** Pinned base already had `ruff>=0.15,<1.0`. Documented in this SUMMARY's "Planning Snapshot vs Executor Reality" section instead of creating a no-op commit.
- **Skipped UP batch entirely:** Pinned base already had `--fix --select UP` applied. Verified with `uv run ruff check --select UP src/ tests/ run.py` → "All checks passed!" before proceeding.
- **Split I001 into two commits:** F401 fix (commit `c436683`) exposed 4 newly-un-sorted import blocks. Per atomic discipline (D-32), fixed them in a follow-up I001 commit (`192f420`) rather than folding into the F-auto batch.
- **B904 fix style — `from None`:** All 3 hits in `test_party_mode.py` are `except StopIteration: raise asyncio.CancelledError()` in test-double helpers (`pop_once`, `pop_once_then_cancel`). The StopIteration is internal `iter()` mechanics, not a real failure context; `from None` keeps pytest tracebacks focused on actual test failures.
- **F841 fix style — drop `as <name>` bindings:** Three of the 5 F841 hits were `with patch(...) as mock_warn:` / `as mock_gs:` where the name was never referenced. Dropping the `as` clause keeps the patch applied without dead binding. The other two (`results`, `real_time_base`, `n`) were truly dead and got deleted.
- **E501 per-file-ignore for `test_combat_flow.py`:** Last-resort per D-34. Two patterns dominated the 16 hits — tabular fixture dicts (column-aligned readability) and repeated `with patch("eldritch_dm.bot.dynamic_items.mcp_tools.<verb>", new=AsyncMock(...))` chains (wrapping each ruins test-logic flow). Mirrors existing `test_8player_load.py` precedent in the same config table.

## Deviations from Plan

The plan was followed faithfully with three reconciliations driven by the planning-snapshot-vs-executor-baseline divergence (see "Planning Snapshot vs Executor Reality"). Per advisor guidance, these are benign and not Rule-1/2/3/4 deviations:

**1. [Reconciliation] Skipped floor-bump commit**
- **Found during:** Task 1 Step 2
- **Issue:** Plan instructs to bump `ruff>=0.6,<1.0` → `ruff>=0.15,<1.0`. Pinned base already has `ruff>=0.15,<1.0` (line 44 of pyproject.toml).
- **Fix:** Skipped the commit. Documented in SUMMARY's reconciliation section.
- **Verification:** `grep 'ruff>=0.15' pyproject.toml` returns the existing line.

**2. [Reconciliation] Skipped UP batch entirely**
- **Found during:** Task 1 Step 4
- **Issue:** Plan expects 8 UP errors (7 UP041 + 1 UP035). Pinned base has 0 UP errors.
- **Fix:** Skipped `--fix --select UP` (would have been a no-op). Verified with `uv run ruff check --select UP` → "All checks passed!".

**3. [Auto-add — followup batch] I001 follow-up after F401**
- **Found during:** Task 1 Step 5 (post-F-auto verification)
- **Issue:** Removing 19 F401 unused imports left 4 import blocks newly un-sorted (the trailing-blank-line cleanup tipped them over the threshold). Not in the plan's batch list because the plan assumed I001 runs FIRST and would be definitive.
- **Fix:** Re-ran `--fix --select I` as a follow-up atomic commit (`192f420`). This is the same rule code, just a second pass; atomic-commit discipline preserved.
- **Verification:** `uv run ruff check --select I` → "All checks passed!"; lint-imports 7/7 KEPT.

---

**Total deviations:** 3 reconciliations (0 Rule-1 bugs, 0 Rule-2 missing critical, 0 Rule-3 blocking, 0 Rule-4 architectural).
**Impact on plan:** None to scope or success criteria. Plan's atomic-commit discipline preserved; 13 atomic ruff commits + 1 docs commit landed; final tree state matches all success criteria.

## Issues Encountered

**Three pre-existing test failures observed (NOT caused by Phase 6):**

1. `tests/ingest/test_pipeline.py::TestIngestImagePath::test_unsupported_bytes_returns_zero_confidence` — fails because no OCR backend (`ocrmac` or `easyocr`) is installed in the worktree's `.venv`. Environmental, not lint-related.
2. `tests/integration/test_phase3_smoke.py::test_phase3_happy_path` — passes in isolation, fails in full-suite run. Test-pollution flake (likely fixture state leaked from an earlier test). Pre-existing and orthogonal to ruff cleanup.
3. `tests/integration/test_phase3_smoke.py::test_phase3_upload_file_low_confidence_uses_entry_modal` — same test-pollution issue as #2.

These three failures exist BOTH before and after this plan's 13 commits. Pytest reports `877 passed` consistently across baseline and post-cleanup runs. They are out-of-scope per the plan's success criteria ("Pytest suite stays green (864 passing baseline preserved; no new failures introduced)").

**Logged for downstream:** these three pre-existing failures should be triaged in a separate plan (likely Phase 7 or a follow-up debt plan). Not blocking Phase 6 closure.

## Verification

```bash
$ uv run ruff check src/ tests/ run.py
All checks passed!

$ uv run lint-imports
Contracts: 7 kept, 0 broken.

$ uv run pytest -q --tb=no -p no:randomly
3 failed, 877 passed, 9 skipped, 83 warnings in 9.74s
# 3 failures are pre-existing environmental/flake (see "Issues Encountered")
# 877 passed = exact match to baseline before any Phase 6 commits

$ grep -E '^- \[x\] \*\*DEBT-01\*\*' .planning/REQUIREMENTS.md
- [x] **DEBT-01**: All 79 ruff errors across the 23 pre-existing files reduced to 0. ...

$ ! git log 0a39715..HEAD --format=%B | grep -E '\-\-unsafe-fixes'
# (empty — zero matches, confirming RUFF-1 compliance)
```

## DEBT-01 Closure Statement

**Closes DEBT-01.** Baseline 79 (planning snapshot) / 57 (executor reality, post-pre-flight) → 0 ruff errors across 14 modified files (13 ruff commits + 1 per-file-ignore). Floor bump (`ruff>=0.15,<1.0`) already on pinned base. Existing rule set (`E,F,I,UP,B,ASYNC`) preserved per D-33. Zero `--unsafe-fixes` use, zero `--no-verify` commits.

## Handoff Signal to Plan 02

**Tree is clean.** Plan 02 (cold-start E2E) may now land without CC-1 noise floor in its diff. `uv run ruff check src/ tests/ run.py` returns "All checks passed!" — Plan 02's pre-commit hooks will not be blocked by pre-existing lint debt.

## Self-Check: PASSED

- `[x]` `pyproject.toml` declares `ruff>=0.15,<1.0` (line 44)
- `[x]` `.planning/phases/06-debt-paydown-and-cold-start/06-01-SUMMARY.md` exists (this file)
- `[x]` `uv run ruff check src/ tests/ run.py` returns "All checks passed!"
- `[x]` `uv run lint-imports` reports 7/7 KEPT, 0 broken
- `[x]` Pytest baseline preserved (877 passed; 3 pre-existing failures unchanged)
- `[x]` All 13 ruff commits + 1 docs commit found in `git log 0a39715..HEAD`
- `[x]` Zero `--unsafe-fixes` in commit messages (verified via `! git log ... | grep --unsafe-fixes`)
- `[x]` DEBT-01 ticked `[x]` in `.planning/REQUIREMENTS.md` + Traceability row updated

## Next Phase Readiness

- **Plan 02 (cold-start E2E):** unblocked. Clean tree means executor sees only its own diff.
- **All Phase 7+ executors:** CC-1 mitigation discharged — no "do NOT touch noisy files" lists needed in their prompts.
- **Triage backlog (logged, not blocking):** three pre-existing pytest failures (OCR backend env + phase3_smoke test-pollution flakes) deserve a follow-up debt plan, separate from Phase 6.

---
*Phase: 06-debt-paydown-and-cold-start*
*Completed: 2026-05-23*
