# Roadmap: EldritchDM

**Created:** 2026-05-21
**Revised:** 2026-05-21 (MCP-hybrid pivot)
**Granularity:** standard (post-pivot — finer would over-fragment a focused 5-phase scope)
**Total phases:** 5
**Coverage:** ~55/55 v1 requirements mapped

## Core Value

Mechanically honest AI DM, on Discord, fully local. Bot never computes game math — all mechanical effects flow through `dm20` MCP tools.

## Phases

- [x] **Phase 1: MCP Client + Local State** — Async MCP wrapper to dm20 at oMLX, local Discord-state SQLite (WAL, repositories), sanitizer pipeline
- [x] **Phase 2: Discord Scaffold + Persistent Views** — discord.py bot, slash command tree, DynamicItem `custom_id`s, embed coalescer, defer discipline, restart-drill infrastructure
- [x] **Phase 3: Lobby + Character Ingest** — `/start_game` + `/load_adventure`, ready-check, D&D Beyond import, OCR/PDF pipeline for paper sheets, manual-review modal
- [x] **Phase 4: Gameplay — Exploration + Combat (Party Mode)** — Bind to dm20 Party Mode queue, action batching, combat embed, turn gatekeeping by Discord user_id, dodge, 8-player load proof
- [x] **Phase 5: Reactions + Self-Host Polish** — Timed Riposte button with restart-survival, README, `.env.example`, bootstrap, `run.py`, launchd recipe, full test suite

## Phase Details

### Phase 1: MCP Client + Local State
**Goal**: A correct, async MCP client to dm20 at oMLX, a small WAL-backed local SQLite for Discord-specific state, and the player-input sanitizer — the trio every later phase depends on, with zero Discord integration
**Mode:** infrastructure (no UI surface — pure plumbing)
**Depends on**: Nothing (foundation)
**Requirements**: MCP-01, MCP-02, MCP-03, MCP-04, MCP-05, MCP-06, MCP-07, LOC-01, LOC-02, LOC-03, LOC-04, LOC-05, LOC-06, SAN-01, SAN-02, SAN-03, SAN-04, SAN-05, SAN-06, OPS-02
**Success Criteria** (what must be TRUE):
  1. `MCPClient` posts to `:8765/v1/mcp/execute` with retry/timeout and returns typed results for every dm20 tool we use; errors are structured exceptions
  2. Health check + circuit breaker working: dm20 down → "DM is offline" mode; recovery automatic on restoration
  3. Local SQLite (`eldritch.sqlite3`) bootstraps four Discord-state tables (`channel_sessions`, `persistent_views`, `riposte_timers`, `sanitizer_audit`) with WAL + busy_timeout; all writes through a single writer task using `BEGIN IMMEDIATE`
  4. `sanitize_player_input` passes a ≥30-scenario adversarial corpus: strips control tokens, caps at 500 chars, wraps in `<player_action>` sentinels, audit row written when stripping occurs
  5. Unit tests for MCP client (httpx mocked), repositories (round-trip), and sanitizer (corpus) all pass; no `database is locked` under a 4-channel concurrent write stress test
**Plans**:
- [x] Plan 01: Foundation (pyproject, config, logging, WAL persistence, import-linter) — COMPLETE (73 tests, 18 files, 18 min)
- [x] Plan 02: Repositories + MCP Client (CRUD repos, MCPClient, health/circuit-breaker, typed tool wrappers) — COMPLETE (105 tests, 15 files, 45 min)
- [x] Plan 03: Sanitizer pipeline (sanitize_player_input, adversarial corpus, audit rows, stress test) — COMPLETE (177 tests, 10 files, 40 min)

