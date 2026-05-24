---
phase: 12-llm-judge-tactical
generated: 2026-05-24
tags: [verification, phase-rollup]
---

# Phase 12 — LLM-as-Judge Tactical Scoring — Verification

End-of-phase rollup confirming all ROADMAP success criteria, all locked
decisions D-71..D-82 honored, and all REQUIREMENTS items ticked.

## ROADMAP Success Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | TacticalJudge returns JudgeVerdict per D-73; judge prompt versioned | ✅ | `src/eldritch_dm/eval/judge.py`, `prompts/judge.txt` line 1: `# judge-prompt-version: 1.0.0`. 11 verdict tests + 9 judge tests passing. |
| 2 | 50-scenario corpus across 5 archetypes (10 each) | ✅ | `tests/eval/dataset/tactical_corpus.jsonl` — `len()` is 50, archetype counter `{brute: 10, spellcaster: 10, swarm: 10, predator: 10, edge_case: 10}`. |
| 3 | `eldritch-dm-eval` CLI with --dataset/--judge-model/--driver-model/--limit/--baseline flags | ✅ | `[project.scripts] eldritch-dm-eval = eldritch_dm.eval.cli:main`. All 6 flags + verbose tested in `test_cli_args.py`. |
| 4 | Exit codes 0/1/2 (passed/regression/critical) | ✅ | `derive_exit_code()` in `aggregator.py`; 7 exit-code tests including critical-beats-regression precedence (S-12-02-B). Smoke tests exercise all 3 codes end-to-end. |
| 5 | Corpus is original Apache-2.0 content (license header documents this) | ✅ | `tests/eval/dataset/LICENSE.md` declares Apache-2.0 + explicit provenance statement. No content derived from copyrighted RPG sources. |
| 6 | Tests: schema validation, end-to-end CLI smoke (mocked LLM) | ✅ | `test_scenarios.py` (12 tests), `test_corpus_validation.py` (5 tests), `test_cli_smoke.py` (3 end-to-end smoke tests with mocked AsyncOpenAI). |

**All 6 ROADMAP criteria met.**

## Locked Decision Coverage (CONTEXT D-71..D-82)

| ID | Status | Evidence |
|----|--------|----------|
| D-71 | ✅ | `judge.py` uses AsyncOpenAI client with `response_format={"type":"json_object"}` (NOT `.beta.parse`). `--judge-model gpt-4o` documented in --help epilog as escape-hatch. |
| D-72 | ✅ | `prompts/judge.txt` line 1: `# judge-prompt-version: 1.0.0`; `load_judge_prompt()` parses with regex `^# judge-prompt-version: (\d+\.\d+\.\d+)$`; eval JSON output writes `judge_prompt_version` field. |
| D-73 | ✅ | `JudgeVerdict` model with `@model_validator(mode="after")` enforcing exactly 4 dimension keys + `abs(overall - mean) <= 0.05`. 11 tests. |
| D-74 | ✅ | JSONL at `tests/eval/dataset/tactical_corpus.jsonl`. `ScenarioEntry` pydantic schema with `extra="forbid"` validates on load. |
| D-75 | ✅ | 5 archetypes × 10 = 50. `Literal["brute","spellcaster","swarm","predator","edge_case"]` enforced at schema level. |
| D-76 | ✅ | `LICENSE.md` declares Apache-2.0 + provenance: "Every scenario in `tactical_corpus.jsonl` is original content, hand-authored in 2026 ... No scenario is derived ... from any copyrighted RPG source material". |
| D-77 | ✅ | argparse build_parser() defines `--dataset/--judge-model/--driver-model/--limit/--baseline/--output/--verbose`. --help epilog documents `gpt-4o` escape-hatch. |
| D-78 | ✅ | Output filename `eval-{ISO timestamp}-{git short sha}.{json,md}`. JSON includes `judge_prompt_version`, `driver_model`, `judge_model`, `scenarios`, `aggregate`, `baseline_diff`. Markdown report companions. |
| D-79 | ✅ | Exit codes 0/1/2 with documented precedence in --help. `derive_exit_code()` implements critical > regression > pass. |
| D-80 | ✅ | `runner.build_eval_driver()` constructs SmartMonsterDriver with `_NoopSentinel` deps. Calls `_choose_target` directly. No mock dm20, no mock combat state. |
| D-81 | ✅ | `traced_eval()` context manager added to `observability/instrumentation.py`. Emits `eldritch.eval.judge` span with attributes `eldritch.eval.{scenario_id,judge_model,driver_model,archetype}` plus runtime-stamped `latency_ms`, `tokens.input/output`, `overall_score`, `error`. 2 tests in `test_traced_eval.py`. |
| D-82 | ✅ | Module layout: `eval/__init__.py`, `eval/judge.py`, `eval/scenarios.py`, `eval/cli.py`, `eval/aggregator.py`, `eval/reporter.py`, plus `eval/runner.py` (new — added because the runner is non-trivial and deserves its own module). Tests at `tests/eval/`, corpus at `tests/eval/dataset/`. |

