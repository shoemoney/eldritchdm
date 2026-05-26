<!-- generated-by: gsd-doc-writer -->
# Testing

EldritchDM tests are the contract that lets us claim the bot is
**mechanically honest**. The integrity rule ("LLM never computes math")
only holds if rules, persistence, and Discord plumbing are independently
verified — so the suite is structured to test each subsystem in
isolation, then in integration, then under restart, load, and (v1.9+)
performance regression.

At v1.11 the suite contains **~1350 `def test_*` functions across 4
test categories** — unit, integration, perf (v1.9), and eval (v1.2).
Default `pytest` runs everything **not** gated by `RUN_STRESS`,
`RUN_LOAD`, or `RUN_INTEGRATION`.

## Test framework and setup

- **Framework:** `pytest >=8.0,<9.0` with `pytest-asyncio >=0.23,<1.0`
  (declared in `pyproject.toml [project.optional-dependencies].dev`).
- **Async mode:** `asyncio_mode = "auto"` in `[tool.pytest.ini_options]`
  — every `async def test_*` is auto-collected; no per-test
  `@pytest.mark.asyncio` decorator required.
- **Coverage:** `pytest-cov >=5.0,<6.0`. CI runs
  `pytest --cov=eldritch_dm --cov-report=term --cov-report=xml:coverage.xml`
  and uploads the XML as a Linux-only artifact.
- **HTTP mocking:** `respx >=0.21,<1.0` for mocking `httpx` calls (every
  oMLX/MCP test is offline by default).
- **Mocking:** `pytest-mock >=3.12,<4.0` plus the stdlib `unittest.mock`
  (`AsyncMock`, `MagicMock`).
- **Snapshots:** `syrupy >=4.6,<5.0` for golden output.
- **Setup:** `uv pip install -e '.[dev]'`. All tests use a fresh
  ephemeral SQLite DB in `tmp_path`; no global DB state to reset.

## Test categories

The four test categories map to the four `tests/` subtrees that have
their own gating logic.

### 1. Unit tests (the bulk of the suite)

Live alongside the source-side firewall:

```
tests/
├── config/                  ── Settings validation, IngestConfig resolution
├── bot/                     ── Views, DynamicItems, modals, cogs, coalescer
│   ├── _edm001_corpus/      ── AST corpus for the EDM001 lint rule
│   ├── cogs/                ── per-cog suites (lobby, ingest, exploration, combat, diagnostics)
│   └── test_restart_drill.py    ── LOBBY restart drill (RUN_INTEGRATION=1)
├── gameplay/                ── exploration batch, party mode, rate-limit, smart driver,
│                                monster memory, eligibility loader, AOE/multi-target
├── ingest/                  ── PDF / OCR / translate pipeline
├── mcp/                     ── MCPClient + MCPCache (respx-mocked)
├── observability/           ── tracer, span buffer, KPI, alerts, cost, degraded mode,
│                                narrcache, metrics endpoint
├── persistence/             ── repos, WriterQueue, bootstrap, checkpoint, character cache
│                                conftest.py: bootstrapped_db + bootstrapped_db_with_repos
└── safety/                  ── Sanitizer + YAML-driven adversarial corpus
```

The structure mirrors the import-linter firewall — each subsystem's
tests sit in their own directory.

### 2. Integration tests (`tests/integration/`)

Cross-subsystem end-to-end flows. The notable ones:

