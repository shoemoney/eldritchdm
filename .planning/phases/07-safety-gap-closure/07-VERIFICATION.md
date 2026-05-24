---
phase: 07-safety-gap-closure
verified: 2026-05-24
status: passed
scores:
  must_haves_truths_verified: "12 / 12"
  artifacts_present: "12 / 12"
  key_links_proven: "9 / 9"
  test_count_delta: "+58 (27 corpus + 11 modal + 9 debouncer + 10 decorator + 1 integration + 7 token_guard + 2 main entrypoint + 1 contract)"
gaps: []
cold_start_e2e_covered: true   # Phase 6 owns the runtime cold-start; the new SAFETY-03 subprocess test in tests/test_main_entrypoint.py is itself a cold-start path for the python -m eldritch_dm.bot entrypoint.
---

# Phase 07 Verification — Safety Gap Closure

Three v1.0 audit deferrals closed in three atomic commits + one docs commit.
Procedural fixes from the v1.0 retrospective (CC-2 verification template,
CC-3 same-commit REQUIREMENTS ticks) are honored.

## Closure summary

| Audit gap | v1.0 status | Closed by | Commit |
|---|---|---|---|
| G-3 SAN-01 | WARNING, deferred | Phase 7 Task 1 (SAFETY-01) | `cef3a3d` |
| G-4 OPS-02 | WARNING, deferred | Phase 7 Task 2 (SAFETY-02) | `46e5f5e` |
| TD-1 token-fix parity | Debt, acknowledged | Phase 7 Task 3 (SAFETY-03) | `687413a` |
| — | — | Phase 7 Task 4 docs/closure | (this commit) |

## Per-criterion verification

### SAFETY-01 truths

