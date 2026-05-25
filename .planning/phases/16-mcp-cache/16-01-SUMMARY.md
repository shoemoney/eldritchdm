---
phase: 16-mcp-cache
plan: 16-01
subsystem: mcp
tags: [cache, lru, sqlite, mechanical-honesty]
requires: [Phase 1 (aiosqlite WAL precedent), Phase 7 (MCPClient)]
provides: [MCPCache class, CACHEABLE_TOOLS allow-list]
affects: [src/eldritch_dm/mcp/__init__.py public surface, src/eldritch_dm/config Settings]
tech-stack-added: []
key-files-created:
  - src/eldritch_dm/mcp/cache.py
  - tests/mcp/test_cache.py
key-files-modified:
  - src/eldritch_dm/config/__init__.py
  - src/eldritch_dm/mcp/__init__.py
  - tests/test_config.py
decisions:
  - D-110 / D-111 / D-112 / D-113 / D-116 / D-117 implemented per CONTEXT
  - "Allow-list tightened from suggested 'dm20__get_* / dm20__list_*' to 6 STATIC reference tools — advisor-driven, see Deviations below"
metrics:
  duration: ~25 minutes
  tasks: 5
  tests-added: 28
status: complete
---

# Phase 16 Plan 01: MCPCache scaffolding — L1 LRU + L2 SQLite + cacheable allow-list

## One-liner

`MCPCache` composes `MCPClient` with a two-layer cache (in-process LRU + opt-in aiosqlite WAL), gated by a fail-CLOSED allow-list of six static D&D reference tools — mutable-state reads are intentionally excluded to preserve the v1.0 mechanical-honesty contract.

## What shipped

- **`src/eldritch_dm/mcp/cache.py`** — the `MCPCache` class.
  - Composes (not inherits) `MCPClient`. Mirrors `MCPClient.call(tool_name, **arguments) -> dict` exactly so it is a drop-in.
  - L1: `OrderedDict[(tool, args_hash), _L1Entry]` + `asyncio.Lock`. LRU eviction on put; TTL drop on read. Configurable via `MCPCACHE_L1_SIZE` (512) and `MCPCACHE_L1_TTL_S` (300).
  - L2: lazy aiosqlite WAL at `MCPCACHE_L2_PATH` (default `~/.eldritch/mcp_cache.sqlite`). Schema mirrors D-111 verbatim. INSERT-OR-REPLACE upsert. TTL drop on read. Opt-in via `MCPCACHE_L2_ENABLED=true`. Default OFF.
  - `args_hash` = SHA-256 of `json.dumps(args, sort_keys=True, separators=(',', ':'), default=str)`. Verified cross-process stable in `test_args_hash_stable_across_processes`.
  - Exposed via `eldritch_dm.mcp.__init__`: `MCPCache`, `CACHEABLE_TOOLS`.
- **6 new env vars** (`src/eldritch_dm/config/__init__.py`): `MCPCACHE_ENABLED`, `MCPCACHE_L1_SIZE`, `MCPCACHE_L1_TTL_S`, `MCPCACHE_L2_ENABLED`, `MCPCACHE_L2_TTL_S`, `MCPCACHE_L2_PATH`.
- **28 tests** in `tests/mcp/test_cache.py`. All pass; `ruff` and `lint-imports` clean.

## Cacheable allow-list (D-117)

```python
CACHEABLE_TOOLS = frozenset({
    "dm20__get_class_info",
    "dm20__get_race_info",
    "dm20__list_campaigns",
    "dm20__get_campaign_info",
    "dnd__search_all_categories",
    "dnd__verify_with_api",
})
```

Pinned in `test_cacheable_tools_membership_snapshot`; modifying this set requires also updating that test and reviewing the D-117 mechanical-honesty implications.

## Deviations from Plan

### 1. [Rule 2 — Critical correctness] Tightened allow-list (advisor-driven)

- **Found during:** Plan-writing (orientation, before any code).
- **Issue:** The task objective's suggested allow-list included `dm20__get_party`, `dm20__get_session_state`, `dm20__list_monsters`, `dm20__list_spells`, `dm20__list_classes`, `dm20__lookup_rule`, `dm20__schema_version`. None of these strings exist in `src/eldritch_dm/mcp/tools.py`'s `TOOL_TO_FUNCTION` registry. Furthermore, the naive "all `dm20__get_*` + `dm20__list_*`" interpretation would have included `dm20__get_character`, `dm20__get_game_state`, `dm20__get_npc`, `dm20__get_party_status`, `dm20__list_characters`, `dm20__get_claudmaster_session_state`, and `dm20__validate_character_rules` — all of which are **mutable-state reads** that change as the game progresses. Caching them between a write and the next read would serve stale HP/turn/state data, breaking D-117 (the mechanical-honesty contract that the dm20 surface upholds).
- **Fix:** Restricted the allow-list to the six tools above — all of which are static D&D 5e reference data or campaign metadata that does not change during a session.
- **Files modified:** `src/eldritch_dm/mcp/cache.py`, `tests/mcp/test_cache.py` (snapshot test + parametrized bypass test covering the excluded mutable-state reads).
- **Plan note:** Plan 16-02 will NOT relax this. Future plans that add per-mutation invalidation wiring at every `dm20__update_*` / `dm20__apply_*` / `dm20__set_*` call site MAY then add the corresponding mutable-state reads, one tool at a time, with explicit tests.

### 2. [Rule 1 — Bug] L2 TTL test sleep duration

- **Found during:** Task 03 first test run.
- **Issue:** `int(time.time())` rounding can produce a 1-second integer diff after a 1.05s wall-clock sleep when `ttl=1`. The check `(now - created_ts) > ttl` is then False and the row survives.
- **Fix:** Test sleeps 2.1s (with `await asyncio.sleep` for ASYNC251 compliance) and the comparison stays `>` (strict). Documented the rationale inline.
- **Files modified:** `tests/mcp/test_cache.py`.

### 3. [Rule 3 — Blocking issue] `MCPClient.execute()` does not exist

- **Found during:** Orientation.
- **Issue:** CONTEXT D-110 and the task objective both reference `MCPClient.execute()`. The real method on the existing client is `MCPClient.call(tool_name, **arguments)`.
- **Fix:** Both plans (16-01, 16-02) target `.call`, and `MCPCache.call` mirrors it exactly. No new method introduced.

## Key design notes for 16-02

- The `_Counters` dataclass already tracks `invalidations_total` and `last_invalidation_removed` so Plan 16-02 only has to populate them.
- L2 has a private `_l2_size()` helper for the KPI gauges 16-02 will emit.
- Module-level `_logger` is bound with `component="mcp_cache"` for structured-log correlation.

## Verification snapshot

| Check | Result |
|---|---|
| `uv run pytest tests/mcp -q` | 88 passed |
| `uv run pytest tests/test_config.py -k mcp -q` | 2 passed |
| `uv run ruff check src/eldritch_dm/mcp tests/mcp src/eldritch_dm/config tests/test_config.py` | clean |
| `uv run lint-imports` | 8/8 contracts kept |

## Self-Check: PASSED

Files created/modified all exist (`ls -la` confirmed via repo paths). Commits exist in `git log` on branch `worktree-agent-aba36c527f6bc66b0`. 28 cache tests visible in pytest output.
