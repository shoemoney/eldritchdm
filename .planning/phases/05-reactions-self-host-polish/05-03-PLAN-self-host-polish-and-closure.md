---
phase: 05-reactions-self-host-polish
plan: 03
type: execute
wave: 3
depends_on:
  - 05-01
  - 05-02
files_modified:
  - src/eldritch_dm/bootstrap.py
  - src/eldritch_dm/persistence/bootstrap.py
  - src/eldritch_dm/config.py
  - run.py
  - .env.example
  - pyproject.toml
  - README.md
  - docs/launchd.plist.example
  - docs/eldritch-dm.service.example
  - docs/dm20-troubleshooting.md
  - docs/character-ingest-formats.md
  - scripts/install-launchd.sh
  - scripts/uninstall-launchd.sh
  - .planning/REQUIREMENTS.md
  - .planning/ROADMAP.md
  - .planning/STATE.md
  - tests/test_bootstrap_preflight.py
  - tests/test_run_entrypoint.py
autonomous: false
requirements:
  - HOST-01
  - HOST-02
  - HOST-03
  - HOST-04
  - HOST-05
  - HOST-06
  - HOST-07
  - HOST-08
  - OPS-01
tags: [self-host, bootstrap, run-py, launchd, systemd, env-audit, readme, closure, milestone-v1]

must_haves:
  truths:
    - "A top-level `src/eldritch_dm/bootstrap.py` module exists; `python -m eldritch_dm.bootstrap` runs `ensure_schema(db_path)` (delegated to `persistence.bootstrap`) AND a 3-stage preflight (oMLX `/v1/models` ping, MCP tools list with dm20__ count, schema verify), returning exit codes 0/1/2/3 per RESEARCH Pattern 5."
    - "A top-level `run.py` at the project root exists; `python run.py` validates env via `Settings()`, runs preflight (unless `ELDRITCH_ALLOW_OFFLINE_START=1`), starts the bot, propagates exit codes to the OS supervisor, and treats SIGTERM as a clean shutdown signal."
    - "`.env.example` adds `MCP_RATE_LIMIT_MS=200` (already in `Settings` per Phase 4; was missing from the example per RESEARCH Q9) and resolves the orphan `OMLX_CACHE_STRATEGY` line (either by adding a `Settings` field that documents env passthrough, OR by removing the line and adding a comment explaining oMLX-only configuration)."
    - "`docs/launchd.plist.example` (label `com.shoemoney.eldritch-dm`) provides a working KeepAlive+RunAtLoad plist mirroring the user's `com.user.omlx` parity model (per RESEARCH Pattern 7), with explicit comment block stating DISCORD_TOKEN must come from `.env`, NOT the plist (RESEARCH anti-pattern callout)."
    - "`scripts/install-launchd.sh` and `scripts/uninstall-launchd.sh` provide one-command lifecycle (`launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.shoemoney.eldritch-dm.plist` + `bootout`)."
    - "`docs/eldritch-dm.service.example` provides a systemd user unit for Linux self-hosters (HOST-07 best-effort)."
    - "`docs/dm20-troubleshooting.md` and `docs/character-ingest-formats.md` cover the two most common self-hoster pain points named in CONTEXT D-18."
    - "README is expanded with: (1) 'First session in 10 minutes' literal slash-command walkthrough, (2) Troubleshooting section (oMLX down, dm20 not loaded, character upload failed), (3) launchd recipe + link to plist example, (4) systemd recipe (best-effort), (5) macOS-primary + Linux best-effort posture, (6) AGPL PyMuPDF note per RESEARCH Pitfall 8."
    - "`pyproject.toml` adds `[project.scripts] eldritch-dm = \"eldritch_dm.bot.__main__:main\"` (D-23) and `[project.urls]` for homepage/repository/issues (D-25); all deps still pinned (HOST-05)."
    - "Full test suite green: `python -m pytest -q` shows 0 failures, ~775+ tests passing (Phase 4's 728 + Plan 01's ~30 + Plan 02's ~17 + this plan's ~15)."
    - "All Phase 5 requirements ticked [x] in REQUIREMENTS.md: COMBAT-09, COMBAT-10, COMBAT-11, HOST-01..08, OPS-01."
    - "ROADMAP.md Phase 5 row is marked [x] and the Plans list reflects the three plans actually shipped."
    - "STATE.md cursor advances to Phase 5 complete; milestone-v1 status flagged for `/gsd:audit-milestone` follow-up."
    - "REQUIREMENTS.md COMBAT-09 wording is updated to correct the Phase 4 mistake (CONTEXT D-04 / RESEARCH finding #5): Battle Master Fighter RAW only; Swashbuckler removed from the requirement text; a code-level TODO references v2 YAML-configurable eligibility."
  artifacts:
    - path: "src/eldritch_dm/bootstrap.py"
      provides: "Top-level package entry: re-exports persistence.bootstrap.bootstrap as ensure_schema; defines preflight() and main() per RESEARCH Pattern 5"
      contains: "def preflight"
    - path: "run.py"
      provides: "Project-root entrypoint per RESEARCH Pattern 6; validates env, runs preflight, starts EldritchBot, handles SIGTERM"
      contains: "def main"
    - path: ".env.example"
      provides: "Audit-clean: adds MCP_RATE_LIMIT_MS, resolves OMLX_CACHE_STRATEGY orphan; consistent with Settings"
      contains: "MCP_RATE_LIMIT_MS"
    - path: "docs/launchd.plist.example"
      provides: "Working com.shoemoney.eldritch-dm plist with KeepAlive dict-form + ThrottleInterval=10 (RESEARCH Pattern 7)"
      contains: "com.shoemoney.eldritch-dm"
    - path: "docs/eldritch-dm.service.example"
      provides: "Linux systemd user unit (best-effort per HOST-07)"
      contains: "[Service]"
    - path: "README.md"
      provides: "Expanded self-host walkthrough, troubleshooting, OS supervision recipes, AGPL note, Phase 5 'Known Limitations' (RAW Battle Master only per D-C)"
      contains: "First session in 10 minutes"
    - path: ".planning/REQUIREMENTS.md"
      provides: "COMBAT-09 wording corrected (RAW Battle Master only); all Phase 5 requirements ticked [x]"
      contains: "[x] **COMBAT-11**"
    - path: ".planning/ROADMAP.md"
      provides: "Phase 5 marked [x]; Plans list shows the three plans actually shipped (replacing TBD)"
      contains: "[x] **Phase 5"
    - path: ".planning/STATE.md"
      provides: "Cursor advanced to Phase 5 complete; milestone-v1 audit-pending status"
      contains: "Phase 5"
  key_links:
    - from: "run.py"
      to: "src/eldritch_dm/bootstrap.py"
      via: "run.py imports `from eldritch_dm import bootstrap as preflight_mod` and calls `await preflight_mod.preflight()` before bot.run"
      pattern: "from eldritch_dm import bootstrap|preflight\\(\\)"
    - from: "src/eldritch_dm/bootstrap.py"
      to: "src/eldritch_dm/persistence/bootstrap.py"
      via: "Top-level bootstrap re-exports persistence.bootstrap.bootstrap as ensure_schema (RESEARCH Pitfall 7: README references python -m eldritch_dm.bootstrap; this plan makes that command work)"
      pattern: "from eldritch_dm.persistence.bootstrap import"
    - from: "docs/launchd.plist.example"
      to: "run.py"
      via: "plist's ProgramArguments invokes `/usr/bin/env python3 /Users/.../run.py`"
      pattern: "run\\.py"
    - from: "README.md"
      to: "docs/launchd.plist.example"
      via: "README HOST-08 section links the example plist and walkthroughs `launchctl bootstrap` install path"
      pattern: "launchd\\.plist\\.example"
