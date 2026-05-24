---
phase: 08-yaml-riposte-eligibility
milestone: v1.1
generated: 2026-05-23
source_research:
  - .planning/research/SUMMARY.md
  - .planning/research/STACK.md
  - .planning/research/ARCHITECTURE.md
  - .planning/research/PITFALLS.md
source_requirements:
  - HOMEBREW-01
  - HOMEBREW-02
---

# Phase 8 — YAML Riposte Eligibility (CONTEXT)

## Mission

Let homebrew DMs add Riposte-eligible class/subclass pairs (Swashbuckler Rogue,
third-party content) without code edits, while keeping the v1.0 D-C strict-RAW
Battle Master Fighter as the shipped default. **Vanilla installs are
byte-identical to v1.0 behavior** — no forced config burden.

## Locked Decisions (binding on the planner)

| ID | Decision | Source |
|----|----------|--------|
| **D-29** | **3-tier YAML precedence: `$ELDRITCH_ELIGIBILITY_YAML` (env) > `~/.eldritch/eligibility.yaml` (per-install) > `database/eligibility.yaml` (in-repo default)**. Closest wins. | ARCHITECTURE.md §2.1 + SUMMARY.md Q2 |
| **D-30** | **In-repo default ships with v1.0 D-C frozenset** — `{fighter: [battle master]}`. Vanilla `pip install -e .` users get identical v1.0 behavior. | ARCHITECTURE.md §2.1 + Roadmap success criterion 1 |
| **D-31** | **`yaml.safe_load` is the only permitted YAML API.** CI grep gate fails the build on `yaml.load(` (without `safe`) anywhere in `src/`. Documented as `bash -c "git grep -nE 'yaml\\.load\\(' src/ && exit 1 || exit 0"` style check. | PITFALLS.md YAML-1 (CRITICAL) + STACK.md §2 |
| **D-32** | **Pydantic v2 schema with `model_config = ConfigDict(extra='forbid')`** rejects unknown YAML keys at load time. | STACK.md §2 + PITFALLS.md YAML-1 |
| **D-33** | **Fail-soft on bad YAML:** missing file OR parse error OR pydantic-validation error → `structlog.warning("eligibility.fallback", reason=...)` + fall back to v1.0 hardcoded defaults. **Never crash the bot.** | PITFALLS.md YAML-3 (HIGH) + Roadmap success criterion 2 |
| **D-34** | **Extend-by-default semantics.** User YAML *adds* to v1.0 defaults. Explicit top-level `mode: replace` opts in to full override. | PITFALLS.md YAML-4 + Roadmap success criterion 4 |
| **D-35** | **Restart-to-apply only — NO hot reload in v1.1.** SIGHUP / file-watcher / admin command deferred to v1.2 candidate per PITFALLS YAML-2. | PITFALLS.md YAML-2 + Out-of-scope §44 of REQUIREMENTS.md |
| **D-36** | **Normalize casing via shared `_normalize` helper extracted to new `gameplay/normalize.py` module.** `Battle Master` / `battle master` / `BATTLE MASTER` all hash equivalently. `pc_classes_repo._normalize` becomes `from eldritch_dm.gameplay.normalize import normalize`. | ARCHITECTURE.md §2.3 + PITFALLS.md YAML-6 |
| **D-37** | **Promote `pyyaml>=6.0.3,<7.0` from `[project.optional-dependencies.dev]` to `[project.dependencies]`.** Pin floor at 6.0.3 (current as of 2026-05-23, FullLoader explicitly marked unsafe upstream). Remove the `pyyaml>=6.0,<7.0` line from `[dev]`. | STACK.md §2 + Recommended Pin Changes |
| **D-38** | **`reactions.ELIGIBLE_CLASS_SUBCLASSES` becomes the in-module fallback constant** (used only when the loader fails). `check_riposte_eligibility` accepts an injected `eligibility_set: frozenset[tuple[str, str]] \| None = None` kwarg (default `None` → use module fallback). `bot/setup_hook` calls `load_eligibility(settings)` once at startup and threads the resulting frozenset into the call sites. | ARCHITECTURE.md §2.4 + Roadmap success criterion 5 |
| **D-39** | **New `Settings.eligibility_yaml_path: Path \| None = None`** field. When set, used as the env-override path; otherwise the loader walks per-install + in-repo paths. `.env.example` documents `ELDRITCH_ELIGIBILITY_YAML`. | ARCHITECTURE.md §2.5 + pydantic-settings convention |
| **D-40** | **Schema shape — top-level `version: int = 1`, `mode: Literal["extend", "replace"] = "extend"`, `eligible: dict[str, list[str]]`.** `dict` keyed by class name maps to list of subclass names. The structure mirrors PITFALLS YAML-4's example. `version` field reserved for v1.2+ migrations; reject `version != 1` with warning + fallback. | PITFALLS.md YAML-4 + ARCHITECTURE.md §2.3 (revised) |