### Phase 2: Discord Scaffold + Persistent Views
**Goal**: A running discord.py bot with slash command surface, embed renderers, and a persistent-view infrastructure that survives restart — proven by a kill-and-restart drill
**Mode:** infrastructure (UI plumbing, no gameplay yet)
**UI hint:** yes
**Depends on**: Phase 1 (uses `persistent_views` table and MCP client for health checks)
**Requirements**: BOT-01, BOT-02, BOT-03, BOT-04, BOT-05, BOT-06, BOT-07, BOT-08, OPS-04
**Success Criteria** (what must be TRUE):
  1. Bot connects to Discord, registers slash command tree, exposes `/ping` (returns MCP health), `/status` (current channel session)
  2. Every interaction callback's first line is `await interaction.response.defer(thinking=True)` (ruff/pre-commit rule enforced; CI fails on violation)
  3. Embed renderers (`lobby_embed`, `room_embed`, `combat_embed`, `character_confirm_embed`) stable shape, all editable via the coalescer (≤1 edit/sec/message)
  4. `DynamicItem` `custom_id` templates for every persistent button class (`endturn`, `riposte`, `ready`, `declare_action`); on `setup_hook` bot reads `persistent_views` rows and `bot.add_view(view, message_id=...)`
  5. Kill-and-restart drill: bot killed while a test message has buttons → process restarts → buttons still functional (matching `custom_id` dispatches to handler with state restored from DB)
**Plans**:
- [x] 01-PLAN-bot-scaffold.md — EldritchBot subclass, /ping + /status diagnostics cog, lifecycle tests, bot/ import-linter contract — COMPLETE (11 tests, 9 files, 15 min)
- [x] 02-PLAN-embeds-and-views.md — 4 embed renderers (snapshot-tested), 4 DynamicItem subclasses (regex custom_ids), ephemeral warning helper — COMPLETE (67 tests, 11 files, 28 min)
- [x] 03-PLAN-coalescer-rehydration-restart.md — EmbedCoalescer, setup_hook persistent-view rehydration, EDM001 lint, kill-and-restart drill, OPS-04 graceful shutdown, Phase 2 SUMMARY — COMPLETE (49 tests, 13 files, 90 min)

### Phase 3: Lobby + Character Ingest
**Goal**: Players can start a session in any channel and load characters two ways: D&D Beyond URL (one MCP call) or photo/PDF of their sheet (OCR/PDF → schema-translation → manual review modal)
**Mode:** mvp (first user-visible gameplay surface)
**UI hint:** yes
**Depends on**: Phase 1 (MCP + sanitizer + DB), Phase 2 (persistent views)
**Requirements**: LOBBY-01, LOBBY-02, LOBBY-03, LOBBY-04, INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06, INGEST-07, INGEST-08, INGEST-09, INGEST-10, INGEST-11
**Success Criteria** (what must be TRUE):
  1. `/start_game` creates a dm20 campaign + Claudmaster session + Party Mode server, records the trio in `channel_sessions`, and posts a lobby embed with QR-code invite + Discord-native ready button
  2. `/load_adventure CoS` (and similar IDs) successfully loads a prebuilt adventure into the active campaign via `dm20__load_adventure`
  3. `/upload_character_url <ddb>` round-trips: DDB URL → dm20-imported character → confirm embed posted in <8s
  4. `/upload_character_file` with PNG/JPG/PDF: OCR (ocrmac on macOS) → oMLX schema translate → manual-review modal → DM/player confirm → `dm20__create_character` or `update_character` in <8s for standard sheets
  5. Confidence gate works: forced-low-confidence test triggers manual-entry modal as the first-class path; uploads restricted to invoking user or DM; confirmations are ephemeral
  6. All-ready button transitions session to EXPLORATION state (recorded in `channel_sessions`, signaled to Claudmaster via state update)
