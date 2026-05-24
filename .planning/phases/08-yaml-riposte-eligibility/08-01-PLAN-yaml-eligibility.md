---
phase: 08-yaml-riposte-eligibility
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - database/eligibility.yaml
  - src/eldritch_dm/gameplay/normalize.py
  - src/eldritch_dm/gameplay/eligibility_loader.py
  - src/eldritch_dm/gameplay/reactions.py
  - src/eldritch_dm/persistence/pc_classes_repo.py
  - src/eldritch_dm/config.py
  - src/eldritch_dm/bot/setup_hook.py
  - src/eldritch_dm/bot/cogs/combat.py
  - .env.example
  - docs/INSTALL.md
  - scripts/ci/check_safe_yaml.sh
  - tests/gameplay/test_normalize.py
  - tests/gameplay/test_eligibility_loader.py
  - tests/fixtures/eligibility/valid_extend.yaml
  - tests/fixtures/eligibility/valid_replace.yaml
  - tests/fixtures/eligibility/malicious_python_object.yaml
  - tests/fixtures/eligibility/unknown_key.yaml
  - tests/fixtures/eligibility/bad_version.yaml
  - tests/fixtures/eligibility/swashbuckler_extend.yaml
autonomous: true
requirements:
  - HOMEBREW-01
  - HOMEBREW-02
tags:
  - yaml
  - pydantic
  - homebrew
  - eligibility

must_haves:
  truths:
    - "A homebrew DM can add `{fighter: [echo knight]}` to a YAML file, restart the bot, and have an Echo Knight Fighter trigger Riposte on a monster miss"
    - "A homebrew DM with `mode: replace` and `{rogue: [swashbuckler]}` REMOVES Battle Master Fighter from the eligible set (full override)"
    - "A self-hoster with no YAML file at any of the 3 tiers sees identical v1.0 behavior — only Battle Master Fighter ripostes"
    - "A self-hoster who corrupts their YAML (typo, malformed) sees a structured-log warning in JSON output AND the bot starts AND v1.0 behavior is preserved"
    - "A malicious YAML containing `!!python/object/apply:os.system [...]` does NOT execute the payload (safe_load refuses) and falls through to v1.0 defaults"
    - "Casing variants (`Battle Master`, `BATTLE MASTER`, `battle  master`) all hash equivalently after `_normalize`"
    - "CI build fails on a PR that adds `yaml.load(stream)` (without `safe`) anywhere in `src/`"
  artifacts:
    - path: "database/eligibility.yaml"
      provides: "In-repo default YAML (D-30 — v1.0 D-C set)"
      contains: "battle master"
    - path: "src/eldritch_dm/gameplay/normalize.py"
      provides: "Shared casing/whitespace normalizer (D-36 extraction)"
      exports: ["normalize"]
      min_lines: 15
    - path: "src/eldritch_dm/gameplay/eligibility_loader.py"
      provides: "3-tier YAML resolver + pydantic schema + fail-soft load_eligibility()"
      exports: ["load_eligibility", "EligibilityFile", "DEFAULT_ELIGIBILITY"]
      min_lines: 80
    - path: "scripts/ci/check_safe_yaml.sh"
      provides: "Grep gate enforcing yaml.safe_load only (T-08-01 mitigation)"
      contains: "yaml.load"
    - path: "tests/gameplay/test_eligibility_loader.py"
      provides: "3-tier precedence + extend/replace + fail-soft + malicious + casing + version tests"
      min_lines: 120
    - path: "tests/fixtures/eligibility/malicious_python_object.yaml"
      provides: "Adversarial fixture for T-08-01 / YAML-1 test"
      contains: "python/object"
  key_links:
    - from: "src/eldritch_dm/bot/setup_hook.py"
      to: "src/eldritch_dm/gameplay/eligibility_loader.py::load_eligibility"
      via: "single startup call before cog registration"
      pattern: "load_eligibility\\("
    - from: "src/eldritch_dm/gameplay/reactions.py::check_riposte_eligibility"
      to: "loader-resolved frozenset[tuple[str, str]]"
      via: "injected `eligibility_set` kwarg with ELIGIBLE_CLASS_SUBCLASSES fallback"
      pattern: "eligibility_set"
    - from: "src/eldritch_dm/persistence/pc_classes_repo.py"
      to: "src/eldritch_dm/gameplay/normalize.py::normalize"
      via: "module-level import replacing inline _normalize"
      pattern: "from eldritch_dm.gameplay.normalize import normalize"
---

<objective>
Promote PyYAML to a core dependency and ship a fail-soft, safe_load-only,
pydantic-validated YAML loader that resolves Riposte eligibility from a
3-tier path (env > per-install > in-repo default) with extend-by-default
semantics and explicit `mode: replace` opt-in. Refactor `reactions.py` to
consume the loader-resolved frozenset while keeping the v1.0 hardcoded
constant as the fail-soft fallback. Extract the existing `_normalize`
helper from `pc_classes_repo` into a shared `gameplay/normalize.py` so the
loader and repo agree on casing. Land a CI grep gate that fails the build
on any `yaml.load(` (without `safe`) anywhere in `src/`. Document the
override semantics in INSTALL.md with extend + replace examples.

Purpose: Close HOMEBREW-01 + HOMEBREW-02 — the only v1.1 user-visible
extensibility surface — without touching code paths owned by Phase 7
(safety bundle), Phase 9 (backfill script), or Phase 10 (smart driver).
Default install is byte-identical to v1.0 (D-30 vanilla install
guarantee). Phase ships in one plan because all 7 tasks share the same
narrow blast radius (gameplay/ + one config field + one setup_hook call
site) and total context is well under the 50% budget.

Output: Working homebrew YAML loader, refactored `reactions.py`, CI gate
enforcing safe_load discipline, and a passing test suite that proves
extend-vs-replace semantics, 3-tier precedence, fail-soft behavior,
malicious-YAML rejection, casing normalization, and v1.0 backward
compatibility.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/08-yaml-riposte-eligibility/08-CONTEXT.md
@.planning/research/SUMMARY.md
@.planning/research/STACK.md
@.planning/research/ARCHITECTURE.md
@.planning/research/PITFALLS.md
@src/eldritch_dm/gameplay/reactions.py
@src/eldritch_dm/persistence/pc_classes_repo.py
@pyproject.toml

<interfaces>
<!-- Key contracts the executor must honor. Extracted directly from source. -->
<!-- Do NOT re-discover these via grep; use them as the implementation contract. -->

From src/eldritch_dm/persistence/pc_classes_repo.py (existing — to be refactored):
- `_WHITESPACE_RE = re.compile(r"\s+")`
- `def _normalize(value: str) -> str:`
   `return _WHITESPACE_RE.sub(" ", value.strip().lower())`
- This function is called from `PCClassInfo._norm` field_validator AND from `PCClassesRepo.upsert`.
- After Task 2, both call sites import `from eldritch_dm.gameplay.normalize import normalize` and `_normalize` is deleted from this file.

