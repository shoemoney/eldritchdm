<!-- generated-by: gsd-doc-writer -->
# Testing

EldritchDM tests are the contract that lets us claim the bot is **mechanically
honest**. The integrity rule ("LLM never computes math") only holds if rules,
persistence, and Discord plumbing are independently verified — so the suite is
structured to test each subsystem in isolation, then in integration, then under
restart and load.

At Phase 4 close the suite is **734 tests** across unit, integration, and
restart-survival drills.

## Test framework and setup

- **Framework:** `pytest >=8.0,<9.0` with `pytest-asyncio >=0.23,<1.0`
  (declared in `pyproject.toml [project.optional-dependencies].dev`).
- **Async mode:** `asyncio_mode = "auto"` in `[tool.pytest.ini_options]` —
  every `async def test_*` is auto-collected; no per-test `@pytest.mark.asyncio`
  decorator required.
- **HTTP mocking:** `respx >=0.21,<1.0` for mocking `httpx` calls (every
  oMLX/MCP test is offline by default).
- **Mocking:** `pytest-mock >=3.12,<4.0` plus the stdlib `unittest.mock`
  (`AsyncMock`, `MagicMock`).
- **Snapshots:** `syrupy >=4.6,<5.0` for any place we need golden output.
- **Setup:** install dev extras once with `uv pip install -e '.[dev]'` (or pip
  equivalent). All tests run against a fresh ephemeral SQLite DB created in
  `tmp_path`; there is no global DB state to reset.

## Where tests live

Tests live **only under `tests/` at the repo root** — there is no `src/`-side
test directory. Source code stays clean of test files; `pyproject.toml`
declares `testpaths = ["tests"]`.

```
tests/
  conftest.py              # tmp_env + frozen_settings fixtures
  test_config.py           # Pydantic Settings validation
  test_logging.py          # structlog wiring
  bot/                     # discord.py layer: Views, DynamicItems, modals, cogs
    _edm001_corpus/        # AST corpus for the EDM001 defer-discipline lint
    cogs/
    test_dynamic_items*.py # custom_id round-trip + callback behavior
    test_coalescer.py      # EmbedCoalescer + ChannelEditBudget
    test_restart_drill.py  # Phase 2 BOT-08: kill-and-restart drill (LOBBY)
    ...
  gameplay/                # exploration batch, party mode, rate-limit logic
  ingest/                  # PDF/OCR character ingest pipeline
  integration/             # cross-subsystem end-to-end flows
    test_8player_load.py   # Phase 4 Plan 03 COMBAT-08 load test (RUN_LOAD=1)
    test_restart_mid_combat.py  # D-35: restart mid-combat survival drill
    test_combat_flow.py
    test_phase{1,3}_smoke.py
  mcp/                     # MCPClient against mocked oMLX (respx)
  persistence/             # SQLite repos, WriterQueue, bootstrap, checkpoint
    conftest.py            # bootstrapped_db + bootstrapped_db_with_repos
    test_concurrent_writes.py    # 4-channel stress (RUN_STRESS=1)
  safety/                  # Sanitizer + adversarial corpus
    test_sanitizer.py      # YAML-driven >= 30-case corpus
```

The structure mirrors the source-side module firewall (enforced by
`import-linter` — see `pyproject.toml [tool.importlinter]`): each subsystem's
tests sit in their own directory and exercise only their own public API.

## How to run

```bash
# Fast suite (default): everything NOT gated by an env var
pytest

# Verbose with summary lines printed (load tests print a summary)
pytest -v -s

# Single subsystem
pytest tests/persistence
pytest tests/safety/test_sanitizer.py

# Single test
pytest tests/integration/test_restart_mid_combat.py::test_restart_mid_combat_survives

# 8-player combat load test (gated; see "Load test" below)
RUN_LOAD=1 pytest tests/integration/test_8player_load.py -v -s

# 4-channel concurrent-write stress test (gated)
RUN_STRESS=1 pytest tests/persistence/test_concurrent_writes.py -v

# Everything, including gated suites
RUN_LOAD=1 RUN_STRESS=1 pytest -v

# Coverage
pytest --cov=eldritch_dm --cov-report=term-missing
pytest --cov=eldritch_dm --cov-report=html  # writes htmlcov/index.html
```

