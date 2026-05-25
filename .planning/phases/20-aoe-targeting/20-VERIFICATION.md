---
phase: 20-aoe-targeting
verified: 2026-05-25
plans: [20-01, 20-02]
requirements: [AOE-01, AOE-02, AOE-03]
status: PASS
---

# Phase 20 — AOE / multi-target tactic selection — VERIFICATION

## Test counts

| Scope | Baseline (pre-Phase-20) | Post-Phase-20 | Δ |
|---|---:|---:|---:|
| `tests/gameplay/test_smart_monster_driver.py` | 23 | 39 | +16 |
| `tests/gameplay/test_monster_driver_corpus.py` | 18 | 31 | +13 |
| `tests/gameplay/test_smart_monster_driver_streaming.py` | 9 | 9 | 0 |
| `tests/gameplay/test_monster_driver_factory.py` | 10 | 10 | 0 |
| `tests/gameplay/test_aoe_addendum_loader.py` (NEW) | — | 5 | +5 |
| **Phase-20-affected files (subtotal)** | **60** | **94** | **+34** |
| `tests/gameplay/` + `tests/eval/` (full sweep) | — | **437 passed** | — |

**Zero regression:** Each of the 60 baseline tests from the four files above still
passes. Verified by spot-running the unchanged tests with the new schema/driver
in place — see commit `42125cd` test report (60 passed before + after Plan 20-01
schema change).

## Lint / contracts

- `ruff check src/eldritch_dm/ tests/`: **All checks passed**.
- `lint-imports`: **8/8 contracts kept** — gameplay still does not import from
  `bot/` or `ingest/`, and the new `gameplay/prompts/` package lives entirely
  under `gameplay/`.

## Files

### Created
- `src/eldritch_dm/gameplay/prompts/__init__.py`
- `src/eldritch_dm/gameplay/prompts/aoe_addendum.txt` (`# aoe-addendum-version: 1.0.0`)
- `src/eldritch_dm/gameplay/prompts/aoe_addendum.py` (loader, `AoeAddendumError`)
- `tests/gameplay/test_aoe_addendum_loader.py` (5 tests)
- `.planning/phases/20-aoe-targeting/20-01-PLAN.md`
- `.planning/phases/20-aoe-targeting/20-02-PLAN.md`
- `.planning/phases/20-aoe-targeting/20-01-SUMMARY.md`
- `.planning/phases/20-aoe-targeting/20-02-SUMMARY.md`
- `.planning/phases/20-aoe-targeting/20-VERIFICATION.md`

### Modified
- `src/eldritch_dm/gameplay/smart_monster_driver.py` —
  * `ActionDescriptor` model added.
  * `MonsterTacticChoice` gained `target_pc_ids`, `tactic_kind`, legacy-coercion
    `model_validator(mode="before")`, arity-validator `model_validator(mode="after")`,
    `@property target_pc_id` shim.
  * `_pick_target_llm` extended to validate + surface `available_actions`,
    inject AOE addendum conditionally, validate full id-set against candidate set
    (issubset).
  * Cache-hit path validates the full `target_pc_ids` set against current candidates.
  * Regex extractors `_TARGET_LIST_RE`, `_QUOTED_ID_RE`, `_TACTIC_KIND_RE` added.
- `tests/gameplay/test_smart_monster_driver.py` — 16 new tests.
- `tests/gameplay/test_monster_driver_corpus.py` — 13 new tests, sentinel bumped ≥25.
- `.planning/REQUIREMENTS.md` — AOE-01/02/03 ticked `[x]`.

## Hard-constraint evidence

| Constraint | Evidence |
|---|---|
| Zero regression in 60 baseline tests | `pytest tests/gameplay/test_{smart,corpus,streaming,factory}.py` returns 60+ passed pre and post; tests preserved verbatim. |
| Backwards-compat: `choice.target_pc_id` still works | `@property` returns `target_pc_ids[0]`; baseline tests use this attribute unchanged and pass. |
| D-57 meta-knowledge guard | `ActionDescriptor` docstring + tests confirm `range_ft`/`save_dc` are MONSTER properties only; `_slim_candidate` still projects PCs to the 6-field subset (id, name, hp_current, hp_max, ac, active_conditions). |
| D-58 fail-soft on new failure modes | Tests `test_corpus_aoe_with_one_hallucinated_id`, `test_corpus_aoe_with_empty_list`, `test_corpus_anti_cluster_aoe_with_one_in_range_falls_back`, `test_corpus_anti_cluster_mixed_kind_rejection` all assert random fallback after schema/validator rejection. Driver `__init__` swallows addendum-load exceptions with `aoe_addendum_load_failed` warning. |
| Random single-target fallback on every new failure | Each adversarial corpus test asserts `chosen == pcs[0]` (random_choice picks index 0) and no exception propagated. |

## Decision ticks

| Decision | Tied to | Status |
|---|---|---|
| D-149 (`target_pc_ids: list[str]` + ALL-in-candidate-set) | AOE-01 | ✅ |
| D-150 (`tactic_kind` Literal + arity validator) | AOE-01 | ✅ |
| D-151 (`ActionDescriptor` + `available_actions` slim context) | AOE-02 | ✅ |
| D-152 (versioned `aoe_addendum.txt` mirroring judge prompt) | AOE-02 | ✅ |
| D-153 (fail-soft → random single-target on any failure) | All | ✅ |
| D-154 (10+ corpus scenarios across 4 categories) | AOE-03 | ✅ (13 added) |
| D-155 (zero regression in existing 60 tests) | AOE-01 | ✅ |
| D-156 (2-plan split) | All | ✅ |

## Outcome

**PASS.** Phase 20 deliverables locked.