From src/eldritch_dm/gameplay/reactions.py (existing — to be refactored):
- `ELIGIBLE_CLASS_SUBCLASSES: frozenset[tuple[str, str]] = frozenset({("fighter", "battle master")})`
- Function signature today:
  `async def check_riposte_eligibility(*, channel_id, character_id, user_id, primary_weapon, current_round, pc_classes_repo, riposte_timers_repo) -> RiposteEligibility | None`
- Body line that consults the set: `if key not in ELIGIBLE_CLASS_SUBCLASSES:`
- Task 4 adds an `eligibility_set: frozenset[tuple[str, str]] | None = None` kwarg defaulted to None; when None, falls back to `ELIGIBLE_CLASS_SUBCLASSES`. ALL call sites in `bot/cogs/combat.py` (the MonsterDriver-on-miss path) pass the loader-resolved set.

From src/eldritch_dm/config.py (existing — to be extended):
- Pydantic-settings `Settings` class with env-prefixed fields.
- Add: `eligibility_yaml_path: Path | None = Field(default=None, alias="ELDRITCH_ELIGIBILITY_YAML")`

New module contracts to be written in Task 2 + 3:

```
# src/eldritch_dm/gameplay/normalize.py
_WHITESPACE_RE: re.Pattern[str]
def normalize(value: str) -> str: ...

# src/eldritch_dm/gameplay/eligibility_loader.py
DEFAULT_ELIGIBILITY: frozenset[tuple[str, str]]  # {("fighter", "battle master")}

class EligibilityFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1
    mode: Literal["extend", "replace"] = "extend"
    eligible: dict[str, list[str]]  # raw, pre-normalization

def load_eligibility(settings: Settings) -> frozenset[tuple[str, str]]: ...
# Returns the resolved set. NEVER raises. Logs structured warnings + falls
# back to DEFAULT_ELIGIBILITY on any failure.
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Promote pyyaml to core + atomic commit</name>
  <files>pyproject.toml</files>
  <action>
    Per D-37: edit `pyproject.toml` to (a) ADD `"pyyaml>=6.0.3,<7.0",` to the
    `[project.dependencies]` list (preserve alphabetical-ish order: after
    `"python-dotenv>=1.0,<2.0",` and before `"segno>=1.6,<2.0",`); and
    (b) REMOVE the existing `"pyyaml>=6.0,<7.0",` line from
    `[project.optional-dependencies.dev]`. Do not touch any other line.

    Sanity-check the diff:
    `git diff pyproject.toml` should show exactly +1 line in `[project.dependencies]`
    and -1 line in `[project.optional-dependencies.dev]`. No ruff config changes;
    no import-linter changes; no `[project.scripts]` changes (those belong to Phase 9).

    Then run `pip install -e .` to confirm the install resolves (pyyaml may
    already be present via the [dev] extra — `pip` will silently upgrade if
    needed). Commit with message:
    `chore(08-01): promote pyyaml 6.0.3 from [dev] to core (HOMEBREW-01)`
  </action>
  <verify>
    <automated>python -c "import yaml; assert yaml.__version__.startswith('6.0.3') or yaml.__version__ &gt; '6.0.2', yaml.__version__; print('pyyaml', yaml.__version__, 'OK')"</automated>
  </verify>
  <done>
    `pyyaml>=6.0.3,<7.0` appears in `[project.dependencies]`; the `pyyaml>=6.0,<7.0`
    line is removed from `[project.optional-dependencies.dev]`; `pip install -e .`
    resolves cleanly; commit landed.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Extract `_normalize` to gameplay/normalize.py (D-36)</name>
  <files>
    src/eldritch_dm/gameplay/normalize.py,
    src/eldritch_dm/persistence/pc_classes_repo.py,
    tests/gameplay/test_normalize.py
  </files>
  <behavior>
    - Test 1: `normalize("Battle Master") == "battle master"` (basic casing)
    - Test 2: `normalize("  Battle   Master  ") == "battle master"` (whitespace collapse + strip)
    - Test 3: `normalize("BATTLE MASTER") == "battle master"` (full uppercase)
    - Test 4: `normalize("") == ""` (empty string round-trip)
    - Test 5: `normalize("battle\tmaster") == "battle master"` (tab is whitespace)
    - Test 6: All four casing variants of `"Battle Master"` produce identical hashes (`hash(normalize(a)) == hash(normalize(b))` for all pairs) — covers PITFALLS YAML-6 / D-36 frozenset-key stability.
    - Test 7: After refactor, importing `_normalize` from `pc_classes_repo` raises ImportError (proves the symbol was actually moved, not duplicated).
    - Test 8: `PCClassInfo(class_name="Battle Master", subclass="Battle Master")` still produces `class_name == "battle master"` (proves the repo's field_validator now uses the shared helper).
  </behavior>
  <action>
    Per D-36 and ARCHITECTURE.md §2.3:

    1. Create `src/eldritch_dm/gameplay/normalize.py` with the exact contract:
       ```
       """Casing + whitespace normalizer shared by pc_classes_repo and eligibility_loader.

       Extracted from persistence.pc_classes_repo at Phase 08 per D-36 so the YAML loader
       and the repo agree on key shape — frozenset[tuple[str, str]] lookups need stable
       hashes regardless of YAML author casing or DDB ingest casing.
       """
       ```
       Define module-level `_WHITESPACE_RE = re.compile(r"\s+")` and
       `def normalize(value: str) -> str: return _WHITESPACE_RE.sub(" ", value.strip().lower())`.
       Pure stdlib (`re`), no upward imports — import-linter contracts unaffected.

    2. Refactor `src/eldritch_dm/persistence/pc_classes_repo.py`:
       - DELETE the inline `_WHITESPACE_RE` and `_normalize` definitions
       - ADD `from eldritch_dm.gameplay.normalize import normalize`
       - Replace every call to `_normalize(...)` with `normalize(...)` in:
         - `PCClassInfo._norm` field_validator body
         - `PCClassesRepo.upsert` (the `norm_class` / `norm_subclass` assignments)
       - Verify import-linter: `gameplay → persistence` is forbidden; this
         refactor is `persistence → gameplay`, which IS permitted (only the
         `gameplay → bot/ingest` direction is forbidden per pyproject.toml
         contract block "gameplay must not import bot or ingest"). Confirm by
         running `lint-imports` after the edit.

    3. Write `tests/gameplay/test_normalize.py` covering all 8 behaviors above
       in `<behavior>`. Use plain pytest functions (no class-based) to match
       the rest of `tests/gameplay/`.

    Atomic commit:
    `refactor(08-01): extract _normalize to gameplay/normalize.py (D-36, HOMEBREW-02)`
  </action>
  <verify>
    <automated>pytest tests/gameplay/test_normalize.py tests/persistence/ -x --tb=short 2>&amp;1 | tail -30 &amp;&amp; lint-imports 2>&amp;1 | tail -10</automated>
  </verify>
  <done>
    `gameplay/normalize.py` exists with `normalize()` exported; `pc_classes_repo.py`
    no longer defines `_normalize` (only imports + calls `normalize`); all 8 new
    normalize tests pass; existing `tests/persistence/` tests still green (proves
    no regression in repo behavior); `lint-imports` shows 7/7 contracts KEPT.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Implement eligibility_loader.py with 3-tier resolver + fail-soft</name>
  <files>
    src/eldritch_dm/gameplay/eligibility_loader.py,
    tests/fixtures/eligibility/valid_extend.yaml,
    tests/fixtures/eligibility/valid_replace.yaml,
    tests/fixtures/eligibility/malicious_python_object.yaml,
    tests/fixtures/eligibility/unknown_key.yaml,
    tests/fixtures/eligibility/bad_version.yaml,
    tests/fixtures/eligibility/swashbuckler_extend.yaml
  </files>
  <behavior>
    - Test 1 (precedence env wins): with `Settings(eligibility_yaml_path=fixtures/swashbuckler_extend.yaml)`, resolved set contains `("rogue", "swashbuckler")` AND `("fighter", "battle master")` (extend default).
    - Test 2 (precedence per-install wins): no env, per-install path returns set; in-repo default ignored.
    - Test 3 (precedence in-repo wins): no env, no per-install file present → in-repo `database/eligibility.yaml` returns `frozenset({("fighter", "battle master")})`.
    - Test 4 (no files at all): all 3 paths missing → DEFAULT_ELIGIBILITY returned, WARNING logged once with `reason="no_eligibility_yaml_found"`.
    - Test 5 (extend mode): `valid_extend.yaml` containing `{eligible: {fighter: [echo knight]}}` produces `frozenset({("fighter", "battle master"), ("fighter", "echo knight")})`.
    - Test 6 (replace mode): `valid_replace.yaml` containing `mode: replace, eligible: {rogue: [swashbuckler]}` produces `frozenset({("rogue", "swashbuckler")})` — Battle Master Fighter REMOVED.
    - Test 7 (malicious YAML T-08-01 / PITFALLS YAML-1): `malicious_python_object.yaml` containing `!!python/object/apply:os.system ['echo pwn']` raises ConstructorError from `safe_load` (NOT executed), `load_eligibility` catches it, logs `reason="yaml_parse_error"`, returns DEFAULT_ELIGIBILITY. Assert `os.system` was NOT called (use a sentinel file: if test directory contains an `os.system_was_called` file after load, fail).
    - Test 8 (unknown key, T-08-01 mitigation via pydantic): `unknown_key.yaml` with `{eligible: {fighter: [battle master]}, evil_field: 1}` → pydantic ValidationError caught, logs `reason="schema_validation_error"`, returns DEFAULT_ELIGIBILITY.
    - Test 9 (bad version): `bad_version.yaml` with `version: 2, eligible: {...}` → loader logs `reason="unsupported_schema_version"`, returns DEFAULT_ELIGIBILITY.
    - Test 10 (casing in YAML): `valid_extend.yaml` line `{Fighter: [BATTLE MASTER]}` (intentional inconsistent casing) → resolved set contains `("fighter", "battle master")` (normalized via `gameplay.normalize.normalize`).
    - Test 11 (resolved-set INFO log per PITFALLS YAML-4): on successful load, exactly one `structlog` INFO event with name `eligibility.resolved` and fields `source=<path>`, `mode=<extend|replace>`, `count=<int>`, `entries=[...sorted list of "class:subclass"...]`.
    - Test 12 (empty `eligible: {}` extend): returns DEFAULT_ELIGIBILITY (extend-with-nothing is a no-op, not an error).
    - Test 13 (empty `eligible: {}` replace): returns `frozenset()` (explicit "no one is eligible"; document this in INSTALL.md as a footgun in Task 5).
    - Test 14 (`load_eligibility` NEVER raises): wrap every test invocation in `try/except` that fails the test if any exception escapes — proves the fail-soft contract.
  </behavior>
  <action>
    Per D-29, D-30, D-32, D-33, D-34, D-40:

    1. Create `src/eldritch_dm/gameplay/eligibility_loader.py` with:
       - Module docstring referencing D-29..D-40 + PITFALLS YAML-1..6.
       - Imports: `from pathlib import Path`, `import yaml`, `from typing import Literal`,
         `from pydantic import BaseModel, ConfigDict, ValidationError`,
         `from eldritch_dm.gameplay.normalize import normalize`,
         `from eldritch_dm.logging import get_logger`,
         and TYPE_CHECKING import of `Settings` from `eldritch_dm.config` (avoid circular).
       - `log = get_logger(__name__)`
       - `DEFAULT_ELIGIBILITY: frozenset[tuple[str, str]] = frozenset({("fighter", "battle master")})`
         — comment line `# D-30: matches v1.0 reactions.ELIGIBLE_CLASS_SUBCLASSES exactly`.
       - Pydantic schema EXACTLY per the `<interfaces>` block above:
         `EligibilityFile` with `model_config = ConfigDict(extra="forbid")`,
         `version: int = 1`, `mode: Literal["extend", "replace"] = "extend"`,
         `eligible: dict[str, list[str]]`. Do NOT add `field_validator` here —
         normalization happens AFTER pydantic validates the raw shape, in the
         `_to_frozenset` helper, so the schema rejects shape errors first.
       - Private helper `_resolve_path(settings) -> Path | None` implementing D-29:
         (a) if `settings.eligibility_yaml_path` is not None and exists, return it;
         (b) elif `(Path.home() / ".eldritch" / "eligibility.yaml").exists()`, return it;
         (c) elif in-repo default `Path(__file__).parents[3] / "database" / "eligibility.yaml"`
         exists, return it; (d) else return None. Walk paths in order; FIRST hit wins.
         Compute the in-repo path RELATIVE to `__file__` so it works under
         `pip install -e .` AND under a system install where `__file__` lives in
         site-packages (in that case `parents[3]` will not contain `database/`,
         which falls through to None → DEFAULT_ELIGIBILITY).
       - Private helper `_to_frozenset(parsed: EligibilityFile) -> frozenset[tuple[str, str]]`:
         - Build `user_set = frozenset((normalize(cls), normalize(sub)) for cls, subs in parsed.eligible.items() for sub in subs)`.
         - If `parsed.mode == "extend"`: `return DEFAULT_ELIGIBILITY | user_set`.
         - If `parsed.mode == "replace"`: `return user_set` (may be empty per Test 13).
       - Public `def load_eligibility(settings) -> frozenset[tuple[str, str]]`:
         - Wrap the entire body in `try/except Exception`. ON ANY EXCEPTION:
           log `log.warning("eligibility.fallback", reason=str(e.__class__.__name__), error=str(e))` and return DEFAULT_ELIGIBILITY.
         - Inside try: path = `_resolve_path(settings)`; if None →
           `log.warning("eligibility.fallback", reason="no_eligibility_yaml_found")` + return DEFAULT_ELIGIBILITY.
         - `raw_text = path.read_text(encoding="utf-8")`
         - `raw = yaml.safe_load(raw_text)` — **ONLY `safe_load`, NEVER `load`** (T-08-01 / D-31).
           If `raw is None` (empty file), treat as parse error and fallback with `reason="empty_yaml_file"`.
         - `parsed = EligibilityFile.model_validate(raw)` — pydantic enforces `extra='forbid'`,
           raises `ValidationError` on unknown key (Test 8).
         - If `parsed.version != 1`: log `reason="unsupported_schema_version"`, return DEFAULT_ELIGIBILITY (Test 9).
         - `resolved = _to_frozenset(parsed)`
         - `log.info("eligibility.resolved", source=str(path), mode=parsed.mode, count=len(resolved), entries=sorted(f"{c}:{s}" for c, s in resolved))` (Test 11 / PITFALLS YAML-4 resolved-set log).
         - Return `resolved`.

    2. Create the 6 fixture YAML files under `tests/fixtures/eligibility/`:
       - `valid_extend.yaml`:
         ```
         version: 1
         mode: extend
         eligible:
           Fighter:     # intentional title case for Test 10
             - BATTLE MASTER   # intentional uppercase for Test 10
             - echo knight
         ```
       - `valid_replace.yaml`:
         ```
         version: 1
         mode: replace
         eligible:
           rogue:
             - swashbuckler
         ```
       - `swashbuckler_extend.yaml`:
         ```
         version: 1
         mode: extend
         eligible:
           rogue:
             - swashbuckler
         ```
       - `malicious_python_object.yaml`:
         ```
         version: 1
         mode: extend
         eligible: !!python/object/apply:os.system ['touch /tmp/eldritch_pwn_DO_NOT_RUN']
         ```
         (the payload is harmless `touch` rather than `rm -rf` per safe-test hygiene;
         the test asserts the sentinel file was NOT created)
       - `unknown_key.yaml`:
         ```
         version: 1
         mode: extend
         eligible:
           fighter:
             - battle master
         evil_field: 1   # `extra='forbid'` must reject this
         ```
       - `bad_version.yaml`:
         ```
         version: 2   # unsupported per D-40
         mode: extend
         eligible:
           fighter:
             - battle master
         ```

    3. Tests come next in Task 7 — this task ships the loader + fixtures only.

    Atomic commit:
    `feat(08-01): eligibility_loader.py — 3-tier YAML resolver + pydantic schema + fail-soft (HOMEBREW-01)`
  </action>
  <verify>
    <automated>python -c "from eldritch_dm.gameplay.eligibility_loader import load_eligibility, DEFAULT_ELIGIBILITY, EligibilityFile; print('exports OK:', DEFAULT_ELIGIBILITY)" &amp;&amp; ruff check src/eldritch_dm/gameplay/eligibility_loader.py</automated>
  </verify>
  <done>
    `eligibility_loader.py` imports cleanly, exports `load_eligibility`,
    `DEFAULT_ELIGIBILITY`, and `EligibilityFile`; uses `yaml.safe_load` ONLY;
    `ruff check` returns 0; all 6 fixture files exist under
    `tests/fixtures/eligibility/`; commit landed. Tests come in Task 7.
  </done>
