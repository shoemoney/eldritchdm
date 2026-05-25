---
phase: 12-llm-judge-tactical
plan: "01"
requirements_completed: [EVAL-01]
subsystem: eval
tags: [eval, llm-as-judge, observability, pydantic]
requires:
  - 11-01 (traced_decision / instrumentation surface)
  - 11-02 (lazy OTel SDK setup)
provides:
  - eldritch_dm.eval.JudgeVerdict
  - eldritch_dm.eval.TacticalJudge
  - eldritch_dm.eval.ScenarioEntry
  - eldritch_dm.eval.load_scenarios
  - eldritch_dm.eval.load_judge_prompt
  - eldritch_dm.observability.traced_eval (extends Phase 11 surface per D-81)
affects:
  - src/eldritch_dm/eval/ (new package)
  - src/eldritch_dm/observability/instrumentation.py (added traced_eval)
  - src/eldritch_dm/observability/__init__.py (re-export)
  - pyproject.toml (new import-linter contract)
tech-stack:
  added: []
  patterns:
    - "pydantic v2 @model_validator(mode='after') for cross-field invariants"
    - "AsyncOpenAI client pattern mirrored from SmartMonsterDriver (D-71)"
    - "fail-soft to None for judge errors (S-12-01-C)"
key-files:
  created:
    - src/eldritch_dm/eval/__init__.py
    - src/eldritch_dm/eval/scenarios.py
    - src/eldritch_dm/eval/judge.py
    - src/eldritch_dm/eval/judge_prompt.py
    - src/eldritch_dm/eval/prompts/__init__.py
    - src/eldritch_dm/eval/prompts/judge.txt
    - tests/eval/__init__.py
    - tests/eval/test_scenarios.py
    - tests/eval/test_judge_prompt.py
    - tests/eval/test_judge_verdict.py
    - tests/eval/test_tactical_judge.py
    - tests/observability/test_traced_eval.py
  modified:
    - src/eldritch_dm/observability/instrumentation.py
    - src/eldritch_dm/observability/__init__.py
    - pyproject.toml
decisions:
  - "S-12-01-A: model_validator(mode='after') with abs(overall-mean) <= 0.05 tolerance"
  - "S-12-01-B: judge sees expected_target_pool/avoidance as 'corpus author's expectation', not ground truth"
  - "S-12-01-C: judge.score() returns None on any error; aggregator records judge_error"
  - "S-12-01-D: prompt SemVer header parsed at init; version flows to eval JSON output"
metrics:
  duration: ~45min
  tests_passing: 41 (12 scenarios + 7 prompt + 11 verdict + 9 judge + 2 traced_eval)
---

# Phase 12 Plan 01: TacticalJudge + JudgeVerdict + ScenarioEntry schema

Shipped the foundational eval primitives: pydantic schemas, judge-prompt
loader, TacticalJudge AsyncOpenAI wrapper, and a new `traced_eval` span
type. All 6 tasks completed; 41 tests green; ruff + import-linter clean.

## What was built

- **`eldritch_dm.eval.scenarios`** — `ScenarioEntry` (with nested
  `MonsterStats` + `PCEntry`) pydantic schemas + `load_scenarios()` JSONL
  loader. Fails LOUD on corruption with 1-indexed line numbers (unlike
  the gameplay `eligibility_loader` which fails soft — eval corruption
  is a developer bug, not an operator one).
- **`eldritch_dm.eval.judge_prompt`** — `load_judge_prompt(path) ->
  (text, version)` reads a SemVer header from line 1 of the prompt file.
  Bundled prompt at `src/eldritch_dm/eval/prompts/judge.txt` v1.0.0 with
  the 4 AI-SPEC §1b dimensions + 0.0/0.5/1.0 anchors per dimension.
- **`eldritch_dm.eval.judge.JudgeVerdict`** — pydantic v2 model with a
  `@model_validator(mode="after")` enforcing: exactly 4 dimension keys
  from the canonical `Literal[...]` set, each value in `[0, 1]`, and
  `abs(overall_score - mean(values)) <= 0.05`.