| File | What it covers | Gate |
|---|---|---|
| `test_phase1_smoke.py` / `test_phase3_smoke.py` | End-to-end smokes of Phase 1 (MCP+state) and Phase 3 (Discord scaffold) | default |
| `test_combat_flow.py` | Combat happy-path across MCP → persistence → embed coalescer | default |
| `test_restart_mid_combat.py` | D-35 — kill orchestrator mid-COMBAT, rebuild from SQLite + DynamicItem reg | default |
| `test_riposte_restart.py` / `test_riposte_smoke.py` | Phase 5 Riposte UI + sweeper survival | default |
| `test_lobby_to_exploration_flow.py` | LOBBY → EXPLORATION transition | default |
| `test_cold_start_e2e.py` | v1.1 G-1 regression guard — fails at v1.0 commit `7d307a1`, passes on main | default |
| `test_circuit_open_warning.py` | DM-offline debouncer + circuit-open warning surface | default |
| `test_sanitizer_audit_persistence.py` | Sanitizer audit rows round-trip through the WriterQueue | default |
| `test_degraded_mode.py` | Phase 13 degraded-mode auto-trip with hysteresis | default |
| `test_observability_smoke.py` | OTel tracer + instrumentation smoke (no exporter required) | default |
| `test_multi_channel_stress.py` | Phase 25 (v1.8) — 4-channel concurrent-session stress (~0.27s wall) | `RUN_STRESS=1` |
| `test_8player_load.py` | Phase 4 Plan 03 (COMBAT-08) — 8-combatant × 5-round virtual-clock load | `RUN_LOAD=1` |

### 3. Performance tests (`tests/perf/`, v1.9+)

Phase 27 perf-profiler + Phase 28 baseline diff. All gated by
`RUN_STRESS=1` (the profiler self-check is slow).

| File | Purpose |
|---|---|
| `test_perf_baseline_cli.py` | `eldritch-dm-perf-baseline` argparse + exit-code surface |
| `test_perf_baseline_diff.py` | Baseline diff math (within tolerance / >+10% warn / >+25% critical) |
| `test_perf_baseline_smoke.py` | Profiler smoke; emits a fresh JSON report |
| `test_profiler_self_check.py` | RUN_STRESS gate; full profiler against `tests/integration/test_phase1_smoke.py` flow |

The committed baseline lives at
`.planning/perf-baseline-v1.9.0.json`. See
[`docs/PERFORMANCE.md`](./PERFORMANCE.md) for per-operation budgets +
WARN (110%) / FAIL (125%) thresholds.

### 4. Eval tests (`tests/eval/`, v1.2+)

Phase 12 LLM-as-judge tactical scoring. The runner itself is hermetic —
no real LLM calls in unit tests; `TacticalJudge` is mocked.

| File | Purpose |
|---|---|
| `test_corpus_validation.py` | Asserts the 50-scenario corpus (`tests/eval/dataset/`) round-trips through `ScenarioEntry` pydantic |
| `test_judge_prompt.py` | Versioned prompt loader (SemVer header) |
| `test_judge_verdict.py` | `JudgeVerdict` schema + dimension-mean validator (D-73) |
| `test_tactical_judge.py` | `TacticalJudge.score(...)` happy path + parse-error fallback |
| `test_scenarios.py` | JSONL scenario streaming loader |
| `test_aggregator.py` / `test_reporter.py` | JSON + Markdown reports |
| `test_runner.py` / `test_cli_args.py` / `test_cli_smoke.py` | `eldritch-dm-eval` end-to-end |
| `test_narration_gate_corpus.py` | Phase 18 NarrCacheGate 50-scenario classification corpus |

## How to run

```bash
# Fast suite (default): everything NOT gated by an env var
pytest

# With coverage (matches CI)
pytest --cov=eldritch_dm --cov-report=term --cov-report=xml:coverage.xml

# Single subsystem
pytest tests/persistence
pytest tests/safety/test_sanitizer.py
pytest tests/eval/

# Single test
pytest tests/integration/test_restart_mid_combat.py::test_restart_mid_combat_survives

# 8-player combat load test (gated; see Load test below)
RUN_LOAD=1 pytest tests/integration/test_8player_load.py -v -s

# 4-channel concurrent-session stress test (v1.8)
RUN_STRESS=1 pytest tests/integration/test_multi_channel_stress.py -v

# Perf-profiler self-check (v1.9)
RUN_STRESS=1 pytest tests/perf/ -v

# LOBBY restart drill (DB I/O)
RUN_INTEGRATION=1 pytest tests/bot/test_restart_drill.py -v

# Everything, including all gated suites
RUN_LOAD=1 RUN_STRESS=1 RUN_INTEGRATION=1 pytest -v
```

## Env-var gates

