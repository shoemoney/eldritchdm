---
phase: 29-docker-compose
milestone: v1.10
generated: 2026-05-26
mode: auto-generated (autonomous-flow)
source_requirements:
  - DEPLOY-01 (docker-compose.yml at repo root)
  - DEPLOY-02 (multi-stage Dockerfile)
  - DEPLOY-03 (docker compose smoke test)
---

# Phase 29 — Bundled docker-compose for full stack (CONTEXT)

## Mission

Single-command operator UX: `docker compose up -d` brings up the bot. NOT bundling oMLX (operator hardware) or dm20 (separate project). Phoenix stays in the existing optional `docker-compose.observability.yml`.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-221** | **`docker-compose.yml` at repo root** (NOT `docker-compose.bot.yml`). Existing `docker-compose.observability.yml` (Phase 11) stays separate. Operators can `docker compose up -d` for just bot; `docker compose -f docker-compose.observability.yml up -d` for observability stack alongside. | Conventional naming for the main service |
| **D-222** | **Single `eldritch-bot` service** in compose. Reads env from `.env` file at repo root (existing `.env.example` already documents the surface). Healthcheck: `python -c "import eldritch_dm"` via `docker compose exec`. Restart policy: `unless-stopped`. | Minimal compose, maximum portability |
| **D-223** | **Multi-stage Dockerfile**:<br>STAGE 1 (`builder`): `python:3.11-slim` + `uv` install + `uv sync --no-dev` (production-only deps)<br>STAGE 2 (`runtime`): `python:3.11-slim` + COPY venv from builder + non-root `eldritch` user (UID 1000) + ENTRYPOINT `python -m eldritch_dm.bot`<br>Image size budget: <500MB compressed | Standard production Docker pattern |
| **D-224** | **Optional extras NOT installed by default in image**: `[mac-ocr]` is macOS-only (won't build on Linux containers anyway), `[observability]` is opt-in (operator can use the Phoenix compose file). To enable observability in the bot container: operator sets `OBSERVABILITY_ENABLED=true` env + installs `[observability]` extras separately. Phase 11 lazy-import means zero-cost when disabled. | Matches Phase 14 + Phase 11 design |
| **D-225** | **`.dockerignore`** at repo root to exclude: `.git/`, `.venv/`, `.planning/tmp/`, `.claude/worktrees/`, `tests/`, `*.sqlite3`. Trims build context. | Faster builds, no secret leakage |
| **D-226** | **DEPLOY-03 smoke**: `scripts/ops/test_docker_smoke.sh` runs `docker compose up -d --wait`, smoke-tests via `docker compose exec`, captures logs on failure, runs `docker compose down`. NOT in default CI matrix (Docker dep). Operator-opt-in (`bash scripts/ops/test_docker_smoke.sh`). | Smoke is regression-detection, not a default gate |
| **D-227** | **NO docker push** logic — operators may use the image locally or push to their own registry. We don't run a public registry. | Self-hosted philosophy |
| **D-228** | **2 plans**: 29-01 = docker-compose.yml + Dockerfile + .dockerignore. 29-02 = smoke test script. | ROADMAP plans section |

## Success Criteria
1. `docker-compose.yml` at repo root brings up `eldritch-bot` service via `docker compose up -d`
2. `Dockerfile` multi-stage; non-root user; <500MB compressed image
3. `.dockerignore` excludes irrelevant paths
4. `scripts/ops/test_docker_smoke.sh` runs the up→exec→down cycle
5. Smoke test gated behind operator action (NOT in default CI)
6. No regression in existing 1662-test suite
7. ruff + lint-imports clean
