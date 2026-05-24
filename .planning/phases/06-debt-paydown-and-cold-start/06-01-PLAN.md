---
phase: 06-debt-paydown-and-cold-start
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  # 23 pre-existing files identified by `uv run ruff check src/ tests/ run.py`.
  # Executor MUST re-derive this list from a fresh `ruff check` run before the
  # first commit (CC-1 contamination guard); the list below is the planning-
  # time snapshot taken on 2026-05-23.
  - src/eldritch_dm/gameplay/exploration_batch.py
  - tests/bot/cogs/test_combat_cog.py
  - tests/bot/test_channel_edit_budget.py
  - tests/bot/test_dynamic_items.py
  - tests/bot/test_dynamic_items_combat_real.py
  - tests/bot/test_embeds_combat_enriched.py
  - tests/bot/test_modals_weapon_select.py
  - tests/gameplay/test_exploration_batch.py
  - tests/gameplay/test_monster_driver.py
  - tests/gameplay/test_party_mode.py
  - tests/gameplay/test_rate_limit.py
  - tests/gameplay/test_reactions.py
  - tests/gameplay/test_riposte_callback.py
  - tests/gameplay/test_riposte_sweeper.py
  - tests/gameplay/test_session_locks.py
  - tests/integration/test_combat_flow.py
  - tests/integration/test_riposte_smoke.py
  - tests/persistence/test_pc_classes_repo.py
autonomous: true
requirements:
  - DEBT-01
tags: [debt, ruff, cleanup, hygiene, infrastructure]

must_haves:
  truths:
    - "`uv run ruff check src/ tests/ run.py` returns exit 0 (was: 79 errors)"
    - "`pyproject.toml` declares `ruff>=0.15,<1.0` (was: `ruff>=0.6,<1.0`); rule selection (`E,F,I,UP,B,ASYNC`) unchanged"
    - "All 7 import-linter contracts remain KEPT after every commit in the batch series"
    - "Full pytest suite (`uv run pytest`) remains green after every commit (864 passing baseline preserved; no new failures introduced)"
    - "Commit history is atomic and bisect-friendly: one rule code per commit, conventional prefix `chore(06-ruff): ...` for auto-fixes and `fix(06-ruff): ...` for hand-fixes"
    - "Zero use of `--unsafe-fixes` anywhere in the plan (RUFF-1; Context7-verified)"
    - "Zero net behavior change in `src/eldritch_dm/` — only formatting, import order, syntax modernization, and unused-symbol removal"
  artifacts:
    - path: "pyproject.toml"
      provides: "Ruff floor bumped to >=0.15,<1.0; rule selection unchanged"
      contains: 'ruff>=0.15,<1.0'
    - path: ".planning/phases/06-debt-paydown-and-cold-start/06-01-SUMMARY.md"
      provides: "Plan closure summary with per-batch commit table + outcome of `ruff check` final run"
  key_links:
    - from: "pyproject.toml"
      to: "all v1.1 phases"
      via: "Floor bump prevents contributor drift; clean tree means no CC-1 noise floor"
      pattern: 'ruff>=0\.15'
    - from: ".planning/REQUIREMENTS.md"
      to: "DEBT-01 line item"
      via: "Closure of this plan ticks DEBT-01 from [ ] to [x]"
      pattern: 'DEBT-01.*\[x\]'
---

<objective>
Eliminate the 79 pre-existing ruff errors across 23 files and bump the ruff floor in `pyproject.toml` to `>=0.15,<1.0`, in atomic-commits-per-rule-code style with pytest + `lint-imports` gates after every batch. Closes DEBT-01.

Purpose: This is the FIRST commit of v1.1 (D-30). Every subsequent v1.1 phase executor needs a clean tree so they don't have to maintain "do NOT touch these noisy files" lists in their prompts (CC-1 mitigation from research/PITFALLS.md). It also bumps the dev-tool floor so contributor environments converge on the 2026-05-21 stable (0.15.14).

