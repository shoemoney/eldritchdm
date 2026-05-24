---
phase: 09-pc-classes-backfill
generated: 2026-05-24
gate: CC-2 hygiene
---

# Phase 9 — Verification (CC-2 Hygiene Gate)

Closes TD-3 / UPGRADE-01. All checks below were executed inside the
worktree against the four commits of Plan 01 (951da46, 18a8e5d, f6a71a5,
plus the docs/SUMMARY commit).

## 1. Lint / style

```bash
ruff check src/eldritch_dm/tools tests/tools
# → All checks passed!

ruff check src tests   # full-tree spot check
# → All checks passed (no Phase-9-introduced violations)

lint-imports --config pyproject.toml
# → Contracts: 7 kept, 0 broken.
```

The new `src/eldritch_dm/tools/` package only imports from `gameplay`,
`persistence`, and `mcp` — all permitted by the 7 import-linter contracts.
Nothing in the new code reaches into `bot/`.

## 2. Console script registered (D-41)

```bash
grep -n "eldritch-dm-backfill-pc-classes" pyproject.toml
# → [project.scripts]:
#     eldritch-dm-backfill-pc-classes = "eldritch_dm.tools.backfill_pc_classes:main"
```

After `pip install -e .`, `which eldritch-dm-backfill-pc-classes` returns
the venv bin path; `eldritch-dm-backfill-pc-classes --help` exits 0 and
prints the argparse help text.

## 3. Dry-run cannot write (D-43)

Two independent assertions:

- **`test_dry_run_uses_readonly_uri`** — monkeypatches
  `backfill.aiosqlite.connect` and asserts at least one call's first
  positional arg is a string containing `mode=ro` with `uri=True` in
  kwargs. This is a driver-level prohibition: even if our code had a bug
  that tried to `INSERT`, SQLite would refuse.

- **`test_dry_run_makes_no_writes`** — seeds an empty `pc_classes`,
  collects 2 rows, runs `apply_rows(..., dry_run=True, force=False)`,
  then asserts `SELECT COUNT(*) FROM pc_classes` is still 0. Post-state
  check, not just behavior.

## 4. `--force` re-processes existing rows (D-45)

`test_force_re_processes_existing` — seeds `pc_classes` with
`class_name="stale_class"`, runs the backfill with `force=True` against a
row whose class_name is `"fighter"`, asserts:

- `report.updated == 1`
- `repo.get(...)` returns `class_name="fighter"` (drift overwritten).

## 5. Idempotency by default (D-45)

`test_idempotent_re_run_skips` — runs `apply_rows` twice with the same
input; second run reports `skipped_existing == 2, inserted == 0` and the
DB count is unchanged.

## 6. dm20-unreachable path (D-44 exit codes)

Two distinct assertions:

- `test_collect_rows_dm20_unreachable_buckets_failures` — at the
  `collect_rows` layer, a 503 response (which surfaces as
  `MCPToolError`) ends up in the `failures` list, not as an exception.
- `test_main_dm20_unreachable_returns_exit_user_error` — at the
  `_run()` layer, the same 503 propagates to `EXIT_USER_ERROR=1`.

## 7. DB-locked path returns `EXIT_FATAL` (C-2)

`test_db_locked_returns_exit_fatal` — monkeypatches
`PCClassesRepo.upsert` to raise `sqlite3.OperationalError("database is
locked")`, runs `_run()`, asserts return value == 3 (`EXIT_FATAL`).

## 8. Test suite green

```bash
pytest tests/tools tests/persistence tests/gameplay -q
# → 301 passed, 2 skipped, 1 warning
```

- 21 new tests in `tests/tools/`
- 280 pre-existing in `tests/persistence` + `tests/gameplay` — unchanged
- The two skips are existing slow/load-gated tests (`RUN_STRESS=1` /
  `RUN_LOAD=1`), unrelated to Phase 9.

## 9. Documentation

```bash
grep -c "v1.0 → v1.1 Upgrade" INSTALL.md
# → 1   (new section added)
grep -c "subclass='battle master'" INSTALL.md
# → 1   (operator hand-edit recipe present)
grep -nE "^- \[x\] \*\*UPGRADE-01" .planning/REQUIREMENTS.md
# → 29:- [x] **UPGRADE-01** …
grep -n "09-01-PLAN-pc-classes-backfill" .planning/REQUIREMENTS.md
# → 83:| UPGRADE-01 | Phase 9 | 09-01-PLAN-pc-classes-backfill |
```

## 10. CONTEXT.md frontmatter alignment

CONTEXT D-41..D-49 + Success Criteria 1–5 all satisfied. Six conflicts
discovered at PLAN time (C-1..C-6) are resolved explicitly in
`09-01-PLAN.md` and re-documented in `09-01-SUMMARY.md::Deviations`.

## Result

**Gate: PASSED.** Plan 01 is the only plan in Phase 9; the phase is
complete. Orchestrator should mark Phase 9 done and proceed to Phase 10
(Smart MonsterDriver / COMBAT-13/14).
