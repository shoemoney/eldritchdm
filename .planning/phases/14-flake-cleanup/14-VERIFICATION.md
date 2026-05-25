---
phase: 14-flake-cleanup
type: verification
generated: 2026-05-25
status: PARTIAL
---

# Phase 14 — Verification Report

## Status

**PARTIAL.** FLAKE-01 and FLAKE-03 fully closed. FLAKE-02 partial (one of two
sub-issues fixed at source; the second diagnosed but mechanism unresolved).
Full-suite-green hard-constraint **NOT verified** due to a pre-existing
writer-queue hang that predates Phase 14 (out of scope; surfaced as new
finding).

## What was verified (PASS)

### FLAKE-01 — fully closed

| Check | Command | Result |
|---|---|---|
| OCR-pipeline test passes in clean `[dev]` venv | `uv run pytest tests/ingest/test_pipeline.py -q` | **14 passed** |
| metrics endpoint tests skip cleanly without `prometheus_client` | `uv run pytest tests/observability/test_metrics_endpoint.py -q` | **3 passed, 4 skipped** |
| `ocrmac` not installed in test venv (confirms skip-gate is actually exercised) | `python -c "import importlib.util; print(importlib.util.find_spec('ocrmac'))"` | `None` |
| `prometheus_client` not installed in test venv | `python -c "import importlib.util; print(importlib.util.find_spec('prometheus_client'))"` | `None` |

### FLAKE-03 — fully closed

| Check | Command | Result |
|---|---|---|
| Backfill script applied | `python scripts/audit/backfill_summary_frontmatter.py --apply` | `APPLIED 14/14 SUMMARY files` |
| All 14 SUMMARYs have underscore form | `grep "^requirements_completed:" .planning/phases/*/*-SUMMARY.md \| wc -l` | **14** |
| No legacy hyphen form remains | `grep "^requirements-completed:" .planning/phases/*/*-SUMMARY.md \| wc -l` | **0** |
| CI gate passes | `bash scripts/ci/check_summary_frontmatter.sh` | `OK: 14 SUMMARY files have requirements_completed: frontmatter` (exit 0) |
| Re-running script is no-op | `python scripts/audit/backfill_summary_frontmatter.py --apply` | `APPLIED 0/14 SUMMARY files` after fresh re-run |

### FLAKE-02 — partial (backfill_pc_classes polluter resolved)

| Check | Command | Result |
|---|---|---|
| Pair-wise polluter+victim test passes | `pytest tests/persistence/test_bootstrap.py::TestBootstrapMainRuns tests/tools/test_backfill_pc_classes.py::test_collect_rows_subclass_warning_emitted` | **2 passed** (was 1 failed before fix) |
| `test_collect_rows_subclass_warning_emitted` no longer appears in targeted-suite FAILED list | targeted suite run | confirmed (1 fewer fail than baseline) |

### Lint

| Check | Command | Result |
|---|---|---|
| ruff | `uv run ruff check .` | `All checks passed!` |

## What was NOT verified (BLOCKED)

### Hard constraint — full-suite green, 3 consecutive runs

**Cannot be verified** because two pre-existing tests hang at ~50% reproduction
rate (0% CPU, sqlite file locks held) on every full-suite run:

1. `tests/bot/test_setup_hook.py::test_writer_queue_drain_timeout`
2. `tests/bot/test_bot_lifecycle.py::test_close_cleanly_shuts_down`

These tests:
- Hang in isolation too (`uv run pytest tests/bot/test_setup_hook.py::test_writer_queue_drain_timeout`
  reproduces at the same rate)
- Cannot be killed by `pytest-timeout` with either `--timeout-method=signal`
  or `--timeout-method=thread` — the hang is at a C-level sqlite/threading
  boundary that signal-based timeouts do not interrupt
- Predate Phase 14:
  - `test_setup_hook.py` — last touched commit `eb4e0f7` (Phase 5)
  - `test_bot_lifecycle.py` — last touched commit `d6e87c4` (Phase 6)

