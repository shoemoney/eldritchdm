<!-- generated-by: gsd-doc-writer -->
# Development

This guide covers everything a contributor needs to be productive in the
EldritchDM codebase: local setup, dependency groups, console scripts,
the custom defer-discipline lint rule, import-linter contracts, the
phase-based development workflow, and CI expectations.

For a tour of modules and layering rules, see
[ARCHITECTURE.md](./ARCHITECTURE.md). For environment variables, see
[CONFIGURATION.md](./CONFIGURATION.md). For the full v1.0 → v1.11
release history, see [`CHANGELOG.md`](../CHANGELOG.md).

## Local Setup

EldritchDM targets Python **3.11+** (capped at `<3.13` because some ML
wheels lag) on Apple Silicon macOS primarily. Linux/CUDA is a best-effort
secondary target.

```bash
git clone <your-fork-url> DiscordDM
cd DiscordDM
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev,mac-ocr]"        # macOS — primary OCR backend
# or
uv pip install -e ".[dev,linux-ocr]"      # Linux/CUDA fallback
pre-commit install
pytest                                     # default suite, ~10s
```

`install.sh` automates these steps with platform detection and an
oMLX/dm20 reachability check. Run `./install.sh` for a guided first-time
setup. See [INSTALL.md](../INSTALL.md) for the operator-facing walkthrough.

### Required Local Services

The bot is an orchestrator — it depends on two local services running
before tests beyond the unit layer make sense:

- **oMLX** (`omlx serve` on `:8765`) — supplies the `ShoeGPT` model used
  for ingest translation and (v1.1+) SmartMonsterDriver target oracle. On
  the developer's machine this is launchd-supervised as
  `com.user.omlx`.
- **dm20 MCP server** — exposes the gameplay tool surface at
  `:8765/v1/mcp/execute`.

Unit tests mock both. Integration tests gated behind `RUN_INTEGRATION=1`,
`RUN_STRESS=1`, and `RUN_LOAD=1` env vars hit real services or simulate
them with a virtual clock. See [TESTING.md](./TESTING.md).

## Dependency Groups

Declared in `pyproject.toml` `[project.optional-dependencies]`:

| Extras | Install command | Contents |
|---|---|---|
| `dev` | `uv pip install -e ".[dev]"` | `pytest >=8`, `pytest-asyncio`, `pytest-cov >=5`, `pytest-mock`, `ruff >=0.15`, `respx`, `import-linter >=2`, `syrupy >=4.6`, `reportlab` (test PDF fixtures). |
| `mac-ocr` | `uv pip install -e ".[dev,mac-ocr]"` | `ocrmac >=1.0,<2.0` — Apple Vision OCR (primary on macOS). |
| `linux-ocr` | `uv pip install -e ".[dev,linux-ocr]"` | `easyocr >=1.7,<2.0` — PyTorch-backed fallback for Linux/CUDA. |
| `observability` | `uv pip install -e ".[dev,observability]"` | `opentelemetry-api/sdk`, `opentelemetry-exporter-otlp-proto-http`, `prometheus_client` — Phase 11+13. Off by default; only paid when `OBSERVABILITY_ENABLED=true`. |

CI installs `[dev]` only on the default matrix; an informational
`extras-mac` job exercises `[dev,mac-ocr,observability]` on macOS.

## Operator CLIs

Each `[project.scripts]` entry is exposed on PATH after
`uv pip install -e .`:

| Console script | Module | Since |
|---|---|---|
| `eldritch-dm` | `eldritch_dm.bot.__main__:main` | v1.0 |
| `eldritch-dm-backfill-pc-classes` | `eldritch_dm.tools.backfill_pc_classes:main` | v1.1 (Phase 9 / TD-3 upgrade tool) |
| `eldritch-dm-eval` | `eldritch_dm.eval.cli:main` | v1.2 (Phase 12 — LLM-as-judge) |
| `eldritch-dm-cost-report` | `eldritch_dm.tools.cost_report:main` | v1.2 (Phase 13 / MON-03) |
| `eldritch-dm-cache-clear` | `eldritch_dm.tools.cache_clear:main` | v1.5 (Phase 17 / CHARCACHE-03) |
| `eldritch-dm-cache-disable` | `eldritch_dm.tools.cache_disable:main` | v1.5 (Phase 18 / NARRCACHE-03) |
| `eldritch-dm-cache-stats` | `eldritch_dm.tools.cache_stats:main` | v1.5 (Phase 18) |
| `eldritch-dm-perf-baseline` | `eldritch_dm.tools.perf_baseline:main` | v1.9 (Phase 28 / TUNE-02) |

