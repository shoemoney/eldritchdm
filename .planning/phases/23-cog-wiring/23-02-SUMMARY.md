---
phase: 23-cog-wiring
plan: 23-02
title: WIRE-03 — Conditional AOE addendum injection (≥2 AOE actions) + OTel version attribute
status: complete
requirements_completed: [WIRE-03]
generated: 2026-05-25
key-files:
  created: []
  modified:
    - src/eldritch_dm/gameplay/prompts/aoe_addendum.py
    - src/eldritch_dm/gameplay/smart_monster_driver.py
    - tests/gameplay/test_monster_driver_corpus.py
    - .planning/REQUIREMENTS.md
decisions:
  - D-180 (tightened predicate): addendum injected IFF sum(1 for a in actions if a.kind in {aoe,cone,breath}) >= 2
  - D-181 (version attr): span.set_attribute('eldritch.aoe.addendum_version', SemVer) when injected, never otherwise
  - D-182 (helper surface): get_addendum_version() in aoe_addendum.py for callers needing version-only
---

# Phase 23 Plan 02: AOE Addendum Live Prompt Assembly Summary

**One-liner:** Tightened SmartMonsterDriver's system-prompt assembly so the AOE
addendum is appended ONLY when the actor has 2+ AOE-class actions, and stamps
the decision span with `eldritch.aoe.addendum_version` when active — closing
v1.6's WIRE-03 honest-gap from Phase 20.

## What was built

1. **`get_addendum_version(path=None) -> str`** added to
   `src/eldritch_dm/gameplay/prompts/aoe_addendum.py`. Thin wrapper over
   `load_aoe_addendum` returning only the SemVer string. Raises
   `AoeAddendumError` on the same conditions (D-182 API surface).

2. **`_pick_target_llm` predicate tightened** in
   `src/eldritch_dm/gameplay/smart_monster_driver.py`:

   ```python
   aoe_count = sum(
       1 for a in action_descriptors
       if a.get("kind") in {"aoe", "cone", "breath"}
   )
   if aoe_count >= 2 and self._aoe_addendum_text:
       system_prompt = legacy_system_prompt + "\n\n" + self._aoe_addendum_text
       if span is not None:
           span.set_attribute(
               "eldritch.aoe.addendum_version", self._aoe_addendum_version
           )
   else:
       system_prompt = legacy_system_prompt
   ```

   The OTel attribute is stamped on the OUTER decision-span (created in
   `_choose_target` via `traced_decision`) — no nested spans, per D-66.

3. **Pre-existing corpus test updated** —
   `test_aoe_addendum_injected_when_available_actions_present` previously asserted
   addendum injection for a SINGLE action; per D-180 this is no longer expected.
   Updated to pass `[_breath_action(), _fireball_action()]` so it exercises the
   tightened predicate.

4. **7 new tests** in `tests/gameplay/test_monster_driver_corpus.py`:
   - `test_addendum_skipped_with_one_aoe_action`
   - `test_addendum_skipped_with_zero_aoe_actions`
   - `test_addendum_injected_with_two_aoe_actions`
   - `test_addendum_version_attr_only_set_when_injected` (mixed back-to-back turns)
   - `test_addendum_load_failure_no_injection` (fail-soft per D-153)
   - `test_get_addendum_version_returns_semver`
   - `test_get_addendum_version_raises_on_missing_file`

## Commits

- `dbc6824` feat(23-02): add get_addendum_version() helper to aoe_addendum
- `7bfc9b4` feat(23-02): tighten AOE addendum predicate to >=2 AOE actions + OTel version attr
- `d699a41` test(23-02): cover conditional AOE addendum injection + version attr

## Tests

- New: 7 in `tests/gameplay/test_monster_driver_corpus.py`
- Updated: 1 pre-existing test in same file (predicate-update aligned with D-180)
- Regression: `tests/gameplay/` 419 passed
- Wider: 670 passed across `tests/bot/cogs/`, `tests/gameplay/`, `tests/observability/`

## Deviations from Plan

None — plan executed as written. The pre-existing
`test_aoe_addendum_injected_when_available_actions_present` was updated to
match the new D-180 contract (it asserted the OLD loose predicate); this is
a planned contract change documented in the plan body, not a deviation.

## Self-Check: PASSED

- `src/eldritch_dm/gameplay/prompts/aoe_addendum.py`: `get_addendum_version`
  defined; tests directly import and exercise it.
- `src/eldritch_dm/gameplay/smart_monster_driver.py`: new predicate at line
  576-593 with `span.set_attribute("eldritch.aoe.addendum_version", ...)`
  guarded by `if span is not None`.
- `tests/gameplay/test_monster_driver_corpus.py`: 7 new test functions added
  near the existing AOE corpus block; all pass.
- `.planning/REQUIREMENTS.md`: WIRE-03 ticked `[x]`.
- All commits visible in `git log --oneline`.
