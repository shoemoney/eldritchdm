---
phase: 07-safety-gap-closure
plan: 01
subsystem: bot+config+mcp+safety
tags: [safety, audit-closure, sanitizer, circuit-breaker, modals, entrypoint, td-paydown]
requires:
  - 06-01  # ruff cleanup baseline
  - 06-02  # cold-start E2E (process-spawn helper pattern reused)
provides:
  - SAFETY-01-closure   # SAN-01 audit gap (G-3)
  - SAFETY-02-closure   # OPS-02 audit gap (G-4)
  - SAFETY-03-closure   # __main__ token-fix parity (TD-1)
  - dm_offline_debouncer-pattern  # 30s + 5s gates for future warning kinds
  - catch_circuit_open-decorator  # reusable MCPCircuitOpen → ephemeral warning wrapper
  - token_guard-helper            # single source of truth for missing-DISCORD_TOKEN
  - bot.sanitizer_audit_callback  # memoized sync→async audit bridge
  - circuit_breaker.opened_at     # monotonic open-transition timestamp
affects:
  - src/eldritch_dm/bot/modals.py
  - src/eldritch_dm/bot/bot.py
  - src/eldritch_dm/bot/cogs/exploration.py
  - src/eldritch_dm/bot/cogs/ingest.py
  - src/eldritch_dm/bot/dynamic_items.py
  - src/eldritch_dm/bot/circuit_decorator.py       # NEW
  - src/eldritch_dm/bot/dm_offline_debouncer.py    # NEW
  - src/eldritch_dm/bot/__main__.py
  - src/eldritch_dm/mcp/health.py
  - src/eldritch_dm/config/__init__.py             # rename from config.py
  - src/eldritch_dm/config/token_guard.py          # NEW
  - run.py
  - tests/safety/test_modal_sanitizer_corpus.py    # NEW
  - tests/bot/test_modals_sanitization.py          # NEW
  - tests/bot/test_dm_offline_debouncer.py         # NEW
  - tests/bot/test_circuit_decorator.py            # NEW
  - tests/integration/test_circuit_open_warning.py # NEW
  - tests/integration/test_sanitizer_audit_persistence.py  # fixture update
  - tests/config/test_token_guard.py               # NEW
  - tests/config/__init__.py                       # NEW
  - tests/test_main_entrypoint.py                  # NEW
  - .planning/REQUIREMENTS.md
  - .planning/phases/07-safety-gap-closure/07-VERIFICATION.md  # NEW
tech-stack:
  added: []                                        # zero new pip dependencies
  patterns:
    - "Per-channel debounce with min-open-duration gate (DMOfflineDebouncer)"
    - "@catch_circuit_open decorator narrowed to MCPCircuitOpen — non-MCP exceptions propagate"
    - "Memoized sync→async audit bridge on the bot instance (replaces per-submit construction)"
    - "Single-source friendly-stderr helper (token_guard.require_token_or_exit) used by both entrypoints"
    - "Local EXIT_MISSING_TOKEN mirror in config.token_guard to honor 'config must not import subsystems' import-linter contract"
    - "config.py → config/ package migration (R100 rename — backward-compatible)"
key-files:
  created:
    - src/eldritch_dm/bot/circuit_decorator.py
    - src/eldritch_dm/bot/dm_offline_debouncer.py
    - src/eldritch_dm/config/token_guard.py
    - tests/safety/test_modal_sanitizer_corpus.py
    - tests/bot/test_modals_sanitization.py
    - tests/bot/test_dm_offline_debouncer.py
    - tests/bot/test_circuit_decorator.py
    - tests/integration/test_circuit_open_warning.py
    - tests/config/__init__.py
    - tests/config/test_token_guard.py
    - tests/test_main_entrypoint.py
    - .planning/phases/07-safety-gap-closure/07-VERIFICATION.md
  modified:
    - src/eldritch_dm/bot/modals.py
    - src/eldritch_dm/bot/bot.py
    - src/eldritch_dm/bot/cogs/exploration.py
    - src/eldritch_dm/bot/cogs/ingest.py
    - src/eldritch_dm/bot/dynamic_items.py
    - src/eldritch_dm/bot/__main__.py
    - src/eldritch_dm/mcp/health.py
    - run.py
    - tests/integration/test_sanitizer_audit_persistence.py
    - .planning/REQUIREMENTS.md
  renamed:
    - src/eldritch_dm/config.py → src/eldritch_dm/config/__init__.py