Output:
- 5-7 atomic commits (one per rule code batch), conventional-prefixed `chore(06-ruff): ...` for auto-fixes or `fix(06-ruff): ...` for hand-fixes
- `pyproject.toml` ruff floor: `ruff>=0.6,<1.0` → `ruff>=0.15,<1.0` (NO new rule families)
- `uv run ruff check src/ tests/ run.py` returns 0
- 7/7 import-linter contracts KEPT
- Pytest suite stays green (864 passing baseline preserved)
- `.planning/phases/06-debt-paydown-and-cold-start/06-01-SUMMARY.md` documents per-batch commit table + final `ruff check` output
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/RETROSPECTIVE.md
@.planning/phases/06-debt-paydown-and-cold-start/06-CONTEXT.md
@.planning/milestones/v1.0-MILESTONE-AUDIT.md
@.planning/research/STACK.md
@.planning/research/PITFALLS.md
@pyproject.toml

<interfaces>
<!-- The executor needs no codebase interfaces — this plan does not call code. -->
<!-- The executor needs the ruff error inventory and the order in which to fix it. -->
<!-- DO NOT re-derive the rule order: the planner already did the math. -->

## Ruff error inventory (planning-time snapshot 2026-05-23)

| Rule | Count | Auto-fix? | Hand-fix notes |
|------|-------|-----------|----------------|
| `I001` (import sort) | 15 | YES (`--fix`) | Re-run `lint-imports` immediately after this batch (RUFF-2: import re-ordering can expose masked cycles) |
| `F401` (unused import) | 19 | YES (`--fix`) | Trivial removal; safe |
| `UP041` (`asyncio.TimeoutError` → `TimeoutError`) | 7 | YES (`--fix`) | Python 3.11+ unified — safe per RUFF-3, but spot-check no `except (asyncio.TimeoutError, ...)` tuple lost an alias |
| `UP035` (`typing.Callable` → `collections.abc.Callable`) | 1 | YES (`--fix`) | Single file: `src/eldritch_dm/gameplay/exploration_batch.py` |
| `F541` (f-string without placeholders) | 1 | YES (`--fix`) | Trivial — strips the `f` prefix |
| `B904` (raise from in except) | 3 | NO | All 3 in `tests/gameplay/test_party_mode.py` lines 167, 217, 272 — add `from err` or `from None` per intent |
| `F841` (unused local) | 5 | NO | Test scaffolding — either delete or prefix with `_` per D-35 |
| `E501` (line too long, >100) | 28 | NO | Hand-wrap per D-34; only fall back to per-file-ignore if wrap genuinely degrades readability |
| **TOTAL** | **79** | **43 auto** | **36 hand-fix** |

## Mandatory batch order (D-32; DO NOT REORDER)

The order matters because:
1. **Import-sort (`I`) first** — fixing it cleans the diff for every subsequent batch, so reviewer sees only the rule-specific change in each commit.
2. **`UP` second** — auto-fix syntactic modernization across the codebase before touching anything else; reduces noise in later F-rule diffs.
3. **`F` (unused symbols) third** — auto-fixable F401 + F541 first, then hand-fix F841.
4. **`B904` fourth** — hand-fix; small (3 occurrences); needs human judgment on `from err` vs `from None`.
5. **`E501` last** — largest batch (28); split per-file or per-area to keep each commit reviewable.

## Commit prefix template

- Auto-fix commits: `chore(06-ruff): apply --fix --select <CODE>`
- Hand-fix commits: `fix(06-ruff): hand-fix <CODE> in <file_or_area>`
- Floor-bump commit: `chore(06-ruff): bump pyproject floor to >=0.15,<1.0`

