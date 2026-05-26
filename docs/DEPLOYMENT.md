<!-- generated-by: gsd-doc-writer -->
# Deployment

EldritchDM is **local-first and self-hostable** by design. There is no
hosted variant and no multi-tenant story. This document describes the
two supported deployment paths and the CI pipeline that validates every
release candidate.

| Path | Config file(s) | Status | When to use |
|---|---|---|---|
| Docker Compose | [`docker-compose.yml`](../docker-compose.yml) + [`Dockerfile`](../Dockerfile) | Recommended (v1.10+) | Linux self-host; one-command bring-up; reproducible |
| Native process (`launchd` / `systemd`) | [`docs/launchd.plist.example`](launchd.plist.example) · [`docs/eldritch-dm.service.example`](eldritch-dm.service.example) | Supported | macOS Apple Silicon developer rigs that already run oMLX as `com.user.omlx` |

Optional add-on:

| Stack | Config file | Purpose |
|---|---|---|
| Phoenix observability | [`docker-compose.observability.yml`](../docker-compose.observability.yml) | Self-hostable Arize Phoenix UI for OTel decision spans (v1.2+ opt-in) |

For step-by-step **install** instructions (oMLX, dm20, Discord token),
see [`INSTALL.md`](../INSTALL.md). For runtime problems, see
[`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md). For per-version
operator actions, see [`docs/UPGRADE.md`](UPGRADE.md).

## What the bot needs at deploy time

EldritchDM is the **Discord adapter**. Deploying it does NOT deploy the
rules engine or the LLM — those are separate processes the operator
must already be running:

1. **oMLX** serving `ShoeGPT` on `:8765` (or another OpenAI-compatible
   server if you've overridden `OMLX_ENDPOINT`). oMLX itself requires
   macOS 13.5+ and Apple Silicon — the bot container can talk to it
   over `host.docker.internal:8765` from any host that runs Docker
   Desktop, or via the `extra_hosts: host-gateway` mapping on Linux
   Docker Engine.
2. **dm20 MCP server** mounted in that same oMLX, exposing
   `/v1/mcp/execute`.
3. A **Discord bot token** in `.env` (`DISCORD_TOKEN`).
4. (Optional) The `[observability]` extras + the Phoenix container if
   you want OTel traces.

`docker-compose.yml` is intentionally a **single-service stack** (D-221)
— it brings up the bot only. oMLX and dm20 stay on the host. Phoenix is
a separate compose file you bring up on demand.

## Path 1 — Docker Compose (v1.10+)

The bundled compose stack lives at the repo root and uses the
multi-stage Dockerfile to produce a single image:

```bash
cp .env.example .env
$EDITOR .env                              # set DISCORD_TOKEN at minimum
docker compose up -d
docker compose logs -f eldritch-bot       # tail the bot
docker compose ps                         # healthcheck status
```

What the compose file declares (verified against
[`docker-compose.yml`](../docker-compose.yml)):

- **Service `eldritch-bot`** — built from `./Dockerfile`, tagged
  `eldritch-dm:local`, `restart: unless-stopped`.
- **`env_file: .env`** with `required: false` (compose v2 form) — lets
  `docker compose config` validate without an `.env` present; the
  daemon refuses to start the bot without `DISCORD_TOKEN`, which is the
  correct failure mode.
- **`extra_hosts: host.docker.internal:host-gateway`** for Linux parity
  with macOS / Windows Docker Desktop. The bot reaches oMLX and dm20 at
  `host.docker.internal:8765`.
- **Named volume `eldritch-data`** mounted at `/app/data` for the
  SQLite + cache files.
- **Healthcheck declared in the Dockerfile**
  (`HEALTHCHECK CMD python -c "import eldritch_dm"`) surfaces in
  `docker compose ps`.

### Dockerfile contract

The multi-stage Dockerfile (`python:3.11-slim` base, `uv` installer
from `ghcr.io/astral-sh/uv:0.5.11`) follows these rules (D-223, D-224):

- Two stages: a `builder` materializes `/app/.venv` from `pyproject.toml`
  + `uv.lock`; a `runtime` stage copies only the venv + `src/` onto a
  fresh slim image. No compilers in the final image.
- **No `[mac-ocr]`** — won't build on Linux. macOS-only.
- **No `[observability]`** — lazy-imported per Phase 11; opt-in extras
  install by the operator if they enable `OBSERVABILITY_ENABLED`.
- Runs as **non-root user `eldritch` (UID/GID 1000)** for host
  bind-mount parity.
- Image-size target: < 500 MB compressed.
- Entrypoint: `python -m eldritch_dm.bot` (equivalent to the
  `eldritch-dm` console script).

### Self-hoster setup

Operator steps from `docker-compose.yml` header comments:

```bash
cp .env.example .env
# Edit .env:
#   - DISCORD_TOKEN=<your bot token>
#   - For Linux Docker Engine, oMLX/dm20 on the host become:
#       OMLX_ENDPOINT=http://host.docker.internal:8765/v1
#       MCP_EXECUTE_URL=http://host.docker.internal:8765/v1/mcp/execute
#       MCP_TOOLS_URL=http://host.docker.internal:8765/v1/mcp/tools
docker compose up -d
```

`INSTALL.md → Docker quickstart (one command)` (line 152+ of
`INSTALL.md`) has the operator-facing playbook with worked examples
including the optional `--build` rebuild flag and tear-down.

### Persistent state

The named volume `eldritch-data` holds:

- `/app/data/eldritch.sqlite3` (or wherever `ELDRITCH_DB_PATH` points)
  — Phase 1 channel sessions + persistent views + riposte timers +
  sanitizer audit + combat conditions + pc_classes.
- (If enabled) `~/.eldritch/mcp_cache.sqlite` — Phase 16 L2 MCP query
  cache. Path lives inside the container's `eldritch` user home; bind
  it out separately if you want host-side visibility.
- (If enabled) `~/.eldritch/character_cache.sqlite` — Phase 17 character
  snapshot cache.
- (If enabled) `~/.eldritch/monster_memory.sqlite` — Phase 21 monster
  memory persistence.

To inspect from the host:

```bash
docker compose exec eldritch-bot sqlite3 /app/data/eldritch.sqlite3 '.tables'
```

### Tear-down

```bash
docker compose down                       # stop + remove containers, keep volume
docker compose down -v                    # also remove eldritch-data volume (destructive)
```

## Path 2 — Native process (launchd / systemd)

For developer rigs already running oMLX as a launchd plist
(`com.user.omlx`), the bot can run as a sibling native process.
Skeletons:

- macOS: [`docs/launchd.plist.example`](launchd.plist.example) — see
  README "Running as a Service" for the full recipe.
- Linux: [`docs/eldritch-dm.service.example`](eldritch-dm.service.example)
  — best-effort; the [linux-ocr] OCR backend is functional but slower.

The bot's working directory is the repo root; logs go to stderr unless
`LOG_FILE` is set. Set `LOG_FORMAT=json` for machine-parseable output to
a log shipper.

## Optional: Phoenix observability stack (v1.2+, Phase 11 / OBS-02)

A second compose file lives next to the main one:
[`docker-compose.observability.yml`](../docker-compose.observability.yml).
It brings up a single `arizephoenix/phoenix:latest` container with the
Phoenix UI on `:6006` and an OTLP HTTP endpoint accepting traces.

```bash
docker compose -f docker-compose.observability.yml up -d
open http://localhost:6006                 # UI
```

The compose file declares (verified against the file):

- Ports `6006` (UI + OTLP HTTP, Phoenix default), `4317` (OTLP gRPC),
  `4318` (OTLP HTTP, standard OTel port).
- Volume `phoenix-data` mounted at `/mnt/data` for trace persistence.
- Bridge network `eldritch_obs` so a future
  `otel/opentelemetry-collector-contrib` sidecar could be added (D-69
  simplification — Phoenix accepts OTLP HTTP directly, no collector
  needed).
- Healthcheck via `wget --spider http://localhost:6006/`.

To enable instrumentation in the bot, install the extras and set the
env vars:

```bash
uv pip install -e ".[observability]"
# in .env:
OBSERVABILITY_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces
```

If the bot is running in Docker too, point `OTEL_EXPORTER_OTLP_ENDPOINT`
at `http://host.docker.internal:6006/v1/traces` and connect both
compose stacks to the same Docker network if desired.

README "Optional: observability stack" has the dashboard-seeding recipe
(9 bundled Phoenix dashboards at v1.8: latency P50/P95/P99, fallback
rate by reason, cache hit rate, plus mcp_cache, character_cache,
narrcache, degraded_mode, budget, eval).

## GitHub Actions pipelines

Two workflows live in `.github/workflows/`. Neither deploys anywhere —
this is a local-first project with no hosted target — but they validate
release candidates.

### `ci.yml` — release-blocking (Phase 24 / POLISH-01, v1.7+)

Two-tier strategy (verified against
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)):

