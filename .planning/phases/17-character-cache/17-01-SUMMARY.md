---
phase: 17-character-cache
plan: 17-01
requirements_completed: [CHARCACHE-01, CHARCACHE-02]
subsystem: persistence
tags: [cache, sqlite, mechanical-honesty, etag, snapshot]
requires: [Phase 1 (aiosqlite WAL precedent), Phase 16 (lazy-conn pattern)]
provides: [CharacterCacheRepo, CharacterSnapshot, ALLOWED_SNAPSHOT_FIELDS, etag_of]
affects: [src/eldritch_dm/persistence/__init__.py, src/eldritch_dm/config Settings, src/eldritch_dm/observability/instrumentation.py]
tech-stack-added: []
key-files-created:
  - src/eldritch_dm/persistence/character_cache.py
  - tests/persistence/test_character_cache.py
key-files-modified:
  - src/eldritch_dm/config/__init__.py
  - src/eldritch_dm/persistence/__init__.py
  - src/eldritch_dm/observability/instrumentation.py
  - tests/test_config.py
decisions:
  - D-119 / D-120 / D-121 / D-122 / D-125 / D-127 implemented per CONTEXT
  - "Allow-list advisor-reviewed: 14 static fields. base_ac/base_speed prefix forces static-vs-current distinction. Projector strips D-125 forbidden names BEFORE construction; extra='forbid' is the secondary line."
  - "Synthetic SHA-256 ETag is the primary refresh signal (dm20 MCP has no HTTP headers) — not a fallback as the original requirement text suggested."
metrics:
  duration: ~25 minutes
  tasks: 5
  tests-added: 52 (character_cache) + 2 (config) = 54
status: complete
  - CHARCACHE-01
  - CHARCACHE-02
---

# Phase 17 Plan 01: CharacterCacheRepo + CharacterSnapshot allow-list

## One-liner

`CharacterCacheRepo` wraps an aiosqlite WAL store at `~/.eldritch/character_cache.sqlite` and serves `CharacterSnapshot` instances whose `extra="forbid"` allow-list of 14 static fields preserves the v1.0 mechanical-honesty contract — combat-mutable state (`current_hp`, `current_conditions`, …) is stripped by the projector AND rejected at write time, fail-CLOSED.

## What shipped

