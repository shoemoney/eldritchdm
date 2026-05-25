---
phase: 23-cog-wiring
milestone: v1.7
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - WIRE-01 (MonsterMemory observe_hit cog wiring)
  - WIRE-02 (session-close hook → memory purge)
  - WIRE-03 (AOE addendum live prompt assembly)
---

# Phase 23 — Honest-gap closure (cog-wiring + AOE prompt integration) — CONTEXT

## Mission

Close two honest-gaps from v1.6:
1. MonsterMemory ships with `observe_hit` / `observe_concentration` / `purge_session` APIs but no cog-side wiring (Phase 21 documented gap)
2. AOE addendum ships as a versioned prompt file but isn't injected into SmartMonsterDriver's live oracle prompt (Phase 20 ship-but-not-wired)

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-176** | **`observe_hit` call site**: bot's combat cog (`src/eldritch_dm/bot/cogs/combat.py`) after dm20 resolves an attack and returns a damage value. Find the post-resolution callback path (likely an `on_resolved_combat` or similar handler). Bot calls `monster_memory_registry.observe_hit(channel_id, session_id, monster_id, pc_id, damage)`. NEVER invents damage — observes ONLY the dm20-resolved value. | Mechanical-honesty contract (v1.0 core) |
| **D-177** | **observe_concentration call site**: when a PC casts a concentration spell, dm20 emits a state-change event. Bot's combat cog (or spell-casting handler — find via grep for "concentration" or "concentrating") calls `monster_memory_registry.observe_concentration(channel_id, session_id, pc_id, spell_name)`. | Same observation-only pattern |
| **D-178** | **Session-close hook**: lobby cog gains `/end_game` slash command (or extends existing close path — investigate during plan). On success: (a) dm20__close_session called, (b) `monster_memory_registry.purge_session(channel_id, session_id)` called, (c) ephemeral confirmation embed. If `/end_game` already exists, extend its handler. | Single canonical session-close path |
| **D-179** | **Fail-soft (v1.1 D-58)**: ANY error in the new observe_hit/observe_concentration/purge_session calls → log + continue. Combat NEVER crashes because memory observation failed. | Same contract as v1.5 cache wiring |
| **D-180** | **AOE addendum conditional injection (WIRE-03)**: in SmartMonsterDriver's `_pick_target`, the system prompt assembly inspects the candidate context's `available_actions: list[ActionDescriptor]`. If `sum(1 for a in actions if a.kind in {"aoe","cone","breath"}) >= 2` → append addendum text from `aoe_addendum.txt`. Else: skip addendum (saves tokens). | Bounded slim-context discipline (Phase 10 D-57) |
| **D-181** | **Addendum versioning**: read `aoe-addendum-version: X.Y.Z` from the addendum file's header at startup, surface to OTel span attributes when active (`eldritch.aoe.addendum_version`). Lets operators see which version influenced a given decision. | Phase 11 observability tie-in |
| **D-182** | **Module touch summary**:<br>- `src/eldritch_dm/bot/cogs/combat.py` — add `observe_hit` + `observe_concentration` call sites in the resolved-event handler<br>- `src/eldritch_dm/bot/cogs/lobby.py` — `/end_game` command (new or extended)<br>- `src/eldritch_dm/gameplay/smart_monster_driver.py` — `_pick_target` prompt assembly extends with conditional addendum injection + OTel attribute<br>- `src/eldritch_dm/gameplay/prompts/aoe_addendum.py` — gains `get_addendum_version()` helper (read header) | Three focused module touches |
| **D-183** | **Test surface**:<br>- WIRE-01: cog test that simulates a resolved-combat event → asserts `monster_memory_registry.observe_hit` was called with the dm20-resolved damage<br>- WIRE-02: cog test that triggers `/end_game` → asserts `purge_session` was called<br>- WIRE-03: driver test with 2+ AOE actions → assert addendum text in prompt; 0/1 AOE → assert NOT in prompt; addendum_version attribute set on span when present | Each requirement individually verified |
| **D-184** | **Zero regression contract**: existing 285+ tests across smart_monster_driver / monster_memory / lobby / combat cogs MUST still pass. Cog tests may use mocked dm20 events as in Phase 5/10. | Preserve v1.0-v1.6 test surface |
| **D-185** | **2 plans**: 23-01 = MonsterMemory cog wiring (WIRE-01 + WIRE-02). 23-02 = AOE addendum live prompt assembly (WIRE-03). | ROADMAP plans section |

## Implementation Sketch

**Plan 01 (23-01):** Find dm20 resolved-event handler in combat cog. Add `observe_hit` call (fail-soft). Same for spell-cast handler (concentration). Lobby cog: investigate `/end_game` — if exists, extend; if not, add minimal slash command (uses lobby cog's existing session-state to get channel/session ids). Tests: 5-8 cog tests covering both wirings.

**Plan 02 (23-02):** SmartMonsterDriver `_pick_target` reads `available_actions`, counts AOE-kind. If ≥2, loads addendum text + version via `get_addendum_version()`, appends to system prompt, sets OTel span attribute. Tests: 4-6 driver tests covering injection on/off + version attribute + addendum-file-missing fail-soft path.

## Success Criteria
1. Combat cog calls observe_hit on resolved-damage event (mocked dm20)
2. Combat cog calls observe_concentration on concentration-cast event (mocked dm20)
3. Lobby cog `/end_game` triggers `purge_session` for the channel's active session
4. SmartMonsterDriver conditionally injects AOE addendum when ≥2 AOE actions present
5. addendum_version OTel attribute set when addendum is active
6. ≥10 new tests; ruff + lint-imports clean
7. Existing 285+ tests still pass (zero regression)
8. All new code fail-soft per v1.1 D-58
