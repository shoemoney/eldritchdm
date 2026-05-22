<!-- generated-by: gsd-doc-writer -->
# Configuration

EldritchDM is configured entirely through environment variables, loaded by
`pydantic-settings` in `src/eldritch_dm/config.py`. Shell environment wins over
`.env` file content (standard `pydantic-settings` precedence). A single
`Settings` instance is cached per process via `get_settings()` and is `frozen=True`
— restart the bot to pick up changes.

`.env.example` in the project root is the canonical, hand-curated reference; this
document mirrors it and adds type/validation detail enforced by `config.py`.

## Required vs optional

`DISCORD_TOKEN` is the **only** variable that has no default and no fallback. If
it is missing, `Settings()` raises `pydantic.ValidationError` at import time and
the bot refuses to start.

Everything else has a sensible default. The Discord-only quickstart is:

```bash
cp .env.example .env
# edit .env, paste your DISCORD_TOKEN
python -m eldritch_dm.persistence.bootstrap
python run.py
```

## Variable reference

### Discord

| Variable | Type | Default | Required | Validation | Purpose / Gotchas |
|---|---|---|---|---|---|
| `DISCORD_TOKEN` | `str` | — | **Yes** | non-empty | Bot token from the Discord Developer Portal. Treat as a password; never commit. Regenerate immediately if leaked. Redacted by `Settings.__repr__`. |
| `DISCORD_APPLICATION_ID` | `int \| None` | `None` | No | parses to int | Optional; used by some slash-command sync tooling. Leave unset to let `discord.py` derive it from the token. |
| `DISCORD_GUILD_IDS` | `str` (CSV) | `""` | No | parsed via `Settings.guild_ids_list` | Comma-separated guild IDs to register slash commands to instantly. Empty → register globally (up to 1 h propagation). Recommended for dev: your test server's ID. |

### Network / endpoints (oMLX + MCP)

EldritchDM assumes an oMLX server is running locally that hosts the `ShoeGPT`
model **and** exposes the dm20 MCP toolbox. The default port `8765` is the
oMLX serve default on Jeremy's reference rig.

| Variable | Type | Default | Required | Validation | Purpose / Gotchas |
|---|---|---|---|---|---|
| `OMLX_ENDPOINT` | `AnyHttpUrl` | `http://localhost:8765/v1` | No | must parse as HTTP(S) URL | Base URL for the OpenAI-compatible chat API. Used for narration and character-sheet schema translation. Trailing `/v1` is part of the URL — do not strip it. |
| `OMLX_MODEL` | `str` | `ShoeGPT` | No | non-empty | Model id the bot requests for narration. Must already be loaded by oMLX — verify with `curl :8765/v1/models`. Per `CLAUDE.md` constraints, ShoeGPT is Gemma 4 4-bit under the hood. |
| `MCP_EXECUTE_URL` | `AnyHttpUrl` | `http://localhost:8765/v1/mcp/execute` | No | must parse as HTTP(S) URL | Endpoint that runs MCP tool calls. The bot expects dm20's full 97-tool surface to be available. |
| `MCP_TOOLS_URL` | `AnyHttpUrl` | `http://localhost:8765/v1/mcp/tools` | No | must parse as HTTP(S) URL | Endpoint that lists available MCP tools. Used by health checks and the `/ping` slash command. Smoke-test: `curl :8765/v1/mcp/tools \| jq '. \| length'`. |
| `OMLX_INGEST_MODEL` | `str \| None` | `None` (falls back to `OMLX_MODEL`) | No | non-empty when set | Override for low-temperature JSON-mode character-sheet OCR translation. Leave unset unless you need a different model for ingest than for narration. |
| `PARTY_MODE_PORT` | `PositiveInt` | `8080` | No | `> 0` | Port for dm20 Party Mode's HTTP server (browser-mode players). Discord-only sessions can leave this alone. <!-- VERIFY: if you want browser players, the port must be reachable from their network (port-forward, Tailscale, reverse proxy) — repo ships no networking config --> |
| `PARTY_POLL_INTERVAL_MS` | `PositiveInt` | `250` | No | `> 0` | Polling interval (ms) for `dm20__party_pop_action`. Lower = snappier, higher = nicer to CPU. 250 ms is the sweet spot. |

> Note: the assignment listed `PARTY_MODE_PORT` alongside the oMLX/MCP vars but
> it is a Party Mode HTTP port, not an oMLX port. It is grouped here for
> network-topology reasons (everything that opens a socket).

### Persistence

EldritchDM's SQLite holds **Discord-state only** — channel ↔ campaign mappings,
the persistent-view registry, riposte timers, sanitizer audit, and the local
condition shim table (e.g. `dodging`). **Gameplay state lives in dm20's
`~/.omlx/dm.db`** and EldritchDM never writes to it. Do not point
`ELDRITCH_DB_PATH` at dm20's database — schema mismatch will brick bootstrap
and cross-contaminate two unrelated migration histories.

