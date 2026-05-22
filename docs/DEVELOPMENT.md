<!-- generated-by: gsd-doc-writer -->
# Development

This guide covers everything a contributor needs to be productive in the EldritchDM codebase: local setup, editor expectations, the custom defer-discipline lint rule, import-linter contracts, and the phase-based development workflow used throughout the project.

For a tour of the modules and layering rules, see [ARCHITECTURE.md](./ARCHITECTURE.md). For environment variables, see [CONFIGURATION.md](./CONFIGURATION.md).

## Local Setup

EldritchDM targets Python **3.11+** (capped at `<3.13` because some ML wheels lag) on Apple Silicon macOS primarily. Linux/CUDA is a best-effort secondary target.

```bash
git clone <your-fork-url> DiscordDM
cd DiscordDM
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev,mac-ocr]"      # macOS — primary OCR backend
# or
uv pip install -e ".[dev,linux-ocr]"    # Linux/CUDA fallback
pre-commit install
pytest                                    # 728 tests should pass (~30s)
```

`install.sh` automates these steps with platform detection and an oMLX/dm20 reachability check. Run `./install.sh` for a guided first-time setup, or `./install.sh --quiet` for CI-style output.

### Required Local Services

The bot is an orchestrator — it depends on two local services running before tests beyond the unit layer make sense:

- **oMLX** (`omlx serve` on `:8765`) — supplies the `ShoeGPT` model used for narration and ingest translation. On the developer's machine this is launchd-supervised as `com.user.omlx`.
- **dm20 MCP server** — exposes the 97-tool gameplay surface at `:8765/v1/mcp/execute`.

Unit tests mock both. Integration tests gated behind `RUN_INTEGRATION=1`, `RUN_STRESS=1`, and `RUN_LOAD=1` env vars hit real services or simulate them with a virtual clock.

## Editor Expectations

- **Format + lint on save** with ruff. Project config lives in `pyproject.toml` under `[tool.ruff]` — line length 100, target `py311`, rule set `E, F, I, UP, B, ASYNC`.
- **Type-check** with pyright. discord.py's type stubs are upstream and accurate; mypy works too but is slower.
- **Pre-commit hooks** must be installed (`pre-commit install`). The hook chain runs ruff (with `--fix`), ruff-format, and the custom EDM001 defer-discipline check on every commit touching `src/eldritch_dm/bot/**/*.py`.

VS Code users: set `python.formatting.provider` to `none` and let the Ruff extension drive both format and lint. PyCharm users: enable the Ruff plugin and disable PyCharm's built-in formatter for `.py` files.

## The Defer-Discipline Rule (EDM001)

Discord interactions have a hard **3-second acknowledgement window**. Miss it and the user sees "This interaction failed." There is no recovery — Discord will not accept a late response. EDM001 is an AST-based lint rule that statically guarantees every interaction callback acks within that window.

**The rule:** Every Discord interaction callback's first non-docstring statement MUST be one of:

```python
await interaction.response.defer(...)          # standard case
await interaction.response.send_modal(...)     # modal-launching exception
```

**What it scans:** functions decorated with `@command`, `@button`, `@select`, `@context_menu`, or `@<cmd>.error`, plus any method named `callback` inside a class that subclasses `View`, `Modal`, `Button`, `Item`, or `DynamicItem`. The check is a conservative AST walk in `src/eldritch_dm/lint/edm001.py` — false positives are acceptable; missed violations are not.

**How to fix a violation:** Move the defer to the top of the callback. If the callback legitimately must respond differently (e.g., `_ModalLaunchView` button → `send_modal` requires a fresh interaction), waive it on the `def` line:

```python
@discord.ui.button(label="Open form")
async def open(self, interaction: discord.Interaction, button) -> None:  # noqa: EDM001 — sends modal, can't defer
    await interaction.response.send_modal(MyModal())
```

**How it runs:** the pre-commit hook invokes `python -m eldritch_dm.lint.edm001` against staged files under `src/eldritch_dm/bot/`. You can run it manually:

```bash
python -m eldritch_dm.lint.edm001 src/eldritch_dm/bot/
```

`tools/lint_defer_discipline.py` is a thin wrapper that lets you invoke the same logic as a standalone script.

## Import-Linter Contracts

