---
phase: 21-monster-memory
plan: 21-01
subsystem: gameplay
tags: [monster-memory, smart-driver, mem-01, mem-02, meta-knowledge-guard]
requirements: [MEM-01, MEM-02]
key-files:
  created:
    - src/eldritch_dm/gameplay/monster_memory.py
    - tests/gameplay/test_monster_memory.py
  modified:
    - src/eldritch_dm/gameplay/smart_monster_driver.py
    - src/eldritch_dm/gameplay/monster_driver_factory.py
    - tests/gameplay/test_smart_monster_driver.py
    - tests/gameplay/test_monster_driver_factory.py
decisions:
  - L-01 damage_dealt_by is cumulative-this-session (not windowed)
  - L-02 damage bands locked at <5 / 5..14 / ≥15
  - L-03 deque(maxlen=200) event log; eviction never rolls back signal totals
  - L-04 _slim_candidate signature frozen; augmentation in separate helper
  - L-05 monster_memory ctor kwarg defaults None → byte-identical legacy behavior
  - L-06 INT-gated marking via observer_int parameter (≥10 marks)
  - L-07 fail-soft at every public boundary
metrics:
  tests_added: 39
  tests_total_in_modified_files: 50 (smart driver) + 12 (factory) + 29 (memory) = 91
  full_gameplay_suite: 340 passed (was ~328 pre-Phase-21)
  regression_in_existing_tests: 0
requirements_completed:
  - MEM-01
  - MEM-02
---

# Phase 21 Plan 01 — MonsterMemory class + slimmed-context augmentation Summary

## One-liner

In-memory `MonsterMemory` + `MonsterMemoryRegistry` with three D-57-safe signals
(cumulative damage → categorical band, concentrating-on spell name, INT-gated
marked-dangerous bool) wired into `SmartMonsterDriver._pick_target_llm` via an
opt-in ctor kwarg; zero regression in the 96+ existing smart-driver tests.

## What Shipped

### `src/eldritch_dm/gameplay/monster_memory.py` (new)

- `MonsterMemory` class:
  - State: `damage_dealt_by: dict[str,int]`, `concentrating_on: dict[str,str|None]`,
    `marked_dangerous: set[str]`, `_events: deque(maxlen=200)`.
  - `observe_hit(pc_id, damage, *, round_number, observer_int)` — accumulates damage,
    appends event, marks dangerous only when `observer_int >= 10` (L-06).
  - `observe_concentration(pc_id, spell, *, round_number)` — set/clear concentration.
  - `damage_band(pc_id)` — returns `"low"|"moderate"|"high"|None` per L-02.
  - `snapshot_dict()` / `from_snapshot()` — JSON-safe persistence boundary
    (no event log; no HP/AC keys — meta-knowledge guard test enforces).
  - All public methods fail-soft per L-07 (swallow + log).
- Module constants `DAMAGE_BAND_MODERATE_MIN=5`, `DAMAGE_BAND_HIGH_MIN=15`,
  `MARK_DANGEROUS_INT_THRESHOLD=10`, `EVENT_LOG_MAX=200`.
- `MonsterMemoryRegistry`:
  - Sync `recall` / `purge_session` / `clear`.
  - Async `recall_async` / `flush` / `flush_all` / `purge_session_async` —
    Plan 21-02 hooks (opt-in repo wired structurally via Protocol so gameplay
    never hard-imports persistence).
  - `has_repo` property for the driver to choose sync vs async.

### `src/eldritch_dm/gameplay/smart_monster_driver.py` (modified — additive)

- Module-level `_augment_with_memory(slim, memory, *, pc_id)` helper. Pure
  function. Returns new dict with three added keys when memory present,
  unchanged input when memory is None, slim-unchanged on any internal failure.
- `SmartMonsterDriver.__init__` adds `monster_memory: MonsterMemoryRegistry | None = None`
  kwarg (default `None`).
- `_pick_target_llm` augments each slimmed candidate AFTER `_slim_candidate`,
  choosing `recall_async` when `registry.has_repo` else sync `recall`.
  Wrapped in try/except → fall back to unaugmented candidates on any failure.

### `src/eldritch_dm/gameplay/monster_driver_factory.py` (modified — additive)

- `make_monster_driver` forwards `monster_memory` to `SmartMonsterDriver` via
  `**driver_kwargs`. Random-mode strip list updated to pop `monster_memory`
  (and `aoe_addendum_loader`, which was missing) so the same call site can
  pass either mode the same kwargs.