Gating is implemented via `pytest.mark.skipif(not os.environ.get(...))`
on each gated test, not by deselecting markers — so a plain `pytest`
always skips the right set without `-m` flags.

| Env var | Skipped tests | Why |
|---|---|---|
| `RUN_STRESS=1` | Multi-channel concurrent-session stress, perf-profiler self-check | Wall-clock cost; flaky on small runners |
| `RUN_LOAD=1` | 8-player combat load test | Virtual-clock heavy test; ~30s |
| `RUN_INTEGRATION=1` | LOBBY restart drill | DB I/O slow on small runners |

Pytest markers declared in `[tool.pytest.ini_options].markers`:

| Marker | Meaning |
|---|---|
| `slow` | Long-running / stress-style tests. |
| `load` | The 8-player combat load test. |

To force-exclude even when env vars are set:
`pytest -m "not slow and not load"`.

## OCR + observability skip-gates (Phase 14 / FLAKE-01, v1.3)

The default suite installs `[dev]` only — without `[mac-ocr]`,
`[linux-ocr]`, or `[observability]`. Tests that depend on those modules
self-skip via `importorskip`:

- OCR tests in `tests/ingest/test_ocr.py` skip cleanly when neither
  `ocrmac` nor `easyocr` is importable.
- `prometheus_client` tests in `tests/observability/test_metrics_endpoint.py`
  skip when the `[observability]` extras are absent.
- OTel tracer tests likewise skip without the OTel SDK.

This is what allows the cross-platform CI matrix (v1.7) Linux runner to
install `[dev]` only and still get a clean GREEN suite — the Linux
runner is precisely what verifies the skip-gates work.

## Async test patterns

- `asyncio_mode = "auto"` — every `async def test_*` runs without extra
  decoration.
- **Fixtures** (all `@pytest_asyncio.fixture`):
  - `tmp_env` (root `conftest.py`) — sets `DISCORD_TOKEN` and
    `ELDRITCH_DB_PATH`, clears the `get_settings()` LRU cache.
  - `bootstrapped_db` (in `tests/persistence/conftest.py`) — bootstraps
    a fresh on-disk SQLite + live `WriterQueue`.
  - `bootstrapped_db_with_repos` — same, plus ChannelSession,
    PersistentView, RiposteTimer, SanitizerAudit, PcClasses repos and a
    `SessionLocks` instance.
- **WriterQueue test pattern:** repos are tested through a live
  `WriterQueue` so the test exercises the same serialized-writer code
  path production uses.
- **Mocking discord.py:** `MagicMock(spec=discord.Interaction)` / `spec=
  discord.Message`. Async methods replaced with `AsyncMock`. No real
  Discord gateway connection is ever opened.

## Adversarial sanitizer corpus

`src/eldritch_dm/safety/corpus/injection_cases.yaml` is the
prompt-injection contract. The driver
(`tests/safety/test_sanitizer.py::load_corpus()`) parametrizes the test
function with every case; `test_corpus_has_at_least_30` asserts the
corpus stays ≥ 30 cases.

Each case has `id`, `raw` (or `raw_repeat` for char-repeat payloads),
`speaker`, `user_id`, and an `expect` block. A scenario passes when:

1. Returned object is a `SanitizedInput`.
2. `result.truncated` matches `expect.truncated`.
3. `len(result.stripped_tokens) >= expect.min_stripped`.
4. `expect.wrapped_contains` appears in `result.wrapped`.
5. `expect.wrapped_not_contains` / `_not_contains_ci` — the attack
   payload is NOT present inside the `<player_action>…</player_action>`
   body.
6. The `audit_callback` fires exactly once when a strip or truncate
   happens, producing a `SanitizerAuditRow`.

## Restart-survival drills

EldritchDM's reliability claim is "full resume across bot restarts."
Two drills prove it by killing the orchestrator mid-state and rebuilding
from SQLite + DynamicItem registration alone:

- `tests/bot/test_restart_drill.py` — Phase 2 BOT-08, LOBBY-state variant
  (gated `RUN_INTEGRATION=1`).
