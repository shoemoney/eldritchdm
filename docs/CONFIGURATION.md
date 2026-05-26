<!-- generated-by: gsd-doc-writer -->
# Configuration

EldritchDM is configured entirely through environment variables. The
authoritative loader is
[`src/eldritch_dm/config/__init__.py`](../src/eldritch_dm/config/__init__.py)
— a `pydantic-settings` `Settings` class that reads the shell environment
and the `.env` file at the project root (shell wins, standard
`pydantic-settings` precedence). The singleton is cached via
`get_settings()` and is `frozen=True` — restart the bot to pick up
changes.

`.env.example` in the project root is the curated reference; this
document documents every field the Settings class actually consumes plus
the environment variables read directly by ancillary modules
(observability, eval CLI, cost report).

Related docs:
[`INSTALL.md`](../INSTALL.md) ·
[`docs/UPGRADE.md`](UPGRADE.md) ·
[`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) ·
[`CHANGELOG.md`](../CHANGELOG.md).

## Required vs optional

`DISCORD_TOKEN` is the only variable that gates the bot from starting.
It is technically `Optional[str]` on the Settings class — preflight
(`python -m eldritch_dm.bootstrap`, `python run.py --check-only`) can
validate oMLX / dm20 / SQLite without a token — but `run.py main()` and
`python -m eldritch_dm.bot` refuse to call `bot.run(...)` if the token
is unset (D-26, see config docstring).

`OPENROUTER_API_KEY` is required only when `INGEST_BACKEND=openrouter`;
`Settings.resolve_ingest_config()` raises `ValueError` if the backend
is openrouter and the key is missing.

Everything else has a sensible default.

```bash
cp .env.example .env
$EDITOR .env                              # set DISCORD_TOKEN
python -m eldritch_dm.bootstrap           # 3-stage preflight + SQLite bootstrap
python run.py
```

## Discord

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `DISCORD_TOKEN` | `str \| None` | `None` | **Yes (at run time)** | Bot token from the Discord Developer Portal. Treat as a password; redacted by `Settings.__repr__`. |
| `DISCORD_APPLICATION_ID` | `int \| None` | `None` | No | Optional; used by slash-command sync tooling. Leave unset to let `discord.py` derive it from the token. |
| `DISCORD_GUILD_IDS` | `str` (CSV) | `""` | No | Comma-separated guild IDs for instant slash-command registration. Empty → register globally (~1h propagation). Parsed via `Settings.guild_ids_list`. |
| `DISCORD_OWNER_ID` | `int \| None` | `None` | No | Phase 22 / OPQOL-02: when set, the bot DMs this user on budget breach + degraded-mode transitions (rate-limited 1 DM/event-type/hour). Unset → log-only. |

## oMLX / MCP

EldritchDM assumes oMLX is running locally on `:8765`, hosting `ShoeGPT`
**and** mounting the dm20 MCP toolbox. Default port `8765` is the oMLX
serve default on the reference rig.

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `OMLX_ENDPOINT` | `AnyHttpUrl` | `http://localhost:8765/v1` | No | Base URL for the OpenAI-compatible chat API. The trailing `/v1` is part of the URL — do not strip it. |
| `OMLX_MODEL` | `str` | `ShoeGPT` | No | Model id requested for narration / ingest. Must already be loaded by oMLX — verify with `curl :8765/v1/models`. |
| `MCP_EXECUTE_URL` | `AnyHttpUrl` | `http://localhost:8765/v1/mcp/execute` | No | Endpoint that runs MCP tool calls. The bot expects the full dm20 tool surface. |
| `MCP_TOOLS_URL` | `AnyHttpUrl` | `http://localhost:8765/v1/mcp/tools` | No | Capability discovery endpoint. Smoke-test: `curl :8765/v1/mcp/tools \| jq '. \| length'`. |
| `OMLX_HEALTH_INTERVAL` | `PositiveInt` (s) | `60` | No | Seconds between oMLX health pings. Lower = faster failover, more background traffic. |
| `OMLX_CIRCUIT_BREAKER_THRESHOLD` | `PositiveInt` | `3` | No | Consecutive ping failures before the breaker opens and the bot replies `🔌 DM is offline`. |
| `OMLX_INGEST_MODEL` | `str \| None` | `None` | No | Legacy override for the character-sheet ingest model. Falls back to `OMLX_MODEL`. Superseded by `INGEST_MODEL_OVERRIDE`. |
| `MCP_RATE_LIMIT_MS` | `PositiveInt` (ms) | `200` | No | Minimum milliseconds between **mutating** MCP calls per channel (OPS-03). Prevents thrashing dm20 under spam clicks. |

## Ingest backend (D-27, v1.0+)

The character-sheet schema translator is the only direct LLM call site
in this codebase (dm20 owns narration internally). Three backends are
supported, all speak OpenAI-compatible Chat Completions:

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `INGEST_BACKEND` | `Literal["omlx","ollama","openrouter"]` | `omlx` | No | Selects the backend. `omlx` co-locates ingest + MCP on the same server. |
| `INGEST_ENDPOINT` | `AnyHttpUrl \| None` | derived from `INGEST_BACKEND` | No | Override the ingest endpoint. Defaults: omlx→`OMLX_ENDPOINT`; ollama→`http://localhost:11434/v1`; openrouter→`https://openrouter.ai/api/v1`. |
| `INGEST_MODEL_OVERRIDE` | `str \| None` | `None` | No | Override model id sent to ingest. For OpenRouter, use a full route (e.g. `anthropic/claude-3.5-sonnet`). Resolution: this → `OMLX_INGEST_MODEL` → `OMLX_MODEL`. |
| `OPENROUTER_API_KEY` | `str \| None` | `None` | **Yes when** `INGEST_BACKEND=openrouter` | Looks like `sk-or-v1-…`. Get one at https://openrouter.ai/keys. Redacted by `Settings.__repr__`. |

> ⚠️ dm20 MCP (the rules engine) is **always** at the oMLX endpoint
> (`OMLX_ENDPOINT + /mcp/execute`). Switching `INGEST_BACKEND` to
> `ollama` or `openrouter` does NOT move dm20 — oMLX must still be
> running locally.

## Persistence (local SQLite)

EldritchDM's SQLite stores **Discord-state only** — channel ↔ campaign
mapping, persistent views, riposte timers, sanitizer audit, the local
condition shim, character-cache snapshots. Gameplay state lives in
dm20's `~/.omlx/dm.db` and EldritchDM never writes to it. WAL is enabled
at bootstrap (`database/schema.sql`).

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `ELDRITCH_DB_PATH` | `str` | `./eldritch.sqlite3` | No | Path to EldritchDM's local SQLite. Created on first run by `python -m eldritch_dm.bootstrap`. |
| `ELDRITCH_DB_BUSY_TIMEOUT_MS` | `PositiveInt` (ms) | `5000` | No | SQLite `busy_timeout`. Raise if you see `database is locked` under load. |
| `ELDRITCH_DB_CHECKPOINT_INTERVAL` | `NonNegativeInt` (s) | `600` | No | Periodic `wal_checkpoint(TRUNCATE)` interval. `0` disables — not recommended. |

## Logging

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `LOG_LEVEL` | `Literal["DEBUG","INFO","WARNING","ERROR"]` | `INFO` | No | Verbosity. Pydantic rejects anything else (including lowercase). Use `DEBUG` when filing a bug report. |
| `LOG_FORMAT` | `Literal["json","console"]` | `console` | No | `console` = pretty colored dev output; `json` = `structlog` JSON for log shippers / Docker / launchd. |
| `LOG_FILE` | `str \| None` | `None` | No | Optional log file path. Unset → stderr only. |

## Gameplay knobs

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `RIPOSTE_TTL_SECONDS` | `PositiveInt` | `8` | No | How long the riposte timed button stays clickable. |
| `EMBED_EDIT_RATE_LIMIT` | `PositiveFloat` (edits/s) | `1.0` | No | Max embed edits per second per message. Discord caps at ~5/5s/channel — keep this ≤ 1.0. |
| `MAX_MODAL_INPUT_CHARS` | `PositiveInt` | `500` | No | Hard cap on player free-text in modal inputs. Sanitizer tuning. |
| `EXPLORE_BATCH_WINDOW_SECONDS` | `PositiveInt` | `30` | No | Window for action batching during exploration. |

## dm20 Party Mode

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `PARTY_MODE_PORT` | `PositiveInt` | `8080` | No | Port for dm20 Party Mode's HTTP server (browser-mode players). |
| `PARTY_POLL_INTERVAL_MS` | `PositiveInt` (ms) | `250` | No | Polling interval for `dm20__party_pop_action`. |

## Riposte eligibility (Phase 8 / HOMEBREW-01)

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `ELDRITCH_ELIGIBILITY_YAML` | `Path \| None` | `None` | No | Override path for the Riposte eligibility YAML. Unset → loader walks `~/.eldritch/eligibility.yaml` then in-repo `database/eligibility.yaml`. Hot-reloads via 60s mtime poll (v1.6). |

## Monster driver (Phase 10 / D-52, v1.1+)

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `MONSTER_DRIVER` | `Literal["smart","random","mixed"]` | `smart` | No | `smart` = LLM-routed targeting (default); `random` = v1.0 escape hatch; `mixed` = SmartMonsterDriver with per-monster INT-gating. Unknown values fall back to `smart` with a structured warning. |

## Streaming embed (Phase 19 / STREAM-03, v1.6+)

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `STREAM_ENABLED` | `bool` | `true` | No | When true (default), SmartMonsterDriver emits a `🤔 {name} is sizing up the party…` indicator while consulting the LLM oracle. Set false for v1.5 silent behavior. |

## Caches (v1.5)

The L1/L2 cache architecture introduced in v1.5. Every cache layer has a
fail-CLOSED allow-list and never caches mutable state or
mechanically-significant fields (D-117 / D-125 / D-129).

### MCP query cache — Phase 16 / MCPCACHE-01..03

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `MCPCACHE_ENABLED` | `bool` | `true` | No | Master gate for the L1 in-process LRU + optional L2. |
| `MCPCACHE_L1_SIZE` | `PositiveInt` | `512` | No | L1 LRU max entries. |
| `MCPCACHE_L1_TTL_S` | `PositiveInt` (s) | `300` | No | L1 TTL. |
| `MCPCACHE_L2_ENABLED` | `bool` | `false` | No | Opt-in aiosqlite WAL L2 (adds disk write cost). |
| `MCPCACHE_L2_TTL_S` | `PositiveInt` (s) | `86400` | No | L2 TTL (default 24h). |
| `MCPCACHE_L2_PATH` | `str` | `~/.eldritch/mcp_cache.sqlite` | No | L2 SQLite file. `~` expanded at use. |

### Character snapshot cache — Phase 17 / CHARCACHE-01..03

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `CHARCACHE_ENABLED` | `bool` | `true` | No | Standalone cache (D-119) for the 14-field static-only PC allow-list. |
| `CHARCACHE_PATH` | `str` | `~/.eldritch/character_cache.sqlite` | No | Cache SQLite file. `~` expanded. |
| `CHARCACHE_TTL_S` | `PositiveInt` (s) | `3600` | No | TTL short-circuit (D-123). |

Operator CLI: `eldritch-dm-cache-clear --characters` (purge), `--all` (purge everything).

### Narration response cache — Phase 18 / NARRCACHE-01..03

**OPT-IN.** Defaults to false (D-129). The riskiest cache in EldritchDM
— wrongly-cached responses could leak mechanical state. Gated both
on-store and on-serve by `NarrCacheGate` (fail-CLOSED regex
classifier).

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `NARRCACHE_ENABLED` | `bool` | `false` | No | Opt-in master gate. |
| `NARRCACHE_L1_SIZE` | `PositiveInt` | `256` | No | LRU max entries. |
| `NARRCACHE_L1_TTL_S` | `PositiveInt` (s) | `3600` | No | TTL. |

Operator CLIs: `eldritch-dm-cache-disable` (runtime kill-switch), `eldritch-dm-cache-stats` (live counters).

## Monster memory persistence (Phase 21 / MEM-03, v1.6+)

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `MONSTER_MEMORY_PERSIST` | `bool` | `false` | No | When true, MonsterMemory snapshots survive bot restart via aiosqlite. Off by default (D-160) keeps the bot self-contained. |
| `MONSTER_MEMORY_PATH` | `str` | `~/.eldritch/monster_memory.sqlite` | No | Memory snapshot DB. `~` expanded at use. |

## Observability (Phase 11 / OBS-01, v1.2+)

These are read directly by `eldritch_dm.observability.*`, **not** by the
Settings class. They are off by default; setting any of them costs
nothing in the cold-start path unless `OBSERVABILITY_ENABLED=true`.

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `OBSERVABILITY_ENABLED` | `bool` (str) | `false` | No | Master gate. Lazy-imports OTel; nothing else here is read until this is truthy. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `str` | `http://localhost:6006/v1/traces` (Phoenix default) | No | OTLP HTTP traces endpoint. Point at the Phoenix container from `docker-compose.observability.yml`. |
| `OBSERVABILITY_METRICS_ENDPOINT` | `bool` (str) | `false` | No | Opt-in for the local Prometheus `/metrics` HTTP endpoint (Phase 13 / MON-01). |
| `OBSERVABILITY_METRICS_BIND` | `str` | `127.0.0.1` | No | Bind interface for `/metrics`. |
| `OBSERVABILITY_METRICS_PORT` | `PositiveInt` | `9090` | No | Port for `/metrics`. |
| `ELDRITCH_SPAN_BUFFER_PATH` | `str` | (in-memory) | No | Optional path for the local span buffer (cost-report + degraded-mode read from this). |

Install extras: `pip install -e ".[observability]"` (or `uv pip install
-e ".[observability]"`).

## Cost guard (Phase 13 / MON-03, v1.2+)

Read directly by `eldritch-dm-cost-report` and by `eldritch_dm.bot.__main__`
at startup.

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `ELDRITCH_DAILY_LLM_BUDGET_USD` | `str` (decimal) | `5.00` | No | Daily spend cap. When exceeded, the bot trips degraded mode and (if `DISCORD_OWNER_ID` is set) DMs the operator. |

## Backfill CLI (v1.1+)

`eldritch-dm-backfill-pc-classes` resolves endpoints in this order
(`src/eldritch_dm/tools/backfill_pc_classes.py`):

| Variable | Default | Purpose |
|---|---|---|
| `DM20_MCP_URL` | (no default) | If set, overrides the dm20 MCP base URL the backfill connects to. |
| `OMLX_ENDPOINT` | `http://localhost:8765/v1` | Fallback if `DM20_MCP_URL` is unset. |

## Dev / test gates

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `RUN_STRESS` | `bool` | `false` | Enables `pytest.mark.skipif`-gated stress + slow tests (multi-channel concurrent writes, perf profiler self-check). |
| `RUN_LOAD` | `bool` | `false` | Enables the 8-player combat load test (`tests/integration/test_8player_load.py`). |
| `RUN_INTEGRATION` | `bool` | `false` | Enables the bot-restart drill (`tests/bot/test_restart_drill.py`). |
| `SANITIZER_VERBOSE_AUDIT` | `bool` | `false` | If true, the sanitizer logs every input (even clean ones) to `sanitizer_audit`. Noisy; useful for chasing injection attempts. |

See [docs/TESTING.md](TESTING.md) for the test-category map.

## Per-environment overrides

EldritchDM does not ship `.env.development` / `.env.production` files.
The intended pattern is:

- **Local dev:** edit `.env`, run `python run.py`. `LOG_FORMAT=console`.
- **Self-host (long-running, launchd / systemd):** export real env vars from
  the supervisor; `LOG_FORMAT=json`.
- **Docker (v1.10+):** the bundled `docker-compose.yml` mounts `.env`
  via `env_file:`. Inside the container, oMLX / dm20 on the host are
  reached via `host.docker.internal:8765` (Docker Desktop) or via the
  `extra_hosts: host-gateway` mapping (Linux Docker Engine). See
  [docs/DEPLOYMENT.md](DEPLOYMENT.md).

## Runtime requirements

- Python `>=3.11,<3.13` (see `pyproject.toml`).
- macOS Apple Silicon (primary). Linux/CUDA is secondary and best-effort —
  `mlx-lm` / oMLX do not install on Intel Mac or Linux.
- oMLX serving `ShoeGPT` at `http://localhost:8765/v1` with the dm20 MCP
  toolbox mounted.

## Accessing settings in code

```python
from eldritch_dm.config import get_settings

settings = get_settings()                # cached singleton
print(settings.omlx_model)               # "ShoeGPT"
print(settings.guild_ids_list)           # parsed list[int]
print(settings.resolve_ingest_config())  # IngestConfig dataclass (endpoint+model+api_key)
print(repr(settings))                    # token + openrouter key redacted
```

`Settings` is `frozen=True` — mutating attributes raises
`ValidationError`. For test overrides, construct a fresh `Settings(...)`
and inject it, or `get_settings.cache_clear()` after monkeypatching the
environment.
