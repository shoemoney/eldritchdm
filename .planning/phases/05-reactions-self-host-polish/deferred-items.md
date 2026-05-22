# Phase 5 — Deferred Items

Pre-existing issues discovered during Phase 5 Plan 01 execution. NOT in scope
for Plan 01 per scope-boundary rules (only auto-fix issues directly caused by
the current task's changes).

## Ruff lint issues in pre-existing files

| File | Issue | First introduced |
|------|-------|------------------|
| `src/eldritch_dm/gameplay/exploration_batch.py` | I001 (unsorted imports), UP035 (`typing.Callable` → `collections.abc.Callable`) | Phase 4 (commit `cab6b18`) |

These lines were untouched by Plan 01. They surface when ruff is run over
`src/eldritch_dm/gameplay/` for verification. Fix in a separate cleanup pass.
