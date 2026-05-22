---
phase: 05-reactions-self-host-polish
plan: 03
subsystem: self-host
tags: [self-host, bootstrap, run-py, launchd, systemd, env-audit, readme, closure, milestone-v1]

# Dependency graph
requires:
  - phase: 05-reactions-self-host-polish
    plan: 02
    provides: bot.setup_hook with sweeper started AFTER rehydration; OPS-04 chain stops sweeper FIRST; 826-test baseline
  - phase: 05-reactions-self-host-polish
    plan: 01
    provides: Plan 02 dep transitively; COMBAT-09/10 functionally satisfied
  - phase: 01-mcp-client-local-state
    provides: persistence.bootstrap.bootstrap (async schema applier — re-exported as ensure_schema by this plan)
provides:
  - src/eldritch_dm/bootstrap.py — top-level 3-stage preflight (schema → oMLX /v1/models → MCP dm20__* tools list) with exit codes 0/1/2/3 (RESEARCH Pattern 5)
  - run.py — project-root entrypoint with --check-only / --no-preflight CLI flags, ELDRITCH_ALLOW_OFFLINE_START=1 env escape hatch, and SIGTERM→KeyboardInterrupt handler (RESEARCH Pattern 6)
  - docs/launchd.plist.example — com.shoemoney.eldritch-dm with dict-form KeepAlive + ThrottleInterval=10 (RESEARCH Pattern 7); DISCORD_TOKEN anti-pattern comment block
  - docs/eldritch-dm.service.example — systemd user unit (HOST-07 best-effort)
  - scripts/install-launchd.sh + scripts/uninstall-launchd.sh — idempotent lifecycle; DRY_RUN=1 renders to tempfile + plutil-lints without touching ~/Library/LaunchAgents
  - docs/dm20-troubleshooting.md — covers the four common self-host failure modes (oMLX down, dm20 not loaded, wrong model, schema bootstrap fail) keyed off preflight exit codes
  - docs/character-ingest-formats.md — supported formats table + INGEST-09 confidence gate + PyMuPDF AGPL note
  - .env.example MCP_RATE_LIMIT_MS=200 added (RESEARCH Q9 — was missing from example despite being in Settings); OMLX_CACHE_STRATEGY orphan REMOVED with explanatory comment (option a per Plan)
  - pyproject.toml [project.scripts] eldritch-dm = "eldritch_dm.bot.__main__:main" (D-23); [project.urls] Homepage/Repository/Issues (D-25)
  - README expansion: First Session in 10 Minutes, Self-Hosting, Running as a Service, Known Limitations (Battle Master RAW only per D-C, public Riposte button, DISCORD_TOKEN-NOT-in-plist), License & Third-Party (PyMuPDF AGPL note)
  - REQUIREMENTS.md COMBAT-09 wording corrected per D-C; all Phase 5 reqs [x]
  - ROADMAP.md Phase 5 [x]; success criteria annotated with delivering-plan refs
  - STATE.md cursor advanced to "Phase 5 complete; ready for /gsd:audit-milestone v1.0"
affects: [Phase 5 SUMMARY synthesis, /gsd:audit-milestone v1.0 input]

# Tech tracking
tech-stack:
  added: []  # zero new pip dependencies
  patterns:
    - "Re-export pattern: `from eldritch_dm.persistence.bootstrap import bootstrap` at the top-level module so legacy `from eldritch_dm.bootstrap import bootstrap` keeps working"
    - "Preflight stage ordering: schema FIRST (short-circuits before any network I/O), then oMLX, then MCP"
    - "Soft warning vs fatal error: missing OMLX_MODEL → log.warning + stderr nudge but EXIT_OK; unreachable oMLX → EXIT_OMLX_UNREACHABLE (operator-controlled distinction per RESEARCH A5)"
    - "Argparse-driven entrypoint with two skip-preflight hatches: --no-preflight CLI flag for ad-hoc dev runs, ELDRITCH_ALLOW_OFFLINE_START=1 env var for launchd-managed prod (RESEARCH Pattern 6 / D-15)"
    - "SIGTERM handler that raises KeyboardInterrupt — reuses discord.py's existing KeyboardInterrupt branch instead of forking the shutdown chain"
    - "{PROJECT_DIR} placeholder substitution in plist + systemd unit; install scripts use sed against `$PWD`"
    - "DRY_RUN tempfile rendering — install script writes to mktemp + plutil-lints there; production write only when DRY_RUN unset (safer for CI smoke)"
    - "dict-form KeepAlive with SuccessfulExit=false + ThrottleInterval=10 — deviates from upstream com.user.omlx's plain KeepAlive=true to avoid bad-token restart-storm; README documents the tradeoff for operators who want the upstream behavior"

