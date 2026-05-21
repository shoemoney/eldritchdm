# EldritchDM — State

**Last updated:** 2026-05-21 (post-MCP-pivot roadmap revision)
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
| 1 | MCP Client + Local State | 🔵 In Progress (CONTEXT.md pending — old persistence-foundation CONTEXT.md superseded) |
| 2 | Discord Scaffold + Persistent Views | ⚪ Not Started |
| 3 | Lobby + Character Ingest | ⚪ Not Started |
| 4 | Gameplay — Exploration + Combat (Party Mode) | ⚪ Not Started |
| 5 | Reactions + Self-Host Polish | ⚪ Not Started |

## Blockers / Concerns

- [ ] Verify dm20 supports concurrent multi-campaign sessions in one process (Phase 1 spike)
- [ ] Verify dm20 has a "dodging" condition / `apply_effect` semantics suitable for our Dodge action (Phase 4)
- [ ] Verify dm20 models reactions (`has_reaction`) natively; if not, design the shim (Phase 5)
- [ ] Confirm `dm20__party_pop_action` returns immediately when queue empty (we may need polling cadence vs WS)

## Recent History

- 2026-05-21: Project init → research → roadmap (11 phases, 87 reqs)
- 2026-05-21: Discovered 116-tool MCP toolbox via `ddmcpskills.md`
- 2026-05-21: Pivot decision: hybrid (dm20 for content, ours for Discord state), Party Mode binding, Riposte stays, OCR/PDF stays
- 2026-05-21: Roadmap revised 11 → 5 phases; requirements 87 → ~55