Each CLI has `--help`. `eldritch-dm-eval` and `eldritch-dm-perf-baseline`
support a `--baseline <file>` flag with **3-tier exit codes**
(0 = within tolerance, 1 = warn, 2 = critical) so they can be wired into
CI as regression detectors.

## Editor Expectations

- **Format + lint on save** with ruff. Config lives in `pyproject.toml`
  under `[tool.ruff]` — line length 100, target `py311`, rule set
  `E, F, I, UP, B, ASYNC`. Project floor is `ruff >=0.15,<1.0` (bumped in
  v1.1 Phase 6 after the 79→0 ruff-debt cleanup).
- **Type-check** with pyright. discord.py's type stubs are upstream and
  accurate; mypy works too but is slower.
- **Pre-commit hooks** must be installed (`pre-commit install`). The hook
  chain (see `.pre-commit-config.yaml`):

  | Hook | Command | Scope |
  |---|---|---|
  | `ruff` (`--fix`) | `astral-sh/ruff-pre-commit v0.9.10` | All Python files |
  | `ruff-format` | same repo | All Python files |
  | `edm001-defer-discipline` | `python -m eldritch_dm.lint.edm001` | `^src/eldritch_dm/bot/.*\.py$` only |
  | `yaml-safe-load-only` | `scripts/ci/check_safe_yaml.sh` (T-08-01) | All files |

VS Code users: set `python.formatting.provider` to `none` and let the
Ruff extension drive both format and lint.

## The Defer-Discipline Rule (EDM001)

Discord interactions have a hard **3-second acknowledgement window**.
Miss it and the user sees "This interaction failed." EDM001 is an
AST-based lint rule that statically guarantees every interaction
callback acks within that window.

**The rule:** Every Discord interaction callback's first non-docstring
statement MUST be one of:

```python
await interaction.response.defer(...)          # standard case
await interaction.response.send_modal(...)     # modal-launching exception
```

**What it scans:** functions decorated with `@command`, `@button`,
`@select`, `@context_menu`, or `@<cmd>.error`, plus any method named
`callback` inside a class that subclasses `View`, `Modal`, `Button`,
`Item`, or `DynamicItem`. The check lives in
`src/eldritch_dm/lint/edm001.py`.

**How to fix a violation:** Move the defer to the top of the callback,
or waive it on the `def` line with `# noqa: EDM001 — <reason>`.

**Run it manually:**

```bash
python -m eldritch_dm.lint.edm001 src/eldritch_dm/bot/
```

## Import-Linter Contracts