key-files:
  created:
    - src/eldritch_dm/bootstrap.py
    - run.py
    - docs/launchd.plist.example
    - docs/eldritch-dm.service.example
    - docs/dm20-troubleshooting.md
    - docs/character-ingest-formats.md
    - scripts/install-launchd.sh
    - scripts/uninstall-launchd.sh
    - tests/test_bootstrap_preflight.py
    - tests/test_run_entrypoint.py
  modified:
    - .env.example
    - pyproject.toml
    - README.md
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
    - .planning/STATE.md

# Key decisions
decisions:
  - D-A: OMLX_CACHE_STRATEGY orphan resolved via REMOVAL (option a per Plan Task 1 alternatives) rather than adding a passthrough Settings field. Rationale: simpler — no orphan field to maintain; explanatory comment in .env.example tells operators where the setting actually lives (oMLX server side via `omlx serve --cache-strategy ...`). Cost: nil; nothing else in EldritchDM consumed this env var.
  - D-B: run.py exposes BOTH --no-preflight CLI flag AND ELDRITCH_ALLOW_OFFLINE_START=1 env var (verification "Open question" resolved YES to both). --no-preflight is for ad-hoc dev runs; the env var is for launchd-managed prod where the cold-start race with oMLX matters. Documented in run.py docstring and README.
  - D-C: install-launchd.sh DRY_RUN=1 renders the plist to a tempfile (mktemp + plutil-lint there) instead of writing to ~/Library/LaunchAgents/. Safer — no stale files left behind on aborted runs; CI smoke is hermetic. Production path (DRY_RUN unset) still writes to the LaunchAgents dir.
  - D-D: Preflight stage ordering — schema FIRST (so permission/disk failures short-circuit before any network I/O), then oMLX, then MCP. Reasoning: operator wants to see the root cause; if the schema can't apply, oMLX status is irrelevant.
  - D-E: Missing OMLX_MODEL is a soft WARNING, not EXIT_OMLX_UNREACHABLE (RESEARCH A5). Operators may load a different model intentionally; the gate should not block them. Preflight emits both `log.warning("preflight_omlx_model_missing")` and a user-friendly stderr line, then continues.
  - D-F: Launchd plist uses dict-form KeepAlive with SuccessfulExit=false + ThrottleInterval=10 (RESEARCH Pattern 7) instead of upstream com.user.omlx's plain KeepAlive=true. Trades unconditional supervision for "don't infinite-loop on a bad DISCORD_TOKEN". README documents the tradeoff so operators can flip to `<true/>` if they prefer the parity model.
  - D-G: pyproject.toml `[project.scripts]` uses `eldritch_dm.bot.__main__:main` (the existing entrypoint) rather than introducing a new `eldritch_dm.cli:main` module. Reuses the proven main(); zero new code surface.

# Metrics
metrics:
  duration_minutes: 45  # commit-to-commit from start of execution
  tasks: 3  # T1 (bootstrap+env+pyproject), T2 (run.py+plist+systemd+scripts+docs), T3 (README+REQ+ROADMAP+STATE)
  files_created: 10
  files_modified: 6
  tests_added: 29  # 14 (bootstrap preflight) + 15 (run.py + plist + systemd + scripts + docs)
  tests_total: 855  # was 826 at start of Plan 03
  completed: "2026-05-22"
---

# Phase 5 Plan 03: Self-Host Polish + Phase 5 Closure Summary

Closes v1 of EldritchDM by shipping the self-host packaging (HOST-01..08), the milestone closure paperwork (REQUIREMENTS / ROADMAP / STATE all updated), and the user-facing surface (README walkthrough + troubleshooting + service-supervision recipes) that turns "the code works on Jeremy's machine" into "a new user with oMLX + dm20 + a Discord token can run `python run.py` and be playing D&D 10 minutes later."

