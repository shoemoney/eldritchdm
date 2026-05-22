---
phase: 05-reactions-self-host-polish
subsystem: cross-cutting (combat + persistence + bot + self-host)
tags: [riposte, sweeper, restart-survival, self-host, launchd, systemd, milestone-v1]

# Phase-level dependency graph
requires:
  - phase: 04-gameplay-exploration-combat
    provides: AttackButton with `_maybe_surface_riposte` seam (deleted in Plan 01), PartyModeOrchestrator (concurrent-with-sweeper), CombatCog + dynamic items + 8-actor load proof
  - phase: 03-lobby-character-ingest
    provides: dm20 character ingest pipeline (Plan 01 pc_classes table persists subclass at ingest time, closing the RESEARCH Q2 gap)
  - phase: 02-discord-scaffold-persistent-views
    provides: persistent-view rehydration, EmbedCoalescer, OPS-04 shutdown chain (extended by Plan 02 to drain the sweeper FIRST)
  - phase: 01-mcp-client-local-state
    provides: WAL SQLite + RiposteTimerRepo + persistence.bootstrap (Plan 03 re-exports as top-level eldritch_dm.bootstrap)

provides_to_milestone_v1:
  - "Timed Riposte UI (Battle Master Fighter RAW only per D-C) that fires on monster-attack-misses-PC, survives bot restart, and serializes click-vs-expiry via shared per-channel asyncio.Lock"
  - "RiposteSweeper background task with conditional mark_expired SQL (belt-and-suspenders against any lock failure)"
  - "OPS-01 resume drill — kill bot during active riposte window, restart, button is still clickable until its deadline_ts; expired timers auto-cleaned on restart (6 integration tests at 0.20s wall-clock)"
  - "Top-level bootstrap.py with 3-stage preflight (schema → oMLX → MCP) and structured exit codes 0/1/2/3"
  - "run.py project-root entrypoint with --check-only / --no-preflight / SIGTERM handler / ELDRITCH_ALLOW_OFFLINE_START escape hatch"
  - ".env.example audited; pyproject.toml [project.scripts] + [project.urls] shipped"
  - "macOS launchd plist + install/uninstall scripts (idempotent, DRY_RUN safe) + Linux systemd best-effort"
  - "Self-host docs (dm20-troubleshooting, character-ingest-formats) + README walkthrough + Self-Hosting / Running as a Service / Known Limitations / License sections"
  - "All Phase 5 requirements ticked [x]; COMBAT-09 wording corrected per D-C; ROADMAP Phase 5 [x]; STATE cursor at v1.0 ready-for-audit"

# Closure status
status: complete
ready_for: "/gsd:audit-milestone v1.0"
human_verify_pending: true  # Plan 03 Task 4 checkpoint must be approved before milestone audit
---

# Phase 5: Reactions + Self-Host Polish — Synthesis Summary

Phase 5 closes v1 of EldritchDM. Going into Phase 5 the gameplay loop worked end-to-end (Phase 4 shipped 8-actor combat + the load proof), but two things kept v1 from being "shippable":

1. **The signature reactive UI (Riposte) was a Phase 2 stub** — the AttackButton had a `_maybe_surface_riposte` seam that did nothing, and the button class returned ephemeral followups that would not survive a bot restart.
2. **The self-host story was implicit** — the README pointed at `python -m eldritch_dm.bootstrap` which did not exist, the launchd recipe was unwritten, the `.env.example` was missing one variable and had an orphan that was never consumed, and there was no `run.py` at the project root.

Phase 5 fixed both. Three plans:

## Plan 01 — Riposte + MonsterDriver

**Wave 0:** schema `consumed_in_round INTEGER` ALTER on `riposte_timers` (the reaction-per-round budget — dm20 has no native reaction model, so we tracked it locally); new `pc_classes` table to persist subclass at character ingest (RESEARCH Q2 — `dm20__get_character` renders text that omits subclass).