**Plans**:
- [x] 01-PLAN-lobby-and-cogs.md — LobbyCog (/start_game, /load_adventure, ReadyButton, lobby embed + QR), ChannelSessionRepo wiring, party_mode_parser, permissions gate — COMPLETE (127 tests, 16 files, 120 min)
- [x] 02-PLAN-ingest-pipeline.md — OCR/PDF ingest pipeline (ocrmac+easyocr+PyMuPDF), oMLX schema translation, IngestResult with confidence score, pydantic CharacterSheet validation — COMPLETE (82 tests, 14 files, 90 min)
- [x] 03-PLAN-ingest-cogs-and-modals.md — IngestCog (3 slash commands), CharacterReviewModal + CharacterEntryModal (5-component cap), QR helper extraction, Phase 3 integration smoke, Phase 3 closure — COMPLETE (55 tests, 12 files, 85 min)

### Phase 4: Gameplay — Exploration + Combat (Party Mode)
**Goal**: A functional play loop — players declare actions in modals, ShoeGPT narrates via dm20's Party Mode queue, combat enforces turn order by Discord user_id, and the 8-player load test passes without Discord rate-limit errors
**Mode:** mvp (the actual game)
**UI hint:** yes
**Depends on**: Phase 3 (lobby + characters exist)
**Requirements**: EXPLORE-01, EXPLORE-02, EXPLORE-03, EXPLORE-04, EXPLORE-05, EXPLORE-06, EXPLORE-07, COMBAT-01, COMBAT-02, COMBAT-03, COMBAT-04, COMBAT-05, COMBAT-06, COMBAT-07, COMBAT-08, COMBAT-12, OPS-03
**Success Criteria** (what must be TRUE):
  1. EXPLORATION loop: `[ 💬 Declare Action ]` modal → sanitized text → posted as Party Mode action → bot pops via `dm20__party_pop_action`, calls `party_thinking`, optionally `party_get_prefetch`, awaits Claudmaster narrative, posts via `party_resolve_action` and renders in Discord
  2. Action batching: when multiple players submit within a 30s window, narratives are coalesced into one batched response (verified by a 4-player synthetic test)
  3. Combat: dm20 state transition to COMBAT renders the combat embed with initiative order, HP/AC, conditions; action buttons render with `custom_id` containing the current actor's Discord user_id
  4. Turn gatekeeping verified: a non-active player clicking an action button receives an ephemeral "❌ Not your turn"; the active player's click dispatches to dm20
  5. Attack flow: weapon select modal → `dm20__combat_action(action="attack", weapon=..., target=...)` → narrative back via party mode; Dodge calls `apply_effect`; End Turn calls `next_turn`
  6. 8-player load test: synthetic 8-actor combat with 4× embed updates/round runs for 5 rounds with zero Discord 429 errors and zero `database is locked`
**Plans**:
- [x] 01-PLAN-orchestrator-and-exploration.md — PartyModeOrchestrator (poll loop, state-change dispatch), ExplorationCog (DeclareAction modal, coalescer integration, /status diagnostics), enriched exploration embed — COMPLETE (58 tests, 13 files, 90 min)
- [x] 02-PLAN-combat-cog-and-turn-gatekeeping.md — combat_conditions table, CombatCog (state-change wiring, embed refresh), AttackButton + DodgeButton + EndTurnButton + CastSpellButton (4 persistent combat buttons), WeaponSelectModal, TurnGatekeeper, dodge shim, asyncio.gather state dispatch, COMBAT cadence=1 — COMPLETE (257 tests, 17 files, 180 min)
- [x] 03-PLAN-load-test-and-closure.md — 8-actor load test (RUN_LOAD=1, virtual clock), restart-mid-combat drill (D-35), Phase 4 closure (REQUIREMENTS [x], ROADMAP [x], STATE cursor advance) — COMPLETE (8 tests, 5 files, 90 min)