- **`src/eldritch_dm/persistence/character_cache.py`** — the cache module.
  - `CharacterSnapshot(BaseModel, frozen=True, extra="forbid")` with the 14 static allow-list fields: `id`, `name`, `race`, `character_class`, `subclass`, `level`, `proficiency_bonus`, `alignment`, `languages`, `max_hp`, `base_stats` (STR/DEX/CON/INT/WIS/CHA), `base_ac`, `base_speed`, `equipment`.
  - `ALLOWED_SNAPSHOT_FIELDS: frozenset[str]` pinned at import time.
  - `FORBIDDEN_SNAPSHOT_FIELDS: frozenset[str]` (D-125 list — 11 combat-mutable names) — used by the projector to strip noisy upstream payloads AND by the parametrized rejection test.
  - `_project_to_snapshot(response)` — drops forbidden fields silently, drops unknown static fields silently, raises `ValueError("missing required: …")` on missing required fields, maps legacy `class` key to `character_class`, normalizes `languages` to a sorted list for ETag stability.
  - `etag_of(payload)` — SHA-256 over `json.dumps(payload, sort_keys=True, separators=(',',':'), default=str)`. Key-order invariant proven by `test_canonical_json_key_order_invariant`.
  - `CharacterCacheRepo` with lazy `_ensure_conn()` (mirrors Phase 16's `MCPCache._l2_ensure_conn()`). NOT routed through Phase 1's `WriterQueue` — this is a separate DB.
  - `get_or_fetch(character_id, fetcher)` with three paths: TTL-hit (skips fetcher), ETag-match (bumps `last_seen_ts` + `refreshed_ts`), miss/mismatch (project + upsert).
  - `invalidate(character_id=None)`, `metrics_snapshot()`, `aclose()` idempotent.
- **3 new env vars** (`src/eldritch_dm/config/__init__.py`): `CHARCACHE_ENABLED`, `CHARCACHE_PATH`, `CHARCACHE_TTL_S`.
- **2 new instrumentation spans** in `observability/instrumentation.py`: `traced_character_cache` + `traced_character_cache_invalidation` — both reuse the existing `_BufferingSpan` dual-sink machinery; attributes mapped onto existing `BufferRow` columns so NO schema extension was needed.
- **54 tests** total (52 in `tests/persistence/test_character_cache.py`, 2 in `tests/test_config.py::TestCharCacheDefaults`). All pass; `ruff` and `lint-imports` clean.

## Allow-list (D-125 mechanical-honesty contract)

```
id, name, race, character_class, subclass, level, proficiency_bonus,
alignment, languages, max_hp, base_stats, base_ac, base_speed, equipment
```

Field naming choice: `base_ac` / `base_speed` (NOT bare `ac` / `speed`) so the static-vs-current distinction is visible at every call site. `current_ac` and `current_speed` are in `FORBIDDEN_SNAPSHOT_FIELDS` and parametrized-tested for rejection.

Pinned in `test_allowed_snapshot_fields_membership_snapshot` — modifying the model REQUIRES updating that test and re-reviewing D-125.

**Explicitly FORBIDDEN** (11 names, parametrized in `test_forbidden_fields_rejected`):
`current_hp`, `current_temp_hp`, `current_conditions`, `exhaustion_level`, `active_buffs`, `concentration_target`, `death_save_successes`, `death_save_failures`, `hit_dice_remaining`, `current_speed`, `current_ac`.

## Deviations from Plan

### 1. [Rule 2 — Critical correctness] Projector silently strips forbidden fields BEFORE construction

- **Found during:** Plan-writing (orientation with advisor).
- **Issue:** If dm20 returns `{"id":"…", …, "current_hp": 12, "current_conditions": ["poisoned"]}` and we just `CharacterSnapshot(**resp)` we hit `extra="forbid"` and the cache write crashes. That makes the cache fragile under realistic upstream payloads.
- **Fix:** `_project_to_snapshot` strips `FORBIDDEN_SNAPSHOT_FIELDS` AND non-allow-listed fields BEFORE construction. `extra="forbid"` remains as a defense-in-depth check at the model level, but the projector is the primary fail-CLOSED gate.
- **Files modified:** `src/eldritch_dm/persistence/character_cache.py`, `tests/persistence/test_character_cache.py::TestProjector::test_drops_combat_state`.

### 2. [Rule 1 — Design clarification] Synthetic SHA-256 ETag is PRIMARY, not fallback

- **Found during:** Plan-writing.
- **Issue:** CHARCACHE-02 in REQUIREMENTS.md is worded as "lazy refresh on dm20 ETag mismatch" implying an HTTP-style `If-None-Match` flow. dm20's surface is MCP tool calls — no response headers, no HTTP semantics.
- **Fix:** Designed around a synthetic ETag = `sha256(canonical-json(latest dm20 response))`. The fetcher is ALWAYS invoked (the network call cannot be avoided without TTL — which is Plan 17-02's job); the savings are: (a) avoid expensive projection on hit, (b) avoid SQLite write on hit, (c) allow the bot to share the cached snapshot across calls within the TTL window. Documented in CONTEXT D-122 and re-emphasized in the SUMMARY.
- **Plan note:** The "free hit" optimization comes from Plan 17-02's TTL short-circuit, NOT from ETag handling.

### 3. [Rule 3 — Blocking issue] `class` is a Python keyword

- **Found during:** Drafting the pydantic model.
- **Issue:** dm20 responses use `"class": "fighter"` but we cannot use `class:` as a Python identifier.
- **Fix:** Model field is `character_class`; projector maps legacy `class` key → `character_class` automatically. Test: `test_legacy_class_key_maps_to_character_class`.

## Key design notes for 17-02

- TTL short-circuit was already wired in 17-01's `get_or_fetch` (the structure was unavoidably entangled) — 17-02's plan-text talks about it but the line lives in this commit.
- `_Counters` already exposes `hits_ttl`, `hits_etag`, `misses`, `invalidations_total` — 17-02's `metrics_snapshot` is wired too.
- The two `traced_character_cache*` spans were added here so the buffer-row schema was settled in one go; 17-02 ties them into the CLI surface and ticks the requirement.

## Verification snapshot

| Check | Result |
|---|---|
| `uv run pytest tests/persistence/test_character_cache.py -q` | 52 passed |
| `uv run pytest tests/test_config.py -k charcache -q` | 2 passed |
| `uv run ruff check src tests` | clean |
| `uv run lint-imports` | 8/8 contracts kept |

## Self-Check: PASSED

Files created/modified all exist. Commits visible in `git log` on branch `worktree-agent-aef302b86045a5ae1`. 52 character_cache tests visible in pytest output.
