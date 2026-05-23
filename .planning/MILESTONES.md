# Milestones

## v1.0 MVP — Mechanically Honest AI Dungeon Master (Shipped: 2026-05-23)

**Tagline:** A local-first, self-hostable Discord bot that runs full D&D 5e games end-to-end with an AI Dungeon Master persona called **ShoeGPT**. Three-brain architecture splits narration (oMLX), rules (dm20 MCP), and Discord orchestration (this repo) so the AI can never hallucinate HP, miscalculate AC, or break turn order.

**Phases completed:** 5 phases · 16 plans · 873 tests (864 passing, 9 skipped) · 7/7 import-linter contracts kept · 71/73 requirements satisfied (97%) · 110 commits over 2 days

**Audit:** `passed` — see `milestones/v1.0-MILESTONE-AUDIT.md`

### Key accomplishments

- **Phase 1: MCP Client + Local State** — Async `MCPClient` to dm20 at oMLX `:8765/v1/mcp/execute` with httpx + tenacity retry + 3-strike circuit breaker; WAL SQLite with single-writer async queue + `BEGIN IMMEDIATE`; player-input sanitizer with 35-scenario adversarial corpus (control-token strip + sentinel wrap + 500-char cap + audit trail).
- **Phase 2: Discord Scaffold + Persistent Views** — `discord.py 2.7.1` bot with `DynamicItem` regex `custom_id`s for every persistent button, `EmbedCoalescer` (≤1 edit/sec/message), custom `EDM001` AST lint rule enforcing `await interaction.response.defer(thinking=True)` as the first line of every callback, kill-and-restart drill, OPS-04 graceful shutdown chain.
- **Phase 3: Lobby + Character Ingest** — `/start_game` provisions dm20 campaign + Claudmaster + Party Mode; `/load_adventure` for prebuilt campaigns; character ingest via D&D Beyond URL OR photo/PDF (ocrmac on macOS, easyocr fallback) routed through confidence-gated `CharacterReviewModal` / `CharacterEntryModal`.
- **Phase 4: Gameplay — Exploration + Combat** — `PartyModeOrchestrator` drives dm20's Party Mode queue, action batching (30s window), `CombatCog` with four turn-gated action buttons (Attack/Dodge/Cast/EndTurn) and `WeaponSelectModal`, dodge condition shim via new `combat_conditions` table, `MonsterTurnDriver` for monster turns; 8-actor virtual-clock load test proves coalescer + rate-limiter + edit-budget triad stays under Discord's 5/5s channel ceiling.
- **Phase 5: Riposte + Self-Host Polish** — Timed Riposte UI on the corrected RAW trigger path (monster-attack-misses-Battle-Master-Fighter); public-message persistent-View button with permission gating; `RiposteSweeper` background task sharing per-channel `SessionLocks` with `reactions.handle_riposte_click`; restart-survival drill proves button survives bot restart until `deadline_ts`; top-level `bootstrap.py` 3-stage preflight; `run.py` entrypoint; launchd plist + systemd unit + install/uninstall scripts; full README + 6 canonical docs (ARCHITECTURE/CONFIGURATION/GETTING-STARTED/DEVELOPMENT/TESTING/CONTRIBUTING).

### Architecture

- **Voice:** oMLX `:8765` running `ShoeGPT` (Gemma 4 4-bit) — narration only
- **Brain:** dm20 MCP server (97 tools — campaigns, characters, combat, Claudmaster autonomous DM, Party Mode HTTP/WS multiplayer) — owns all gameplay state
- **Orchestrator:** this repo — Discord adapter + small local WAL SQLite (`channel_sessions`, `persistent_views`, `riposte_timers`, `sanitizer_audit`, `combat_conditions`, `pc_classes`) — never computes game math

### Known deferred items

- **SAN-01** — Sanitizer not applied to `WeaponSelectModal` and `CharacterReviewModal` free-text fields (per-modal allow-list regex is a different defense). Deferred to v1.1.
- **OPS-02** — `WarningKind.DM_OFFLINE` defined but never dispatched on circuit-breaker open. Deferred to v1.1.
- **TD-1** — `eldritch_dm.bot.__main__` lacks `run.py`'s friendly missing-token error; canonical entrypoint is `run.py` so not a blocker. Deferred to v1.1.
- **TD-2** — 79 ruff errors across 23 pre-existing files (import ordering, `Optional` → `| None`). 43 auto-fixable. Deferred to v1.1 cleanup pass.
- **TD-3** — `pc_classes` ingest-backfill for self-hosters upgrading from Phase 4 (empty table until characters re-ingested). Documented in README "Known Limitations".

### Key decisions

| ID | Decision | Outcome |
|---|---|---|
| D-A | Delete Phase 4's `_maybe_surface_riposte` no-op seam (wrong trigger direction); add correct trigger on `MonsterDriver` | ✓ Good — preserved bisect history |
| D-B | Minimal random-target `MonsterDriver` for v1; smart Claudmaster targeting → v2 | ✓ Good — unblocked Riposte testability without scope creep |
| D-C | Strict RAW eligibility: Battle Master Fighter only (override CONTEXT.md D-04 which listed Swashbuckler) | ✓ Good — by-the-book accuracy; v2 YAML-config for homebrewers |
| D-26 | Made `Settings.discord_token` `Optional[str] = None` so preflight runs token-free | ✓ Good — enables the README's documented `bootstrap before token` quickstart flow |
| D-F | Sweeper share per-channel `SessionLocks` with `reactions.handle_riposte_click` | ✓ Good — eliminates click-at-deadline race |
| (Audit) | Public channel message + permission gating for Riposte button (NOT ephemeral) | ✓ Good — required for restart-survival (ephemerals die when interaction expires) |

### Milestone tag

`v1.0` — see `git tag -l v1.0` and `milestones/v1.0-ROADMAP.md` for the archived roadmap.

---