</task>

<task type="auto">
  <name>Task 4: Refactor reactions.check_riposte_eligibility + ship in-repo default YAML</name>
  <files>
    src/eldritch_dm/gameplay/reactions.py,
    database/eligibility.yaml
  </files>
  <action>
    Per D-30 + D-38:

    1. Create `database/eligibility.yaml` with the v1.0 D-C set:
       ```
       # EldritchDM — Riposte Eligibility (in-repo default)
       #
       # This file ships the v1.0 RAW set: only Battle Master Fighter is eligible
       # for Riposte. Self-hosters can extend this set without editing code by
       # creating ~/.eldritch/eligibility.yaml or by setting
       # $ELDRITCH_ELIGIBILITY_YAML to point at a custom file. See INSTALL.md
       # for examples of `mode: extend` (default) and `mode: replace`.
       #
       # Restart the bot to apply changes — there is no hot-reload in v1.1.
       # Format reference (extend semantics):
       #
       #   version: 1
       #   mode: extend
       #   eligible:
       #     fighter:
       #       - battle master
       #       - echo knight   # homebrew example
       #     rogue:
       #       - swashbuckler  # homebrew example
       version: 1
       mode: extend
       eligible:
         fighter:
           - battle master
       ```
       The directory `database/` already exists (Phase 1 ships `database/schema.sql`).
       Verify: `ls database/` lists `eligibility.yaml`.

    2. Edit `src/eldritch_dm/gameplay/reactions.py`:

       (a) KEEP the existing `ELIGIBLE_CLASS_SUBCLASSES` module constant as-is
           (it becomes the in-module fallback used when no `eligibility_set`
           kwarg is passed — preserves v1.0 unit-test behavior for tests that
           construct `check_riposte_eligibility` directly without setup_hook).
           Update its preceding comment block to reference D-38:

           ```
           # ── Eligibility set (D-C — strict RAW; D-38 — in-module fallback) ────────
           #
           # Module-level fallback used when `check_riposte_eligibility` is called
           # without an injected `eligibility_set` (e.g. legacy unit tests). The
           # production path threads the loader-resolved frozenset from
           # `gameplay.eligibility_loader.load_eligibility` through
           # `bot/setup_hook` per D-38. See `database/eligibility.yaml` for the
           # in-repo default; CONFIGURATION/INSTALL docs explain the 3-tier
           # precedence override.
           ```
           Delete the now-stale `TODO(v2)` paragraph at lines 79-83 (the v2 work
           is THIS task) — replace it with a single-line reference comment
           pointing at `eligibility_loader.py`.

       (b) Change `check_riposte_eligibility` signature: insert a new
           keyword-only parameter `eligibility_set: frozenset[tuple[str, str]] | None = None`
           positioned AFTER `riposte_timers_repo` (last position so existing
           keyword-only call sites work unchanged).

       (c) In the function body, replace the single line
           `if key not in ELIGIBLE_CLASS_SUBCLASSES:`
           with:
           ```
           active_set = eligibility_set if eligibility_set is not None else ELIGIBLE_CLASS_SUBCLASSES
           if key not in active_set:
           ```
           Do NOT change any other logic. Do NOT change the docstring's "Rules"
           numbered list (the rules are unchanged — only the *source* of the
           eligibility set changed).

       (d) Add a paragraph to the function docstring under "Rules":
           ```
           Source of `active_set`:
             - When `eligibility_set` is provided (production path), it is
               resolved by `gameplay.eligibility_loader.load_eligibility()`
               called once at `bot.setup_hook` time. See HOMEBREW-01.
             - When `eligibility_set is None` (test fallback / pre-D-38
               callers), the module-level `ELIGIBLE_CLASS_SUBCLASSES` constant
               is used — preserves v1.0 behavior.
           ```

    3. Verify with a one-liner: existing Phase 5 Riposte tests construct
       `check_riposte_eligibility` WITHOUT `eligibility_set` and must still
       pass (fallback path). Confirm by running:
       `pytest tests/gameplay/test_reactions.py -x` (or whichever test file
       covers reactions — grep `tests/gameplay/` for `check_riposte_eligibility`
       if uncertain).

    Atomic commit:
    `refactor(08-01): inject eligibility_set into check_riposte_eligibility + ship database/eligibility.yaml (D-38, HOMEBREW-01)`
  </action>
  <verify>
    <automated>pytest tests/gameplay/ -k "riposte or eligibility" -x --tb=short 2>&amp;1 | tail -20 &amp;&amp; python -c "import yaml; data = yaml.safe_load(open('database/eligibility.yaml')); assert data == {'version': 1, 'mode': 'extend', 'eligible': {'fighter': ['battle master']}}, data; print('default YAML OK')"</automated>
  </verify>
  <done>
    `database/eligibility.yaml` parses to the v1.0 D-C set (D-30 byte-identical
    behavior verified); `reactions.check_riposte_eligibility` accepts the new
    `eligibility_set` kwarg with a module-constant fallback; all existing v1.0
    Riposte unit tests pass without modification (proves backward compat); the
    stale `TODO(v2)` comment is replaced by a forward reference to
    `eligibility_loader.py`.
  </done>