## Deferred to v1.2+ (NOT in this phase)

- YAML hot-reload via SIGHUP / `/admin reload-eligibility` / file-watcher (PITFALLS YAML-2, REQUIREMENTS §44)
- `homebrew: true` opt-in flag to suppress unknown-subclass warnings (PITFALLS YAML-5)
- Per-PC eligibility overrides (REQUIREMENTS §51)
- Validating user YAML against dm20's known class/subclass list (PITFALLS YAML-5)
- `schema_version: 2+` migration logic (D-40 reserves the slot only)

## In-Scope Files

**Created:**
- `database/eligibility.yaml` — ships v1.0 D-C frozenset; commented walkthrough of `mode: extend` vs `mode: replace`
- `src/eldritch_dm/gameplay/normalize.py` — extracts `_normalize` from `pc_classes_repo` for shared use
- `src/eldritch_dm/gameplay/eligibility_loader.py` — pydantic schema + 3-tier resolver + `load_eligibility()` with fail-soft
- `tests/gameplay/test_normalize.py` — round-trip + casing tests
- `tests/gameplay/test_eligibility_loader.py` — 3-tier precedence, extend-vs-replace, malformed-YAML fail-soft, `extra=forbid` rejection, version reject, casing
- `tests/fixtures/eligibility/` — directory with `valid_extend.yaml`, `valid_replace.yaml`, `malicious_python_object.yaml`, `unknown_key.yaml`, `bad_version.yaml`, `swashbuckler_extend.yaml`
- `scripts/ci/check_safe_yaml.sh` — grep gate (one-liner script committed for CI + pre-commit hook reuse)

**Modified:**
- `pyproject.toml` — promote `pyyaml>=6.0.3,<7.0` to `[project.dependencies]`; remove from `[dev]`
- `src/eldritch_dm/persistence/pc_classes_repo.py` — replace inline `_normalize` with `from eldritch_dm.gameplay.normalize import normalize`
- `src/eldritch_dm/gameplay/reactions.py` — `check_riposte_eligibility` accepts `eligibility_set` kwarg with module-constant fallback; `ELIGIBLE_CLASS_SUBCLASSES` kept as the fallback constant
- `src/eldritch_dm/config.py` — add `eligibility_yaml_path: Path | None = None` Settings field bound to `ELDRITCH_ELIGIBILITY_YAML`
- `src/eldritch_dm/bot/setup_hook.py` — call `load_eligibility(settings)` once at startup; thread the resolved frozenset into the call site (cog/registration that builds `check_riposte_eligibility`)
- `src/eldritch_dm/bot/cogs/combat.py` (or wherever MonsterDriver invokes `check_riposte_eligibility`) — pass `eligibility_set` through (single call site per Architecture §2.4 grep result)
- `.env.example` — document `ELDRITCH_ELIGIBILITY_YAML`
- `docs/INSTALL.md` (or `README.md` if INSTALL.md absent) — add "Homebrew Riposte Eligibility" subsection with extend + replace examples
- `.pre-commit-config.yaml` (if present) — add `safe_load`-only hook calling `scripts/ci/check_safe_yaml.sh`

**Out-of-scope (do NOT touch):**
- `src/eldritch_dm/gameplay/monster_driver.py` (Phase 10 owns this)
- `src/eldritch_dm/bot/modals.py` (Phase 7 owns sanitizer wiring)
- `src/eldritch_dm/bot/warnings.py` (Phase 7 owns DM_OFFLINE)
- `src/eldritch_dm/scripts/` (Phase 9 owns the new subpackage)
- Any `tests/integration/test_cold_start_*` file (Phase 6 owns the cold-start smoke)

