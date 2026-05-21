---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in_progress
last_updated: "2026-05-21T23:55:00Z"
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 3
  completed_plans: 3
  percent: 33
current_phase: "02-discord-scaffold"
current_plan: "02-01"
---

# EldritchDM — State

**Last updated:** 2026-05-21 (Phase 1 complete — all 3 plans done, 177 tests passing)
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
| 2 | Discord Scaffold + Persistent Views | ⚪ Not Started |
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

## Performance Metrics

| Phase | Plan | Duration (min) | Tasks | Files |
|-------|------|----------------|-------|-------|
| 01-mcp-client-local-state | 01 | 18 | 3 | 18 |
| 01-mcp-client-local-state | 02 | 45 | 5 | 15 |
| 01-mcp-client-local-state | 03 | 40 | 4 | 10 |

## Recent History

- 2026-05-21: Project init → research → roadmap (11 phases, 87 reqs)
- 2026-05-21: Discovered 116-tool MCP toolbox via `ddmcpskills.md`
- 2026-05-21: Pivot decision: hybrid (dm20 for content, ours for Discord state), Party Mode binding, Riposte stays, OCR/PDF stays
- 2026-05-21: Roadmap revised 11 → 5 phases; requirements 87 → ~55
- 2026-05-21: Phase 1 Plan 01 (foundation) complete — pyproject.toml, config, logging, WAL persistence, import-linter; 73 tests passing
- 2026-05-21: Phase 1 Plan 02 (repositories+MCP) complete — 4 repos, MCPClient, circuit breaker, 28 tool wrappers; 105 tests passing
- 2026-05-21: Phase 1 Plan 03 (sanitizer+stress) complete — sanitizer, 34-case corpus, 4-channel stress test, integration smoke; 177 tests passing
- 2026-05-21: Phase 1 COMPLETE — all 3 plans done, pre-commit ruff hooks, import-linter 4 contracts KEPT