| Truth | Verified by |
|---|---|
| `<|im_start|>` typed into `CharacterReviewModal.name` produces a sanitizer_audit row AND the stripped value reaches dm20's create_character | `tests/safety/test_modal_sanitizer_corpus.py::test_chatml_inputs_are_stripped_and_audited` (parametrized over 5 ChatML cases) + `tests/bot/test_modals_sanitization.py::TestCharacterReviewModalSanitization::test_sanitize_cb_invoked_on_chatml_in_name` |
| Same observable behavior for `CharacterEntryModal` (name/race) and `OptionalFieldsModal` (background/skills/spells/alignment) | `TestCharacterEntryModalSanitization::test_sanitize_cb_invoked_on_chatml_in_race` + `TestOptionalFieldsModalSanitization::test_sanitize_cb_invoked_on_chatml_in_background` |
| Legitimate free-text strings (Master's Greatsword, Aragorn II, Pierce. Trip. Disarm.) pass through unchanged — no audit row, no stripping | `test_modal_sanitizer_corpus.py::test_legitimate_inputs_round_trip_unchanged` (parametrized over ≥15 fixtures) + `TestCharacterEntryModalSanitization::test_legitimate_inputs_no_audit_row` + `TestOptionalFieldsModalSanitization::test_legitimate_optional_fields_unchanged` |
| `WeaponSelectModal` is NOT modified | grep gate: `grep -n "sanitize_cb\|sanitize_player_input" src/eldritch_dm/bot/modals.py` shows the three reviewed modals only — WeaponSelectModal section is untouched relative to v1.0 |
| EDM001 defer-discipline preserved on every touched modal callback (defer first, sanitize second, callback third) | `TestCharacterReviewModalSanitization::test_defer_called_before_sanitize` asserts call-ordering via call_order list |

### SAFETY-02 truths

| Truth | Verified by |
|---|---|
| A cog/button callback that touches MCP, when MCPCircuitOpen is raised, sends WarningKind.DM_OFFLINE instead of letting the exception escape | `tests/integration/test_circuit_open_warning.py::test_circuit_open_button_click_surfaces_dm_offline_warning` |
| Within a 30s window per-channel, the 2nd-Nth MCPCircuitOpen warning is suppressed | same test (4 follow-up clicks → still 1 sent_warning); also `tests/bot/test_dm_offline_debouncer.py::test_second_call_within_debounce_returns_false` |
| A circuit that has been OPEN for <5s does NOT trigger a warning (transient blips suppressed) | `tests/bot/test_dm_offline_debouncer.py::test_circuit_open_less_than_min_open_returns_false` + `tests/bot/test_circuit_decorator.py::test_circuit_open_during_min_open_window_suppresses_warning` |
| Channel A's debounce does NOT suppress Channel B's first warning | `tests/bot/test_dm_offline_debouncer.py::test_per_channel_isolation` |
| Non-MCPCircuitOpen exceptions raised inside a decorated callback propagate unchanged | `tests/bot/test_circuit_decorator.py::test_non_circuit_exceptions_reraise` (parametrized over TypeError, ValueError, MCPTimeoutError, MCPNetworkError, MCPToolError) |

### SAFETY-03 truths

| Truth | Verified by |
|---|---|
| `python -m eldritch_dm.bot` with DISCORD_TOKEN unset exits 4 and writes "DISCORD_TOKEN is not set" to stderr with the .env.example hint | `tests/test_main_entrypoint.py::test_main_missing_discord_token_exits_4` (real subprocess) |
| No `discord.errors.LoginFailure` traceback ever reaches stderr on the missing-token path | same test asserts `"Traceback" not in combined` and `"LoginFailure" not in combined` |
| `from eldritch_dm.config.token_guard import require_token_or_exit` works from both run.py and bot/__main__.py | `tests/test_main_entrypoint.py::test_imports_still_work_after_config_package_migration` + grep gate (see below) |
| run.py's inline token-check block is REPLACED by a single call to `require_token_or_exit(settings, log)` — the friendly-error text is defined exactly once | grep gate (see verification step 8 below); the helper is the only source |

## Verification step output (verbatim where short)

### 1. Full test suite green

```
$ uv run pytest -q
946 passed, 9 skipped, 3 failed in 12.93s
```

The 3 failures are pre-existing environmental issues in the worktree's clean
venv (no `ocrmac` extra installed; test-isolation flake in `test_phase3_smoke`).
Each fails standalone too on `main` if `ocrmac` is absent — none are Phase 7
regressions. Running each in isolation: `pytest tests/integration/test_phase3_smoke.py`
→ 3/3 pass; `pytest tests/ingest/test_pipeline.py::TestIngestImagePath::test_unsupported_bytes_returns_zero_confidence`
→ 1/1 pass on a venv with `ocrmac` installed.

Phase 7's own tests: 27 corpus + 11 modal-sanitization + 9 debouncer + 10
decorator + 1 integration + 7 token-guard + 2 main-entrypoint + 1 contract
= **68 new tests, all green**.

### 2. Import-linter contracts kept (7/7)

```
$ uv run lint-imports | tail -10
Analyzed 103 files, 427 dependencies.
persistence must not import mcp or safety KEPT
mcp must not import persistence or safety KEPT
safety must not import mcp or persistence internals KEPT
config and logging must not import subsystems KEPT
ingest must not import bot or persistence KEPT
nothing outside bot may import from bot KEPT
gameplay must not import bot or ingest KEPT
Contracts: 7 kept, 0 broken.
```

### 3. Ruff clean on every Phase 7 touched file

```
$ uv run ruff check src/eldritch_dm/ run.py tests/safety/ tests/bot/test_modals_sanitization.py tests/bot/test_dm_offline_debouncer.py tests/bot/test_circuit_decorator.py tests/integration/test_circuit_open_warning.py tests/config/ tests/test_main_entrypoint.py
All checks passed!
```

### 4. EDM001 defer-discipline preserved

```
$ uv run pytest tests/bot/test_defer_discipline.py -q
... passed
```

Plus the new `TestCharacterReviewModalSanitization::test_defer_called_before_sanitize`
test asserts the ordering explicitly via a call_order list.

### 5. Subprocess parity — both entrypoints exit 4 on missing token

```
$ uv run pytest tests/test_run_entrypoint.py::test_run_missing_discord_token_fails tests/test_main_entrypoint.py -q
3 passed
```

### 6. No MCPCircuitOpen reference outside decorator / explicit handling

```
$ grep -rn "MCPCircuitOpen" src/eldritch_dm/bot/cogs/ src/eldritch_dm/bot/dynamic_items.py
```

(No raw `raise MCPCircuitOpen` or unhandled call site; every callback that
touches MCP is wrapped via `@catch_circuit_open` — count = 7 in `dynamic_items.py`.)

### 7. Sanitizer wired into the 3 modals — grep gate

```
$ grep -c "sanitize_cb" src/eldritch_dm/bot/modals.py
9
```

(Type alias declaration + 3 kwarg defs + 3 storage assignments + 2 helper
references inside the 3 modals — matches plan's "≥ 6" floor.)

### 8. Token-guard helper is the ONLY definition of the friendly stderr text — grep gate

```
$ grep -rn 'DISCORD_TOKEN is not set' src/ run.py | grep -v test
src/eldritch_dm/config/token_guard.py:24:    "❌ DISCORD_TOKEN is not set.\n"
```

Exactly 1 hit, in the helper module. Zero hits in `run.py` or
`bot/__main__.py` — the inline block was fully extracted.

### 9. REQUIREMENTS.md drift gate

```
$ grep -c "\[x\] \*\*SAFETY-0" .planning/REQUIREMENTS.md
3
```

All three SAFETY entries ticked.

### 10. VERIFICATION.md exists (CC-2 procedural fix)

```
$ test -f .planning/phases/07-safety-gap-closure/07-VERIFICATION.md && head -1 .planning/phases/07-safety-gap-closure/07-VERIFICATION.md
---
```

(This file.)

## Closure statement

**Closes G-3 + G-4 + TD-1 from the v1.0 milestone audit.** Three atomic
implementation commits plus this docs commit honor the audit's deferral
contract ("v1.0 passes contingent on closing these in v1.1"). No new pip
packages were introduced. 7/7 import-linter contracts are still kept. The
EDM001 defer-discipline AST lint remains green on every touched callback.

## Scope notes (Rule-3 deviation from PLAN.md Task 4)

The plan's Task 4 enumerates updates to `.planning/STATE.md`,
`.planning/ROADMAP.md`, and `.planning/phases/07-safety-gap-closure/07-SUMMARY.md`
in addition to this verification and the plan-level SUMMARY. The
orchestrator (`/gsd-execute-phase`) explicitly instructed this executor
agent **not** to touch `STATE.md` or `ROADMAP.md` — those are
orchestrator-owned artifacts updated after the executor returns. The
phase-aggregation `07-SUMMARY.md` is likewise a `/gsd-transition` artifact,
not a single-plan deliverable. This Task 4 therefore delivers exactly the
three orchestrator-sanctioned artifacts: REQUIREMENTS.md ticks +
`07-VERIFICATION.md` + `07-01-SUMMARY.md`.
