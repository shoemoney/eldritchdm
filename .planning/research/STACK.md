# Technology Stack — v1.1 Polish

**Project:** EldritchDM
**Milestone:** v1.1 Polish (subsequent — v1.0 shipped 2026-05-23)
**Researched:** 2026-05-23
**Scope:** ONLY new dependencies / config changes needed for v1.1.
v1.0 pinned stack (discord.py 2.7.1, httpx, aiosqlite, pydantic v2, tenacity,
structlog, PyMuPDF, pypdf, ocrmac/easyocr, openai, segno, pyyaml [dev],
ruff [dev], import-linter [dev]) is unchanged and out of scope here.
**Confidence:** HIGH (4/4 candidate libs verified against PyPI + Context7
on 2026-05-23).

## TL;DR — Minimal Changes

| Deliverable | Stack change | Severity |
|---|---|---|
| SAN-01 close, OPS-02 close, `__main__` token-fix | **None.** Pure refactor on existing modules. | 0 deps |
| Ruff cleanup (TD-2) | **No new deps.** Bump `ruff>=0.6,<1.0` floor to `>=0.15,<1.0`; do NOT add new rule families this milestone — defer `SIM`/`PERF` to v1.2. | config-only |
| Smart MonsterDriver | **No new deps.** Reuse existing `openai` AsyncOpenAI client to call dm20's `dm20__claudmaster_step` MCP tool (or `dm20__party_thinking`) for tactical-oracle calls. Build prompts with f-strings; do NOT introduce Jinja2. | 0 deps |
| YAML Riposte eligibility | **Promote `pyyaml` from `[dev]` to runtime.** Bump pin to `pyyaml>=6.0.3,<7.0`. Load via `yaml.safe_load`, validate with new pydantic v2 model. Do NOT add `ruamel.yaml` or `pydantic-yaml`. | 1 promoted dep |
| `pc_classes` ingest-backfill script | **No new deps.** Ship as `eldritch-dm-backfill-pc-classes` console-script in `pyproject.toml [project.scripts]`, mirroring the existing `eldritch-dm` entry. Use stdlib `argparse` (consistent with `run.py`); do NOT add `click` or `typer`. | 0 deps |

**Net change:** 1 dependency promoted from `[dev]` → core (`pyyaml`).
1 dev-tool floor bumped (`ruff`). One new console-script entry. Zero new
top-level pip packages.

## Recommended Pin Changes

```toml
# pyproject.toml — diff vs v1.0

[project.dependencies]
# … (existing 12 deps unchanged) …
+ "pyyaml>=6.0.3,<7.0",            # promoted from [dev] for Riposte YAML config

[project.optional-dependencies.dev]
- "ruff>=0.6,<1.0",
+ "ruff>=0.15,<1.0",               # 0.15.14 is current (2026-05-21)
- "pyyaml>=6.0,<7.0",              # remove — now a core dep
  # … other dev deps unchanged …

[project.scripts]
  eldritch-dm = "eldritch_dm.bot.__main__:main"
+ eldritch-dm-backfill-pc-classes = "eldritch_dm.scripts.backfill_pc_classes:main"
```

## Decision Audit (Per Deliverable)

### 1. Smart MonsterDriver — Tactical Oracle via dm20 (Claudmaster)

**Decision: Reuse existing `openai` AsyncOpenAI client + plain f-string prompts.
No new libraries.**

**dm20 tool surface (verified against memory):** dm20 exposes ~97 MCP tools.
Two are relevant here:

| Tool | What it does | Fit for "who should this monster attack?" |
|---|---|---|
| `dm20__claudmaster_step` | Advances the autonomous-DM loop one tick. Heavyweight — owns narration, initiative, the whole turn. | **Wrong shape.** Steals control from our turn-gating + EmbedCoalescer. |
| `dm20__party_thinking` | Returns the model's free-text reasoning about current party state. Read-only oracle. | **Better fit, but still indirect** — it answers "what's the party thinking", not "what should this monster target". |
| (none) | Direct "best target for this monster" tool | **Not exposed.** Confirmed against PROJECT.md tool inventory. |

