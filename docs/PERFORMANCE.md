# EldritchDM — Performance Budgets & Hot-Path Latency

> **Phase 27 / PROFILE-02 / D-210.**
> Operator reference for per-operation latency budgets, the v1.9.0 baseline,
> and the WARN/FAIL thresholds the Phase 28 `eldritch-dm-perf-baseline` CLI
> uses for regression detection.

---

## Purpose

This doc covers latency budgets for the 6 hot paths inside **our code** —
the parts EldritchDM is directly responsible for. It explicitly does **not**
cover:

- **dm20 MCP RTT** — measured separately; documented in
  [Operator-tunable network budgets](#operator-tunable-network-budgets) below.
- **ShoeGPT / LLM inference latency** — owned by `oMLX` and dm20's own
  metrics; out of scope per D-207, D-213.
- **Discord HTTP round-trip** — owned by `discord.py`'s built-in rate
  limiter; not measurable from our side.

If a hot path exceeds its budget, this doc tells you where to look. If
the actual user-facing latency is bad but our hot paths are within
budget, the regression is almost certainly in one of the three
out-of-scope layers above.

## Hot paths

The 6 hot paths profiled by `scripts/perf/profile_hot_paths.py` (D-206):

1. **`combat-turn-resolution`** — inner dm20-call sequence for a player
   turn: `party_pop_action` → `party_thinking` → `party_resolve_action`.
2. **`mcp-cache-roundtrip`** — Phase 16 MCP cache lookup. 3 sub-paths:
   - `l1-hit` — in-memory LRU hit.
   - `l1-miss-l2-hit` — L1 cold, L2 SQLite cold (cache-cold fast branch).
   - `l1-l2-miss` — cache bypass; full inner call.
3. **`smart-driver-oracle`** — `SmartMonsterDriver._pick_target_llm`.
   3 sub-paths:
   - `smart-success` — LLM mock returns valid `MonsterTacticChoice` JSON.
   - `smart-fallback-to-random` — LLM mock returns garbage → parse fail
     → fail-soft to random.
   - `cache-hit` — per-round LRU `(channel, round, monster)` cache hit.
4. **`character-ingest-fast-path`** — `translate_to_character_sheet` —
   sanitize + LLM call (mocked) + pydantic validate.
5. **`ingest-pipeline-ocr`** — `pipeline.ingest()` over a 50×50 white PNG
   with `ocrmac` monkeypatched + LLM mocked + dm20 verify mocked.
6. **`riposte-click-handler`** — `handle_riposte_click` happy path: real
   SQLite + `SessionLocks` + `RiposteTimerRepo`, AsyncMock interaction.

## Budget table (v1.9.0)

| Operation | Target p99 | Observed p99 (v1.9.0) | OK ≤ | WARN > | FAIL > | Methodology |
|---|---:|---:|---:|---:|---:|---|
| combat-turn-resolution                       |    500 ms  |   0.61 ms | 550 ms  | 550 ms  | 625 ms  | 100-iter wall-clock; respx-mocked dm20; profiles our `mcp_tools` call chain |
| mcp-cache-roundtrip.l1-hit                   |      1 ms  |   0.02 ms |   1.1 ms |   1.1 ms |  1.25 ms | 100-iter wall-clock; pre-populated L1; same args every call |
| mcp-cache-roundtrip.l1-miss-l2-hit           |     10 ms  |   0.09 ms |  11 ms  |  11 ms  | 12.5 ms  | 100-iter wall-clock; L2 enabled but cold-branch |
| mcp-cache-roundtrip.l1-l2-miss               |     50 ms  |   0.33 ms |  55 ms  |  55 ms  | 62.5 ms  | 100-iter wall-clock; cache disabled — measures inner client only |
| smart-driver-oracle.smart-success            |    100 ms  |   0.12 ms | 110 ms  | 110 ms  | 125 ms  | 100-iter wall-clock; AsyncMock OpenAI client returns valid JSON instantly; per-round cache cleared each iter |
| smart-driver-oracle.smart-fallback-to-random |      5 ms  |   0.13 ms |   5.5 ms |   5.5 ms |  6.25 ms | 100-iter wall-clock; AsyncMock returns invalid JSON; measures parse-fail path |
| smart-driver-oracle.cache-hit                |      1 ms  |   0.01 ms |   1.1 ms |   1.1 ms |  1.25 ms | 100-iter wall-clock; per-round LRU primed once; same `(channel, round, monster)` |
| character-ingest-fast-path                   |     50 ms  |   1.08 ms |  55 ms  |  55 ms  | 62.5 ms  | 100-iter wall-clock; respx LLM returns canned valid sheet JSON |
| ingest-pipeline-ocr                          |    100 ms  |   1.45 ms | 110 ms  | 110 ms  | 125 ms  | 100-iter wall-clock; ocrmac monkeypatched + respx LLM + executor pre-warmed |
| riposte-click-handler                        |    200 ms  |   3.57 ms | 220 ms  | 220 ms  | 250 ms  | 100-iter wall-clock; real SQLite + WriterQueue + SessionLocks; AsyncMock Discord interaction |

**Observed p99 source:** `.planning/perf-baseline-v1.9.0.json`, generated
on M3 Ultra with `omlx` idle (no real LLM calls — all backends mocked).
Sanity: 9 of 10 operations are >50× under target. That headroom is
intentional — it gives us room to take a correctness fix that costs
latency without immediately tripping the regression CLI.

### cProfile top-10

Each operation also carries a `cprofile_top_10` field listing the
top-10 functions by cumulative time. Use that to identify *where* time
is being spent when a regression is observed. For example, the current
`character-ingest-fast-path` top-3 is:

1. `translate.translate_to_character_sheet:194` (99.9%)
2. `translate.translate_character_sheet:116` (94.9%)
3. `completions.create:2539` (90.3%)

— confirming that nearly all time is in the openai-client request-build
machinery (mocked LLM returns instantly), not in our sanitize/validate
code. If a future regression shows >50% in `pydantic.validate`, that's a
schema-validation problem; if it shows in `sanitize_player_input`, that's
a sentinel-wrapping problem; etc.

## Thresholds

All thresholds match the Phase 28 `eldritch-dm-perf-baseline` CLI exit
codes (TUNE-02):

| Status | Condition (per-operation p99) | CLI exit |
|---|---|---:|
| **OK**   | `observed ≤ target × 1.10`                        | 0 |
| **WARN** | `target × 1.10 < observed ≤ target × 1.25`        | 1 |
| **FAIL** | `observed > target × 1.25`                         | 2 |

A WARN does not block CI; it asks the operator to investigate. A FAIL
should block — either the regression is real and needs fixing, or the
fix is acceptable and the baseline should be re-committed (see
[Re-running the profiler](#re-running-the-profiler) below).

## Operator-tunable network budgets

The hot-path budget table above measures *our code only*. The full
user-facing latency for any operation also includes:

| Layer | Typical budget | Where it lives | Tuning |
|---|---|---|---|
| **dm20 MCP RTT** | ≤ 5 ms (same host) | `oMLX` `omlx serve` + dm20 in-process | Run dm20 + omlx on the same host (the launchd-supervised default). Add ≤ 5 ms ceiling to `combat-turn-resolution` + each `mcp-cache-roundtrip.l1-l2-miss` if dm20 is over LAN. |
| **ShoeGPT inference (real LLM)** | Depends on prompt — see dm20 metrics | oMLX | The profiler's `smart-driver-oracle.smart-success` does **not** call the real LLM; it measures only our slim-context build + JSON parse + validate. Real-LLM latency is governed by D-54 (≤ 1500 ms timeout) and dm20's `eldritch.tokens.input/output` spans. |
| **Discord ack** | < 3 s (hard) | `discord.py` rate limiter | EDM001 AST lint enforces `interaction.response.defer()` as the first line of every interaction handler, so the Discord ack budget is independent of any hot path here. |
| **Embed update batching** | ≤ 1 edit/sec/msg, 5/5s/channel | `EmbedCoalescer` (Phase 19) | Self-tunes; no operator action needed. |

## Re-running the profiler

```bash
# Default — writes .planning/perf-baseline-v1.9.0.json
python scripts/perf/profile_hot_paths.py

# Faster (no cProfile) — useful for iterating
python scripts/perf/profile_hot_paths.py \
    --output /tmp/perf-test.json \
    --skip-cprofile \
    --iterations 50

# Just one path
python scripts/perf/profile_hot_paths.py \
    --paths smart-driver-oracle \
    --output /tmp/smart.json
```

**When to commit a new baseline (D-212):**

Baseline JSON is **not auto-rotated**. Commit a new
`.planning/perf-baseline-v1.10.0.json` (and bump the `--version` flag)
when:

- You ship a milestone (every v1.X release).
- You **deliberately accept** a regression (a correctness fix that costs
  latency). In that case: regenerate, eyeball the new numbers in this
  table, commit the baseline together with the cause.

Do **not** commit a new baseline to silence a WARN/FAIL. That's exactly
the signal that should not be quieted by hand.

## Self-check

```bash
RUN_STRESS=1 pytest tests/perf/ -v
```

Verifies (a) the profiler still runs cleanly with `--iterations 5`,
(b) the committed v1.9.0 baseline still validates against
`scripts.perf._schema.BaselineSchema`.

## Phase 28 TUNE-01 closure (no targets — Branch B)

**Decision:** Phase 28's TUNE-01 ships as a documented "no targets" closure.
No code changes were made. This mirrors Phase 25's CONC-03 closure (Branch B
when profile-driven analysis finds no work to do).

**Evidence (per-op budget % against Phase 27 baseline):**

| Operation | Target p99 | Observed p99 | % of budget | WARN/FAIL? |
|---|---:|---:|---:|---|
| riposte-click-handler                       | 200 ms | 3.573 ms | 1.79% | NO |
| ingest-pipeline-ocr                         | 100 ms | 1.446 ms | 1.45% | NO |
| character-ingest-fast-path                  |  50 ms | 1.084 ms | 2.17% | NO |
| combat-turn-resolution                      | 500 ms | 0.606 ms | 0.12% | NO |
| mcp-cache-roundtrip.l1-l2-miss              |  50 ms | 0.332 ms | 0.66% | NO |
| smart-driver-oracle.smart-fallback-to-random|   5 ms | 0.130 ms | 2.60% | NO |
| smart-driver-oracle.smart-success           | 100 ms | 0.118 ms | 0.12% | NO |
| mcp-cache-roundtrip.l1-miss-l2-hit          |  10 ms | 0.085 ms | 0.85% | NO |
| mcp-cache-roundtrip.l1-hit                  |   1 ms | 0.020 ms | 2.04% | NO |
| smart-driver-oracle.cache-hit               |   1 ms | 0.014 ms | 1.41% | NO |

**Honesty clause (D-215):** Every operation is ≥45× under its target. None
are in WARN or FAIL. The empirical bar from D-216 — "≥10% p99 reduction OR
move out of WARN/FAIL category" — cannot be satisfied for any operation
because there is no meaningful, user-observable benefit to chase:

- Discord ack budget is 3 s; our slowest op (riposte-click) is 0.12% of it.
- Character ingest budget is 6 s; our pipeline-ocr op is 0.024% of it.
- Narration budget (D-54) is 1500 ms; our smart-driver fast path is 0.008%
  of it.

The codebase being fast is the **correct** result. Manufacturing
optimization work to avoid acknowledging that violates the D-215 honesty
clause. If a future change (correctness fix, new feature) regresses any
of these p99s by ≥10% or pushes it into WARN/FAIL, the Phase 28 TUNE-02
CLI will detect it; only then should optimization work resume.

**Forward look:** TUNE-02 (`eldritch-dm-perf-baseline` CLI) and TUNE-03
(`.github/workflows/perf.yml` CI integration) ship in Plan 28-02 regardless
of TUNE-01 — they're regression-detection infrastructure that protects the
already-fast baseline.

## References

- **Phase 27 CONTEXT** — `.planning/phases/27-profiling/27-CONTEXT.md`
  (D-206 .. D-214).
- **Phase 27 Plan 01 SUMMARY** —
  `.planning/phases/27-profiling/27-01-SUMMARY.md` (profiler + baseline).
- **Phase 28 TUNE-02** — the regression-detection CLI consuming this
  baseline. Adds `eldritch-dm-perf-baseline` to `[project.scripts]`.
- **PROJECT.md performance constraints** — the source of the
  user-facing budgets the per-operation targets are derived from.
- **`.planning/REQUIREMENTS.md`** — PROFILE-01, PROFILE-02, PROFILE-03.
