# 🐉 EldritchDM — ShoeGPT, Your Forever Dungeon Master

> 🎲 **An open-source, local-first Discord bot that runs full Dungeons & Dragons 5e games end-to-end with an AI Dungeon Master persona called *ShoeGPT*.** No API bills. No data leaves your machine. No more "sorry can't DM tonight." Just hit `/start_game` and roll initiative.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#-license)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Apple Silicon](https://img.shields.io/badge/Apple%20Silicon-optimized-black.svg?logo=apple)](https://www.apple.com/mac/)
[![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)](#-roadmap)

**Created with ♥ by [Jeremy Schoemaker](https://shoemoney.com)** — open source, MIT-licensed, contributions welcome. 🤝

---

## 🤔 What is this?

🎭 **EldritchDM** is the missing piece between "I want to play D&D" and "the whole party can show up at the same time." It's a Discord bot that wears the costume of an evocative, gritty, ancient Dungeon Master named **ShoeGPT** — but underneath that costume is a clockwork brain that *cannot* hallucinate HP, *cannot* forget your conditions, and *cannot* let illegal moves slip through.

🧠 The trick is the **three-brain architecture**:

| Brain | What it does | Tech |
|---|---|---|
| 🗣️ **The Voice** | Narrates the world, plays NPCs, paints scenes | [oMLX](https://github.com/macabdul9/omlx) running the `ShoeGPT` model (Gemma 4, 4-bit) on Apple Silicon |
| 🧮 **The Brain** | Computes every die roll, HP change, AC check, turn boundary | [`dm20-protocol`](https://github.com/Polloinfilzato/dm20-protocol) — a complete D&D 5e engine exposed as MCP tools |
| 🎮 **The Orchestrator** | This bot — speaks Discord, gatekeeps turns, surfaces timed reactions, ingests character sheets | `discord.py 2.7+` plus a small local SQLite for Discord-specific state |

🛡️ **The integrity contract:** ShoeGPT *narrates* what happens, but the math is always done by deterministic Python code. If a goblin hits an AC of 14, you can audit every step. If your fighter rolls a natural 20, the engine doubles the damage dice — not the LLM's imagination.

✨ **The differentiator:** EldritchDM adds Discord-native affordances that no AI-DM product currently ships:

- ⚔️ **Timed reactive Riposte button** — when a monster misses your Battle Master, a private 8-second button appears just for you. Click to counter-strike. Survives bot restarts. Pure D&D magic.
- 🔒 **Turn gatekeeping by Discord user ID** — only the current actor can click action buttons. Try out of turn? Ephemeral "❌ Not your turn yet."
- 📸 **Photo & PDF character ingest** — got a scanned sheet from a printed PDF or a phone snap of handwritten stats? OCR pipeline ingests it.
- 🌐 **D&D Beyond URL import** — paste a public character URL, done.
- 💀 **Full state recovery** — kill the bot mid-combat, restart it, all your buttons keep working. HP, initiative, conditions, riposte timers — everything resumes.

---

## 🚀 30-Second Quickstart

```bash
# 1️⃣ Clone
git clone https://github.com/shoemoney/eldritchdm.git
cd eldritchdm

# 2️⃣ Install everything (Python 3.11+, system deps, Python deps)
./install.sh

# 3️⃣ Configure
cp .env.example .env
$EDITOR .env   # ✏️ paste your Discord bot token, confirm oMLX URL

# 4️⃣ Bootstrap the local DB + verify dependencies
python -m eldritch_dm.bootstrap

# 5️⃣ Run
python run.py
```

🎉 Now invite the bot to a Discord server, type `/start_game` in a channel, and let the dice fall.

---

## 🏗️ Architecture in 60 Seconds

```text
                              ┌──────────────────────────────┐
                              │   👥 You + your D&D party    │
                              │       (Discord channel)      │
                              └──────────────┬───────────────┘
                                             │ slash commands, buttons, modals
                                             ▼
                              ┌──────────────────────────────┐
                              │  🎮 EldritchDM (this repo)   │
                              │  discord.py orchestrator     │
                              │  + tiny local SQLite (WAL)   │
                              │  for channel↔campaign state, │
                              │  view registry, ⏱️ riposte   │
                              │  timers, sanitizer audit     │
                              └──────────────┬───────────────┘
                                             │ HTTP — MCP tool calls
                                             ▼
                              ┌──────────────────────────────┐
                              │ 🧠 oMLX `:8765`              │
                              │   ├─ 🗣️  ShoeGPT model      │
                              │   │      (narration)         │
                              │   └─ 🛠️  MCP gateway         │
                              │          /v1/mcp/execute     │
                              └──────────────┬───────────────┘
                                             │ 116 tools across 5 servers
                ┌────────────────────┬───────┴────────┬───────────────────┐
                ▼                    ▼                ▼                   ▼
        ┌───────────────┐   ┌───────────────┐  ┌──────────┐      ┌───────────────┐
        │ 🧮 dm20       │   │ 🎲 dice       │  │ 📚 dnd   │      │ 🌐 fetch      │
        │ (97 tools)    │   │ (4 tools)     │  │ (8 tools)│      │ (1 tool)      │
        │ campaigns,    │   │ d20kh1,       │  │ SRD,     │      │ HTTP fetcher  │
        │ characters,   │   │ exploding,    │  │ monsters │      │               │
        │ combat,       │   │ keep-highest, │  │ by CR    │      │               │
        │ Claudmaster,  │   │ etc.          │  │          │      │               │
        │ Party Mode,   │   │               │  │          │      │               │
        │ adventures,   │   │               │  │          │      │               │
        │ rulebook RAG  │   │               │  │          │      │               │
        └───────────────┘   └───────────────┘  └──────────┘      └───────────────┘
```

🧩 **Why this is cool:** because dm20 already implements a complete D&D engine (~70% of what you'd think a custom AI DM needs), EldritchDM doesn't *reimplement* any of it. We just wrap it in a Discord skin, add the timed-reaction UI, and let oMLX narrate. It's the rare "stand on the shoulders of giants" project where the giants are already configured on your laptop.

---

## 📋 Prerequisites

Before installing EldritchDM, you need three things running on your machine. The install script will check for them and tell you if anything is missing. 🔍

### 🍎 Required hardware

- 🖥️ **Apple Silicon Mac** (M1/M2/M3/M4). Linux works "best effort" — see below.
- 🧠 **≥16 GB unified memory** for the 7B fallback model. **36 GB+** recommended to run the default `ShoeGPT` (Gemma 4 4-bit).
- 💾 **~25 GB free disk** for models + caches.

### 🛠️ Required software

| Dependency | Why | How to get it |
|---|---|---|
| 🐍 **Python 3.11+** | Runtime | `brew install python@3.11` |
| 🧠 **oMLX server** running on `:8765` | Hosts ShoeGPT + MCP gateway | [github.com/macabdul9/omlx](https://github.com/macabdul9/omlx) |
| 🎲 **dm20-protocol** MCP server exposed via oMLX | The 5e engine | [github.com/Polloinfilzato/dm20-protocol](https://github.com/Polloinfilzato/dm20-protocol) |
| 🤖 **Discord bot token** | You knew this one was coming | [discord.com/developers/applications](https://discord.com/developers/applications) |
| 🔧 **`uv`** (recommended) or `pip` | Python package manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

ℹ️ **Don't have oMLX + dm20 set up yet?** Check the [oMLX docs](https://github.com/macabdul9/omlx) and [dm20-protocol README](https://github.com/Polloinfilzato/dm20-protocol). On Jeremy's reference rig they're supervised by `launchd` as `com.user.omlx` so they survive reboots. The install script will warn you (not fail) if they're not running.

---

## ⚙️ Installation (the Verbose Tour)

### 🤖 The easy way

```bash
./install.sh
```

That's it. The script:

1. 🔎 Checks Python version (must be ≥3.11)
2. 🔎 Checks for `uv` (installs via official script if missing)
3. 🌱 Creates a `.venv/` virtualenv with `uv venv`
4. 📦 Installs all Python dependencies (`discord.py`, `httpx`, `aiosqlite`, `pydantic`, `tenacity`, `structlog`, `ocrmac` on macOS, `PyMuPDF`, `pypdf` as fallback, plus dev deps for tests/lint)
5. 🩺 Pings `:8765/v1/models` to verify oMLX is running and reports which model is loaded (should be `ShoeGPT`)
6. 🩺 Pings `:8765/v1/mcp/tools` to confirm dm20 is exposed (expects ≥97 dm20 tools)
7. 💡 Tells you exactly what to do next (copy `.env.example`, run `bootstrap`, run the bot)

If anything fails, the script tells you why in plain English (no cryptic exit codes). 💬

### 🧙 The "I want to know what's happening" way

If you want to do this by hand:

```bash
# 1) Make sure Python 3.11+ is your interpreter
python3 --version            # → Python 3.11.x or higher

# 2) Install uv if you don't have it (fast, hermetic, friendly)
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL                  # reload PATH

# 3) Create + activate a virtualenv
uv venv
source .venv/bin/activate

# 4) Install runtime + dev dependencies (when pyproject.toml exists)
uv pip install -e ".[dev,linux-ocr-fallback]"

# 5) (macOS) Install ocrmac native deps
uv pip install ocrmac

# 6) Verify oMLX + dm20 are reachable
curl -s http://localhost:8765/v1/models | jq .
curl -s http://localhost:8765/v1/mcp/tools | jq '. | length'   # should print a number ≥ 116

# 7) Configure
cp .env.example .env
$EDITOR .env

# 8) Initialize local DB
python -m eldritch_dm.bootstrap

# 9) Launch the bot
python run.py
```

If you see `🎲 EldritchDM connected as ShoeGPT#0001 — let the games begin!` in stdout, you win. 🏆

---

## 🔑 Configuration: the `.env` file

EldritchDM reads its config from environment variables, typically loaded from a `.env` file at the project root. **Never commit your real `.env` to git** — `.gitignore` excludes it by default. 🤫

Copy `.env.example` and edit:

```bash
cp .env.example .env
```

Then open it and fill in the secrets. Every variable, what it does, and a sane default:

| Var | Required | Default | What it does |
|---|---|---|---|
| `DISCORD_TOKEN` | ✅ | — | 🤖 Your Discord bot token. Treat like a password. |
| `OMLX_ENDPOINT` | ❌ | `http://localhost:8765/v1` | 🧠 Base URL of your oMLX server's OpenAI-compatible API |
| `OMLX_MODEL` | ❌ | `ShoeGPT` | 🗣️ Which model id to use for narration. Must already be loaded into oMLX. |
| `MCP_EXECUTE_URL` | ❌ | `http://localhost:8765/v1/mcp/execute` | 🛠️ Endpoint that runs MCP tool calls |
| `MCP_TOOLS_URL` | ❌ | `http://localhost:8765/v1/mcp/tools` | 📜 Endpoint that lists available MCP tools (used by health checks) |
| `ELDRITCH_DB_PATH` | ❌ | `./eldritch.sqlite3` | 💾 Path to the *local* Discord-state SQLite (the small one — not dm20's DB) |
| `LOG_LEVEL` | ❌ | `INFO` | 📝 `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FORMAT` | ❌ | `json` | `json` (structlog JSON for prod) or `console` (pretty colored for dev) |
| `OMLX_HEALTH_INTERVAL` | ❌ | `60` | ⏱️ Seconds between oMLX health pings |
| `OMLX_CIRCUIT_BREAKER_THRESHOLD` | ❌ | `3` | 🔌 Consecutive failures before circuit opens |
| `RIPOSTE_TTL_SECONDS` | ❌ | `8` | 🗡️ How long a riposte button stays clickable |
| `EMBED_EDIT_RATE_LIMIT` | ❌ | `1.0` | 📡 Max Discord embed edits per second per message |
| `MAX_MODAL_INPUT_CHARS` | ❌ | `500` | ✂️ Hard cap on player free-text in modals |
| `PARTY_MODE_PORT` | ❌ | `8080` | 🌐 Port dm20 Party Mode HTTP server listens on |

The full annotated template lives in [`.env.example`](.env.example).

---

## 🧪 First-Time Walkthrough — Your First Session

1. 🆕 **Invite the bot** to a Discord server you own. Give it the `bot` + `applications.commands` scopes plus permissions for *Send Messages*, *Embed Links*, *Use External Emojis*, and *Read Message History*.
2. 💬 **Pick a text channel** that'll be your "table." One channel = one campaign.
3. 🎬 `/start_game name:"The Cursed Vault"` — this:
   - Creates a new dm20 campaign 🗂️
   - Starts a Claudmaster autonomous-DM session 🧙
   - Spins up dm20's Party Mode server (HTTP/WS on `PARTY_MODE_PORT`) 🌐
   - Posts a lobby embed with a QR code (for any browser-mode players) and a Discord "Join" button
4. 📜 (Optional) `/load_adventure CoS` to load *Curse of Strahd*. Other supported IDs: `LMoP`, `HotDQ`, `PotA`, `OotA`, `ToA`, `WDH`, `WDMM`, `BGDIA`.
5. 🧙‍♂️ Each player loads a character:
   - **D&D Beyond import:** `/upload_character_url <https://www.dndbeyond.com/characters/12345>` (character must be set to public on DDB)
   - **Photo or PDF:** `/upload_character_file` and attach. OCR extracts the text, oMLX translates to JSON, you get a confirmation modal to review and tweak before saving.
   - **Manual entry:** just answer the modal questions.
6. ✅ Everyone clicks the **Ready** button. Lobby transitions to **EXPLORATION**.
7. 💬 ShoeGPT describes the opening scene. Each player clicks `[ 💬 Declare Action ]`, types what they want to do (max 500 chars), and submits.
8. 🎲 The bot batches actions, sends them to ShoeGPT through dm20's Party Mode queue, narrates the result. Combat triggers automatically when warranted.
9. ⚔️ In combat, the bot enforces turn order — only the current actor's Discord ID can click `[⚔️ Attack]`, `[🛡️ Dodge]`, etc. Out-of-turn clicks get a private "❌ Not your turn yet."
10. 🗡️ When a monster misses an eligible PC, that PC gets a private 8-second `[ ↩️ Riposte ]` button. Click to counter-strike. If you don't click, the button quietly disappears.
11. 💾 You can `Ctrl+C` the bot any time. Run `python run.py` again later — everything resumes exactly where it left off. Memory, HP, turn order, even the timed buttons. 🎩✨

---

## 🛠️ How It Works — Verbose Edition

### 🔌 The MCP Client (`src/eldritch_dm/mcp/`)

EldritchDM's spine is an async HTTP client that POSTs to oMLX's MCP execute endpoint:

```python
result = await mcp.call("dm20__combat_action",
                        session_id=session_id,
                        action="attack",
                        weapon="longsword",
                        target="goblin_3")
```

Under the hood: `httpx.AsyncClient` with `connect=2s`, `read=30s`, `write=5s` timeouts, [`tenacity`](https://github.com/jd/tenacity)-backed exponential retry on transient errors, structured exception types per tool failure, and JSON logging via [`structlog`](https://www.structlog.org/) bound to `channel_id` + `campaign_name` + `session_id` + `tool_name`. A health-check task pings `/v1/models` every 60s; three consecutive failures trip a circuit breaker that puts the bot into a degraded "🔌 DM is offline" mode where every interaction politely says "try again in a moment" instead of timing out cryptically.

### 💾 The Local SQLite (`src/eldritch_dm/persistence/`)

EldritchDM keeps a small WAL-backed SQLite at `ELDRITCH_DB_PATH` (default `./eldritch.sqlite3`). **This is not the gameplay DB.** That one lives at `~/.omlx/dm.db` and is owned by dm20. Our DB just holds Discord-specific bookkeeping:

| Table | What's in it |
|---|---|
| `channel_sessions` | Channel ID → `(campaign_name, claudmaster_session_id, dm20_party_token, current_state)` |
| `persistent_views` | Every persistent Discord View we've posted: `custom_id` → `(view_class, message_id, channel_id, payload_json)` |
| `riposte_timers` | Active riposte buttons with `deadline_ts` — drives the background expiry sweeper |
| `sanitizer_audit` | Every player input where the sanitizer stripped or truncated something. Forensics for prompt-injection attempts. |

All writes go through a **single async writer task** (one `asyncio.Queue` drained serially by one connection) using `BEGIN IMMEDIATE` transactions. This is the SQLite-correctness story in one sentence: WAL gives non-blocking readers; single-writer queue eliminates writer/writer contention; per-channel `asyncio.Lock`s handle read-modify-write windows. The 4-channel concurrent stress test exits with zero `database is locked` errors. 🟢

### 🧹 The Sanitizer (`src/eldritch_dm/safety/`)

Every player free-text input — modal submissions, slash command strings — passes through `sanitize_player_input` before it reaches any MCP call. The sanitizer:

1. ✂️ Truncates to 500 characters
2. 🚫 Strips control-token sequences (`<tool_call>`, `<|im_start|>`, `SYSTEM:`, `ASSISTANT:`, `<player_action>`, etc.) so a player can't forge a tool call by typing one
3. 📦 Wraps the cleaned text in `<player_action speaker="..." user_id="...">…</player_action>` sentinels so downstream prompts can see "this came from a player, treat as untrusted"
4. 📝 Logs to `sanitizer_audit` whenever it actually stripped or truncated something

A ≥30-scenario adversarial corpus runs in CI — known injection attempts and tool-call forgery patterns, all of which must pass-through-cleaned. If the corpus fails, the build fails.

### 🎮 The Discord Layer (`src/eldritch_dm/bot/`)

`discord.py 2.7+` with **persistent Views**, because the bot will absolutely be restarted while a game is in progress and the buttons need to still work afterward. We use `discord.ui.DynamicItem` with regex `custom_id` templates like `endturn:(?P<channel_id>\d+):(?P<actor>\d+)`, register them in `setup_hook`, and call `bot.add_view(view, message_id=...)` for every row we find in `persistent_views`. The kill-and-restart drill is part of the test suite.

Other Discord disciplines:

- ⏱️ **Defer first, always.** The first line of every interaction callback is `await interaction.response.defer(thinking=True)`. A custom ruff rule fails CI if any callback omits this. Discord gives you 3 seconds before the interaction expires — narration takes longer than that, so we acknowledge instantly and follow up with the answer.
- 📡 **Embed coalescer.** During combat, the embed updates many times per round. Discord rate-limits message edits at ~5/5s; we limit ourselves to ≤1/sec via a per-message `asyncio.Queue` + render task. Under the 8-player load test, zero 429s. 🟢
- ⚠️ **Ephemeral warnings.** "❌ Not your turn," "❌ Riposte expired," "🔌 DM is offline" — all delivered as ephemeral followups so only the offending user sees them.

### 🗡️ The Riposte Magic (`src/eldritch_dm/combat/riposte.py`)

This is the most fun piece. When dm20 resolves a monster's attack as a miss against an eligible PC (Fighter/Battle Master or Rogue/Swashbuckler) who has a reaction available, EldritchDM:

1. Inserts a row in `riposte_timers` with `deadline_ts = now() + RIPOSTE_TTL_SECONDS`
2. Posts an ephemeral message visible only to that PC's user, containing the `[ ↩️ Riposte Counter-strike ]` button
3. The button's `custom_id` includes the timer ID and is registered as a `DynamicItem`
4. A background sweeper task wakes at the deadline and removes the message
5. If the bot is killed before the deadline and restarted after, the sweeper picks up the still-pending row and either continues the wait or cleans up an expired one
6. On click, the bot calls `dm20__combat_action(reaction=true, weapon=primary)` and narrates the result

It's the kind of thing every D&D player wishes their VTT had. 🥹

---

## 🗺️ Roadmap

EldritchDM is in pre-alpha. Here's where we're going, in 5 phases:

| Phase | Name | What ships | Status |
|---|---|---|---|
| 1️⃣ | MCP Client + Local State | Async MCP wrapper, local SQLite, sanitizer | 🔵 In progress |
| 2️⃣ | Discord Scaffold + Persistent Views | Bot, slash commands, embed coalescer, restart-survival | ⚪ Not started |
| 3️⃣ | Lobby + Character Ingest | `/start_game`, DDB import, OCR/PDF pipeline | ⚪ Not started |
| 4️⃣ | Gameplay (Exploration + Combat) | Party Mode binding, action batching, turn gatekeeping, 8-player load | ⚪ Not started |
| 5️⃣ | Reactions + Self-Host Polish | Riposte timed UI, README, tests, launchd recipe | ⚪ Not started |

📜 Full details in [`.planning/ROADMAP.md`](.planning/ROADMAP.md) and [`.planning/REQUIREMENTS.md`](.planning/REQUIREMENTS.md). Planning artifacts are committed alongside the code — open them up to see *why* every decision was made. 🔍

---

## 🧪 Testing

```bash
# Default fast suite (<10s, runs on every commit)
pytest

# Including the stress tests (multi-channel concurrent writes, 8-player combat)
RUN_STRESS=1 pytest

# With coverage
pytest --cov=eldritch_dm --cov-report=term-missing

# Just the sanitizer adversarial corpus (a fun read on its own)
pytest tests/safety/test_sanitizer_corpus.py -v
```

CI runs the full suite plus lint (`ruff`) plus a custom rule that enforces `defer-first` discipline on every Discord callback.

---

## 🤝 Contributing

EldritchDM is open source under the MIT license. **Contributions are welcome and appreciated.** 💜

Before you open a PR:

1. 📖 Read `CLAUDE.md` and `.planning/PROJECT.md` for the architectural ground rules. The "**bot never computes game math**" rule is load-bearing — *every* mechanical effect must go through a dm20 MCP tool call.
2. 🧪 Make sure `pytest` passes and `ruff check` is clean.
3. 📝 Add tests. If you're adding a new MCP tool wrapper, add a mocked httpx test. If you're adding a Discord interaction, add a defer-discipline check.
4. 💬 Open an issue first for anything bigger than a bug fix — the roadmap is tight on purpose, and we want to make sure your work doesn't collide with planned phases.

🐛 **Bug reports**: please include your `LOG_LEVEL=DEBUG` log snippet, your oMLX `dm20` version (`dm20__check_for_updates`), and a minimal reproduction.

🌟 **Feature ideas**: open an issue with the prefix `[idea]`. Even if it doesn't land in v1, ideas in the issue tracker shape v2.

---

## 🎓 Inspiration & Credits

- 🧠 [**Polloinfilzato/dm20-protocol**](https://github.com/Polloinfilzato/dm20-protocol) — the actual D&D engine and the secret reason this project is small. Standing on the shoulders of giants.
- 🍎 [**macabdul9/oMLX**](https://github.com/macabdul9/omlx) — the Apple Silicon LLM server that makes local inference *not painful*.
- 🎲 [**dnd5eapi.co**](https://www.dnd5eapi.co/) — the SRD JSON API.
- 🎭 [**Avrae**](https://avrae.io/) — the original Discord D&D bot. We don't try to be Avrae; we try to be its weirder, AI-shaped cousin.
- 🪄 The countless DMs whose "you walk into the cave..." has filled a thousand basements with chip dust and bad accents. This is for you.

---

## 📜 License

MIT © 2026 Jeremy Schoemaker — see [LICENSE](LICENSE). Use it, fork it, sell it, run it on a beach somewhere. Just don't claim you invented the dice. 🎲

---

<p align="center">

  <em>"You hear the distant scrape of stone on stone. The torches flicker.</em><br>
  <em>You sense the Dungeon Master is</em> <strong>thinking…</strong> ⏳

</p>

<p align="center">

  🐉 <strong>Roll initiative.</strong> 🐉

</p>
