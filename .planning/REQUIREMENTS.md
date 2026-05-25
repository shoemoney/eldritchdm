# EldritchDM — Requirements (v1.7 Integration & Polish)

**Milestone:** v1.7 Integration & Polish
**Goal:** Close v1.6's honest-gap follow-ups (MonsterMemory cog-wiring + AOE addendum prompt integration), set up cross-platform CI (Linux matrix to properly surface ocrmac skip behavior), ship bundled Phoenix dashboards for cache observability, and resolve the lingering atomicity-wording doc-fix.
**Total v1.7 requirements:** 6 across 2 categories.

---

## v1.7 Requirements

### WIRE — Cog wiring + prompt integration (Phase 23)

- [ ] **WIRE-01** *(deferred — blocked on dm20 structured damage-event surface; see `.planning/phases/23-cog-wiring/23-HALT-REPORT.md`)*: MonsterMemory cog-side integration — bot's combat cog (`src/eldritch_dm/bot/cogs/combat.py`) calls `monster_memory.observe_hit(pc_id, damage)` after every dm20-resolved damage event. **Blocker:** dm20 returns markdown narration (not a structured `(attacker, target, damage)` event); parsing damage out of LLM text would violate the mechanical-honesty integrity rule (D-176 / EldritchDM core constraint). The concentration observation half (originally D-177) is blocked by the same missing event surface. Re-open after dm20 ships a post-resolve event emission.
- [x] **WIRE-02**: Session-close hook — lobby cog (`src/eldritch_dm/bot/cogs/lobby.py`) `/end_game` command calls `monster_memory_registry.purge_session(channel_id, session_id)`. Discord slash-command confirms ephemerally with "Session Ended … Monster memory cleared (N entries) … Channel returned to LOBBY." Closed by Phase 23-01.
- [x] **WIRE-03**: AOE addendum live integration — SmartMonsterDriver's `_pick_target` prompt assembly conditionally appends the AOE addendum (versioned `aoe_addendum.txt` from Phase 20) when the candidate context's `available_actions` list contains 2+ AOE-kind entries. When 0 or 1 AOE actions: skip addendum (saves tokens, matches v1.1 slim-context discipline). Closed by Phase 23-02.

### POLISH — CI matrix + dashboards + doc-fix (Phase 24)

- [x] **POLISH-01**: GitHub Actions CI matrix added at `.github/workflows/ci.yml` (or extend existing). Matrix: `{os: [macos-latest, ubuntu-latest], python: ["3.11"]}`. Linux runner verifies ocrmac/observability skip-gates behave correctly (Phase 14 FLAKE-01 fix). Mac runner verifies the full stack. Both run `uv run ruff check`, `uv run lint-imports`, `uv run pytest tests/ -q`. Closed by Phase 24-01.
- [x] **POLISH-02**: Phoenix dashboard cache panels — bundled in `database/dashboards/` add `mcp_cache.json`, `character_cache.json`, `narrcache.json` following Phase 11's seed-dashboards.sh recipe (D-67). Each shows hit_rate + size + invalidations from the cache span attributes Phase 16/17/18 emit. Same our-format spec JSON pattern. Closed by Phase 24-02.
- [x] **POLISH-03**: REQUIREMENTS.md atomicity doc-fix (v1.6 Phase 22 follow-up) + gsd-tools upstream issue write-up. Atomicity: update `.planning/milestones/v1.6-REQUIREMENTS.md` line 64 (NOT v1.5 — CONTEXT.md typo; the wording lives in v1.6 because OPQOL-03 is a v1.6 phase) to match the implementation ("partial-wipe acceptable when caches are independent; log and continue"). Upstream: write `.planning/UPSTREAM-ISSUES.md` with the gsd-tools planner-template gap (SUMMARYs don't consistently emit `requirements_completed:` frontmatter) — flag for filing as a future gsd-tools issue. Closed by Phase 24-02.

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| WIRE-01 | 23 (deferred) | v1.6 Phase 21 honest gap — blocked on dm20 damage-event surface (see 23-HALT-REPORT.md) |
| WIRE-02 | 23 | v1.6 Phase 21 honest gap — session-close hook (closed by 23-01) |
| WIRE-03 | 23 | v1.6 Phase 20 — AOE addendum ships but isn't wired into live oracle (closed by 23-02) |
| POLISH-01 | 24 | v1.3 carried — cross-platform CI matrix |
| POLISH-02 | 24 | v1.5 carried — Phoenix dashboard cache panels (mentioned in v1.4 PROJECT.md candidates) |
| POLISH-03 | 24 | v1.6 Phase 22 doc-fix reconciliation + v1.3 audit gsd-tools template gap |

## Mode Constraints

- WIRE-01: bot cog observes damage ONLY from dm20-resolved events. Never infers/invents damage. Mechanical-honesty contract preserved.
- WIRE-02: session-close is the ONLY trigger for memory purge (no time-based or LRU-based eviction at session level — only at round-event level per Phase 21 D-157 cap).
- WIRE-03: addendum injection is BOUNDED (skip when ≤1 AOE actions in monster's actions list — saves tokens; matches Phase 10 D-57 slim-context discipline).
- POLISH-01: Linux runner MUST skip ocrmac-dependent tests cleanly (Phase 14 FLAKE-01 fix). Skip-message must be unambiguous so operators know to install `[mac-ocr]` extras for full coverage.
- POLISH-02: Dashboards use OUR-FORMAT JSON spec (Phase 11 D-67a deviation reasoning), NOT Phoenix-native dashboard JSON (schema unstable per Phase 11).
- POLISH-03: doc-fix only — no behavior change. UPSTREAM-ISSUES.md is a backlog file for future filings; not a v1.7 SHIP requirement.
