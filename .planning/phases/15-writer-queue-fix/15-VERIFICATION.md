---
phase: 15
generated: 2026-05-25
status: GREEN
---

# Phase 15 — Verification Report

All three required verification runs are GREEN. Full suite verified GREEN twice consecutively. No `--no-verify`, no `pytest-timeout`, no test-skip workarounds.

## Run 1 — Polluters → victim

```bash
uv run pytest tests/bot/test_setup_hook.py \
              tests/bot/test_bot_lifecycle.py \
              tests/integration/test_phase3_smoke.py -q
```

Result:
```
.......................                                                  [100%]
23 passed, 1 warning in 5.43s
```

Pre-fix this run produced `2 failed, 21 passed, 1 warning in 5.51s` (`test_phase3_happy_path` and `test_phase3_upload_file_low_confidence_uses_entry_modal`, both with `AssertionError: view (button) must be included` downstream of `UnavailableOCRBackend`).

## Run 2 — Full `tests/bot/`

```bash
uv run pytest tests/bot/ -q
```

Result:
```
373 passed, 5 skipped, 78 warnings in 10.16s
```

No regressions in the bot suite from the fixture rewrite.

## Run 3 — Full suite, 2 consecutive

### Run 3a
```bash
uv run pytest tests/ -q
```

Result:
```
1244 passed, 17 skipped, 83 warnings in 99.98s (0:01:39)
```

### Run 3b
```bash
uv run pytest tests/ -q
```

Result:
```
1244 passed, 17 skipped, 83 warnings in 100.54s (0:01:40)
```

Pre-fix the full suite consistently produced `2 failed, 1242 passed, 17 skipped, 83 warnings in ~104s` (the same two phase3 tests).

## Lint

```bash
uv run ruff check tests/bot/conftest.py tests/conftest.py
```

Result:
```
All checks passed!
```

## Mechanism evidence — inline diagnostic (not retained in tree)

A throwaway diagnostic test (`tests/bot/test_repro_module_swap.py`, since deleted) verified the snapshot/restore mechanism works as theorized:

```
POLLUTER end: sys.modules cogs.ingest id=4454281792   (MODULE_B, post load_extension)
VICTIM start: sys.modules cogs.ingest id=4444166064   (MODULE_A, restored)
  callback __globals__ id=4444279104
  sys.modules dict id=4444279104
  same: True                                          ← restored module == cog class globals
  AFTER mock.patch: cb_globals['ingest'] is mock: True ← mock lands on the right dict
```

The diagnostic proved the failure mode (MODULE_A vs MODULE_B identity divergence post-load_extension) and that the snapshot/restore puts the test back in a state where `mock.patch` resolves to the same dict the test class's `__globals__` references.

## Requirements satisfaction

- **HANG-01** — verified not reproducible at HEAD (Phase 14 already fixed). Re-verified by 2 consecutive full-suite GREEN runs. **Ticked.**
- **HANG-02** — same as HANG-01. **Ticked.**
- **HANG-03** / **FLAKE-02** (v1.3 carried partial) — closed by this plan's autouse fixture. **Ticked.**

## Out-of-scope (deferred)

No deferred items from this work.