**Plan 01 D-A:** **Delete** the Phase 4 `_maybe_surface_riposte` seam in AttackButton (fired on the wrong RAW path — PC misses monster, not monster misses PC). Riposte now fires from a new MonsterDriver code path.

**Plan 01 D-B:** MonsterDriver is **minimal random-target for v1**. Smart Claudmaster-driven targeting (REACT-* family) is deferred to v2.

**Plan 01 D-C:** **Strict RAW** eligibility — Battle Master Fighter only. CONTEXT.md D-04's earlier note of "Battle Master Fighter, Swashbuckler Rogue" was incorrect by-the-book; Swashbuckler has Fancy Footwork + Rakish Audacity, not Riposte. v2 plans YAML-configurable eligibility for homebrew (Swashbuckler / Brute / etc.).

**Public riposte message + permission gate**, not ephemeral followup. RESEARCH Q5: ephemeral followups die at 15 min and cannot be re-edited from a fresh bot process — they would break COMBAT-11 restart-survival. Tradeoff documented in README "Known Limitations."

**PLAN-02-LOCK-SEAM marker** placed at `reactions.py:280` so Plan 02's executor could grep-and-replace deterministically.

**64 new tests, 798 total at Plan 01 close (70 min).**

## Plan 02 — Sweeper + Restart Survival

**SessionLocks** namespaced asyncio.Lock registry (`gameplay/session_locks.py`) — gameplay primitive, not a bot primitive (D-A: lives under `gameplay/` to satisfy the import-linter "gameplay must not import bot" contract).

**RiposteSweeper** background task (`gameplay/riposte_sweeper.py`) — RESEARCH Pattern 4 — wakes at the earliest pending `deadline_ts`, marks expired rows with conditional `WHERE status='pending'` SQL (belt-and-suspenders, D-C), deletes the Discord message OUTSIDE the lock on success (D-E — HTTP latency must not stall click-vs-sweeper serialization).

**handle_riposte_click wrapped in the same lock** — eliminates the click-vs-sweeper race. Two `repo.get()` calls per click: pre-lock to discover `channel_id` (the lock key) and under-lock for the authoritative status read after the sweeper may have flipped it (D-D).

**setup_hook ordering** (D-F): sweeper.start() comes AFTER `rehydrate_persistent_views` so DynamicItems are registered before any sweeper-routed Discord interactions could dispatch. **close() ordering** (OPS-04 extension): sweeper.stop() FIRST so in-flight Discord deletes finish before the orchestrator/health/writer-queue/mcp/super.close cascade.

**OPS-01 resume drill** — 6 integration tests at `tests/integration/test_riposte_restart.py` (0.20s wall-clock) — proving COMBAT-11. Kill the bot mid-window, restart, click → still works. Or wait past deadline, restart → expired-cleanup happens on first sweep.

**28 net new tests, 826 total at Plan 02 close (35 min). Zero new pip deps.**

## Plan 03 — Self-Host Polish + Phase 5 Closure

**Top-level `eldritch_dm.bootstrap`** module (`src/eldritch_dm/bootstrap.py`) closing RESEARCH Pitfall 7 — README + docs/CONFIGURATION had been referencing `python -m eldritch_dm.bootstrap` for months but the module didn't exist (only `persistence.bootstrap`). Plan 03 re-exports the persistence one AND adds a 3-stage preflight per RESEARCH Pattern 5 (schema → oMLX → MCP) with structured exit codes (0/1/2/3).

**`run.py`** project-root entrypoint per RESEARCH Pattern 6 — `--check-only` for CI/launchd smoke, `--no-preflight` for ad-hoc dev (D-B), `ELDRITCH_ALLOW_OFFLINE_START=1` for launchd cold-start race, SIGTERM→KeyboardInterrupt handler so OS-supervisor shutdowns trigger the OPS-04 chain cleanly.

