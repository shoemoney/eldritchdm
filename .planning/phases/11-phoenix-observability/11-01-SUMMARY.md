---
phase: 11-phoenix-observability
plan: "01"
subsystem: observability
tags: [otel, phoenix, instrumentation, lazy-import, opt-in]
requires: []
provides:
  - eldritch_dm.observability package
  - traced_decision context manager (eldritch.monster.decision spans)
  - traced_translate context manager (eldritch.ingest.translate spans)
  - init_tracing() lazy OTel setup
affects:
  - src/eldritch_dm/gameplay/smart_monster_driver.py (decoration only)
  - src/eldritch_dm/ingest/translate.py (decoration + channel_id pass-through)
tech-stack:
  added:
    - opentelemetry-api>=1.27,<2.0
    - opentelemetry-sdk>=1.27,<2.0
    - opentelemetry-exporter-otlp-proto-http>=1.27,<2.0
  patterns:
    - Lazy-import gating via _TRACER sentinel + module-local OTel imports inside init_tracing()
    - Explicit span threading (span=kwarg) — no nested spans, no trace.get_current_span()
key-files:
  created:
    - src/eldritch_dm/observability/__init__.py
    - src/eldritch_dm/observability/instrumentation.py
    - src/eldritch_dm/observability/tracer.py
    - tests/observability/__init__.py
    - tests/observability/test_lazy_import.py
    - tests/observability/test_disabled_noop.py
    - tests/observability/test_span_attributes.py
  modified:
    - pyproject.toml (added [project.optional-dependencies] observability group)
    - src/eldritch_dm/gameplay/smart_monster_driver.py (wrapped _choose_target + _pick_target_llm with span instrumentation)
    - src/eldritch_dm/ingest/translate.py (wrapped translate_character_sheet with traced_translate)
decisions:
  - D-65a (sub): "Narration path" in CONTEXT.md means "every AsyncOpenAI call this codebase makes outside the smart driver." dm20 owns true narration internally; ingest is the second AsyncOpenAI call site.
  - D-65b (sub): Two span schemas — eldritch.monster.decision (full 8-attr D-65 schema) and eldritch.ingest.translate (subset). Ingest is NOT a driver decision; do not extend the driver.path enum.
  - D-65c (sub): Optional-deps group is minimal — opentelemetry-api/sdk/exporter-otlp-proto-http. NO opentelemetry-instrumentation-openai (D-66 says hand-roll spans at driver boundary to avoid double-counting).
  - D-65d (sub): Lazy-import canary uses subprocess + full bot tree import. Same-process tests can be polluted by prior init_tracing() runs.
metrics:
  duration: ~30 minutes
  completed: 2026-05-24
---

# Phase 11 Plan 01: OTel instrumentation + span schema — Summary

## One-liner

OpenTelemetry instrumentation as an opt-in optional-deps group with a strict lazy-import invariant: when `OBSERVABILITY_ENABLED` is unset, no `opentelemetry` symbol enters `sys.modules` even after the full bot tree is imported.

## What landed

- New `src/eldritch_dm/observability/` package: three modules, no module-level OTel imports.
- `init_tracing()` lazily wires `TracerProvider` + `OTLPSpanExporter` (HTTP) + `BatchSpanProcessor` only when `OBSERVABILITY_ENABLED` is truthy. Idempotent.
- `traced_decision(monster_id, channel_id, combat_round, driver_path)` context manager — yields a no-op `_NoopSpan` when disabled, a real OTel Span when enabled. Schema enforces D-65.
- `traced_translate(channel_id, model)` context manager — D-65b ingest subset.
- `SmartMonsterDriver._choose_target` opens **exactly one** span per decision, threads it into `_pick_target_llm` as a `span=` kwarg. All eight D-65 attributes are stamped on the same span across every outcome path: cache hit (driver.path=cache), success (driver.path=smart + tokens), timeout (fallback.reason=timeout), generic exception (fallback.reason=generic or rate_limit), refusal (empty content), json_parse failure, hallucinated_id failure.
- `translate_character_sheet` wraps the AsyncOpenAI call in `traced_translate`. Records latency, tokens (defensive against MLX's `usage=None`), and `ingest.parse_error` bool.
- Optional-deps group: `pip install -e ".[observability]"` pulls OTel API + SDK + HTTP exporter (verified against installed 1.42.1).
- Tests:
  - `test_lazy_import.py` — subprocess canary asserting `"opentelemetry" not in sys.modules` after a full bot import tree, even with the no-op context managers invoked.
  - `test_disabled_noop.py` — context managers yield real `_NoopSpan` instances and accept the full set of Span-API calls without raising.
  - `test_span_attributes.py` — in-memory exporter asserts all 8 D-65 attributes land on `eldritch.monster.decision` spans, D-65b subset on `eldritch.ingest.translate` spans, and `init_tracing()` is idempotent when enabled.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Sub-decisions documented in the plan (not changes during execution)

The four D-65a..d sub-decisions were derived during plan reconciliation with the advisor and locked into the PLAN.md before any code was written. They are recorded above for cross-plan visibility.

## Files modified vs. created

- **Created:** 7 files (3 src modules, 4 test modules).
- **Modified:** 3 files (pyproject.toml, smart_monster_driver.py, translate.py). All modifications are pure-decoration — no behavior change in the underlying smart-driver or translate logic, verified by the 28-test smart-driver suite and 83-test ingest suite both staying green.

## Verification

- ruff: clean on all new/modified files.
- import-linter: 7/7 contracts kept (gameplay still cannot import bot/ingest; ingest still cannot import bot/persistence; observability is unrestricted).
- pytest tests/observability/: 8/8 passed (lazy-import + disabled-noop + 5 enabled-mode tests, including idempotent init_tracing).
- pytest tests/gameplay/ -k smart_monster: 28/28 passed (regression baseline for "pure observation layer").
- pytest tests/ingest/: 83/83 passed.
- Full pytest tests/ --ignore=tests/integration: 1013 passed, 1 unrelated pre-existing flaky failure (test_collect_rows_subclass_warning_emitted in tools/backfill — passes in isolation; ordering issue, NOT a Phase 11 regression).

## Threat Flags

None — observability is a pure read-only telemetry export. No new network surface beyond an opt-in OTLP endpoint targeting localhost by default. No auth path changes, no DB-schema changes.

## Self-Check: PASSED

- Created files exist:
  - src/eldritch_dm/observability/__init__.py — FOUND
  - src/eldritch_dm/observability/instrumentation.py — FOUND
  - src/eldritch_dm/observability/tracer.py — FOUND
  - tests/observability/test_lazy_import.py — FOUND
  - tests/observability/test_disabled_noop.py — FOUND
  - tests/observability/test_span_attributes.py — FOUND
- Commits exist on this branch:
  - d042aa8 (pyproject.toml extras) — FOUND
  - 63c8740 (observability skeleton) — FOUND
  - f6fedad (lazy OTel tracer init) — FOUND
  - 48d1f16 (smart driver wrap) — FOUND
  - 97d9cf4 (ingest translate wrap) — FOUND
  - 020e443 (tests) — FOUND
