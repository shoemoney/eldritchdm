---
phase: 18-narration-cache
plan: 18-02
subsystem: observability
tags: [narration-cache, runtime-override, cli, observability, savings-kpi]
requirements: [NARRCACHE-03]
status: complete
completed: 2026-05-25
---

# Phase 18 Plan 18-02: Runtime override + savings observability + CLIs — Summary

## One-liner

Operator-facing surface for the narration cache: a process-wide runtime
override singleton, a `traced_narrcache` dual-sink span with `savings_usd`
KPI on hit, and two CLIs — `eldritch-dm-cache-disable --narration` for
runtime flip and `eldritch-dm-cache-stats --narration` for aggregating
hit-rate + cost savings from the Phase 13 span buffer.

## What landed

- `src/eldritch_dm/observability/narrcache_runtime.py` —
  `NarrCacheRuntimeOverride` singleton + `threading.RLock`. Idempotent
  `disable()` / `enable()`. `NarrCacheOverrideSnapshot` for read-only views.
- `src/eldritch_dm/observability/instrumentation.py` — new
  `traced_narrcache(*, model)` context manager. `_to_row` extended to map
  `eldritch.narrcache.{layer,size,latency_ms,model,savings_usd}` onto
  existing `BufferRow` columns (no schema migration; reuses
  `model`/`driver_path`/`combat_round`/`latency_ms`/`overall_score`).
- `src/eldritch_dm/observability/narration_cache.py` — `NarrCache.acompletion`
  now wraps every call in `traced_narrcache`, stamps `layer ∈ {bypass,
  hit, miss, gate_reject_store, gate_reject_serve}`, and on hit computes
  `savings_usd` via Phase 13's `calculate_cost(model, in, out, table)`.
  Also consults `get_narrcache_override().is_disabled()` so the CLI flip
  takes effect on the next call.
- `src/eldritch_dm/tools/cache_disable.py` — `eldritch-dm-cache-disable
  --narration [--enable] [--reason TEXT]` CLI.
- `src/eldritch_dm/tools/cache_stats.py` —
  `eldritch-dm-cache-stats --narration [--since YYYY-MM-DD]
  [--until YYYY-MM-DD] [--format markdown|json] [--buffer-path PATH]`.
- `pyproject.toml` — two new `project.scripts` entries.
- 27 new tests across `tests/observability/test_narrcache_runtime.py`
  (9), `tests/observability/test_narrcache_spans.py` (6),
  `tests/tools/test_cache_disable.py` (5), and
  `tests/tools/test_cache_stats.py` (7). Plus the +1 TTL clock fix in
  `tests/observability/test_narration_cache.py`.

## Verification

- ruff check + ruff format: clean
- lint-imports: 8 contracts kept, 0 broken
- `pytest tests/observability/ tests/eval/ tests/tools/`: 343 + 12 = 355 passing
- end-to-end span emission verified for every layer (`miss`, `hit`,
  `gate_reject_store`, `gate_reject_serve` indirectly via the chain,
  `bypass`) — see `tests/observability/test_narrcache_spans.py`

## Deviations from PLAN

None for 18-02. The Plan 18-01 D-138 obsolescence (no in-repo narration
call site to wire) is the only deviation for the whole phase and is fully
documented in 18-01-SUMMARY.md + 18-VERIFICATION.md.

## Key files

### Created
- `src/eldritch_dm/observability/narrcache_runtime.py`
- `src/eldritch_dm/tools/cache_disable.py`
- `src/eldritch_dm/tools/cache_stats.py`
- `tests/observability/test_narrcache_runtime.py`
- `tests/observability/test_narrcache_spans.py`
- `tests/tools/test_cache_disable.py`
- `tests/tools/test_cache_stats.py`

### Modified
- `src/eldritch_dm/observability/instrumentation.py` — `traced_narrcache` ctx mgr + `_to_row` narrcache mapping
- `src/eldritch_dm/observability/narration_cache.py` — span emission + savings calc + runtime-override consultation
- `tests/observability/test_narration_cache.py` — TTL test now uses a settable clock to survive multiple `time.monotonic()` calls
- `pyproject.toml` — two new `project.scripts` entries
- `.planning/REQUIREMENTS.md` — ticked NARRCACHE-03

## Commits

| Commit | Description |
|--------|-------------|
| `8dc4eca` | feat(18-02): NarrCacheRuntimeOverride singleton + bypass wiring |
| `e2f0f5f` | feat(18-02): traced_narrcache span + savings_usd KPI on hit |
| `04a99f1` | feat(18-02): eldritch-dm-cache-disable + eldritch-dm-cache-stats CLIs |
| (this commit) | docs(18-02): mark NARRCACHE-03 + write 18-02 SUMMARY + 18-VERIFICATION |

## Self-Check: PENDING — run at phase end