All commits MUST end with the project's Co-Authored-By footer per `CLAUDE.md` discipline.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Re-derive inventory + bump floor + apply auto-fix batches (I → UP → F)</name>
  <files>
    pyproject.toml,
    src/eldritch_dm/gameplay/exploration_batch.py,
    tests/bot/cogs/test_combat_cog.py,
    tests/bot/test_channel_edit_budget.py,
    tests/bot/test_dynamic_items_combat_real.py,
    tests/bot/test_embeds_combat_enriched.py,
    tests/bot/test_modals_weapon_select.py,
    tests/gameplay/test_exploration_batch.py,
    tests/gameplay/test_monster_driver.py,
    tests/gameplay/test_party_mode.py,
    tests/gameplay/test_rate_limit.py,
    tests/gameplay/test_reactions.py,
    tests/gameplay/test_riposte_callback.py,
    tests/gameplay/test_riposte_sweeper.py,
    tests/gameplay/test_session_locks.py,
    tests/integration/test_combat_flow.py,
    tests/integration/test_riposte_smoke.py,
    tests/persistence/test_pc_classes_repo.py
  </files>
  <action>
    Step 1 — Re-derive the ruff inventory on the executor's tree (CC-1: planning snapshot may be stale by hours):
    ```bash
    uv run ruff check src/ tests/ run.py --output-format=concise | tee /tmp/ruff-06-01-baseline.txt
    uv run ruff check src/ tests/ run.py --output-format=concise | grep -oE '\b[A-Z]+[0-9]+\b' | sort | uniq -c | sort -rn
    ```
    Sanity-check the counts against the planning snapshot above (~79 errors; 43 auto-fixable). If counts diverge by more than ~5 in any category, STOP and report the divergence — something landed since planning.

    Step 2 — Bump the ruff floor (separate atomic commit before any cleanup so contributor envs converge first):
    Edit `pyproject.toml`'s `[project.optional-dependencies.dev]` table: change `"ruff>=0.6,<1.0"` to `"ruff>=0.15,<1.0"`. Do NOT add `SIM` or `PERF` to `[tool.ruff.lint].select` — D-33 explicitly preserves the existing rule set. Do NOT remove any existing entries in `[tool.ruff.lint.per-file-ignores]`.
    ```bash
    git add pyproject.toml
    git commit -m "$(cat <<'EOF'
    chore(06-ruff): bump pyproject floor to >=0.15,<1.0

    Bump ruff floor from >=0.6,<1.0 to >=0.15,<1.0 per D-33 + research/
    STACK.md decision. Current stable 0.15.14 (PyPI 2026-05-21). Existing
    rule selection (E,F,I,UP,B,ASYNC) preserved; SIM/PERF deliberately
    deferred to v1.2 (don't conflate debt-paydown with raising the bar).

    Closes step 1 of DEBT-01.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    uv run pytest -x -q
    uv run lint-imports
    ```

    Step 3 — Batch A: `I001` (import sort), 15 errors, ALL auto-fixable. Apply, gate, commit:
    ```bash
    uv run ruff check --fix --select I src/ tests/ run.py
    uv run pytest -x -q                # MUST be green; RUFF-2 says import reorder can expose cycles
    uv run lint-imports                # 7/7 contracts KEPT
    git add -A
    git commit -m "$(cat <<'EOF'
    chore(06-ruff): apply --fix --select I (import sort, 15 errors)

    Safe-fix only. lint-imports confirms 7/7 contracts still KEPT
    (RUFF-2 mitigation: re-ordered imports did not expose masked cycles).
    Full pytest suite green.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    ```

    Step 4 — Batch B: `UP` family (`UP041` 7 + `UP035` 1 = 8 errors), ALL auto-fixable.
    Spot-check the `UP041` diff for any `except (asyncio.TimeoutError, OSError):` tuple where the rename matters; the rule should rewrite to `except (TimeoutError, OSError):` — verify the line still parses and the test that owns it still passes.
    ```bash
    uv run ruff check --fix --select UP src/ tests/ run.py
    uv run pytest -x -q
    uv run lint-imports
    git add -A
    git commit -m "$(cat <<'EOF'
    chore(06-ruff): apply --fix --select UP (pyupgrade, 8 errors)

    UP041 collapses asyncio.TimeoutError -> TimeoutError (Python 3.11+
    unified); UP035 swaps typing.Callable -> collections.abc.Callable in
    src/eldritch_dm/gameplay/exploration_batch.py. RUFF-3 spot-check:
    no `except (asyncio.TimeoutError, ...)` tuple lost an alias.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    ```

    Step 5 — Batch C: `F` auto-fixable subset (`F401` 19 + `F541` 1 = 20 errors). F841 is hand-fix only and is handled in Task 2.
    ```bash
    uv run ruff check --fix --select F401,F541 src/ tests/ run.py
    uv run pytest -x -q
    uv run lint-imports
    git add -A
    git commit -m "$(cat <<'EOF'
    chore(06-ruff): apply --fix --select F401,F541 (unused imports + bare f-string, 20 errors)

    F401: 19 unused imports across test files (test_combat_cog,
    test_channel_edit_budget, test_modals_weapon_select, test_party_mode,
    test_rate_limit, test_combat_flow, test_embeds_combat_enriched,
    test_dynamic_items_combat_real, test_exploration_batch).
    F541: tests/gameplay/test_riposte_callback.py:390 — bare f-string
    stripped to a plain string literal.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    ```

    Step 6 — Verify auto-fix progress. Should now have ~36 errors remaining (79 - 43 auto-fixed):
    ```bash
    uv run ruff check src/ tests/ run.py --output-format=concise | grep -oE '\b[A-Z]+[0-9]+\b' | sort | uniq -c | sort -rn
    ```
    Remaining breakdown should be roughly: 28 E501, 5 F841, 3 B904. Hand off to Task 2.

    Do NOT use `--unsafe-fixes` at any point (D-31, RUFF-1). Do NOT add inline `# noqa: <CODE>` to silence errors (D-34/D-35).
  </action>
  <verify>
    <automated>uv run ruff check src/ tests/ run.py --output-format=concise | tee /tmp/ruff-after-task1.txt; uv run pytest -x -q; uv run lint-imports; ERR_COUNT=$(grep -cE '^[a-z]' /tmp/ruff-after-task1.txt || true); echo "remaining ruff errors: $ERR_COUNT (expected ~36)"; test "$ERR_COUNT" -le 40</automated>
  </verify>
  <done>
    `pyproject.toml` declares `ruff>=0.15,<1.0`; 4 atomic commits landed (floor bump + I + UP + F-auto); ~36 ruff errors remain (only the hand-fix bucket); pytest green; 7/7 import-linter contracts KEPT; zero use of `--unsafe-fixes`.
  </done>