## D-57 Meta-Knowledge Guard — Verification

The augmented slim-candidate dict the LLM sees adds EXACTLY three fields and
NEVER raw HP, AC, exact damage, or class/subclass:

| Field | Type | Source | Safety |
|-------|------|--------|--------|
| `recent_damage_dealt` | `"low"\|"moderate"\|"high"\|None` | `MonsterMemory.damage_band` | Categorical band — raw cumulative damage stays inside MonsterMemory |
| `concentrating_on` | `str \| None` | `MonsterMemory.concentrating_on[pc_id]` | Spell NAME is battlefield-observable; spec-conformant |
| `marked_dangerous` | `bool` | `pc_id in marked_dangerous` | INT-gated upstream (≥10) per L-06 |

Test `test_augment_with_memory_never_includes_raw_damage_or_extra_keys`
asserts the augmented key-set is exactly `slim_keys ∪ {recent_damage_dealt,
concentrating_on, marked_dangerous}` AND that the raw damage value (42) is
not present in any value. Test `test_snapshot_dict_has_no_hp_ac_keys` asserts
the persistence boundary likewise carries no `hp_current`, `hp_max`, `ac`, or
`armor_class` keys.

## D-163 — Damage observation is rules-engine-only

`MonsterMemory.observe_hit` is a public method intended to be called by the
bot cog AFTER the rules engine resolves the action. SmartMonsterDriver itself
never calls `observe_hit` — it only READS via `recall(_async)`. This preserves
mechanical honesty: the bot/LLM never invents damage.

The cog-side wiring is deferred to a v1.7 follow-up (see 21-02-SUMMARY.md's
"Known Gap" section for the survey of `combat.py:on_resolved_combat` and why
that schema is not currently typed for damage extraction).

## Fail-Soft (D-58 / D-165 / L-07)

Three failure boundaries, all swallowed + logged:

1. `MonsterMemory.observe_*` — invalid pc_id or damage type → log + no-op.
2. `MonsterMemoryRegistry.recall` — exception inside dict ops → log + return
   empty `MonsterMemory()`.
3. `_augment_with_memory` — exception during band lookup → return slim
   unchanged. Combat continues with v1.0-equivalent context.

`test_smart_driver_memory_lookup_failure_is_fail_soft` injects an exploding
registry; combat still completes correctly.

## Deviations from Plan

None — plan executed exactly as written. Two tiny cleanups baked into the
factory change:

1. Factory strip list now also pops `aoe_addendum_loader` (was missing —
   defensive cleanup for the same code path). Pre-existing, but absent from
   the strip list meant a Phase 20 kwarg could surface as an unexpected
   keyword argument on `MonsterDriver(**kwargs)` if anyone passed both. Rule
   2 (auto-add missing critical functionality) applies.
2. Tests use full-path PYTHONPATH override because the worktree shares its
   venv with the main repo's editable install of `eldritch_dm`. Documented
   here for the verifier — no production impact.

## Verification

```
$ pytest tests/gameplay/test_monster_memory.py -v          # 29 passed
$ pytest tests/gameplay/test_smart_monster_driver.py -v    # 50 passed (was 42)
$ pytest tests/gameplay/test_monster_driver_factory.py -v  # 12 passed (was 10)
$ pytest tests/gameplay/                                   # 340 passed
$ ruff check src/eldritch_dm/gameplay/monster_memory.py
                src/eldritch_dm/gameplay/smart_monster_driver.py
                src/eldritch_dm/gameplay/monster_driver_factory.py
                tests/gameplay/test_monster_memory.py
                tests/gameplay/test_smart_monster_driver.py
                tests/gameplay/test_monster_driver_factory.py             # All checks passed!
$ lint-imports                                             # 8 kept, 0 broken
```

39 new tests; 0 regression in the 96+ pre-Phase-21 smart-driver tests
(now 50; 8 new); 340 total gameplay tests pass.

## Self-Check: PASSED

- `src/eldritch_dm/gameplay/monster_memory.py` exists
- `tests/gameplay/test_monster_memory.py` exists
- SmartMonsterDriver `monster_memory` kwarg present (line ~308)
- `_augment_with_memory` exported (test imports it)
- REQUIREMENTS.md MEM-01 + MEM-02 marked [x]
- Commits: `6d8c5be feat(21-01): MonsterMemory class + Registry`,
  `df50309 feat(21-01): SmartMonsterDriver _augment_with_memory integration`,
  `e77e6f8 feat(21-01): factory accepts monster_memory kwarg`
