# Roadmap: EldritchDM

## Milestones

- ✅ **v1.0 MVP — Mechanically Honest AI Dungeon Master** — Phases 1-5 (shipped 2026-05-23) — see [`milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md)
- 📋 **v1.1 Polish** — gap closure + smart MonsterDriver (planned)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-5) — SHIPPED 2026-05-23</summary>

- [x] **Phase 1**: MCP Client + Local State (3/3 plans) — async MCP client to dm20 at oMLX; WAL SQLite with single-writer queue; sanitizer + 35-scenario adversarial corpus
- [x] **Phase 2**: Discord Scaffold + Persistent Views (3/3 plans) — discord.py 2.7.1 bot, DynamicItem regex custom_ids, EmbedCoalescer, EDM001 defer-discipline lint, kill-and-restart drill, OPS-04 graceful shutdown
- [x] **Phase 3**: Lobby + Character Ingest (3/3 plans) — `/start_game`, `/load_adventure`, DDB URL import, OCR/PDF pipeline (ocrmac + PyMuPDF), confidence-gated review modals
- [x] **Phase 4**: Gameplay — Exploration + Combat (3/3 plans) — PartyModeOrchestrator, action batching (30s window), CombatCog with 4 turn-gated buttons, dodge shim, MonsterTurnDriver, 8-actor virtual-clock load test
- [x] **Phase 5**: Reactions + Self-Host Polish (3/3 plans) — Riposte timed UI (Battle Master Fighter RAW), RiposteSweeper with shared SessionLocks, restart-survival drill, bootstrap.py preflight, run.py + launchd + systemd + install scripts

**Final stats:** 5 phases · 15 plans · 110 commits · 864 tests passing / 873 collected · 7/7 import-linter contracts kept · 71/73 requirements satisfied (97%) · 2 documented v1.1 deferrals (SAN-01, OPS-02)

**Tag:** `v1.0` · **Audit:** [`milestones/v1.0-MILESTONE-AUDIT.md`](milestones/v1.0-MILESTONE-AUDIT.md) (passed) · **Requirements archive:** [`milestones/v1.0-REQUIREMENTS.md`](milestones/v1.0-REQUIREMENTS.md)

</details>

### 📋 v1.1 Polish (Planned)

Tracking items from the v1.0 audit and post-ship feedback. Will be scoped into discrete phases by `/gsd:new-milestone`.

- [ ] **G-3 close**: Wire `sanitize_player_input` into `WeaponSelectModal` + `CharacterReviewModal` (SAN-01 completion)
- [ ] **G-4 close**: Catch `MCPCircuitOpen` and dispatch `WarningKind.DM_OFFLINE` ephemeral (OPS-02)
- [ ] **TD-1**: `eldritch_dm.bot.__main__` token-fix parity with `run.py`
- [ ] **TD-2**: Ruff cleanup pass (79 errors / 43 auto-fixable across 23 files)
- [ ] **TD-3**: `pc_classes` ingest-backfill script for Phase 4 → Phase 5 self-host upgrades
- [ ] **Smart MonsterDriver**: route monster targeting through Claudmaster (v1 ships random-target per D-B)
- [ ] **YAML Riposte eligibility**: configurable subclass list for homebrewers (v1 hardcodes Battle Master Fighter per D-C)

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|---|---|---|---|---|
| 1. MCP Client + Local State | v1.0 | 3/3 | ✅ Complete | 2026-05-21 |
| 2. Discord Scaffold + Persistent Views | v1.0 | 3/3 | ✅ Complete | 2026-05-21 |
| 3. Lobby + Character Ingest | v1.0 | 3/3 | ✅ Complete | 2026-05-21 |
| 4. Gameplay — Exploration + Combat | v1.0 | 3/3 | ✅ Complete | 2026-05-22 |
| 5. Reactions + Self-Host Polish | v1.0 | 3/3 | ✅ Complete | 2026-05-23 |

---
*Last revised: 2026-05-23 after v1.0 milestone close*