## Architectural Constraints

1. **Import-linter:** Stays inside `gameplay/` + `persistence/` + `config/` + `bot/setup_hook.py`. No new contract block. `gameplay.normalize` is pure stdlib (`re`) — no upward imports.
2. **Integrity rule:** Loader is pure data resolution. Touches no dm20, no LLM, no SQLite. Pure function from `(Settings, filesystem)` → `frozenset[tuple[str, str]]`.
3. **Defer-discipline (EDM001):** Not applicable — no interaction callbacks added.
4. **Atomic-commit + conventional-prefix:** Each commit listed in PLAN below is a bisectable unit with a matching test pass.
5. **Cold-start E2E (Phase 6 lesson):** The phase ships with one integration-style test that exercises the full path: bot.setup_hook → load_eligibility (with `ELDRITCH_ELIGIBILITY_YAML` pointed at a test fixture) → check_riposte_eligibility honors the YAML-augmented set. No mocks beyond the path env var.

## Threat Model (STRIDE — security_enforcement enabled)

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| **T-08-01** | **Tampering / Elevation** | `eligibility_loader.py` YAML parser | **mitigate** | `yaml.safe_load` ONLY (D-31). CI grep gate fails build if `yaml.load(` (without `safe`) appears anywhere in `src/`. Pydantic v2 `extra='forbid'` rejects unknown keys (D-32). Fixture `malicious_python_object.yaml` contains `!!python/object/apply:os.system ['echo pwn']` and asserts parser refuses (not just our pydantic layer). |
| **T-08-02** | **Denial of Service** | `eligibility_loader.py` startup load | **mitigate** | Fail-soft to v1.0 defaults (D-33) — corrupt YAML logs warning, does not crash bot. Bot remains usable. |
| **T-08-03** | **Tampering** | `database/eligibility.yaml` (in-repo default) | **accept** | File is committed; tampering requires repo write access (already a threat the project accepts). |
| **T-08-04** | **Information Disclosure** | YAML file on disk | **accept** | File contains class/subclass lookup data only — no secrets, no PII. |
| **T-08-05** | **Repudiation** | Resolved eligibility set | **mitigate** | `structlog.info("eligibility.resolved", source=<path>, mode=<extend|replace>, count=N, set=[...])` at INFO level — operator can grep their JSON logs for what was loaded. |
| **T-08-SC** | **Tampering (Supply Chain)** | `pyyaml>=6.0.3` promotion | **mitigate** | PyYAML is `[OFFICIAL]` per RESEARCH.md Package Legitimacy (canonical Python YAML lib, pyyaml.org / yaml/pyyaml on GitHub, >5M weekly DL on PyPI). Already in `[dev]` since Phase 1 — no first-touch risk. Pin floor at 6.0.3 (current stable per STACK §2). No blocking checkpoint needed. |

**Trust boundaries:** Filesystem (user-controlled YAML files) → Python process. Network is NOT crossed at any point in this phase.

## Source Audit (multi-source coverage)

