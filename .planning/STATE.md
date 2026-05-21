---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in_progress
last_updated: "2026-05-21T23:15:00.000Z"
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 6
  percent: 0
---

# EldritchDM — State

**Last updated:** 2026-05-21 (Phase 2 Plan 01 complete — EldritchBot scaffold, 188 tests passing)
**Milestone:** v1.0
**Mode:** YOLO + autonomous loop via `/loop /gsd-autonomous`

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-21)

**Core value:** Mechanically honest AI DM, on Discord, fully local — bot never computes game math; all mechanical effects flow through dm20 MCP tools.
**Current focus:** Phase 1 — MCP Client + Local State

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
| 2 | Discord Scaffold + Persistent Views | 🔄 In Progress (1/3 plans complete) |
| 3 | Lobby + Character Ingest | ⚪ Not Started |
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

## Performance Metrics

| Phase | Plan | Duration (min) | Tasks | Files |
|-------|------|----------------|-------|-------|
| 01-mcp-client-local-state | 01 | 18 | 3 | 18 |
| 01-mcp-client-local-state | 02 | 45 | 5 | 15 |
| 01-mcp-client-local-state | 03 | 40 | 4 | 10 |
| 02-discord-scaffold-persistent-views | 01 | 15 | 3 | 9 |

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
