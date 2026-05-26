---
phase: 16-mcp-cache
plan: 16-02
requirements_completed: [MCPCACHE-03]
subsystem: mcp
tags: [cache, invalidation, observability, kpi, schema-version]
requires: [16-01]
provides: [MCPCache.invalidate, start_schema_version_poller, MCPCacheMetrics, traced_mcp_cache spans]
affects: [src/eldritch_dm/observability/instrumentation.py, src/eldritch_dm/mcp/__init__.py]
tech-stack-added: []
key-files-modified:
  - src/eldritch_dm/mcp/cache.py
  - src/eldritch_dm/mcp/__init__.py
  - src/eldritch_dm/observability/instrumentation.py
  - tests/mcp/test_cache.py
  - .planning/REQUIREMENTS.md
decisions:
  - D-114 (invalidation triggers) and D-115 (OTel KPIs) implemented per CONTEXT
  - "Reused existing BufferRow fields via attr-key mapping in _BufferingSpan._build_row — no schema extension"
  - "Schema-version poller gracefully disables on MCPToolError (404) — bot startup unaffected"
metrics:
  duration: ~20 minutes
  tasks: 6
  tests-added: 10
status: complete
  - MCPCACHE-03
---

# Phase 16 Plan 02: Invalidation API + schema-version polling + KPI integration

## One-liner

`MCPCache` grew an `invalidate()` API (3 scopes), an opt-in `dm20__schema_version` background poller that auto-wipes on version change (and disables itself if the tool is absent), a `metrics_snapshot()` accessor returning a frozen pydantic model, and two new dual-sink OTel/span-buffer spans (`eldritch.mcp.cache` per call, `eldritch.mcp.cache.invalidation` per wipe).

## What shipped

### Invalidation API

```python
removed = await cache.invalidate()                                # scope='all'
removed = await cache.invalidate(tool_name="dm20__get_class_info")  # scope='tool'
removed = await cache.invalidate(tool_name="X", args={...})       # scope='entry'
```

Returns the count of entries removed across BOTH layers (L1 + L2). Atomic per layer — L1 holds `_l1_lock` during the wipe; L2 commits a single DELETE then `commit()`. Programmer error (`args` without `tool_name`) raises `ValueError`.

### Schema-version poller

```python
task = cache.start_schema_version_poller(client, interval_s=60.0)
# ... bot runs ...
await cache.stop_schema_version_poller()
```

