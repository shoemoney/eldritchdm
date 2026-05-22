---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in_progress
last_updated: "2026-05-22T01:08:33Z"
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 9
  completed_plans: 9
  percent: 60
---

# EldritchDM — State

**Last updated:** 2026-05-22 (Phase 3 COMPLETE — IngestCog + modals + QR + smoke test, 469 tests passing)
**Milestone:** v1.0
**Mode:** YOLO + autonomous loop via `/loop /gsd-autonomous`

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-21)

**Core value:** Mechanically honest AI DM, on Discord, fully local — bot never computes game math; all mechanical effects flow through dm20 MCP tools.
**Current focus:** Phase 4 — Gameplay — Exploration + Combat (Party Mode)

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
| 4 | Gameplay — Exploration + Combat (Party Mode) | ⚪ Not Started |
| 5 | Reactions + Self-Host Polish | ⚪ Not Started |

## Blockers / Concerns

- [ ] Verify dm20 supports concurrent multi-campaign sessions in one process (Phase 1 spike)
- [ ] Verify dm20 has a "dodging" condition / `apply_effect` semantics suitable for our Dodge action (Phase 4)
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