decisions:
  - "D-31 honored: OPS-02 ships warning only in v1.1 (no queue-replay of combat-critical button intents)."
  - "D-32-SAN honored: SAN-01 wires 3 modals; WeaponSelectModal intentionally untouched (regex allow-list already tighter than sanitizer for those fields)."
  - "D-33 honored: shared helper at eldritch_dm.config.token_guard prevents TD-1-1 copy-paste drift between run.py and bot/__main__.py."
  - "D-34 honored: DMOfflineDebouncer defaults to 30s per-channel debounce + 5s min-open gate."
  - "Inlined EXIT_MISSING_TOKEN=4 in config.token_guard rather than importing from eldritch_dm.bootstrap. Importing would pull persistence into the config layer and break the 'config and logging must not import subsystems' import-linter contract. A test asserts the two values stay equal (single-test contract gate)."
  - "OptionalFieldsModal sanitize_cb wired even though the modal has no live caller in v1.0/v1.1 — when Phase 8 (or v2) wires the 'Refine' button, the sanitization will already be in place. Inertness documented inline."
  - "Skipped STATE.md/ROADMAP.md updates and the phase-aggregation 07-SUMMARY.md per orchestrator instructions (Rule-3 deviation from PLAN Task 4; documented in VERIFICATION.md scope notes)."
metrics:
  duration_minutes: 90
  commits: 4
  net_new_tests: 68
  completed: 2026-05-24
---

# Phase 07 Plan 01 — Safety Gap Closure Summary

Three v1.0 audit deferrals (G-3 SAN-01, G-4 OPS-02, TD-1 `__main__` token-fix
parity) closed in three atomic implementation commits plus one docs/closure
commit, with shared infrastructure built once and reused across the three
sub-gaps so no diff fights another.

## What was built

### SAFETY-01 — Modal sanitization (G-3 closure)

