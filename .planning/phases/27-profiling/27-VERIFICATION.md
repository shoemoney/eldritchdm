# Phase 27 — Verification

## Plans completed

- **27-01** — Hot-path profiler script + v1.9.0 baseline JSON (PROFILE-01, PROFILE-03)
- **27-02** — `docs/PERFORMANCE.md` per-operation budget table (PROFILE-02)

## Success criteria (from objective)

- [x] 27-01-PLAN.md + 27-02-PLAN.md committed
      (`fffb95a docs(27): plans 27-01 and 27-02 — profiler + PERFORMANCE.md budget table`)
- [x] `scripts/perf/profile_hot_paths.py` runs all 6 hot paths
      (with 3 sub-paths each for `mcp-cache-roundtrip` + `smart-driver-oracle`)
- [x] Output JSON validates against the D-209 schema
      (verified by `scripts.perf._schema.BaselineSchema.model_validate` —
      both at write-time inside `main()` and at re-validate-time inside the
      self-check test)
- [x] `tests/perf/test_profiler_self_check.py` smoke-tests the profiler
      (2 passed in 0.51 s under `RUN_STRESS=1`)
- [x] `.planning/perf-baseline-v1.9.0.json` committed
      (commit `90aa613`, 10 operations, ~7 KB)
- [x] `docs/PERFORMANCE.md` with per-operation budget table + WARN(110%)/FAIL(125%) thresholds
      (commit `d3072a5`)
- [x] Profiler completes in ≤120s wallclock — **observed: 1.1 s**
- [x] `ruff check .` clean
- [x] `lint-imports` clean — 8 contracts kept, 0 broken
- [x] Zero regression in existing 1655-test suite
      (`pytest -q -x` → 1655 passed, 13 skipped, 0 failures)
- [x] PROFILE-01/02/03 ticked `[x]` in `.planning/REQUIREMENTS.md`
- [x] 27-01-SUMMARY.md + 27-02-SUMMARY.md + 27-VERIFICATION.md committed
- [x] No STATE.md or ROADMAP.md edits (per objective)

## Hard constraints (from objective)

- [x] Profile OUR CODE, NOT network/dm20/LLM — all paths use respx-mocked
      dm20 + AsyncMock LLM/Discord + monkeypatched OCR. No real
      `omlx`/dm20 process is required for the profiler to run.
- [x] Mock dm20 via respx (Phase 12 pattern) — `respx.mock(...)` blocks
      route `POST http://localhost:8765/v1/mcp/execute` per-path.
- [x] NO real LLM calls — `character-ingest-fast-path` and
      `ingest-pipeline-ocr` route to a respx-mocked
      `http://localhost:8080/v1/chat/completions`; `smart-driver-oracle`
      uses an `AsyncMock`-stubbed `chat.completions.create`.
- [x] 6 hot paths per D-206 with sub-paths where applicable — 10
      total operation keys in the baseline JSON.
- [x] Output JSON schema per D-209 — `BaselineSchema` (pydantic v2) +
      `OperationStats` enforce `{version, git_sha, generated_at,
      operations: {name: {p50_ms, p95_ms, p99_ms, iterations,
      cprofile_top_10}}}`.
- [x] 100 wall-clock iterations populate p50/p95/p99 (separate from
      cProfile run per advisor #1 — sharing them would have made the
      percentile numbers garbage).
- [x] `cprofile_top_10` populated by a separate cProfile pass (20 iter
      by default) — formatted as `module.func:lineno (cumtime_pct)`.
- [x] Baseline committed at `.planning/perf-baseline-v1.9.0.json` —
      NOT auto-rotated. Re-run + manual-commit guidance documented in
      `docs/PERFORMANCE.md`.
- [x] Profiler completes in ≤120 s wallclock — 1.1 s observed (×100 budget headroom).
- [x] Zero regression in existing 1655-test suite — verified.

## Commits

| Commit | Subject |
|---|---|
| `b04f0fa` | docs(27): Phase 27 CONTEXT — profiling + latency budgets (D-206..D-214)¹ |
| `fffb95a` | docs(27): plans 27-01 and 27-02 — profiler + PERFORMANCE.md budget table |
| `f7818a4` | feat(27-01): hot-path profiler script + JSON schema (PROFILE-01) |
| `90aa613` | feat(27-01): commit v1.9.0 baseline + self-check tests + os._exit fix (PROFILE-01, PROFILE-03) |
| `d3072a5` | docs(27-02): docs/PERFORMANCE.md per-operation budget table (PROFILE-02) |
| (+ this commit) | docs(27): SUMMARYs + REQUIREMENTS.md ticks + VERIFICATION |

¹ Pre-existing CONTEXT from the spawn-time base; included for context.

## Notable deviations (Rule 1-3 auto-fixes)

**1. [Rule 3 - Blocking] `riposte_timers` FK constraint failed at insert
time.** Bare `RiposteTimerRepo.insert(...)` fails against a freshly-
bootstrapped DB because `riposte_timers.channel_id REFERENCES
channel_sessions(channel_id)`. Fixed by inserting the parent
`channel_sessions` row via `ChannelSessionRepo.upsert` once at
setup-time, mirroring the Phase 25 stress-test pattern. (Commit 90aa613,
documented in 27-01-SUMMARY.md.)

**2. [Rule 3 - Blocking] Self-check test deadlocked on subprocess pipe
buffer.** The profiler emits a large volume of structlog INFO output
(~23 KB for a 5-iter run, vastly more at 100 iter). With
`subprocess.run(capture_output=True)` the kernel pipe buffer caps at
~64 KiB and the writer blocks. Fixed by (a) redirecting stdout/stderr
to files in the test, and (b) `os._exit(rc)` at the bottom of
`main()` — necessary because `aiosqlite.WriterQueue` and
`structlog`'s span-buffer sqlite handle install non-daemon shutdown
hooks that block normal interpreter exit. Both safe: the JSON is
already written and the script holds no user-facing resources. (Commit
90aa613, documented in 27-01-SUMMARY.md.)

No Rule 4 (architectural) deviations.

## Out-of-scope (deferred to Phase 28)

- `eldritch-dm-perf-baseline` CLI — TUNE-02. Adds
  `[project.scripts]` entry, consumes our baseline JSON, applies the
  WARN/FAIL thresholds documented in `docs/PERFORMANCE.md`, exits
  0/1/2 per Phase 28 contract.

## Snapshot — observed v1.9.0 p99 (M3 Ultra, all backends mocked)

```
character-ingest-fast-path                         p50=0.565ms p99=1.084ms
combat-turn-resolution                             p50=0.437ms p99=0.606ms
ingest-pipeline-ocr                                p50=1.061ms p99=1.446ms
mcp-cache-roundtrip.l1-hit                         p50=0.007ms p99=0.020ms
mcp-cache-roundtrip.l1-l2-miss                     p50=0.170ms p99=0.332ms
mcp-cache-roundtrip.l1-miss-l2-hit                 p50=0.007ms p99=0.085ms
riposte-click-handler                              p50=2.481ms p99=3.573ms
smart-driver-oracle.cache-hit                      p50=0.012ms p99=0.014ms
smart-driver-oracle.smart-fallback-to-random       p50=0.087ms p99=0.130ms
smart-driver-oracle.smart-success                  p50=0.091ms p99=0.118ms
```

All 10 operations are >50× under their `docs/PERFORMANCE.md` target —
intentional headroom so a Rule-1 correctness fix that costs latency
doesn't immediately trip the Phase 28 CLI.
