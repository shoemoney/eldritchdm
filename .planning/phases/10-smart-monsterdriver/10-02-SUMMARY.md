---
phase: 10-smart-monsterdriver
plan: "02"
requirements_completed: [COMBAT-14]
subsystem: gameplay/combat
tags: [adversarial-corpus, cache, env-var, factory, fail-soft, phase-closure]
requires: [10-01-SUMMARY.md, REQUIREMENTS.md::COMBAT-14, REQUIREMENTS.md::COMBAT-13]
provides:
  - gameplay.monster_driver_factory.make_monster_driver
  - config.Settings.monster_driver (MONSTER_DRIVER env var alias)
  - tests/gameplay/test_monster_driver_corpus.py (16 adversarial scenarios)
  - tests/gameplay/test_monster_driver_factory.py (10 factory tests)
affects:
  - eldritch_dm.bot.bot (orchestrator now uses make_monster_driver, shares one
    AsyncOpenAI client across smart driver + ingest cog)
tech-stack:
  added: []
  patterns: [factory-dispatch, env-var-config, fifo-cache, adversarial-corpus-tests]
key-files:
  created:
    - src/eldritch_dm/gameplay/monster_driver_factory.py
    - tests/gameplay/test_monster_driver_corpus.py
    - tests/gameplay/test_monster_driver_factory.py
    - .planning/phases/10-smart-monsterdriver/10-VERIFICATION.md
  modified:
    - src/eldritch_dm/config/__init__.py (Settings.monster_driver field)
    - src/eldritch_dm/bot/bot.py (orchestrator wire-up via factory)
    - .planning/REQUIREMENTS.md (COMBAT-13/14 ticked [x], traceability updated)
decisions: [D-52, D-56, D-58, D-60, D-61]
metrics:
  duration_minutes: ~35
  completed: 2026-05-24
---

# Phase 10 Plan 02 — Corpus, cache, factory, closure

## One-liner

Locks in production resilience for the smart driver: per-round
`(channel_id, round, monster_id)` cache with FIFO eviction, `MONSTER_DRIVER`
env-var-driven factory dispatch, 16-scenario adversarial corpus proving no
exception ever leaks to the combat orchestrator, and Phase 10 closure
artifacts (REQUIREMENTS ticked, VERIFICATION written).

## What shipped

### Per-round cache (D-56)

Implemented inside `SmartMonsterDriver._pick_target_llm` (already in Plan 01's
module): an `OrderedDict[(channel_id, round_number, monster_id),
MonsterTacticChoice]` with a 256-entry FIFO eviction guard. Cache hits are
logged as `event=smart_driver_cache_hit`. Verified by:

  - `test_corpus_cache_hit_same_key` — mock LLM called exactly once across
    two identical-key calls
  - `test_corpus_cache_fifo_eviction` — capacity-bounded test with
    `cache_max_size=3` proves the oldest entry is evicted when a fourth
    distinct key is added

### `make_monster_driver` factory + `MONSTER_DRIVER` env var (D-52, D-60)

New `gameplay/monster_driver_factory.py` centralizes driver construction.
Resolution order: explicit `env_override` arg > `Settings().monster_driver` >
`"smart"` default. Values:

  - `"smart"`  → `SmartMonsterDriver` (LLM-routed)
  - `"random"` → `MonsterDriver` (v1.0 escape hatch)
  - `"mixed"`  → `SmartMonsterDriver` (per-monster INT-gating handles mixing)
  - unknown    → log warning, fall back to `"smart"`

`Settings.monster_driver: Literal["smart","random","mixed"]` lives in
`config/__init__.py` with `alias="MONSTER_DRIVER"`. The factory pops
smart-only kwargs (`openai_client`, `llm_model`, ...) when constructing the
random driver so call sites stay mode-agnostic.

### Adversarial corpus — 16 scenarios

`tests/gameplay/test_monster_driver_corpus.py` covers the matrix from
COMBAT-14 + CONTEXT D-61:

