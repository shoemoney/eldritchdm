---
phase: 09-pc-classes-backfill
plan: 01
requirements_completed: [UPGRADE-01]
subsystem: tools
tags: [cli, upgrade, backfill, td-3, riposte, idempotency]
requires:
  - "Phase 5 Plan 01 — pc_classes table + PCClassesRepo"
  - "Phase 7 — MCPClient + CircuitBreaker"
  - "Phase 8 Plan 01 — gameplay.normalize.normalize"
provides:
  - "src/eldritch_dm/tools/ (new CLI tools package)"
  - "src/eldritch_dm/tools/backfill_pc_classes.py::main"
  - "src/eldritch_dm/tools/backfill_pc_classes.py::collect_rows"
  - "src/eldritch_dm/tools/backfill_pc_classes.py::apply_rows"
  - "src/eldritch_dm/tools/backfill_pc_classes.py::BackfillRow"
  - "src/eldritch_dm/tools/backfill_pc_classes.py::ApplyReport"
  - "eldritch-dm-backfill-pc-classes (console script on PATH)"
affects:
  - "pyproject.toml [project.scripts] — new entry"
  - "INSTALL.md — v1.0 → v1.1 upgrade section added"
  - ".planning/REQUIREMENTS.md — UPGRADE-01 ticked + traceability row updated"
tech-stack:
  added: []  # no new pip deps; all reused (httpx, aiosqlite, structlog, respx)
  patterns:
    - "[project.scripts] console-script entry for one-shot CLI tools"
    - "Dry-run via mode=ro URI (driver-level write prohibition; no PCClassesRepo
       construction in the dry-run branch)"
    - "CLI-level idempotency gate (repo.get() pre-check + skip) — keeps repo SQL
       unchanged when callers want DO NOTHING semantics"
    - "Pre-built MCPClient injection into collect_rows() so tests can mock dm20
       with respx and share lifecycle"
key-files:
  created:
    - "src/eldritch_dm/tools/__init__.py"
    - "src/eldritch_dm/tools/backfill_pc_classes.py"
    - "tests/tools/__init__.py"
    - "tests/tools/test_backfill_pc_classes.py"
    - ".planning/phases/09-pc-classes-backfill/09-01-SUMMARY.md"
    - ".planning/phases/09-pc-classes-backfill/09-VERIFICATION.md"
  modified:
    - "pyproject.toml"
    - "INSTALL.md"
    - ".planning/REQUIREMENTS.md"
decisions:
  - "D-41: console script via [project.scripts]"
  - "D-42: reuse MCPClient + circuit breaker (no new HTTP)"
  - "D-43: --dry-run opens mode=ro URI (driver-level)"
  - "D-44: exit codes 0/1/2/3 = ok/user-error/partial/fatal"
  - "D-45: idempotent by default; --force re-processes"
  - "D-46: structlog with bound channel_id + character_id"
  - "D-47: src/eldritch_dm/tools/ new package"
  - "D-48: DM20_MCP_URL env override"
  - "D-49: respx fixtures + structured class tests"
  - "C-1: subclass='' best-effort; dm20 schema omits subclass (DEVIATION from D-49 hand-wave)"
  - "C-2: PID-file lock deferred to v1.2; v1.1 catches sqlite3 OperationalError 'database is locked' → EXIT_FATAL"
  - "C-3: idempotency gated at CLI (repo.get pre-check), not repo SQL"
  - "C-4: dry-run never constructs PCClassesRepo — direct mode=ro aiosqlite"
  - "C-5: dm20 fallback URL is :8765 (CONTEXT D-48 stated :7777 in error)"
  - "C-6: tests use asyncio_mode=auto (Phase 8 pattern); respx for HTTP mocks"
metrics:
  tasks_completed: 4
  files_created: 4
  files_modified: 3
  tests_added: 21
  duration_minutes: ~20
  completed_date: 2026-05-24
---

# Phase 9 Plan 01: pc_classes Ingest-Backfill Script — Summary

One-shot CLI tool (`eldritch-dm-backfill-pc-classes`) that populates a
v1.0 operator's `pc_classes` table from existing dm20 characters. Closes
TD-3 (silent no-Riposte-fires gap from the v1.0 audit) without rolling
new HTTP code or new database surface.

