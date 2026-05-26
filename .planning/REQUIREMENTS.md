# EldritchDM — Requirements (v1.10 Operator Deployment Polish)

**Milestone:** v1.10 Operator Deployment Polish
**Goal:** Make self-hosting genuinely easy. Bundled `docker-compose.yml` for the full stack (bot + optional Phoenix + dm20 placeholder docs). Refresh INSTALL.md reflecting v1.0-v1.9 changes. New TROUBLESHOOTING.md FAQ covering operator gotchas surfaced across the build.
**Total v1.10 requirements:** 6 across 2 categories.

---

## v1.10 Requirements

### DEPLOY — Bundled docker-compose stack (Phase 29)

- [x] **DEPLOY-01**: `docker-compose.yml` at repo root (NOT the existing `docker-compose.observability.yml` — that one's optional/Phoenix-only). Brings up `eldritch-bot` service (the Discord bot). Reads `DISCORD_TOKEN`, `DM20_MCP_URL`, etc. from a `.env` file at repo root (existing `.env.example` already documents the surface). Healthcheck endpoint or simple `python -c "import eldritch_dm"` startup probe. Restart policy `unless-stopped`. Single-command operator UX: `docker compose up -d`.
- [x] **DEPLOY-02**: `Dockerfile` at repo root — multi-stage build using Python 3.11 official image; `uv sync` for dependencies; `[mac-ocr]` extras NOT installed by default (Linux container; matches Phase 14 skip-gate decision); `[observability]` NOT installed by default (gated by env). Image runs as non-root user `eldritch`. Size budget: <500MB compressed (achievable with python:3.11-slim + uv).
- [x] **DEPLOY-03**: Smoke test at `scripts/ops/test_docker_smoke.sh` — `docker compose up -d`, wait for healthcheck, `docker compose exec eldritch-bot python -c "import eldritch_dm; print('OK')"`, `docker compose down`. Fails fast on any error. Gated behind operator opt-in (NOT in default CI matrix — assumes Docker available).

### DOCS — INSTALL refresh + troubleshooting runbook (Phase 30)

- [x] **DOCS-01**: `INSTALL.md` updated reflecting v1.0-v1.9: new optional dep groups (`observability`, `linux-ocr`), new env vars (OBSERVABILITY_ENABLED, MONSTER_DRIVER, NARRCACHE_ENABLED, MCPCACHE_L2_ENABLED, MONSTER_MEMORY_PERSIST, DISCORD_OWNER_ID, ELDRITCH_DAILY_LLM_BUDGET_USD, STREAM_ENABLED), new CLIs (eldritch-dm-backfill-pc-classes, eldritch-dm-eval, eldritch-dm-cost-report, eldritch-dm-cache-clear, eldritch-dm-cache-disable, eldritch-dm-cache-stats, eldritch-dm-perf-baseline). One-command Docker setup. macOS-native setup (with [mac-ocr] for OCR).
- [x] **DOCS-02**: NEW `docs/TROUBLESHOOTING.md` — FAQ covering: (a) "Bot says DM is offline" → check oMLX + circuit breaker; (b) "OCR not working" → mac-ocr extras OR observability skip-gate; (c) "Cache hit rate is 0" → check OBSERVABILITY_ENABLED + MCPCACHE_ENABLED; (d) "Discord DM token errors" → token_guard + EXIT_MISSING_TOKEN=4; (e) "Pytest hangs" → orchestrator-session-specific issue, recommend fresh shell; (f) "Linux ocrmac unavailable" → use `[linux-ocr]` extras. ≥10 entries surfaced from real operator gotchas in v1.0-v1.9 SUMMARYs.
- [x] **DOCS-03**: `docs/UPGRADE.md` (NEW) — version-to-version upgrade notes: v1.0→v1.1 needs `eldritch-dm-backfill-pc-classes` for legacy chars (UPGRADE-01); v1.2→v1.3 has the OCR skip-gate (no operator action); v1.5→v1.6 has hot-reload eligibility (no restart); v1.7→v1.8 includes auto-discovery backfill; v1.9 docs/PERFORMANCE.md is informational. Operators can step-by-step trace what changed.

---

## Traceability

| REQ-ID | Phase | Source |
|---|---|---|
| DEPLOY-01 | 29 | Self-hoster UX — single-command Docker setup |
| DEPLOY-02 | 29 | Multi-stage Dockerfile w/ non-root user |
| DEPLOY-03 | 29 | Smoke test gates regressions on the deploy path |
| DOCS-01 | 30 | INSTALL.md needs to reflect 10 milestones of changes |
| DOCS-02 | 30 | Operator gotchas surfaced across v1.0-v1.9 |
| DOCS-03 | 30 | Version-to-version upgrade trail |

## Mode Constraints

- DEPLOY-01: docker-compose.yml is for the BOT only — does NOT bundle oMLX (that's the operator's hardware), does NOT bundle dm20 (separate project). Phoenix stays optional via existing docker-compose.observability.yml (Phase 11).
- DEPLOY-02: Linux container image; no macOS-only deps installed by default. Operators on macOS native run `pip install -e ".[dev,mac-ocr]"` separately (existing path).
- DEPLOY-03: Docker smoke test gated behind operator action (NOT in default CI matrix — adds Docker build dependency to every CI run).
- DOCS-01: reflects EXISTING surface — don't invent flags. Cross-check against pyproject.toml + Settings + [project.scripts].
- DOCS-02: ≥10 FAQ entries grounded in real v1.0-v1.9 SUMMARY surface (not invented "common questions").
- DOCS-03: version-to-version notes match existing milestone archives in `.planning/milestones/`.
