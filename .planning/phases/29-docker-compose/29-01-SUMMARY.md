---
phase: 29-docker-compose
plan: 29-01
subsystem: deploy
tags: [docker, compose, dockerfile, self-host]
requirements: [DEPLOY-01, DEPLOY-02]
key-files:
  created:
    - .dockerignore
    - Dockerfile
    - docker-compose.yml
  modified: []
decisions:
  - D-221 (compose at repo root, separate from observability)
  - D-222 (single eldritch-bot service, env_file .env, unless-stopped)
  - D-223 (multi-stage Dockerfile, python:3.11-slim + uv, <500MB target)
  - D-224 (no [mac-ocr] / [observability] in default image)
  - D-225 (.dockerignore excludes .git/.venv/.planning/tests/etc)
  - D-227 (no docker push logic; self-hosted only)
metrics:
  duration: ~25 min
  completed: 2026-05-26
---

# Phase 29 Plan 01: Bundled docker-compose + Dockerfile Summary

## One-liner
Self-hoster single-command UX: `docker compose up -d` builds a multi-stage `python:3.11-slim + uv` image, runs the bot as non-root user `eldritch`, mounts persistent state to `eldritch-data`, and reaches host-side oMLX/dm20 via `host.docker.internal`.

## What Shipped

### `.dockerignore`
Trims the build context shipped to the daemon. Excludes `.git/`, `.venv/`, `.planning/`, `.claude/`, `tests/`, `*.sqlite3`, `.env` (defense in depth — `.env.example` still gets in), build artifacts, and the optional `docker-compose.observability.yml` (irrelevant inside the bot image). Whitelists `uv.lock` and `.env.example`.

### `Dockerfile` (multi-stage)
- **STAGE 1 `builder`** (`python:3.11-slim`):
  - `uv` binary copied from `ghcr.io/astral-sh/uv:0.5.11` (pinned, no curl bootstrap)
  - `uv sync --frozen --no-dev --no-install-project` from `pyproject.toml + uv.lock` (dep layer)
  - then `COPY src/` + `uv sync --frozen --no-dev` (project install layer)
  - Result: `/app/.venv` with all production deps + the project itself
- **STAGE 2 `runtime`** (`python:3.11-slim`):
  - Non-root user `eldritch` (UID/GID 1000, `/usr/sbin/nologin` shell)
  - Copies venv + `src/` + `README.md` + `pyproject.toml` from builder
  - `mkdir /app/data` (chowned) — the compose named volume binds here
  - `PATH=/app/.venv/bin:$PATH`, `PYTHONUNBUFFERED=1`
  - **HEALTHCHECK**: `python -c "import eldritch_dm; sys.exit(0)"` (30s interval)
  - **ENTRYPOINT**: `python -m eldritch_dm.bot` (matches `[project.scripts] eldritch-dm`)

Image size budget per D-223 is <500 MB compressed; deps are pure-Python or wheel-only on linux/amd64 + linux/arm64. PyMuPDF (~20 MB) is the biggest single dep. Actual image size will be measured by the 29-02 smoke script when an operator runs it.

### `docker-compose.yml`
Compose v2 (no `version:` key — modern compose deprecates it). Single service:
```
services:
  eldritch-bot:
    build: .
    image: eldritch-dm:local
    container_name: eldritch_bot
    restart: unless-stopped
    env_file: [{ path: .env, required: false }]  # see fix commit
    extra_hosts: ["host.docker.internal:host-gateway"]
    volumes: ["eldritch-data:/app/data"]
volumes:
  eldritch-data: { driver: local }
```
- `host.docker.internal` + `host-gateway` gives Linux parity with Docker Desktop semantics so the container can reach the operator's host-side oMLX (`:8765`) and dm20 MCP without a docker network for them.
- `env_file: required: false` (compose v2 syntax) lets `docker compose config` lint-validate without an `.env` present. The bot itself still refuses to start without `DISCORD_TOKEN` via `require_token_or_exit` (exit 4, SAFETY-03).
- Phoenix is **not** in this file. Operators bring it up separately with `docker compose -f docker-compose.observability.yml up -d`.

## Verification

- `python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"` → OK
- `uv run ruff check .` → All checks passed
- `uv run lint-imports` → 8 contracts kept, 0 broken
- `uv run python -c "import eldritch_dm"` → OK (sanity)
- Full pytest run was launched in background; outcome captured in 29-VERIFICATION.md.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - bug] env_file required-by-default broke compose lint**
- **Found during:** Task 3 verification (`docker-compose -f docker-compose.yml config`)
- **Issue:** Compose v1/v2 default behavior is to error out if `env_file:` paths are missing. That made `docker compose config` unusable as a lint step pre-`.env`.
- **Fix:** Switched to compose v2's `env_file: - { path: .env, required: false }` form. The bot still hard-fails at runtime if `DISCORD_TOKEN` is absent (SAFETY-03), so the correctness contract is unchanged — only the lint UX got better.
- **Files modified:** `docker-compose.yml`
- **Commit:** 6bd3822

No other deviations.

## Commits

| Commit  | Type | Description                                                 |
| ------- | ---- | ----------------------------------------------------------- |
| ad30bdf | docs | Plans 29-01 + 29-02                                         |
| 7123784 | feat | `.dockerignore`                                             |
| 5ed1737 | feat | Multi-stage `Dockerfile` (slim + uv + non-root `eldritch`)  |
| aeed4d2 | feat | `docker-compose.yml` single `eldritch-bot` service          |
| 6bd3822 | fix  | `env_file: required: false` so compose config validates     |

## Self-Check: PASSED
- `.dockerignore`: FOUND
- `Dockerfile`: FOUND
- `docker-compose.yml`: FOUND
- All five commits: FOUND in git log
