---
phase: 08-yaml-riposte-eligibility
plan: 01
subsystem: gameplay
tags: [yaml, pydantic, homebrew, eligibility, riposte]
requires:
  - "Phase 5 Plan 01 — reactions.check_riposte_eligibility shape"
  - "Phase 5 Plan 01 — persistence.pc_classes_repo (provides _normalize)"
provides:
  - "src/eldritch_dm/gameplay/normalize.py::normalize"
  - "src/eldritch_dm/gameplay/eligibility_loader.py::load_eligibility"
  - "src/eldritch_dm/gameplay/eligibility_loader.py::DEFAULT_ELIGIBILITY"
  - "src/eldritch_dm/gameplay/eligibility_loader.py::EligibilityFile"
  - "database/eligibility.yaml (v1.0 D-C set, ships in repo)"
  - "scripts/ci/check_safe_yaml.sh (T-08-01 CI gate)"
  - "bot.eligibility_set attribute on EldritchBot"
affects:
  - "src/eldritch_dm/persistence/pc_classes_repo.py (delegates to gameplay.normalize)"
  - "src/eldritch_dm/gameplay/reactions.py (eligibility_set kwarg added)"
  - "src/eldritch_dm/gameplay/monster_driver.py (threads eligibility_set through)"
  - "src/eldritch_dm/bot/bot.py (calls load_eligibility at setup_hook)"
  - "src/eldritch_dm/config/__init__.py (new Settings.eligibility_yaml_path)"
tech-stack:
  added:
    - "pyyaml>=6.0.3,<7.0 — promoted from [dev] to core (D-37)"
  patterns:
    - "Fail-soft YAML loader with structlog warning + DEFAULT_ELIGIBILITY fallback"
    - "Pydantic v2 schema with model_config = ConfigDict(extra='forbid')"
    - "3-tier path resolution: env > per-install > in-repo default"
    - "yaml.safe_load ONLY; CI grep gate enforces"
key-files:
  created:
    - "src/eldritch_dm/gameplay/normalize.py"
    - "src/eldritch_dm/gameplay/eligibility_loader.py"
    - "database/eligibility.yaml"
    - "scripts/ci/check_safe_yaml.sh"
    - "tests/gameplay/test_normalize.py"
    - "tests/gameplay/test_eligibility_loader.py"
    - "tests/fixtures/eligibility/valid_extend.yaml"
    - "tests/fixtures/eligibility/valid_replace.yaml"
    - "tests/fixtures/eligibility/swashbuckler_extend.yaml"
    - "tests/fixtures/eligibility/malicious_python_object.yaml"
    - "tests/fixtures/eligibility/unknown_key.yaml"
    - "tests/fixtures/eligibility/bad_version.yaml"
    - ".planning/phases/08-yaml-riposte-eligibility/VERIFICATION.md"
  modified:
    - "pyproject.toml"
    - "src/eldritch_dm/persistence/pc_classes_repo.py"
    - "src/eldritch_dm/gameplay/reactions.py"
    - "src/eldritch_dm/gameplay/monster_driver.py"
    - "src/eldritch_dm/bot/bot.py"
    - "src/eldritch_dm/config/__init__.py"
    - ".env.example"
    - "INSTALL.md"
    - ".pre-commit-config.yaml"
    - ".planning/REQUIREMENTS.md"
decisions:
  - "D-29: 3-tier YAML precedence env > per-install > in-repo"
  - "D-30: in-repo default ships v1.0 D-C frozenset (byte-identical vanilla)"
  - "D-31: yaml.safe_load ONLY; CI grep gate enforces"
  - "D-32: pydantic v2 with extra='forbid'"
  - "D-33: fail-soft on any error → DEFAULT_ELIGIBILITY + structlog warning"
  - "D-34: extend-by-default; mode: replace opts in to full override"
  - "D-35: restart-to-apply only; no hot reload in v1.1"
  - "D-36: shared gameplay/normalize.py for casing parity"
  - "D-37: pyyaml 6.0.3 promoted to core dep"
  - "D-38: reactions.ELIGIBLE_CLASS_SUBCLASSES kept as in-module fallback"
  - "D-39: new Settings.eligibility_yaml_path bound to ELDRITCH_ELIGIBILITY_YAML"
  - "D-40: schema shape version/mode/eligible; reject version != 1"