- **`test` matrix:** `macos-latest` + `ubuntu-latest` × Python 3.11.
  Installs `[dev]` ONLY (no mac-ocr, no observability). Runs:
  1. `uv run ruff check src/ tests/ run.py`
  2. `uv run lint-imports`
  3. `uv run pytest tests/ -q --cov=eldritch_dm --cov-report=term --cov-report=xml:coverage.xml`
  4. Linux only: `coverage.xml` artifact upload (14-day retention).
  5. Linux only: `scripts/ci/check_safe_yaml.sh` (Phase 8 yaml.safe_load
     gate).
  6. Linux only: `scripts/ci/check_summary_frontmatter.sh` (Phase 14
     SUMMARY frontmatter gate).

  The Linux runner is precisely what verifies the Phase 14 skip-gates
  (OCR + observability self-skip when extras absent) work cleanly.

- **`extras-mac` job:** `macos-latest` with `[dev,mac-ocr,observability]`.
  Marked `continue-on-error: true` — flaky native extras (ocrmac,
  PyObjC) never block a merge; it's informational only.

Triggers: every push (all branches) + pull_request to `main`.
Concurrency group cancels in-progress runs on push.

### `perf.yml` — informational (Phase 28 / TUNE-03 / D-219, v1.9+)

Single job on `macos-latest` (the primary target). Runs:

