---
phase: 20-aoe-targeting
plan: 20-01
subsystem: gameplay/smart_monster_driver
tags: [schema, pydantic, backwards-compat, aoe, fail-soft]
requires: []
provides: [MonsterTacticChoice.target_pc_ids, MonsterTacticChoice.tactic_kind, MonsterTacticChoice.target_pc_id-property]
affects: [smart_monster_driver, monster_driver_corpus, monster_driver_streaming, monster_driver_factory]
tech_added: []
patterns: [pydantic-v2 model_validator(mode=before) for legacy coercion, @property shim to preserve backwards-compat against Field/property collision]
key_files_created: []
key_files_modified:
  - src/eldritch_dm/gameplay/smart_monster_driver.py
  - tests/gameplay/test_smart_monster_driver.py
decisions: [D-149, D-150, D-153, D-155]
metrics:
  duration_minutes: ~20
  tests_baseline: 60
  tests_added: 16
  tests_final: 282 (full gameplay suite)
completed_date: 2026-05-25
---

# Phase 20 Plan 01: MonsterTacticChoice schema extension — Summary

One-line: `MonsterTacticChoice` gains `target_pc_ids: list[str]` + `tactic_kind: Literal[...]`
with a `model_validator(mode="before")` that rewrites legacy `{target_pc_id: "x"}` JSON
into the new shape, and a `@property target_pc_id` that returns the first element —
zero regression in the existing 60 tests and ready for Plan 20-02 to layer
ActionDescriptor + prompt addendum on top.

## What Shipped

### Schema (`src/eldritch_dm/gameplay/smart_monster_driver.py`)
- `target_pc_ids: list[str] = Field(..., min_length=1)` — the AOE-aware multi-target shape.
- `tactic_kind: Literal["single", "aoe", "multi_attack", "breath", "cone"] = "single"`
  — discriminator for downstream resolution and validator arity enforcement.
- `@model_validator(mode="before") _coerce_legacy_shape`: rewrites legacy dict
  `{target_pc_id: "x"}` (and kwargs path) → `{target_pc_ids: ["x"], tactic_kind: "single"}`.
  Newer shape wins if both keys present.
- `@model_validator(mode="after") _validate_kind_arity`: enforces
  `single → len==1`, `aoe/breath/cone → len>=2`, `multi_attack → len>=1`,
  and rejects duplicate ids in the list.
- `@property target_pc_id`: backwards-compat shim returning `target_pc_ids[0]`.
  Avoids the pydantic v2 Field/@property collision noted by the advisor.

### Internal call-site updates
- **Cache hit (line ~399):** `set(cached.target_pc_ids).issubset(candidate_ids)`
  invalidates AOE cached choices when a PC dropped between rounds.
- **Membership check (line ~556):** ALL ids must be in candidate set + upper-bound
  `len(ids) <= len(candidates)`. Any hallucination → fail-soft fallback.
- **Regex extractors (new):** `_TARGET_LIST_RE` (AOE list shape) tried FIRST,
  `_TARGET_RE` (legacy single-id) as fallback. `_TACTIC_KIND_RE` extracts kind
  hint from prose; absent → infer `"single"` for 1 id, `"aoe"` for 2+.
- **Logging:** `target_id`, `target_ids`, `tactic_kind` keys all surfaced for
  greppable traces; old `target_id` key preserved.

### Tests (`tests/gameplay/test_smart_monster_driver.py`)
16 new tests appended:
- 12 schema/validation tests (legacy coercion, new shape acceptance, kind/arity
  validation per Literal, duplicates rejection, empty-list rejection, property
  semantics, invalid Literal rejection).
- 4 oracle-integration tests (AOE end-to-end success, prose-wrapped AOE regex
  recovery, partial hallucination falls back at `_pick_target_llm`, partial
  hallucination falls back at `_choose_target` via random_choice).

## Verification

| Check | Result |
|---|---|
| `pytest tests/gameplay/` | **282 passed** (60 baseline + 222 other gameplay tests + 16 new) |
| `ruff check src/eldritch_dm/gameplay/ tests/gameplay/` | **All checks passed** |
| `lint-imports` | **8/8 contracts kept** |
| Backwards-compat (60 baseline tests untouched) | **all green** |

## Decisions Honored

- **D-149**: `target_pc_ids: list[str]` + ALL ids validated against candidate set.
- **D-150**: `tactic_kind` Literal + arity validator enforces lower bound; upper
  bound enforced at call site.
- **D-153**: Fail-soft preserved — any ValidationError/hallucination → caller
  falls back to `random_choice`. New test `test_choose_target_aoe_partial_hallucination_random_fallback`
  exercises this end-to-end.
- **D-155**: Zero regression — 60 existing tests still green; existing
  `choice.target_pc_id` access pattern unchanged via `@property`.

## Deviations from Plan

None. The plan executed exactly as written. The advisor-flagged
Field/@property collision risk was avoided by design (drop the Field, keep
the property), as scoped in PLAN.md.

## Commits

- `4b8868a` — feat(20-01): extend MonsterTacticChoice with target_pc_ids + tactic_kind
- `d1d3807` — feat(20-01): update internal call sites for AOE-aware MonsterTacticChoice
- `42125cd` — test(20-01): add schema + AOE-integration tests for MonsterTacticChoice

## Self-Check: PASSED

- src/eldritch_dm/gameplay/smart_monster_driver.py: FOUND
- tests/gameplay/test_smart_monster_driver.py: FOUND (39 test functions)
- Commits 4b8868a, d1d3807, 42125cd: FOUND in git log
