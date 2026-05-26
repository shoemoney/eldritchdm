# EldritchDM — multi-stage Dockerfile for the Discord bot runtime image.
#
# Build:    docker compose build eldritch-bot   (or:  docker build -t eldritch-dm:local .)
# Run:      docker compose up -d                (single-service stack, see docker-compose.yml)
#
# Image philosophy (D-223, D-224):
#   * python:3.11-slim base — small, official, current security backports.
#   * uv as the package manager — reuses pyproject.toml + uv.lock so the
#     container deps match local dev exactly. No pip resolve at build time.
#   * Two stages: a `builder` that materializes /app/.venv from the lockfile,
#     and a `runtime` that copies only the venv + src/ on top of a fresh slim
#     image. No compilers in the final stage.
#   * No [mac-ocr] (macOS-only — won't build on Linux anyway).
#   * No [observability] (lazy-imported per Phase 11; opt-in extras install
#     by the operator if they enable OBSERVABILITY_ENABLED).
#   * Runs as non-root user `eldritch` (UID/GID 1000).
#   * Healthcheck: `python -c "import eldritch_dm"` — proves the venv + source
#     are wired up; the bot's actual Discord login is exercised by the
#     ENTRYPOINT once the container starts.
#
# Image-size target: <500 MB compressed (the deps are pure-Python or
# wheel-only on linux/amd64 + linux/arm64; PyMuPDF is the biggest at ~20 MB).

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — builder: materialize /app/.venv from the lockfile
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Pull the uv binary from the official Astral image — avoids curl/pip bootstrap.
# Pinning to a release tag (not :latest) for reproducibility; bump deliberately.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Layer 1: install dependencies only (no project source).
# This layer rebuilds only when pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Layer 2: install the project itself.
# Rebuilds when src/ or README.md changes; deps layer above stays cached.
COPY src/ ./src/
COPY README.md ./
RUN uv sync --frozen --no-dev

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — runtime: minimal image with venv + source + non-root user
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Create a non-root user. UID/GID 1000 plays nicely with host bind mounts
# from typical Linux user accounts. /home/eldritch exists for any tools
# that look up $HOME.
RUN groupadd --system --gid 1000 eldritch \
 && useradd  --system --uid 1000 --gid eldritch \
             --create-home --home-dir /home/eldritch \
             --shell /usr/sbin/nologin \
             eldritch

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/app/.venv

WORKDIR /app

# Copy the prebuilt venv and project source from the builder stage,
# chowning into the eldritch user so it owns its own runtime.
COPY --from=builder --chown=eldritch:eldritch /app/.venv /app/.venv
COPY --from=builder --chown=eldritch:eldritch /app/src /app/src
COPY --from=builder --chown=eldritch:eldritch /app/README.md /app/README.md
COPY --from=builder --chown=eldritch:eldritch /app/pyproject.toml /app/pyproject.toml

# Persistent runtime state lives here — the compose file mounts a named volume.
RUN mkdir -p /app/data && chown -R eldritch:eldritch /app/data

USER eldritch

# Cheap, dependency-free liveness check: if the venv + source are intact,
# `import eldritch_dm` returns 0. Failing this means the image is broken,
# not just that Discord is down.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import eldritch_dm, sys; sys.exit(0)"]

# Console-script equivalent of `eldritch-dm` (see pyproject.toml [project.scripts]),
# spelled out as a module for clarity. Exit codes are documented in
# src/eldritch_dm/bot/__main__.py.
ENTRYPOINT ["python", "-m", "eldritch_dm.bot"]