## What Shipped

- **`src/eldritch_dm/tools/` package** — new CLI tools layer (D-47).
  Keeps standalone tooling off `bot/` and `gameplay/` so they remain
  hermetic and Discord-free.
- **`backfill_pc_classes.py`** — three-stage pipeline:
  1. `_list_channel_sessions_readonly` — opens `mode=ro` URI for the
     read of `channel_sessions`. Safe regardless of `--dry-run`.
  2. `collect_rows` — per session, calls `dm20__list_characters` via
     the existing `MCPClient` (D-42). Per-channel failures are bucketed
     into a `failures` list; the loop never raises. Subclass is left
     empty (C-1) and an explicit `backfill.subclass_unknown` WARNING
     is emitted per row so operators know which PCs need hand-edits.
  3. `apply_rows` — dry-run branch opens `aiosqlite.connect("file:{path}?mode=ro", uri=True)`
     and counts `would_*`. Real branch constructs `PCClassesRepo` and
     gates idempotency at the CLI (C-3: pre-check via `repo.get()`,
     skip unless `--force`).
- **Exit codes (D-44):** 0=ok, 1=user error / dm20 unreachable / DB-open
  failure, 2=partial (some channels failed, some succeeded), 3=fatal
  (database is locked).
- **`[project.scripts]` entry:**
  `eldritch-dm-backfill-pc-classes = "eldritch_dm.tools.backfill_pc_classes:main"`.
  Exposed on PATH after `pip install -e .`.
- **INSTALL.md upgrade flow** — full section with stop-the-bot recipe,
  dry-run-first guidance, exit-code table, subclass caveat, sqlite3
  hand-edit example for Battle Masters.
- **REQUIREMENTS** — UPGRADE-01 ticked `[x]`; traceability row points at
  `09-01-PLAN-pc-classes-backfill`.

## Atomic Commits (5)

| # | Hash | Title |
|---|------|-------|
| 1 | `996d0be` | docs(09-01): plan — pc_classes ingest-backfill (4 atomic tasks) |
| 2 | `951da46` | chore(09-01): tools package + CLI scaffold + console-script entry (D-41/D-47) |
| 3 | `18a8e5d` | feat(09-01): dm20 fetch loop with normalize + per-channel failure bucketing (D-42/D-46) |
| 4 | `f6a71a5` | feat(09-01): SQLite write path + dry-run mode=ro + --force re-process (D-43/D-44/D-45) |
| 5 | (this commit) | docs(09-01): INSTALL.md upgrade flow + REQUIREMENTS tick + Phase 9 SUMMARY/VERIFICATION |

## Tests

- 21 tests in `tests/tools/test_backfill_pc_classes.py` covering:
  - **Scaffold:** module importable, exit codes, `--help` exits 0,
    argparse flag defaults, dm20 URL resolution precedence (4 tests).
  - **Fetch loop (respx-mocked dm20):** happy path with normalization,
    empty DB, dm20-unreachable (503 → MCPToolError), subclass WARNING
    emitted, partial success across channels.
  - **Apply path:** dry-run makes no writes (post-state COUNT(*)
    assertion), dry-run uses `mode=ro` URI (spy on `aiosqlite.connect`),
    real-run inserts new rows, idempotent re-run skips, `--force`
    re-processes existing rows, DB-locked surfaces as `EXIT_FATAL`,
    full `main()` happy path, dm20-unreachable returns
    `EXIT_USER_ERROR`, sync `main()` wraps `_run()` in `asyncio.run`.
- 280 pre-existing tests in `tests/persistence` + `tests/gameplay` all
  pass — zero regressions.

## Threat Mitigations

| Threat | Mitigation |
|--------|------------|
| **TD-3** (silent no-Riposte-fires for legacy PCs) | Tool populates `class_name` for every dm20 character into `pc_classes`; eligibility loader picks up the data on bot restart. |
| **Write during operator dry-run** | `mode=ro` URI passed to aiosqlite.connect; driver-level prohibition. Dry-run branch never constructs `PCClassesRepo`. Verified by `test_dry_run_makes_no_writes` post-state COUNT(*) == 0 and `test_dry_run_uses_readonly_uri` connect-spy assertion. |
| **Concurrent bot writes during backfill** | `sqlite3.OperationalError("database is locked")` is caught and surfaced as `EXIT_FATAL=3` with a stderr hint to stop the bot. Verified by `test_db_locked_returns_exit_fatal`. |
| **Slopsquatted / hallucinated package install** | No new pip dependencies. Reuses httpx, aiosqlite, pydantic, structlog, respx (all already in `[project]` or `[project.optional-dependencies.dev]`). |