- Background `asyncio.Task` keyed on an internal `asyncio.Event` so `stop_schema_version_poller()` wakes the task immediately (no 60s shutdown lag).
- Initial poll establishes baseline. Subsequent polls compare `response["version"]`; on change → full wipe (scope='schema_version') + structured `mcp_cache_schema_version_changed` log.
- **Graceful degradation**: if the very first poll returns `MCPToolError` (4xx — dm20 doesn't expose the tool), the task logs `mcp_cache_schema_poller_disabled` and exits cleanly. Non-fatal network errors (timeout, 5xx) are logged via `mcp_cache_schema_poll_failed` and the loop continues.
- `stop_schema_version_poller()` is idempotent (safe to call without start).

### KPI emission (dual-sink: Phase 11 OTel + Phase 13 span buffer)

Two new spans added to `src/eldritch_dm/observability/instrumentation.py`:

- **`eldritch.mcp.cache`** — emitted from every `MCPCache.call(...)`. Attributes: `tool_name`, `cache.layer` (`l1`|`l2`|`miss`|`bypass`), `cache.size_l1`, `cache.size_l2`, `cache.latency_ms`.
- **`eldritch.mcp.cache.invalidation`** — emitted from `invalidate()` and the schema-version wipe. Attributes: `invalidation.scope`, `invalidation.tool_name`, `invalidation.entries_removed`.

**No schema extension** to `BufferRow` — attribute keys are mapped onto existing columns inside `_BufferingSpan._build_row`:

| Cache attribute | BufferRow column |
|---|---|
| `eldritch.mcp.tool_name` | `model` |
| `eldritch.mcp.cache.layer` / `invalidation.scope` | `driver_path` |
| `eldritch.mcp.cache.size_l1` / `invalidation.entries_removed` | `combat_round` |
| `eldritch.mcp.cache.size_l2` | `tokens_input` (-1 sentinel on hot path) |
| `eldritch.mcp.cache.latency_ms` | `latency_ms` |

This keeps the 11 existing `test_span_buffer.py` schema canaries green.

### Metrics snapshot

```python
class MCPCacheMetrics(BaseModel):
    hits_l1: int
    misses_l1: int
    hits_l2: int
    misses_l2: int
    bypass_count: int
    size_l1: int
    size_l2: int  # -1 sentinel when L2 disabled
    invalidations_total: int
```

`await cache.metrics_snapshot()` is the authoritative source for L2 size (the per-call span uses a `-1` sentinel because a sync `SELECT COUNT(*)` is not safe on the hot path).

## Tests added (10)

- `test_invalidate_all_clears_both_layers` (with L2 enabled — verifies returned count = L1+L2 sum)
- `test_invalidate_by_tool_only_clears_that_tool`
- `test_invalidate_by_tool_and_args_single_entry`
- `test_invalidate_args_without_tool_raises`
- `test_schema_version_poller_wipes_on_change` (uses `interval_s=0.05`, asserts L1 cleared within 0.25s)
- `test_schema_version_poller_disables_on_404` (asserts task `done()` within 0.1s and subsequent cache calls still work)
- `test_stop_poller_is_idempotent`
- `test_metrics_snapshot_shape`
- `test_traced_span_emitted_per_call` (3 calls → 3 rows in span buffer with layers `[bypass, l1, miss]`)
- `test_invalidation_span_emitted` (scope='all', entries_removed=1)

**Total cache tests across 16-01 + 16-02: 38** — exceeds success-criteria minimum of 20.

## Deviations from Plan

### 1. [Rule 1 — Bug] `size_l2` on per-call span is a sentinel, not authoritative

- **Found during:** Task 02 implementation.
- **Issue:** The per-call span runs on the asyncio hot path and cannot `await SELECT COUNT(*)` synchronously inside `set_attribute(...)`. A naive impl would block or report stale values.
- **Fix:** `eldritch.mcp.cache.size_l2` is always stamped as `-1` on per-call spans. The authoritative source is `await cache.metrics_snapshot()`, which performs the COUNT(*) and is what Prometheus / KPI exporters should call.
- **Files modified:** `src/eldritch_dm/mcp/cache.py` (`_stamp_cache_span`).

### 2. [Rule 2 — Critical correctness] Schema-poller `aclose()` ordering

- **Found during:** Task 02 implementation.
- **Issue:** `aclose()` originally only closed the L2 connection. If the schema-version poller was still running, it would continue calling `client.call()` after the connection was closed, causing spurious errors.
- **Fix:** `aclose()` now calls `stop_schema_version_poller()` first, then closes L2.
- **Files modified:** `src/eldritch_dm/mcp/cache.py`.

## Verification snapshot

| Check | Result |
|---|---|
| `uv run pytest tests/mcp tests/observability tests/test_config.py -q` | 200 passed, 7 skipped |
| `uv run pytest tests/mcp/test_cache.py -q` | 38 passed |
| `uv run lint-imports` | 8/8 contracts kept |
| `uv run ruff check src tests` | clean |
| MCPCACHE-01/02/03 in REQUIREMENTS.md | all `[x]` |

## Self-Check: PASSED

- 16-02-SUMMARY.md exists at `.planning/phases/16-mcp-cache/16-02-SUMMARY.md`
- Commits visible on branch `worktree-agent-aba36c527f6bc66b0` (`git log --oneline`)
- 38 cache tests visible in pytest output
- REQUIREMENTS.md shows three `[x]` marks for MCPCACHE-0[123]