</task>

<task type="auto">
  <name>Task 2: Hand-fix remaining errors (B904 → F841 → E501) with per-rule atomic commits</name>
  <files>
    tests/gameplay/test_party_mode.py,
    tests/bot/cogs/test_combat_cog.py,
    tests/bot/test_modals_weapon_select.py,
    tests/gameplay/test_rate_limit.py,
    tests/gameplay/test_riposte_callback.py,
    tests/bot/test_dynamic_items.py,
    tests/bot/test_dynamic_items_combat_real.py,
    tests/bot/test_modals_weapon_select.py,
    tests/gameplay/test_reactions.py,
    tests/gameplay/test_riposte_callback.py,
    tests/integration/test_combat_flow.py
  </files>
  <action>
    Step 1 — Hand-fix `B904` (3 errors, all in `tests/gameplay/test_party_mode.py` at lines ~167, ~217, ~272):

    Read each `except` block first. The pattern is `raise SomeError(...)` inside `except Exception as err:` without `from err` or `from None`. Decision per occurrence:
    - If the new exception SEMANTICALLY replaces the original (lost context is intentional): use `raise NewError(...) from None`
    - If the new exception WRAPS the original (chain matters for debug): use `raise NewError(...) from err`

    For test-double helpers (most likely case here), `from None` is usually correct — these are scaffolding raises that shouldn't pollute pytest tracebacks with the original. Apply, then:
    ```bash
    uv run pytest tests/gameplay/test_party_mode.py -x -q
    uv run pytest -x -q                # full suite, no regression
    uv run lint-imports
    git add tests/gameplay/test_party_mode.py
    git commit -m "$(cat <<'EOF'
    fix(06-ruff): hand-fix B904 in tests/gameplay/test_party_mode.py

    Three `raise NewError(...)` inside `except` clauses now use explicit
    `from None` (test scaffolding helpers — original context is not
    relevant to assertion failures). All three are in test doubles, not
    production code. pytest green; lint-imports 7/7 KEPT.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    ```

    Step 2 — Hand-fix `F841` (5 errors per planning snapshot; re-derive on the executor's tree):
    ```bash
    uv run ruff check --select F841 src/ tests/ run.py --output-format=concise
    ```
    For each occurrence:
    - If the local is truly dead (assigned but never read, not even for shape): DELETE the assignment.
    - If the local is intentionally retained (e.g., it documents the return shape of a mock, or pytest scaffolding): prefix with `_` per D-35.
    Examples from planning snapshot (verify against fresh `ruff` output before editing):
    - `tests/bot/cogs/test_combat_cog.py:627` — `results = ...` — likely deletable
    - `tests/bot/cogs/test_combat_cog.py:701` — `mock_gs = ...` — check context: scaffolding for asserting `mock_gs.assert_called` later? If unused, delete.
    - `tests/bot/test_modals_weapon_select.py:169` — `mock_warn = ...` — check context
    - `tests/gameplay/test_rate_limit.py:145` — `real_time_base = ...` — likely deletable
    - `tests/gameplay/test_riposte_callback.py:445` — `n = ...` — check context

    Per affected file, atomic commit:
    ```bash
    git add <file>
    git commit -m "$(cat <<'EOF'
    fix(06-ruff): hand-fix F841 in <file>

    <one-liner per occurrence: deleted vs prefixed with _>

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    ```
    Re-run `pytest -x -q` and `lint-imports` between commits.

    Step 3 — Hand-fix `E501` (28 errors per planning snapshot, largest batch). Group by file to keep each commit reviewable:

    For each file with E501 hits, attempt hand-wrap FIRST (D-34):
    - Long string literals: break across lines with implicit concatenation (`"foo" "bar"`)
    - Long function calls: wrap arguments across lines, one per line if needed
    - Long assertion messages: extract to a local `msg = "..."` then `assert cond, msg`
    - Long lambdas / dict literals in fixtures: extract to named helper

    Only fall back to per-file-ignore IF the hand-wrap genuinely degrades readability AND you can justify it in the commit message. The existing `[tool.ruff.lint.per-file-ignores]` table already has many `E501` exceptions — adding a new file is acceptable when justified, but is the LAST resort.

    Files with E501 errors (planning snapshot; verify on executor's tree):
    - `tests/bot/test_dynamic_items.py` (4 hits, lines 62-67) — likely long mock chain; hand-wrap recommended
    - `tests/bot/test_dynamic_items_combat_real.py` (5 hits)
    - `tests/bot/test_modals_weapon_select.py` (1 hit, line 185)
    - `tests/gameplay/test_reactions.py` (1 hit, line 433)
    - `tests/gameplay/test_riposte_callback.py` (1 hit, line 336)
    - `tests/integration/test_combat_flow.py` (16 hits) — LARGEST single-file bucket; consider per-file-ignore if the file is fundamentally long-fixture-driven (mirrors precedent of `test_8player_load.py` already in per-file-ignores)

    Suggested commit grouping (one commit per file unless a single-file fix is tiny):
    ```bash
    # Commit per file with conventional prefix
    git add tests/bot/test_dynamic_items.py
    git commit -m "$(cat <<'EOF'
    fix(06-ruff): hand-fix E501 in tests/bot/test_dynamic_items.py

    Wrapped 4 long mock-chain lines (>100 chars) across multiple lines.
    No behavior change; readability preserved.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    # ... continue per file ...
    ```

    For `test_combat_flow.py` specifically: if the 16 hits are dominated by long-fixture-builder lines that would become substantially less readable wrapped, add the file to `[tool.ruff.lint.per-file-ignores]` with the comment style of existing entries:
    ```toml
    # tests/integration/test_combat_flow.py: long mock-chain assertion messages and
    # fixture builders exceed 100 chars; readability is better as-is than artificially wrapping.
    "tests/integration/test_combat_flow.py" = ["E501"]
    ```
    Commit that pyproject change separately:
    ```bash
    git add pyproject.toml
    git commit -m "$(cat <<'EOF'
    chore(06-ruff): per-file-ignore E501 in tests/integration/test_combat_flow.py

    16 long lines are dominated by mock-chain assertions and 8-actor combat
    fixture builders. Mirrors precedent of test_8player_load.py per-file-
    ignore. Hand-wrapping degrades readability for this load-test scenario.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    ```

    Step 4 — Final verification:
    ```bash
    uv run ruff check src/ tests/ run.py
    # MUST return: "All checks passed!"
    uv run pytest -x -q
    # MUST be green; 864+ passing
    uv run lint-imports
    # MUST report 7/7 contracts KEPT
    ```

    Step 5 — Tick DEBT-01 in `.planning/REQUIREMENTS.md` (atomic paperwork commit per RETROSPECTIVE.md Lesson 2 — REQUIREMENTS drift is a hard gate now):
    ```bash
    # Edit .planning/REQUIREMENTS.md: change "- [ ] **DEBT-01**:" to "- [x] **DEBT-01**:"
    # Update the Traceability table row for DEBT-01: TBD -> 06-01-PLAN-ruff-cleanup
    git add .planning/REQUIREMENTS.md
    git commit -m "$(cat <<'EOF'
    docs(06-01): tick DEBT-01 in REQUIREMENTS.md

    All 79 ruff errors cleaned; floor bumped to >=0.15,<1.0; rule set
    unchanged. See .planning/phases/06-debt-paydown-and-cold-start/
    06-01-SUMMARY.md for per-batch commit table.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    ```

    Step 6 — Write SUMMARY:
    Create `.planning/phases/06-debt-paydown-and-cold-start/06-01-SUMMARY.md` per `@$HOME/.claude/get-shit-done/templates/summary.md`. Include:
    - Per-batch commit table: rule code, error count fixed, commit SHA, pytest+lint-imports status
    - Files added to `[tool.ruff.lint.per-file-ignores]` (if any) with justification per file
    - Final `ruff check` output (should be "All checks passed!")
    - Final pytest count (should match or exceed 864 baseline)
    - Closes DEBT-01 statement
  </action>
  <verify>
    <automated>uv run ruff check src/ tests/ run.py 2>&1 | tee /tmp/ruff-final.txt; grep -q "All checks passed" /tmp/ruff-final.txt; uv run pytest -x -q; uv run lint-imports; grep -E '^- \[x\] \*\*DEBT-01\*\*' .planning/REQUIREMENTS.md</automated>
  </verify>
  <done>
    `uv run ruff check src/ tests/ run.py` returns "All checks passed!"; pytest suite green (>=864 passing); 7/7 import-linter contracts KEPT; DEBT-01 ticked in REQUIREMENTS.md; SUMMARY.md committed with per-batch table; zero use of `--unsafe-fixes` across the entire plan; all commits conventional-prefixed `chore(06-ruff): ...` or `fix(06-ruff): ...`.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Executor (Claude) ↔ codebase | This plan formats / rewrites imports / removes unused symbols across 23 files. Each commit is gated by pytest + lint-imports to catch any inadvertent behavior regression. |
| `pip` install of new ruff version | Floor bump pulls a new ruff wheel from PyPI. The package is in the v1.0 pinned dev-deps; floor bump only changes the minimum version. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-01 | Tampering | `--unsafe-fixes` rewrites semantically (RUFF-1) | mitigate | D-31: forbidden. Executor commands explicitly use `--fix` only (never `--fix --unsafe-fixes`). Verification step greps the commit messages and bash history for `--unsafe-fixes` and fails if found. |
| T-06-02 | Tampering | Import re-ordering exposes a masked cycle (RUFF-2) | mitigate | `lint-imports` re-run after every batch; 7/7 contracts must remain KEPT. Atomic commit per rule code means any cycle exposure is isolated to a single bisectable commit. |
| T-06-03 | Tampering | `UP041` collapse of `asyncio.TimeoutError` breaks `except` tuple aliasing (RUFF-3) | mitigate | Pytest after the UP batch catches any runtime regression; manual spot-check called out in Task 1 Step 4. |
| T-06-04 | Repudiation | Bundled / non-atomic commits make bisect impossible if a regression sneaks in | mitigate | D-32: one rule code per commit, conventional prefixes; bisect-friendly history is the load-bearing recovery mechanism. |
| T-06-05 | Denial of Service | Pre-commit hook fails on a touched file, executor uses `--no-verify` to push through | mitigate | D-43: `--no-verify` forbidden; fix the underlying issue and create a NEW commit. Executor's commit commands omit `--no-verify` entirely. |
| T-06-SC | Tampering | Supply-chain — pulling a new ruff version from PyPI | mitigate | `ruff` is in v1.0's pinned dev-deps (`ruff>=0.6,<1.0`). Floor bump to `>=0.15,<1.0` only changes the minimum; the package itself was already audited. Latest stable (0.15.14, 2026-05-21) is documented in research/STACK.md with PyPI link. Astral-sh is the canonical maintainer. No `[ASSUMED]`/`[SUS]`/`[SLOP]` flags — package is `[OK]`, no checkpoint required. |
</threat_model>

<verification>
**Plan-level checks (must all pass before SUMMARY commit):**

1. `uv run ruff check src/ tests/ run.py` returns exit 0 with "All checks passed!" output.
2. `uv run pytest -x -q` exits 0; passing count >= 864 (v1.0 baseline). No new failures, no newly-skipped tests.
3. `uv run lint-imports` reports `7 broken / 7 contracts kept` — wait, it must report 7/7 KEPT and 0 broken.
4. `git log --oneline -- pyproject.toml src/ tests/ run.py | head -20` — every commit since the floor bump has prefix `chore(06-ruff): ...` or `fix(06-ruff): ...`. No bundled / off-prefix commits.
5. `! git log --all --format=%s | grep -E '\-\-unsafe-fixes'` — zero matches; no commit mentions `--unsafe-fixes`.
6. `grep -E '^- \[x\] \*\*DEBT-01\*\*' .planning/REQUIREMENTS.md` returns the ticked line.
7. `.planning/phases/06-debt-paydown-and-cold-start/06-01-SUMMARY.md` exists and lists per-batch commit SHAs in a table.

**Risks identified:**

- **R-1 (LOW):** Re-derived inventory diverges from planning snapshot. Plan accepts: executor re-runs `ruff check` first thing (Task 1 Step 1) and STOPs + reports if divergence >5 errors per rule. Mitigation: deterministic — count is testable.
- **R-2 (LOW):** A hand-wrap on E501 inadvertently changes a string literal (line continuation vs implicit concat). Pytest after every commit catches it; bisect to the commit; revert and re-do that one file. Mitigation: atomic commits.
- **R-3 (LOW):** `UP041` collapses `asyncio.TimeoutError` in an `except` tuple where another name was the SOLE difference between two branches. Spot-check called out in Task 1 Step 4; pytest catches the regression.
- **R-4 (LOW):** A test depending on `__future__` annotations interacts oddly with `UP007` (`Optional[X]` → `X | None`) in eval-string contexts. The planning-time ruff snapshot showed NO UP007 hits in this codebase — risk is theoretical only. RUFF-3 calls for `pyright` after UP batch as belt-and-suspenders; not enforced here because pyright isn't in dev-deps.
- **R-5 (MEDIUM):** A pre-commit hook other than ruff (e.g., the EDM001 AST linter from Phase 2 Plan 03) fires on a file the executor touched and fails. Resolution path: fix the EDM001 issue in the same commit (it's a related code-quality fix), NOT split into a follow-up — but if the EDM001 fix is large enough to warrant its own commit, that's fine. Either way, no `--no-verify`.
</verification>

<success_criteria>
- `uv run ruff check src/ tests/ run.py` returns exit 0 ("All checks passed!"); was 79 errors at plan start.
- `pyproject.toml` declares `ruff>=0.15,<1.0`; rule selection `[E, F, I, UP, B, ASYNC]` unchanged.
- 5-7 atomic commits landed: floor bump → I → UP → F-auto → B904 → F841 → E501 (some may be split per-file).
- 7/7 import-linter contracts remain KEPT throughout (verified after every batch).
- Pytest suite green; passing count >= 864 (v1.0 baseline preserved).
- DEBT-01 ticked `[x]` in `.planning/REQUIREMENTS.md`; Traceability row updated.
- `.planning/phases/06-debt-paydown-and-cold-start/06-01-SUMMARY.md` exists with per-batch commit table.
- Zero use of `--unsafe-fixes` in commands or commit messages.
- Zero `--no-verify` commits.
- Conventional-prefix discipline kept: every commit `chore(06-ruff): ...` or `fix(06-ruff): ...`.
- Tree is now clean: subsequent v1.1 phase executors do NOT need a "do NOT touch these noisy files" list (CC-1 mitigation discharged).
</success_criteria>

<output>
Create `.planning/phases/06-debt-paydown-and-cold-start/06-01-SUMMARY.md` per the standard template, including:

- **Per-batch commit table** with columns: batch | rule code | files touched | errors fixed | commit SHA | pytest result | lint-imports result
- **`pyproject.toml` per-file-ignore additions** (if any) with one-line justification each
- **Final ruff output:** copy-paste the "All checks passed!" line
- **Final pytest baseline:** "<N> passed, <M> skipped, 0 failed" — must match or exceed 864 passing
- **DEBT-01 closure statement:** "Closes DEBT-01. 79 → 0 ruff errors across 23 files. Floor bumped to `ruff>=0.15,<1.0`. Existing rule set (`E,F,I,UP,B,ASYNC`) preserved per D-33."
- **Handoff signal to Plan 02:** "Tree is clean. Plan 02 (cold-start E2E) may now land without CC-1 noise floor in its diff."
</output>