**Workaround used:** All targeted-suite verification runs added
`--ignore=tests/bot/test_setup_hook.py --ignore=tests/bot/test_bot_lifecycle.py`.
Under that workaround:

```
uv run pytest tests/ \
  --ignore=tests/bot/test_setup_hook.py \
  --ignore=tests/bot/test_bot_lifecycle.py \
  -q --tb=no --timeout=30 --timeout-method=signal -p no:cacheprovider
```
→ **2 failed, 1222 passed, 17 skipped, 83 warnings in 95.33s**

The 2 remaining failures are both `test_phase3_smoke.py` — see Phase 14 Plan 01
SUMMARY Known Limitations.

### Partial — FLAKE-02 `test_phase3_smoke` pollution

Polluter located (`test_cold_start_e2e`). Mechanism unresolved after ~3h
investigation. See `.planning/phases/14-flake-cleanup/14-01-SUMMARY.md`
Known Limitations §1 for the diagnostic trail and suggested next steps.

## Baseline → final delta

| Metric | Baseline (pre-Phase-14) | Final (post-Phase-14) | Δ |
|---|---|---|---|
| Targeted-suite failures | 8 | 2 | **−6 (75% reduction)** |
| OCR-related failures in `[dev]` venv | 5 | 0 | **−5 (FLAKE-01 fully closed)** |
| `test_collect_rows_subclass_warning_emitted` failures | 1 | 0 | **−1 (FLAKE-02 polluter #1 fixed)** |
| `test_phase3_smoke` failures | 2 | 2 | **0 (FLAKE-02 polluter #2 unresolved)** |
| SUMMARYs with `requirements_completed:` frontmatter | 0 | 14 | **+14 (FLAKE-03 fully closed)** |

## New findings (surfaced for next milestone)

### NEW-01 — Pre-existing writer-queue hang (suggested REQ-ID: `WRITER-QUEUE-HANG-01`)

`tests/bot/test_setup_hook.py::test_writer_queue_drain_timeout` and
`tests/bot/test_bot_lifecycle.py::test_close_cleanly_shuts_down` hang at
~50% rate, both in isolation and in suite. Sometimes complete in <1s,
sometimes block at 0% CPU holding sqlite file locks indefinitely. Likely
an aiosqlite/threading race in WriterQueue teardown. Out of scope per
advisor guidance — should be its own requirement in the next milestone.

### NEW-02 — `test_phase3_smoke` pollution mechanism (suggested REQ-ID: `WRITER-QUEUE-FLAKE-02` or extend FLAKE-02)

Polluter `test_cold_start_e2e` causes `test_phase3_smoke`'s
`with patch("eldritch_dm.bot.cogs.ingest.ingest", ...)` to become a no-op,
making the real pipeline run and raise `UnavailableOCRBackend`. Mechanism
unresolved — diagnostic next-step suggestions in Plan 01 SUMMARY.

## Commits this phase

| Hash | Subject |
|---|---|
| `b9be05e` | `docs(14): write Phase 14 plan files (14-01, 14-02)` |
| `b6ceb26` | `test(14-01): fix test_unsupported_bytes to use application/octet-stream (FLAKE-01)` |
| `96b2794` | `test(14-01): skip metrics endpoint tests when prometheus_client missing (FLAKE-01)` |
| `494b709` | `feat(14-02): add SUMMARY.md requirements_completed backfill script` |
| `c339daa` | `docs(14-02): backfill requirements_completed: frontmatter on all 14 v1.1+v1.2 SUMMARYs (FLAKE-03)` |
| `d6a8d13` | `ci(14-02): add CI gate scripts/ci/check_summary_frontmatter.sh (FLAKE-03)` |
| `ea15cb8` | `test(14-01): reset structlog + stdlib logging state after each test (FLAKE-02 partial)` |