| Source | Item | Covered by |
|--------|------|------------|
| **GOAL** (ROADMAP §Phase 8) | Homebrewers add Riposte subclasses without code | Plan 08-01 entire scope |
| **GOAL** | Keep v1.0 D-C Battle Master Fighter as default | D-30, ships `database/eligibility.yaml` with v1.0 set |
| **REQ HOMEBREW-01** | 3-tier YAML loader at `gameplay/eligibility_loader.py`, safe_load only, pydantic forbid, fail-soft | Plan 08-01 Task 3 + Task 6 (CI gate) + Task 7 (fail-soft tests) |
| **REQ HOMEBREW-02** | Extend-not-override default, `mode: replace` opt-in, casing normalized via shared `_normalize`, restart-to-apply | Plan 08-01 Task 2 (normalize extract) + Task 3 (mode field) + Task 7 (mode tests) + D-35 (no hot reload) |
| **RESEARCH STACK** | Promote pyyaml 6.0.3 from [dev] to core | Plan 08-01 Task 1 |
| **RESEARCH STACK** | safe_load + pydantic v2 `extra='forbid'` | Plan 08-01 Task 3 + Task 7 |
| **RESEARCH ARCH §2.1** | 3-tier precedence (env > per-install > in-repo) | Plan 08-01 Task 3 (resolver) + Task 7 (precedence tests) |
| **RESEARCH ARCH §2.3** | Extract `_normalize` to `gameplay/normalize.py` | Plan 08-01 Task 2 |
| **RESEARCH ARCH §2.4** | `check_riposte_eligibility` injection point | Plan 08-01 Task 4 (reactions.py refactor) |
| **RESEARCH ARCH §2.5** | New Settings field + setup_hook wiring + .env.example + docs | Plan 08-01 Task 5 |
| **RESEARCH PITFALLS YAML-1** | safe_load grep CI gate + malicious YAML test | Plan 08-01 Task 6 (CI gate) + Task 7 (malicious fixture) |
| **RESEARCH PITFALLS YAML-2** | No hot reload v1.1 | D-35 (decision, not a code task) |
| **RESEARCH PITFALLS YAML-3** | Fail-soft + structured warning | Plan 08-01 Task 3 (loader) + Task 7 (corrupt YAML test) |
| **RESEARCH PITFALLS YAML-4** | Extend-vs-replace explicit; resolved-set logged | Plan 08-01 Task 3 (mode field + log) + Task 7 (both-modes test) |
| **RESEARCH PITFALLS YAML-5** | Cross-pollination warning (Hunter ≠ Riposte) | **Deferred to v1.2** per CONTEXT §"Deferred" — documented in INSTALL.md disclaimer (Task 5) |
| **RESEARCH PITFALLS YAML-6** | Casing normalization | Plan 08-01 Task 2 (extract) + Task 7 (casing test) |
| **CONTEXT D-29..D-40** | All 12 locked decisions | Distributed across all 7 tasks of Plan 08-01 (per decision-ID column above) |

**Audit result:** No unplanned items. All source artifacts have a covering task. Phase fits in one plan (~50% context).

## Success Criteria (verbatim from ROADMAP)

1. `database/eligibility.yaml` ships with `{fighter: [battle master]}` — matches v1.0 RAW default exactly.
2. `src/eldritch_dm/gameplay/eligibility_loader.py` resolves YAML in 3-tier precedence (env > per-install > in-repo), pydantic-validated, `safe_load` only, fail-soft to defaults on bad YAML with structured-log warning.
3. CI grep gate fails the build if `yaml.load` (unsafe) ever appears in the codebase.
4. Extend-not-override is the default; explicit `mode: replace` opt-in. Override semantics documented in INSTALL.md with an example.
5. `reactions.ELIGIBLE_CLASS_SUBCLASSES` no longer hardcoded — pulled from loader. Existing v1.0 Riposte tests still green (default YAML preserves v1.0 behavior).

## Closure Checklist (gates before phase complete)

- [ ] Both HOMEBREW-01 + HOMEBREW-02 ticked in `.planning/REQUIREMENTS.md`
- [ ] `ruff check src/eldritch_dm/gameplay/eligibility_loader.py src/eldritch_dm/gameplay/normalize.py` returns 0
- [ ] `lint-imports` — 7/7 contracts still KEPT (this phase adds no new contracts)
- [ ] `pytest tests/gameplay/test_eligibility_loader.py tests/gameplay/test_normalize.py` all green
- [ ] All pre-existing v1.0 Riposte tests still green (`pytest tests/gameplay/test_reactions.py` and any `tests/integration/test_riposte_*`)
- [ ] `scripts/ci/check_safe_yaml.sh` exits 0 against current `src/` tree
- [ ] `database/eligibility.yaml` exists; `yaml.safe_load(open("database/eligibility.yaml"))` parses cleanly
- [ ] INSTALL.md (or README.md) updated with extend + replace examples
- [ ] `.env.example` documents `ELDRITCH_ELIGIBILITY_YAML`
- [ ] STATE.md updated with D-29..D-40 entries
- [ ] ROADMAP Phase 8 row flipped to ✅ Complete
- [ ] `VERIFICATION.md` written for the phase (per CC-2 hygiene gate)
