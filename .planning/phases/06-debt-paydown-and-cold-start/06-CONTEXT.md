# Phase 6: Debt Paydown + Cold-Start Smoke — Context

**Gathered:** 2026-05-23
**Status:** Ready for planning (research complete; v1.0 audit lessons logged)
**Mode:** Synthesized from v1.1 REQUIREMENTS (DEBT-01, DEBT-02), RETROSPECTIVE.md (cold-start E2E gap = `NEEDS IMPROVEMENT v1.1`), v1.0-MILESTONE-AUDIT.md (G-1 origin + commit `4c15641` fix), and research/{SUMMARY,STACK,PITFALLS}.md (all 4 researchers converged on "Ruff cleanup FIRST, non-negotiable").

<domain>
## Phase Boundary

Infrastructure-only. **No user-visible behavior changes.** Two atomic deliverables that together extinguish the v1.0 debt pile and lock in the discipline that should have caught G-1 before it shipped:

1. **DEBT-01 — Ruff cleanup.** All 79 ruff errors across 23 pre-existing files reduced to 0. Floor bumped to `ruff>=0.15,<1.0` in `pyproject.toml`. **Existing rule set (`E,F,I,UP,B,ASYNC`) preserved** — `SIM`/`PERF` explicitly deferred to v1.2 (research consensus: don't conflate "pay down debt" with "raise the bar").
2. **DEBT-02 — Cold-start E2E smoke.** New `tests/integration/test_cold_start_e2e.py` exercises the documented quickstart end-to-end with **zero shared fixtures pre-creating state**: `bot.setup_hook` → simulate `/start_game` → simulate ready-up → assert orchestrator task alive in the **same process lifetime**. Test must **FAIL** against commit `7d307a1` (Phase 5 Plan 03 closure, before G-1 fix) and **PASS** against current `main` — proof it would have caught G-1.

**In scope:**
- Ruff `--fix` on 43 auto-fixable errors, hand-fix on 36, atomic commit per rule batch
- `lint-imports` re-run + `pytest` after every commit (RUFF-2: import-sort can expose masked cycles)
- `pyproject.toml` floor bump (`ruff>=0.6,<1.0` → `ruff>=0.15,<1.0`)
- One new integration test exercising the cold-start lobby→ready→orchestrator-alive path
- Historical-regression verification (git stash + checkout `7d307a1` + run test + expect fail + restore + expect pass)

**NOT in scope (explicit deferrals):**
- `SIM` / `PERF` ruff rules (v1.2)
- `--unsafe-fixes` (forbidden per research; RUFF-1)
- Adding new tests beyond the cold-start E2E (other phases own their own smoke tests)
- Touching feature code in `src/` (this phase only formats/imports; behavioral fixes are out of scope)
- `__main__` token parity (Phase 7 — SAFETY-03 owns it)
- Sanitizer modal coverage (Phase 7 — SAFETY-01 owns it)
- DM_OFFLINE warning (Phase 7 — SAFETY-02 owns it)

</domain>

<decisions>
## Implementation Decisions

### Plan structure (locked at planning input)
- **D-29:** Phase 6 ships **two plans**, one per requirement, atomic. Plan 01 = DEBT-01 (ruff). Plan 02 = DEBT-02 (cold-start E2E). No bundling.
- **D-30:** **Plan 01 (Ruff cleanup) is the FIRST commit of v1.1.** All subsequent v1.1 phases work in a clean tree per research consensus and CC-1 (untracked-files-contaminate-executor) mitigation.

### Ruff cleanup approach (DEBT-01)
- **D-31:** **`--unsafe-fixes` is forbidden** (RUFF-1, Context7-verified). Use `ruff check --fix` (safe-only) on the 43 auto-fixable errors; hand-fix the remaining 36.
- **D-32:** **Atomic commit per rule batch.** Order: `I001` (import sort) → `UP` (UP041 + UP035 pyupgrade) → `F` (F401 unused imports + F541 f-string + F841 unused locals) → `B904` (exception chaining) → `E501` (line length). Pytest + `lint-imports` after every batch. Conventional prefix: `chore(06-ruff): apply --fix --select I` for auto-fixes, `fix(06-ruff): hand-fix B904 in <file>` for hand-fixes.
- **D-33:** **Existing rule set preserved** (`E,F,I,UP,B,ASYNC`). `SIM`/`PERF` explicitly NOT added. Floor bump only: `ruff>=0.6,<1.0` → `ruff>=0.15,<1.0` (current stable 0.15.14 verified 2026-05-21).
- **D-34:** **E501 (28 errors) handling:** prefer hand-wrapping over `noqa` or per-file-ignores. If a line genuinely cannot wrap cleanly (long assertion message, fixture URL), extend the existing `[tool.ruff.lint.per-file-ignores]` table — never add inline `# noqa: E501`.
- **D-35:** **F841 (unused locals) handling:** delete unused assignment if truly dead; if intentionally retained for shape (e.g., test scaffolding), prefix variable with `_` to silence ruff without `noqa`.

### Cold-start E2E test approach (DEBT-02)
- **D-36:** **Test file location:** `tests/integration/test_cold_start_e2e.py`. NOT under `tests/bot/` — this is cross-cog integration that exercises bot construction.
- **D-37:** **Zero shared fixtures that pre-create state.** No `conftest.py` reuse beyond ambient ones (`tmp_path`, `caplog`). The test constructs `EldritchBot` from settings, calls `setup_hook` directly, then simulates the lobby flow via direct `ReadyButton.callback` invocation with a mocked `discord.Interaction`. This mirrors how `test_lobby_to_exploration_flow.py` already drives G-1 closure, but is broader: it covers the FULL cold-start chain (settings → bootstrap → setup_hook → cog load → ready-up → orchestrator alive).
- **D-38:** **Same process lifetime.** The test must NOT spawn a subprocess and must NOT restart the bot between setup_hook and ready-up. The whole point is "no RESUME path saves us this time" — the orchestrator must start from the click, not from setup_hook's restart loop.
- **D-39:** **External-dependency strategy:** oMLX and dm20 are stubbed at the MCP client boundary (`AsyncMock` on `MCPClient.call` or `respx` against `localhost:8765/v1`). Discord is NOT touched — `interaction.client = bot` is wired directly; we never call `bot.run(...)`.
- **D-40:** **Historical-regression verification protocol** (the proof that the test catches G-1):
  ```bash
  # Step 1: ensure clean tree (the test file is the only new artifact)
  git stash --keep-index --include-untracked
  # Step 2: check out the pre-G-1-fix commit
  git checkout 7d307a1
  # Step 3: apply just the new test file from the stash
  git checkout stash@{0} -- tests/integration/test_cold_start_e2e.py
  # Step 4: run the test — EXPECT fail
  uv run pytest tests/integration/test_cold_start_e2e.py -x -v
  # Step 5: restore main
  git checkout main
  git stash pop
  # Step 6: re-run — EXPECT pass
  uv run pytest tests/integration/test_cold_start_e2e.py -x -v
  ```
  Document the outcome in the plan's SUMMARY.md (RED→GREEN gate proof).
- **D-41:** **Assertion shape:** at end of the simulated all-ready click, the test asserts `bot.orchestrator._tasks[channel_id_str]` exists and `.done() is False`. Stronger assertion (one round of `party_pop_action` returns expected envelope) is **out of scope** — the orchestrator being alive is the load-bearing fact G-1 missed.

### Quality gates (apply to both plans)
- **D-42:** Every commit in Phase 6 must pass `uv run pytest`, `uv run ruff check src/ tests/ run.py`, and `uv run lint-imports`. 7/7 import-linter contracts must remain KEPT. Pre-commit hooks unchanged.
- **D-43:** No `--no-verify` commits. If a pre-commit hook fails, fix the underlying issue and create a NEW commit (per global CLAUDE.md and project commit discipline).

</decisions>

<dependencies>
## Phase Dependencies

- **Depends on:** Nothing (v1.0 baseline at `main`).
- **Blocks:** All subsequent v1.1 phases. Phase 7+ executors expect a zero-ruff-error tree (CC-1 mitigation).

## File Ownership (Plan 01 vs Plan 02 — must NOT overlap)

- **Plan 01 (Ruff cleanup):** touches ~23 files across `src/eldritch_dm/` + `tests/` + `run.py` (full list derived from `ruff check` output during planning). Also touches `pyproject.toml` for the floor bump.
- **Plan 02 (Cold-start E2E):** creates **exactly one new file** — `tests/integration/test_cold_start_e2e.py`. No edits to existing source.

Zero file overlap → plans CAN run in parallel, but **D-30 forces Plan 01 to land first** so Plan 02's pre-commit hooks operate on a clean tree.

</dependencies>

<open_questions>
## Open Questions (resolve during planning / executor)

1. **E501 hand-wrap vs per-file-ignore policy:** Plan 01 prefers hand-wrap (D-34). If a hand-wrap genuinely degrades readability (e.g., breaks a long URL or a fixture-builder one-liner), the executor's call is to add the file to the existing `[tool.ruff.lint.per-file-ignores]` table. Document the decision per-file in the plan's SUMMARY.
2. **Cold-start E2E: dm20 mock fidelity.** Should `party_pop_action` return an empty action (orchestrator parks waiting) or a non-empty action (orchestrator drives one full pop→thinking→resolve cycle)? **Recommended:** empty — the test's load-bearing assertion is "orchestrator task is alive after the click", not "narration round-trips". Keeping the mock minimal also keeps the test fast (<2s wall-clock).
3. **Settings injection:** the cold-start test needs a `Settings` instance with a valid `DISCORD_TOKEN` placeholder, a real `eldritch_db_path` (tmp), and a stubbed `omlx_endpoint`. Use `Settings(...)` directly with kwargs; do NOT rely on `.env` discovery in tests.
</open_questions>
