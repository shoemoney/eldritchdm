<!-- generated-by: gsd-doc-writer -->
# 🐉 Getting Started — From Clone to First Roll in ~10 Minutes

> 🎲 This guide picks up where the [README's 30-second quickstart](../README.md#-30-second-quickstart) leaves off. Same path, more checkpoints. By the end, **ShoeGPT will be narrating your first scene.**

If you just want the lightning version, the README has it. If you want to actually know what each step does — and how to verify it worked before moving on — read this. ⬇️

---

## 🧰 Before You Start

You need three things up and running on this machine. **The full prereqs list, with versions and links, lives in the [README → Prerequisites](../README.md#-prerequisites) section** — don't skip it if you're new to this stack.

The short version:

- 🧠 **oMLX** serving `ShoeGPT` on `:8765`
- 🎲 **dm20-protocol** MCP server exposed by that same oMLX
- 🤖 A **Discord bot token** from [discord.com/developers/applications](https://discord.com/developers/applications)
- 🐍 Python 3.11+ and (recommended) `uv`

ℹ️ Don't have oMLX + dm20 running yet? Set those up first — `install.sh` will warn you if they're missing, but the bot can't actually run without them.

---

## 1️⃣ Clone the Repo

```bash
git clone https://github.com/shoemoney/eldritchdm.git
cd eldritchdm
```

✅ **Checkpoint:** `ls .env.example install.sh README.md` should list all three. If it doesn't, you're in the wrong directory.

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

If either of those returns nothing useful, jump to the [README → 🩺 Troubleshooting](../README.md#-troubleshooting) section.

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

## 4️⃣ Bootstrap the Local SQLite

```bash
python -m eldritch_dm.persistence.bootstrap
```

This creates `./eldritch.sqlite3` (the path comes from `ELDRITCH_DB_PATH`), applies [`database/schema.sql`](../database/schema.sql), enables WAL journaling, and logs a SHA-256 of the schema for audit. **Idempotent** — safe to run twice.

✅ **Checkpoint:** you should see `Bootstrap complete: /…/eldritch.sqlite3` at the end. Verify the tables landed:

```bash
sqlite3 eldritch.sqlite3 '.tables'
# → channel_sessions  combat_conditions  persistent_views  riposte_timers  sanitizer_audit

sqlite3 eldritch.sqlite3 'PRAGMA journal_mode;'
# → wal
```

🔬 **Why a separate DB?** This SQLite holds Discord-specific bookkeeping only (channel↔campaign mapping, persistent views, riposte timers, sanitizer audit). Gameplay state — HP, initiative, inventory, encounters — lives in dm20's `~/.omlx/dm.db` and is never touched by this bot. See [docs/ARCHITECTURE.md](ARCHITECTURE.md) for the full why.

---

## 5️⃣ Launch the Bot

```bash
python run.py
```

✅ **Checkpoint:** you should see something like:

```text
🎲 EldritchDM connected as ShoeGPT#0001 — let the games begin!
```

If you see `discord.LoginFailure: Improper token has been passed` → wrong `DISCORD_TOKEN`. If the process starts but immediately reports `🔌 DM is offline` → oMLX isn't reachable. Both flavors are covered in [README → 🩺 Troubleshooting](../README.md#-troubleshooting).

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

…then attach the JPEG/PNG/PDF. The OCR pipeline ([`ocrmac`](https://pypi.org/project/ocrmac/) on macOS, [`easyocr`](https://pypi.org/project/easyocr/) on Linux) extracts the text, ShoeGPT translates it into the dm20 character schema, and you'll get a confirmation modal to review/tweak before saving.

✅ **Checkpoint:** both players appear in the lobby embed with green checkmarks. Hit the **Ready** button — the lobby transitions to `EXPLORATION` (you can confirm by re-running the `SELECT state FROM channel_sessions` query).

---

### 🌲 Exploration → First Combat → Riposte

ShoeGPT narrates the opening scene. Each player clicks **[ 💬 Declare Action ]**, types intent (max 500 chars, sanitizer strips any forged tool-call tokens), and submits. The bot batches actions over `EXPLORE_BATCH_WINDOW_SECONDS` (default `30`), pushes them to ShoeGPT through dm20's Party Mode queue, and posts the narrated result.

When the scene calls for it, **combat triggers automatically**:

- 🎲 Bot rolls initiative, posts a turn tracker embed
- 🚧 Turn gatekeeping: only the current actor's Discord ID can click `[⚔️ Attack]` / `[🛡️ Dodge]` / etc. Out-of-turn clicks get a private "❌ Not your turn yet."
- 🗡️ **The riposte moment:** when a monster *misses* an eligible PC (Battle Master Fighter or Swashbuckler Rogue with a reaction available), that player — and only that player — sees an ephemeral **[ ↩️ Riposte Counter-strike ]** button for `RIPOSTE_TTL_SECONDS` (default `8`). Click it for a counter-strike. Ignore it and it quietly vanishes.

✅ **Checkpoint #1:** between rounds, peek at `persistent_views`:

```bash
sqlite3 eldritch.sqlite3 'SELECT custom_id, view_class FROM persistent_views;'
```

Every active button has a row. This is what makes restart-survival work.

✅ **Checkpoint #2 (the cool one):** `Ctrl+C` the bot mid-combat. Run `python run.py` again. Initiative order, HP, conditions, **and the riposte timer** all resume exactly where you left off. 🎩✨

---

## 🆘 When Something Breaks

Don't reinvent the troubleshooting wheel — the **[README → 🩺 Troubleshooting](../README.md#-troubleshooting)** section already covers the common failure modes:

- 🔌 "DM is offline" / circuit breaker tripped
- 🛠️ Slash commands return "interaction failed"
- 🤖 `discord.LoginFailure: Improper token has been passed`
- 🪟 Slash commands don't appear in Discord
- 📡 HTTP 429 spam in logs
- 🔒 `database is locked`
- 📸 OCR returns garbage
- 🔁 Bot restart and buttons don't work
- 🚪 Port `:8080` conflict

For deeper investigation: set `LOG_LEVEL=DEBUG` and `LOG_FORMAT=console` in `.env`, restart, and re-read the logs — bound context (`channel_id`, `campaign_name`, `session_id`, `tool_name`) makes every event traceable.

---

## 🧭 Where to Go Next

- 📐 **Want to understand the three-brain split?** → [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- 🔧 **Tuning knobs, every env var explained?** → [docs/CONFIGURATION.md](CONFIGURATION.md)
- 🗺️ **Big-picture project tour, roadmap, non-goals?** → [README.md](../README.md)
- 🧪 **Run the tests** — `pytest` is fast (<10s); `RUN_STRESS=1 pytest` runs the 4-channel concurrent stress suite and the 8-player combat load test.

🐉 **Now go roll some dice.** 🎲