```bash
uv run eldritch-dm-perf-baseline \
  --baseline .planning/perf-baseline-v1.9.0.json \
  --output ./perf-runs
```

Triggers:

- Weekly schedule: Sundays at `02:00 UTC`.
- Push to `main` **only when the commit message contains `[perf]`**.
- Manual `workflow_dispatch`.

`continue-on-error: true` — perf is operator-tunable, not a correctness
contract. The CLI's 3-tier exit codes
(0 = ±10% / 1 = >10% / 2 = >25%) surface drift; investigate before
committing a new baseline.

The profiler uses hermetic mocks (respx dm20, AsyncMock LLM/Discord,
monkeypatched OCR) so the runner just executes Python — no external
services needed.

Artifact: `perf-diff-{run_id}/perf-runs/` (30-day retention).

## Release workflow

EldritchDM ships **milestone releases** (v1.0 → v1.11+). The flow:

1. Phase planning under `.planning/phases/<phase>/`.
2. Phase execution + per-plan SUMMARYs.
3. Phase closure: a `v1.N-MILESTONE-AUDIT.md` written into
   `.planning/`, a `[v1.N]` block prepended to
   [`CHANGELOG.md`](../CHANGELOG.md), and a `v1.N-ROADMAP.md`
   archived under `.planning/milestones/`.
4. Git tag `v1.N` on the closing commit (see
   `git tag --list | sort -V`).

There is no PyPI publish step, no Docker registry push, and no hosted
target — operators pull from `main` (or a tag) and run
`docker compose up -d` (or `python run.py`) themselves.

## Rollback

The bot is **stateful in SQLite** (the `eldritch.sqlite3` schema is
purely additive — see `database/schema.sql`). Rollback strategy:

1. **Image-level (Docker):** `docker compose down`, `git checkout
   v1.<previous>`, `docker compose up -d --build`. The named volume
   survives — the bot picks up its previous SQLite state.
2. **Source-level (native):** `git checkout v1.<previous>`, restart the
   process. No DB migration is required (schema is additive).
