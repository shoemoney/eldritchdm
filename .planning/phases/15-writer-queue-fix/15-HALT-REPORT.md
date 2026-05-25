---
phase: 15-writer-queue-fix
status: HALTED — CONTEXT.md premise invalidated by empirical evidence
generated: 2026-05-25
generated_by: gsd-execute-phase agent (combined plan+execute mode)
constraint_invoked: "If you cannot achieve green after 3 consecutive runs, halt and report — DO NOT silently mark green"
---

# Phase 15 — HALT REPORT

## Why I am halting

The orchestrator brief asked me to write Plans 15-01/02/03 against CONTEXT.md's
D-101..D-109 (rewrite WriterQueue with `asyncio.Event` + sentinel) and then
execute them.

**Before writing the plans, I reproduced the bugs to ground the work.** What I
found contradicts the CONTEXT.md premise on every load-bearing point:

1. **HANG-01** (`test_writer_queue_drain_timeout`) — **does not reproduce.**
   Passes in isolation (5.6s). Passes in the full suite (104s, 1242 passed).
2. **HANG-02** (`test_close_cleanly_shuts_down`) — **does not reproduce.**
   Passes in isolation and in the full suite.
3. **HANG-03 / FLAKE-02** — **confirmed real, but is not a hang.** Two tests
   fail in the full suite with `AssertionError: view (button) must be included`
   in `tests/integration/test_phase3_smoke.py`. These same tests pass in
   isolation.
4. The existing `src/eldritch_dm/persistence/connection.py:WriterQueue` already
   implements exactly the pattern CONTEXT.md D-102 wants me to add: an
   `asyncio.Queue` with a `None` sentinel, `asyncio.wait_for(self._task, ...)`
   in `stop()` with a 5s timeout, cancel-fallback. The "fix" is already in
   place. Rewriting it would be invented work risking regression of 177
   passing tests.

The CONTEXT.md's locked decisions (D-101 "Fix at SOURCE in persistence/, NOT
in test code") are based on a stale v1.3 audit. Phase 14's logging-polluter
fix likely already neutralized the HANG-01/02 hangs the audit captured.

Per the orchestrator's HARD CONSTRAINT, I am halting and reporting rather
than silently rescoping a 3-plan milestone into a 1-plan one or fabricating
work to comply with stale guidance.

## Empirical evidence

### HANG-01 / HANG-02 — not reproducible

```text
$ uv run pytest tests/bot/test_setup_hook.py::test_writer_queue_drain_timeout -xvs
========================= 1 passed, 1 warning in 5.56s =========================

$ uv run pytest tests/bot/test_bot_lifecycle.py::test_close_cleanly_shuts_down -xvs
========================= 1 passed, 1 warning in 0.17s =========================

$ uv run pytest tests/ --timeout=30 --timeout-method=thread -q   (full suite)
2 failed, 1242 passed, 17 skipped, 83 warnings in 104.26s (0:01:44)
# Note: ZERO hangs. Both HANG-01 and HANG-02 PASS in the full suite.
```

### HANG-03 / FLAKE-02 — confirmed, real failure mode is NOT a hang

```text
FAILED tests/integration/test_phase3_smoke.py::test_phase3_happy_path
FAILED tests/integration/test_phase3_smoke.py::test_phase3_upload_file_low_confidence_uses_entry_modal
```

Both failures have the same root cause: the test patches
`eldritch_dm.bot.cogs.ingest.ingest` with an `AsyncMock`, but the real
`pipeline.ingest` is what runs, which raises `UnavailableOCRBackend(
"No OCR backend available...")` because `ocrmac` is not installed in the
test venv. The cog catches it and the assertion `send_kwargs.get("view")
is not None` fails because the high-confidence branch never runs.

### Bisected polluter

```text
$ pytest tests/persistence/ tests/integration/test_phase3_smoke.py     → 84 passed
$ pytest tests/bot/cogs/      tests/integration/test_phase3_smoke.py   → 94 passed
$ pytest tests/bot/test_restart_drill.py tests/integration/...         → 3 passed
$ pytest tests/bot/test_setup_hook.py    tests/integration/...         → 2 FAILED
$ pytest tests/bot/test_bot_lifecycle.py tests/integration/...         → 2 FAILED

Narrowed to single tests:
$ pytest tests/bot/test_bot_lifecycle.py::test_close_cleanly_shuts_down + phase3 → FAILS
$ pytest tests/bot/test_bot_lifecycle.py::test_setup_hook_initializes_subsystems + phase3 → FAILS
$ pytest tests/bot/test_bot_lifecycle.py::test_setup_hook_failure_is_fatal + phase3       → PASSES
```

