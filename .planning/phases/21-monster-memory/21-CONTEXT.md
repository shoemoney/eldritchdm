---
phase: 21-monster-memory
milestone: v1.6
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - MEM-01 (bounded LRU class)
  - MEM-02 (slimmed-context augmentation w/ meta-knowledge guard)
  - MEM-03 (opt-in persistence + session-close cleanup)
---

# Phase 21 — Cross-round monster memory (CONTEXT)

## Mission

Give monsters session-level memory of prior combat rounds: who dealt them the most damage (DPS ranking), who concentrated on a high-impact spell, who they've internally flagged "dangerous." LLM sees DERIVED categorical flags (NOT raw HP/AC — preserves v1.1 D-57 meta-knowledge guard). Opt-in disk persistence survives bot restarts.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-157** | **`MonsterMemory` class** at `src/eldritch_dm/gameplay/monster_memory.py`. Bounded LRU per `(channel_id, session_id, monster_id)` key. Max 200 round-events per session (cap memory growth in long combats). Eviction is FIFO by round-number. | Per-monster scope (different monsters in same session each have their own memory) |
| **D-158** | **Tracked signals**:<br>(a) `damage_dealt_by[pc_id] -> int` (cumulative damage this PC dealt to THIS monster)<br>(b) `concentrating_on[pc_id] -> str | None` (spell name being concentrated on, e.g. "Hypnotic Pattern")<br>(c) `marked_dangerous: set[pc_id]` (INT≥10 monsters flag this on first hit; INT<10 never sets) | Three distinct combat-relevant signals; INT-gated marking matches v1.1 D-53 |
| **D-159** | **Meta-knowledge guard preserved (v1.1 D-57)**: slimmed PC context to LLM gains:<br>- `recent_damage_dealt: Literal["low", "moderate", "high"]` (NOT exact number — categorized into low<5, moderate 5-15, high>15)<br>- `concentrating_on: str | None` (spell name OK — that's observable on the battlefield)<br>- `marked_dangerous: bool`<br>RAW HP/AC NEVER added. Numerical damage NEVER passed verbatim. | Honors the contract; bands not numbers |
| **D-160** | **Opt-in persistence (MEM-03)**: `MONSTER_MEMORY_PERSIST=true` (default false) → snapshot to `~/.eldritch/monster_memory.sqlite`. Phase 17 cache pattern (aiosqlite WAL, single-writer). On `dm20__close_session` event hook, purge session rows. | Phase 17 pattern proven |
| **D-161** | **Schema**: `(channel_id TEXT, session_id TEXT, monster_id TEXT, snapshot_json TEXT, last_updated_ts INTEGER, PRIMARY KEY(channel_id, session_id, monster_id))`. `snapshot_json` is the full MonsterMemory state pydantic-serialized. | Composite PK; one row per active monster |
| **D-162** | **`SmartMonsterDriver.recall_memory(channel_id, session_id, monster_id)`** new method — returns the MonsterMemory instance (constructs empty if missing). Driver's `_pick_target` calls this and merges memory-derived flags into slimmed candidates BEFORE the LLM call. | Single integration point |
| **D-163** | **Memory update hook**: post-combat-resolution, the bot cog calls `monster_memory.observe_hit(pc_id, damage)` + `monster_memory.observe_concentration(pc_id, spell)` whenever the rules engine reports those events. SmartMonsterDriver does NOT observe — observations come from the rules engine (mechanical-honesty: bot doesn't infer damage). | Damage numbers flow ONLY through dm20-resolved events, never invented by bot/LLM |
| **D-164** | **Session-close hook**: subscribes to bot's session-lifecycle event (find existing channel/session-close path in `src/eldritch_dm/bot/cogs/lobby.py` or similar). On close → `monster_memory.purge_session(channel_id, session_id)`. | Memory bounded by session lifetime |
| **D-165** | **Fail-soft (same v1.1 D-58)**: any error reading/writing memory → empty memory → SmartMonsterDriver continues with v1.0-equivalent (no memory) context. Combat NEVER crashes. | Combat continuity sacred |
| **D-166** | **2 plans**: 21-01 = MonsterMemory class + slimmed-context augmentation. 21-02 = opt-in persistence + session-close cleanup hook. | ROADMAP plans section |

## Success Criteria
1. MonsterMemory class with bounded LRU (200/session); 3 tracked signals
2. INT-gated marked_dangerous (≥10 flags, <10 never)
3. Slimmed context adds 3 fields (recent_damage_dealt categorized, concentrating_on, marked_dangerous) — NO raw HP/AC
4. `observe_hit` / `observe_concentration` API for bot cog to call
5. Opt-in persistence (MEM-03) via Phase 17 cache pattern; off by default
6. Session-close hook purges session rows
7. Fail-soft on any error → empty memory → combat continues
8. ≥20 new tests; ruff + lint-imports clean
9. Existing smart_monster_driver/corpus tests still pass (zero regression)
