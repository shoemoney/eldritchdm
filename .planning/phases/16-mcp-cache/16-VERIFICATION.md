---
phase: 16-mcp-cache
generated: 2026-05-25
status: complete
---

# Phase 16 Verification — dm20 MCP query cache

## Requirements coverage

| ID | Status | Implementation |
|----|--------|----------------|
| MCPCACHE-01 | [x] | `src/eldritch_dm/mcp/cache.py` — L1 OrderedDict + asyncio.Lock; `MCPCACHE_L1_SIZE=512`, `MCPCACHE_L1_TTL_S=300`; LRU + TTL eviction. |
| MCPCACHE-02 | [x] | Same file — opt-in aiosqlite WAL at `MCPCACHE_L2_PATH`; `MCPCACHE_L2_ENABLED=false` default; `MCPCACHE_L2_TTL_S=86400`; PRIMARY KEY (tool_name, args_hash). |
| MCPCACHE-03 | [x] | `MCPCache.invalidate(tool_name, args)` (3 scopes) + `start_schema_version_poller()` w/ graceful 4xx fallback + `traced_mcp_cache` / `traced_mcp_cache_invalidation` spans (Phase 11 dual-sink). |

## Allow-list (D-117 — mechanical-honesty contract)

Cacheable tools, fail-CLOSED — any tool not on this list bypasses the cache:

```
dm20__get_class_info
dm20__get_race_info
dm20__list_campaigns
dm20__get_campaign_info
dnd__search_all_categories
dnd__verify_with_api
```

**Explicitly NOT cacheable** (verified by `test_bypass_for_non_cacheable_tools` parametrization):

- All mutations: `dm20__create_*`, `dm20__update_*`, `dm20__apply_*`, `dm20__set_*`, `dm20__start_*`, `dm20__end_*`, `dm20__next_*`, `dm20__remove_*`, `dm20__combat_*`, `dm20__party_*`, `dm20__player_action`, `dm20__load_*`.
- Mutable-state reads: `dm20__get_character`, `dm20__get_npc`, `dm20__get_game_state`, `dm20__get_party_status`, `dm20__list_characters`, `dm20__get_claudmaster_session_state`, `dm20__validate_character_rules`.
- RNG: `dice__dice_roll`.

Pinned by `test_cacheable_tools_membership_snapshot` — modifying `CACHEABLE_TOOLS` requires also updating that test and reviewing D-117 implications.

## Test counts

| Suite | Count |
|---|---|
| `tests/mcp/test_cache.py` (new) | 38 |
| `tests/test_config.py` (delta — `TestMcpCacheDefaults`) | 2 |
| `tests/observability/` (regression — still green) | 91 (7 skip) |
| `tests/mcp/` (total — incl. existing client/health/tools) | 98 |

## Tooling

| Check | Command | Result |
|---|---|---|
| Tests | `uv run pytest tests/mcp tests/observability tests/test_config.py -q` | 200 passed, 7 skipped |
| Ruff | `uv run ruff check src tests` | clean |
| Import boundaries | `uv run lint-imports` | 8/8 contracts kept |

## Files

### Created

- `src/eldritch_dm/mcp/cache.py`
- `tests/mcp/test_cache.py`
- `.planning/phases/16-mcp-cache/16-01-PLAN.md`
- `.planning/phases/16-mcp-cache/16-01-SUMMARY.md`
- `.planning/phases/16-mcp-cache/16-02-PLAN.md`
- `.planning/phases/16-mcp-cache/16-02-SUMMARY.md`
- `.planning/phases/16-mcp-cache/16-VERIFICATION.md`

### Modified

- `src/eldritch_dm/config/__init__.py` — 6 new `MCPCACHE_*` settings
- `src/eldritch_dm/mcp/__init__.py` — exports `MCPCache`, `MCPCacheMetrics`, `CACHEABLE_TOOLS`
- `src/eldritch_dm/observability/instrumentation.py` — 2 new context managers + attr-key mapping
- `tests/test_config.py` — `TestMcpCacheDefaults`
- `.planning/REQUIREMENTS.md` — MCPCACHE-01/02/03 → `[x]`

## Cross-phase impact

- Phase 17 (CHARCACHE) can use `MCPCache.invalidate(tool_name=..., args=...)` as a prior-art reference for character-cache invalidation hooks.
- Phase 18 (NARRCACHE) has a different mechanical-honesty story (regex content gate) but inherits the `traced_mcp_cache`-style span pattern.
- The Phase 11 `_BufferingSpan._build_row` attr-key mapping now covers cache spans — any future cache subsystem can map onto the existing columns without extending `BufferRow`.

## Known limitations / non-goals

- **Mutable-state reads are not cacheable.** `dm20__get_character`, `dm20__get_game_state`, etc. always bypass. Future plans that add per-mutation invalidation wiring at every `dm20__update_*` call site MAY then add those tools to `CACHEABLE_TOOLS`, one at a time, with explicit tests.
- **Schema-version polling is opt-in.** Callers must explicitly invoke `start_schema_version_poller(client)` — typically from the bot's `setup_hook`. Plan 16-02 deliberately did NOT auto-start it from `MCPCache.__init__` because the poll target may not exist on every dm20 deployment.
- **`size_l2` on per-call spans is a `-1` sentinel.** Use `await cache.metrics_snapshot()` for the authoritative L2 row count.

## Status: COMPLETE
