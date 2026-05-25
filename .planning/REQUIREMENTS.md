# EldritchDM — Requirements (v1.5 Cache Architecture)

**Milestone:** v1.5 Cache Architecture
**Goal:** Multi-level cache across the stack — dm20 MCP query cache (the hot path for rules lookups), persistent character cache (avoid rebuild on bot restart), narration response cache (opt-in, with mechanical-honesty guardrails). Real perf wins + operator cost reduction; UNBLOCKED now that v1.4 ships full-suite green.
**Total v1.5 requirements:** 9 across 3 categories.

---

## v1.5 Requirements

### MCPCACHE — dm20 MCP query cache (Phase 16)

- [ ] **MCPCACHE-01**: L1 in-process LRU cache wraps `MCPClient` calls — keyed on `(tool_name, frozenset(args.items()))`. Default `maxsize=512` entries, configurable via `MCPCACHE_L1_SIZE` env. TTL default `300s`, configurable via `MCPCACHE_L1_TTL_S`. Cache HIT bypasses HTTP; cache MISS hits dm20 and stores result. Opt-out via `MCPCACHE_ENABLED=false` (defaults to true for v1.5 since it's safe-by-default).
- [ ] **MCPCACHE-02**: L2 SQLite-backed cache extends the L1 TTL across bot restarts. Persisted at `~/.eldritch/mcp_cache.sqlite` (WAL, mirrors Phase 1 pattern). Schema: `(tool_name TEXT, args_hash TEXT, response_json TEXT, etag TEXT, created_ts INTEGER, PRIMARY KEY(tool_name, args_hash))`. L2 TTL default `86400s` (24h), configurable. L2 is OPT-IN via `MCPCACHE_L2_ENABLED=true` (default false — adds DB write overhead).
- [ ] **MCPCACHE-03**: Cache invalidation hook — `MCPCache.invalidate(tool_name=None, args=None)` clears matching entries from BOTH layers. Auto-invalidation on dm20 schema version change (`dm20__schema_version` tool result diff from last cached value). KPIs added: `eldritch_mcp_cache_hit_rate` + `eldritch_mcp_cache_size` gauges via Phase 11 OTel spans.

### CHARCACHE — Persistent character cache (Phase 17)

- [ ] **CHARCACHE-01**: Character snapshots (stats, current HP, class/subclass, conditions) cached in `~/.eldritch/character_cache.sqlite` after first dm20 lookup. Schema: `(character_id TEXT PRIMARY KEY, snapshot_json TEXT, etag TEXT, last_seen_ts INTEGER)`. Snapshots survive bot restarts; eliminates the "first turn of every restart waits N seconds for character ingest" UX problem.
- [ ] **CHARCACHE-02**: Lazy refresh on dm20 ETag mismatch — if cached `etag` differs from current dm20 response, refetch full snapshot and update cache. ETag check is a lightweight HEAD-style dm20 call (or first 1024 bytes of GET). Cache hit avoids the full character-build path entirely.
- [ ] **CHARCACHE-03**: TTL fallback for ETag-less responses — if dm20 doesn't expose an ETag for some tool, fall back to TTL-based refresh (default `3600s`, configurable via `CHARCACHE_TTL_S`). Operator can force refresh via `eldritch-dm-cache-clear --characters` CLI.

### NARRCACHE — Narration response cache (Phase 18)

- [ ] **NARRCACHE-01**: OPT-IN narration cache (default OFF) — `NARRCACHE_ENABLED=true` to enable. Keyed on `(model_id, system_prompt_hash, user_prompt_hash, max_tokens)`. SHA-256 prompt hashes. Stored at `~/.eldritch/narration_cache.sqlite`. **Hard constraint**: only narration responses (free-form text) are cacheable. ANY response that includes mechanical effects (HP changes, condition applications, dice results) MUST bypass the cache — verified by a content-classifier that rejects responses matching a regex set for HP/AC/damage patterns.
- [ ] **NARRCACHE-02**: Mechanical-honesty guard — `NarrCacheGate` class with `is_pure_narration(response_text: str) -> bool` static method that returns False on any line matching: `\b(HP|AC|damage|dmg|hit points|saves? against|takes \d+|deals \d+)\b` (case-insensitive). Cache stores are gated through this — fail-CLOSED (don't cache when uncertain). 50-scenario test corpus split 50/50 between cacheable narration and non-cacheable mechanical text.
- [ ] **NARRCACHE-03**: Operator off-switch + observability — `eldritch-dm-cache-disable --narration` flips a runtime override that disables narration cache without restart. KPI `eldritch_narrcache_hit_rate` gauge + `eldritch_narrcache_rejected_count` (responses bypassed by `NarrCacheGate`) via Phase 11 OTel spans. `eldritch-dm-cache-stats --narration` CLI reports hit rate + cost-savings estimate (using Phase 13's cost calculator).

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| MCPCACHE-01 | 16 | User v1.2.1 hint: cache architecture; dm20 rules lookups are hottest path |
| MCPCACHE-02 | 16 | Restart-survival pattern (mirrors Phase 1 WAL SQLite) |
| MCPCACHE-03 | 16 | Phase 11 observability tie-in + safety (cache invalidation on schema bump) |
| CHARCACHE-01 | 17 | First-turn UX latency; dm20 character lookup is slow |
| CHARCACHE-02 | 17 | Avoid staleness via ETag check |
| CHARCACHE-03 | 17 | Fallback when ETag unavailable + operator escape hatch |
| NARRCACHE-01 | 18 | LLM inference cost reduction (Phase 13 cost guard tie-in) |
| NARRCACHE-02 | 18 | Mechanical-honesty contract preservation (v1.0 core value) — narration only |
| NARRCACHE-03 | 18 | Phase 13 observability + Phase 7 operator-control pattern |

## Mode Constraints

- **Mechanical-honesty contract is sacrosanct**: NARRCACHE-02 fail-CLOSED gate is non-negotiable. The bot must NEVER cache an LLM response that includes mechanical effects — even if it costs LLM spend.
- Phase 11 observability (OTel spans) is the integration point for KPIs — don't add a new monitoring stack.
- Phase 13 cost guard is the integration point for savings estimates.
- All caches respect `OBSERVABILITY_ENABLED` — when off, KPI emission is no-op.
- L2 SQLite caches use WAL + busy_timeout (Phase 1 pattern); single-writer task with `BEGIN IMMEDIATE` (the WriterQueue we now know is correct — v1.4 verified).
- Cross-phase impact: Phase 16's MCPCACHE invalidation hook may need to fire when Phase 17's CHARCACHE detects a character schema-version change.
