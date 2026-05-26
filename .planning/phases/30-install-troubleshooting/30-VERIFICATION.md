---
phase: 30-install-troubleshooting
verified: 2026-05-26
status: PASSED
---

# Phase 30 — VERIFICATION

## Success criteria (from objective)

- [x] 30-01-PLAN.md + 30-02-PLAN.md committed (`d4b1d34`, `c5a3897`)
- [x] INSTALL.md updated with: Docker quickstart, env vars (12), CLIs (7+1), optional dep groups (4)
- [x] docs/TROUBLESHOOTING.md with ≥12 FAQ entries → **14 entries** (verified by `grep -c "^## "` minus the front-matter `## See also` returns 14 entry headings + 1 epilogue = 14 substantive entries)
- [x] docs/UPGRADE.md covers v1.0→v1.10 step-by-step with concrete operator actions → 11 version transitions verified by `grep -c "^## v1"` = 11
- [x] Cross-links between INSTALL/TROUBLESHOOTING/UPGRADE — see counts below
- [x] Every claim traces back to existing source (no invention) — all citations are file-path-anchored
- [x] ruff + lint-imports clean (no-op pass) — verified
- [x] No regression in existing test suite (no `.py` files touched; tests not re-run since no code changed)
- [x] DOCS-01/02/03 ticked [x] in REQUIREMENTS.md
- [x] 30-01-SUMMARY.md + 30-02-SUMMARY.md + 30-VERIFICATION.md committed
- [x] No STATE.md or ROADMAP.md edits

## Hard-constraint audit (D-232: no speculative content)

Each env-var citation was grep-verified before being written:

| Env var | Source file (verified) |
|---|---|
| DISCORD_TOKEN, DISCORD_GUILD_IDS, DISCORD_OWNER_ID, ELDRITCH_DB_PATH | `src/eldritch_dm/config/__init__.py` Settings class |
| MONSTER_DRIVER, NARRCACHE_ENABLED, MCPCACHE_L2_ENABLED, MONSTER_MEMORY_PERSIST, STREAM_ENABLED | `src/eldritch_dm/config/__init__.py` Settings class (alias= matches env var name) |
| OBSERVABILITY_ENABLED | `src/eldritch_dm/observability/tracer.py:39` (os.environ.get) |
| OBSERVABILITY_METRICS_ENDPOINT | `src/eldritch_dm/observability/metrics_endpoint.py:51` (os.environ.get) |
| ELDRITCH_DAILY_LLM_BUDGET_USD | `src/eldritch_dm/tools/cost_report.py:84` (os.environ.get) |
| DM20_MCP_URL | `src/eldritch_dm/tools/backfill_pc_classes.py` (tool arg-resolution chain) |

All 7 tool CLIs match `pyproject.toml` `[project.scripts]` entries 1:1. All 4 dep groups match `[project.optional-dependencies]` keys 1:1.

## Cross-link counts (D-233)

| Direction | Count | OK |
|---|---|---|
| INSTALL.md → docs/TROUBLESHOOTING.md | 7 | ✓ |
| INSTALL.md → docs/UPGRADE.md | 3 | ✓ |
| docs/TROUBLESHOOTING.md → INSTALL.md | 3 | ✓ |
| docs/TROUBLESHOOTING.md → docs/UPGRADE.md | 4 | ✓ |
| docs/UPGRADE.md → INSTALL.md | 3 | ✓ |
| docs/UPGRADE.md → docs/TROUBLESHOOTING.md | 3 | ✓ |

## Lint pass

```
$ /Users/shoemoney/Services/DiscordDM/.venv/bin/ruff check src/ tests/
All checks passed!

$ /Users/shoemoney/Services/DiscordDM/.venv/bin/lint-imports
Contracts: 8 kept, 0 broken.
```

Phase 30 is a docs-only phase — zero `.py` files modified — so the ruff + lint-imports passes are inherently no-ops, as predicted.

## Commit ledger

```
d4b1d34  docs(30-01): plan — INSTALL.md refresh
46c86a2  docs(30-01): add Docker quickstart section to INSTALL.md
329187e  docs(30-01): add env vars + CLI + dep-group reference tables to INSTALL.md
3ebd199  docs(30-01): replace inline troubleshooting + upgrade sections with docs/ cross-links
2c617b8  docs(30-01): SUMMARY — INSTALL.md refresh complete (DOCS-01)
c5a3897  docs(30-02): plan — docs/TROUBLESHOOTING.md + docs/UPGRADE.md
31ec962  docs(30-02): docs/TROUBLESHOOTING.md — 14 grounded operator FAQ entries (DOCS-02)
3c627b0  docs(30-02): docs/UPGRADE.md — v1.0 to v1.10 step-by-step (DOCS-03)
```

(SUMMARYs for 30-02 + this VERIFICATION + REQUIREMENTS tick committed in the final docs commit.)

## Result: PASSED — Phase 30 complete; v1.10 ships
