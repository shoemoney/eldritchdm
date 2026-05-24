---
phase: 06-debt-paydown-and-cold-start
plan: 02
subsystem: tests
tags: [debt, cold-start, integration, e2e, smoke, regression-guard]
requires:
  - 06-01
provides:
  - cold-start-regression-guard
  - DEBT-02-closure
affects:
  - tests/integration/test_cold_start_e2e.py
tech-stack:
  added: []
  patterns:
    - "Class-method patch of MCPClient.call with a dispatch coroutine (vs AsyncMock+side_effect) so descriptor binding works on every bot.mcp instance"
    - "In-process EldritchBot.setup_hook() execution with bot.tree.sync replaced by AsyncMock — exercises the full boot path without touching Discord"
    - "RESUME-loop pre-condition assertion (_tasks == {} after setup_hook on fresh DB) protects against the meta-pitfall recurring through pre-populated state"
key-files:
  created:
    - tests/integration/test_cold_start_e2e.py
  modified:
    - .planning/REQUIREMENTS.md
decisions:
  - "Did NOT use git stash for the historical-regression dance (prohibited in worktrees — refs/stash is shared with the main checkout). Used surgical `git checkout 7d307a1 -- src/eldritch_dm/bot/dynamic_items.py` instead, restored via `git checkout HEAD -- ...`."
  - "Lenient MCP-dispatch default (`{'ok': True}` for unmocked tool names) per plan R-1 trade-off: a regression guard for ONE bug class should not break on future MCP call sites added to setup_hook."
  - "Single positional Settings arg to EldritchBot construction (plan body's `EldritchBot(settings=settings, ...)` was hand-wavy — actual signature is `__init__(self, settings: Settings)`)."
metrics:
  duration_minutes: 12
  completed: 2026-05-24
---

# Phase 06 Plan 02: Cold-Start E2E Regression Guard Summary

Cold-start E2E regression guard installed at `tests/integration/test_cold_start_e2e.py` — single async test that exercises settings → bootstrap → EldritchBot construction → `setup_hook` → simulated `/start_game` → simulated ready-up in one process lifetime with zero shared fixtures, asserting `bot.orchestrator._tasks[channel_id]` is alive after the click. Historical-regression protocol confirmed RED at `7d307a1` (pre-G-1-fix) and GREEN at current main.

## Test File Overview

| Attribute | Value |
|---|---|
| Path | `tests/integration/test_cold_start_e2e.py` |
| LOC | 241 |
| Test count | 1 (`test_cold_start_e2e_orchestrator_alive_after_ready`) |
| Wall-clock | **0.24s** on main (well under 5s budget) |
| Fixtures used | **NONE** beyond `tmp_path` (pytest built-in) |
| Imports from `conftest` | NONE (D-37) |
| Ruff status | All checks passed |
| import-linter | 7/7 contracts KEPT |

## Mock Boundary

| Production Surface | Mock Type | Return Shape |
|---|---|---|
| `eldritch_dm.mcp.client.MCPClient.call` | `unittest.mock.patch(..., new=_mcp_dispatch)` (coroutine function, binds `self` via descriptor) | Per `tool_name` dispatch: `dm20__list_characters` → 1-character roster keyed to `_USER_ID`; `dm20__party_pop_action` → `{"empty": True, "pending": 0}` (parks orchestrator at `_sleep`); `dm20__player_action` → `{"ok": True}`; `dm20__get_game_state` → `{"round_number": 0, "actor": None}`; default → `{"ok": True}` |
| `bot.tree.sync` | `AsyncMock(return_value=[])` assigned after construction, before `setup_hook` | Empty list — setup_hook's command-sync step bypasses Discord |
| `discord.Interaction` (the ready-up click) | `MagicMock(spec=discord.Interaction)` with `response`/`followup`/`message` as `AsyncMock`s | `interaction.client = bot` so ReadyButton.callback resolves dependencies off the real bot |
| Discord gateway | NEVER reached — no `bot.run()` |
| HealthCheck HTTP ping | NEVER fires — `_run` sleeps `interval=60s` first; test ends in 0.24s |

## Historical-Regression Verification Log (LOAD-BEARING)

The plan-level discharge of DEBT-02 requires proving this test would have caught G-1. The protocol: apply the test against the pre-G-1-fix `dynamic_items.py` from commit `7d307a1` (Phase 5 Plan 03 closure), expect FAIL on the load-bearing `_tasks` assertion; restore current main, expect PASS.

### RED — against `7d307a1` (pre-G-1-fix)

Surgical revert (no stash, no detached HEAD — `git stash` is prohibited in worktrees per the deviation rules; only one commit since 7d307a1 changed dynamic_items.py, so wholesale file checkout is clean):

```bash
$ git checkout 7d307a1 -- src/eldritch_dm/bot/dynamic_items.py
$ uv run pytest tests/integration/test_cold_start_e2e.py -x -v
```

Output (excerpted from `/tmp/cold-start-7d307a1.log`):