| # | Scenario | Path verified |
|---|----------|---------------|
| 1 | malformed JSON | random fallback |
| 2 | hallucinated target id | membership check → random fallback |
| 3 | timeout exceeded (`asyncio.wait_for` fires) | log warn + random fallback |
| 4 | empty candidate list (via `drive()`) | no LLM call; `next_turn` invoked |
| 5 | sub-INT bypass (INT=2) | LLM never called |
| 6 | INT=12 with downed PC | no crash; valid pick |
| 7 | INT=18 with concentration holder | LLM consulted |
| 8 | invisible PC in candidates | no crash (engine enforces RAW, not driver) |
| 9 | refusal (empty content) | random fallback |
| 10 | rate-limit 429 (exception in `create`) | random fallback |
| 11 | cache hit (same c,r,m) | mock called once |
| 12 | PC death between calls (round changes) | cache miss → 2 LLM calls, new pick |
| 13 | cross-channel isolation | cache miss across channels |
| 14 | mixed-mode seeded determinism (INT=6) | 20× identical route |
| 15 | self-target attempt (LLM returns monster's own id) | membership check → fallback |
| + | cache FIFO eviction sanity | oldest key evicted at max_size |

Plus `test_corpus_size_meets_requirement` — a self-counting guard that fails
loudly if any future patch drops a scenario below the COMBAT-14 floor.

### Orchestrator wire-up

`bot/bot.py:341` now constructs the driver via `make_monster_driver(...)`.
The smart driver needs an `AsyncOpenAI` client — bot.py builds one from
`settings.resolve_ingest_config()` and exposes it on `self.openai_client`,
which the ingest cog already opportunistically reuses (`bot.openai_client`
injection hook). Both subsystems now talk to the same oMLX server through
one shared client.

### Phase closure

- `REQUIREMENTS.md`: COMBAT-13 / COMBAT-14 → `[x]`; traceability table
  rows replaced `TBD` with `10-01` / `10-02`
- `10-VERIFICATION.md`: walks all 7 ROADMAP success criteria with proof
  pointers (test names, file paths, commit hashes)

## Verification

```bash
# 26 new tests across Plan 02 (corpus + factory)
PYTHONPATH=src .venv/bin/pytest \
  tests/gameplay/test_monster_driver_corpus.py \
  tests/gameplay/test_monster_driver_factory.py -v
# 28 passed (16 corpus + 2 sanity + 10 factory)

# Full gameplay suite still green
PYTHONPATH=src .venv/bin/pytest tests/gameplay/
# 250 passed

# Repo-wide (1 pre-existing flaky test in tests/tools/ — out of scope)
PYTHONPATH=src .venv/bin/pytest --ignore=tests/integration
# 1050 passed, 1 failed (pre-existing flake; passes in isolation)
```

```bash
.venv/bin/ruff check src/eldritch_dm/gameplay/ \
                    src/eldritch_dm/bot/bot.py \
                    src/eldritch_dm/config/__init__.py \
                    tests/gameplay/test_monster_driver_corpus.py \
                    tests/gameplay/test_monster_driver_factory.py
# All checks passed!
```

## Deferred Issues

- One pre-existing flake in `tests/tools/test_backfill_pc_classes.py::test_collect_rows_subclass_warning_emitted`
  (passes in isolation, fails when run in full suite). Out of scope per
  executor SCOPE BOUNDARY — predates Phase 10 and lives outside `gameplay/`.

## Deviations from plan

None substantive — plan executed as written. The corpus ended up with 16
scenarios (one extra: cache FIFO eviction) which exceeds the COMBAT-14 floor
of 15. Plan task 5b (closure) intentionally appended a meta-test
(`test_corpus_size_meets_requirement`) that fails loudly if the floor is
ever broken by a future drop.

## Self-Check: PASSED

All claimed files exist on disk; all claimed commits exist on this branch.
