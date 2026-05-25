---
phase: 20-aoe-targeting
plan: 20-02
subsystem: gameplay/smart_monster_driver + gameplay/prompts
tags: [llm-prompt, aoe, action-descriptor, fail-soft, corpus]
requires: [20-01]
provides: [ActionDescriptor, available_actions-payload-field, aoe_addendum.txt, AoeAddendumError, load_aoe_addendum]
affects: [smart_monster_driver, monster_driver_corpus]
tech_added: []
patterns: [SemVer-versioned system-prompt addendum mirroring Phase 12 judge_prompt, conditional prompt injection only when monster surfaces actions, fail-soft loader (missing file → empty addendum → legacy prompt)]
key_files_created:
  - src/eldritch_dm/gameplay/prompts/__init__.py
  - src/eldritch_dm/gameplay/prompts/aoe_addendum.txt
  - src/eldritch_dm/gameplay/prompts/aoe_addendum.py
  - tests/gameplay/test_aoe_addendum_loader.py
  - .planning/phases/20-aoe-targeting/20-VERIFICATION.md
key_files_modified:
  - src/eldritch_dm/gameplay/smart_monster_driver.py
  - tests/gameplay/test_monster_driver_corpus.py
  - .planning/REQUIREMENTS.md
decisions: [D-151, D-152, D-154]
metrics:
  duration_minutes: ~25
  tests_added: 18  # 5 loader + 13 corpus
  tests_final_gameplay_eval: 437
completed_date: 2026-05-25
---

# Phase 20 Plan 02: AOE system prompt + ActionDescriptor + corpus expansion — Summary

One-line: `SmartMonsterDriver` now surfaces the monster's own actions (range_ft, save_dc)
to the LLM via `ActionDescriptor` + `available_actions` payload field, conditionally
appends a SemVer-versioned `aoe_addendum.txt` system-prompt extension explaining
multi-target heuristics, and ships 13 new corpus scenarios (3 cluster-optimal, 3
anti-cluster, 2 mixed-tactic, 2 adversarial, 3 wiring) — all fail-soft paths preserved.

## What Shipped

### ActionDescriptor (D-151)
- `name: str`, `kind: Literal["single","aoe","multi_attack","breath","cone"]`,
  `range_ft: int`, `save_dc: int | None`.
- Scoped to **monster** properties (its own range/save DC) — never PC properties.
  D-57 meta-knowledge guard preserved.

### Versioned AOE prompt addendum (D-152)
- `src/eldritch_dm/gameplay/prompts/aoe_addendum.txt` — header
  `# aoe-addendum-version: 1.0.0` mirroring `eval/prompts/judge.txt`.
- `aoe_addendum.py` loader — `AoeAddendumError` on missing / empty / malformed-header.
- Mirrors `eval/judge_prompt.py` SemVer pattern exactly.

### Driver wiring
- `SmartMonsterDriver.__init__` lazily loads addendum; any loader exception →
  empty addendum text + `aoe_addendum_load_failed` warning log (D-153 fail-soft —
  combat keeps Phase 10 behavior if addendum is missing).
- `_pick_target_llm`:
  - Validates `current_actor['available_actions']` entries via
    `ActionDescriptor.model_validate`; malformed dropped silently.
  - System prompt = legacy + addendum **only** when validated descriptors are
    non-empty AND addendum loaded — preserves bit-identical Phase 10 prompt for
    actors without `available_actions`.
  - `user_payload['available_actions']` always present (possibly `[]`).
- `aoe_addendum_loader` kwarg accepts injection for testing.

### Tests
- `tests/gameplay/test_aoe_addendum_loader.py` (5 new): version load, missing file,
  malformed header, empty file, bad version format.
- `tests/gameplay/test_monster_driver_corpus.py` (13 new):
  - **Cluster-optimal (3):** dragon breath cluster, fireball wizard cluster,
    breath-arity validator gating.
  - **Anti-cluster (3):** lone-PC single-target preferred, aoe-with-1id
    validator rejection, mixed-kind rejection.
  - **Mixed-tactic (2):** multi_attack pile-on-one-PC, multi_attack cleave 2 PCs.
  - **Adversarial (2):** AOE with one hallucinated id, AOE with empty list.
  - **Wiring (3):** addendum injection conditional, ActionDescriptor validation
    drops malformed, ActionDescriptor schema sanity.
- Sentinel bumped: `test_corpus_size_meets_requirement` now requires `≥25`.

## Verification

| Check | Result |
|---|---|
| `pytest tests/gameplay/ tests/eval/` | **437 passed** |
| `pytest tests/gameplay/test_monster_driver_corpus.py` | **31 passed** (18 baseline + 13 new) |
| `pytest tests/gameplay/test_aoe_addendum_loader.py` | **5 passed** |
| `ruff check src/eldritch_dm/ tests/` | **All checks passed** |
| `lint-imports` | **8/8 contracts kept** |
| Backwards-compat (Phase 10 tests no `available_actions`) | **all green — legacy prompt verbatim** |

## Decisions Honored

- **D-151** ActionDescriptor scoped to monster; D-57 meta-knowledge guard intact.
- **D-152** SemVer-versioned addendum + loader mirroring judge_prompt.
- **D-153** Fail-soft on all new failure modes: missing addendum, malformed
  ActionDescriptor entries, hallucinated AOE ids, empty list, schema-arity
  violations. Every path verified by tests to fall back to `random_choice`.
- **D-154** 10+ corpus scenarios across the four required categories (13 added).

## Deviations from Plan

None. Plan executed exactly as written.

## Commits

- `5b1...` — feat(20-02): AOE addendum + ActionDescriptor + 10-scenario corpus

(See `git log --oneline` for actual hash; commit followed Plan 20-01's 3 commits.)

## Self-Check: PASSED

- src/eldritch_dm/gameplay/prompts/aoe_addendum.txt: FOUND with version 1.0.0 header
- src/eldritch_dm/gameplay/prompts/aoe_addendum.py: FOUND
- tests/gameplay/test_aoe_addendum_loader.py: FOUND (5 tests)
- tests/gameplay/test_monster_driver_corpus.py: 31 tests
- 437 tests passing across gameplay + eval
- ruff clean; lint-imports 8/8 contracts kept
