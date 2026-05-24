---
phase: 10-smart-monsterdriver
plan: "01"
subsystem: gameplay/combat
tags: [smart-driver, llm-routing, INT-gating, fail-soft]
requires: [10-CONTEXT.md, 10-AI-SPEC.md, REQUIREMENTS.md::COMBAT-13]
provides:
  - gameplay.smart_monster_driver.SmartMonsterDriver
  - gameplay.smart_monster_driver.MonsterTacticChoice
  - gameplay.monster_driver.MonsterDriver._choose_target (new async hook)
affects:
  - gameplay.monster_driver (extracted async _choose_target hook — behaviour-preserving)
tech-stack:
  added: [openai.AsyncOpenAI (already in repo via ingest), pydantic.BaseModel]
  patterns: [fail-soft, async-with-timeout, post-parse-validation, regex-fallback]
key-files:
  created:
    - src/eldritch_dm/gameplay/smart_monster_driver.py
    - tests/gameplay/test_smart_monster_driver.py
  modified:
    - src/eldritch_dm/gameplay/monster_driver.py
decisions: [D-50, D-51, D-53, D-54, D-55, D-57, D-58, D-60]
metrics:
  duration_minutes: ~30
  completed: 2026-05-24
---

# Phase 10 Plan 01 — Smart MonsterDriver Core (INT-gated, LLM-routed)

## One-liner

`SmartMonsterDriver` subclasses v1.0's `MonsterDriver`, overrides `_choose_target`
to consult oMLX/ShoeGPT for INT≥8 monsters with a 1500ms hard deadline and
fail-soft random fallback on any error.

## What shipped

1. **`src/eldritch_dm/gameplay/smart_monster_driver.py`** (NEW, 359 lines)
   - `MonsterTacticChoice` pydantic v2 model (`extra="ignore"` for local-model
     forward-compat — D-55)
   - `_slim_candidate()` projection that strips class/subclass before sending
     to the LLM (D-57 meta-knowledge guardrail)
   - `_extract_monster_int()` handling both `current_actor.intelligence` and
     `current_actor.stats.intelligence`
   - `SmartMonsterDriver._route_path()` static method: INT<=4 → "random",
     INT>=8 → "llm", INT in [5,7] → deterministic 50/50 via
     `random.Random(hash((channel_id, round_number, monster_id)))` (D-53)
   - `_pick_target_llm()` with `asyncio.wait_for(..., timeout=1.5)`, fail-soft
     to None on any exception, regex last-chance extractor for JSON-in-prose
     (D-51, D-54, D-58)
   - Per-round cache scaffold (`OrderedDict` with FIFO eviction at 256) —
     verified by tests, with the orchestrator wire-up landing in 10-02

2. **`src/eldritch_dm/gameplay/monster_driver.py`** (refactor)
   - Extracted the v1.0 inline `self._random_choice(targets)` call into an
     async `_choose_target` hook. v1.0 default returns `self._random_choice` —
     behaviour preserved (all 15 existing tests pass).
   - `drive()` now awaits `_choose_target`.

3. **`tests/gameplay/test_smart_monster_driver.py`** (NEW, 23 tests)
   - Schema validation (3 tests)
   - `_slim_candidate` / `_extract_monster_int` (5 tests)
   - `_route_path` INT-gating including boundary 4/8 (6 tests)
   - LLM oracle success + timeout + malformed JSON + hallucinated ID + regex
     fallback + empty content (6 tests)
   - `_choose_target` integration (3 tests: low-INT skips LLM, high-INT uses
     LLM, LLM failure falls back to random)

## Reconciliations with AI-SPEC

AI-SPEC §3 prescribes `.beta.chat.completions.parse(response_format=PydanticModel)`
strict mode against hosted OpenAI. **Production uses local oMLX/ShoeGPT** per
PROJECT.md, which is not reliably strict-mode capable. CONTEXT D-51 locked in
`response_format={"type":"json_object"}` + post-parse
`MonsterTacticChoice.model_validate_json(...)` + regex last-chance extractor.
This mirrors the existing pattern in `gameplay/ingest/translate.py` against
the same oMLX server.

Arize Phoenix instrumentation (AI-SPEC §7) deferred to v1.2 per CONTEXT D-59.

## Verification

```bash
PYTHONPATH=src .venv/bin/pytest tests/gameplay/test_smart_monster_driver.py tests/gameplay/test_monster_driver.py
# 38 passed
```

```bash
.venv/bin/ruff check src/eldritch_dm/gameplay/smart_monster_driver.py \
                    src/eldritch_dm/gameplay/monster_driver.py \
                    tests/gameplay/test_smart_monster_driver.py
# 0 errors
```

## Deviations from plan

None — plan executed as written. Ruff `--fix` made two cosmetic adjustments
(`asyncio.TimeoutError` → builtin `TimeoutError`, import sort in test file)
applied during Task 6.

## Known stubs / open work for Plan 02

- Per-round cache hit/eviction *behaviour* is implemented but only minimally
  tested at the unit level — Plan 02's corpus test 11 (`cache_hit_same_key`)
  closes the gap with mock-call-count assertions.
- `make_monster_driver` factory + `MONSTER_DRIVER` env var: deferred to
  Plan 02 task 2.
- Orchestrator wire-up (`bot.py:341`): deferred to Plan 02 task 4.

## Self-Check: PASSED

All claimed files exist on disk; all claimed commits exist on this branch.