The schema in `database/schema.sql` sets `PRAGMA journal_mode = WAL` and
`PRAGMA foreign_keys = ON` at bootstrap. WAL means concurrent readers (embed
refreshes) coexist with the serialized writer (aiosqlite).

| Variable | Type | Default | Required | Validation | Purpose / Gotchas |
|---|---|---|---|---|---|
| `ELDRITCH_DB_PATH` | `str` | `./eldritch.sqlite3` | No | path string | Path to EldritchDM's local SQLite. Created on first run by `python -m eldritch_dm.persistence.bootstrap`. **Do not share with dm20's `~/.omlx/dm.db`.** |
| `ELDRITCH_DB_BUSY_TIMEOUT_MS` | `PositiveInt` | `5000` | No | `> 0` | SQLite `busy_timeout` in ms. Default is fine for single-bot deployments; raise if you ever see `database is locked` under load. |
| `ELDRITCH_DB_CHECKPOINT_INTERVAL` | `NonNegativeInt` | `600` | No | `>= 0` | Periodic WAL checkpoint interval in seconds. `0` disables periodic checkpointing — not recommended (WAL file will grow without bound). |

### Logging

| Variable | Type | Default | Required | Validation | Purpose / Gotchas |
|---|---|---|---|---|---|
| `LOG_LEVEL` | `Literal["DEBUG","INFO","WARNING","ERROR"]` | `INFO` | No | one of the four literals | Logging verbosity. Pydantic rejects anything else (including lowercase). Use `DEBUG` when filing a bug report. |
| `LOG_FORMAT` | `Literal["json","console"]` | `console` | No | one of `json` / `console` | `console` = pretty colored output for dev; `json` = `structlog` JSON renderer for production / log shippers. Switch to `json` when running under launchd / systemd / Docker so logs are machine-parseable. |
| `LOG_FILE` | `str \| None` | `None` | No | path string when set | Optional log file path. If unset, logs go to stderr only. |

### Resilience tunables

These control the oMLX health-check + circuit-breaker subsystem. The circuit
breaker opens after N consecutive ping failures and causes the bot to reply
"🔌 DM is offline" to every interaction until oMLX recovers; it auto-closes on
the next successful ping.

| Variable | Type | Default | Required | Validation | Purpose / Gotchas |
|---|---|---|---|---|---|
| `OMLX_HEALTH_INTERVAL` | `PositiveInt` | `60` | No | `> 0` (seconds) | Seconds between oMLX health pings. Lower = faster failover, more background traffic. |
| `OMLX_CIRCUIT_BREAKER_THRESHOLD` | `PositiveInt` | `3` | No | `> 0` | Consecutive ping failures before the breaker opens. `3` is a conservative default; lower it if you want faster user-visible failure. |
| `MCP_RATE_LIMIT_MS` | `PositiveInt` | `200` | No | `> 0` (ms) | Minimum milliseconds between mutating MCP calls per channel (OPS-03). Prevents flooding dm20 with concurrent state-changing tool calls from one channel. **Discrepancy:** present in `config.py` but **not** documented in `.env.example` — treat the `config.py` default as authoritative until `.env.example` is updated. |

### Discord behavior

| Variable | Type | Default | Required | Validation | Purpose / Gotchas |
|---|---|---|---|---|---|
| `RIPOSTE_TTL_SECONDS` | `PositiveInt` | `8` | No | `> 0` | How long the riposte timed-button stays clickable. PRD default is 8 s. Increase if your players have slow connections; decrease for tighter pacing. |
| `EMBED_EDIT_RATE_LIMIT` | `PositiveFloat` | `1.0` | No | `> 0.0` | Max Discord embed edits per second per message (combat coalescer). Discord caps message edits at ~5/5 s per channel — keep this **≤ 1.0** to stay safely under the limit. |
| `MAX_MODAL_INPUT_CHARS` | `PositiveInt` | `500` | No | `> 0` | Hard cap on player free-text in modal inputs. Larger = more verbose; smaller = less prompt-injection surface. 500 is the sanitizer's tuned middle ground. |
| `EXPLORE_BATCH_WINDOW_SECONDS` | `PositiveInt` | `30` | No | `> 0` | How long to wait for additional player intents before resolving an exploration batch. 30 s = generous for thoughtful players; drop to 10–15 for snappier groups. |

### Dev / test