**`.env.example` audit:** added `MCP_RATE_LIMIT_MS=200` (was missing per RESEARCH Q9 despite Settings field being live since Phase 1); removed orphan `OMLX_CACHE_STRATEGY` line with explanatory comment (D-A: option (a) per Task 1 — no Python consumer ever existed; configured on oMLX server side).

**`pyproject.toml`:** `[project.scripts] eldritch-dm = "eldritch_dm.bot.__main__:main"` (D-23) and `[project.urls]` Homepage/Repository/Issues (D-25).

**launchd recipe** — `docs/launchd.plist.example` with dict-form KeepAlive + `ThrottleInterval=10` per RESEARCH Pattern 7 (D-F: deliberately deviates from `com.user.omlx`'s plain `KeepAlive=true` to prevent bad-token restart storms; README documents the tradeoff). `scripts/install-launchd.sh` is idempotent and DRY_RUN=1-safe (D-C: tempfile rendering avoids writing to `~/Library/LaunchAgents/` during dry runs).

**systemd unit** — `docs/eldritch-dm.service.example` (HOST-07 best-effort).

**Self-host docs:** `docs/dm20-troubleshooting.md` maps preflight exit codes to specific fixes; `docs/character-ingest-formats.md` covers all supported character-sheet formats with confidence-gate rules.

**README expansion:** First Session in 10 Minutes, Self-Hosting, Running as a Service, expanded Known Limitations (Battle Master RAW only per D-C, public Riposte button rationale, DISCORD_TOKEN-NOT-in-plist warning, Phase 4 pc_classes ingest-backfill caveat), License & Third-Party (PyMuPDF AGPL note per RESEARCH Pitfall 8).

**Closure paperwork:** REQUIREMENTS.md COMBAT-09 wording corrected per D-C; all 12 Phase 5 reqs ticked [x] (COMBAT-09/10/11, HOST-01..08, OPS-01); ROADMAP.md Phase 5 [x] with three-plan reflection; STATE.md cursor advanced to `status: ready_for_audit`, `completed_phases: 5/5`, `percent: 100`.

**29 net new tests, 855 total at Plan 03 close.**

## v1 Ships With

- **Mechanically honest AI DM** — every die roll, HP change, AC check, turn boundary enforced by deterministic Python; the LLM only narrates.
- **Timed Riposte** (Battle Master Fighter RAW only) — public button with permission gating; 8-second deadline enforced by `RiposteSweeper`; survives bot kill.
- **Restart-survival** — Phase 2's persistent_views + Phase 5's RiposteSweeper + WAL SQLite + dm20's own state — proven by OPS-01 (6 tests) + COMBAT-11 + BOT-08 (kill-mid-combat).
- **Self-host runbook** — `python -m eldritch_dm.bootstrap` preflight, `python run.py` (or `eldritch-dm` CLI), launchd recipe with one-command install + uninstall, systemd best-effort.
- **Full test suite green** — 855 passed, 9 skipped, 9.27s; 7/7 import-linter contracts KEPT; defer-discipline enforced by EDM001 lint; 4-channel concurrent write stress test (RUN_STRESS=1); 8-player combat load proof (RUN_LOAD=1).
- **Documentation** — every architectural decision in `.planning/`; every operational pain point in `docs/`; the README explicitly states the "in 10 minutes" claim and walks through it.

## v2 Deferred List

| Item | Why deferred | Surface |
| ---- | ------------ | ------- |
| YAML-configurable Riposte eligibility (Swashbuckler, homebrew classes) | RAW first; homebrew via config rather than core branch | `gameplay/reactions.py` ELIGIBLE_CLASS_SUBCLASSES |
| Smart Claudmaster-driven monster targeting | Claudmaster session-state plumbing is days of work; v1 random-target is RAW-correct | `gameplay/monster_driver.py` |
| REACT-01 / 02 / 03 (Shield, Counterspell, Hellish Rebuke) | Each reaction has its own UX (modal-driven cost selection, spell-slot menus); v1 only ships the simplest reaction | new `gameplay/reactions_*.py` modules |
| EXUI-01 (voice / TTS narration to Discord voice channels) | Wrong surface for v1 — text only | `bot/cogs/voice_cog.py` (planned v2) |
| EXUI-02 (map/grid visuals — dm20 has `show_map`) | Rendering layer scope; competes with inference for unified memory | `bot/embeds/map_embed.py` (planned v2) |
| ADV-* (adventure browser, sheet sync flow, compendium I/O) | Workflow polish, not core mechanics | various |

## The OPS-01 Resume Drill as Marketing-Grade Proof

The single most quotable thing about v1: **kill the bot mid-combat, restart it, the button still works.**

Proof: `tests/integration/test_riposte_restart.py` (6 tests, 0.20s wall-clock):

1. `test_pending_timer_survives_restart` — open a riposte, kill the bot, restart, the row is still pending, the button still dispatches.
2. `test_expired_timer_cleaned_on_restart` — open a riposte, wait past deadline, restart, the first sweeper iteration marks the row expired (conditional SQL is a no-op if a Plan 01 callback already flipped it).
3. `test_sweeper_does_not_double_mark_expired` — concurrent sweeper iterations under load do not double-mark.
4. `test_click_vs_sweeper_race_serialized` — simultaneous click and sweeper iteration acquire the same per-channel lock; whichever runs first wins.
5. `test_setup_hook_orders_sweeper_after_rehydration` — source-inspection assertion of the D-F ordering.
6. `test_ops04_close_drains_sweeper_first` — source-inspection assertion of the OPS-04 extended chain.

## Lessons Learned

1. **Phase 4 mis-placed the riposte seam.** The `_maybe_surface_riposte` hook in AttackButton fired on PC-attacks-monster-and-misses, but RAW Riposte fires on monster-attacks-PC-and-misses. Caught only because Phase 5 RESEARCH re-walked the AttackButton callback. **Planner lesson:** when a prior phase leaves a stub-shaped seam, the next phase should grep ALL stubs and validate each one against the RAW source before extending.

2. **Documentation drift is real and costly.** README and `docs/CONFIGURATION.md` had been referencing `python -m eldritch_dm.bootstrap` for months even though that module did not exist. Detected by RESEARCH Pitfall 7. **Lesson:** every code-organization decision should be cross-checked against any user-facing instructions that reference it. A CI hook (lint that the documented `python -m foo.bar` paths actually import) would catch this.

3. **Phase 1's `RiposteTimer` model had `consumed_in_round` as a TODO in the schema docstring** — but the actual column wasn't there. Phase 5 Plan 01 added it via `ALTER TABLE` in `bootstrap()` (idempotent via try/except duplicate-column detection). **Lesson:** TODO-comments in schema files should be tracked as planning items, not allowed to drift.

4. **Single-process pytest is a signal-handler trap.** Plan 03 Task 2's first full-suite run "hung" because `test_run_offline_start_skips_preflight` invoked `run.main([])` which installed a SIGTERM handler that overrode pytest's own signal handling. Caught and fixed in Task 3 by monkeypatching `_install_sigterm_handler` to a no-op in that test, plus adding a `try/finally` handler-restoration in the `test_sigterm_handler_raises_keyboard_interrupt` test itself. **Lesson:** any test that exercises code which calls `signal.signal()` must restore the pre-test handler in a `finally` block, OR the function-under-test must be monkeypatched out.

## Next Action

`/gsd:audit-milestone v1.0` — verifies every v1 requirement is `[x]`, all SUMMARY.md files self-checked, no Known Stubs prevent goal achievement.

Then `/gsd:complete-milestone v1.0` — archives the planning artifacts and tags the release.

**Pre-audit gate:** Plan 03 Task 4 human-verify checkpoint — operator runs the manual smoke (README readthrough, `python run.py --check-only`, `DRY_RUN=1 bash scripts/install-launchd.sh`) and approves.