## What Shipped

### Bootstrap & Preflight (`src/eldritch_dm/bootstrap.py`)

- Top-level `eldritch_dm.bootstrap` module that wraps `persistence.bootstrap.bootstrap` (re-exported so `from eldritch_dm.bootstrap import bootstrap` keeps working for any legacy callers) and adds a 3-stage preflight per RESEARCH Pattern 5:
  1. **Schema** — `await bootstrap(settings.eldritch_db_path)` — short-circuits on permission/disk failures.
  2. **oMLX** — `httpx.GET {omlx_endpoint}/models` with `Timeout(5.0, connect=2.0)` — fails fast on connection refused or HTTP errors.
  3. **MCP** — `httpx.GET {mcp_tools_url}` — counts `dm20__*`-prefixed entries; zero → fatal `EXIT_DM20_NOT_LOADED`.
- Named exit-code constants (`EXIT_OK=0`, `EXIT_OMLX_UNREACHABLE=1`, `EXIT_DM20_NOT_LOADED=2`, `EXIT_SCHEMA_FAIL=3`) usable by tests and by `run.py`.
- `main()` configures structlog console output, runs `asyncio.run(preflight())`, and `sys.exit(code)` — so `python -m eldritch_dm.bootstrap` is the canonical README-referenced command (closes RESEARCH Pitfall 7).

### Project-Root Entrypoint (`run.py`)

- argparse-driven main with `--check-only` (preflight + exit; CI/launchd smoke) and `--no-preflight` (skip gate; dev convenience).
- Honors `ELDRITCH_ALLOW_OFFLINE_START=1` for production cold-start where oMLX may not yet be up — the OPS-02 circuit breaker takes over for runtime oMLX loss.
- Installs a SIGTERM→KeyboardInterrupt handler so launchd/systemd's SIGTERM triggers the OPS-04 shutdown chain cleanly (riposte sweeper stop → coalescer flush → DB writer queue drain → `bot.close`).
- Inline imports so `python run.py --help` doesn't pay full startup cost.
- Three equivalent entrypoints now ship: `python run.py`, `python -m eldritch_dm.bot`, and `eldritch-dm` (the `[project.scripts]` CLI). README documents all three.

### .env.example Audit + pyproject Scripts

- **Added** `MCP_RATE_LIMIT_MS=200` line (was missing per RESEARCH Q9 even though the Settings field has been live since Phase 1) with a 🧪 tag and a comment block referencing OPS-03 and matching the Settings default.
- **Removed** the orphan `# OMLX_CACHE_STRATEGY=` line (D-A) with an explanatory comment block: "oMLX cache strategy is configured on the oMLX server side, not via this .env." No Settings field was ever consumed; clean removal beats maintaining a passthrough.
- `pyproject.toml` adds `[project.scripts] eldritch-dm = "eldritch_dm.bot.__main__:main"` (D-23) and `[project.urls]` with Homepage/Repository/Issues (D-25). Confirmed `pip install -e .` builds and `which eldritch-dm` resolves.

### Launchd + Systemd + Scripts

- `docs/launchd.plist.example` — Label `com.shoemoney.eldritch-dm`, ProgramArguments invokes `/usr/bin/env python3 {PROJECT_DIR}/run.py`, dict-form `KeepAlive` (`SuccessfulExit=false`, `Crashed=true`) + `ThrottleInterval=10` per RESEARCH Pattern 7 (D-F). `EnvironmentVariables` deliberately contains zero secrets — only `PATH`, `LOG_FORMAT=json`, and `ELDRITCH_ALLOW_OFFLINE_START=1`; a top-of-file XML comment block warns against putting `DISCORD_TOKEN` in the plist (anti-pattern callout).
- `docs/eldritch-dm.service.example` — Linux systemd user unit (HOST-07 best-effort). `Restart=on-failure` + `RestartSec=10`; same env-var posture as the plist.
- `scripts/install-launchd.sh` — idempotent (`launchctl bootout` first), substitutes `{PROJECT_DIR}` with `$PWD`, validates with `plutil -lint`, bootstraps + kickstarts. **DRY_RUN=1 path** (D-C) renders to a tempfile and lints there — no writes to `~/Library/LaunchAgents/`.
- `scripts/uninstall-launchd.sh` — idempotent bootout + plist removal.
- Both scripts: `#!/usr/bin/env bash` + `set -euo pipefail` + executable (`chmod +x`).

