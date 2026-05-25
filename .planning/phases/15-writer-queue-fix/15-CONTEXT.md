---
phase: 15-writer-queue-fix
milestone: v1.4
generated: 2026-05-25
mode: auto-generated (autonomous-flow, discuss skipped per 'confirmed continue')
source_requirements:
  - HANG-01 (test_writer_queue_drain_timeout)
  - HANG-02 (test_close_cleanly_shuts_down)
  - HANG-03 (FLAKE-02 residual — phase3_smoke pollution)
source_design:
  - .planning/v1.3-MILESTONE-AUDIT.md (where WRITER-QUEUE-HANG-01 was surfaced)
  - .planning/phases/14-flake-cleanup/14-01-SUMMARY.md (Known Limitations section)
---

# Phase 15 — Writer-queue shutdown rewrite (CONTEXT)

## Mission

Fix the two pre-existing pytest hangs that v1.3's logging-polluter fix
surfaced. The bot's writer-queue shutdown path blocks on something that
`pytest-timeout` can't kill (C-level thread boundary). Rewrite the
shutdown to be cleanly cancellable via an asyncio.Event-based stop
signal. Once done, FLAKE-02 should resolve in the same pass.

## Locked Decisions (autonomous)

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-101** | **Fix at SOURCE in `src/eldritch_dm/persistence/`** (likely `connection.py` or `__init__.py`'s writer-task setup), NOT in test code. No `monkeypatch.setattr` workarounds, no `pytest-timeout` rescues. | v1.3 audit was explicit: the writer-queue is a real production-path bug; tests are the symptom, not the disease |
| **D-102** | **Shutdown contract**: `WriterQueue.stop()` becomes cleanly cancellable. New asyncio.Event `_stop_event` is checked in the writer-task's main loop between `queue.get()` calls. `stop()` sets the event, sends a sentinel value through the queue (to unblock the `get()`), and awaits the task completion with a default 5s timeout. After timeout: log + cancel. | The hang is almost certainly a blocking `queue.get()` with no cancellation — sentinel-pattern is the canonical asyncio fix |
| **D-103** | **Preserve existing public API**: `WriterQueue.put(stmt, params)` + `WriterQueue.stop()` + `WriterQueue.start()` keep their signatures. Callers in `bot.py` / cogs / repos shouldn't have to change. Internal refactor only. | v1.0 Phase 1 had ~177 tests covering this surface; minimize blast radius |
| **D-104** | **Preserve invariants**: single-writer task, BEGIN IMMEDIATE per write, WAL mode, busy_timeout. v1.0's REL-01 contract from MCP-01..03 must not regress. | The whole point of v1.0's persistence design — don't break the foundation |
| **D-105** | **Plan-01 = characterization test** first. Write a test that reliably reproduces the hang (use `pytest-timeout` + thread method for SAFETY against re-hanging the suite). Mark with `@pytest.mark.timeout(10, method="thread")`. The hang itself is the bug we're fixing; the characterization test gives us a green→red→green proof. | Don't fix what you can't reproduce; characterization test is also the regression guard |
| **D-106** | **Plan-02 = the actual fix**. Rewrite writer-task with asyncio.Event + sentinel-value queue protocol. All existing 177 Phase-1 writer-queue tests must still pass. | Core of the milestone |
| **D-107** | **Plan-03 = full-suite verification + FLAKE-02 closure**. Run full suite 3x consecutively. If all green, FLAKE-02 is closed and `HANG-03` ticks. If phase3_smoke still flakes, halt + report (the residual is a third bug we haven't found yet). | HANG-03 is conditional on the fix actually fixing the downstream symptom |
| **D-108** | **3 plans matching ROADMAP**:<br>15-01: Characterization test (red marker)<br>15-02: Fix + green characterization<br>15-03: Full-suite green + FLAKE-02 closure | ROADMAP plans section |
| **D-109** | **Investigation entry points** (give the executor a head start):<br>- `src/eldritch_dm/persistence/connection.py` (likely WriterQueue impl)<br>- `src/eldritch_dm/persistence/__init__.py` (writer-task lifecycle hooks)<br>- `src/eldritch_dm/persistence/checkpoint.py` (might also have a queue)<br>- `tests/bot/test_setup_hook.py:316` `test_writer_queue_drain_timeout`<br>- `tests/bot/test_bot_lifecycle.py:75` `test_close_cleanly_shuts_down`<br>- v1.0 Phase 1 Plan 01 SUMMARY for the original writer-queue design context | The agent saves tokens not re-discovering the surface |

## Implementation Sketch

**Plan 01 (15-01-PLAN.md) — Reproduce + characterize:**
1. Read existing writer-queue code (likely `persistence/connection.py`)
2. Write isolated test that reproduces hang (will need `@pytest.mark.timeout(10, method="thread")`)
3. Document the EXACT sequence that hangs (probably: `WriterQueue.start()` → enqueue some writes → `WriterQueue.stop()` with no drain completion path)
4. Commit RED (test fails / times out) as proof-of-bug

**Plan 02 (15-02-PLAN.md) — Cancellable shutdown:**
1. Add `_stop_event: asyncio.Event` to WriterQueue
2. Writer-task loop checks `_stop_event.is_set()` between `queue.get()` calls (use `asyncio.wait_for(queue.get(), timeout=0.1)` with TimeoutError swallow, OR `asyncio.wait([queue_get_task, stop_event_wait_task], return_when=FIRST_COMPLETED)`)
3. `stop()` method: `_stop_event.set()`, put sentinel `None` in queue to unblock pending `get()`, await `_task` with 5s timeout, cancel if needed
4. Run characterization test from Plan 01 — should now GREEN
5. Run all 177 Phase-1 writer-queue tests — must still pass

**Plan 03 (15-03-PLAN.md) — Full-suite green + FLAKE-02:**
1. Run `uv run pytest tests/` 3 consecutive times
2. If all green: tick HANG-01, HANG-02, HANG-03 in REQUIREMENTS.md; also tick FLAKE-02 in `milestones/v1.3-REQUIREMENTS.md` (back-update) with reference to Phase 15
3. Commit closure docs (15-01/02/03-SUMMARY.md + 15-VERIFICATION.md)
4. If any flake remains: halt + report the new bug

## Success Criteria (from ROADMAP)

1. test_writer_queue_drain_timeout passes 5× consecutive full-suite runs
2. test_close_cleanly_shuts_down passes 5× consecutive full-suite runs
3. test_phase3_smoke passes 3× consecutive full-suite runs
4. Full suite green (0 failures; skips OK)
5. No regression in 873-test baseline
6. ruff + lint-imports clean

## Deferred (post-v1.4)

- Generalize the asyncio.Event-based shutdown pattern into a reusable mixin (could simplify Phase 13's DegradedModeState similar pattern) — v1.5+
- Replace asyncio.Queue with a smaller bounded buffer (current size is unbounded) — perf optimization, not v1.4 scope
- Add metrics: writer-queue depth gauge to the Phase 11 OTel surface — could be a v1.5 cache-arch tie-in