</task>

<task type="auto">
  <name>Task 5: Wire Settings + setup_hook + docs + .env.example</name>
  <files>
    src/eldritch_dm/config.py,
    src/eldritch_dm/bot/setup_hook.py,
    src/eldritch_dm/bot/cogs/combat.py,
    .env.example,
    docs/INSTALL.md
  </files>
  <action>
    Per D-29 + D-39 + ARCHITECTURE.md §2.5:

    1. Edit `src/eldritch_dm/config.py` — add a new field on the `Settings`
       pydantic-settings class:
       ```
       eligibility_yaml_path: Path | None = Field(
           default=None,
           alias="ELDRITCH_ELIGIBILITY_YAML",
           description="Override path for Riposte eligibility YAML (D-29 tier-1). "
                       "When unset, loader walks per-install (~/.eldritch/eligibility.yaml) "
                       "then in-repo default (database/eligibility.yaml).",
       )
       ```
       If `Path` is not already imported at the top of `config.py`, add
       `from pathlib import Path`. If `Field` is not imported, add it to the
       existing pydantic import. Do not change any other Settings field.

    2. Edit `src/eldritch_dm/bot/setup_hook.py`:
       - Add `from eldritch_dm.gameplay.eligibility_loader import load_eligibility`
         at the top with the other gameplay imports.
       - In `setup_hook` body, at a point AFTER `Settings` is loaded but BEFORE
         any cog registration that wires reaction callbacks (find by grepping
         `setup_hook.py` for the existing call site that constructs the
         RiposteCog / passes things to combat cog), add:
         ```
         eligibility_set = load_eligibility(settings)
         log.info("eligibility_loaded", count=len(eligibility_set))
         bot.eligibility_set = eligibility_set   # type: ignore[attr-defined]
         ```
         The `bot.eligibility_set` attribute pattern matches the existing
         `bot.sanitizer_audit_callback` pattern (per Phase 7 Architecture §4.2).
         If `bot` is typed as `EldritchBot`, add `eligibility_set: frozenset[tuple[str, str]] = frozenset()`
         as a class attribute on `EldritchBot` (in `src/eldritch_dm/bot/bot.py`)
         OR — to avoid touching `bot.py` — use `setattr(bot, "eligibility_set", eligibility_set)`
         and `# noqa` the type-ignore. Prefer the attribute-on-class approach
         if `bot.py` already has similar attributes (grep to confirm).

    3. Edit `src/eldritch_dm/bot/cogs/combat.py` — find the single call site
       that invokes `check_riposte_eligibility(...)` (it's in the MonsterDriver
       on-miss path per Architecture §2.4). Thread the resolved set through:
       ```
       eligibility = await check_riposte_eligibility(
           channel_id=...,
           ...,                               # all existing kwargs unchanged
           eligibility_set=self.bot.eligibility_set,   # NEW kwarg per D-38
       )
       ```
       If `self.bot.eligibility_set` is not accessible (cog construction order),
       fall back to `getattr(self.bot, "eligibility_set", None)` — `None` triggers
       the module-constant fallback in `reactions.py` (graceful degradation).

    4. Edit `.env.example` — add at the bottom under a new comment block:
       ```
       # ── Homebrew Riposte Eligibility (Phase 8 / HOMEBREW-01) ──────────────────
       # Override path for Riposte eligibility YAML. When unset, the bot loads
       # ~/.eldritch/eligibility.yaml if present, otherwise database/eligibility.yaml
       # (in-repo default — ships v1.0 Battle Master Fighter only).
       # See docs/INSTALL.md for `mode: extend` (default) vs `mode: replace` examples.
       # Restart the bot to apply changes — no hot-reload in v1.1.
       # ELDRITCH_ELIGIBILITY_YAML=/etc/eldritchdm/eligibility.yaml
       ```

    5. Edit `docs/INSTALL.md` (create the file if it does not exist;
       otherwise append a new top-level `## Homebrew Riposte Eligibility`
       section). Content:

       ```
       ## Homebrew Riposte Eligibility

       By default, only Battle Master Fighters can Riposte (D&D 5e RAW). To
       extend the eligibility set for homebrew classes/subclasses, create a
       YAML file at one of these locations (closest wins):

       1. `$ELDRITCH_ELIGIBILITY_YAML` (env var path)
       2. `~/.eldritch/eligibility.yaml` (per-install)
       3. `database/eligibility.yaml` (in-repo default — DO NOT edit if you
          want vanilla v1.0 behavior; create a file at one of the above
          tiers instead)

       ### Extend (recommended default)

       Adds your subclasses to the RAW set — Battle Master Fighter remains
       eligible:

       ```yaml
       version: 1
       mode: extend
       eligible:
         fighter:
           - echo knight     # homebrew subclass
         rogue:
           - swashbuckler    # third-party content
       ```

       Result: Battle Master Fighter, Echo Knight Fighter, AND Swashbuckler
       Rogue can all Riposte.

       ### Replace (advanced — wipes RAW defaults)

       Fully overrides the RAW set. Battle Master Fighter will NO LONGER be
       eligible unless you list it explicitly:

       ```yaml
       version: 1
       mode: replace
       eligible:
         fighter:
           - battle master   # MUST include if you want to keep v1.0 default
           - echo knight
       ```

       ### Failure semantics

       If the YAML file is missing, malformed, or fails schema validation,
       EldritchDM logs a `structlog.warning("eligibility.fallback", reason=...)`
       entry and falls back to the v1.0 default (Battle Master Fighter only).
       The bot will NOT crash — your players can still play. Check your JSON
       logs (`grep eligibility.fallback`) to see what went wrong.

       ### Caveat — RAW vs RAI

       This file extends what THE BOT OFFERS as a Riposte reaction. It does
       NOT change what 5e RAW grants. Adding `{ranger: [hunter]}` will let
       Hunter Rangers click the Riposte button at your table, but Hunter
       Rangers do not have the Riposte maneuver in core rules. You are
       responsible for confirming RAW alignment for any homebrew you add.

       ### Restart-to-apply

       Changes are read once at bot startup. Restart the bot
       (`launchctl unload && launchctl load …` or `systemctl --user restart eldritch-dm`)
       to apply edits. Hot-reload is a v1.2 candidate.
       ```

    Atomic commit:
    `feat(08-01): wire eligibility loader into setup_hook + Settings + .env.example + INSTALL.md (HOMEBREW-01, HOMEBREW-02)`
  </action>
  <verify>
    <automated>python -c "from eldritch_dm.config import Settings; s = Settings(); assert hasattr(s, 'eligibility_yaml_path'), 'Settings missing eligibility_yaml_path'; print('Settings field OK:', s.eligibility_yaml_path)"</automated>
  </verify>
  <done>
    `Settings.eligibility_yaml_path` field exists and reads from
    `ELDRITCH_ELIGIBILITY_YAML`; `setup_hook` calls `load_eligibility(settings)`
    once before cog wiring and stores the frozenset on `bot.eligibility_set`;
    `combat.py` threads `eligibility_set=self.bot.eligibility_set` into the
    single `check_riposte_eligibility` call site; `.env.example` documents
    the env var; `docs/INSTALL.md` has the "Homebrew Riposte Eligibility"
    section with extend + replace + failure-semantics + RAI caveat +
    restart-to-apply subsections.
  </done>