- **`eldritch_dm.eval.judge.TacticalJudge`** — AsyncOpenAI wrapper that
  mirrors SmartMonsterDriver's call pattern (D-71):
  `response_format={"type":"json_object"}`, `asyncio.wait_for`, defensive
  token-usage extraction. Fail-soft: returns `None` on timeout, malformed
  JSON, refusal, dimension-mean validation failure, or any generic
  exception. Logs the failure path via structlog for triage.
- **`eldritch_dm.observability.traced_eval`** — new context manager
  emitting span `eldritch.eval.judge` with D-81 attributes:
  `scenario_id`, `judge_model`, `driver_model`, `archetype`. No-op when
  `OBSERVABILITY_ENABLED=false`, mirrors the existing `traced_decision`
  pattern exactly. Phase 11's surface is extended (not modified) to
  satisfy D-81 — the existing `traced_decision` is hardwired to span
  name `eldritch.monster.decision`, so a new context manager is
  required, not a parameterization.

## Decisions made

- **S-12-01-A (validator shape):** pydantic v2 `@model_validator(mode="after")`,
  returning `self`. The Literal-typed dict catches unknown keys at parse time;
  the validator catches missing keys, out-of-range values, and mean drift.
- **S-12-01-B (expected fields passed to judge):** judge SEES
  `expected_target_pool` and `expected_avoidance`, labeled as "corpus
  author's expectation." Rationale documented in 12-01-PLAN.md.
- **S-12-01-C (fail-soft):** Judge errors → `None`; aggregator (Plan 02)
  records `judge_error: "<reason>"`. We do NOT silently substitute zeros
  — the eval JSON output has explicit error reasons for triage.
- **S-12-01-D (prompt version):** `prompt_version` is an init-time
  property on `TacticalJudge`; Plan 02's CLI reads it and writes into
  the eval JSON output for cross-run comparability (D-72).

## Deviations from Plan

**None.** All 6 tasks executed exactly as planned. Two scope-clarifying
notes:

- T-12-01-05 (`traced_eval` impl) was bundled into the T-12-01-03 commit
  (`cfc3dba`) to avoid a circular import situation between `eval/judge.py`
  and `observability/`. The T-12-01-05 commit (`9b77ad0`) adds only the
  test file. Net surface delivered matches the plan.
- The eval/__init__.py imports from judge.py / judge_prompt.py / scenarios.py
  at package import time. T-12-01-01 used placeholder modules so this
  worked, then T-12-01-02..04 progressively filled them in. The
  placeholders were never visible to test code.

## Self-Check: PASSED

Files verified exist:
- `src/eldritch_dm/eval/__init__.py` — FOUND
- `src/eldritch_dm/eval/scenarios.py` — FOUND
- `src/eldritch_dm/eval/judge.py` — FOUND
- `src/eldritch_dm/eval/judge_prompt.py` — FOUND
- `src/eldritch_dm/eval/prompts/judge.txt` — FOUND
- `tests/eval/test_*.py` (4 files) — FOUND
- `tests/observability/test_traced_eval.py` — FOUND

Commits verified in git log:
- `9f5c3d0` — feat(12-01): eval/ package + ScenarioEntry schema
- `d109f0a` — feat(12-01): judge prompt + SemVer loader
- `cfc3dba` — feat(12-01): JudgeVerdict + dimension-mean validator
- `3d26b9a` — feat(12-01): TacticalJudge AsyncOpenAI wrapper
- `9b77ad0` — feat(12-01): traced_eval span tests
- `573dbf3` — chore(12-01): import-linter + ruff clean

Verification commands all green:
- `pytest tests/eval/ tests/observability/test_traced_eval.py` → 41 passed
- `ruff check src/eldritch_dm/eval tests/eval` → all checks passed
- `lint-imports` → 8 contracts kept, 0 broken