## Test categories

### Unit tests (the bulk of the 734)

- **`tests/safety/test_sanitizer.py`** — runs the >= 30-case adversarial YAML
  corpus through `sanitize_player_input` and asserts strip count, audit-row
  emission, and `<player_action>` sentinel integrity. See the
  **Adversarial sanitizer corpus** section below.
- **`tests/mcp/test_client.py`** — `MCPClient` against `respx`-mocked oMLX.
  Covers happy-path, timeouts, retries, circuit breaker, tool errors. Zero
  real network traffic.
- **`tests/persistence/test_*_repo.py`** — round-trip every repo: upsert →
  read → assert pydantic model equality. Each repo test uses the
  `bootstrapped_db` fixture (fresh on-disk SQLite + live `WriterQueue`).
- **`tests/bot/test_dynamic_items.py`** — `discord.ui.DynamicItem` subclasses
  (AttackButton, DodgeButton, EndTurnButton, CastSpellButton, ReadyButton,
  RiposteButton, DeclareActionButton): asserts `custom_id` construction stays
  under the 100-char Discord limit, the regex template round-trips via
  `from_custom_id`, and bad custom_ids do NOT match.
- **`tests/bot/test_coalescer.py`** — `EmbedCoalescer` + `ChannelEditBudget`
  cadence math (per-message ≥ 1s gap; ≤ 5 edits/5s/channel).
- **`tests/ingest/`** — pypdf + PyMuPDF + OCR (ocrmac/easyocr) pipeline with
  synthetic PDF fixtures generated by `reportlab` in the test conftest.

### Integration tests

- **`tests/integration/test_phase1_smoke.py`** and
  **`tests/integration/test_phase3_smoke.py`** — end-to-end smokes of the
  Phase 1 (MCP+local state) and Phase 3 (Discord scaffold) milestones.
- **`tests/integration/test_combat_flow.py`** — combat happy-path across
  MCP → persistence → embed coalescer.
- **`tests/integration/test_restart_mid_combat.py`** — see
  **Restart-survival drills** below.
- **`tests/integration/test_8player_load.py`** — see **Load test** below.

### Lint tests (EDM001 defer-discipline)

- **`tests/bot/test_defer_discipline.py`** — exercises the AST-based EDM001
  lint rule defined in `src/eldritch_dm/lint/edm001.py`. The rule enforces
  that every Discord interaction callback's first non-docstring statement is
  `await interaction.response.defer(...)` (or `send_modal(...)`), with
  `# noqa: EDM001 — <reason>` as the only escape hatch.
- **`tests/bot/_edm001_corpus/good/`** — 6 files that MUST pass the rule.
- **`tests/bot/_edm001_corpus/bad/`** — 5 files that MUST trigger the rule.
- **Bonus:** the test runs EDM001 against the real `src/eldritch_dm/bot/`
  tree and asserts zero violations there.

## Test markers

Declared in `[tool.pytest.ini_options].markers`:

| Marker | Meaning | Default behavior |
|---|---|---|
| `load` | 8-player combat load test (Plan 03 COMBAT-08). Gated by `RUN_LOAD=1`. | Skipped unless `RUN_LOAD=1` is set. |
| `slow` | Long-running / stress-style tests. Gated by `RUN_STRESS=1` for the persistence stress, or `RUN_LOAD=1` for the load test (which carries both markers). | Skipped unless the relevant env var is set. |

Skipping is implemented via `pytest.mark.skipif(not os.environ.get(...))` on
each gated test, not by deselecting markers — so a plain `pytest` always skips
the right set without `-m` flags. To force-include, set the env var. To
force-exclude even if env vars are set, use `pytest -m "not slow and not load"`.

## Async test patterns

- `asyncio_mode = "auto"` means every `async def test_*` runs in the default
  event loop without extra decoration.