- `tests/integration/test_restart_mid_combat.py` — Phase 4 Plan 03 D-35,
  COMBAT-state variant. Default-suite (no gate).

The pattern: seed `channel_sessions` + `persistent_views` rows, build
orchestrator A, cancel it, build a FRESH orchestrator B, rehydrate, and
assert that DynamicItem regex routing still dispatches a simulated
click. The Phase 21 monster-memory persistence opt-in (v1.6) extends
this contract — `MONSTER_MEMORY_PERSIST=true` makes
`damage_dealt_by` / `concentrating_on` / `marked_dangerous` survive
restarts too.

## Load test

`tests/integration/test_8player_load.py` is the COMBAT-08 headline test
for Phase 4 Plan 03. 5 rounds × 8 combatants × 4 embed-update events
per turn = **160 update events scheduled**, plus 60 rate-limited
mutating calls. Hard assertions (A–G) cover suppression rate, min
edit-delta per message, per-channel edit-budget, rate-limiter delta,
no-`database is locked`, wall-clock budget, and 429-free `Message.edit`
mocks. A negative control
(`test_negative_control_violates_assertion_c`) fabricates a 6-edits-in-5s
timeline and asserts the detection logic trips.

The Phase 25 (v1.8) **4-channel multi-channel stress** test
(`tests/integration/test_multi_channel_stress.py`) closes v1.0's oldest
open Blockers/Concerns item — concurrent multi-campaign sessions in one
process. Five D-195 assertions all pass; no architectural bugs
surfaced.

## CI expectations

`.github/workflows/ci.yml` (Phase 24, expanded over v1.7+) runs:

| Step | Where | Notes |
|---|---|---|
| `ruff check src/ tests/ run.py` | macOS + Linux | Lint |
| `lint-imports` | macOS + Linux | 8 import-linter contracts |
| `pytest tests/ -q --cov=eldritch_dm --cov-report=term --cov-report=xml:coverage.xml` | macOS + Linux | Default suite + coverage XML (Linux uploads artifact) |
| `scripts/ci/check_safe_yaml.sh` | Linux only | T-08-01 yaml.safe_load gate |
| `scripts/ci/check_summary_frontmatter.sh` | Linux only | Phase 14 SUMMARY frontmatter gate |
| `extras-mac` informational job | macOS | Installs `[dev,mac-ocr,observability]`, `continue-on-error: true` |

`.github/workflows/perf.yml` (v1.9 / Phase 28) runs
`eldritch-dm-perf-baseline` against the committed v1.9.0 baseline JSON
weekly + on `[perf]`-tagged pushes; informational, never release-blocking.

The gated suites (`RUN_LOAD=1`, `RUN_STRESS=1`, `RUN_INTEGRATION=1`) are
**not** invoked by the default CI matrix. Operators can wire them into
their own runners as a nightly job.

## Pre-commit hooks

Configured in `.pre-commit-config.yaml`:

| Hook | Command | Scope |
|---|---|---|
| `ruff` (with `--fix`) | `astral-sh/ruff-pre-commit v0.9.10` | All Python files |
| `ruff-format` | same repo | All Python files |
| `edm001-defer-discipline` | `python -m eldritch_dm.lint.edm001` | `^src/eldritch_dm/bot/.*\.py$` only |
| `yaml-safe-load-only` (T-08-01) | `bash scripts/ci/check_safe_yaml.sh` | always_run |

Install once: `pre-commit install`. The corpus at
`tests/bot/_edm001_corpus/bad/` intentionally violates the rule, so the
per-file ignore at `tests/bot/_edm001_corpus/**` (in `pyproject.toml`)
keeps `F821` quiet for those undefined-name fixtures.

## Cross-references

- [DEVELOPMENT.md](./DEVELOPMENT.md) — local setup + dependency groups +
  console scripts.
- [CONFIGURATION.md](./CONFIGURATION.md) — env-var reference (including
  the test gates).
- [PERFORMANCE.md](./PERFORMANCE.md) — v1.9 baseline + budget table.
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) — "Pytest hangs" + "OCR
  tests are skipping" entries.
