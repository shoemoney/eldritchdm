---
phase: 17-character-cache
generated: 2026-05-25
status: complete
---

# Phase 17 Verification — Persistent character cache

## Requirements coverage

| ID | Status | Implementation |
|----|--------|----------------|
| CHARCACHE-01 | [x] | `src/eldritch_dm/persistence/character_cache.py` — `CharacterCacheRepo` with lazy aiosqlite WAL at `~/.eldritch/character_cache.sqlite` (D-119). Schema D-120: `(character_id PRIMARY KEY, snapshot_json, etag, last_seen_ts, refreshed_ts)`. Survives bot restart (proven by `test_cache_survives_repo_recreation`). |
| CHARCACHE-02 | [x] | Same file — synthetic SHA-256 ETag over canonical JSON (D-122). `get_or_fetch(character_id, fetcher)` returns cached on ETag match (no schema rewrite), refreshes on mismatch. `hits_etag` / `misses` / `etag_match_rate` exposed via `metrics_snapshot()`. |
| CHARCACHE-03 | [x] | TTL short-circuit (D-123) via `CHARCACHE_TTL_S` (default 3600). `eldritch-dm-cache-clear --characters [--character-id ID] [--dry-run]` CLI on PATH (D-124, `src/eldritch_dm/tools/cache_clear.py`). KPI spans `eldritch.character_cache.lookup` + `eldritch.character_cache.invalidation` via Phase 11/13 dual-sink. |

## Allow-list (D-125 — mechanical-honesty contract)

`CharacterSnapshot.model_config = ConfigDict(extra="forbid", frozen=True)`. The 14 cacheable static fields:

```
id, name, race, character_class, subclass, level, proficiency_bonus,
alignment, languages, max_hp, base_stats, base_ac, base_speed, equipment
```

Field-naming choice: `base_ac` / `base_speed` (NOT bare `ac` / `speed`) so the static-vs-current distinction is visible at every call site.

**Explicitly NOT cacheable** (parametrized in `test_forbidden_fields_rejected`, 11 cases):

- `current_hp`, `current_temp_hp`, `current_conditions`, `exhaustion_level`,
  `active_buffs`, `concentration_target`, `death_save_successes`,
  `death_save_failures`, `hit_dice_remaining`, `current_speed`, `current_ac`.

These are silently STRIPPED by `_project_to_snapshot` BEFORE construction, AND would be REJECTED by `extra="forbid"` if they ever reached the model. Defense-in-depth.

Pinned by `test_allowed_snapshot_fields_membership_snapshot` — modifying `CharacterSnapshot` REQUIRES updating that test and re-reviewing D-125.

## Test counts

| Suite | Count |
|---|---|
| `tests/persistence/test_character_cache.py` (new) | 52 |
| `tests/tools/test_cache_clear.py` (new) | 7 |
| `tests/test_config.py` (delta — `TestCharCacheDefaults`) | 2 |
| Phase-17-related total | **61** (exceeds ≥15 success-criteria minimum) |
| Full focused suite | 361 passed, 9 skipped |

## Tooling

| Check | Command | Result |
|---|---|---|
| Phase 17 tests | `uv run pytest tests/persistence/test_character_cache.py tests/tools/test_cache_clear.py tests/test_config.py -q` | 61 passed |
| Wider regression | `uv run pytest tests/persistence tests/observability tests/tools tests/test_config.py tests/mcp -q` | 361 passed, 9 skipped |
| Ruff | `uv run ruff check src tests` | clean |
| Import boundaries | `uv run lint-imports` | 8/8 contracts kept |
| CLI on PATH | `uv run eldritch-dm-cache-clear --help` | shows usage |

## Files

### Created

- `src/eldritch_dm/persistence/character_cache.py`
- `src/eldritch_dm/tools/cache_clear.py`
- `tests/persistence/test_character_cache.py`
- `tests/tools/test_cache_clear.py`
- `.planning/phases/17-character-cache/17-01-PLAN.md`
- `.planning/phases/17-character-cache/17-01-SUMMARY.md`
- `.planning/phases/17-character-cache/17-02-PLAN.md`
- `.planning/phases/17-character-cache/17-02-SUMMARY.md`
- `.planning/phases/17-character-cache/17-VERIFICATION.md`

### Modified

- `src/eldritch_dm/config/__init__.py` — 3 new `CHARCACHE_*` settings.
- `src/eldritch_dm/persistence/__init__.py` — exports `CharacterCacheRepo`, `CharacterSnapshot`, `CharacterCacheMetrics`, `ALLOWED_SNAPSHOT_FIELDS`, `FORBIDDEN_SNAPSHOT_FIELDS`, `etag_of`.
- `src/eldritch_dm/observability/instrumentation.py` — 2 new context managers (`traced_character_cache`, `traced_character_cache_invalidation`) + extended `_BufferingSpan._build_row` attribute mapping.
- `tests/test_config.py` — `TestCharCacheDefaults` (2 tests).
- `pyproject.toml` — registers `eldritch-dm-cache-clear` script.
- `.planning/REQUIREMENTS.md` — CHARCACHE-01/02/03 → `[x]`.

## Cross-phase impact

- **Phase 16 (MCPCache) parallel:** The Phase 16 `_BufferingSpan._build_row` attr-key mapping has been extended to also route Phase 17 character-cache attrs. Both phases share the same dual-sink schema; future cache subsystems can add attrs onto the existing columns without `BufferRow` schema extensions. The Phase 13 `test_span_buffer` schema canaries remained green.
- **Phase 18 (NARRCACHE)** can mirror this exact CLI structure (`eldritch-dm-cache-clear --narration …`) and reuse the dual-sink span pattern.
- **dm20 mutation call-sites:** Bot code that triggers a level-up / equipment change SHOULD call `repo.invalidate(character_id)` to force a fresh snapshot. Without explicit hooks, TTL (default 3600s) is the freshness mechanism — documented as a known limitation.

## Known limitations / non-goals

- **No per-mutation invalidation wiring** at level-up / shopping call sites. TTL (3600s) + manual CLI clear are the v1.5 freshness primitives.
- **dm20 schema-version polling not auto-started.** Phase 16's `start_schema_version_poller` pattern was deliberately not adopted for the character cache because character snapshots are scoped per-character (not global), and the staleness story is different (level-up is the dominant event, not a server-side schema bump).
- **Fetcher is invoked on every non-TTL hit.** The synthetic ETag still saves projection + SQLite write cost; the network call is unavoidable without a real upstream conditional-request mechanism (which dm20's MCP surface does not expose). TTL is the only "zero-network" hit path.

## Status: COMPLETE