3. **Schema migrations are idempotent** — `database/schema.sql` uses
   `CREATE TABLE IF NOT EXISTS` and indexes. Running an older release
   against a newer DB will silently ignore newer tables; running a
   newer release against an older DB will add the new tables. See
   [`docs/UPGRADE.md`](UPGRADE.md) for per-version notes on any
   operator-action required (e.g. v1.0 → v1.1's `pc_classes` backfill).

The cache SQLites (`mcp_cache.sqlite`, `character_cache.sqlite`,
`monster_memory.sqlite`) are SAFE to delete at any time — they
regenerate on the next miss. Deleting them is the recommended rollback
move if you suspect a cache-introduced bug; see
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) entries
"Cache hit rate is zero" and "Monster driver always picks random
targets" for diagnostic hints.

## Monitoring

If `OBSERVABILITY_ENABLED=true` and the Phoenix stack is up, the bot
emits:

- **Decision spans** — `SmartMonsterDriver` outer span, D-65 8-attribute
  schema (`monster.id`, `channel.id`, `combat.round`, `driver.path`,
  `latency_ms`, `tokens.input`, `tokens.output`, `fallback.reason`).
- **Ingest spans** — `traced_translate` around character-sheet schema
  translation.
- **KPI metrics** — 5 live KPIs (Phase 13 / MON-02). 3-tier alert
  thresholds in `database/alerts.yaml`.
- **Cost telemetry** — token + USD against `database/pricing.yaml`
  (v1.2.1-verified). Daily cap from `ELDRITCH_DAILY_LLM_BUDGET_USD`
  (default $5.00). Breach trips degraded mode + DMs the operator
  (`DISCORD_OWNER_ID`, rate-limited 1/event-type/hour).
- **Cache hit/miss counters** for MCP / character / narration caches.

For shell-only operators, the equivalent without Phoenix:

```bash
eldritch-dm-cost-report                  # today's spend from the local span buffer
eldritch-dm-cache-stats                  # cache hit/miss live counters
```

If Phase 13's Prometheus `/metrics` endpoint is enabled
(`OBSERVABILITY_METRICS_ENDPOINT=true`), scrape
`http://OBSERVABILITY_METRICS_BIND:OBSERVABILITY_METRICS_PORT/metrics`
(defaults `127.0.0.1:9090`) into your existing Prometheus.

## Troubleshooting deploy issues

See [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for full coverage.
Common deploy-time issues:

- **Bot exits with code 4** (`DISCORD_TOKEN` missing) — set the token in
  `.env` and `docker compose up -d` again.
- **Phoenix dashboards empty** — `OBSERVABILITY_ENABLED=true` not set,
  or `OTEL_EXPORTER_OTLP_ENDPOINT` pointing at the wrong host (use
  `host.docker.internal:6006/v1/traces` if both compose stacks run on
  the same machine).
- **Bot can't reach oMLX from inside the container** — Linux operators
  must keep the `extra_hosts: host-gateway` mapping intact; the bot
  uses `host.docker.internal:8765`.
- **`sqlite3.OperationalError: database is locked`** — bump
  `ELDRITCH_DB_BUSY_TIMEOUT_MS` higher; only one process should be
  writing to `eldritch.sqlite3` at a time.
- **OCR tests skip in CI** — expected. The `[dev]`-only install path
  has no OCR backend; tests self-skip via `importorskip`.

## Cross-references

- [`INSTALL.md`](../INSTALL.md) — Discord-token setup, oMLX install,
  dm20 install, ingest backend selection (D-27).
- [`docs/UPGRADE.md`](UPGRADE.md) — per-version operator actions
  (e.g. v1.0 → v1.1 `pc_classes` backfill).
- [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — 14 FAQ entries
  grounded in real v1.0-v1.9 SUMMARY surface.
- [`docs/PERFORMANCE.md`](PERFORMANCE.md) — v1.9 budget table + the
  `eldritch-dm-perf-baseline` CLI surface.
- [`docs/CONFIGURATION.md`](CONFIGURATION.md) — every env var the
  Docker `.env` can carry.
- [`CHANGELOG.md`](../CHANGELOG.md) — Keep-a-Changelog rolling release
  log (v1.0 → v1.11).
