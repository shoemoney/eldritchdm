# EldritchDM — Requirements (v1.7 Integration & Polish)

**Milestone:** v1.7 Integration & Polish
**Goal:** Close v1.6's honest-gap follow-ups (MonsterMemory cog-wiring + AOE addendum prompt integration), set up cross-platform CI (Linux matrix to properly surface ocrmac skip behavior), ship bundled Phoenix dashboards for cache observability, and resolve the lingering atomicity-wording doc-fix.
**Total v1.7 requirements:** 6 across 2 categories.

---

## v1.7 Requirements

### WIRE — Cog wiring + prompt integration (Phase 23)

- [ ] **WIRE-01**: MonsterMemory cog-side integration — bot's combat cog (`src/eldritch_dm/bot/cogs/combat.py`) calls `monster_memory.observe_hit(pc_id, damage)` after every dm20-resolved damage event (the rules-engine callback path that already exists for damage resolution). NEVER invents damage; observes ONLY from rules-engine results. Same fail-soft contract (v1.1 D-58).
- [ ] **WIRE-02**: Session-close hook — lobby cog (`src/eldritch_dm/bot/cogs/lobby.py`) `/end_game` command (add if missing OR extend existing close path) calls `monster_memory_registry.purge_session(channel_id, session_id)`. Discord slash-command auto-confirms with "Session ended. Monster memory cleared."
- [ ] **WIRE-03**: AOE addendum live integration — SmartMonsterDriver's `_pick_target` prompt assembly conditionally appends the AOE addendum (versioned `aoe_addendum.txt` from Phase 20) when the candidate context's `available_actions` list contains 2+ AOE-kind entries. When 0 or 1 AOE actions: skip addendum (saves tokens, matches v1.1 slim-context discipline).

### POLISH — CI matrix + dashboards + doc-fix (Phase 24)

- [ ] **POLISH-01**: GitHub Actions CI matrix added at `.github/workflows/ci.yml` (or extend existing). Matrix: `{os: [macos-latest, ubuntu-latest], python: ["3.11"]}`. Linux runner verifies ocrmac/observability skip-gates behave correctly (Phase 14 FLAKE-01 fix). Mac runner verifies the full stack. Both run `uv run ruff check`, `uv run lint-imports`, `uv run pytest tests/ -q`.
- [ ] **POLISH-02**: Phoenix dashboard cache panels — bundled in `database/dashboards/` add `mcp_cache.json`, `character_cache.json`, `narrcache.json` following Phase 11's seed-dashboards.sh recipe (D-67). Each shows hit_rate + size + invalidations from the cache span attributes Phase 16/17/18 emit. Same our-format spec JSON pattern.
- [ ] **POLISH-03**: REQUIREMENTS.md atomicity doc-fix (v1.6 Phase 22 follow-up) + gsd-tools upstream issue write-up. Atomicity: update `.planning/milestones/v1.5-REQUIREMENTS.md` (line 62 in original) to match the implementation ("partial-wipe acceptable when caches are independent; log and continue"). Upstream: write `.planning/UPSTREAM-ISSUES.md` with the gsd-tools planner-template gap (SUMMARYs don't consistently emit `requirements_completed:` frontmatter) — flag for filing as a future gsd-tools issue.

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| WIRE-01 | 23 | v1.6 Phase 21 honest gap — MonsterMemory cog-side wiring |
| WIRE-02 | 23 | v1.6 Phase 21 honest gap — session-close hook |
| WIRE-03 | 23 | v1.6 Phase 20 — AOE addendum ships but isn't wired into live oracle |
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