**All 12 locked decisions honored.**

## REQUIREMENTS coverage

| ID | Status | Source plan |
|----|--------|-------------|
| EVAL-01 | ✅ ticked | 12-01-PLAN.md (T-12-01-01..06) |
| EVAL-02 | ✅ ticked | 12-02-PLAN.md (T-12-02-07, T-12-02-08) |
| EVAL-03 | ✅ ticked | 12-02-PLAN.md (T-12-02-01..06) |

## Test inventory

```
$ pytest tests/eval/ tests/observability/test_traced_eval.py
====== 80 passed in 0.31s ======
```

Breakdown by file:

| Test file | Tests |
|-----------|-------|
| tests/eval/test_scenarios.py | 12 |
| tests/eval/test_judge_prompt.py | 7 |
| tests/eval/test_judge_verdict.py | 11 |
| tests/eval/test_tactical_judge.py | 9 |
| tests/observability/test_traced_eval.py | 2 |
| tests/eval/test_aggregator.py | 16 |
| tests/eval/test_reporter.py | 5 |
| tests/eval/test_runner.py | 7 |
| tests/eval/test_cli_args.py | 3 |
| tests/eval/test_cli_smoke.py | 3 |
| tests/eval/test_corpus_validation.py | 5 |
| **Total** | **80** |

## Lint + import-linter

- `ruff check src/eldritch_dm/eval tests/eval` → All checks passed.
- `lint-imports` → 8 contracts kept, 0 broken (the existing 7 plus the
  new `eval must not import bot or ingest`).

## Deferred / not-in-scope

Carried forward from CONTEXT "Deferred" section to v1.3+:

- Crowd-sourced corpus expansion via GitHub PRs.
- Inter-judge agreement (Cohen's kappa) studies.
- Auto-detect drift on judge model upgrade.
- Chain-of-thought judge reasoning visible in Phoenix dashboards.

## Verification commands (operator)

```bash
# Run the test suite
PYTHONPATH=src pytest tests/eval/ tests/observability/test_traced_eval.py -v

# Lint
ruff check src/eldritch_dm/eval tests/eval

# Import contracts
lint-imports

# Confirm corpus shape
PYTHONPATH=src python -c "
from collections import Counter
from pathlib import Path
from eldritch_dm.eval.scenarios import load_scenarios
s = load_scenarios(Path('tests/eval/dataset/tactical_corpus.jsonl'))
print(f'n={len(s)}  counts={dict(Counter(e.archetype for e in s))}')
"

# Confirm CLI registration (post pip install -e .)
PYTHONPATH=src python -m eldritch_dm.eval.cli --help
```

## Out-of-scope notes

- **STATE.md / ROADMAP.md not updated** per execution objective. These
  documents are maintained by the orchestrator at phase-close time.