The polluters are tests that fully boot the bot via `bot_factory()`
(which runs `setup_hook`, which calls
`await self.load_extension("eldritch_dm.bot.cogs.ingest")`), then close it.
The non-polluter (`test_setup_hook_failure_is_fatal`) mocks `bootstrap`,
which short-circuits before any `load_extension` call.

## Hypothesis (unconfirmed — proven INSUFFICIENT)

Original hypothesis: discord.py's `load_extension` mutates `sys.modules`
in a way that breaks `mock.patch` resolution. Candidate fix: patch at the
source (`eldritch_dm.ingest.pipeline.ingest`) instead of at the cog binding.

**Tested in scratch edit (reverted, not committed):** patching at
`eldritch_dm.ingest.pipeline.ingest` **breaks the test in isolation too**
because the cog's `from eldritch_dm.ingest import ingest` re-export pulls
from `eldritch_dm.ingest.__init__`, not directly from `pipeline`. Neither
patch target works in the polluted case. The fix is more nuanced than the
advisor's initial hypothesis — the next agent needs to investigate further.

## Recommendation

**Rescope Phase 15 to a single plan: "FLAKE-02 closure via test-isolation
fix"** — DO NOT touch `src/eldritch_dm/persistence/`.

Suggested next-agent investigation plan:

1. Add an inline print/assert in the cog's `upload_character_file` callback
   inside a polluted run to confirm whether `ingest` resolves to the
   patched `AsyncMock` or the real function — this pins down whether the
   patch is being applied to the wrong dict.
2. Compare `id(IngestCog.upload_character_file.callback.__globals__)`
   vs `id(sys.modules["eldritch_dm.bot.cogs.ingest"].__dict__)` before
   and after a polluting test. If they diverge, discord.py's extension
   teardown is re-importing the cog module.
3. Three candidate fixes to evaluate:
   - **(a) Patch unload_extension into bot_factory teardown.** `bot.close()`
     does NOT call `unload_extension`; adding it to the `bot_factory`
     fixture (or to `bot.close()` itself) would clean up extension state.
   - **(b) Restructure phase3 smoke to inject the mocked `ingest` via
     dependency injection** instead of `mock.patch`, e.g. constructor
     parameter on `IngestCog`. More invasive but immune to import churn.
   - **(c) Force-reimport the cog module at the start of each phase3 test:**
     `importlib.reload(sys.modules["eldritch_dm.bot.cogs.ingest"])` before
     constructing `IngestCog`. Cheapest but smelly.

## REQUIREMENTS.md status (proposed, NOT applied)

Per the orchestrator brief I am NOT updating REQUIREMENTS.md. Suggested
post-rescope ticks:

- **HANG-01** — tick `[x]` with note "Resolved by Phase 14 logging-polluter
  fix; verified not reproducible at HEAD. No Phase 15 code change required."
- **HANG-02** — same as HANG-01.
- **HANG-03 / FLAKE-02** — LEAVE OPEN. Real bug, requires further
  diagnosis (see Recommendation above).

## Files inspected during diagnosis

- `src/eldritch_dm/persistence/connection.py` (WriterQueue — sentinel already
  implemented at lines 142–171; `stop()` already has `asyncio.wait_for`
  with 5s timeout + cancel-fallback at lines 213–222)
- `src/eldritch_dm/persistence/checkpoint.py`
- `src/eldritch_dm/persistence/__init__.py`
- `src/eldritch_dm/bot/bot.py` (`load_extension` calls at lines 402–410;
  `close()` at lines 452–517)
- `src/eldritch_dm/bot/cogs/ingest.py` (line 50: `from eldritch_dm.ingest
  import ingest`; line 487: call site)
- `src/eldritch_dm/ingest/__init__.py` (re-exports `ingest` from
  `pipeline`)
- `src/eldritch_dm/ingest/pipeline.py` (line 198–202:
  `UnavailableOCRBackend`)
- `src/eldritch_dm/ingest/ocr.py` (line 44: `resolve_ocr_backend()`)
- `tests/conftest.py` (Phase 14 logging reset fixture)
- `tests/bot/conftest.py` (`bot_factory` — no `unload_extension` call)
- `tests/bot/test_bot_lifecycle.py`
- `tests/bot/test_setup_hook.py`
- `tests/integration/test_phase3_smoke.py`

## Working-tree status at halt

Clean. The scratch edit that tested the candidate fix was reverted before
committing. The only new file is this halt report.