---

<objective>
Close v1 of EldritchDM by shipping the self-host packaging (HOST-01..08) and milestone closure (OPS-01 sign-off, REQUIREMENTS/ROADMAP/STATE updates). This plan is the difference between "the code works on Jeremy's machine" and "a new user with oMLX + dm20 + a Discord token can run `python run.py` and be playing D&D 10 minutes later."

Purpose: Phase 5 is the final phase of milestone v1. After this plan: `/gsd:audit-milestone` verifies every v1 requirement is [x]; `/gsd:complete-milestone v1.0` archives.

This is the ONLY plan in Phase 5 marked `autonomous: false` — it contains the Phase 5 closure human-verify checkpoint (manual `python run.py` smoke + READY-prompt walkthrough) because launchd install + README readability are inherently human-verifiable artifacts.

Output:
- `src/eldritch_dm/bootstrap.py` (top-level preflight wrapper per RESEARCH Pattern 5)
- `run.py` (project-root entrypoint per RESEARCH Pattern 6)
- `.env.example` audit (add MCP_RATE_LIMIT_MS; resolve OMLX_CACHE_STRATEGY orphan)
- `pyproject.toml` `[project.scripts]` + `[project.urls]` per D-23/D-25
- 4 new docs files (launchd plist + systemd unit + 2 troubleshooting docs)
- 2 lifecycle scripts (`scripts/install-launchd.sh`, `scripts/uninstall-launchd.sh`)
- Expanded README with walkthrough + troubleshooting + supervision recipes
- 15+ new tests (preflight exit codes, run.py smoke, env audit)
- Closure paperwork: REQUIREMENTS [x], ROADMAP [x], STATE cursor advance
- Phase 5 SUMMARY + (optional) Phase 5 cross-plan synthesis SUMMARY
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md
@.planning/phases/05-reactions-self-host-polish/05-CONTEXT.md
@.planning/phases/05-reactions-self-host-polish/05-RESEARCH.md
@.planning/phases/05-reactions-self-host-polish/05-01-PLAN-riposte-and-monster-driver.md
@.planning/phases/05-reactions-self-host-polish/05-02-PLAN-sweeper-and-restart-survival.md
@src/eldritch_dm/config.py
@src/eldritch_dm/persistence/bootstrap.py
@src/eldritch_dm/bot/__main__.py
@src/eldritch_dm/bot/bot.py
@.env.example
@pyproject.toml
@README.md
@docs/CONFIGURATION.md