Module boundaries are enforced by [import-linter](https://import-linter.readthedocs.io/) contracts defined in `pyproject.toml` under `[tool.importlinter]`. Run them with:

```bash
lint-imports
```

Current contracts (all `forbidden` type):

| Contract | Forbids | Why |
|---|---|---|
| `persistence must not import mcp or safety` | `eldritch_dm.persistence → mcp \| safety` | Persistence is pure SQL + pydantic models; can be tested without any subsystem |
| `mcp must not import persistence or safety` | `eldritch_dm.mcp → persistence \| safety` | MCP client must be reusable in isolation; no DB coupling |
| `safety must not import mcp or persistence internals` | `eldritch_dm.safety → mcp \| persistence.connection \| ...repos` | Sanitizer is pure-Python; may only import `persistence.models` (pydantic data shapes) |
| `config and logging must not import subsystems` | `config \| logging → mcp \| persistence \| safety` | Bootstrap utilities cannot depend on what they configure |
| `ingest must not import bot or persistence` | `eldritch_dm.ingest → bot \| persistence internals` | OCR/PDF pipeline is pure-Python; testable without Discord or DB |
| `nothing outside bot may import from bot` | `config, logging, mcp, persistence, safety, gameplay → bot` | Subsystems stay hermetic; only the Discord integration layer reaches downward |
| `gameplay must not import bot or ingest` | `eldritch_dm.gameplay → bot \| ingest` | Gameplay (orchestrator, batchers, rate limiters) is Discord-agnostic |

Two firewalls deserve a special call-out:

- **`mcp` → `ingest` is banned** by transitive consequence of the `ingest` contract — the OCR/translation pipeline imports `mcp.client` to call oMLX, but nothing in `mcp/` may reach back into `ingest`. This keeps the MCP client a leaf dependency.
- **`bot/ingest` → `gameplay` is banned** by the `gameplay` contract — gameplay primitives (orchestrator, rate limiter, batcher) must not depend on the Discord layer or the ingest pipeline, so they can be tested in isolation and reused.

## Layered Architecture Rules

The contracts above encode a layered architecture. From innermost (no dependencies) to outermost (integration):

1. `config`, `logging` — pure bootstrap
2. `persistence.models` — pydantic data shapes
3. `safety`, `mcp`, `persistence` (internals) — independent subsystems
4. `ingest`, `gameplay` — pure-Python pipelines and orchestration primitives
5. `bot` — the only layer that touches discord.py

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the detailed module map and the rationale behind each layer.

## Phase-Based Development Workflow

EldritchDM follows the **GSD (Get Sh*t Done)** workflow. Work is organized into phases (large scope, weeks of effort) which contain plans (focused scope, hours of effort). Each plan moves through four artifacts:

1. **RESEARCH** — what's the unknown? What does dm20 expose? What pitfalls exist? Lives in `.planning/phases/<phase>/<phase>-RESEARCH.md`.
2. **PLAN** — atomic numbered tasks with success criteria. Lives in `.planning/phases/<phase>/<NN>-PLAN-<slug>.md`.
3. **Execute** — RED→GREEN gates, atomic commits, one task at a time.
4. **SUMMARY** — what shipped, decisions made, deviations. Lives in `<NN>-SUMMARY.md` per plan and a phase-wide `<phase>-SUMMARY.md` at closure.

Phases are tracked in `.planning/ROADMAP.md` (long-lived plan) and the current cursor lives in `.planning/STATE.md` (single source of truth for "what's next"). Browse `.planning/phases/01-mcp-client-local-state/` through `04-gameplay-exploration-combat/` for completed examples — each shows the full RESEARCH → PLAN → SUMMARY arc.

### GSD Command Suite

Do not make direct repo edits outside a GSD workflow. Entry points:

| Command | When |
|---|---|
| `/gsd-quick` | Small fixes, doc updates, ad-hoc tasks |
| `/gsd-debug` | Investigation and bug fixing |
| `/gsd-execute-phase` | Planned phase work — picks up from STATE.md cursor |
| `/gsd-autonomous` | Auto-loop through a phase's plans (used with `/loop`) |

## Atomic-Commit Discipline

Small, descriptive commits. Each commit either adds a failing test (RED), makes a test pass (GREEN), or is a chore/doc step. Conventional-commit prefixes scoped by phase-plan:

```
feat(04-gameplay-exploration-combat): combat buttons + dodge shim + WeaponSelectModal
test(04-02): add failing tests for CombatCog + combat flow integration
docs(04-02): complete combat-cog-and-turn-gatekeeping plan
chore(04-gameplay-exploration-combat): audit MCP wrappers — drop stray campaign_name kwargs
fix(04-gameplay-exploration-combat): remove DeclareActionButton from stub test parametrize
```

Run `git log --oneline -30` to see the pattern in action.

## Rule 1 / Deviation Protocol

When a plan task's test gate fails, the auto-fix loop ("Rule 1") kicks in — instead of papering over the failure, you back out, diagnose the root cause, and let the failing test drive a structural fix. Two real examples from Phase 4 Plan 03 (commit `6457212`):

- **Double-started aiosqlite Thread.** `CombatConditionsRepo._connect()` returned an already-started `Connection`; callers used `async with await self._connect()`, which re-started the underlying thread (`RuntimeError: threads can only be started once`). Fix: `_connect()` returns an *unstarted* `Connection`; a new `_configure()` helper applies `row_factory` and pragmas after the single `async with` entry.
- **Duplicate combat-condition rows.** The original `INSERT ON CONFLICT ... + INSERT OR REPLACE` pattern produced duplicate rows because the schema had no `UNIQUE` on `(channel_id, character_id, condition_kind)`. Fix: `DELETE`-by-triple followed by a single `INSERT`.

Both bugs were discovered the first time a non-mocked integration test exercised the repo. The takeaway: integration tests find Rule 1 violations that unit tests with mocks cannot.

## Tech Stack (Pinned Versions)

| Layer | Library | Pin |
|---|---|---|
| Runtime | Python | `>=3.11,<3.13` |
| Discord | `discord.py` | `>=2.7.1,<3.0` |
| HTTP | `httpx[http2]` | `>=0.27,<0.29` |
| DB | `aiosqlite` | `>=0.20,<0.22` |
| Validation | `pydantic` | `>=2.8,<3.0` |
| Retries | `tenacity` | `>=8.5,<10.0` |
| Logging | `structlog` | `>=24.4,<26.0` |
| LLM client | `openai` | `>=1.55,<2.0` |
| PDF | `PyMuPDF` + `pypdf` | `>=1.24,<2.0` / `>=4.3,<6.0` |
| OCR (macOS) | `ocrmac` | `>=1.0,<2.0` |
| OCR (Linux) | `easyocr` | `>=1.7,<2.0` |
| Lint/format | `ruff` | `>=0.6,<1.0` |
| Imports | `import-linter` | `>=2.0,<3.0` |
| Tests | `pytest` + `pytest-asyncio` + `respx` + `syrupy` | see `[project.optional-dependencies].dev` |

See `CLAUDE.md` § Technology Stack for the full rationale, alternatives considered, and confidence ratings on each choice.
