<!-- generated-by: gsd-doc-writer -->
# 🐉 Getting Started — From Clone to First Roll in ~10 Minutes

> 🎲 This guide picks up where the [README's 30-second quickstart](../README.md#-30-second-quickstart) leaves off. Same path, more checkpoints. By the end, **ShoeGPT will be narrating your first scene.**

If you just want the lightning version, the README has it. If you want to actually know what each step does — and how to verify it worked before moving on — read this. ⬇️

For the operator-grade install (oMLX, dm20, ingest-backend selection, full `.env` walkthrough), see [`INSTALL.md`](../INSTALL.md). For per-version operator actions, see [`docs/UPGRADE.md`](UPGRADE.md). For runtime problems, see [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md). For the rolling release log, see [`CHANGELOG.md`](../CHANGELOG.md).

---

## 🧰 Before You Start

You need three things up and running on this machine. **The full prereqs list, with versions and links, lives in the [README → Prerequisites](../README.md#-prerequisites) section** — don't skip it if you're new to this stack.

The short version:

- 🧠 **oMLX** serving `ShoeGPT` on `:8765`
- 🎲 **dm20-protocol** MCP server exposed by that same oMLX
- 🤖 A **Discord bot token** from [discord.com/developers/applications](https://discord.com/developers/applications)
- 🐍 Python 3.11+ and (recommended) `uv`

ℹ️ Don't have oMLX + dm20 running yet? Set those up first — `install.sh` will warn you if they're missing, but the bot can't actually run without them. [`INSTALL.md`](../INSTALL.md) has the deep-dive component install.

---

## 1️⃣ Clone the Repo

```bash
git clone https://github.com/shoemoney/EldritchDM.git DiscordDM
cd DiscordDM
```

✅ **Checkpoint:** `ls .env.example install.sh README.md` should list all three. If it doesn't, you're in the wrong directory.

---

## 🐳 Shortcut — Docker Compose (v1.10+)

If you'd rather skip the by-hand install and let Docker handle the Python venv:

```bash
cp .env.example .env
$EDITOR .env                                  # paste DISCORD_TOKEN
docker compose up -d
docker compose logs -f eldritch-bot
```

The bundled [`docker-compose.yml`](../docker-compose.yml) brings up a single `eldritch-bot` service against the host's oMLX + dm20 via `host.docker.internal:8765`. Linux users get parity via the built-in `extra_hosts: host-gateway` mapping. Persistent state (the local SQLite + caches) lives in the named volume `eldritch-data`.

✅ **Checkpoint:** `docker compose ps` shows `eldritch_bot` with `(healthy)`. The Dockerfile's `import eldritch_dm` healthcheck has run.

🐳 **Full docker-compose recipe + the optional Phoenix observability stack** → [`docs/DEPLOYMENT.md`](DEPLOYMENT.md).

If you went the Docker route, skip ahead to step 6️⃣ to invite the bot to a server. Everything below is for the by-hand install path.

---

## 2️⃣ Run the Installer

```bash
./install.sh
```

This script walks 8 phases — Python version check → `uv` install → `.venv` creation → dependency install → oMLX reachability ping → dm20 MCP tool count check → final hint. See the [README → Installation (the Verbose Tour)](../README.md#%EF%B8%8F-installation-the-verbose-tour) for the by-hand version.

✅ **Checkpoint:** the script ends with `✅ Installation complete.` and a numbered "Next steps" block. If you see ⚠️ warnings about oMLX or dm20 — fix those before continuing (the bot will start without them, but every interaction will say `🔌 DM is offline`).

🔎 **Manually verify oMLX + dm20 yourself:**

```bash
# 🧠 oMLX is up and ShoeGPT is loaded?
curl -s http://localhost:8765/v1/models | jq .
# → should list at least one model with id "ShoeGPT"

# 🛠️ dm20 is exposed via MCP?
curl -s http://localhost:8765/v1/mcp/tools | jq '. | length'
# → should be a number ≥ 116 (97 dm20 + 4 dice + 8 dnd + 1 fetch + a few extras)
```

If either of those returns nothing useful, jump to [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) → "Bot says DM is offline".

---

## 3️⃣ Fill in `.env`

```bash
cp .env.example .env
$EDITOR .env
```

At minimum, paste your `DISCORD_TOKEN`. Everything else has sane defaults that match oMLX on the same machine. Every variable, its default, and what it does is documented in [docs/CONFIGURATION.md](CONFIGURATION.md).

✅ **Checkpoint:** `grep -c '^DISCORD_TOKEN=replace-me' .env` should print `0`. If it prints `1`, you forgot to paste your real token. 🤫

🚨 **Never commit your real `.env`** — `.gitignore` excludes it, but double-check with `git status` before any push.

---

## 4️⃣ Bootstrap & Preflight

```bash
python -m eldritch_dm.bootstrap
```

This is the canonical 3-stage preflight (`src/eldritch_dm/bootstrap.py`):

1. **Env check** — `.env` loaded, `DISCORD_TOKEN` either set or noted as preflight-mode-only.
2. **oMLX + dm20 reachability** — pings `:8765/v1/models` and `:8765/v1/mcp/tools`.
3. **SQLite schema bootstrap** — wraps `python -m eldritch_dm.persistence.bootstrap`, which creates `./eldritch.sqlite3` (path comes from `ELDRITCH_DB_PATH`), applies [`database/schema.sql`](../database/schema.sql), enables WAL journaling, and logs a SHA-256 of the schema for audit. **Idempotent** — safe to run twice.

✅ **Checkpoint:** you should see `Bootstrap complete: /…/eldritch.sqlite3` at the end. Verify the tables landed:

```bash
sqlite3 eldritch.sqlite3 '.tables'
# → channel_sessions  combat_conditions  pc_classes  persistent_views
#   riposte_timers    sanitizer_audit

sqlite3 eldritch.sqlite3 'PRAGMA journal_mode;'
# → wal
```

🔬 **Why a separate DB?** This SQLite holds Discord-specific bookkeeping only (channel↔campaign mapping, persistent views, riposte timers, sanitizer audit, PC class lookup for Riposte eligibility). Gameplay state — HP, initiative, inventory, encounters — lives in dm20's `~/.omlx/dm.db` and is never touched by this bot. See [docs/ARCHITECTURE.md](ARCHITECTURE.md) for the full why.

---

## 5️⃣ Launch the Bot

```bash
python run.py
# or, equivalently
python -m eldritch_dm.bot
# or, once installed, the console script
eldritch-dm
```

✅ **Checkpoint:** you should see something like:

```text
🎲 EldritchDM connected as ShoeGPT#0001 — let the games begin!
```

If you see `discord.LoginFailure: Improper token has been passed` → wrong `DISCORD_TOKEN`. If the process starts but immediately reports `🔌 DM is offline` → oMLX isn't reachable. Both flavors are covered in [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

---

## 6️⃣ Invite the Bot to a Server

In the [Discord Developer Portal](https://discord.com/developers/applications) → your app → **OAuth2** → **URL Generator**, tick:

- ✅ `bot`
- ✅ `applications.commands`

…and for bot permissions: *Send Messages*, *Embed Links*, *Use External Emojis*, *Read Message History*.

Open the generated URL, pick a server you own, **Authorize**.

✅ **Checkpoint:** the bot appears as offline-but-present in your server's member list — until step 5 is running, at which point it goes online.

💡 **Pro tip for dev:** set `DISCORD_GUILD_IDS=<your-test-server-id>` in `.env` so slash commands register **instantly** instead of taking up to an hour to propagate globally.

---

## 7️⃣ Your First Session 🎬

Pick a text channel — that's your "table." One channel = one campaign. Then:

```text
/start_game name:"The Lost Mine"
```

You should see a lobby embed appear with a QR code (for any future browser-mode players) and a Discord **Join** button. Under the hood this just created a dm20 campaign, spun up a Claudmaster autonomous-DM session, and started dm20's Party Mode HTTP server on `PARTY_MODE_PORT` (default `:8080`).

✅ **Checkpoint:** the lobby embed is posted and the bot's row in `channel_sessions` says `state = 'LOBBY'`:

```bash
sqlite3 eldritch.sqlite3 'SELECT channel_id, campaign_name, state FROM channel_sessions;'
```

---

### 📜 Load an Adventure (optional but recommended)

```text
/load_adventure LMoP
```

LMoP = *Lost Mine of Phandelver* — the canonical "first 5e adventure." Other supported IDs: `CoS`, `HotDQ`, `PotA`, `OotA`, `ToA`, `WDH`, `WDMM`, `BGDIA`.

---

### 🧙‍♂️ Load Two Characters (one from D&D Beyond, one from a phone photo)

**Player A — D&D Beyond URL** (character sheet must be public):

```text
/upload_character_url url:https://www.dndbeyond.com/characters/12345
```

**Player B — phone photo of a printed sheet:**

```text
/upload_character_file
```

…then attach the JPEG/PNG/PDF. The OCR pipeline ([`ocrmac`](https://pypi.org/project/ocrmac/) on macOS, [`easyocr`](https://pypi.org/project/easyocr/) on Linux) extracts the text, the ingest backend (`OMLX_ENDPOINT` by default — see [CONFIGURATION.md → Ingest backend](CONFIGURATION.md#ingest-backend-d-27-v10)) translates it into the dm20 character schema, and you'll get a confirmation modal to review/tweak before saving.

✅ **Checkpoint:** both players appear in the lobby embed with green checkmarks. Hit the **Ready** button — the lobby transitions to `EXPLORATION` (you can confirm by re-running the `SELECT state FROM channel_sessions` query).

---

### 🌲 Exploration → First Combat → Riposte

ShoeGPT narrates the opening scene. Each player clicks **[ 💬 Declare Action ]**, types intent (max 500 chars, sanitizer strips any forged tool-call tokens), and submits. The bot batches actions over `EXPLORE_BATCH_WINDOW_SECONDS` (default `30`), pushes them to dm20 through Party Mode, and posts the narrated result.

When the scene calls for it, **combat triggers automatically**:

- 🎲 Bot rolls initiative, posts a turn tracker embed.
- 🚧 Turn gatekeeping: only the current actor's Discord ID can click `[⚔️ Attack]` / `[🛡️ Dodge]` / etc. Out-of-turn clicks get a private "❌ Not your turn yet."
- 🤔 **Streaming indicator** (v1.6+ — `STREAM_ENABLED=true` default): when the SmartMonsterDriver consults the LLM oracle, you'll briefly see `🤔 {name} is sizing up the party…` in the combat embed.
- 🗡️ **The riposte moment:** when a monster *misses* an eligible PC (Battle Master Fighter or Swashbuckler Rogue with a reaction available — homebrewable via `database/eligibility.yaml`), that player — and only that player — sees an ephemeral **[ ↩️ Riposte Counter-strike ]** button for `RIPOSTE_TTL_SECONDS` (default `8`).

✅ **Checkpoint #1:** between rounds, peek at `persistent_views`:

```bash
sqlite3 eldritch.sqlite3 'SELECT custom_id, view_class FROM persistent_views;'
```

Every active button has a row. This is what makes restart-survival work.

✅ **Checkpoint #2 (the cool one):** `Ctrl+C` the bot mid-combat. Run `python run.py` again. Initiative order, HP, conditions, **and the riposte timer** all resume exactly where you left off. 🎩✨

---

## 🆘 When Something Breaks

The full operator-grade troubleshooting tree lives in [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — 14 FAQ entries grounded in real v1.0-v1.9 SUMMARY surface. Common entries:

- 🔌 "DM is offline" / circuit breaker tripped
- 🛠️ Slash commands return "interaction failed"
- 🤖 `discord.LoginFailure: Improper token has been passed`
- 🪟 Slash commands don't appear in Discord
- 📸 OCR returns garbage
- 🔁 Bot restart and buttons don't work
- 🔒 `database is locked`
- 🚪 Port `:8080` conflict
- 📊 Cache hit rate is zero / Phoenix dashboards empty (v1.2+)
- 🛡️ Monster driver always picks random targets (v1.1+)
- 🗡️ Riposte button doesn't fire
- 💸 Cost calculator is off
- ⚡ perf-baseline regression alert (v1.9+)

For deeper investigation: set `LOG_LEVEL=DEBUG` and `LOG_FORMAT=console` in `.env`, restart, and re-read the logs — bound context (`channel_id`, `campaign_name`, `session_id`, `tool_name`) makes every event traceable.

---

## 🧭 Where to Go Next

- 📐 **Want to understand the three-brain split?** → [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- 🔧 **Tuning knobs, every env var explained?** → [docs/CONFIGURATION.md](CONFIGURATION.md)
- 🗺️ **Big-picture project tour + roadmap + non-goals?** → [README.md](../README.md)
- 🧪 **Run the tests** — `pytest` is fast (~10s); `RUN_STRESS=1 pytest` runs multi-channel + perf-profiler stress; `RUN_LOAD=1 pytest` runs the 8-player combat load test. Full guide: [docs/TESTING.md](TESTING.md).
- 🛠️ **Operator CLIs** — `eldritch-dm-cost-report`, `eldritch-dm-cache-stats`, `eldritch-dm-eval --baseline …`, `eldritch-dm-perf-baseline …`. See [docs/DEVELOPMENT.md → Operator CLIs](DEVELOPMENT.md#operator-clis).
- 🐳 **Deploying** — Docker compose + GitHub Actions matrix + Phoenix observability → [docs/DEPLOYMENT.md](DEPLOYMENT.md).
- 🔼 **Upgrading from an older version** → [docs/UPGRADE.md](UPGRADE.md) covers every v1.0 → v1.11 transition with concrete operator actions.
- 📜 **What shipped when** → [CHANGELOG.md](../CHANGELOG.md) (Keep-a-Changelog format, v1.0 onward).

🐉 **Now go roll some dice.** 🎲