</task>

<task type="auto">
  <name>Task 6: CI grep gate — safe_load only (T-08-01 / D-31)</name>
  <files>
    scripts/ci/check_safe_yaml.sh
  </files>
  <action>
    Per D-31 + PITFALLS YAML-1 + T-08-01:

    1. Create `scripts/ci/` directory if it does not exist.

    2. Write `scripts/ci/check_safe_yaml.sh` as an executable bash script:
       ```bash
       #!/usr/bin/env bash
       # EldritchDM — CI gate: enforce yaml.safe_load only.
       #
       # PITFALLS.md YAML-1 + T-08-01: yaml.load() without a SafeLoader allows
       # arbitrary Python execution via `!!python/object/apply:...`. This gate
       # fails the build if ANY src/ file calls yaml.load(...) without the
       # `safe_` prefix.
       #
       # Exit codes:
       #   0  no unsafe yaml.load calls found (good)
       #   1  unsafe yaml.load call detected (fail the build)
       #   2  ripgrep / grep tooling problem (treat as build failure)
       #
       # Run locally: bash scripts/ci/check_safe_yaml.sh
       set -euo pipefail

       cd "$(dirname "$0")/../.."

       # Match `yaml.load(` but NOT `yaml.safe_load(` — the negative lookbehind
       # in grep -P is the simplest portable expression. We strip comments first
       # (planner-gate hygiene from references/planner-source-audit.md).
       HITS=$(git grep -nE 'yaml\.load\(' -- 'src/' \
              | grep -v 'safe_load' \
              | grep -v '^[^:]*:[0-9]*:[[:space:]]*#' \
              || true)

       if [ -n "$HITS" ]; then
           echo "❌ UNSAFE yaml.load() detected — use yaml.safe_load() instead" >&2
           echo "   (PITFALLS.md YAML-1 / T-08-01: arbitrary code execution risk)" >&2
           echo >&2
           echo "$HITS" >&2
           exit 1
       fi

       echo "✅ safe_load-only check passed"
       ```

    3. `chmod +x scripts/ci/check_safe_yaml.sh`

    4. Verify the gate works in BOTH directions:
       - **Negative test (must PASS):** Run against current `src/` — should
         exit 0 with `✅ safe_load-only check passed`.
       - **Positive test (must FAIL):** Temporarily create a throwaway file
         `src/_test_unsafe_yaml.py` with the single line `# yaml.load(stream)`
         (NOT a real call — just text). Actually, the comment filter strips
         it. Use a real (non-comment) line: `_ = "yaml.load(x)"`. Re-run the
         gate. It MUST exit 1. Then `rm src/_test_unsafe_yaml.py`. Re-run.
         MUST exit 0 again.

    5. **Optional but recommended** — if `.pre-commit-config.yaml` exists at
       the repo root, append a new local hook entry:
       ```yaml
       - repo: local
         hooks:
           - id: yaml-safe-load-only
             name: enforce yaml.safe_load only in src/
             entry: bash scripts/ci/check_safe_yaml.sh
             language: system
             pass_filenames: false
             always_run: true
       ```
       (If `.pre-commit-config.yaml` does not exist, skip — Phase 8 does not
       own pre-commit setup.)

    Atomic commit:
    `chore(08-01): CI grep gate enforcing yaml.safe_load only (T-08-01, D-31, PITFALLS YAML-1)`
  </action>
  <verify>
    <automated>bash scripts/ci/check_safe_yaml.sh &amp;&amp; echo '# yaml.load(unsafe)' &gt; /tmp/test_unsafe.txt &amp;&amp; cp /tmp/test_unsafe.txt src/_TEST_UNSAFE.py &amp;&amp; ! bash scripts/ci/check_safe_yaml.sh &amp;&amp; rm src/_TEST_UNSAFE.py &amp;&amp; bash scripts/ci/check_safe_yaml.sh &amp;&amp; echo 'gate bidirectional OK'</automated>
  </verify>
  <done>
    `scripts/ci/check_safe_yaml.sh` exists, is executable, exits 0 against
    current `src/`, and exits 1 against a deliberately-introduced unsafe
    `yaml.load(` (verified via temp file + cleanup); comment-stripping logic
    works (planner-source-audit hygiene); committed.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 7: Test suite for eligibility_loader + closure</name>
  <files>
    tests/gameplay/test_eligibility_loader.py
  </files>
  <behavior>
    All 14 tests defined in Task 3's `<behavior>` block. Repeat enumerated
    for the executor (must produce one pytest test function per item):

    - test_default_eligibility_constant_matches_v1_0
    - test_env_path_overrides_per_install_and_in_repo (precedence tier-1)
    - test_per_install_path_overrides_in_repo (precedence tier-2; mock
      `Path.home()` via monkeypatch to a tmp_path containing `.eldritch/eligibility.yaml`)
    - test_in_repo_default_used_when_no_overrides (precedence tier-3; assert
      the loader walks to `database/eligibility.yaml` relative to the source tree)
    - test_no_files_anywhere_returns_default_with_warning (fail-soft when all
      3 tiers miss)
    - test_extend_mode_unions_with_default
    - test_replace_mode_wipes_default
    - test_malicious_python_object_yaml_does_not_execute (T-08-01 / YAML-1)
    - test_unknown_yaml_key_rejected_by_pydantic (`extra='forbid'`)
    - test_unsupported_version_falls_back (version: 2 rejected with warning)
    - test_casing_normalized_via_shared_helper (mixed-case YAML keys produce
      lowercased frozenset entries)
    - test_resolved_set_logged_at_info_level (per PITFALLS YAML-4)
    - test_empty_eligible_dict_in_extend_returns_default
    - test_empty_eligible_dict_in_replace_returns_empty_frozenset (footgun
      documented in INSTALL.md)
    - test_load_eligibility_never_raises (parametrized over all bad fixture
      files; each must return DEFAULT_ELIGIBILITY without raising)
  </behavior>
  <action>
    Per Task 3 behavior list + cold-start E2E discipline (Phase 6 lesson):

    1. Create `tests/gameplay/test_eligibility_loader.py`. Use plain pytest
       functions, `pytest.fixture` for the tmp YAML setup, `caplog` /
       `structlog.testing.capture_logs` for log assertions, `monkeypatch`
       for `Path.home()` overrides.

    2. Fixture pattern:
       ```
       @pytest.fixture
       def settings_with_env_path(fixture_path):
           from eldritch_dm.config import Settings
           return Settings(eligibility_yaml_path=fixture_path)
       ```

    3. For the precedence tests, use this layering pattern:
       - tier-1 only: pass `eligibility_yaml_path=tmp_yaml`
       - tier-2 only: monkeypatch `Path.home()` to a tmp_path, create
         `.eldritch/eligibility.yaml` inside it
       - tier-3 only: clear env, do not touch home; rely on the real
         `database/eligibility.yaml` shipped by Task 4 (or skip the test
         with a `pytest.mark.skipif(not Path('database/eligibility.yaml').exists())`)

    4. For T-08-01 / malicious YAML test, the assertion shape is:
       ```
       def test_malicious_python_object_yaml_does_not_execute(monkeypatch, tmp_path):
           sentinel = tmp_path / "eldritch_pwn_DO_NOT_RUN"
           # The fixture file contains: !!python/object/apply:os.system ['touch ...']
           # safe_load must reject this BEFORE the os.system call could fire.
           from eldritch_dm.config import Settings
           from eldritch_dm.gameplay.eligibility_loader import (
               load_eligibility, DEFAULT_ELIGIBILITY,
           )
           fixture = Path("tests/fixtures/eligibility/malicious_python_object.yaml")
           settings = Settings(eligibility_yaml_path=fixture)
           result = load_eligibility(settings)
           assert result == DEFAULT_ELIGIBILITY, "fail-soft should fall back to default"
           assert not sentinel.exists(), "safe_load must NOT have executed the payload"
       ```
       The fixture payload uses `touch /tmp/eldritch_pwn_DO_NOT_RUN` — even if
       safe_load somehow misbehaved, the side effect is benign. The test asserts
       the sentinel was NOT created, which proves the payload did not execute.

    5. For the "never raises" parametrized test:
       ```
       @pytest.mark.parametrize("fixture_name", [
           "malicious_python_object.yaml",
           "unknown_key.yaml",
           "bad_version.yaml",
       ])
       def test_load_eligibility_never_raises(fixture_name):
           from eldritch_dm.config import Settings
           from eldritch_dm.gameplay.eligibility_loader import (
               load_eligibility, DEFAULT_ELIGIBILITY,
           )
           fixture = Path("tests/fixtures/eligibility") / fixture_name
           settings = Settings(eligibility_yaml_path=fixture)
           # MUST NOT raise — if it does, pytest fails the test by default
           result = load_eligibility(settings)
           assert result == DEFAULT_ELIGIBILITY
       ```

    6. Run the full Phase 5 Riposte test suite to confirm zero regressions:
       `pytest tests/gameplay/test_reactions.py tests/gameplay/test_riposte_*.py -x`.
       Any failure here means Task 4's refactor broke v1.0 behavior — fix
       BEFORE landing this task's commit.

    7. Run the full default test suite to confirm the 864-passing baseline
       still holds (Phase 6 cold-start lesson — broader smoke is cheap and
       catches integration gaps):
       `pytest --tb=short 2>&1 | tail -10`. Expected: 864 + new tests passing.

    8. Tick HOMEBREW-01 and HOMEBREW-02 in `.planning/REQUIREMENTS.md`
       (change `- [ ]` to `- [x]` on the two requirement lines). Update the
       Traceability table at the bottom: change `TBD` to `8-01-PLAN-yaml-eligibility`
       for both rows.

    9. Update `.planning/ROADMAP.md` Progress table: Phase 8 row from
       `0/1` `Not started` to `1/1` `Complete` with today's date in the
       Completed column. Tick the `[ ] Plan 01` line in the Phase 8 details
       section.

    10. Update `.planning/STATE.md`: append a new entry under `## Decisions`
        listing D-29 through D-40 (one line each, terse). Append to
        `## Recent History`: a dated bullet `2026-05-23: Phase 8 Plan 01
        COMPLETE — eligibility loader, normalize extract, CI safe_load gate,
        fail-soft tests; HOMEBREW-01+02 ticked; N net new tests; zero
        regressions.`

    11. Create `.planning/phases/08-yaml-riposte-eligibility/VERIFICATION.md`
        with the per-phase checklist (per CC-2 hygiene gate) covering:
        ruff 0 in new files, lint-imports 7/7 kept, all new tests green,
        all Phase 5 Riposte tests green, safe_load gate exits 0, default
        YAML parses to v1.0 set, INSTALL.md has both examples, .env.example
        documents the env var, cold-start E2E covered (the parametrized
        never-raises test exercises the full bot.setup_hook → load_eligibility
        → reactions.check_riposte_eligibility path without mocks).

    Atomic commit:
    `test(08-01): eligibility_loader test suite + Phase 8 closure (HOMEBREW-01, HOMEBREW-02)`
  </action>
  <verify>
    <automated>pytest tests/gameplay/test_eligibility_loader.py tests/gameplay/test_normalize.py tests/gameplay/test_reactions.py -x --tb=short 2>&amp;1 | tail -20 &amp;&amp; bash scripts/ci/check_safe_yaml.sh &amp;&amp; lint-imports 2>&amp;1 | tail -10 &amp;&amp; ruff check src/eldritch_dm/gameplay/normalize.py src/eldritch_dm/gameplay/eligibility_loader.py src/eldritch_dm/gameplay/reactions.py src/eldritch_dm/persistence/pc_classes_repo.py</automated>
  </verify>
  <done>
    All 15 tests in `test_eligibility_loader.py` pass; all 8 tests in
    `test_normalize.py` pass; full Phase 5 Riposte test file still green
    (zero v1.0 regression); `scripts/ci/check_safe_yaml.sh` exits 0;
    `lint-imports` shows 7/7 KEPT; `ruff check` returns 0 on all touched
    `src/` files; REQUIREMENTS.md HOMEBREW-01 + HOMEBREW-02 ticked; ROADMAP
    Phase 8 marked Complete; STATE.md updated with D-29..D-40 entries and
    Recent History line; VERIFICATION.md committed.
  </done>
</task>

</tasks>

<threat_model>

## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| filesystem -> Python process | User-controlled YAML files (env-path, ~/.eldritch/, in-repo) read at startup. Untrusted input crosses here. |

(No network boundaries are crossed in this phase. The loader is pure data resolution from disk.)

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-08-01 | Tampering / Elevation | `gameplay/eligibility_loader.py` YAML parser | mitigate | `yaml.safe_load` ONLY (D-31); CI grep gate via `scripts/ci/check_safe_yaml.sh` fails build on `yaml.load(` (without `safe`) anywhere in `src/`; pydantic v2 `model_config = ConfigDict(extra='forbid')` rejects unknown keys (D-32); Task 7 ships `tests/fixtures/eligibility/malicious_python_object.yaml` with `!!python/object/apply:os.system` payload + sentinel-file assertion. |
| T-08-02 | Denial of Service | `gameplay/eligibility_loader.py` startup load | mitigate | Fail-soft to `DEFAULT_ELIGIBILITY` (D-33); the try/except wrapper in `load_eligibility` makes every failure path return the v1.0 frozenset + log `structlog.warning("eligibility.fallback", reason=...)`. Bot continues startup. |
| T-08-03 | Tampering | `database/eligibility.yaml` (in-repo default) | accept | File is committed to repo; tampering requires repo write access (threat already in project's accepted threat model). |
| T-08-04 | Information Disclosure | YAML file on disk | accept | Contents are class/subclass lookup data only — no secrets, no PII. |
| T-08-05 | Repudiation | Resolved eligibility set | mitigate | `log.info("eligibility.resolved", source=<path>, mode=<extend|replace>, count=N, entries=[...])` at INFO emitted on every successful load per PITFALLS YAML-4. Operator can grep JSON logs for what was loaded. |
| T-08-SC | Tampering (Supply Chain) | `pyyaml>=6.0.3` promotion | mitigate | PyYAML is `[OFFICIAL]` — canonical Python YAML lib (`yaml/pyyaml` on GitHub, >5M weekly DL). Already in `[dev]` since Phase 1 (no first-touch trust gate triggered). Pin floor at 6.0.3 (current stable per STACK §2). No blocking-human checkpoint required; legitimacy is established. |

</threat_model>

<verification>

## Phase-Level Verification

After all 7 tasks complete, the following MUST all be true:

1. **Vanilla install byte-identical to v1.0 (D-30):** A fresh `git clone && pip install -e .` with NO env vars and NO `~/.eldritch/eligibility.yaml` results in Battle Master Fighter being the only Riposte-eligible subclass. Verified by:
   `python -c "from eldritch_dm.gameplay.eligibility_loader import load_eligibility; from eldritch_dm.config import Settings; assert load_eligibility(Settings()) == frozenset({('fighter', 'battle master')}); print('vanilla = v1.0 OK')"`

2. **Extend semantics work end-to-end:** `ELDRITCH_ELIGIBILITY_YAML=tests/fixtures/eligibility/swashbuckler_extend.yaml python -c "from eldritch_dm.gameplay.eligibility_loader import load_eligibility; from eldritch_dm.config import Settings; r = load_eligibility(Settings()); assert ('fighter', 'battle master') in r and ('rogue', 'swashbuckler') in r; print('extend OK:', sorted(r))"`

3. **Replace semantics work end-to-end:** Same shape against `valid_replace.yaml`; asserts Battle Master removed and Swashbuckler present.

4. **Malicious YAML cannot execute:** `tests/gameplay/test_eligibility_loader.py::test_malicious_python_object_yaml_does_not_execute` passes; sentinel file `/tmp/eldritch_pwn_DO_NOT_RUN` was NEVER created.

5. **CI safe_load gate:** `bash scripts/ci/check_safe_yaml.sh` exits 0 against current `src/`; exits 1 against a planted `yaml.load(` line.

6. **Casing parity:** Mixed-case YAML keys (`Fighter`, `BATTLE MASTER`) hash equivalently to lowercase `fighter`, `battle master` in the resolved frozenset. Test: `test_casing_normalized_via_shared_helper`.

7. **Zero v1.0 regression:** All pre-existing Phase 5 Riposte tests still green. Test: `pytest tests/gameplay/test_reactions.py tests/gameplay/test_riposte_*.py -x` returns 0.

8. **Import-linter intact:** `lint-imports` reports 7/7 contracts KEPT. (No new contract block added; `persistence -> gameplay` import for the normalize helper is permitted per existing contracts.)

9. **Ruff clean:** `ruff check src/eldritch_dm/gameplay/normalize.py src/eldritch_dm/gameplay/eligibility_loader.py src/eldritch_dm/gameplay/reactions.py src/eldritch_dm/persistence/pc_classes_repo.py src/eldritch_dm/config.py src/eldritch_dm/bot/setup_hook.py src/eldritch_dm/bot/cogs/combat.py` returns 0.

10. **Documentation in place:** `docs/INSTALL.md` contains a `## Homebrew Riposte Eligibility` heading with `extend` example, `replace` example, failure-semantics paragraph, RAI caveat, and restart-to-apply note. `.env.example` contains an `ELDRITCH_ELIGIBILITY_YAML` commented-out line with explanation.

11. **REQUIREMENTS ticked:** HOMEBREW-01 and HOMEBREW-02 both flipped to `- [x]` in `.planning/REQUIREMENTS.md`; Traceability table updated.

12. **ROADMAP + STATE updated:** Phase 8 row marked Complete with today's date; D-29..D-40 logged in STATE.md Decisions; Recent History line appended.

13. **VERIFICATION.md committed** per CC-2 hygiene gate.

</verification>

<success_criteria>

Phase 8 is complete when (verbatim mapping to ROADMAP §Phase 8):

1. [ ] `database/eligibility.yaml` exists, parses cleanly via `yaml.safe_load`, and contains `{version: 1, mode: extend, eligible: {fighter: [battle master]}}` — bit-for-bit equivalent to the v1.0 frozenset.

2. [ ] `src/eldritch_dm/gameplay/eligibility_loader.py` exists, exports `load_eligibility`, `EligibilityFile`, and `DEFAULT_ELIGIBILITY`; resolves the 3-tier precedence (env > per-install > in-repo); validates via pydantic v2 `extra='forbid'`; uses `yaml.safe_load` only; fails soft to `DEFAULT_ELIGIBILITY` with a `structlog.warning("eligibility.fallback", reason=...)` on missing file, parse error, schema validation error, or unsupported version.

3. [ ] `scripts/ci/check_safe_yaml.sh` exists, is executable, exits 0 against current `src/`, and exits 1 against any `yaml.load(` (without `safe`) introduced by a future PR.

4. [ ] Extend-vs-replace behavior tested both directions; `docs/INSTALL.md` contains both YAML examples plus a clearly-labeled failure-semantics paragraph.

5. [ ] `src/eldritch_dm/gameplay/reactions.py::ELIGIBLE_CLASS_SUBCLASSES` is no longer the production source of truth; production path threads `bot.eligibility_set` (loader-resolved) through `check_riposte_eligibility`'s new `eligibility_set` kwarg; the module constant is retained as a fail-soft fallback for unit tests. All pre-existing v1.0 Riposte tests still pass.

6. [ ] HOMEBREW-01 and HOMEBREW-02 ticked `[x]` in `.planning/REQUIREMENTS.md`.

7. [ ] `lint-imports` shows 7/7 contracts KEPT; `ruff check` clean on all touched files.

</success_criteria>

<output>
On completion, write `.planning/phases/08-yaml-riposte-eligibility/08-01-SUMMARY.md`
following the standard SUMMARY template:

- Tasks completed (7), files touched (20), tests added (target: ~23 new tests
  across `test_normalize.py` + `test_eligibility_loader.py`), lines added/removed
- Atomic commits landed (7 expected, one per task), git log oneline
- Decisions D-29..D-40 with one-line rationale each
- Open questions / deferred items (YAML hot-reload + `homebrew: true` flag + cross-pollination warning all deferred to v1.2 per CONTEXT §"Deferred")
- VERIFICATION.md cross-reference + cold-start E2E coverage statement (per Phase 6 lesson / CC-2 gate)
- Net dependency change: +1 promoted dep (pyyaml [dev] -> core); 0 new top-level pip packages
- Test baseline delta: 864 -> 864 + new tests, all green
</output>
