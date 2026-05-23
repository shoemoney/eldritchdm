---
status: resolved
trigger: "Both `python -m eldritch_dm.bootstrap` and `python run.py --check-only` call `Settings()` BEFORE checking what they're supposed to verify. DISCORD_TOKEN is required, so new self-hosters without .env get a raw pydantic.ValidationError traceback instead of a friendly diagnostic."
created: 2026-05-22T00:00:00Z
updated: 2026-05-22T16:50:00Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "bootstrap.preflight() at line 74 calls get_settings() → Settings() unconditionally. run.py main() at line 88 also calls Settings() unconditionally BEFORE checking --check-only at line 99. Since Settings.discord_token (config.py:36) is `str` with no default, missing token raises pydantic ValidationError before any preflight logic executes."
  confirming_evidence:
    - "Reproduced: `python -m eldritch_dm.bootstrap` exits 1 with pydantic_core ValidationError at bootstrap.py:74 → config.py:99 → pydantic_settings"
    - "Reproduced: `python run.py --check-only` exits 1 with same ValidationError at run.py:88"
    - "Confirmed in config.py:36: `discord_token: str` — no default, no Optional"
    - "Confirmed in run.py:85-88 comment explicitly says: 'We let that propagate' — current intent is broken"
  falsification_test: "If after fix we still see a raw pydantic ValidationError traceback in any of these 3 scenarios: (a) bootstrap missing token (b) run.py --check-only missing token (c) run.py (no flag) missing token — hypothesis was incomplete or fix is wrong."
  fix_rationale: "Make discord_token Optional[str] = None in Settings so the model validates with token absent. Validate token at the boundary that actually needs it: run.py main() before invoking EldritchBot.run(), and bot/__main__.py.main(). preflight() never references discord_token, so it gains nothing by enforcing it. Exit code 4 = ELDRITCH_MISSING_DISCORD_TOKEN for the friendly-error path."
  blind_spots: "Existing test `test_missing_discord_token_raises` in test_config.py asserts ValidationError — this test encodes the old contract and must be UPDATED, not preserved. Existing test_run_missing_discord_token_fails currently checks for 'discord_token' substring in output AND non-zero exit — the new structured stderr must still contain 'DISCORD_TOKEN' to satisfy this without test edits. Also: 23 unstaged Phase 4 files must remain untouched."

hypothesis: confirmed — both entrypoints instantiate Settings before preflight; discord_token has no default
test: applied fix to config.py + bootstrap.py + run.py + bot/__main__.py
expecting: bootstrap and --check-only succeed/give friendly preflight failures regardless of token; bare run.py gives exit 4 + friendly stderr (still mentions DISCORD_TOKEN)
next_action: apply edits, then run 3 smoke tests + full pytest

## Approach

1. **config.py**: change `discord_token: str` → `discord_token: str | None = None`; add docstring note
2. **bootstrap.py**: no code change needed (it never references discord_token); doc-string note added
3. **run.py**: parse argv FIRST; after Settings() succeeds, if not --check-only and discord_token is missing, emit friendly structured log + stderr and return EXIT_MISSING_TOKEN (4)
4. **bot/__main__.py**: same friendly check before bot.run()
5. **bootstrap.py**: add EXIT_MISSING_TOKEN = 4 constant; export
6. **tests**: update test_config.py to assert Optional behavior; update test_run_entrypoint.py Test 3 to assert exit 4 + friendly stderr (no traceback); add a Test 16 for `--check-only` without token (exit 0 path through preflight mocks).

## Symptoms

expected:
  - `python -m eldritch_dm.bootstrap` runs preflight (oMLX ping, dm20 tool count, DB schema), exits 0 on success, 1/2/3 on respective failures with friendly stderr
  - `python run.py --check-only` does the same
  - `python run.py` (no flag) with missing token: friendly structured error + exit 4 (next available code), no traceback
actual:
  - Both bootstrap and run.py --check-only fail with raw `pydantic_core.ValidationError` traceback (exit 1) when DISCORD_TOKEN is unset
errors:
  - pydantic.ValidationError for missing discord_token field
reproduction:
  - unset DISCORD_TOKEN; no .env file present
  - run: `python -m eldritch_dm.bootstrap` → ValidationError
  - run: `python run.py --check-only` → ValidationError
