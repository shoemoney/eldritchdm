# Phase 8 — Verification (CC-2 hygiene gate)

Executed at the close of Plan 08-01.

## Hygiene Gates

| Gate | Result | Command |
|------|--------|---------|
| `ruff check` on new + touched src files | PASS (0 errors) | `uv run ruff check src/eldritch_dm/gameplay/normalize.py src/eldritch_dm/gameplay/eligibility_loader.py src/eldritch_dm/gameplay/reactions.py src/eldritch_dm/persistence/pc_classes_repo.py src/eldritch_dm/config/__init__.py src/eldritch_dm/bot/bot.py src/eldritch_dm/gameplay/monster_driver.py` |
| `lint-imports` | 7/7 KEPT | `uv run lint-imports` |
| safe_load CI gate (negative path) | exit 0 | `bash scripts/ci/check_safe_yaml.sh` |
| safe_load CI gate (positive path) | exit 1 against planted `yaml.load(` | manually verified (see PLAN Task 6 §4) |
| `pytest tests/gameplay/test_normalize.py` | 11 passed | |
| `pytest tests/gameplay/test_eligibility_loader.py` | 19 passed | |
| `pytest tests/gameplay/test_reactions.py` | 14 passed (v1.0 zero regression) | |
| `pytest tests/gameplay/test_monster_driver.py` | 15 passed | |
| `pytest tests/integration/test_riposte_restart.py` | 6 passed | |

## Behavior Checks

| Check | Result |
|-------|--------|
| Vanilla install byte-identical to v1.0 (D-30) | `load_eligibility(Settings()) == frozenset({('fighter','battle master')})` |
| Default YAML parses cleanly | `yaml.safe_load(open('database/eligibility.yaml'))` returns `{'version': 1, 'mode': 'extend', 'eligible': {'fighter': ['battle master']}}` |
| Malicious `!!python/object/apply` rejected | sentinel `/tmp/eldritch_pwn_DO_NOT_RUN` NOT created |
| extend semantics work | `swashbuckler_extend.yaml` → fighter:battle master + rogue:swashbuckler |
| replace semantics wipe defaults | `valid_replace.yaml` → only rogue:swashbuckler |
| Casing normalized | `Fighter` / `BATTLE MASTER` in YAML → `('fighter', 'battle master')` in resolved set |

## Documentation Checks

| Artifact | Status |
|----------|--------|
| `INSTALL.md` "Homebrew Riposte Eligibility" section | Present (extend + replace + failure-semantics + RAI caveat + restart-to-apply) |
| `.env.example` documents `ELDRITCH_ELIGIBILITY_YAML` | Present (commented-out with explanation) |
| `database/eligibility.yaml` ships with v1.0 D-C set | Present + parses to `{fighter: [battle master]}` |

## Cold-Start E2E Coverage (Phase 6 lesson)

The full path `bot.setup_hook → load_eligibility(settings) → MonsterDriver.__init__(eligibility_set=…) → check_riposte_eligibility(eligibility_set=…)` is exercised without mocks by:

- `tests/gameplay/test_eligibility_loader.py::test_env_path_overrides_per_install_and_in_repo` — env-tier path resolution with real YAML on disk.
- `tests/gameplay/test_eligibility_loader.py::test_load_eligibility_never_raises[*]` — parametrized over every bad fixture, proves fail-soft invariant.
- `tests/gameplay/test_reactions.py::*` — all 14 v1.0 cases unchanged, proving the `eligibility_set is None → ELIGIBLE_CLASS_SUBCLASSES` fallback path is preserved.
- `tests/gameplay/test_monster_driver.py::*` — 15 cases all green, proves the driver's `_maybe_surface_riposte` still calls `check_riposte_eligibility` correctly with the new kwarg threaded through.

## Closure

All 7 closure-checklist items from `08-CONTEXT.md` are satisfied except the STATE/ROADMAP updates, which are explicitly deferred to the orchestrator per executor prompt.