metrics:
  tasks_completed: 7
  files_created: 13
  files_modified: 10
  tests_added: 30  # 11 normalize + 19 eligibility_loader (incl. parametrized)
  duration_minutes: ~25
  completed_date: 2026-05-24
---

# Phase 8 Plan 01: YAML Riposte Eligibility Summary

Loader-driven homebrew Riposte eligibility — vanilla installs are byte-identical
to v1.0, while self-hosters can extend (or fully replace) the eligible
class/subclass set via a YAML file at any of 3 tiers, without code edits.

## What Shipped

- **`gameplay/normalize.py`** — shared casing/whitespace normalizer extracted
  from `persistence.pc_classes_repo._normalize`. Single source of truth so
  YAML author casing and dm20 ingest casing produce identical frozenset keys.
- **`gameplay/eligibility_loader.py`** — pure-function loader with 3-tier
  path resolution, `yaml.safe_load` (never `load`), pydantic v2
  `extra='forbid'` schema, and a try/except-everywhere fail-soft contract.
  Always returns a `frozenset[tuple[str, str]]`; never raises.
- **`database/eligibility.yaml`** — in-repo default shipping the v1.0 D-C
  set (`fighter: [battle master]`) so vanilla `pip install -e .` reproduces
  v1.0 behavior exactly.
- **`scripts/ci/check_safe_yaml.sh`** — bash CI gate that fails the build if
  `yaml.load(` (without `safe_`) appears anywhere in `src/`. Verified
  bidirectional: exits 0 against current tree; exits 1 against a planted
  unsafe call. Also wired into `.pre-commit-config.yaml`.
- **`bot.eligibility_set`** — `setup_hook` resolves the YAML once and stores
  the frozenset on the bot. `MonsterDriver` consumes it via its new
  `eligibility_set` constructor kwarg; `check_riposte_eligibility` threads
  it through with a fallback to the in-module `ELIGIBLE_CLASS_SUBCLASSES`
  constant for legacy test callers.
- **Docs:** `INSTALL.md` gains a "Homebrew Riposte Eligibility" section with
  extend + replace examples, failure semantics, RAW-vs-RAI caveat, and
  restart-to-apply note. `.env.example` documents `ELDRITCH_ELIGIBILITY_YAML`.

## Atomic Commits (7)

| # | Hash | Title |
|---|------|-------|
| 1 | `2ba72e7` | chore(08-01): promote pyyaml 6.0.3 from [dev] to core (HOMEBREW-01) |
| 2 | `f66ce27` | refactor(08-01): extract _normalize to gameplay/normalize.py (D-36) |
| 3 | `1ee7861` | feat(08-01): eligibility_loader.py — 3-tier YAML resolver + pydantic schema + fail-soft |
| 4 | `f627151` | refactor(08-01): inject eligibility_set into check_riposte_eligibility + ship database/eligibility.yaml |
| 5 | `9199318` | feat(08-01): wire eligibility loader into setup_hook + Settings + .env.example + INSTALL.md |
| 6 | `5a3f540` | chore(08-01): CI grep gate enforcing yaml.safe_load only (T-08-01) |
| 7 | (this commit) | test(08-01): eligibility_loader test suite + Phase 8 closure |

## Tests

- 11 tests in `tests/gameplay/test_normalize.py` — all pass.
- 19 tests in `tests/gameplay/test_eligibility_loader.py` — all pass; covers
  3-tier precedence, extend/replace, fail-soft, malicious YAML, casing,
  resolved-set INFO log, never-raises invariant, schema-level extra='forbid'.
- 286 pre-existing Phase 5 / persistence / integration Riposte tests still
  green — zero v1.0 regression.

## Threat Mitigations