**Recommended pattern: structured oracle call via existing AsyncOpenAI client
to the `ShoeGPT` model at oMLX `:8765/v1` — NOT via dm20.** The bot already
talks to oMLX for character-sheet ingest (`openai>=1.55,<2.0` is pinned). We
add a second call site: `gameplay/monster_tactics.py::pick_target(state) →
character_id`. The LLM is the oracle; the choice is then handed back to
`mcp_tools.combat_action(attacker=monster, target=chosen)` so dm20 still owns
the math (integrity rule preserved — D-B's "v2 may route via Claudmaster" was
optimistic phrasing; the LLM-as-oracle path keeps dm20 the rules-engine of
record).

**Prompting: f-strings, NOT Jinja2.** The prompt is one function, ≤30 lines,
takes ≤5 parameters (monster name, HP, party list, current round, recent
events). Jinja2 adds 700KB + a template-loading lifecycle for zero gain at
this scale. The existing v1.0 codebase has no template engine; introducing
one for one call site is overhead. f-strings + a `MonsterTacticPrompt`
pydantic v2 model (frozen, like every other model in the codebase) for the
*response* shape covers both directions.

**Response validation: pydantic v2 (already pinned `>=2.8,<3.0`).** Define
`MonsterTacticChoice(BaseModel)` with `target_character_id: str` and
optional `rationale: str`. Pass `response_format={"type": "json_object"}` to
`AsyncOpenAI.chat.completions.create` (oMLX supports it — Phase 1 verified).
Parse + validate with `MonsterTacticChoice.model_validate_json(resp)`.

**Fallback chain (resilience — TD-2-adjacent):** If the oracle call fails,
times out, or returns an unparseable response, fall back to the existing
`random.choice(targets)` from v1.0. This makes the smart driver a non-fatal
enhancement: dm20 outage or oMLX hiccup degrades gracefully to v1.0 behavior.
Wire via `tenacity` retry (already pinned `>=8.5,<10.0`) with
`stop_after_attempt(2) + retry_if_exception_type((httpx.HTTPError, ValidationError))`.