```
tests/integration/test_cold_start_e2e.py::test_cold_start_e2e_orchestrator_alive_after_ready FAILED [100%]

E   AssertionError: G-1 regression (DEBT-02): orchestrator task NOT started
    after all-ready click. ReadyButton.callback's all-ready branch is
    missing the start_orchestrator_for_channel(...) call. See
    .planning/milestones/v1.0-MILESTONE-AUDIT.md G-1 and
    .planning/research/PITFALLS.md META meta-pitfall.
    _tasks keys: []

tests/integration/test_cold_start_e2e.py:192: AssertionError
========================= 1 failed, 1 warning in 0.27s =========================
```

The `_tasks keys: []` confirms the failure mode is exactly the load-bearing one (T-06-02-01 satisfied — not a false-positive from an import error or a stale-mock).

### GREEN — restored to current `main` (post-G-1-fix `4c15641`)

```bash
$ git checkout HEAD -- src/eldritch_dm/bot/dynamic_items.py
$ git status --porcelain   # empty — tree clean
$ uv run pytest tests/integration/test_cold_start_e2e.py -x -v
```

Output (excerpted from `/tmp/cold-start-main.log`):

```
tests/integration/test_cold_start_e2e.py::test_cold_start_e2e_orchestrator_alive_after_ready PASSED [100%]
========================= 1 passed, 1 warning in 0.24s =========================
```

DEBT-02 is fully discharged: the test FAILS at the pre-fix commit with the assertion the plan demanded, and PASSES on main.

## Commits Added

| SHA | Subject |
|---|---|
| `d816f5e` | `test(06-cold-start): regression guard for cold-start orchestrator wiring (DEBT-02)` |
| `513980a` | `docs(06-02): tick DEBT-02 in REQUIREMENTS.md` |
| (this file) | `docs(06-02): plan closure summary — cold-start E2E (DEBT-02)` |

## Deviations from Plan

**[Rule 3 — Blocking issue] Replaced the `git stash` dance with surgical file checkout.**

- **Found during:** Task 2 planning
- **Issue:** The plan body's Step 2-7 use `git stash push -u` + `git checkout 7d307a1` + `git stash pop`. Per the executor's `<destructive_git_prohibition>` deviation rules, `git stash*` is forbidden in worktrees because `refs/stash` lives in the parent `.git` and is shared with the main checkout and every sibling worktree — pop semantics are unpredictable and can leak WIP from other agents (#3542).
- **Fix:** Used `git checkout 7d307a1 -- src/eldritch_dm/bot/dynamic_items.py` to grab just the pre-G-1-fix version of the one file the fix touched (verified via `git log --oneline 7d307a1..HEAD -- src/eldritch_dm/bot/dynamic_items.py` → exactly one commit, `4c15641`, the G-1 fix itself). Restored via `git checkout HEAD -- src/eldritch_dm/bot/dynamic_items.py`. No detached HEAD, no stash, no shared-state risk.
- **Files modified:** None (the deviation is a tooling change, not a code change).
- **Outcome:** Tree is clean post-dance (`git status --porcelain` empty), test FAILED at `7d307a1` as required, test PASSED on restored main.

## DEBT-02 Closure Statement

**Closes DEBT-02.** Cold-start E2E regression guard installed. Test FAILS at `7d307a1` (pre-G-1-fix) with `_tasks keys: []`, PASSES at current main (post-`4c15641`). The v1.0 META meta-pitfall identified in `research/PITFALLS.md` is discharged for the orchestrator-wiring class of bugs.

## Handoff Signal for Phase 7+

Every subsequent v1.1 phase plan MUST ship at least one cold-start integration test of this shape — test name pattern `test_*_cold_start_*` or `test_*_fresh_install_*`. Phase 6 sets the precedent; the pattern is the regression-prevention mechanism for the META meta-pitfall identified in `research/PITFALLS.md`. Specifically:

- **Phase 7 (Smart MonsterDriver):** must include a cold-start test that wires Smart MonsterDriver to Claudmaster from a fresh DB and asserts the first monster-turn detector fires correctly.
- **Phase 8/9 (YAML eligibility):** must include a cold-start test that loads default + user-extended eligibility YAML and asserts a Battle Master Riposte surfaces from a fresh combat.
- **Phase 10 (backfill UPGRADE-01):** must include a cold-start test that runs the backfill console script against a fresh DB containing dm20 characters and asserts the `pc_classes` table is populated.

The discipline is the regression mechanism. Without it, the next G-1-class bug ships unnoticed.

## Self-Check: PASSED

- `tests/integration/test_cold_start_e2e.py` exists (committed at `d816f5e`).
- `.planning/REQUIREMENTS.md` DEBT-02 ticked `[x]`; Traceability row updated (committed at `513980a`).
- Both proof commits visible via `git log --oneline -5`.
- Test PASSES on current main in 0.24s wall-clock.
- Ruff + import-linter clean.
- No `STATE.md` / `ROADMAP.md` modifications (orchestrator owns those).