- **Fixtures** (all `@pytest_asyncio.fixture`):
  - `tmp_env` (in root `conftest.py`) — sets `DISCORD_TOKEN` and
    `ELDRITCH_DB_PATH` env vars, clears the `get_settings()` LRU cache.
  - `bootstrapped_db` (in `tests/persistence/conftest.py`) — bootstraps a
    fresh on-disk SQLite DB and starts a live `WriterQueue`. Yields
    `(db_path, writer_queue)`; teardown stops the queue.
  - `bootstrapped_db_with_repos` — same, plus ChannelSession, PersistentView,
    RiposteTimer, SanitizerAudit repos and a `SessionLocks` instance.
  - Per-test ad-hoc fixtures: `db_path`, `writer_queue`, `repos` (see
    `tests/integration/test_restart_mid_combat.py`).
- **WriterQueue test pattern:** repos are tested through a live `WriterQueue`
  so the test exercises the same serialized-writer code path production uses.
  All writes go via `wq.execute(...)`; reads use `aiosqlite` directly with
  `PRAGMA journal_mode = WAL`. The bootstrapped fixtures handle queue
  start/stop automatically.
- **Mocking discord.py:** `MagicMock(spec=discord.Interaction)` / `spec=
  discord.Message`. Async methods replaced with `AsyncMock`. No real Discord
  gateway connection is ever opened — `dpytest` is deferred until it supports
  discord.py 2.7+.

## Adversarial sanitizer corpus

The sanitizer test suite is the strongest line of defense against
prompt-injection — if `sanitize_player_input` ever lets a `<|im_start|>`,
`<tool_call>`, or sentinel-breakout through, the rules engine could be tricked
into emitting hallucinated state. The corpus is **YAML-driven** to make it
trivial to add new attack vectors without touching Python.

- **Location:** `src/eldritch_dm/safety/corpus/injection_cases.yaml`
- **Loader:** `tests/safety/test_sanitizer.py::load_corpus()`
- **Driver:** `@pytest.mark.parametrize("case", _CORPUS, ids=lambda c: c["id"])`
- **Floor:** `test_corpus_has_at_least_30` asserts the corpus stays >= 30 cases.

Each case is a dict with `id`, `raw` (or `raw_repeat` for char-repeat payloads),
`speaker`, `user_id`, and an `expect` block. A scenario **passes** when:

1. Returned object is a `SanitizedInput`.
2. `result.truncated` matches `expect.truncated`.
3. `len(result.stripped_tokens) >= expect.min_stripped` — at least N
   attack tokens were stripped.
4. `expect.wrapped_contains` (e.g. `<player_action speaker="Thorin"`)
   appears in `result.wrapped` — sentinels intact.
5. `expect.wrapped_not_contains` / `wrapped_not_contains_ci` — the attack
   payload is NOT present inside the `<player_action>...</player_action>`
   inner body.
6. The `audit_callback` fires exactly once when a strip or truncate happens,
   producing a `SanitizerAuditRow` ready for the `sanitizer_audit` table.

To add a new scenario: append a YAML block with a unique `id` to
`injection_cases.yaml`, re-run `pytest tests/safety/test_sanitizer.py -v`,
and the parametrized test will pick it up automatically (ids show as e.g.
`test_sanitizer_case[chatml-im-start]`).

## Restart-survival drills

EldritchDM's reliability claim is "full resume across bot restarts." The drills
prove it by **killing the orchestrator mid-state and rebuilding from SQLite +
DynamicItem registration alone** — no in-memory cheating.

The canonical pattern is in
**`tests/integration/test_restart_mid_combat.py`** (Phase 4 Plan 03 D-35):

1. **Seed** a `channel_sessions` row in state=COMBAT, four combat
   `persistent_views` rows (Attack/Dodge/EndTurn/CastSpell) with known
   `actor_id` + `round=2`, plus a `combat_conditions` row (in-flight dodge).
