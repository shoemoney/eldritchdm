---
phase: 30-install-troubleshooting
plan: 30-02
requirements: [DOCS-02, DOCS-03]
status: complete
completed: 2026-05-26
---

# Plan 30-02 Summary — docs/TROUBLESHOOTING.md + docs/UPGRADE.md

## One-liner
Created `docs/TROUBLESHOOTING.md` (14 grounded operator FAQ entries — exceeds the ≥10 D-230 minimum) and `docs/UPGRADE.md` (11 version transitions covering v1.0 → v1.10, every operator-facing change cited to a milestone archive or source file). All claims trace to existing source per D-232.

## What changed

| File | Δ | Purpose |
|---|---|---|
| `docs/TROUBLESHOOTING.md` | +323 (new) | 14 symptom → cause → diagnose → fix entries; each cites a Settings field, milestone archive, or `src/` file. |
| `docs/UPGRADE.md` | +331 (new) | 11 version sections (v1.0→v1.1 through v1.9→v1.10); at-a-glance table marks operator-action-required transitions. |

## FAQ entries (TROUBLESHOOTING.md, 14)

1. Bot says DM is offline (Phase 7 OPS-02 circuit-breaker)
2. OCR tests are skipping (Phase 14 FLAKE-01)
3. Cache hit rate is zero (Phase 16/17/18 — gating switches)
4. Bot exits with code 4 / DISCORD_TOKEN missing (Phase 7 SAFETY-03)
5. Pytest hangs in the full suite (v1.3 FLAKE-02 user-accepted partial)
6. Monster driver always picks random (Phase 10 D-52 / Phase 22 D-170 degraded mode)
7. Riposte button doesn't fire (Phase 9 TD-3 / UPGRADE-01)
8. Phoenix dashboards empty (Phase 11 OBS-01 + Phase 13 MON-01)
9. Cost calculator is off (v1.2.1 hotfix pattern / Phase 13 MON-03)
10. perf-baseline regression alert (Phase 28 TUNE-02 / D-218)
11. Restart loses character state (Phase 17 D-119 + Phase 4 OPS-04)
12. Eligibility YAML edits don't take effect (Phase 22 OPQOL hot-reload)
13. `sqlite3.OperationalError: database is locked` (v1.4 writer-queue / migrated from INSTALL.md)
14. Bot disconnected — buttons inert after restart (Phase 4 persistent-view discipline / migrated from INSTALL.md)

## Version transitions (UPGRADE.md, 11)

v1.0→v1.1 (full backfill flow), v1.1→v1.2 (observability opt-in), v1.2→v1.2.1 (pricing.yaml hotfix), v1.2→v1.3 (no action), v1.3→v1.4 (no action), v1.4→v1.5 (cache opt-ins), v1.5→v1.6 (UX opt-outs + persistence + owner DMs), v1.6→v1.7 (no action), v1.7→v1.8 (no action), v1.8→v1.9 (new perf-baseline CLI), v1.9→v1.10 (docker compose).

## Cross-link verification (D-233)

| Direction | Count | OK |
|---|---|---|
| INSTALL.md → docs/TROUBLESHOOTING.md | 7 | ✓ (≥2) |
| INSTALL.md → docs/UPGRADE.md | 3 | ✓ (≥2) |
| docs/TROUBLESHOOTING.md → INSTALL.md | 3 | ✓ (≥2) |
| docs/TROUBLESHOOTING.md → docs/UPGRADE.md | 4 | ✓ (≥2) |
| docs/UPGRADE.md → INSTALL.md | 3 | ✓ (≥2) |
| docs/UPGRADE.md → docs/TROUBLESHOOTING.md | 3 | ✓ (≥2) |

## Commits

| Hash | Message |
|---|---|
| `c5a3897` | docs(30-02): plan — docs/TROUBLESHOOTING.md + docs/UPGRADE.md |
| `31ec962` | docs(30-02): docs/TROUBLESHOOTING.md — 14 grounded operator FAQ entries (DOCS-02) |
| `3c627b0` | docs(30-02): docs/UPGRADE.md — v1.0 to v1.10 step-by-step (DOCS-03) |

## Verification commands run

```bash
grep -c "^## " docs/TROUBLESHOOTING.md      # 14 (≥12 ✓)
grep -c "^## v1" docs/UPGRADE.md            # 11 (all transitions present)
/Users/shoemoney/Services/DiscordDM/.venv/bin/ruff check src/ tests/   # All checks passed!
/Users/shoemoney/Services/DiscordDM/.venv/bin/lint-imports             # Contracts: 8 kept, 0 broken.
```

## Deviations from plan
None — executed as written.

## Self-Check: PASSED
