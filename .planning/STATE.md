---
gsd_state_version: 1.0
milestone: v1.8
milestone_name: Multi-Channel Hardening
status: executing
last_updated: "2026-05-26T04:35:44.040Z"
last_activity: 2026-05-26 -- Phase 28 execution started
progress:
  total_phases: 23
  completed_phases: 22
  total_plans: 41
  completed_plans: 41
  percent: 96
---

# EldritchDM — State

**Last updated:** 2026-05-22 (v1.0 milestone audit BLOCKERS closed via hotfix series 4c15641/e22be5b/25cb7a0 + closure commit; audit status `gaps_found` → `passed`; 71/73 reqs satisfied (G-3 SAN-01 + G-4 OPS-02 deferred to v1.1); 864 passing / 873 collected; awaiting human `/gsd:complete-milestone v1.0`)
**Milestone:** v1.0 — feature-complete; awaiting human-verify checkpoint then milestone audit
**Mode:** YOLO + autonomous loop via `/loop /gsd-autonomous`

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-21)

**Core value:** Mechanically honest AI DM, on Discord, fully local — bot never computes game math; all mechanical effects flow through dm20 MCP tools.
**Current focus:** Phase 28 — tuning

## Architecture (post-pivot)

- **Voice** = oMLX `ShoeGPT` model on `:8765` (already running, launchd `com.user.omlx`)
- **Brain** = `dm20` MCP server, 97 tools exposed at `:8765/v1/mcp/execute`
- **Orchestrator** = this Discord bot (the thing we're building)
- **Local DB** = small SQLite for Discord-specific state only (channel↔campaign, riposte timers, view registry, sanitizer audit)
- **Discord ↔ dm20** = Party Mode queue binding (pop_action / thinking / get_prefetch / resolve_action)

## Phase Progress

| # | Phase | Status |
|---|-------|--------|
| 1 | MCP Client + Local State | ✅ Complete (3/3 plans, 177 tests) |
| 2 | Discord Scaffold + Persistent Views | ✅ Complete (3/3 plans, 284 tests) |
| 3 | Lobby + Character Ingest | ✅ Complete (3/3 plans, 469 tests) |
| 4 | Gameplay — Exploration + Combat (Party Mode) | ✅ Complete (3/3 plans, 730 tests inc. load-gated) |
| 5 | Reactions + Self-Host Polish | ✅ Complete (3/3 plans, ~870 tests inc. preflight + run.py + closure) |

## Blockers / Concerns

- [ ] Verify dm20 supports concurrent multi-campaign sessions in one process (Phase 1 spike)
- [x] Verify dm20 has a "dodging" condition / `apply_effect` semantics suitable for our Dodge action (Phase 4) — resolved: shim uses combat_conditions table + apply_effect("dodging")
- [ ] Verify dm20 models reactions (`has_reaction`) natively; if not, design the shim (Phase 5)
- [ ] Confirm `dm20__party_pop_action` returns immediately when queue empty (we may need polling cadence vs WS)

## Decisions

- Used Python 3.11 venv (python3.11 on PATH) despite project allowing <3.13
- Removed TCH ruff rules — false positives with pydantic/aiosqlite runtime usage
- ASYNC240 (pathlib in async) suppressed for bootstrap.py — startup-only code, not hot path
- safety may import persistence.models (pure pydantic data shapes); contract relaxed to allow this while still forbidding persistence internals
- CircuitBreaker is CLOSED/OPEN only (no HALF_OPEN) for Phase 1 simplicity
- sanitize_player_input is sync — Discord event handler calls it synchronously before any async work
- Truncate-first in sanitizer: cap before strip prevents cap-evading injection attacks
- Stress test gated behind RUN_STRESS=1: excluded from default pytest run
- bootstrap() (async) used in setup_hook — Phase 1 shipped bootstrap(), not ensure_schema(); same function
- EldritchBot setup_hook raises on failure — never calls bot.close() (Discord.py issue #8210)
- Intents.default() + message_content=False: security decision per D-04 — bot cannot read raw messages
- dpytest skipped: officially caps at discord.py 2.6; direct MagicMock/AsyncMock recipe used instead
- MCPClient URL: strip trailing /v1 from omlx_endpoint before passing to MCPClient
- add_dynamic_items alone is sufficient for DynamicItem restart-survival; add_view calls are audit-only (RESEARCH.md Pitfall 1)
- asyncio.Event + latest-value slot for EmbedCoalescer; not Queue(maxsize=1) (non-blocking, race-free)
- EDM001 implemented as AST-based pre-commit hook; no Rust toolchain needed
- OPS-04: asyncio.wait_for(writer_queue.stop(), timeout=5.0) — shutdown always completes (T-02-16)
- RUN_INTEGRATION=1 gate for restart-drill integration tests (slow DB I/O)
- _ModalLaunchView 2-step: defer() conflicts with send_modal() (first-response-only); solution is ephemeral button → fresh interaction → send_modal()
- 5-component Modal cap: ability scores packed as space-separated single TextInput ("15 14 13 12 10 8")
- EDM001 noqa: _ModalLaunchView button and modal on_submit are valid exceptions to defer-first rule
- Confidence threshold 0.6: >= 0.6 → CharacterReviewModal (prefilled); < 0.6 → CharacterEntryModal
- player_id=str(interaction.user.id) persisted on dm20__create_character for Phase 4 turn gatekeeping
- Non-ephemeral lobby update: lobby_message_id from dm20_party_token JSON; missing key = graceful skip
- _get_poll_cadence: COMBAT returns 1 (every tick), EXPLORATION returns _combat_check_every_n (default 4)
- asyncio.gather(return_exceptions=True) for state_change callbacks: one cog raising doesn't block others
- AttackButton._maybe_surface_riposte is Phase 5 seam: no-op in Phase 4; RiposteCog hooks here (DELETED in Phase 5 Plan 01 — wrong RAW path per D-A; Riposte fires from MonsterDriver on monster-misses-PC)
- Phase 5 D-B: MonsterDriver is minimal random-target for v1; smart Claudmaster-driven targeting deferred to v2 (REQUIREMENTS REACT-*)
- Phase 5 D-C: Strict RAW eligibility for Riposte — Battle Master Fighter only (Swashbuckler explicitly excluded; corrects CONTEXT.md D-04)
- Phase 5 reaction-budget shim: additive ALTER TABLE riposte_timers ADD COLUMN consumed_in_round INTEGER (dm20 has no native reaction tracking — RESEARCH Q1)
- Phase 5 pc_classes table: subclass persisted at ingest because dm20 get_character text omits subclass (RESEARCH Q2)
- Phase 5 Riposte button is public message + permission gate (NOT ephemeral) — ephemeral followups die at 15 min and break COMBAT-11 restart-survival
- Phase 5 deadline recompute AFTER channel.send (RESEARCH Pitfall 1) — TTL not consumed by Discord API latency
- Phase 5 PLAN-02-LOCK-SEAM marker convention: deliberate one-line docstring marker in handle_riposte_click for Plan 02's executor to grep (REPLACED in Plan 02 by real session_locks.lock_for wrapper)
- Phase 5 dependency-inject send_warning + WarningKind + button_factory into gameplay/reactions so import-linter contract "gameplay must not import bot or ingest" stays KEPT
- Phase 5 Plan 02 D-A: SessionLocks lives under gameplay/ (not bot/) per the import-linter contract; same reasoning extends to RiposteSweeper. Both are gameplay synchronization primitives, not Discord primitives.
- Phase 5 Plan 02 D-B: RiposteSweeper.stop() CANCELS (does not flush) in-flight mark_expired calls — clean shutdown semantics; pending rows survive across restart and get cleaned up on the next bot's first sweep
- Phase 5 Plan 02 D-C: mark_expired SQL is conditional (WHERE id=? AND status='pending') — race-loser's UPDATE is a 0-row no-op, belt-and-suspenders correctness alongside the shared lock
- Phase 5 Plan 02 D-D: handle_riposte_click does TWO repo.get() per click — pre-lock to discover channel_id (lock key is per-channel), under-lock for authoritative status read after sweeper may have flipped status
- Phase 5 Plan 02 D-E: Discord message delete moved OUTSIDE the lock on the success path — HTTP latency must not stall click-vs-sweeper serialization
- Phase 5 Plan 02 D-F: setup_hook orders sweeper.start() AFTER rehydrate_persistent_views — DynamicItems must be registered before sweeper-triggered Discord interactions could route
- Dodge v1 shim: combat_conditions table + apply_effect("dodging"); expires_round = applied_round + 1
- Cross-cog helpers on EldritchBot: close_exploration_coalescer_for / close_combat_coalescer_for avoid cog-to-cog circular imports
- _PARAM_REMAP in setup_hook.py bridges regex group names (round) to __init__ params (round_n) for combat buttons
- attrs-before-super pattern in combat DynamicItems: set self.channel_id/actor_id/round_n BEFORE super().__init__() (discord.py accesses custom_id during init)
- RUN_LOAD=1 gate for 8-actor combat load test: mirrors Phase 1 RUN_STRESS=1 convention; nightly/contributor opt-in via env var
- Virtual-clock injection (clock=clock.now, sleep=clock.advance) threaded through ChannelRateLimiter + ChannelEditBudget + EmbedCoalescer for deterministic sub-second load simulation
- CombatConditionsRepo._connect() returns UNSTARTED Connection — callers do `async with self._connect()` (Rule 1 fix: prior `async with await self._connect()` double-started the Thread)
- CombatConditionsRepo.insert() does DELETE-by-triple + single INSERT (Rule 1 fix: prior INSERT ON CONFLICT + INSERT OR REPLACE pattern created duplicate rows because schema has no UNIQUE on (channel_id, character_id, condition_kind))
- Phase 5 Plan 03 D-A: OMLX_CACHE_STRATEGY orphan resolved via REMOVAL (option a) — line deleted from .env.example with explanatory comment "oMLX cache strategy is configured on the oMLX server side, not via this .env" (avoids maintaining a passthrough Settings field with no Python consumer)
- Phase 5 Plan 03 D-B: run.py exposes BOTH --no-preflight CLI flag AND ELDRITCH_ALLOW_OFFLINE_START=1 env var — CLI flag for ad-hoc dev runs, env var for launchd-managed prod (RESEARCH Pattern 6 / D-15)
- Phase 5 Plan 03 D-C: install-launchd.sh DRY_RUN=1 renders the plist to a tempfile + plutil-lints there, instead of writing to ~/Library/LaunchAgents/ (safer for CI smoke; no stale files left behind on failed runs)
- Phase 5 Plan 03 D-D: Preflight schema check FIRST, then oMLX, then MCP — schema failure (permission denied, disk full) short-circuits before any network I/O so the operator sees the root cause immediately
- Phase 5 Plan 03 D-E: Missing OMLX_MODEL is a soft WARNING (not EXIT_OMLX_UNREACHABLE) — operators may load a different model intentionally; preflight does not exit on this (RESEARCH A5)
- Phase 5 Plan 03 D-F: launchd plist uses dict-form KeepAlive with SuccessfulExit=false + ThrottleInterval=10 (RESEARCH Pattern 7); deliberately deviates from com.user.omlx's plain KeepAlive=true so bad DISCORD_TOKEN doesn't cause infinite restart storm; README documents the tradeoff so operators can flip to plain KeepAlive=true if they want unconditional supervision

## Performance Metrics

| Phase | Plan | Duration (min) | Tasks | Files |
|-------|------|----------------|-------|-------|
| 01-mcp-client-local-state | 01 | 18 | 3 | 18 |
| 01-mcp-client-local-state | 02 | 45 | 5 | 15 |
| 01-mcp-client-local-state | 03 | 40 | 4 | 10 |
| 02-discord-scaffold-persistent-views | 01 | 15 | 3 | 9 |
| 02-discord-scaffold-persistent-views | 02 | 45 | 3 | 12 |
| 02-discord-scaffold-persistent-views | 03 | 90 | 4 | 13 |
| 03-lobby-character-ingest | 01 | 120 | 4 | 16 |
| 03-lobby-character-ingest | 02 | 90 | 4 | 14 |
| 03-lobby-character-ingest | 03 | 85 | 5 | 12 |
| 04-gameplay-exploration-combat | 02 | 180 | 3 | 17 |
| 04-gameplay-exploration-combat | 03 | 90 | 3 | 5 |
| 05-reactions-self-host-polish | 01 | 70 | 3 | 27 |
| 05-reactions-self-host-polish | 02 | 35 | 2 | 12 |
| 05-reactions-self-host-polish | 03 | TBD | 3 | 14 |

## Recent History

- 2026-05-21: Project init → research → roadmap (11 phases, 87 reqs)
- 2026-05-21: Discovered 116-tool MCP toolbox via `ddmcpskills.md`
- 2026-05-21: Pivot decision: hybrid (dm20 for content, ours for Discord state), Party Mode binding, Riposte stays, OCR/PDF stays
- 2026-05-21: Roadmap revised 11 → 5 phases; requirements 87 → ~55
- 2026-05-21: Phase 1 Plan 01 (foundation) complete — pyproject.toml, config, logging, WAL persistence, import-linter; 73 tests passing
- 2026-05-21: Phase 1 Plan 02 (repositories+MCP) complete — 4 repos, MCPClient, circuit breaker, 28 tool wrappers; 105 tests passing
- 2026-05-21: Phase 1 Plan 03 (sanitizer+stress) complete — sanitizer, 34-case corpus, 4-channel stress test, integration smoke; 177 tests passing
- 2026-05-21: Phase 1 COMPLETE — all 3 plans done, pre-commit ruff hooks, import-linter 4 contracts KEPT
- 2026-05-21: Phase 2 Plan 01 COMPLETE — EldritchBot scaffold, /ping+/status diagnostics cog, lifecycle test harness, import-linter 5 contracts KEPT; 188 tests passing
- 2026-05-21: Phase 2 Plan 02 COMPLETE — embed renderers (4 templates, JSON snapshots), DynamicItem subclasses (4 persistent buttons), warning helper; 235 tests passing
- 2026-05-21: Phase 2 Plan 03 COMPLETE — EmbedCoalescer (≤1 edit/sec), setup_hook rehydration, EDM001 AST lint, restart drill (BOT-08), OPS-04 shutdown; 284 tests passing
- 2026-05-21: PHASE 2 COMPLETE — all 3 plans done, BOT-01..08 + OPS-04 satisfied, pre-commit ruff+EDM001 hooks, import-linter 5 contracts KEPT
- 2026-05-22: Phase 3 Plan 01 COMPLETE — LobbyCog (/start_game, /load_adventure, ReadyButton), party_mode_parser, permissions, QR embed; 127 new tests
- 2026-05-22: Phase 3 Plan 02 COMPLETE — OCR/PDF ingest pipeline, oMLX schema translation, IngestResult with confidence scoring; 82 new tests
- 2026-05-22: Phase 3 Plan 03 COMPLETE — IngestCog (3 upload commands), CharacterReviewModal + CharacterEntryModal (5-component cap), _ModalLaunchView 2-step pattern, QR helper extracted; 55 new tests; 469 total passing
- 2026-05-22: PHASE 3 COMPLETE — all 3 plans done, LOBBY-01..04 + INGEST-01..11 satisfied, import-linter 6 contracts KEPT
- 2026-05-22: Phase 4 Plan 01 COMPLETE — PartyModeOrchestrator + ExplorationCog + DeclareActionModal + embed rendering; 58 new tests
- 2026-05-22: Phase 4 Plan 02 COMPLETE — CombatCog + combat buttons + dodge shim + turn gatekeeping + orchestrator cadence + integration tests; 257 new tests; 726 total passing
- 2026-05-22: Phase 4 Plan 03 COMPLETE — 8-actor combat load test (RUN_LOAD=1, virtual clock, 5 rounds × 8 actors × 4 events, assertions A-G hold); restart-mid-combat drill (D-35, 6 tests); Rule 1 fixes in CombatConditionsRepo (double-start + duplicate-insert bugs found by first non-mocked integration test); 8 new tests; 728 default + 2 load-gated
- 2026-05-22: PHASE 4 COMPLETE — orchestrator + combat + load proof + closure; EXPLORE-01..07, COMBAT-01..08, COMBAT-12, OPS-03 satisfied; Phase 5 Riposte seam documented in AttackButton._maybe_surface_riposte (no-op); cursor advances to 05-reactions-self-host-polish
- 2026-05-22: Phase 5 Plan 01 COMPLETE — Wave 0 schema (consumed_in_round ALTER + pc_classes table), combat_outcome_parser, gameplay/reactions (eligibility + surface + handle_click), MonsterDriver (random target per D-B), RiposteButton.callback promoted from Phase 2 stub, _maybe_surface_riposte DELETED (D-A, atomic commit 1d2edc8); COMBAT-09 + COMBAT-10 functionally satisfied; PLAN-02-LOCK-SEAM marker at src/eldritch_dm/gameplay/reactions.py:280; 64 new tests; 798 default passing
- 2026-05-22: Phase 5 Plan 02 COMPLETE — gameplay/session_locks (namespaced asyncio.Lock registry), gameplay/riposte_sweeper (RESEARCH Pattern 4 background task), PLAN-02-LOCK-SEAM marker REPLACED by real session_locks.lock_for wrapper at reactions.py:345, conditional mark_expired SQL, setup_hook starts sweeper AFTER rehydration + close() stops sweeper FIRST in OPS-04 chain, OPS-01 resume drill (6 tests in test_riposte_restart.py, 0.20s wall-clock); COMBAT-11 + OPS-01 functionally satisfied; 28 net new tests; 826 default passing; zero new pip deps
- 2026-05-22: Phase 5 Plan 03 COMPLETE — src/eldritch_dm/bootstrap.py (3-stage preflight: schema → oMLX → MCP, exit codes 0/1/2/3 per RESEARCH Pattern 5, re-exports persistence.bootstrap for legacy callers); run.py (project-root entrypoint with --check-only/--no-preflight CLI flags, ELDRITCH_ALLOW_OFFLINE_START=1 escape hatch, SIGTERM→KeyboardInterrupt handler); .env.example audited (MCP_RATE_LIMIT_MS=200 added per RESEARCH Q9, OMLX_CACHE_STRATEGY orphan removed with explanatory comment); pyproject.toml [project.scripts] eldritch-dm + [project.urls] (D-23, D-25); docs/launchd.plist.example (com.shoemoney.eldritch-dm with dict-form KeepAlive + ThrottleInterval=10 per RESEARCH Pattern 7, DISCORD_TOKEN anti-pattern callout); docs/eldritch-dm.service.example (systemd user unit, HOST-07 best-effort); docs/dm20-troubleshooting.md + docs/character-ingest-formats.md (the two top self-hoster pain points); scripts/install-launchd.sh + uninstall-launchd.sh (idempotent, DRY_RUN safe); README expanded with First Session in 10 Minutes + Self-Hosting + Running as a Service + Known Limitations (Battle Master RAW only, public Riposte button, no DISCORD_TOKEN in plist) + License & Third-Party (PyMuPDF AGPL note); REQUIREMENTS.md COMBAT-09 wording corrected per D-C (Swashbuckler removed); all Phase 5 reqs ticked [x]; ROADMAP Phase 5 [x]; 29 net new tests across test_bootstrap_preflight.py + test_run_entrypoint.py; zero new pip deps; PHASE 5 COMPLETE; v1.0 milestone awaiting `/gsd:audit-milestone v1.0`
- 2026-05-22: v1.0 milestone audit ran → status `gaps_found` (2 BLOCKERS: G-1 ReadyButton no orchestrator start + G-2 SanitizerAuditRepo never instantiated; 2 WARNINGS: G-3 SAN-01 modal coverage + G-4 OPS-02 DM_OFFLINE warning). `.planning/v1.0-MILESTONE-AUDIT.md` written with full gap inventory.
- 2026-05-22: v1.0 audit BLOCKERS closed via hotfix series on `main` (3 atomic commits + 1 closure):
    - `4c15641` fix(audit-v1.0): G-1 — ReadyButton.callback all-ready branch now starts orchestrator via `bot.orchestrator.start_orchestrator_for_channel(...)`. RED→GREEN gate: tests/integration/test_lobby_to_exploration_flow.py.
    - `e22be5b` fix(audit-v1.0): G-2 — SanitizerAuditRepo wired into EldritchBot.setup_hook + DeclareActionModal.on_submit via `make_async_audit_callback`. SAN-05 now satisfied at runtime. RED→GREEN gate: tests/integration/test_sanitizer_audit_persistence.py (2 tests).
    - `25cb7a0` docs(audit-v1.0): ticked 11 implemented-but-unticked requirements (MCP-01..05, MCP-07, LOC-05, SAN-02..04, SAN-06).
    - Closure: this entry — audit doc status flipped `gaps_found` → `passed`, SAN-05 ticked. Test baseline: 864 passing / 873 collected (was 861 / 870). 7/7 import-linter contracts kept. G-3 + G-4 explicitly deferred to v1.1 per audit recommendation.
    - **Next action:** human re-runs `/gsd:complete-milestone v1.0`. `status: ready_for_audit` retained on STATE.md until that gate.

## Current Position

Phase: 28 (tuning) — EXECUTING
Plan: 1 of 2
Status: Executing Phase 28
Last activity: 2026-05-26 -- Phase 28 execution started

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
