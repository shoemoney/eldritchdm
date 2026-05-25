# EldritchDM — Requirements (v1.5 Cache Architecture)

**Milestone:** v1.5 Cache Architecture
**Goal:** Multi-level cache across the stack — dm20 MCP query cache (the hot path for rules lookups), persistent character cache (avoid rebuild on bot restart), narration response cache (opt-in, with mechanical-honesty guardrails). Real perf wins + operator cost reduction; UNBLOCKED now that v1.4 ships full-suite green.
**Total v1.5 requirements:** 9 across 3 categories.

---

## v1.5 Requirements

### MCPCACHE — dm20 MCP query cache (Phase 16)

- [x] **MCPCACHE-01**: L1 in-process LRU cache wraps `MCPClient` calls — keyed on `(tool_name, sha256(canonical-json(args)))` (NOT `frozenset(args.items())` — PYTHONHASHSEED-stable per D-112). Default `maxsize=512` entries, configurable via `MCPCACHE_L1_SIZE` env. TTL default `300s`, configurable via `MCPCACHE_L1_TTL_S`. Cache HIT bypasses HTTP; cache MISS hits dm20 and stores result. Opt-out via `MCPCACHE_ENABLED=false` (defaults to true for v1.5 since it's safe-by-default). **Allow-list tightened to 6 static-reference tools only — mutable-state reads are NEVER cacheable per D-117 (see 16-01-SUMMARY).**
- [x] **MCPCACHE-02**: L2 SQLite-backed cache extends the L1 TTL across bot restarts. Persisted at `MCPCACHE_L2_PATH` (default `~/.eldritch/mcp_cache.sqlite`, WAL, mirrors Phase 1 pattern). Schema: `(tool_name TEXT, args_hash TEXT, response_json TEXT, etag TEXT, created_ts INTEGER, PRIMARY KEY(tool_name, args_hash))`. L2 TTL default `86400s` (24h), configurable. L2 is OPT-IN via `MCPCACHE_L2_ENABLED=true` (default false — adds DB write overhead).
- [x] **MCPCACHE-03**: Cache invalidation hook — `MCPCache.invalidate(tool_name=None, args=None)` clears matching entries from BOTH layers (scopes: 'all' / 'tool' / 'entry'). Auto-invalidation on dm20 schema version change via `start_schema_version_poller(client, interval_s=60)` — poller gracefully disables itself if `dm20__schema_version` returns 4xx. KPIs added: `eldritch.mcp.cache` and `eldritch.mcp.cache.invalidation` spans via Phase 11 OTel + Phase 13 span buffer (dual-sink, honors `OBSERVABILITY_ENABLED`).

### CHARCACHE — Persistent character cache (Phase 17)

- [x] **CHARCACHE-01**: Character snapshots cached in `~/.eldritch/character_cache.sqlite` (lazy aiosqlite WAL, NOT routed through Phase 1 WriterQueue). Schema D-120: `(character_id PRIMARY KEY, snapshot_json, etag, last_seen_ts, refreshed_ts)`. Snapshots survive bot restarts (proven by `test_cache_survives_repo_recreation`). `CharacterSnapshot` pydantic model with `extra="forbid"` enforces a hard-coded static-fields-only allow-list (D-125) — combat-mutable state (`current_hp`, `current_conditions`, …) is silently stripped by the projector AND rejected at write time. Allow-list: 14 fields pinned in `test_allowed_snapshot_fields_membership_snapshot`. Provided by `eldritch_dm.persistence.character_cache.CharacterCacheRepo`.
- [x] **CHARCACHE-02**: Synthetic SHA-256 ETag over canonical JSON of the latest dm20 response (D-122 — dm20's MCP surface has no HTTP ETag headers, synthetic is the primary path, not a fallback). `get_or_fetch(character_id, fetcher)` returns cached on ETag match (no schema rewrite) and refreshes on mismatch. Counters: `hits_etag`, `misses`, `etag_match_rate`.
- [x] **CHARCACHE-03**: TTL short-circuit (D-123) via `CHARCACHE_TTL_S` (PositiveInt, default 3600s). Inside TTL → return cached without calling the fetcher (true zero-network hit, `hits_ttl` counter). Outside TTL → fall through to ETag-refresh path. Operator CLI `eldritch-dm-cache-clear --characters [--character-id ID] [--dry-run]` on PATH (Phase 9 argparse pattern). KPIs: `eldritch.character_cache.lookup` + `eldritch.character_cache.invalidation` spans via Phase 11/13 dual-sink (OBSERVABILITY_ENABLED honored, no BufferRow schema extension — attrs mapped onto existing columns).

### NARRCACHE — Narration response cache (Phase 18)

- [x] **NARRCACHE-01**: OPT-IN narration cache (default OFF) — `NARRCACHE_ENABLED=true` to enable. Keyed on `(model_id, system_prompt_hash, user_prompt_hash, max_tokens)`. SHA-256 prompt hashes. Stored at `~/.eldritch/narration_cache.sqlite`. **Hard constraint**: only narration responses (free-form text) are cacheable. ANY response that includes mechanical effects (HP changes, condition applications, dice results) MUST bypass the cache — verified by a content-classifier that rejects responses matching a regex set for HP/AC/damage patterns.
- [x] **NARRCACHE-02**: Mechanical-honesty guard — `NarrCacheGate` class with `is_pure_narration(response_text: str) -> bool` static method that returns False on any line matching: `\b(HP|AC|damage|dmg|hit points|saves? against|takes \d+|deals \d+)\b` (case-insensitive). Cache stores are gated through this — fail-CLOSED (don't cache when uncertain). 50-scenario test corpus split 50/50 between cacheable narration and non-cacheable mechanical text.
- [x] **NARRCACHE-03**: Operator off-switch + observability — `eldritch-dm-cache-disable --narration` flips a runtime override that disables narration cache without restart. KPI `eldritch_narrcache_hit_rate` gauge + `eldritch_narrcache_rejected_count` (responses bypassed by `NarrCacheGate`) via Phase 11 OTel spans. `eldritch-dm-cache-stats --narration` CLI reports hit rate + cost-savings estimate (using Phase 13's cost calculator).

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