Module boundaries are enforced by
[import-linter](https://import-linter.readthedocs.io/) contracts defined
in `pyproject.toml` under `[tool.importlinter]`. Run them with:

```bash
lint-imports
```

Eight `forbidden`-type contracts (full table in
[ARCHITECTURE.md → Layering Rules](./ARCHITECTURE.md#layering-rules-import-linter-contracts)).
The headline rules:

- **`mcp` → `ingest`** is banned (transitive consequence) — keeps MCP a
  leaf transport layer.
- **`bot` / `ingest` → `gameplay`** is banned — gameplay primitives must
  be Discord-agnostic.
- **`eval` → `bot` / `ingest`** is banned (v1.2 addition) — the eval
  runner may import `gameplay` (to invoke SmartMonsterDriver) and
  `observability` (for `traced_eval`), but never Discord or ingest.

## Phase-Based Development Workflow

EldritchDM follows the **GSD (Get Sh*t Done)** workflow. Work is
organized into phases (large scope, weeks of effort) which contain plans
(focused scope, hours of effort). Each plan moves through four artifacts:

1. **RESEARCH** — what's the unknown? What does dm20 expose? What
   pitfalls exist? `.planning/phases/<phase>/<phase>-RESEARCH.md`.
2. **PLAN** — atomic numbered tasks with success criteria.
   `.planning/phases/<phase>/<NN>-PLAN-<slug>.md`.
3. **Execute** — RED→GREEN gates, atomic commits, one task at a time.
4. **SUMMARY** — what shipped, decisions made, deviations. `<NN>-SUMMARY.md`
   per plan and a phase-wide `<phase>-SUMMARY.md` at closure.

Milestone-level history is collapsed in
[`CHANGELOG.md`](../CHANGELOG.md); per-milestone audits live in
`.planning/v1.NN-MILESTONE-AUDIT.md`; the cursor lives in
`.planning/STATE.md`.

### GSD Command Suite

Do not make direct repo edits outside a GSD workflow. Entry points:

| Command | When |
|---|---|
| `/gsd-quick` | Small fixes, doc updates, ad-hoc tasks |
| `/gsd-debug` | Investigation and bug fixing |
| `/gsd-execute-phase` | Planned phase work — picks up from STATE.md cursor |
| `/gsd-autonomous` | Auto-loop through a phase's plans |

## Atomic-Commit Discipline

Conventional-commit prefixes scoped by phase-plan:

```
feat(04-gameplay-exploration-combat): combat buttons + dodge shim
test(04-02): add failing tests for CombatCog
docs(04-02): complete combat-cog-and-turn-gatekeeping plan
chore(06-ruff): apply --fix --select I
fix(20-aoe): post-parse validation rejects hallucinated target_pc_ids
```

Run `git log --oneline -30` to see the pattern in action.

## CI Expectations

`.github/workflows/ci.yml` (Phase 24 / POLISH-01, expanded over v1.7+):

- **`test` matrix:** macOS-latest + ubuntu-latest × Python 3.11.
  Installs `[dev]` ONLY (no mac-ocr, no observability). Runs:
  1. `uv run ruff check src/ tests/ run.py`
  2. `uv run lint-imports`
  3. `uv run pytest tests/ -q --cov=eldritch_dm --cov-report=term --cov-report=xml:coverage.xml`
  4. (Linux only) `scripts/ci/check_safe_yaml.sh`
  5. (Linux only) `scripts/ci/check_summary_frontmatter.sh`
  6. (Linux only) uploads `coverage.xml` artifact (14-day retention).
- **`extras-mac` job:** macOS-latest with `[dev,mac-ocr,observability]`.
  Marked `continue-on-error: true` — flaky native extras never block a
  merge.

`.github/workflows/perf.yml` (Phase 28 / TUNE-03 / D-219, v1.9+):

- Runs `eldritch-dm-perf-baseline --baseline .planning/perf-baseline-v1.9.0.json`
  on macOS-latest.
- Triggers: weekly Sundays 02:00 UTC, push to `main` only when commit
  message contains `[perf]`, manual `workflow_dispatch`.
- `continue-on-error: true` — informational only. Exit codes
  0 / 1 / 2 surface drift; investigate before committing a new baseline.

Test commands the CI runs are the same you can run locally:

```bash
uv run ruff check src/ tests/ run.py
uv run lint-imports
uv run pytest tests/ -q --cov=eldritch_dm --cov-report=term
RUN_STRESS=1 uv run pytest tests/perf/ -v
RUN_LOAD=1   uv run pytest tests/integration/test_8player_load.py -v
```

## Tech Stack (Pinned Versions)

| Layer | Library | Pin |
|---|---|---|
| Runtime | Python | `>=3.11,<3.13` |
| Discord | `discord.py` | `>=2.7.1,<3.0` |
| HTTP | `httpx[http2]` | `>=0.27,<0.29` |
| DB | `aiosqlite` | `>=0.20,<0.22` |
| Validation | `pydantic` + `pydantic-settings` | `>=2.8,<3.0` / `>=2.4,<3.0` |
| Retries | `tenacity` | `>=8.5,<10.0` |
| Logging | `structlog` | `>=24.4,<26.0` |
| LLM client | `openai` | `>=1.55,<2.0` |
| PDF | `PyMuPDF` + `pypdf` | `>=1.24,<2.0` / `>=4.3,<6.0` |
| OCR (macOS) | `ocrmac` | `>=1.0,<2.0` (extras) |
| OCR (Linux) | `easyocr` | `>=1.7,<2.0` (extras) |
| Lint/format | `ruff` | `>=0.15,<1.0` |
| Imports | `import-linter` | `>=2.0,<3.0` |
| Tests | `pytest` + `pytest-asyncio` + `pytest-cov` + `respx` + `syrupy` | see `[project.optional-dependencies].dev` |
| Telemetry (opt-in) | `opentelemetry-*` + `prometheus_client` | see `[observability]` extras |

See `CLAUDE.md` § Technology Stack for the full rationale, alternatives
considered, and confidence ratings on each choice.

## Cross-references

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — PR process, code of conduct
  reference, what NOT to contribute.
- [`docs/TESTING.md`](./TESTING.md) — test categories + env gates.
- [`docs/CONFIGURATION.md`](./CONFIGURATION.md) — every env var.
- [`docs/DEPLOYMENT.md`](./DEPLOYMENT.md) — Docker compose stack +
  GitHub Actions deploy paths.
- [`docs/PERFORMANCE.md`](./PERFORMANCE.md) — v1.9 baseline + hot-path
  budgets.