### Phase 5: Reactions + Self-Host Polish
**Goal**: The Riposte timed UI is functional and survives restart; the project is documented, tested, and self-hostable end-to-end by a user with oMLX/dm20 already running
**Mode:** mvp (closes v1)
**UI hint:** yes
**Depends on**: Phase 4 (combat works)
**Requirements**: COMBAT-09, COMBAT-10, COMBAT-11, HOST-01, HOST-02, HOST-03, HOST-04, HOST-05, HOST-06, HOST-07, HOST-08, OPS-01
**Success Criteria** (what must be TRUE):
  1. Riposte detection: when a monster's attack misses an eligible PC (**Battle Master Fighter RAW only** per D-C; Swashbuckler removed) with `has_reaction=true`, an 8s timed button appears for that PC only; `riposte_timers` row created with `deadline_ts` ✓ delivered by Plan 01
  2. Riposte execution: click → `dm20__combat_action(reaction=true, weapon=primary)` (or documented shim); only target player can click; expiry cleans the button ✓ delivered by Plan 01
  3. Restart-survival drill: kill bot during an active riposte window, restart, button is still clickable until its `deadline_ts`; expired timers auto-cleaned on restart ✓ delivered by Plan 02
  4. README walks a new user from "I have oMLX + dm20 + a Discord bot token" to "I am playing D&D in 10 minutes"; `.env.example` documents every var; `bootstrap.py` provisions the local DB and pings oMLX ✓ delivered by Plan 03
  5. Full test suite green: MCP-client mocked tests, sanitizer adversarial corpus, repository round-trip, persistent-view restart drill, 4-player concurrent write stress, 8-player combat load — all pass; CI lint enforces defer discipline ✓ delivered cumulatively across Plans 01+02+03
**Plans**:
- [x] 01-PLAN-riposte-and-monster-driver.md — Wave 0 schema (consumed_in_round ALTER + pc_classes), combat_outcome_parser, gameplay/reactions (eligibility + surface + handle_click + PLAN-02-LOCK-SEAM marker), MonsterDriver (random target per D-B), RiposteButton.callback promoted to real, _maybe_surface_riposte DELETED (D-A); COMBAT-09 + COMBAT-10 functionally satisfied; 64 new tests, 798 total — COMPLETE (70 min)
- [x] 02-PLAN-sweeper-and-restart-survival.md — SessionLocks namespaced registry (gameplay/session_locks.py), RiposteSweeper background task (gameplay/riposte_sweeper.py — RESEARCH Pattern 4), PLAN-02-LOCK-SEAM marker REPLACED by real session_locks.lock_for wrapper at reactions.py:345, conditional mark_expired SQL, setup_hook orders sweeper AFTER rehydration + close() stops sweeper FIRST in OPS-04 chain, 6-test OPS-01 resume drill (test_riposte_restart.py); COMBAT-11 + OPS-01 functionally satisfied; 28 net new tests, 826 total — COMPLETE (35 min)
- [x] 03-PLAN-self-host-polish-and-closure.md — src/eldritch_dm/bootstrap.py (3-stage preflight, exit codes 0/1/2/3 ✓ HOST-03), run.py (--check-only, --no-preflight, SIGTERM handler ✓ HOST-04), .env.example audit (MCP_RATE_LIMIT_MS added; OMLX_CACHE_STRATEGY orphan resolved ✓ HOST-02), pyproject [project.scripts] + [project.urls] ✓ HOST-05, docs/launchd.plist.example + scripts/install-launchd.sh + uninstall ✓ HOST-08, docs/eldritch-dm.service.example (Linux best-effort ✓ HOST-07), docs/dm20-troubleshooting.md + docs/character-ingest-formats.md, README expansion (First Session in 10 Minutes + Troubleshooting + Self-Hosting + Running as a Service + Known Limitations + License & Third-Party AGPL note ✓ HOST-01), REQUIREMENTS.md COMBAT-09 wording corrected per D-C, all Phase 5 reqs ticked [x]; 29 net new tests — COMPLETE

## Traceability

Mapping every v1 requirement to its phase. (To be populated by `gsd-roadmapper` or hand-verified before Phase 1 plan-phase.)

See `.planning/REQUIREMENTS.md` § Traceability — will be populated alongside this roadmap revision.

---
*Roadmap created: 2026-05-21*
*Last revised: 2026-05-21 after MCP-hybrid pivot (11→5 phases, 87→~55 requirements)*
