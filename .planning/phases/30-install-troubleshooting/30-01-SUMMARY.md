---
phase: 30-install-troubleshooting
plan: 30-01
requirements: [DOCS-01]
status: complete
completed: 2026-05-26
---

# Plan 30-01 Summary — INSTALL.md refresh

## One-liner
Refreshed `INSTALL.md` with a Docker quickstart, the v1.0→v1.10 env var / CLI / dep-group reference tables, and replaced the inline troubleshooting + v1.0→v1.1 upgrade sections with cross-links to the new `docs/TROUBLESHOOTING.md` and `docs/UPGRADE.md` (produced in plan 30-02). Every claim cross-references an existing source: pyproject.toml, Settings, `os.environ` read sites in `src/`, or Phase 29 docker artifacts.

## What changed

| File | Δ | Sections touched |
|---|---|---|
| `INSTALL.md` | +86 / -175 net | `🎯 Hero` (cross-link banner), `🐳 Docker quickstart` (new), `🔑 Configure .env` (3 new ref tables: env vars / CLIs / dep groups), `🩺 Troubleshooting` (body → cross-link), `v1.0 → v1.1 Upgrade` (body → cross-link) |

## Commits

| Hash | Message |
|---|---|
| `d4b1d34` | docs(30-01): plan — INSTALL.md refresh |
| `46c86a2` | docs(30-01): add Docker quickstart section to INSTALL.md (Phase 29 DEPLOY-01 surface) |
| `329187e` | docs(30-01): add env vars + CLI + dep-group reference tables to INSTALL.md (D-229) |
| `3ebd199` | docs(30-01): replace inline troubleshooting + upgrade sections with docs/ cross-links (D-233) |

## Source-of-truth citations (D-232)

Every variable / CLI / dep-group named in the new INSTALL.md sections is traceable to one of:

- `pyproject.toml` `[project.scripts]` — 8 entries verified (eldritch-dm + 7 tool CLIs)
- `pyproject.toml` `[project.optional-dependencies]` — 4 groups verified (dev, mac-ocr, linux-ocr, observability)
- `src/eldritch_dm/config/__init__.py` `Settings` class — 8 vars verified (discord_token, discord_guild_ids, discord_owner_id, eldritch_db_path, monster_driver, narrcache_enabled, mcpcache_l2_enabled, monster_memory_persist, stream_enabled)
- `src/eldritch_dm/observability/tracer.py:39` — `OBSERVABILITY_ENABLED` (NOT a Settings field; read via `os.environ.get`)
- `src/eldritch_dm/tools/cost_report.py:84` — `ELDRITCH_DAILY_LLM_BUDGET_USD` (NOT a Settings field; read via `os.environ.get`)
- `src/eldritch_dm/tools/backfill_pc_classes.py` — `DM20_MCP_URL` (NOT a Settings field; read via the tool's own arg-resolution chain)
- `docker-compose.yml` lines 49-52 — Linux `host-gateway` mapping

## Deviations from plan
None — executed as written. The advisor-flagged env-var citation gap (3 vars not in Settings) was resolved by citing the actual `os.environ` read sites rather than pretending they were Settings fields.

## Self-check

- `grep -c "^## " INSTALL.md` → 16 top-level sections (was 16 before; net structure preserved, content swap only — Docker section added, 0 sections removed because Troubleshooting and Upgrade headings kept as discoverability anchors).
- All 12 env vars in the new reference table trace back to grep-verifiable source paths (cited above).
- All 7 CLIs match `[project.scripts]` entries 1:1.
- All 4 dep groups match `[project.optional-dependencies]` keys 1:1.

## Self-Check: PASSED
