---
phase: 09-pc-classes-backfill
milestone: v1.1
generated: 2026-05-24
mode: auto-generated (autonomous-flow, discuss skipped per "go with recommendations")
source_requirements:
  - TD-3 (silent no-Riposte-fires gap from v1.0 audit)
  - HOMEBREW-01 follow-through (Phase 8 ships loader; backfill populates the data the loader consumes)
---

# Phase 9 — pc_classes Ingest-Backfill Script (CONTEXT)

## Mission

Give self-hosters upgrading v1.0 → v1.1 a one-shot CLI tool that populates the
local `pc_classes` table from their existing dm20 characters. Closes TD-3 (silent
no-Riposte-fires gap) — without backfill, Phase 8's eligibility loader sees no
class data for legacy chars and Riposte never fires.

## Locked Decisions (autonomous)

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-41** | **CLI entry: `eldritch-dm-backfill-pc-classes`** via `[project.scripts]`, exposed on PATH after `pip install -e .` | ROADMAP success criterion 1 |
| **D-42** | **Reuse existing `MCPClient` + circuit breaker** — no new HTTP, no new auth flow | ROADMAP success criterion 2; aligns with Phase 7's circuit-decorator pattern |
| **D-43** | **`--dry-run` opens SQLite read-only** (`mode=ro` URI), making writes impossible at the driver level. `--force` re-processes already-populated rows. `--help` documents both | ROADMAP success criterion 3; defensive default |
| **D-44** | **Exit codes**: 0=success, 1=user error (bad args, dm20 unreachable), 2=partial (some chars failed, others succeeded), 3=fatal (DB locked, schema drift) | Operational tooling convention; lets CI/wrappers branch |
| **D-45** | **Idempotent default behavior**: by default skip rows already in `pc_classes`. `--force` is the explicit re-process flag | Safe to re-run without `--dry-run`; matches "one-shot upgrade tool" framing |
| **D-46** | **Use `structlog` (already in stack) with bound `character_id`** for per-row trace; stdout summary table at end | Phase 7 used structlog with bound context — same pattern |
| **D-47** | **Module location**: `src/eldritch_dm/tools/backfill_pc_classes.py` (new `tools/` package); tests at `tests/tools/test_backfill_pc_classes.py` | Avoid polluting `bot/` or `gameplay/`; standalone CLI tool |
| **D-48** | **Connect to dm20 via env: `DM20_MCP_URL`** (already used by bot); document fallback to `http://localhost:7777` if unset, matching MCPClient defaults | Operator already has this configured for normal bot operation |
| **D-49** | **Mock dm20 in tests via `respx`** (already in dev deps from PRD); fixture characters cover Fighter/Battle-Master, Rogue/Swashbuckler, and a non-eligible class | Phase 8 introduced PyYAML + fixtures; this mirrors that pattern |

## Implementation Plan Sketch

Single PLAN with ~4 tasks:

1. **Tools package + CLI scaffold** — `src/eldritch_dm/tools/__init__.py`, `backfill_pc_classes.py` with argparse (--dry-run, --force, --help), `[project.scripts]` entry, smoke import test
2. **dm20 fetch loop** — reuse `MCPClient`, paginate characters, extract `class` + `subclass` via existing dm20 char schema, normalize with `gameplay.normalize.normalize` (the Phase 8 helper)
3. **SQLite upsert (or read-only) path** — write to `pc_classes` via `PCClassesRepo.upsert` (existing Phase 8 repo); dry-run uses `sqlite3.connect("file:path?mode=ro", uri=True)` and short-circuits writes
4. **Tests + docs** — unit tests for arg parsing + dry-run no-write guarantee + force semantics; integration test with respx-mocked dm20; INSTALL.md section explaining when to run the tool (upgrade scenario)

## Deferred (post-v1.1)

- Resume from interruption (checkpoint file) — TD-3 doesn't require it; one-shot tool can just be re-run
- Concurrent dm20 fetch (asyncio.gather) — small character counts make this unnecessary
- Per-character report file emission — stdout summary is enough for v1.1
- Multi-installation backfill (one bot serving N dm20 instances) — single-tenant assumption holds for v1.1

## Success Criteria (from ROADMAP)

1. `pip install -e .` exposes `eldritch-dm-backfill-pc-classes` on PATH
2. Script reuses MCPClient + circuit breaker; no new HTTP code
3. `--dry-run` opens SQLite read-only; `--force` reprocesses; `--help` documents
4. Test suite passes; new tests cover dry-run, force, idempotency, and dm20-unreachable error paths
5. INSTALL.md documents the upgrade flow