started: pre-existing; surfaced as Phase 5 ship blocker

## Eliminated

(none yet)

## Evidence

- timestamp: 2026-05-22
  checked: bootstrap.py:74 + run.py:88 + config.py:36
  found: get_settings() called before any preflight; discord_token is required `str`
  implication: ANY ValidationError on missing DISCORD_TOKEN triggers a traceback before useful code runs

- timestamp: 2026-05-22
  checked: smoke reproduction with unset DISCORD_TOKEN
  found: bootstrap exits 1 with `pydantic_core._pydantic_core.ValidationError`; run.py --check-only exits 1 same way
  implication: matches user-reported bug exactly

- timestamp: 2026-05-22
  checked: test_config.py:TestMissingToken
  found: existing test asserts `ValidationError` raised on missing token via direct `Settings(_env_file=None)`
  implication: this test encodes the OLD contract; must be rewritten to assert new contract (Settings instantiates with token=None; consumer-side validation fails the bot)

- timestamp: 2026-05-22
  checked: test_run_entrypoint.py:test_run_missing_discord_token_fails
  found: subprocess test only checks non-zero exit + 'discord_token' substring in combined output
  implication: friendly stderr that says 'DISCORD_TOKEN' satisfies the substring check; this test does NOT have to be loosened — but it should be tightened to forbid 'Traceback'

- timestamp: 2026-05-22
  checked: bot/__main__.py:33
  found: also calls Settings() at top of main(); same problem
  implication: must also add a friendly token check here, OR funnel the entry through run.py path

- timestamp: 2026-05-22
  checked: bootstrap.py preflight body
  found: references settings.eldritch_db_path, settings.omlx_endpoint, settings.omlx_model, settings.mcp_tools_url — none of which is discord_token
  implication: making discord_token Optional has zero functional impact on preflight

## Resolution

root_cause: |
  `Settings.discord_token: str` had no default (config.py:36). Both
  `bootstrap.preflight()` (via `get_settings()`) and `run.py main()`
  instantiated Settings unconditionally before any preflight-specific
  branching. With DISCORD_TOKEN unset and no `.env` file, pydantic-settings
  raised ValidationError at Settings construction — before any of the
  preflight checks ran, and visible to the operator as a raw traceback.

fix: |
  Three-part fix:
  1. `src/eldritch_dm/config.py`: discord_token → `str | None = None`.
     preflight never needs it; only the bot-launch path does.
  2. `src/eldritch_dm/bootstrap.py`: added `EXIT_MISSING_TOKEN = 4`
     constant (reserved for run.py / bot.__main__; preflight never
     returns it) and expanded docstring to document the token-free
     contract.
  3. `run.py`: after Settings() (which now succeeds without token),
     branch on --check-only FIRST (preflight is token-free). Only on
     the bot-launch path do we check `(settings.discord_token or
     "").strip()` and emit a friendly structured-log error + stderr
     pointing at .env.example, returning EXIT_MISSING_TOKEN (4) — no
     traceback ever reaches the operator.

verification: |
  Smoke tests (DISCORD_TOKEN unset, no .env):
    * python -m eldritch_dm.bootstrap        → exit 0 (oMLX/dm20 live)
    * python run.py --check-only             → exit 0
    * DRY_RUN=1 bash scripts/install-launchd.sh → exit 0
    * python run.py                          → exit 4 (friendly stderr)
  Pytest: 861 passed, 9 skipped in 9.49s (was 864 collected, now 870
  with +6 new D-26 tests).
  import-linter: 7/7 contracts KEPT.
  ruff check + ruff format: clean.

files_changed:
  - src/eldritch_dm/config.py
  - src/eldritch_dm/bootstrap.py
  - run.py
  - tests/test_config.py
  - tests/test_bootstrap_preflight.py
  - tests/test_run_entrypoint.py

commits:
  - 56f19ee fix(config): make discord_token Optional[str] = None (D-26)
  - c9fd52e feat(bootstrap): add EXIT_MISSING_TOKEN=4 constant (D-26)
  - e9bb392 fix(run): friendly missing-token error instead of pydantic traceback (D-26)
  - 8fc093f test(D-26): cover token-free preflight + friendly missing-token error
