---
phase: 17-character-cache
plan: 17-02
requirements_completed: [CHARCACHE-03]
subsystem: persistence
tags: [cache, cli, ttl, kpi, observability]
requires: [17-01]
provides: [eldritch-dm-cache-clear CLI, CharacterCacheMetrics, traced_character_cache spans]
affects: [pyproject.toml [project.scripts], REQUIREMENTS.md]
tech-stack-added: []
key-files-created:
  - src/eldritch_dm/tools/cache_clear.py
  - tests/tools/test_cache_clear.py
key-files-modified:
  - pyproject.toml
  - .planning/REQUIREMENTS.md
decisions:
  - D-123 / D-124 / D-126 implemented per CONTEXT
  - "TTL short-circuit + KPI spans were wired in 17-01's commit because get_or_fetch is monolithic — 17-02 ties them off with the operator CLI surface and ticks REQUIREMENTS."
  - "CLI scope is intentionally narrow (--characters only) for v1.5. Future versions will add --mcp for Phase 16 invalidation."
metrics:
  duration: ~15 minutes
  tasks: 6
  tests-added: 7 (CLI)
status: complete
  - CHARCACHE-03
---

# Phase 17 Plan 02: TTL fallback + eldritch-dm-cache-clear CLI + KPIs

## One-liner

`eldritch-dm-cache-clear --characters [--character-id ID] [--dry-run]` lands on PATH as the operator escape-hatch for the Phase 17 character cache; TTL short-circuit (default 3600s) gives zero-network hits inside the window; KPIs flow through the Phase 11/13 dual-sink span buffer with no schema extension.

## What shipped

### TTL short-circuit (D-123)

Inside `CharacterCacheRepo.get_or_fetch`:

```
if row and (now - row.refreshed_ts) <= CHARCACHE_TTL_S:
    bump last_seen_ts; counters.hits_ttl += 1; return cached  # NO fetcher call
```

The fetcher is NEVER invoked on a TTL hit. `CHARCACHE_TTL_S` is `PositiveInt` (default 3600s); operators force a refresh via the CLI rather than `TTL=0` (which the type rejects). Proven by `test_ttl_hit_skips_fetcher` — the fetcher inside the test raises `AssertionError` and the test still passes because the fetcher is never reached.

### `eldritch-dm-cache-clear` CLI

```
$ eldritch-dm-cache-clear --characters --dry-run
DRY-RUN: would remove 3 row(s) from ~/.eldritch/character_cache.sqlite

$ eldritch-dm-cache-clear --characters --character-id char-abc
Removed 1 row(s) from ~/.eldritch/character_cache.sqlite matching character_id=char-abc

$ eldritch-dm-cache-clear --characters
Removed 3 row(s) from ~/.eldritch/character_cache.sqlite
```

- Argparse mirrors the Phase 9 `eldritch-dm-backfill-pc-classes` shape.
- `--dry-run` opens SQLite via `file:...?mode=ro` URI — writes are driver-impossible.
- Exit codes: `0=ok`, `1=user error (missing file / no scope)`, `3=fatal (DB locked)`.
- Wired into `pyproject.toml`:
  ```toml
  eldritch-dm-cache-clear = "eldritch_dm.tools.cache_clear:main"
  ```
- 7 tests in `tests/tools/test_cache_clear.py` (CLI runs in a separate thread via `concurrent.futures.ThreadPoolExecutor` so its `asyncio.run()` doesn't collide with pytest-asyncio's running loop).

### KPI emission (Phase 11/13 dual-sink)

Two spans, already added in 17-01 (the build was monolithic — the `_BufferingSpan._build_row` attribute mapping was settled in one go):

- **`eldritch.character_cache.lookup`** — emitted from every `get_or_fetch`. Attributes: `character_id`, `layer` (`ttl_hit`|`etag_match`|`miss`), `size`, `latency_ms`.
- **`eldritch.character_cache.invalidation`** — emitted from `invalidate()`. Attributes: `scope` (`all`|`entry`), `character_id`, `entries_removed`.

`BufferRow` attribute mapping (no schema extension):