### Self-Host Docs

- `docs/dm20-troubleshooting.md` (with YAML frontmatter `title` + `audience: self-host`) — maps preflight exit codes 1/2/3 to specific fixes, plus runtime errors (wrong model, dm20 tool 500s, schema fail). Diagnostic recipes use the user's existing `com.user.omlx` launchd label.
- `docs/character-ingest-formats.md` (same frontmatter) — table of supported formats (D&D Beyond URL / PNG-JPG / digital PDF / scanned PDF), per-format expected round-trip times against INGEST-11, INGEST-09 confidence gate rules, and the AGPL note on PyMuPDF.

### README Expansion

Added (preserving the existing voice — incremental, not rewrite):

- **First Session in 10 Minutes** section — minute-by-minute step-through from "fresh clone" to "rolling initiative."
- **First-Time Walkthrough — Reference** section — same flow condensed to a 11-step checklist for the second-time-around.
- **Self-Hosting** section — explicit macOS-primary + Linux best-effort posture with a platform support matrix; three equivalent entrypoint paths documented.
- **Running as a Service** section — macOS (launchd) + Linux (systemd) subsections; one-command install via `scripts/install-launchd.sh`; KeepAlive tradeoff explained; explicit `DISCORD_TOKEN`-NOT-in-plist warning.
- **License & Third-Party** section (renamed from "License") — PyMuPDF AGPL note + the fork-and-close pypdf-swap recipe (RESEARCH Pitfall 8).
- **Known Limitations & v1 Non-Goals** — added a "v1 design choices worth flagging" subsection covering: Battle Master RAW only (D-C), public Riposte button vs ephemeral (RESEARCH Q5), DISCORD_TOKEN-NOT-in-plist anti-pattern, OMLX_MODEL soft-warning behavior, Phase 4 pc_classes ingest-backfill caveat.
- **Roadmap** table updated to show all 5 phases ✅ Complete; v2 deferred list added.
- **Status badge** updated from `pre-alpha` to `v1.0-ready`.
- **Riposte references** corrected: was "Fighter/Battle Master or Rogue/Swashbuckler", now strict RAW Battle Master Fighter only per Phase 5 D-C.

### REQUIREMENTS / ROADMAP / STATE Closure

- **REQUIREMENTS.md**: COMBAT-09 wording amended per D-C (Swashbuckler removed; not RAW; v2 may add YAML-configurable eligibility). Ticked [x] for COMBAT-09, COMBAT-10, HOST-01..08 (12 total Phase 5 reqs now all complete; COMBAT-11 + OPS-01 were already [x] from Plan 02).
- **ROADMAP.md**: Phase 5 line flipped [ ] → [x]; Plans list now reflects three plans actually shipped (no more TBD); Phase 5 success criteria annotated with delivering-plan refs (✓ delivered by Plan NN).
- **STATE.md**: `status: in_progress → ready_for_audit`; `completed_phases: 0 → 5`; `percent: 0 → 100`; Phase Progress table row updated; Plan 03 performance-metric row added; six new decisions captured (D-A through D-F); Recent History updated with the full delivery surface.

### Tests

29 new tests across two new modules:

- `tests/test_bootstrap_preflight.py` (14 tests) — preflight exit-code paths, short-circuit ordering (schema fails → oMLX not queried), soft-warning behavior for missing OMLX_MODEL, .env.example MCP_RATE_LIMIT_MS + OMLX_CACHE_STRATEGY audit, pyproject `[project.scripts]` + `[project.urls]` + pinned-deps invariant (HOST-05).
- `tests/test_run_entrypoint.py` (15 tests) — `--check-only` returns preflight's code, `ELDRITCH_ALLOW_OFFLINE_START=1` skips preflight, missing `DISCORD_TOKEN` fails non-zero with field-named stderr, SIGTERM handler raises KeyboardInterrupt (with finally-clause handler restoration so the test does NOT leak its handler into the rest of the pytest session), `import run` has no side effects, plist validates with plutil + has correct structure + DISCORD_TOKEN warning is inside an XML comment block, systemd unit has required sections + fields, install-launchd.sh + uninstall-launchd.sh are executable + idempotent + DRY_RUN-clean, both troubleshooting docs are substantive (>500 bytes) with YAML frontmatter.

