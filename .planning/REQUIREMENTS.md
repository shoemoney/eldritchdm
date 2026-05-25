# EldritchDM — Requirements (v1.4 Writer-Queue Reliability)

**Milestone:** v1.4 Writer-Queue Reliability
**Goal:** Fix WRITER-QUEUE-HANG-01 — the two pre-existing pytest hangs (`test_writer_queue_drain_timeout`, `test_close_cleanly_shuts_down`) that v1.3's logging-polluter fix surfaced. Both predate v1.3 (Phase 5 + Phase 6 origin). Once fixed, FLAKE-02's residual phase3_smoke pollution should resolve in the same pass, and the full test suite returns green for the first time since v1.1.
**Total v1.4 requirements:** 3 in 1 category.

---

## v1.4 Requirements

### HANG — Writer-queue shutdown reliability (Phase 15)

- [ ] **HANG-01**: `tests/bot/test_setup_hook.py::test_writer_queue_drain_timeout` passes deterministically in 5 consecutive full-suite runs. Root cause documented (current code blocks on a `queue.get()` or similar that no cancellation can interrupt — needs asyncio.Event-based stop signal in the writer loop). The fix is at the SOURCE in `src/eldritch_dm/persistence/` writer-task code, NOT a test-side hack (no monkeypatching, no time.sleep workarounds).
- [ ] **HANG-02**: `tests/bot/test_bot_lifecycle.py::test_close_cleanly_shuts_down` passes deterministically in 5 consecutive full-suite runs. Same root-cause path as HANG-01 if shared; otherwise documented separately. `pytest-timeout` should NOT be needed to "rescue" — the fix should mean the test completes within its natural deadline.
- [ ] **HANG-03**: FLAKE-02 (carried partial from v1.3) — `tests/integration/test_phase3_smoke.py` passes deterministically in full-suite run. Verified by running full suite 3× consecutively post-fix with zero failures. If the writer-queue fix didn't resolve FLAKE-02, halt and report (the residual is a different bug class than what v1.3 audit hypothesized).

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| HANG-01 | 15 | v1.3 milestone audit surfaced WRITER-QUEUE-HANG-01 |
| HANG-02 | 15 | v1.3 milestone audit surfaced WRITER-QUEUE-HANG-01 (sibling test) |
| HANG-03 | 15 | v1.3 FLAKE-02 carried partial (writer-queue is the suspected downstream cause) |

## Mode Constraints

- Fix at the SOURCE in `src/eldritch_dm/persistence/`, not in test code.
- No `pytest-timeout` workarounds — the goal is tests that complete naturally.
- Preserve existing writer-queue API (callers in `bot.py` / cogs shouldn't have to change unless absolutely necessary).
- Preserve WAL + busy_timeout + single-writer invariants from v1.0 Phase 1.
- All existing writer-queue tests must continue to pass — no regressions in the 873 baseline tests.