**Side findings baked in:**
- README and docs/CONFIGURATION.md reference `python -m eldritch_dm.bootstrap` — that module doesn't exist today (it's `eldritch_dm.persistence.bootstrap`). Create the top-level wrapper per RESEARCH Pitfall 7.
- `.env.example` is missing `MCP_RATE_LIMIT_MS` (RESEARCH Q9 + RESEARCH finding #10); `OMLX_CACHE_STRATEGY` is in `.env.example` but not consumed by Settings.
- launchd plist follows the user's existing `com.user.omlx` parity model with one improvement: dict-form `KeepAlive` with `SuccessfulExit=false` + `ThrottleInterval=10` (RESEARCH Pattern 7) so a bad DISCORD_TOKEN doesn't cause an infinite restart storm. README must document the tradeoff so operators can flip to `KeepAlive=true` if they want unconditional supervision.
- `ELDRITCH_ALLOW_OFFLINE_START=1` is the escape hatch when oMLX hasn't yet started (RESEARCH Pitfall 6 + Pattern 6); document in README + plist EnvironmentVariables.
- D-C correction: REQUIREMENTS.md COMBAT-09 currently says "Fighter/Battle Master, Rogue Swashbuckler" — must be amended to "Fighter/Battle Master (RAW)" with a note that v2 may add YAML-configurable eligibility for homebrew (Swashbuckler removal per RESEARCH finding #5).

<interfaces>
<!-- Already-existing contracts the executor must reuse. -->

From src/eldritch_dm/config.py (verified — relevant fields):
```python
class Settings(BaseSettings):
    discord_token: SecretStr                     # required
    omlx_endpoint: HttpUrl                        # default http://localhost:8765/v1
    omlx_model: str = "ShoeGPT"
    mcp_tools_url: HttpUrl                        # default http://localhost:8765/v1/mcp/tools
    mcp_execute_url: HttpUrl                      # default http://localhost:8765/v1/mcp/execute
    mcp_rate_limit_ms: PositiveInt = 200          # already wired
    riposte_ttl_seconds: PositiveInt = 8
    eldritch_db_path: Path = Path("./eldritch.sqlite3")
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    log_file: Path | None = None
```

From src/eldritch_dm/persistence/bootstrap.py:
```python
async def bootstrap(db_path: Path | str) -> None  # creates schema idempotently
```

From src/eldritch_dm/bot/__main__.py:
```python
def main() -> None  # existing entrypoint for `python -m eldritch_dm.bot`
```

User's existing `~/Library/LaunchAgents/com.user.omlx.plist` is the parity model — same Label naming convention, same KeepAlive/RunAtLoad pattern, same StandardOut/Err paths to log files.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: bootstrap.py wrapper + preflight + .env.example audit + pyproject scripts (RED→GREEN)</name>
  <files>
    src/eldritch_dm/bootstrap.py,
    src/eldritch_dm/config.py,
    .env.example,
    pyproject.toml,
    tests/test_bootstrap_preflight.py
  </files>
  <behavior>
    src/eldritch_dm/bootstrap.py (top-level wrapper per RESEARCH Pattern 5):
      - Test 1: `from eldritch_dm.bootstrap import bootstrap as ensure_schema` works (re-export from persistence.bootstrap).
      - Test 2: `from eldritch_dm.bootstrap import preflight, EXIT_OK, EXIT_OMLX_UNREACHABLE, EXIT_DM20_NOT_LOADED, EXIT_SCHEMA_FAIL` works (named constants 0, 1, 2, 3).
      - Test 3: `await preflight()` with all mocks green returns `EXIT_OK`. Mocks: httpx `GET {omlx_endpoint}/models` returns 200 with `{"data": [{"id": "ShoeGPT"}]}`; httpx `GET {mcp_tools_url}` returns 200 with a list including at least one dict whose `name` starts with `dm20__`.
      - Test 4: `await preflight()` with oMLX unreachable (httpx raises `httpx.ConnectError`) returns `EXIT_OMLX_UNREACHABLE`; prints user-friendly stderr message including the endpoint URL.
      - Test 5: `await preflight()` with oMLX up but `omlx_model` not in the models list logs WARNING but still returns `EXIT_OK` (model missing is a soft warning, not a fatal error — RESEARCH A5).
      - Test 6: `await preflight()` with MCP tools list returning zero `dm20__*` entries returns `EXIT_DM20_NOT_LOADED`.
      - Test 7: `await preflight()` with `ensure_schema` raising returns `EXIT_SCHEMA_FAIL` (and runs FIRST so schema failure short-circuits).
      - Test 8: `main()` invokes `asyncio.run(preflight())` and `sys.exit(code)` with the returned code. Verify by monkeypatching sys.exit.

    .env.example audit:
      - Test 9: `MCP_RATE_LIMIT_MS=200` line exists in `.env.example` with `🧪` tag + comment explaining "minimum interval between mutating MCP calls per channel (OPS-03; matches Settings default)".
      - Test 10: One of two outcomes for `OMLX_CACHE_STRATEGY` (executor's call, document in SUMMARY):
          (a) Line is REMOVED + a small comment block explains "oMLX cache strategy is configured on the oMLX server side, not via this .env"; OR
          (b) Line is kept BUT a new `omlx_cache_strategy: str | None = None` Settings field is added with a docstring saying "forwarded to oMLX process via env passthrough; not consumed by Python".
      - Test 11: After `unset MCP_RATE_LIMIT_MS && python -c "from eldritch_dm.config import Settings; print(Settings().mcp_rate_limit_ms)"`, prints `200` (default preserved).

    pyproject.toml:
      - Test 12: `[project.scripts]` table exists with `eldritch-dm = "eldritch_dm.bot.__main__:main"` (D-23). `pip install -e .` makes `eldritch-dm` available on PATH.
      - Test 13: `[project.urls]` table exists with `Homepage`, `Repository`, `Issues` keys (D-25). Values are placeholders (`https://github.com/shoemoney/EldritchDM` — executor confirms or substitutes per the actual repo URL; if unknown, use placeholder + a `# TODO` comment).
      - Test 14: All deps still pinned per HOST-05 — `python -c "import tomllib; deps = tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; assert all(any(op in d for op in ['==','>=','~=']) for d in deps), 'Unpinned dependency'"`.
  </behavior>
  <action>
    Create `src/eldritch_dm/bootstrap.py` per RESEARCH Pattern 5 verbatim. Module structure:
      - Re-export: `from eldritch_dm.persistence.bootstrap import bootstrap`  (so `from eldritch_dm.bootstrap import bootstrap` works for legacy README references).
      - Define `EXIT_OK = 0`, `EXIT_OMLX_UNREACHABLE = 1`, `EXIT_DM20_NOT_LOADED = 2`, `EXIT_SCHEMA_FAIL = 3` module-level constants.
      - `async def preflight() -> int`: runs the 3 stages in order — (a) `await bootstrap(settings.eldritch_db_path)`, (b) httpx GET `settings.omlx_endpoint/models`, (c) httpx GET `settings.mcp_tools_url`. Each stage returns its exit code on failure; structured-log + stderr-print on each failure as in RESEARCH Pattern 5.
      - `def main() -> None`: `configure_logging(level="INFO", fmt="console"); code = asyncio.run(preflight()); sys.exit(code)`.
      - Module-level `if __name__ == "__main__": main()` so `python -m eldritch_dm.bootstrap` works (D-27, RESEARCH Pitfall 7).
      - Use `httpx.AsyncClient` with `timeout=httpx.Timeout(5.0, connect=2.0)` per RESEARCH Pattern 5.

    Edit `.env.example`:
      - Add a `MCP_RATE_LIMIT_MS=200` line in the appropriate section (search for `MCP_EXECUTE_URL` and add adjacent — both are MCP-layer configs). Comment block above explaining the OPS-03 rate-limit context, tagged `🧪`.
      - Decide the `OMLX_CACHE_STRATEGY` fate. Lean: **remove the orphan line** (option a) and add a comment block: `# 🧪 oMLX cache strategy is configured on the oMLX server side (e.g. omlx serve --cache-strategy ...).` (Easier than maintaining a passthrough field in Settings; the env was never consumed by Python.) Document the decision in the SUMMARY.
      - If option (b) is chosen instead, add the corresponding `omlx_cache_strategy` field to `Settings` with default None.

    Edit `src/eldritch_dm/config.py` ONLY if option (b) is chosen for `OMLX_CACHE_STRATEGY`. Otherwise no changes.

    Edit `pyproject.toml`:
      - Add `[project.scripts]` table with `eldritch-dm = "eldritch_dm.bot.__main__:main"` (per D-23).
      - Add `[project.urls]` table with `Homepage`, `Repository`, `Issues` keys (per D-25). Use `https://github.com/shoemoney/EldritchDM` as placeholder if exact repo URL is unknown; add a `# TODO confirm repo URL` comment.
      - Confirm `requires-python = ">=3.11"` is still set.
      - Verify every dep in `dependencies` has a pin operator (`==`, `>=`, `~=`) — error out if any unpinned.

    Create `tests/test_bootstrap_preflight.py` with the 14 tests. Use respx (already in dev deps) for the httpx mocking; AsyncMock for `bootstrap()` failure injection.
  </action>
  <verify>
    <automated>uv run pytest tests/test_bootstrap_preflight.py -x -v && python -c "from eldritch_dm.bootstrap import preflight, EXIT_OK, EXIT_OMLX_UNREACHABLE, EXIT_DM20_NOT_LOADED, EXIT_SCHEMA_FAIL; assert (EXIT_OK, EXIT_OMLX_UNREACHABLE, EXIT_DM20_NOT_LOADED, EXIT_SCHEMA_FAIL) == (0,1,2,3)" && grep -q '^MCP_RATE_LIMIT_MS=' .env.example && grep -q 'eldritch-dm = "eldritch_dm.bot.__main__:main"' pyproject.toml</automated>
  </verify>
  <done>
    `python -m eldritch_dm.bootstrap` runs with proper exit codes; `.env.example` is audit-clean (MCP_RATE_LIMIT_MS added, OMLX_CACHE_STRATEGY resolved); `pyproject.toml` ships `[project.scripts]` + `[project.urls]`; 14 tests pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: run.py + launchd plist + systemd unit + install scripts + docs (RED→GREEN)</name>
  <files>
    run.py,
    docs/launchd.plist.example,
    docs/eldritch-dm.service.example,
    docs/dm20-troubleshooting.md,
    docs/character-ingest-formats.md,
    scripts/install-launchd.sh,
    scripts/uninstall-launchd.sh,
    tests/test_run_entrypoint.py
  </files>
  <behavior>
    run.py (project root, per RESEARCH Pattern 6):
      - Test 1: `python run.py --check-only` (new flag — runs preflight then exits, never starts the bot) returns exit code 0 when all mocks green; returns the preflight's exit code otherwise. Useful for CI smoke + launchd-debugging.
      - Test 2: `python run.py` with `ELDRITCH_ALLOW_OFFLINE_START=1` skips preflight and proceeds to bot construction (mocked bot.run for the test).
      - Test 3: `python run.py` with a missing required env var (e.g. DISCORD_TOKEN unset) raises `ValidationError` at `Settings()` construction and exits non-zero with a stderr line naming the missing var.
      - Test 4: SIGTERM handler is installed via `signal.signal(SIGTERM, ...)`; receiving SIGTERM raises KeyboardInterrupt in the test (verified by spawning a subprocess and sending it SIGTERM via `os.kill`).
      - Test 5: `run.py` imports work without side effects (no bot.run called) when the module is imported, only when `__main__` block fires. Verified via `python -c "import run; print('ok')"`.

    docs/launchd.plist.example (per RESEARCH Pattern 7):
      - Test 6: File exists; `plutil -lint docs/launchd.plist.example` exits 0 (verifies plist XML correctness).
      - Test 7: Label is `com.shoemoney.eldritch-dm`; ProgramArguments invokes `python3 /path/to/run.py`; WorkingDirectory is the project root; KeepAlive is dict-form with `SuccessfulExit=false`; ThrottleInterval=10; RunAtLoad=true.
      - Test 8: EnvironmentVariables sets `LOG_FORMAT=json` and includes a comment (XML comment) stating DISCORD_TOKEN must come from `.env`, not the plist.
      - Test 9: `ELDRITCH_ALLOW_OFFLINE_START=1` is included in EnvironmentVariables with a comment explaining the RESEARCH Pitfall 6 tradeoff (skips preflight; OPS-02 circuit breaker handles runtime oMLX loss).

    docs/eldritch-dm.service.example (HOST-07 best-effort):
      - Test 10: File exists; passes `systemd-analyze verify docs/eldritch-dm.service.example` IF systemd-analyze is available (skip test on macOS).
      - Test 11: `[Service] ExecStart=/usr/bin/env python3 /path/to/run.py`; `Restart=on-failure`; `RestartSec=10`; `Environment="LOG_FORMAT=json"`.

    scripts/install-launchd.sh:
      - Test 12: Script is `#!/usr/bin/env bash` with `set -euo pipefail`. Substitutes `$PWD` for `{PROJECT_DIR}` placeholders in the plist, copies to `~/Library/LaunchAgents/com.shoemoney.eldritch-dm.plist`, runs `launchctl bootstrap gui/$UID ...`. Idempotent (calls bootout first if already loaded). Test exits cleanly under dry-run mode (`DRY_RUN=1`).

    scripts/uninstall-launchd.sh:
      - Test 13: Script runs `launchctl bootout gui/$UID ~/Library/LaunchAgents/com.shoemoney.eldritch-dm.plist` and removes the plist file. Idempotent; exits 0 if already uninstalled.

    docs/dm20-troubleshooting.md and docs/character-ingest-formats.md:
      - Test 14: Both files exist and are non-empty (>500 bytes each). dm20-troubleshooting.md covers: "Is oMLX running?" (`curl :8765/v1/models`), "Is dm20 loaded?" (`curl :8765/v1/mcp/tools | jq 'length'`), "Bot logs say preflight_dm20_not_loaded — what now?" (point to `--mcp-config` in user's oMLX setup). character-ingest-formats.md covers: D&D Beyond URL format, supported PDF layouts, when manual-entry modal kicks in.
      - Test 15: Both .md files have YAML frontmatter with `title` + `audience: self-host`.
  </behavior>
  <action>
    Create `run.py` at project root per RESEARCH Pattern 6 verbatim. Add a `--check-only` flag (argparse) that runs preflight and exits without starting the bot — useful for CI + launchd debugging. The check-only path is the one used by Test 1.

    Create `docs/launchd.plist.example` per RESEARCH Pattern 7 verbatim. CRITICAL: Use `{PROJECT_DIR}` placeholders in `WorkingDirectory` and `ProgramArguments[2]`; the install script substitutes them with `$PWD`. Include the explanatory comment block per RESEARCH Pattern 7 (DISCORD_TOKEN from .env, KeepAlive tradeoff, ThrottleInterval rationale).

    Create `docs/eldritch-dm.service.example` (systemd user unit):
      ```ini
      [Unit]
      Description=EldritchDM — Discord D&D bot
      After=network-online.target
      Wants=network-online.target

      [Service]
      Type=simple
      WorkingDirectory={PROJECT_DIR}
      ExecStart=/usr/bin/env python3 {PROJECT_DIR}/run.py
      Restart=on-failure
      RestartSec=10
      StandardOutput=append:{PROJECT_DIR}/eldritch-dm.log
      StandardError=append:{PROJECT_DIR}/eldritch-dm.err
      Environment="LOG_FORMAT=json"
      Environment="ELDRITCH_ALLOW_OFFLINE_START=1"

      [Install]
      WantedBy=default.target
      ```

    Create `scripts/install-launchd.sh`:
      ```bash
      #!/usr/bin/env bash
      set -euo pipefail
      PLIST_LABEL="com.shoemoney.eldritch-dm"
      TARGET="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
      # Idempotent: bootout if already loaded
      launchctl bootout "gui/$UID/$PLIST_LABEL" 2>/dev/null || true
      # Substitute {PROJECT_DIR} -> $PWD, write to target
      sed "s|{PROJECT_DIR}|$PWD|g" docs/launchd.plist.example > "$TARGET"
      # Validate
      plutil -lint "$TARGET"
      # Load
      if [[ "${DRY_RUN:-0}" != "1" ]]; then
          launchctl bootstrap "gui/$UID" "$TARGET"
          launchctl kickstart -k "gui/$UID/$PLIST_LABEL"
          echo "Installed and started $PLIST_LABEL — check ~/eldritch-dm.log"
      else
          echo "[DRY_RUN] Would bootstrap $TARGET"
      fi
      ```

    Create `scripts/uninstall-launchd.sh`:
      ```bash
      #!/usr/bin/env bash
      set -euo pipefail
      PLIST_LABEL="com.shoemoney.eldritch-dm"
      TARGET="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
      launchctl bootout "gui/$UID/$PLIST_LABEL" 2>/dev/null || true
      [[ -f "$TARGET" ]] && rm "$TARGET" && echo "Uninstalled $PLIST_LABEL" || echo "Not installed."
      ```

    Make both scripts executable: `chmod +x scripts/install-launchd.sh scripts/uninstall-launchd.sh` (test asserts this).

    Create `docs/dm20-troubleshooting.md` with frontmatter + the diagnostic checklist (RESEARCH per CONTEXT D-18). Length target: 60-120 lines markdown. Cover the four common failures from RESEARCH (oMLX down, dm20 not loaded, bad model id, character upload failed).

    Create `docs/character-ingest-formats.md` with frontmatter + table of supported formats (D&D Beyond URL, PNG/JPG scan, PDF). Note OCR quality expectations on each. Reference Phase 3's INGEST-09 confidence-gated manual-entry fallback.

    Create `tests/test_run_entrypoint.py` with the 15 tests. Use subprocess for Test 5 (SIGTERM), respx + AsyncMock for preflight stubbing.
  </action>
  <verify>
    <automated>uv run pytest tests/test_run_entrypoint.py -x -v && plutil -lint docs/launchd.plist.example && bash -n scripts/install-launchd.sh && bash -n scripts/uninstall-launchd.sh && [ -x scripts/install-launchd.sh ] && DRY_RUN=1 bash scripts/install-launchd.sh</automated>
  </verify>
  <done>
    `run.py --check-only` runs preflight cleanly; `docs/launchd.plist.example` passes plutil -lint; both install/uninstall scripts are executable, idempotent, and dry-run-clean; systemd unit + troubleshooting docs exist with frontmatter; 15 tests pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: README expansion + Phase 5 closure paperwork + full test suite gate</name>
  <files>
    README.md,
    .planning/REQUIREMENTS.md,
    .planning/ROADMAP.md,
    .planning/STATE.md
  </files>
  <behavior>
    README expansion (per HOST-01, HOST-07, HOST-08, D-17, D-18):
      - Test 1: README contains a section `## First Session in 10 Minutes` with literal slash-command examples (`/start_game`, `/upload_character_url`, `/load_adventure CoS`, etc.).
      - Test 2: README contains a section `## Troubleshooting` covering the four scenarios from `docs/dm20-troubleshooting.md` with brief inline guidance + cross-links.
      - Test 3: README `## Self-Hosting` section explicitly states macOS-primary + Linux best-effort posture (HOST-07).
      - Test 4: README has a `## Running as a Service` section with two subsections (`### macOS (launchd)` linking install/uninstall scripts + docs/launchd.plist.example, and `### Linux (systemd, best-effort)` linking docs/eldritch-dm.service.example). HOST-08.
      - Test 5: README mentions PyMuPDF AGPL caveat (RESEARCH Pitfall 8) with one sentence on "swap to pypdf if forking commercially".
      - Test 6: README has a `## Known Limitations (v1)` subsection covering: RAW Battle Master Riposte only (per D-C), public Riposte button (per RESEARCH Q5 / Pattern 3), launchd plist DOES NOT contain DISCORD_TOKEN (per RESEARCH anti-pattern).
      - Test 7: README's quickstart explicitly mentions `python run.py` AND `python -m eldritch_dm.bootstrap` AND `eldritch-dm` (the `[project.scripts]` entry) as three equivalent ways to run.

    REQUIREMENTS.md closure:
      - Test 8: COMBAT-09 wording is updated. OLD: "Fighter/Battle Master, Rogue Swashbuckler". NEW: "Fighter/Battle Master (RAW; per Phase 5 D-C). Swashbuckler removed — not RAW; v2 may add YAML-configurable eligibility for homebrew."
      - Test 9: Every Phase 5 requirement is `[x]`: COMBAT-09, COMBAT-10, COMBAT-11, HOST-01, HOST-02, HOST-03, HOST-04, HOST-05, HOST-06, HOST-07, HOST-08, OPS-01.
      - Test 10: Other Phase 1-4 sanitizer requirements (SAN-01..06) — these were checked by other phases per their SUMMARYs; this plan does NOT touch them. Verify with grep that nothing pre-Phase-5 was accidentally toggled. (Defensive — this is a "do no harm" check.)

    ROADMAP.md closure:
      - Test 11: Phase 5 line is `- [x] **Phase 5: Reactions + Self-Host Polish** — ...`.
      - Test 12: Phase 5's Plans list reflects the three plans actually shipped (not "TBD"): `- [x] 05-01-PLAN-riposte-and-monster-driver.md`, `- [x] 05-02-PLAN-sweeper-and-restart-survival.md`, `- [x] 05-03-PLAN-self-host-polish-and-closure.md`.

    STATE.md closure:
      - Test 13: STATE.md shows current cursor at Phase 5 complete; lists v1 as "ready for /gsd:audit-milestone".
      - Test 14: STATE.md "completed phases" list includes all 5 phases with their commit refs.

    Full test suite gate (HOST-06):
      - Test 15: `uv run pytest -q` (full suite) shows 0 failures. Expected count: Phase 4's 728 + Plan 01's ~30 + Plan 02's ~17 + this plan's ~30 ≈ ~805 tests.
      - Test 16: `uv run ruff check src/ tests/` clean.
      - Test 17: `uv run lint-imports` clean.
  </behavior>
  <action>
    Edit README.md (expand existing structure; do NOT rewrite from scratch — preserve existing tone/voice):
      - Add `## First Session in 10 Minutes` section after the existing quickstart. Use literal slash-command examples; show what the bot replies; include screenshots or ascii-art if practical (skip if it bloats the section beyond ~80 lines).
      - Add `## Troubleshooting` section with the four scenarios from `docs/dm20-troubleshooting.md` summarized in 2-3 sentences each + a link to the docs file for the full diagnostic.
      - Add `## Self-Hosting` section: state macOS-primary + Linux best-effort posture clearly. Link to docs/ subdirectory contents.
      - Add `## Running as a Service` section with macOS (launchd) + Linux (systemd) subsections. macOS subsection: `./scripts/install-launchd.sh` + a one-liner explaining KeepAlive semantics + link to docs/launchd.plist.example. Linux subsection: link + warning "best-effort: mlx-lm is Apple Silicon only; Linux must use Ollama+MLX or a remote oMLX".
      - Add `## Known Limitations (v1)` section per Test 6.
      - Add `## License & Third-Party` (or amend existing license section) with the PyMuPDF AGPL note per Test 5.
      - Update the quickstart to show three equivalent run paths (`python run.py`, `python -m eldritch_dm.bot`, `eldritch-dm`).

    Edit `.planning/REQUIREMENTS.md`:
      - Update COMBAT-09's text per Test 8 (D-C correction).
      - Tick `[x]` for: COMBAT-09, COMBAT-10, COMBAT-11, HOST-01..08, OPS-01.
      - Update the Traceability table's "Mapped to phases" count.

    Edit `.planning/ROADMAP.md`:
      - Change Phase 5 line from `- [ ]` to `- [x]`.
      - Replace `**Plans**: TBD` with the actual three-plan list per Test 12.
      - Update the Phase 5 success criteria block: each numbered criterion now has a brief "✓ delivered by Plan NN" annotation cross-referencing the plan that delivered it (goal-backward audit trail).

    Edit `.planning/STATE.md`:
      - Advance cursor: `phase 5 complete`.
      - Append to "Recent Phase Completions" with the v1 milestone-pending note + "next: /gsd:audit-milestone v1.0".

    **CHECKPOINT** (see Task 4 below) — the human-verify gate for the README walkthrough + a manual `python run.py --check-only` + `DRY_RUN=1 bash scripts/install-launchd.sh` smoke happens AFTER Task 3 closure.

    Run the full test suite one final time. Address any regressions immediately (Rule 1 — auto-fix bugs found during gate runs; document them in the SUMMARY as Deviations).
  </action>
  <verify>
    <automated>uv run pytest -q && uv run ruff check src/ tests/ && uv run lint-imports && grep -c '^- \[x\] \*\*COMBAT-09' .planning/REQUIREMENTS.md | tee /tmp/g1.txt && grep -c '^- \[x\] \*\*COMBAT-10' .planning/REQUIREMENTS.md | tee /tmp/g2.txt && grep -c '^- \[x\] \*\*COMBAT-11' .planning/REQUIREMENTS.md | tee /tmp/g3.txt && grep -c '^- \[x\] \*\*OPS-01' .planning/REQUIREMENTS.md | tee /tmp/g4.txt && grep -c '^- \[x\] \*\*HOST-0[1-8]' .planning/REQUIREMENTS.md | tee /tmp/g5.txt && [ "$(cat /tmp/g1.txt)" = "1" ] && [ "$(cat /tmp/g2.txt)" = "1" ] && [ "$(cat /tmp/g3.txt)" = "1" ] && [ "$(cat /tmp/g4.txt)" = "1" ] && [ "$(cat /tmp/g5.txt)" = "8" ]</automated>
  </verify>
  <done>
    README has the full walkthrough + troubleshooting + service supervision recipes + AGPL note + known limitations; REQUIREMENTS.md COMBAT-09 wording fixed and all Phase 5 reqs ticked; ROADMAP Phase 5 [x]; STATE cursor advanced; full test suite green (~805 tests); ruff + lint-imports clean.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4: Phase 5 closure human-verify — README walkthrough + run.py smoke + launchd dry-run</name>
  <what-built>
    - Top-level `src/eldritch_dm/bootstrap.py` (oMLX + dm20 preflight)
    - `run.py` project-root entrypoint with --check-only flag
    - `.env.example` audited (MCP_RATE_LIMIT_MS added, OMLX_CACHE_STRATEGY resolved)
    - `docs/launchd.plist.example` (com.shoemoney.eldritch-dm) + install/uninstall scripts
    - `docs/eldritch-dm.service.example` (Linux best-effort)
    - `docs/dm20-troubleshooting.md` + `docs/character-ingest-formats.md`
    - README expanded with walkthrough, troubleshooting, service supervision, Known Limitations, AGPL note
    - All Phase 5 requirements ticked in REQUIREMENTS.md (COMBAT-09 wording corrected per D-C)
    - ROADMAP Phase 5 [x] with three-plan reflection
    - STATE cursor advanced to "Phase 5 complete; ready for /gsd:audit-milestone v1.0"
  </what-built>
  <how-to-verify>
    1. Read README's `## First Session in 10 Minutes` section top-to-bottom. Does it actually convince a new self-hoster they could complete a session in 10 minutes? (Subjective but matters — flag any "this would never work in practice" steps.)

    2. Run `python run.py --check-only`. Expected output: structured-log lines for preflight stages, exit code 0 (if your oMLX + dm20 are currently running) or one of 1/2/3 (with a stderr message naming what's wrong).

    3. Run `python -m eldritch_dm.bootstrap`. Same expected behavior as #2 (this is the canonical README-referenced command).

    4. Run `DRY_RUN=1 bash scripts/install-launchd.sh`. Expected: prints `[DRY_RUN] Would bootstrap /Users/.../Library/LaunchAgents/com.shoemoney.eldritch-dm.plist`; verifies plist validity via plutil -lint; does NOT actually install. Exit code 0.

    5. (Optional, only if you want to test the real launchd integration) Run `bash scripts/install-launchd.sh` for real. Then `launchctl list | grep eldritch` should show the job. Run `bash scripts/uninstall-launchd.sh` to clean up.

    6. Read README's `## Known Limitations (v1)` section. Verify:
       - Battle Master Fighter only is called out clearly (per D-C).
       - Public Riposte button (vs ephemeral) tradeoff is documented.
       - DISCORD_TOKEN-not-in-plist warning is visible.

    7. Read README's `## Running as a Service` section. Verify both launchd + systemd recipes are present and link to their respective example files.

    8. Skim REQUIREMENTS.md to confirm all v1 items show `[x]` (excluding v2 sections). Type-check by running: `grep -c '^- \[ \] \*\*' .planning/REQUIREMENTS.md` — should be 0 above the `## v2 Requirements` header.

    9. Skim ROADMAP.md to confirm all five phases show `[x]`.

    10. (Optional) Run `uv run pytest -q` one more time on a fresh terminal. Confirm 0 failures + the test count matches the SUMMARY's claim (~805 tests).

    Expected outcome:
    - All 10 checks pass → reply "approved" or "complete v1"; orchestrator proceeds with closure.
    - Any check fails → describe what's wrong; executor patches and re-checkpoints.
  </how-to-verify>
  <resume-signal>Type "approved" to advance, or describe issues to address.</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Self-hoster's `.env` file ↔ run.py | Trusted (operator-controlled filesystem); Settings validates required fields and fails fast on missing token. |
| run.py ↔ launchd/systemd (OS supervisor) | Exit-code contract; SIGTERM = clean shutdown. |
| Bootstrap preflight ↔ oMLX HTTP | Untrusted in the sense that oMLX may return malformed JSON; httpx + try/except handles. |
| launchd plist (world-readable) ↔ secrets | DISCORD_TOKEN MUST NOT live in the plist (T-05-16). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-16 | Information Disclosure | launchd plist world-readable + DISCORD_TOKEN | mitigate | DISCORD_TOKEN sourced from `.env` (mode 0600 recommended by README); plist EnvironmentVariables contain ONLY non-secret operational config (LOG_FORMAT, ELDRITCH_ALLOW_OFFLINE_START); README + plist-comment-block both warn. |
| T-05-17 | DoS | Bad DISCORD_TOKEN → infinite restart loop | mitigate | KeepAlive dict-form with `SuccessfulExit=false` + ThrottleInterval=10 (RESEARCH Pattern 7); operator sees the crash logs accumulate slowly enough to debug. |
| T-05-18 | Tampering | preflight reaches oMLX over plaintext localhost HTTP | accept | localhost-only HTTP is the standard oMLX pattern; not a real attack surface for a local-first bot. |
| T-05-19 | Repudiation | "the bot crashed and lost state" | mitigate | Phase 1 WAL SQLite + Phase 2 persistent_views + Phase 5 Plan 02 sweeper survive arbitrary crashes; OPS-01 drill proves it. README documents the resume guarantees. |
| T-05-20 | Elevation of Privilege | install-launchd.sh asks for sudo | accept | LaunchAgents are user-scoped (NOT system-scoped); script does NOT use sudo; `launchctl bootstrap gui/$UID` is per-user. README clarifies this. |
| T-05-SC | Supply chain | No new third-party packages | accept | Plan 03 introduces zero new pip dependencies; `httpx`/`pydantic-settings`/`structlog` are already pinned in earlier phases. |
</threat_model>

<verification>
**Plan-level checks (in addition to per-task `<verify>`):**

1. `uv run pytest -q` — full suite green, ~805 tests passing, 0 failed.
2. `uv run ruff check src/ tests/ run.py` — clean.
3. `uv run lint-imports` — clean.
4. `plutil -lint docs/launchd.plist.example` — exits 0.
5. `bash -n scripts/install-launchd.sh scripts/uninstall-launchd.sh` — syntax-clean.
6. `[ -x scripts/install-launchd.sh ] && [ -x scripts/uninstall-launchd.sh ]` — both executable.
7. `python -c "import run; print('importable')"` — succeeds (run.py is importable as a module without running main).
8. `pip install -e . && which eldritch-dm` — the project.scripts entry installs the CLI.
9. `grep -c '^- \[ \] \*\*' .planning/REQUIREMENTS.md | awk '$1 == 0 || $1 == "0"'` — verifies all v1 reqs are [x] (the v2 section starts later; grep should return zero `[ ]` lines among Phase 1-5 requirements). Use line-range bounded grep to be safe (the executor's tooling choice).
10. README contains the required sections (Test 1-7 in Task 3) — visual check.

**Risks:**
- **README walkthrough subjectivity:** The "in 10 minutes" claim depends on the user already having oMLX + dm20 configured. README must state this prerequisite clearly. Plan 03's checkpoint verifies the walkthrough is plausible.
- **Plist path substitution:** install-launchd.sh substitutes `{PROJECT_DIR}` with `$PWD`. If a self-hoster moves the project directory after install, the plist breaks. README documents the re-install step.
- **systemd unit untested by the planner's reference rig (macOS-only):** The systemd unit is HOST-07 best-effort; we cannot fully validate it without a Linux test machine. Document this caveat in README + the unit file itself.
- **Pyproject.toml `[project.urls]` placeholder:** If the repo URL isn't known at planning time, leave a `# TODO confirm repo URL` comment; the executor decides whether to substitute the actual URL during execution or defer.
- **OMLX_CACHE_STRATEGY decision (Task 1):** Two valid options; SUMMARY documents which one was chosen and why.
- **Full test count drift:** Plan 01 estimated ~30, Plan 02 estimated ~17, this plan ~30. If actual counts diverge significantly, the SUMMARY documents and the ROADMAP success criterion still passes ("full test suite green" is the spec, not a specific count).
- **REQUIREMENTS.md COMBAT-09 wording change is a `docs` change to a tracking file** — but it changes the semantics of what v1 ships. The SUMMARY's Deviations section must document this prominently so `/gsd:audit-milestone` doesn't flag it as inconsistent.

**Open question (resolved here):**
- `OMLX_CACHE_STRATEGY`: REMOVE the orphan line (Task 1 lean) vs ADD the Settings passthrough. SUMMARY documents the choice.
- Whether `run.py` should accept a `--no-preflight` flag in addition to `ELDRITCH_ALLOW_OFFLINE_START=1`. Lean: yes, both work, `--no-preflight` for ad-hoc dev runs and the env var for launchd-managed prod. Document.
</verification>

<success_criteria>
- `src/eldritch_dm/bootstrap.py` exists with `preflight()` returning 0/1/2/3 per RESEARCH Pattern 5; `python -m eldritch_dm.bootstrap` works.
- `run.py` exists at project root; `python run.py --check-only` runs preflight only; `python run.py` validates env, runs preflight (unless ELDRITCH_ALLOW_OFFLINE_START=1), starts the bot, handles SIGTERM.
- `.env.example` is audit-clean (MCP_RATE_LIMIT_MS added; OMLX_CACHE_STRATEGY resolved).
- `docs/launchd.plist.example` passes plutil -lint; install/uninstall scripts work dry-run.
- `docs/eldritch-dm.service.example` provides Linux systemd unit (HOST-07 best-effort).
- `docs/dm20-troubleshooting.md` + `docs/character-ingest-formats.md` cover the top self-hoster pain points.
- README has First Session in 10 Minutes + Troubleshooting + Self-Hosting + Running as a Service + Known Limitations + AGPL note.
- `pyproject.toml` ships `[project.scripts] eldritch-dm` + `[project.urls]`; all deps pinned.
- REQUIREMENTS.md: COMBAT-09 wording corrected per D-C; COMBAT-09/10/11, HOST-01..08, OPS-01 all [x].
- ROADMAP.md: Phase 5 [x]; Plans list shows three actual plans; success criteria annotated with delivering-plan refs.
- STATE.md: cursor advanced to Phase 5 complete; v1 ready for /gsd:audit-milestone.
- Full test suite: `uv run pytest -q` returns 0 failures, ~805 tests passing; ruff + lint-imports clean.
- Human-verify checkpoint (Task 4) is approved.
</success_criteria>

<output>
On completion (after Task 4 approval), create `.planning/phases/05-reactions-self-host-polish/05-03-SUMMARY.md` AND `.planning/phases/05-reactions-self-host-polish/05-SUMMARY.md` (cross-plan synthesis) per the standard templates.

05-03-SUMMARY.md captures Plan 03 specifics:
- files created/modified counts
- decisions (OMLX_CACHE_STRATEGY removal vs passthrough; --no-preflight CLI flag yes/no)
- test count delta (~30 new across preflight + run.py + closure)
- README diff size

05-SUMMARY.md captures the whole-Phase synthesis:
- v1 ships with: timed Riposte (RAW Battle Master Fighter), restart-safe sweeper, full self-host runbook
- v2 deferral list (Swashbuckler eligibility via YAML, smart MonsterDriver targeting, REACT-01..03 other reactions, EXUI/ADV families)
- The OPS-01 resume drill is the marketing-grade proof: kill mid-combat, restart, button still works
- Next action for the operator: `/gsd:audit-milestone v1.0` then `/gsd:complete-milestone v1.0`
- Lessons learned (especially: Phase 4 mis-placed the riposte seam — caught only because Phase 5 RESEARCH re-walked the AttackButton callback; lesson: planner should grep all stubs left by prior phases as part of phase-prep)
</output>