| Variable | Type | Default | Required | Validation | Purpose / Gotchas |
|---|---|---|---|---|---|
| `RUN_STRESS` | `bool` | `False` | No | `0` / `1` / `true` / `false` | Enables the slow stress test suite (`pytest -m slow`). Off by default to keep `pytest` fast. |
| `SANITIZER_VERBOSE_AUDIT` | `bool` | `False` | No | `0` / `1` / `true` / `false` | If true, the sanitizer logs **every** input (even clean ones) to the `sanitizer_audit` table. Noisy; useful when chasing injection attempts. |
| `OMLX_CACHE_STRATEGY` | (n/a) | unset | No | — | Documented in `.env.example` as a 🧪 advanced knob but **not** modelled in `config.py` Settings — currently ignored by the Python layer and only read by oMLX itself if you export it into the oMLX server's environment. |

## Defaults cross-check

Cross-checked `.env.example` against `src/eldritch_dm/config.py`:

| Variable | `.env.example` | `config.py` | Match |
|---|---|---|---|
| `OMLX_ENDPOINT` | `http://localhost:8765/v1` | `http://localhost:8765/v1` | yes |
| `OMLX_MODEL` | `ShoeGPT` | `ShoeGPT` | yes |
| `MCP_EXECUTE_URL` | `http://localhost:8765/v1/mcp/execute` | `http://localhost:8765/v1/mcp/execute` | yes |
| `MCP_TOOLS_URL` | `http://localhost:8765/v1/mcp/tools` | `http://localhost:8765/v1/mcp/tools` | yes |
| `OMLX_HEALTH_INTERVAL` | `60` | `60` | yes |
| `OMLX_CIRCUIT_BREAKER_THRESHOLD` | `3` | `3` | yes |
| `ELDRITCH_DB_PATH` | `./eldritch.sqlite3` | `./eldritch.sqlite3` | yes |
| `ELDRITCH_DB_BUSY_TIMEOUT_MS` | `5000` (commented) | `5000` | yes |
| `ELDRITCH_DB_CHECKPOINT_INTERVAL` | `600` (commented) | `600` | yes |
| `LOG_LEVEL` | `INFO` | `INFO` | yes |
| `LOG_FORMAT` | `console` | `console` | yes |
| `RIPOSTE_TTL_SECONDS` | `8` | `8` | yes |
| `EMBED_EDIT_RATE_LIMIT` | `1.0` | `1.0` | yes |
| `MAX_MODAL_INPUT_CHARS` | `500` | `500` | yes |
| `EXPLORE_BATCH_WINDOW_SECONDS` | `30` | `30` | yes |
| `PARTY_MODE_PORT` | `8080` | `8080` | yes |
| `PARTY_POLL_INTERVAL_MS` | `250` | `250` | yes |
| `MCP_RATE_LIMIT_MS` | **absent** | `200` | **mismatch — `.env.example` does not list this var** |
| `OMLX_CACHE_STRATEGY` | listed (commented) | **absent from Settings** | **mismatch — `.env.example` documents a var the Settings model does not consume** |

Action items implicit in the table above:

- Add `MCP_RATE_LIMIT_MS=200` to `.env.example` (with a 🧪 marker and the OPS-03 reference).
- Either drop `OMLX_CACHE_STRATEGY` from `.env.example` or add a corresponding
  `Settings` field that forwards it to the oMLX client. Currently setting it
  in `.env` does nothing inside the Python process.

## Per-environment overrides

EldritchDM does not ship `.env.development` / `.env.production` files. The
intended pattern is:

- **Local dev:** edit `.env`, run `python run.py` directly. `LOG_FORMAT=console`.
- **Self-host (long-running):** export real env vars from your process supervisor
  (launchd, systemd, Docker, etc.). `LOG_FORMAT=json` so logs are
  machine-parseable.

<!-- VERIFY: this repo ships no launchd plist, systemd unit, Dockerfile, or
     compose file — supervisor-specific configuration (e.g. `com.user.omlx`
     launchd plist, port-forwarding, reverse proxy, Tailscale) is operator-owned
     and lives outside the repo -->

## Runtime requirements

Per `CLAUDE.md` constraints, the runtime targets are:

- Python `>=3.11,<3.13`
- macOS Apple Silicon (primary). Linux/CUDA is secondary and best-effort —
  `mlx-lm` / oMLX will not install on Intel Mac or Linux.
- oMLX serving `ShoeGPT` (Gemma 4 4-bit quantized) at `http://localhost:8765/v1`
  with the dm20 MCP toolbox mounted.

## Accessing settings in code

```python
from eldritch_dm.config import get_settings

settings = get_settings()  # cached singleton; safe to call from anywhere
print(settings.omlx_model)            # "ShoeGPT"
print(settings.guild_ids_list)        # parsed list[int] from DISCORD_GUILD_IDS CSV
# print(settings.discord_token)       # raw value; never log this directly
print(repr(settings))                 # token is redacted in repr
```

`Settings` is `frozen=True` — mutating attributes raises `ValidationError`. For
test overrides, construct a fresh `Settings(...)` and inject it, or
`get_settings.cache_clear()` after monkeypatching the environment.
