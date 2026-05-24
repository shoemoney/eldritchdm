# Phase 8 — Deferred Items

## Pre-existing test failures (out of scope per Rule 3 scope boundary)

These 3 failures exist at HEAD~6 (before Phase 8 work) — they are NOT caused
by Plan 08-01 changes:

- `tests/ingest/test_pipeline.py::TestIngestImagePath::test_unsupported_bytes_returns_zero_confidence`
- `tests/integration/test_phase3_smoke.py::test_phase3_happy_path`
- `tests/integration/test_phase3_smoke.py::test_phase3_upload_file_low_confidence_uses_entry_modal`

All three concern the Phase 3 ingest pipeline. Phase 8 does not touch
`src/eldritch_dm/ingest/`. Verified by `git checkout HEAD~6 -- src/ tests/`
+ targeted re-run — failures reproduce on the pre-Phase-8 tree.

Owner: Whichever phase owns ingest hygiene (likely a future cleanup phase).
