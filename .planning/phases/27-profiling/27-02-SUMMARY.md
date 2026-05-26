---
phase: 27-profiling
plan: 27-02
requirements_completed: [PROFILE-02]
subsystem: docs
tags: [perf, docs, budgets, regression-thresholds]
dependency_graph:
  requires: [27-01-baseline]
  provides: [docs-performance-md]
  affects: [phase-28-tune-cli]
tech_stack:
  added: []
  patterns: [target-vs-observed-table, warn-fail-thresholds]
key_files:
  created:
    - docs/PERFORMANCE.md
  modified: []
decisions:
  - WARN at 110% / FAIL at 125% of target — matches Phase 28 TUNE-02
    exit codes 0/1/2 by construction so the doc and the CLI agree.
  - Observed-p99 column populated from the committed v1.9.0 baseline
    JSON rather than re-running the profiler. Single source of truth.
  - Operator-tunable network budgets (dm20 RTT, ShoeGPT inference,
    Discord ack, embed batching) get their own section to make it
    explicit which layer to investigate when user-facing latency is
    bad but our hot paths are within budget.
  - Re-run + commit guidance explicitly forbids "commit new baseline
    to silence a WARN/FAIL". That's exactly the signal that should
    not be quieted by hand (D-212).
metrics:
  duration_minutes: ~15
  completed_date: 2026-05-25
---

# Phase 27 Plan 02: docs/PERFORMANCE.md per-operation budget table (PROFILE-02) Summary

One-liner: shipped `docs/PERFORMANCE.md` — the single doc operators read
to reason about EldritchDM latency. 10-row budget table (6 hot paths,
4 of which expand into sub-paths) with target p99, observed v1.9.0 p99
(from the committed baseline), OK/WARN/FAIL thresholds (110%/125%
matching Phase 28 TUNE-02 exit codes), and per-operation measurement
methodology.

## What shipped

### PROFILE-02 — docs/PERFORMANCE.md

7 sections:

1. **Purpose** — explicit scope boundary (our code only; dm20/LLM/Discord
   are out-of-scope per D-207, D-213).
2. **Hot paths** — bulleted list of the 6 paths with sub-path expansion.
3. **Budget table** — 10 operations × `{target p99, observed v1.9.0 p99,
   OK/WARN/FAIL thresholds, methodology}`. Observed values pulled directly
   from `.planning/perf-baseline-v1.9.0.json`. Plus a cProfile-top-10
   subsection showing how to read the per-operation breakdown when
   investigating a regression.
4. **Thresholds** — explicit math (`110%` WARN, `125%` FAIL) + CLI
   exit-code mapping (0/1/2).
5. **Operator-tunable network budgets** (D-207) — table of the 4
   out-of-scope layers (dm20 RTT, ShoeGPT inference, Discord ack, embed
   batching) with where-to-tune-it hints. This is the section that
   answers "user-facing latency is bad but the perf-baseline CLI is
   green — where do I look?".
6. **Re-running the profiler** — one-liner invocations + when-to-commit
   guidance (D-212 — manual, deliberate; don't auto-rotate to silence
   alerts).
7. **References** — back-links to CONTEXT D-206..D-214, Phase 27 Plan 01
   SUMMARY, Phase 28 TUNE-02, PROJECT.md performance constraints.

### Targets derived from PROJECT.md constraints

| Operation | Target p99 | Rationale |
|---|---:|---|
| combat-turn-resolution                       |  500 ms | Inner chain of Discord-ack <3s constraint, with ample headroom |
| mcp-cache-roundtrip.l1-hit                   |    1 ms | LRU memory access must be sub-ms |
| mcp-cache-roundtrip.l1-miss-l2-hit           |   10 ms | SQLite WAL read must beat the lower bound of dm20 RTT |
| mcp-cache-roundtrip.l1-l2-miss               |   50 ms | Bound by dm20 RTT (mocked here) |
| smart-driver-oracle.smart-success            |  100 ms | Slim-context + JSON parse + validate inside D-54's 1500ms LLM ceiling |
| smart-driver-oracle.smart-fallback-to-random |    5 ms | Parse-fail must be fast (fail-soft contract) |
| smart-driver-oracle.cache-hit                |    1 ms | Per-round LRU cache must be sub-ms |
| character-ingest-fast-path                   |   50 ms | Slice of the 6s end-to-end ingest budget excluding real LLM |
| ingest-pipeline-ocr                          |  100 ms | Slice of the 6s end-to-end ingest budget excluding real OCR + LLM |
| riposte-click-handler                        |  200 ms | Slice of the 3s Discord-ack budget excluding real Discord HTTP |

All 10 observed p99 values currently sit at 0.5%-1.8% of target — large
headroom is intentional so a Rule-1 correctness fix that costs latency
doesn't immediately trip the regression CLI.

## Deviations from Plan

None — the plan was a straight write-the-doc task and the executor
followed it.

## Auth gates

None.

## Known Stubs

None.

## Verification

- `ruff check .` — All checks passed (no Python in the docs change).
- `lint-imports` — n/a (doc-only change).
- File renders correctly as Markdown with all 10 budget rows + cross-
  references to the v1.9.0 baseline JSON.
- Existing test suite: zero regression (verified in Plan 27-01 commit
  90aa613 — same tree state).

## Self-Check: PASSED

- FOUND: `docs/PERFORMANCE.md` (169 lines, 1 file changed)
- FOUND commit `d3072a5`: docs(27-02): docs/PERFORMANCE.md per-operation
  budget table (PROFILE-02)
