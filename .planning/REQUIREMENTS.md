# EldritchDM — Requirements (v1.6 UX/Feature Expansion)

**Milestone:** v1.6 UX/Feature Expansion
**Goal:** Close the deferred UX + feature items from v1.1 (Phase 10 deferrals) and v1.5 (operator QoL). Extend SmartMonsterDriver to support AOE targeting + cross-round memory; surface "thinking" state in the player-visible Discord embed; deliver operator quality-of-life (hot-reload eligibility, Discord DM on budget breach, Phase 16↔17 invalidation wire).
**Total v1.6 requirements:** 10 across 4 categories.

---

## v1.6 Requirements

### STREAM — Streaming "monster is thinking" embed (Phase 19)

- [ ] **STREAM-01**: During SmartMonsterDriver oracle call (max 1500ms per v1.1 D-54), the combat embed updates with a "🤔 The {monster_name} is sizing up the party..." indicator. Embed is updated via discord.py's embed coalescer (Phase 2 — already rate-limit-aware at ≤1 edit/sec/message). NO new dependencies.
- [ ] **STREAM-02**: Fallback path — when oracle call falls back to random (timeout, refusal, hallucination), embed transitions to the resolved action WITHOUT exposing the fallback to players (no "the AI failed" message — just the chosen target). Preserves player immersion. Structured log entry captures fallback reason for operator.
- [ ] **STREAM-03**: Honors `STREAM_ENABLED` env var (default true). When false, embed updates only after the resolved choice (v1.5 behavior). Player-visible UX latency capped at the existing 2s embed-stall budget.

### AOE — AOE / multi-target tactic selection (Phase 20)

- [ ] **AOE-01**: `MonsterTacticChoice` pydantic model extended with `target_pc_ids: list[str]` (in addition to current `target_pc_id`). Single-target tactics emit a 1-element list; AOE/breath/cone tactics emit 2+. Post-parse validator ensures ALL ids are in the candidate set; hallucinated → fallback (same fail-soft path as v1.1 D-58).
- [ ] **AOE-02**: SmartMonsterDriver system prompt extended with explicit AOE tactic enumeration (breath weapons, AOE spells, multi-attack). Monster's available actions surfaced to the LLM via the slimmed candidate context (D-57 expanded to include `available_actions: list[ActionDescriptor]`). Tests cover dragon breath, fireball-style spells, multi-attack.
- [ ] **AOE-03**: New corpus entries (10 scenarios) in `tests/gameplay/test_monster_driver_corpus.py` covering AOE-appropriate situations (clustered PCs, line formations, single-target-only-monsters-rejecting-AOE). Fail-soft on any hallucination — combat continues with random single-target.

### MEM — Cross-round monster memory (Phase 21)

- [ ] **MEM-01**: `MonsterMemory` class — bounded LRU per `(channel_id, session_id, monster_id)` tracks: who hit this monster most (DPS ranking), who concentrated on what spell (concentration map), who's flagged "dangerous" by INT-derived heuristic. Bounded to 200 rounds per session to cap memory growth.
- [ ] **MEM-02**: Memory exposed to SmartMonsterDriver via the existing slimmed candidate context — augments each PC entry with `recent_damage_dealt: int`, `concentrating_on: str | None`, `marked_dangerous: bool`. LLM sees this but doesn't get exact HP/AC (D-57 meta-knowledge guard preserved). Tests verify the LLM uses memory to bias targeting toward "the wizard who keeps casting Hypnotic Pattern."
- [ ] **MEM-03**: Memory persistence — opt-in via `MONSTER_MEMORY_PERSIST=true` (default false). When persistent, memory snapshots to `~/.eldritch/monster_memory.sqlite` (Phase 17 cache pattern). Survives bot restart. Cleared when session ends (`dm20__close_session` event hook).

### OPQOL — Operator quality-of-life bundle (Phase 22)

- [ ] **OPQOL-01**: Hot-reload `eligibility.yaml` — Phase 8's loader gains a `reload()` method + file-mtime watcher background task (60s poll). When file changes, reload + emit structured log. NO bot restart needed. Failure case: bad YAML → keep last-known-good + log error (fail-soft, matches Phase 8 fail-soft contract).
- [ ] **OPQOL-02**: Discord DM-to-owner on budget breach — Phase 13's degraded-mode trigger sends a Discord DM to `DISCORD_OWNER_ID` (env, optional) when: (a) ELDRITCH_DAILY_LLM_BUDGET_USD breached, (b) degraded mode entered, (c) degraded mode exited (recovery). Rate-limited 1 DM per event-type per hour. If `DISCORD_OWNER_ID` unset → log-only (today's behavior).
- [ ] **OPQOL-03**: Wire Phase 16's schema-version poller to fire Phase 17's character_cache invalidation (the carried v1.5 connect-the-dots item). When dm20 schema bumps, BOTH caches wipe atomically. Integration test verifies both layers respond.

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| STREAM-01 | 19 | v1.1 Phase 10 "streaming monster thinking embed" deferral |
| STREAM-02 | 19 | Phase 10 D-58 fail-soft requirement extended to UX |
| STREAM-03 | 19 | Operator opt-out + 2s embed-stall budget |
| AOE-01 | 20 | v1.1 Phase 10 "AOE/multi-target tactic selection" deferral |
| AOE-02 | 20 | Same; prompt + context-window extension |
| AOE-03 | 20 | Adversarial corpus expansion (10 new scenarios) |
| MEM-01 | 21 | v1.1 Phase 10 "cross-round monster memory" deferral |
| MEM-02 | 21 | LLM context tie-in; meta-knowledge guard preserved |
| MEM-03 | 21 | Persistence pattern (mirrors Phase 17 cache) |
| OPQOL-01 | 22 | v1.1 Phase 8 "hot-reload eligibility.yaml" deferral |
| OPQOL-02 | 22 | v1.2 Phase 13 "Discord DM-to-owner on budget breach" deferral |
| OPQOL-03 | 22 | v1.5 cross-phase invalidation connect-the-dots |

## Mode Constraints

- All extensions to SmartMonsterDriver preserve v1.1 D-58 fail-soft contract: ANY exception → fallback to random; combat orchestrator never sees an exception.
- Meta-knowledge guard (v1.1 D-57): LLM still doesn't see exact HP/AC. AOE candidate context adds `available_actions` only; MEM context adds derived flags (recent_damage_dealt category, marked_dangerous bool) NOT raw HP.
- New persistence (MEM-03) uses Phase 17 cache pattern: aiosqlite WAL, single-writer, fail-soft on schema mismatch.
- Streaming embed (STREAM-01) uses Phase 2 embed coalescer; NO new rate-limit infrastructure.
- Hot-reload (OPQOL-01) uses Phase 8's 3-tier loader's existing fail-soft path; bot continues with last-known-good on bad YAML.
- Discord DM (OPQOL-02) is opt-in via env (DISCORD_OWNER_ID); zero behavior change when unset.
- Phase 16↔17 invalidation wire (OPQOL-03) is atomic — partial wipes are forbidden; either both layers clear or neither.