## Deviations from Plan / CONTEXT

Documented inline with rationale; no architectural deviations (no Rule 4
events). All six were resolved at PLAN time (see "Resolved Conflicts" in
`09-01-PLAN.md`), so the executor did not stall.

1. **[C-1 — Rule 3] Subclass left empty.** CONTEXT D-49 hand-waved
   "extract class + subclass from existing dm20 char schema" but the
   schema (per `dm20__list_characters` docstring and the existing
   `pc_classes_repo.py` module docstring) explicitly omits subclass.
   Resolved with option (a): backfill `class_name`, write
   `subclass=""`, emit per-row WARNING, document operator hand-edit
   recipe in INSTALL.md.
2. **[C-2 — Rule 3] PID-file lock check deferred.** REQUIREMENTS
   UPGRADE-01 called for a PID-file lock; CONTEXT D-41..D-49 omitted
   it. Phase 9 detects an active write lock via
   `sqlite3.OperationalError("database is locked")` → `EXIT_FATAL=3`;
   full PID-file logic deferred to v1.2.
3. **[C-3 — Rule 3] Idempotency gated at the CLI, not the repo SQL.**
   `PCClassesRepo.upsert` uses `ON CONFLICT … DO UPDATE` (intentional
   for ingest-time callers). REQUIREMENTS' "DO NOTHING" phrasing is
   honored by the CLI doing a `repo.get()` pre-check and skipping
   unless `--force`. Repo SQL stays unchanged — no risk to other
   callers.
4. **[C-4 — Rule 3] Dry-run never constructs PCClassesRepo.** Repo's
   `_connect()` calls `aiosqlite.connect(self._db_path)` with no URI
   mode, so reusing it would allow writes. Dry-run branch opens
   `aiosqlite.connect("file:{path}?mode=ro", uri=True)` directly and
   only emits `would_*` counters.
5. **[C-5 — Doc drift] dm20 fallback URL is :8765, not :7777.**
   CONTEXT D-48 stated `http://localhost:7777` as the default. The
   actual codebase default (`Settings.omlx_endpoint`) is `:8765`.
   Phase 9 uses 8765; flagged here as upstream CONTEXT typo for the
   next planner to fix.
6. **[C-6 — pattern reuse] Tests use asyncio_mode=auto.** Plain
   `async def` tests; mirrors Phase 8.

## Auth Gates

None.

## Known Stubs

- `subclass=""` in every backfilled row is **intentional, not a stub**
  (C-1). dm20 does not expose subclass; documented in INSTALL.md with a
  copy-pasteable `sqlite3 UPDATE` recipe.

## Self-Check: PASSED

- `src/eldritch_dm/tools/__init__.py` — FOUND
- `src/eldritch_dm/tools/backfill_pc_classes.py` — FOUND
- `tests/tools/__init__.py` — FOUND
- `tests/tools/test_backfill_pc_classes.py` — FOUND (21 tests)
- `.planning/phases/09-pc-classes-backfill/09-01-PLAN.md` — FOUND
- `.planning/phases/09-pc-classes-backfill/09-VERIFICATION.md` — FOUND
  (this commit)
- `grep "eldritch-dm-backfill-pc-classes" pyproject.toml` — FOUND
- `grep "v1.0 → v1.1 Upgrade" INSTALL.md` — FOUND
- `grep "\[x\] \*\*UPGRADE-01" .planning/REQUIREMENTS.md` — FOUND
- Commit hashes `996d0be`, `951da46`, `18a8e5d`, `f6a71a5` — FOUND in
  `git log`

## Net Test Count

The pre-Phase-9 baseline (after Phase 8) was 894 tests; after Phase 9
the count is **915** (+21 new in `tests/tools/`). 280 of those 915 in
`tests/persistence` + `tests/gameplay` re-ran green to verify no
regressions in the surfaces this CLI touches.