## Behavior Changes

| Surface | Before Plan 03 | After Plan 03 |
| ------- | -------------- | ------------- |
| `python -m eldritch_dm.bootstrap` | `ModuleNotFoundError` (only `persistence.bootstrap` existed) | Runs 3-stage preflight; returns 0/1/2/3 |
| `python run.py` | File did not exist | Validates env, runs preflight, starts bot with SIGTERM handler |
| `python run.py --check-only` | N/A | Runs preflight and exits with preflight's code |
| `python run.py --no-preflight` | N/A | Skips preflight (dev hatch) |
| `eldritch-dm` (CLI) | Not installed | Available after `pip install -e .` — runs `eldritch_dm.bot.__main__:main` |
| `.env.example` MCP_RATE_LIMIT_MS | Missing despite Settings field | Documented with default 200 + 🧪 tag |
| `.env.example` OMLX_CACHE_STRATEGY | Orphan (commented; not consumed) | Removed with explanatory comment |
| `pyproject.toml` `[project.scripts]` | Missing | `eldritch-dm = "eldritch_dm.bot.__main__:main"` |
| `pyproject.toml` `[project.urls]` | Missing | Homepage/Repository/Issues placeholders |
| `scripts/install-launchd.sh` | Did not exist | One-command launchd lifecycle (DRY_RUN=1 supported) |
| README "First Session in 10 Minutes" | Implicit in 11-step walkthrough | Explicit section, minute-by-minute |
| REQUIREMENTS.md COMBAT-09 | "Fighter/Battle Master, Rogue Swashbuckler" | "Fighter/Battle Master (RAW)" + v2 homebrew note |
| ROADMAP.md Phase 5 | [ ] | [x] with three-plan reflection |
| STATE.md cursor | Phase 5 in-progress | Phase 5 complete; v1.0 ready for audit |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test SIGTERM handler leaking into rest of pytest session**
- **Found during:** Full-suite verification after Task 2 commit
- **Issue:** `test_sigterm_handler_raises_keyboard_interrupt` installed a SIGTERM handler that persisted into the rest of the pytest run (single-process). Additionally `test_run_offline_start_skips_preflight` called `run.main([])` which itself installs the SIGTERM handler before invoking the faked `bot.run`.
- **Fix:** (a) `test_sigterm_handler_raises_keyboard_interrupt` captures the pre-test handler and restores it in a `finally` block; (b) `test_run_offline_start_skips_preflight` monkeypatches `run._install_sigterm_handler` to a no-op so the test path through `main()` does not modify the test process's signal handling.
- **Files modified:** `tests/test_run_entrypoint.py`
- **Commit:** `7d307a1` (Task 3 — folded in with closure paperwork)

**2. [Rule 3 - Blocking] First pyproject.toml edit created two `[project]` tables**
- **Found during:** Task 1 — initial `[project.scripts]` placement
- **Issue:** The Edit operation inserted `[project.scripts]` + `[project.urls]` after `authors` but before `dependencies`, then re-opened `[project]` with `dependencies = [...]` — creating two `[project]` tables. TOML build would have failed.
- **Fix:** Restructured to keep `dependencies` inside the original `[project]` table and place the two new tables AFTER it.
- **Files modified:** `pyproject.toml`
- **Commit:** Pre-commit fix in Task 1 — never landed as broken.

### Open-Question Resolutions

- **OMLX_CACHE_STRATEGY** — option (a) REMOVE the orphan line. Rationale documented in D-A above. Alternative (option b) would have required maintaining a passthrough Settings field with no Python consumer, which would resurface as confusion in future audits.
- **`run.py --no-preflight` flag** — YES, ship it alongside `ELDRITCH_ALLOW_OFFLINE_START=1` (D-B). CLI flag is friendlier for ad-hoc dev runs; env var is friendlier for launchd-managed prod.