**Pattern reference:** This is the standard "LLM as a function" / "structured
output oracle" pattern (`pydantic-ai`/`instructor` formalize it). The v1.0
STACK.md explicitly rejected `pydantic-ai`/`instructor` ("couples you to a
framework's prompt patterns") — that decision still holds for v1.1. Direct
`openai` client + `pydantic v2` validation is the v1.0-consistent pattern.

**Confidence:** HIGH. Reuses 100% of v1.0 stack. Matches the integrity rule.
Phase scope is contained (one new module + one prompt + one pydantic model +
fallback wiring).

### 2. YAML-Configurable Riposte Eligibility

**Decision: Promote `pyyaml>=6.0.3,<7.0` from `[dev]` to core. Load with
`yaml.safe_load`. Validate with a new pydantic v2 model.**

**Why not `tomllib`** (zero new deps — built into Python 3.11): TOML's nested-
array-of-tables syntax for the eligibility list (`[[eligibility]]` with
`class`/`subclass` keys) is verbose for what is fundamentally a flat list of
(class, subclass) pairs. YAML's `- [fighter, battle master]` is the right
ergonomic shape for the *user* writing the file — and the user here is the
homebrew DM, not a programmer. YAML wins on author UX.

**Why not `ruamel.yaml>=0.19.1`:** Round-trip comment preservation is its
selling point. We don't edit the file programmatically — we only read it. The
extra ~150KB and slower load time buy nothing. `pyyaml.safe_load` is the
right tool.

**Why not `pydantic-yaml`:** It's a thin wrapper over `pyyaml + pydantic`.
We already have both — adding a third lib for a 10-line load helper is the
wrong trade. Write the helper.

**Why not `pydantic-settings`** (already pinned): It's purpose-built for
config-from-env / config-from-secrets, with YAML support added as a
`YamlConfigSettingsSource` in v2.4+. Using it here is technically possible
but conceptually wrong: this YAML file is *data* (a homebrew lookup table),
not *configuration* (knobs for app behavior). Keep `pydantic-settings` for
its actual job (env loading); use plain `pyyaml + pydantic v2 BaseModel` for
the eligibility data.

**Implementation sketch:**

```python
# src/eldritch_dm/gameplay/eligibility_config.py
from pathlib import Path
import yaml
from pydantic import BaseModel, ConfigDict, field_validator

class EligibilityRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    class_name: str
    subclass: str

    @field_validator("class_name", "subclass", mode="before")
    @classmethod
    def _norm(cls, v: object) -> str:
        return str(v or "").strip().lower()

class EligibilityConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    riposte: list[EligibilityRule]

DEFAULT_RIPOSTE: frozenset[tuple[str, str]] = frozenset(
    {("fighter", "battle master")}
)

def load_riposte_eligibility(path: Path | None) -> frozenset[tuple[str, str]]:
    """Return the active riposte eligibility set, falling back to RAW default."""
    if path is None or not path.exists():
        return DEFAULT_RIPOSTE
    raw = yaml.safe_load(path.read_text())
    cfg = EligibilityConfig.model_validate(raw)
    return frozenset((r.class_name, r.subclass) for r in cfg.riposte)
```

**File location:** `.eldritch/eligibility.yaml` (mirrors existing
`.eldritch/` convention used elsewhere in self-host layout per
`bootstrap.py`). Document in CONFIGURATION.md.

**Security:** `yaml.safe_load` ONLY — never `yaml.load` without a SafeLoader.
PyYAML 6.x defaults are safe; 6.0.3 (current as of 2026-09-25, verified
2026-05-23) shipped with FullLoader explicitly marked unsafe. This matches
the v1.0 sanitizer hygiene posture.

**Migration:** `reactions.ELIGIBLE_CLASS_SUBCLASSES` becomes a runtime-loaded
attribute on the cog (or singleton in `gameplay.eligibility_config`).
Existing v1.0 behavior is preserved when no YAML file exists — zero forced
config burden on existing self-hosters.

**Confidence:** HIGH. PyYAML is the canonical Python YAML lib; promotion
from `[dev]` is a one-line `pyproject.toml` change. The model + loader fit
the v1.0 pydantic pattern exactly.

### 3. `pc_classes` Ingest-Backfill Script

**Decision: Console-script in `pyproject.toml [project.scripts]`. Stdlib
`argparse`. Lives at `src/eldritch_dm/scripts/backfill_pc_classes.py`.**

**Console-script vs standalone:** The existing `run.py` is the only top-
level entrypoint; `pyproject.toml` already declares `eldritch-dm =
"eldritch_dm.bot.__main__:main"` (D-23). Self-hosters who `pip install -e .`
get `eldritch-dm` on PATH. Adding `eldritch-dm-backfill-pc-classes` as a
sibling entry-point is the consistent shape. Standalone `scripts/foo.py`
files would force `python scripts/foo.py` invocation which (a) breaks
on systemd/launchd installs that PATH-resolve binaries and (b) drifts from
the established convention.

**`argparse` vs `click` vs `typer`:**

| Tool | Pros | Cons | Verdict for this script |
|---|---|---|---|
| **`argparse` (stdlib)** | Zero deps. Already used in `run.py` (`--check-only`). Predictable. | Verbose for nested subcommands (irrelevant here — 1 command, ≤4 flags). | ✅ Use this. |
| `click==8.4.1` (2026-05-22) | Decorator API is pleasant. Echo helpers. | New dep for one ~50-line script. Pin + audit overhead. | ❌ Overkill. |
| `typer` (Click wrapper + types) | Same as click + type hints. | Same cons as click + an additional layer. | ❌ Overkill. |

The backfill script is a one-shot migration utility (NOT an interactive CLI
suite). Flags will be: `--db-path`, `--dry-run`, `--channel-id`,
`--force`. Stdlib argparse handles this in 15 lines.

**Architecture:** The script imports `eldritch_dm.persistence.pc_classes_repo`
+ talks to dm20 via `eldritch_dm.mcp.client` to list characters per channel
+ writes via `PCClassesRepo.upsert`. It bypasses Discord entirely (no bot,
no token). This is consistent with the `run.py --check-only` pattern (D-26
made `Settings.discord_token` Optional precisely so preflight + utility
paths can run token-free).

**Import-linter implications:** `eldritch_dm.scripts` is a new top-level
subpackage. Add a contract: `scripts may import mcp and persistence, but
NOT bot or ingest`. This keeps the script lightweight (no Discord
dependency in the import graph) and follows the existing layered firewall.

**Confidence:** HIGH. Zero new deps. Matches v1.0 conventions (`run.py`
already uses argparse). Console-script shape is already established.

### 4. Ruff Cleanup (TD-2)

**Decision: Bump `ruff>=0.6,<1.0` → `ruff>=0.15,<1.0`. Keep current rule
selection (`E,F,I,UP,B,ASYNC`). Run `--fix` (NOT `--unsafe-fixes`) on the
43 auto-fixable errors. Hand-fix the remaining 36. Defer `SIM` and `PERF`
to v1.2.**

**Why bump ruff:** Current floor is 0.6 (mid-2024); latest stable is
**0.15.14 released 2026-05-21** (Context7 + PyPI verified 2026-05-23 — one
day before v1.0 ship; pinning the new floor avoids contributor drift). 0.15
adds incremental performance + stability fixes; no migration burden for our
ruleset.

**Why NOT enable SIM / PERF this milestone:**

- **SIM (flake8-simplify):** SIM115 stabilized in 0.7 (file-opening
  patterns); SIM103/SIM108 frequently fire on async-resource code where
  the "simplification" hurts readability. Reviewing ~50–100 SIM hits
  against a 16k LOC codebase is its own deliverable. Defer.
- **PERF (perflint):** PERF401/402 (list-comprehension rewrites) frequently
  conflict with structlog-bound logging loops where the explicit `for`
  with bound context is clearer than a comprehension. PERF203 (`try`
  in loop) can fire in tenacity-wrapped retry call sites where the
  try/except IS the loop body's purpose. Defer to v1.2 after a one-time
  audit pass on what it would flag.

**Why NOT `--unsafe-fixes`:** Per Ruff docs (Context7), unsafe fixes "may
alter runtime behavior or comments". The 43 auto-fixable errors are
overwhelmingly import-ordering (I001) and `Optional[X]` → `X | None` (UP007)
— both safe. The 36 hand-fixes are likely F841 (unused variables in tests)
+ B-series (function-call defaults) which require human judgment. Running
`--unsafe-fixes` against a 23-file blast radius without per-file review
violates the v1.0 import-linter discipline.

**Procedure:**
1. `ruff check --fix .` (safe fixes only) — commit per-file or per-module.
2. Human-walk the remaining errors — likely 5 commits of 4–10 fixes each.
3. Final `ruff check .` must return 0. Add CI gate.
4. Verify `pytest` still passes 864/873 (no regressions).

**Watch out for:** `UP007` (`Optional[X]` → `X | None`) on pydantic v2
`Field()` defaults — pydantic v2 handles both, but mypy/pyright in strict
mode may complain in edge cases. Spot-check the model files after the
`--fix` pass.

**Confidence:** HIGH. Ruff config changes are the lowest-risk change in v1.1.

## Confidence Assessment

| Choice | Confidence | Verified via |
|---|---|---|
| Reuse `openai` AsyncOpenAI client for tactical oracle | HIGH | v1.0 codebase + PROJECT.md (multi-backend ingest already established) |
| f-strings over Jinja2 for one prompt | HIGH | Common-sense + v1.0 has no template engine |
| pydantic v2 `model_validate_json` for oracle response | HIGH | Already the pattern across the codebase |
| `tenacity` retry with fallback to v1.0 random | HIGH | Mirrors v1.0 MCP client retry pattern |
| Promote `pyyaml>=6.0.3,<7.0` from [dev] to core | HIGH | PyPI 2026-05-23: 6.0.3 (2025-09-25) is current stable |
| `yaml.safe_load` over `ruamel.yaml` round-trip | HIGH | Read-only use case; ruamel buys nothing |
| Reject `pydantic-yaml` and `pydantic-settings` for this | HIGH | Wrong-tool analysis — both have legitimate uses, neither fits this one |
| Console-script entry in pyproject + stdlib argparse | HIGH | Matches D-23 convention + run.py precedent |
| Reject `click==8.4.1` for one-shot migration script | HIGH | PyPI 2026-05-22 confirms 8.4.1; tool is solid but overkill here |
| Bump ruff floor to `>=0.15,<1.0` | HIGH | PyPI 2026-05-21: 0.15.14 is current stable |
| Defer SIM / PERF rules to v1.2 | MEDIUM-HIGH | Judgment call — Context7 confirms both rule families are stable but their hit-count on this codebase is unknown |
| `--fix` safe-only on the 43 auto-fixable, hand-fix the 36 | HIGH | Ruff docs explicitly warn `--unsafe-fixes` may alter behavior |

## Anti-Patterns to Avoid

| Avoid | Why | Use Instead |
|---|---|---|
| Adding `jinja2` for one f-string prompt | 700KB + template lifecycle for zero benefit | f-string in `gameplay/monster_tactics.py` |
| Calling `dm20__claudmaster_step` to ask "who to attack" | Wrong shape — that tool runs a full DM tick and would conflict with our turn-gating | Direct `openai` client call to ShoeGPT with structured response |
| Wiring the smart driver without a random-target fallback | Single point of failure; oMLX hiccup deadlocks combat | `tenacity` retry → fallback `random.choice` (v1.0 behavior) |
| Using `yaml.load(stream)` without a SafeLoader | RCE via custom Python tag deserialization | `yaml.safe_load(stream)` only |
| `pydantic-settings.YamlConfigSettingsSource` for eligibility | Mis-applies a config tool to data | `pyyaml + pydantic v2 BaseModel` |
| Standalone `scripts/backfill.py` invoked via `python -m` | Drifts from D-23 console-script convention | `[project.scripts]` entry |
| `click==8.4.1` for the backfill script | New runtime dep for a 50-line one-shot CLI | stdlib `argparse` |
| `ruff check --fix --unsafe-fixes .` across all 23 files | May silently alter runtime behavior; defeats the per-file review discipline | `ruff check --fix .` (safe-only), then manual pass |
| Enabling `SIM` + `PERF` in the same milestone as the 79-error cleanup | Conflates "fix existing debt" with "raise the bar"; risks regressions | Cleanup in v1.1, raise the bar in v1.2 after dust settles |

## Phase Ordering Implications (for Roadmapper)

The deliverables are mostly independent and can be parallelized, but two
sequencing constraints matter:

1. **Ruff cleanup (TD-2) FIRST.** Touches 23 files including some that the
   other deliverables will modify (`reactions.py` for YAML, `monster_driver.py`
   for smart driver). Doing it first prevents merge conflicts and keeps
   each subsequent diff narrowly scoped to its actual feature.

2. **YAML eligibility BEFORE smart MonsterDriver.** Both touch
   `gameplay/`. YAML is the smaller change (one new module + one config-load
   site). Landing it first lets the smart driver phase consume a clean,
   already-loaded eligibility set rather than racing two refactors of
   `reactions.py`.

3. **Backfill script can ship in parallel with anything.** It lives in a
   new subpackage (`scripts/`) and only reads from existing repos.

4. **SAN-01, OPS-02, `__main__` parity** are pure refactor in `bot/` —
   parallel with everything, no stack changes.

## Sources

- [PyYAML on PyPI](https://pypi.org/project/PyYAML/) — 6.0.3 verified 2026-05-23 (released 2025-09-25)
- [ruamel.yaml on PyPI](https://pypi.org/project/ruamel.yaml/) — 0.19.1 verified 2026-05-23 (released 2026-01-02)
- [Click on PyPI](https://pypi.org/project/click/) — 8.4.1 verified 2026-05-23 (released 2026-05-22)
- [Ruff on PyPI](https://pypi.org/project/ruff/) — 0.15.14 verified 2026-05-23 (released 2026-05-21)
- Context7 `/astral-sh/ruff` — `--unsafe-fixes` semantics + recommended rule selection (E,F,I,UP,B,SIM)
- Context7 `/yaml/pyyaml` — `safe_load` vs `load` security posture
- v1.0 STACK.md (CLAUDE.md inline) — historical decisions on `pydantic-ai`/`instructor`/`langchain` rejection, `pydantic v2` over v1, `openai`-client-over-MLX-server pattern
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md` — TD-1/TD-2/TD-3, G-3/G-4 origins
- `src/eldritch_dm/gameplay/reactions.py:84-88` — current hardcoded `ELIGIBLE_CLASS_SUBCLASSES` + TODO(v2) marker
- `src/eldritch_dm/gameplay/monster_driver.py:64-77` — current random-target driver + D-B "smart Claudmaster-driven targeting deferred to v2" comment
- `src/eldritch_dm/persistence/pc_classes_repo.py` — backfill target schema + normalization rules
- `pyproject.toml` — current pinned deps + ruff config + `[project.scripts]` precedent