| Cache attribute | BufferRow column |
|---|---|
| `eldritch.character_cache.character_id` | `monster_id` |
| `eldritch.character_cache.layer` / `invalidation.scope` | `driver_path` |
| `eldritch.character_cache.size` / `invalidation.entries_removed` | `combat_round` |
| `eldritch.character_cache.latency_ms` | `latency_ms` |

Verified by `test_lookup_span_recorded` (3 calls → 3 rows with layers `[miss, ttl_hit, ttl_hit]`) and `test_invalidation_span_recorded`.

### `CharacterCacheMetrics`

```python
class CharacterCacheMetrics(BaseModel, frozen=True, extra="forbid"):
    hits_ttl: int
    hits_etag: int
    misses: int
    size: int                # await SELECT COUNT(*)
    invalidations_total: int
    etag_match_rate: float   # hits_etag / (hits_etag + misses); 0.0 if denom = 0
```

Verified by `TestMetrics::test_etag_match_rate` (1 MISS + 1 match + 1 mismatch → rate = 1/3).

## Deviations from Plan

### 1. [Rule 3 — Blocking issue] `asyncio.run()` collides with pytest-asyncio loop

- **Found during:** First CLI test run.
- **Issue:** `main()` calls `asyncio.run(_run(args))`. Pytest-asyncio's auto mode means the test itself runs inside an event loop already. `asyncio.run()` then raises `RuntimeError: asyncio.run() cannot be called from a running event loop`.
- **Fix:** `tests/tools/test_cache_clear.py::run_cli(argv)` helper submits `main(argv)` to a single-worker `ThreadPoolExecutor` so the CLI's `asyncio.run()` spins up its own loop in a fresh thread. The sync test `test_missing_cache_file_returns_user_error` calls `main()` directly since it isn't inside an event loop.
- **Files modified:** `tests/tools/test_cache_clear.py`.

### 2. [Rule 2 — Plan tightening] TTL=0 not exposed; operator escape is the CLI

- **Found during:** Writing TTL tests.
- **Issue:** Plan-text suggested testing `CHARCACHE_TTL_S=0` disables TTL. `PositiveInt` rejects 0, so the field minimum is 1.
- **Fix:** Documented the escape route as "use `eldritch-dm-cache-clear --characters` instead of setting TTL=0". The `test_etag_match_after_ttl_expiry` test uses `CHARCACHE_TTL_S=1` and `monkeypatch`'s `time.time` to fast-forward past TTL, which exercises the fall-through path cleanly.

## Known limitations (per the plan)

- **Level-up / equipment-change staleness window.** The cache caches semi-mutable static fields (`level`, `equipment`, `base_stats`). Without explicit per-mutation invalidation hooks at dm20 level-up / shopping call sites, TTL (default 3600s) is the SOLE freshness mechanism for these events. v1.5 ships with TTL-only; operators force-refresh via `eldritch-dm-cache-clear --characters --character-id ID`. Future phases MAY add explicit `cache.invalidate(character_id)` hooks at those call sites — Phase 16's MCPCache invalidation API is the prior-art pattern.
- **`size` on per-call spans is computed live.** Unlike Phase 16's `size_l2: -1` sentinel, Phase 17 calls a synchronous `SELECT COUNT(*)` from the awaiting context manager. The table is small enough (one row per active PC) that the COUNT is cheap; if this becomes a hot-path concern, mirror the Phase 16 sentinel pattern.

## Verification snapshot

| Check | Result |
|---|---|
| `uv run pytest tests/tools/test_cache_clear.py -q` | 7 passed |
| `uv run pytest tests/persistence/test_character_cache.py -q` | 52 passed |
| `uv run pytest tests/persistence tests/observability tests/tools tests/test_config.py tests/mcp -q` | 361 passed, 9 skipped |
| `uv run ruff check src tests` | clean |
| `uv run lint-imports` | 8/8 contracts kept |
| CHARCACHE-01/02/03 in REQUIREMENTS.md | all `[x]` |

## Self-Check: PASSED

- `src/eldritch_dm/tools/cache_clear.py` exists.
- `tests/tools/test_cache_clear.py` exists with 7 tests.
- `pyproject.toml` registers `eldritch-dm-cache-clear`.
- `.planning/REQUIREMENTS.md` shows three `[x]` marks for CHARCACHE-0[123].
- Commits visible on branch `worktree-agent-aef302b86045a5ae1`.