### Scope Adherence

- No pre-existing unstaged file in the repo at start of Plan 03 (the 23+ modified files surfaced in the user's prompt) was touched by this plan. All Plan 03 commits stage only files newly created or actively modified by the plan's tasks.
- Full-suite ruff has 79 errors in pre-existing files (mostly E501 + I001 + UP035). These are out of scope per the SCOPE BOUNDARY rule — none originate in Plan 03 surface. Plan 03 files (`src/eldritch_dm/bootstrap.py`, `run.py`, `tests/test_bootstrap_preflight.py`, `tests/test_run_entrypoint.py`) pass `uv run ruff check` cleanly.

## Threat Surface Scan

No new security-relevant surface introduced. STRIDE register T-05-16 (DISCORD_TOKEN in world-readable plist) is **mitigated** as planned:

- The plist's `EnvironmentVariables` contains only `PATH`, `LOG_FORMAT=json`, and `ELDRITCH_ALLOW_OFFLINE_START=1` — no secrets.
- A top-of-file XML comment block in `docs/launchd.plist.example` warns against putting DISCORD_TOKEN in the plist.
- README's "Known Limitations" subsection states `DISCORD_TOKEN MUST NOT live in the launchd plist (or systemd unit)` with the rationale.
- The test `test_plist_environment_and_comment` asserts `<key>DISCORD_TOKEN</key>` is NOT in the plist body — only inside an `<!-- … -->` comment block — so any future regression would fail CI.

T-05-17 (bad-token restart storm) **mitigated** via dict-form KeepAlive + ThrottleInterval=10.

T-05-18 (localhost plaintext HTTP to oMLX) **accepted** as the standard local-first pattern.

T-05-20 (sudo escalation) **accepted** as not-relevant — `install-launchd.sh` is user-scope, never invokes sudo, uses `launchctl bootstrap gui/$UID`.

T-05-SC (supply chain) **accepted** — zero new pip dependencies introduced.

## Test Suite Status

```
855 passed, 9 skipped, 83 warnings in 9.27s
```

Delta from start of Plan 03: **+29 tests** (826 → 855).

7/7 import-linter contracts KEPT.

Ruff clean on all Plan 03 files (`src/eldritch_dm/bootstrap.py`, `run.py`, `tests/test_bootstrap_preflight.py`, `tests/test_run_entrypoint.py`).

`uv run python -m eldritch_dm.bootstrap` resolves the module and runs `main()` (verified end-to-end).

`DRY_RUN=1 bash scripts/install-launchd.sh` exits 0 and validates the rendered plist via `plutil -lint` without touching `~/Library/LaunchAgents/`.

## Self-Check: PASSED

All claimed artifacts exist on disk and are committed:

- `src/eldritch_dm/bootstrap.py` ✓ (commit `70316db`)
- `run.py` ✓ (commit `d862b55`)
- `docs/launchd.plist.example` ✓ (commit `d862b55`)
- `docs/eldritch-dm.service.example` ✓ (commit `d862b55`)
- `docs/dm20-troubleshooting.md` ✓ (commit `d862b55`)
- `docs/character-ingest-formats.md` ✓ (commit `d862b55`)
- `scripts/install-launchd.sh` ✓ (commit `d862b55`, executable)
- `scripts/uninstall-launchd.sh` ✓ (commit `d862b55`, executable)
- `tests/test_bootstrap_preflight.py` ✓ (commit `70316db`, 14 tests passing)
- `tests/test_run_entrypoint.py` ✓ (commit `d862b55` + handler-leak fix in `7d307a1`, 15 tests passing)
- README expansion ✓ (commit `7d307a1`)
- REQUIREMENTS.md tick marks ✓ (commit `7d307a1`)
- ROADMAP.md Phase 5 [x] ✓ (commit `7d307a1`)
- STATE.md cursor advance ✓ (commit `7d307a1`)

## Next Step

**Phase 5 closure human-verify checkpoint** (Task 4 of the plan) is the gate before the milestone-audit step. After human approval the operator runs `/gsd:audit-milestone v1.0` and then `/gsd:complete-milestone v1.0`.
