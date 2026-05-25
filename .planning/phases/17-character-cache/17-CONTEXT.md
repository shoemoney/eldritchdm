---
phase: 17-character-cache
milestone: v1.5
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - CHARCACHE-01 (snapshot SQLite + first-load population)
  - CHARCACHE-02 (ETag-based lazy refresh)
  - CHARCACHE-03 (TTL fallback + cache-clear CLI)
---

# Phase 17 — Persistent character cache (CONTEXT)

## Mission

Cache character snapshots (id, name, stats, current HP, class/subclass, conditions) across bot restarts so the first turn of a re-launched session doesn't wait for full dm20 character ingest. ETag-based refresh keeps the cache fresh; TTL fallback handles dm20 responses without ETags.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-119** | **Standalone cache** at `~/.eldritch/character_cache.sqlite` (separate from Phase 16's mcp_cache.sqlite) — different schemas, different TTLs, different invalidation rules. Aiosqlite WAL + single-writer (Phase 1 / v1.4 pattern). | Cleaner separation; character cache has heavier per-row data |
| **D-120** | **Schema**: `(character_id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL, etag TEXT, last_seen_ts INTEGER NOT NULL, refreshed_ts INTEGER NOT NULL)`. `snapshot_json` is the full normalized character payload the bot needs (NOT the raw dm20 response — pre-projected to what `bot/cogs/combat.py` actually uses). `last_seen_ts` for LRU eviction; `refreshed_ts` for TTL check. | Pre-projection trades cache-build cost for cache-hit speed |
| **D-121** | **First-load path**: bot startup → for each tracked character, call `CharacterCache.get_or_fetch(character_id)`. On cache HIT with valid ETag/TTL → return snapshot in <10ms. On MISS → call dm20, project to snapshot shape, store. | Lazy population — don't preload all chars at startup |
| **D-122** | **ETag refresh**: when fetching via dm20, capture the response's ETag header (or compute a content-hash if dm20 doesn't expose one — `sha256(canonical-json(response))` as a synthetic ETag). On subsequent `get_or_fetch`, send `If-None-Match` (or compare synthetic ETag). 304 / match → serve from cache, bump `last_seen_ts`. Mismatch → refetch + restore. | Cheap freshness check |
| **D-123** | **TTL fallback (CHARCACHE-03)**: `CHARCACHE_TTL_S` env, default `3600s`. If `time.time() - refreshed_ts > TTL` → force refresh regardless of ETag. Belt-and-suspenders for dm20 endpoints that don't honor ETag semantics. | Operator escape via env override |
| **D-124** | **Operator CLI**: `eldritch-dm-cache-clear --characters [--character-id ID]` purges entries. Mirrors Phase 9's `eldritch-dm-backfill-pc-classes` CLI pattern. Wire into pyproject `[project.scripts]`. | Operator control surface |
| **D-125** | **Mechanical-honesty preserve**: `snapshot_json` MUST NOT cache derived combat state (computed AC, current HP after damage, condition durations) — only static character data (stats, max HP, class, race, items). Combat-state lives in dm20 and is never cached by us. Schema-level: snapshot_json's pydantic model has a hardcoded allow-list of fields; anything else is rejected at write time. | Same fail-CLOSED contract as Phase 16 D-117 |
| **D-126** | **KPIs**: extend Phase 11/13's KPI surface with `eldritch_character_cache_hit_rate`, `eldritch_character_cache_size`, `eldritch_character_cache_etag_match_rate`. Honors OBSERVABILITY_ENABLED. | Single observability layer |
| **D-127** | **Module location**: `src/eldritch_dm/persistence/character_cache.py` (sibling of existing `pc_classes_repo.py`). Tests at `tests/persistence/test_character_cache.py`. | Persistence package per Phase 1 convention |
| **D-128** | **2 plans**: 17-01 = snapshot SQLite + ETag refresh path. 17-02 = TTL fallback + cache-clear CLI + KPIs. | ROADMAP plans section |

## Implementation Sketch

**Plan 01:** `CharacterCacheRepo` with aiosqlite WAL; `get_or_fetch(character_id, fetcher)` async method; ETag-based refresh; pydantic `CharacterSnapshot` model with static-fields allow-list; unit + integration tests.

**Plan 02:** TTL refresh path; `eldritch-dm-cache-clear` CLI entry; KPI emission via Phase 11 traced_decision; ≥10 new tests covering TTL expiry + CLI dry-run/force.

## Success Criteria
1. Character snapshot cached after first dm20 fetch; survives bot restart
2. ETag match → serve from cache; mismatch → refetch
3. TTL fallback triggers on stale entries beyond `CHARCACHE_TTL_S`
4. `eldritch-dm-cache-clear --characters` on PATH + functional
5. Snapshot schema rejects combat-state fields (HP changes, condition durations) — fail-CLOSED
6. KPIs visible in Phase 11 spans
7. ≥15 new tests; ruff + lint-imports clean