| Threat | Mitigation |
|--------|------------|
| T-08-01 (Tampering/RCE via YAML) | `safe_load` only; pydantic `extra='forbid'`; CI grep gate; `malicious_python_object.yaml` fixture with sentinel-file assertion |
| T-08-02 (DoS via bad YAML) | try/except-everywhere fail-soft; bot continues with DEFAULT_ELIGIBILITY |
| T-08-05 (Repudiation) | `log.info("eligibility.resolved", source, mode, count, entries=…)` on every successful load |
| T-08-SC (Supply chain — pyyaml promote) | PyYAML is [OFFICIAL]; pinned `>=6.0.3,<7.0`; was already in `[dev]` |

## Deviations from Plan

Documented inline; no architectural deviations (no Rule 4 events).

1. **[Rule 3 — Blocking discrepancy] Wired through `monster_driver.py`, not `combat.py`.**
   Plan Task 5 said "Edit `src/eldritch_dm/bot/cogs/combat.py` — find the single
   call site that invokes `check_riposte_eligibility(...)`". The actual single
   call site is in `gameplay/monster_driver.py::_maybe_surface_riposte`
   (line 247). `combat.py` has zero references. Fixed by threading
   `eligibility_set` into `MonsterDriver.__init__` and using
   `self._eligibility_set` at the call site — same data flow, correct file.
   Commit: `9199318`.

2. **[Rule 3 — Blocking discrepancy] Patched root `INSTALL.md`, not `docs/INSTALL.md`.**
   Plan said `docs/INSTALL.md`. Repo ships `INSTALL.md` at the root (852 lines)
   and `docs/` is a sibling. Appended the Homebrew Riposte section to the
   existing root file rather than creating a duplicate. Commit: `9199318`.

3. **[Rule 2 — Auto-add missing critical functionality] Added `populate_by_name=True`
   to `SettingsConfigDict`.** Without it, the plan's verification command
   `Settings(eligibility_yaml_path=path)` silently dropped the value because
   pydantic-settings prefers the alias name (`ELDRITCH_ELIGIBILITY_YAML`).
   This would have caused every test in Task 7 to fail in mysterious ways.
   Commit: `9199318`.

## Auth Gates

None.

## Known Stubs

None. The loader is a complete pure function; the bot wires it at startup;
no UI surfaces gate on placeholder data.

## Deferred Issues (out-of-scope per Rule 3 scope boundary)

Three pre-existing test failures in `tests/ingest/test_pipeline.py` and
`tests/integration/test_phase3_smoke.py` reproduce at HEAD~6 (before any
Phase 8 work). They concern the Phase 3 ingest pipeline, which Phase 8 does
not touch. Logged to `deferred-items.md` in the phase directory.

## Verification

See `VERIFICATION.md` in this directory for the full CC-2 hygiene gate
checklist (ruff, lint-imports, safe_load gate bidirectional, all targeted
test suites green, behavior + documentation + cold-start coverage).

## Dependency Delta

- **Net:** +1 promoted dep (`pyyaml` moved from `[dev]` to core), 0 new pip
  packages. `[dev]` extras list also shortened by one line.

## Net Test Count

864 baseline → 894 (after 30 new tests across `test_normalize.py` and
`test_eligibility_loader.py`). All 894 pass. Pre-existing 3 failures noted
above are unchanged.

## Self-Check: PASSED

- `database/eligibility.yaml` — FOUND
- `src/eldritch_dm/gameplay/normalize.py` — FOUND
- `src/eldritch_dm/gameplay/eligibility_loader.py` — FOUND
- `scripts/ci/check_safe_yaml.sh` — FOUND (executable)
- `tests/gameplay/test_normalize.py` — FOUND (11 tests)
- `tests/gameplay/test_eligibility_loader.py` — FOUND (19 tests)
- `tests/fixtures/eligibility/*.yaml` — 6 fixtures FOUND
- `.planning/phases/08-yaml-riposte-eligibility/VERIFICATION.md` — FOUND
- Commit hashes 2ba72e7, f66ce27, 1ee7861, f627151, 9199318, 5a3f540 — FOUND in git log