`sanitize_player_input` now runs on free-text fields of three Discord modals
that previously bypassed it (the only sanitized modal was the
`DeclareActionModal` in exploration.py — the v1.0 audit flagged the gap as
"only Discord-mediated text that could carry ChatML smuggling is covered
on one of four code paths"). The new wiring:

- `CharacterReviewModal` (name + race), `CharacterEntryModal` (name + race),
  `OptionalFieldsModal` (background + skills + spells + alignment + subclass)
  each accept a `sanitize_cb` kwarg. Sanitization runs AFTER
  `interaction.response.defer(...)` in every callback (EDM001 preserved).
- `bot.sanitizer_audit_callback` is memoized once in `setup_hook` via
  `make_async_audit_callback(self.sanitizer_audit_repo)`. Every modal-
  construction site passes the same callable; pre-Phase-7 the exploration
  cog constructed one per submit, which is now refactored to the memoized
  path.
- `WeaponSelectModal` is intentionally NOT touched per D-32-SAN — its
  regex allow-list (`^[a-zA-Z0-9 '+]+$` for weapon, `^[a-z0-9-]+$` for
  target_id) is tighter than the sanitizer for those fields, and stacking
  a second strip would risk SAN-EXP-1 (mangling legitimate inputs like
  `Master's Greatsword`).

### SAFETY-02 — DM_OFFLINE warning surface (G-4 closure)

`MCPCircuitOpen` previously escaped from cog and DynamicItem callbacks
straight to discord.py's default unhandled-error handler — players saw
discord-internal UI noise instead of a meaningful "DM offline" message.
The new surface:

- `src/eldritch_dm/bot/circuit_decorator.py`: `@catch_circuit_open`
  wraps async Discord callbacks. On `MCPCircuitOpen` it consults
  `bot.dm_offline_debouncer.maybe_warn(channel_id, circuit)` and, if that
  returns True, dispatches `send_warning(interaction, WarningKind.DM_OFFLINE,
  failure_count=N)`. The decorator is narrow — non-`MCPCircuitOpen`
  exceptions (TypeError, ValueError, MCPTimeoutError, MCPNetworkError,
  MCPToolError) propagate unchanged so genuine bugs remain visible.
- `src/eldritch_dm/bot/dm_offline_debouncer.py`: `DMOfflineDebouncer` with
  per-channel keyed dict of last-warned timestamps. Two gates per D-34:
  1. **30s per-channel debounce** (OPS-02-1) — mashing buttons during an
     outage produces at most one ephemeral per channel per window.
  2. **5s minimum-open-duration** (OPS-02-2) — transient circuit blips
     (3-strike trip → 200ms recovery) do not surface a warning.
- `CircuitBreaker` now exposes monotonic `opened_at: float | None` (set on
  CLOSED→OPEN, cleared on close) and a public `failure_count` property.
  Wall-clock would be wrong for the 5s gate — NTP slew could falsify it.
- `@catch_circuit_open` applied to all 7 MCP-touching button callbacks in
  `dynamic_items.py` (ReadyButton, DeclareActionButton, EndTurnButton,
  AttackButton, DodgeButton, CastSpellButton, RiposteButton).
- Per D-31, queue-replay of combat-critical button intents is **deferred
  to v1.2** — v1.1 ships the warning only.

### SAFETY-03 — token_guard helper (TD-1 closure)

Pre-Phase-7, `run.py` had a 15-line inline block that emitted a friendly
stderr message + structured-log line + returned EXIT_MISSING_TOKEN=4 on
missing DISCORD_TOKEN. `python -m eldritch_dm.bot` had no equivalent — it
let `discord.errors.LoginFailure` traceback through. The new helper:

- `src/eldritch_dm/config/token_guard.py::require_token_or_exit(settings, log)`
  is the single source of truth for the friendly stderr text + log key.
  Returns the stripped token on success; returns None on missing/blank and
  emits both side effects so the caller can `return EXIT_MISSING_TOKEN`.
- `run.py`'s inline block is replaced by a 3-line call to the helper.
- `bot/__main__.py` calls the same helper BEFORE `bot.run(token)`, so the
  missing-token path now produces exit 4 + friendly stderr — identical
  behavior to `run.py`. The module docstring's `Exit codes` section adds
  the new code 4.
- `src/eldritch_dm/config.py` migrated to `src/eldritch_dm/config/__init__.py`
  (R100 rename — all existing `from eldritch_dm.config import Settings`
  imports continue to resolve unchanged). The new `token_guard.py` lives
  inside this package.

## Commits

| SHA | Subject |
|---|---|
| `cef3a3d` | `fix(audit-v1.1): SAN-01 close — sanitize_player_input in 3 modals (SAFETY-01 / G-3)` |
| `46e5f5e` | `fix(audit-v1.1): OPS-02 close — @catch_circuit_open + DMOfflineDebouncer (SAFETY-02 / G-4)` |
| `687413a` | `fix(audit-v1.1): TD-1 close — shared token_guard helper for run.py + __main__ (SAFETY-03)` |
| (this file) | `docs(07-safety-gap-closure): close plan 01 — REQUIREMENTS ticks + VERIFICATION + SUMMARY` |

## Test delta

| File | Tests | Status |
|---|---|---|
| `tests/safety/test_modal_sanitizer_corpus.py` | 27 (≥15 round-trip + 5 ChatML + 7 sanity) | NEW |
| `tests/bot/test_modals_sanitization.py` | 11 (4 per Review + 3 per Entry + 4 per Optional) | NEW |
| `tests/bot/test_dm_offline_debouncer.py` | 9 (min-open + debounce + isolation + knobs + force_warn) | NEW |
| `tests/bot/test_circuit_decorator.py` | 10 (success + 5 propagate cases + 3 MCPCircuitOpen branches + 1 missing-infra) | NEW |
| `tests/integration/test_circuit_open_warning.py` | 1 (end-to-end debounce + re-arm) | NEW |
| `tests/config/test_token_guard.py` | 8 (present + None + empty + whitespace + no-sys.exit + no-traceback + 2 contract gates) | NEW |
| `tests/test_main_entrypoint.py` | 2 (subprocess exit-4 + import-compat) | NEW |
| `tests/integration/test_sanitizer_audit_persistence.py` | fixture update only — same 2 tests | MOD |
| **Total** | **+68 new** | green |

Pre-Phase-7 suite: 864 (v1.0 baseline). Phase 6: +2 (cold-start E2E). Phase 7
ships +68 new = **934 net at green**. Full `uv run pytest -q` reports
946 passed (3 failed are pre-existing environmental issues — see VERIFICATION.md
section §1).

## Deviations from Plan

### [Rule 3 — Blocking issue] import-linter contract on `config → bootstrap`

- **Found during:** Task 3 verification — first attempt imported
  `EXIT_MISSING_TOKEN` from `eldritch_dm.bootstrap` per the plan body's
  recommended pattern.
- **Issue:** `eldritch_dm.bootstrap` re-exports `bootstrap` from
  `eldritch_dm.persistence.bootstrap`, so `config.token_guard → bootstrap`
  transitively pulls persistence into the config layer. The
  `config and logging must not import subsystems` import-linter contract
  breaks.
- **Fix:** Inlined `EXIT_MISSING_TOKEN = 4` as a module constant in
  `config/token_guard.py`, with a contract test
  (`tests/config/test_token_guard.py::test_exit_code_constant_matches_bootstrap_namespace`)
  asserting the local value equals
  `eldritch_dm.bootstrap.EXIT_MISSING_TOKEN`. If either is bumped the test
  fails, forcing the maintainer to bump both.
- **Outcome:** 7/7 import-linter contracts kept; contract test green.

### [Rule 3 — Scope clarification] Task 4 narrowed per orchestrator instructions

- **Issue:** The plan's Task 4 enumerates updates to `STATE.md`,
  `ROADMAP.md`, and a phase-aggregation `07-SUMMARY.md` in addition to
  REQUIREMENTS ticks + VERIFICATION + plan-level SUMMARY.
- **Fix:** The orchestrator (`/gsd-execute-phase` spawning this executor)
  explicitly instructed: "Do NOT update STATE.md or ROADMAP.md" — those are
  orchestrator-owned artifacts updated after the executor returns. The
  phase-aggregation `07-SUMMARY.md` is likewise a `/gsd-transition`
  artifact, not a single-plan deliverable. Task 4 therefore delivers
  exactly: REQUIREMENTS.md ticks + `07-VERIFICATION.md` + this
  `07-01-SUMMARY.md`. Documented in VERIFICATION.md "Scope notes".
- **Outcome:** All orchestrator success-criteria satisfied; STATE.md and
  ROADMAP.md left untouched for the orchestrator to update.

## Auth gates / blockers

None encountered. All work was local Python — no Discord login, no external
auth required.

## Self-Check: PASSED

- `src/eldritch_dm/bot/circuit_decorator.py` exists — `git ls-files | grep` confirms tracked.
- `src/eldritch_dm/bot/dm_offline_debouncer.py` exists — tracked.
- `src/eldritch_dm/config/token_guard.py` exists — tracked.
- `src/eldritch_dm/config/__init__.py` exists (R100 rename target) — `git log --follow` shows the rename.
- All 8 new test files exist and pass (see Test delta table).
- Commits `cef3a3d`, `46e5f5e`, `687413a` exist in `git log` on the
  per-agent branch — verified via `git log --oneline -5`.
- REQUIREMENTS.md shows `[x]` on SAFETY-01, SAFETY-02, SAFETY-03 — grep gate
  in VERIFICATION.md §9 returns 3.
- 7/7 import-linter contracts KEPT.
- Ruff clean on every touched source + test file.
- VERIFICATION.md exists at `.planning/phases/07-safety-gap-closure/07-VERIFICATION.md`.
