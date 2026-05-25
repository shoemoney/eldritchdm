---
phase: 16-mcp-cache
milestone: v1.5
generated: 2026-05-25
mode: auto-generated (autonomous-flow, discuss skipped per 'confirmed continue')
source_requirements:
  - MCPCACHE-01 (L1 LRU)
  - MCPCACHE-02 (L2 SQLite restart-survival)
  - MCPCACHE-03 (invalidation + KPI integration)
---

# Phase 16 — dm20 MCP query cache (CONTEXT)

## Mission

Wrap `MCPClient` with a multi-level cache. L1 is in-process LRU (fast, ephemeral); L2 is SQLite-backed (survives restart). Auto-invalidation on dm20 schema-version change. Phase 11 OTel KPI integration.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-110** | **L1 = `functools.lru_cache`-style decorator** wrapping `MCPClient.execute()` — backed by an `OrderedDict` + asyncio.Lock for thread safety. Key: `(tool_name, hashable_args)`. Default `maxsize=512`, `ttl=300s`. | Stdlib-friendly; asyncio.Lock makes it safe for `MCPClient`'s async call sites |
| **D-111** | **L2 = aiosqlite WAL** at `~/.eldritch/mcp_cache.sqlite`. Single-writer pattern (mirrors Phase 1 / v1.4 WriterQueue). Schema: `(tool_name TEXT, args_hash TEXT, response_json TEXT, etag TEXT, created_ts INTEGER, PRIMARY KEY(tool_name, args_hash))`. | Phase 1 WAL precedent + v1.4 fix is now battle-tested |
| **D-112** | **args_hash = SHA-256 of sorted-JSON-canonical args** — deterministic across runs. NOT `hash(frozenset(...))` (Python hash is per-process random with PYTHONHASHSEED). | L2 needs cross-restart key stability |
| **D-113** | **MCPCACHE_ENABLED=true by default** for L1 (safe — TTL means stale data clears in 5 min). MCPCACHE_L2_ENABLED=false by default (opt-in — adds disk write cost). | Safe-by-default for L1; conservative for L2 |
| **D-114** | **Invalidation triggers**: (1) explicit `MCPCache.invalidate(tool, args)` API, (2) dm20 schema version change detected by polling `dm20__schema_version` every 60s in a bot-startup background task. On change → wipe entire cache + log structured event. | Schema-version polling is the canonical staleness signal for dm20 |
| **D-115** | **KPIs via Phase 11 OTel**: `eldritch_mcp_cache_hit_rate` (gauge, rolling 5min), `eldritch_mcp_cache_size_l1` + `eldritch_mcp_cache_size_l2` (gauges), `eldritch_mcp_cache_invalidations_total` (counter). Emitted from `MCPCache.execute()` wrapper. Honors `OBSERVABILITY_ENABLED` (no-op when off). | Single observability layer per Phase 11 |
| **D-116** | **Module location**: `src/eldritch_dm/mcp/cache.py` (next to existing `client.py`). `MCPCache` class composes (wraps) `MCPClient` rather than inheriting — simpler tests, no Liskov risk. Existing `MCPClient` callers may opt-in via `MCPCache(MCPClient(...))` constructor or via a factory in `mcp/__init__.py`. | Composition > inheritance; preserves Phase 1 callers |
| **D-117** | **NEVER cache mutations** — only `dm20__get_*` and `dm20__list_*` tools cached. Set of cacheable tool prefixes is explicit (allow-list, NOT deny-list — fail-CLOSED). Any tool name that doesn't match → bypass cache. | Mechanical-honesty extension: cache must never serve stale write results |
| **D-118** | **2 plans**: 16-01 = L1+L2 scaffolding + cacheable allow-list. 16-02 = invalidation hook + KPI integration. | ROADMAP plans section |

## Implementation Sketch

**Plan 01 (16-01):** `MCPCache` class with L1 OrderedDict + L2 aiosqlite; `execute()` async method that checks L1 → L2 → MCPClient; cacheable tool allow-list; pytest fixture set with respx-mocked dm20.

**Plan 02 (16-02):** `MCPCache.invalidate()` API + schema-version polling background task + OTel KPI emission + integration test that mutates schema version and asserts cache wipe.

## Success Criteria
1. `MCPCACHE_ENABLED=true` (default L1 on): cache hit rate measurable; L1 size ≤ maxsize; TTL eviction works
2. `MCPCACHE_L2_ENABLED=true`: L2 persists across restart; cache survives `bot.close()` → reopen
3. `MCPCache.invalidate()` clears both layers; schema-version-change auto-invalidates
4. KPIs visible in Phase 11 spans when OBSERVABILITY_ENABLED=true
5. Cacheable allow-list rejects mutation tools (no `create_*`, `update_*`, `apply_*`)
6. ≥20 new tests; ruff + lint-imports clean