2. **Build orchestrator A** and start the per-channel orchestrator task.
3. **Cancel** the task (simulates a crash).
4. **Build a FRESH orchestrator B** — new tasks, new in-memory bookkeeping.
5. **Rehydrate**: re-register DynamicItems and restart the orchestrator for
   the seeded channel.
6. **Assert**:
   - All 4 combat button classes are present in the rehydration class map.
   - The orchestrator task for the channel is running again.
   - The `combat_conditions` row survived (dodge still active).
   - `persistent_views` rows for round 2 are still in the DB.
   - A simulated AttackButton click after restart matches the regex template
     and dispatches via the registered class.

The Phase 2 BOT-08 drill (`tests/bot/test_restart_drill.py`) covers the LOBBY-
state variant. Both drills run in < 5s and are part of the default suite (no
`slow`/`load` marker).

## Load test

`tests/integration/test_8player_load.py` is the COMBAT-08 headline test for
Phase 4 Plan 03. It drives a synthetic 8-combatant fight for 5 rounds with a
**virtual clock** injected into `ChannelRateLimiter`, `ChannelEditBudget`, and
`EmbedCoalescer` — so hours of game-time pressure complete in milliseconds of
wall time.

**Scenario:** 5 rounds × 8 combatants × 4 embed-update events per turn =
**160 update events scheduled**, plus 60 rate-limited mutating calls
(20 PC attack clicks + 40 `next_turn` calls).

**Hard assertions (A–G):**

| ID | Assertion | Plan 03 measured |
|---|---|---|
| A | Coalescer suppresses ≥ 40 % of events; some edits still fire | **81 actual edits from 160 events → 49.4 % suppression** |
| B | No two edits on the same message < 1.0s apart (virtual) | **min delta 1.05s** |
| C | ≤ 5 edits in any rolling 5s window per channel | satisfied |
| D | `ChannelRateLimiter.acquire` deltas ≥ 0.2s | satisfied |
| E | No `database is locked` raised | satisfied (in-memory smoke) |
| F | Wall-clock runtime < 30s | satisfied |
| G | Mocked `Message.edit` never receives a 429 — by construction, B+C are the cadence proof | satisfied |

The test also ships a **negative control**
(`test_negative_control_violates_assertion_c`) that fabricates a 6-edits-in-5s
timeline and asserts the detection logic trips — inverse-truth proof that the
budget-violation check actually bites.

Run it: `RUN_LOAD=1 pytest tests/integration/test_8player_load.py -v -s`
(the `-s` shows the summary block printed by the test).

## CI expectations

No `.github/workflows/` directory exists yet — CI is not wired in this repo.
<!-- VERIFY: project CI policy (which gated suites run on PR vs. main merge) -->

When CI is added, the intended policy (from the plan docs) is:

- **Every commit / PR:** `pytest` (fast suite) + `ruff check` +
  `ruff format --check` + `python -m eldritch_dm.lint.edm001 src/eldritch_dm/bot/`
  + `lint-imports` (import-linter contracts).
- **PR (slow lane):** `RUN_LOAD=1 pytest tests/integration/test_8player_load.py`.
- **Main merge / nightly:** `RUN_STRESS=1 pytest tests/persistence/test_concurrent_writes.py`.

## Pre-commit hooks

Configured in `.pre-commit-config.yaml`:

| Hook | Command | Scope |
|---|---|---|
| `ruff` (with `--fix`) | `astral-sh/ruff-pre-commit v0.9.10` | All Python files |
| `ruff-format` | same repo | All Python files |
| `edm001-defer-discipline` | `python -m eldritch_dm.lint.edm001` | `^src/eldritch_dm/bot/.*\.py$` only |

Install once: `pre-commit install`. Then every commit runs ruff lint + format
and the EDM001 defer-discipline check on any touched `src/eldritch_dm/bot/`
file. EDM001 is **not** run on tests — the `_edm001_corpus/bad/` files
intentionally violate the rule, so the per-file ignore at
`tests/bot/_edm001_corpus/**` (in `pyproject.toml`) also keeps `F821` quiet
for those undefined-name fixtures.
