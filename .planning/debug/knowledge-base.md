# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## preflight-requires-token — preflight commands raise pydantic ValidationError on missing DISCORD_TOKEN
- **Date:** 2026-05-22
- **Error patterns:** pydantic, ValidationError, discord_token, Field required, missing, preflight, bootstrap, check-only, Settings, get_settings
- **Root cause:** `Settings.discord_token: str` had no default. Both `bootstrap.preflight()` and `run.py main()` called `Settings()` unconditionally before any preflight branching, so unset DISCORD_TOKEN raised pydantic.ValidationError at Settings construction before any check-relevant code ran. Operator-facing failure was a raw Python traceback.
- **Fix:** Made `discord_token: str | None = None` in Settings (Optional); added `EXIT_MISSING_TOKEN = 4` to bootstrap.py; in run.py, parse argv first, branch on --check-only before the token check, and on the bot-launch path emit a friendly structured-log + stderr error (exit 4) instead of letting ValidationError escape.
- **Files changed:** src/eldritch_dm/config.py, src/eldritch_dm/bootstrap.py, run.py, tests/test_config.py, tests/test_bootstrap_preflight.py, tests/test_run_entrypoint.py
---

