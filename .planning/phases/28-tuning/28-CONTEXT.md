---
phase: 28-tuning
milestone: v1.9
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - TUNE-01 (top 3 optimizations — IF profile shows real targets)
  - TUNE-02 (eldritch-dm-perf-baseline CLI)
  - TUNE-03 (CI integration .github/workflows/perf.yml)
---

# Phase 28 — Targeted optimizations + regression-detection (CONTEXT)

## Mission

Use Phase 27's baseline to (a) identify and fix top 3 slowest operations IF they have material headroom against budget, and (b) ship the `eldritch-dm-perf-baseline` CLI + CI integration for regression-detection going forward.

## Baseline Findings (Phase 27 output)

All 10 baselined operations are p99 < 4ms. Slowest:
- riposte-click-handler: 3.573ms p99
- ingest-pipeline-ocr: 1.446ms p99
- character-ingest-fast-path: 1.084ms p99
- combat-turn-resolution: 0.606ms p99
- mcp-cache l1-l2-miss: 0.332ms p99
- (everything else < 0.2ms p99)

**Honest assessment:** the codebase is already fast. There's no operational user-visible latency to chase — Discord ack is 3s, character ingest budget is 6s, narration is 1500ms. Our SLOWEST operation (riposte-click) is 0.12% of its budget (3.5ms / 3000ms Discord ack).

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-215** | **TUNE-01 may be a Branch B no-op** like Phase 25's CONC-03. Profile-driven optimization rule applies: don't speculate. If no operation has material headroom against its budget, TUNE-01 ships a documented "no targets — codebase already within budget" closure. | Honest-report — don't churn code that's already fine |
| **D-216** | **If TUNE-01 has targets**: each optimization needs (a) profile-evidence BEFORE, (b) the change, (c) profile AFTER showing measurable improvement (≥10% p99 reduction OR move out of WARN/FAIL category), (d) regression-guard test. NO speculative optimization. | Empirical bar |
| **D-217** | **TUNE-02 always ships** regardless of TUNE-01 outcome — the CLI is forward-looking (regression-detection on NEW changes), not retrospective. | Independent value |
| **D-218** | **CLI shape**: `eldritch-dm-perf-baseline [--baseline PATH] [--output PATH] [--limit-iterations N]`. Default --baseline points to `.planning/perf-baseline-v1.9.0.json`. Exit codes: 0 (within ±10% of baseline on all p99s), 1 (one or more p99 > +10%), 2 (one or more p99 > +25% — critical). Mirrors Phase 12 `eldritch-dm-eval` --baseline pattern. | Familiar CLI shape |
| **D-219** | **CI integration (TUNE-03)**: `.github/workflows/perf.yml` runs on schedule (weekly Sunday 02:00 UTC) + on push to main with `[perf]` in commit message. Job runs `uv run eldritch-dm-perf-baseline` and uses exit code to set workflow status. Failure → workflow status fail (informational only — does NOT block release tagging). Optional: GitHub Issues integration via `actions/github-script` to auto-file an issue on regression (deferred to v1.10 if v1.9 runs long). | Weekly cadence; non-blocking |
| **D-220** | **2 plans**: 28-01 = TUNE-01 (top 3 optimizations OR documented no-targets closure). 28-02 = TUNE-02 CLI + TUNE-03 CI workflow. | ROADMAP plans section |

## Success Criteria
1. TUNE-01: profile-driven top 3 optimization commits OR documented Branch-B "no targets" closure
2. TUNE-02: `eldritch-dm-perf-baseline` CLI on PATH; --baseline diff mode functional; 3 exit codes documented in --help
3. TUNE-03: `.github/workflows/perf.yml` runs on weekly schedule + push-with-[perf]; uses CLI exit code for status
4. CLI smoke test (mocked) — runs against current baseline → exit 0 (within tolerance)
5. ≥5 new tests
6. ruff + lint-imports clean
7. Existing 1655-test suite still passes

## Honesty Clause
If TUNE-01 finds no real targets, that's the result. Document with full profile-data evidence in 28-01-SUMMARY.md. The codebase being fast is GOOD — don't manufacture work to avoid acknowledging it.
