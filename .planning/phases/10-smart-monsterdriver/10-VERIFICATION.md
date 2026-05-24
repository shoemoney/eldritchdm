---
phase: 10-smart-monsterdriver
artifact: VERIFICATION
generated: 2026-05-24
---

# Phase 10 — Verification (ROADMAP success criteria)

Walks the 7 ROADMAP success criteria from `10-CONTEXT.md §Success Criteria`,
each with a proof pointer (test name / file path / commit hash).

## 1. New `smart_monster_driver.py` replaces `monster_driver.py`'s random `_pick_target`; `MONSTER_DRIVER` env var wired

**Status: [x] PASSED**

- `src/eldritch_dm/gameplay/smart_monster_driver.py` exists (commit `3ab88b0`)
- v1.0 `monster_driver.py` gained an async `_choose_target` hook; default
  implementation is `self._random_choice(targets)` (behaviour-preserving —
  all 15 v1.0 tests still pass)
- `SmartMonsterDriver` overrides `_choose_target` to dispatch through INT-
  gating → LLM oracle → fail-soft random fallback
- `MONSTER_DRIVER` env var wired via `Settings.monster_driver` field
  (`config/__init__.py` commit `a5a99e7`); orchestrator constructs driver
  through `make_monster_driver(...)` (`bot/bot.py:341` commit `acadda3`)

## 2. INT-gating verified (`≤4` random, `≥8` LLM, `5..7` mixed)

**Status: [x] PASSED**

Proven by:

- `tests/gameplay/test_smart_monster_driver.py`:
  - `test_route_low_int_is_random`
  - `test_route_high_int_is_llm`
  - `test_route_boundary_4_random`
  - `test_route_boundary_8_llm`
  - `test_route_mixed_is_deterministic`
  - `test_route_none_int_is_random`
  - `test_choose_target_low_int_skips_llm` — asserts mock LLM not called
  - `test_choose_target_high_int_uses_llm` — asserts mock LLM called once
- `tests/gameplay/test_monster_driver_corpus.py::test_corpus_sub_int_bypass`
- `tests/gameplay/test_monster_driver_corpus.py::test_corpus_mixed_mode_seeded_determinism`

## 3. 1500ms hard deadline + structured-log fallback verified

**Status: [x] PASSED**

- `tests/gameplay/test_smart_monster_driver.py::test_pick_target_llm_timeout` —
  mock client awaits 5s with `llm_timeout_seconds=0.05` → `asyncio.wait_for`
  fires, structured `smart_driver_timeout` warning logged, returns `None`,
  caller falls back to random
- `tests/gameplay/test_monster_driver_corpus.py::test_corpus_timeout_exceeded` —
  end-to-end via `_choose_target` (no exception leaks, valid PC returned)

## 4. Pydantic post-parse validation: hallucinated IDs → fallback, NOT exception

**Status: [x] PASSED**

- `MonsterTacticChoice` lives in `smart_monster_driver.py` (D-55)
- Membership check happens at the call site (D-55 + AI-SPEC §4b.1):
  `if choice.target_pc_id not in candidate_ids: return None`
- Proven by:
  - `tests/gameplay/test_smart_monster_driver.py::test_pick_target_llm_hallucinated_id`
  - `tests/gameplay/test_monster_driver_corpus.py::test_corpus_hallucinated_target_id`
  - `tests/gameplay/test_monster_driver_corpus.py::test_corpus_self_target_attempt`
    (LLM returns the monster's own id — not in PC candidate set → fallback)
- Regex last-chance extractor (D-51) covered by
  `tests/gameplay/test_smart_monster_driver.py::test_pick_target_llm_regex_extractor`

## 5. Per-round cache: `(channel_id, round, monster_id)` returns cached value; mock asserted called once

**Status: [x] PASSED**

- Cache implemented as `OrderedDict[(channel_id, round_number, monster_id),
  MonsterTacticChoice]` on `SmartMonsterDriver` instance, FIFO eviction at
  `cache_max_size=256` (commit `3ab88b0`)
- Proven by:
  - `tests/gameplay/test_monster_driver_corpus.py::test_corpus_cache_hit_same_key` —
    asserts `mock.call_count == 1` across two identical-key invocations
  - `tests/gameplay/test_monster_driver_corpus.py::test_corpus_pc_death_between_calls` —
    different `round_number` → cache miss → 2 LLM calls
  - `tests/gameplay/test_monster_driver_corpus.py::test_corpus_cross_channel_isolation` —
    different `channel_id` → cache miss
  - `tests/gameplay/test_monster_driver_corpus.py::test_corpus_cache_fifo_eviction` —
    fourth entry into a 3-slot cache evicts the oldest

## 6. 15+ adversarial corpus tests pass

**Status: [x] PASSED**

- 16 corpus scenarios (one over the floor) in
  `tests/gameplay/test_monster_driver_corpus.py` (commit `975e2e4`)
- A meta-guard (`test_corpus_size_meets_requirement`) self-counts the
  `test_corpus_*` functions and asserts `>= 15` — protects against future
  drops of scenarios
- See the full scenario table in `10-02-SUMMARY.md §What shipped`

## 7. Full v1.1 suite green; `pc_classes` populated by Phase 9

**Status: [x] PASSED (with one noted out-of-scope flake)**

```
PYTHONPATH=src .venv/bin/pytest --ignore=tests/integration
# 1050 passed, 1 failed, 9 skipped in 15.49s
```

The 1 failure (`tests/tools/test_backfill_pc_classes.py::test_collect_rows_subclass_warning_emitted`)
is a pre-existing flake: it passes when run in isolation. Lives outside
`gameplay/`, predates Phase 10, and is documented under "Deferred Issues" in
10-02-SUMMARY.md.

- Full `tests/gameplay/` suite: **250 passed**
- Phase 10 net additions: 49 new tests (23 smart driver + 16 corpus + 10
  factory; 18 corpus file tests include 2 sanity meta-tests)

## Ruff + lint-imports

```
.venv/bin/ruff check src/eldritch_dm/gameplay/ \
                    src/eldritch_dm/bot/bot.py \
                    src/eldritch_dm/config/__init__.py \
                    tests/gameplay/test_smart_monster_driver.py \
                    tests/gameplay/test_monster_driver_corpus.py \
                    tests/gameplay/test_monster_driver_factory.py
# All checks passed!
```

`import-linter` discipline: `smart_monster_driver.py`, `monster_driver_factory.py`
both live under `gameplay/` and import only from `gameplay/`, `logging`,
`openai`, `pydantic`. No upward imports into `bot/`. Verified by grep.

## REQUIREMENTS traceability

| Requirement | Plan | Status |
|-------------|------|--------|
| COMBAT-13   | 10-01 | [x] ticked |
| COMBAT-14   | 10-02 | [x] ticked |
