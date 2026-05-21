# Requirements: EldritchDM

**Defined:** 2026-05-21 (post-MCP-pivot)
**Core Value:** Mechanically honest AI DM, on Discord, fully local. Bot never computes game math — all mechanical effects flow through `dm20` MCP tools.

## v1 Requirements

### MCP & Local State (MCP)

- [ ] **MCP-01**: Async MCP client posts to `http://localhost:8765/v1/mcp/execute` with `{tool_name, arguments}` payload
- [ ] **MCP-02**: `httpx.AsyncClient` with timeouts (connect=2s, read=30s, write=5s) and tenacity retry on transient errors
- [ ] **MCP-03**: Typed wrapper functions for every dm20 tool we use (campaign, character, combat, party-mode, claudmaster, library) — generated or hand-written, but type-checked
- [ ] **MCP-04**: Error mapping: dm20 tool errors surface as structured exceptions with tool_name + arg snapshot for logging
- [ ] **MCP-05**: Health-check ping (`fetch__fetch` GET `:8765/v1/models`) every 60s; circuit-breaker trips after 3 consecutive failures; surface "DM is offline" embed
- [x] **MCP-06**: `structlog` JSON logging binds `channel_id`, `campaign_name`, `session_id`, `tool_name` on every MCP call
- [ ] **MCP-07**: Per-channel `asyncio.Lock` around MCP calls that mutate dm20 state (prevents concurrent `combat_action` clobbering each other)

### Local Discord-State Persistence (LOC)

- [x] **LOC-01**: SQLite (WAL) at `ELDRITCH_DB_PATH` (default `./eldritch.sqlite3`)
- [x] **LOC-02**: Schema tables (small, Discord-specific only):
  - `channel_sessions` (channel_id PK, campaign_name, claudmaster_session_id, dm20_party_token, state, created_at)
  - `persistent_views` (custom_id PK, view_class, message_id, channel_id, payload_json, created_at)
  - `riposte_timers` (id PK, channel_id, character_id, deadline_ts, monster_uuid, weapon_used, status)
  - `sanitizer_audit` (id PK, channel_id, user_id, raw_input, stripped_tokens, redacted_output, ts)
- [x] **LOC-03**: WAL + `busy_timeout=5000` + `BEGIN IMMEDIATE` for writes
- [x] **LOC-04**: Single-writer asyncio queue for `eldritch.sqlite3` writes
- [ ] **LOC-05**: Repositories per table using `aiosqlite` and pydantic v2 frozen models
- [x] **LOC-06**: `bootstrap.py` creates schema idempotently on startup

### Discord Scaffold (BOT)

- [x] **BOT-01**: `discord.py 2.7.1+` bot with slash command tree
- [x] **BOT-02**: Every interaction callback's first line is `await interaction.response.defer(thinking=True)` (lint-enforced via custom ruff/pre-commit rule)
- [x] **BOT-03**: Embed renderers: `lobby_embed`, `room_embed`, `combat_embed`, `character_confirm_embed`
- [x] **BOT-04**: Persistent Views: `discord.ui.DynamicItem` with regex `custom_id` templates, e.g. `endturn:(?P<channel_id>\d+):(?P<actor>\d+)`
- [x] **BOT-05**: `setup_hook` rehydrates active channel sessions from `channel_sessions`, calls `bot.add_view(view, message_id=...)` for every row in `persistent_views`
- [x] **BOT-06**: Embed update coalescer — per-message `asyncio.Queue` + render task limits edits to ≤1/sec/message
- [x] **BOT-07**: Ephemeral warning helper for invalid actions: `❌ Not your turn`, `❌ Riposte expired`, `❌ DM is thinking…`
- [x] **BOT-08**: Kill-and-restart-mid-combat test: bot process killed during a combat turn, restart, click buttons → flows continue

### Lobby (LOBBY)

- [ ] **LOBBY-01**: `/start_game` slash command — creates dm20 campaign via `dm20__create_campaign`, starts Claudmaster session via `dm20__start_claudmaster_session`, starts Party Mode via `dm20__start_party_mode`, records mapping in `channel_sessions`
- [ ] **LOBBY-02**: Optional `/load_adventure <id>` — runs `dm20__load_adventure` (CoS, LMoP, etc.)
- [ ] **LOBBY-03**: Lobby embed lists party-mode invite/QR (output of `start_party_mode`) AND a Discord-native "Join" persistent button
- [ ] **LOBBY-04**: Ready check: each player marks ready via persistent button; all-ready transitions to EXPLORATION and signals Claudmaster

### Character Ingest (INGEST)

- [ ] **INGEST-01**: `/upload_character_url <ddb_url>` slash command → `dm20__import_from_dndbeyond(url_or_id, player_name)`
- [ ] **INGEST-02**: `/upload_character_file` accepts PNG/JPG/PDF attachment for non-DDB sheets
- [ ] **INGEST-03**: `ocrmac` (Apple Vision) primary OCR on macOS; `easyocr` via `linux-ocr` extra
- [ ] **INGEST-04**: `PyMuPDF` primary PDF parse; `pypdf` MIT fallback
- [ ] **INGEST-05**: OCR/PDF work runs on `ThreadPoolExecutor(max_workers=2)` via `run_in_executor`
- [ ] **INGEST-06**: Extracted text passed to oMLX (`/v1/chat/completions`, response_format=json_object, temp=0.05) for schema translation
- [ ] **INGEST-07**: Pydantic validates LLM output; ability-score ranges checked; class/race verified against `dm20__get_class_info`/`get_race_info`
- [ ] **INGEST-08**: Manual-review modal: parsed fields rendered; player confirms or edits before `dm20__create_character` is called
- [ ] **INGEST-09**: Confidence-gated: low-confidence OCR triggers manual-entry modal as first-class path
- [ ] **INGEST-10**: Confirmations are ephemeral; uploads restricted to invoking player or DM
- [ ] **INGEST-11**: End-to-end ingest (image → dm20 character) completes in <8s for standard sheets

### Exploration State (EXPLORE)

- [ ] **EXPLORE-01**: Each room renders `room_embed` + `[ 💬 Declare Action ]` persistent button
- [ ] **EXPLORE-02**: Action button opens text modal (500-char cap); submission posts a Party Mode action via the dm20 queue
- [ ] **EXPLORE-03**: Bot polls `dm20__party_pop_action` (or subscribes if WS); on action, calls `dm20__party_thinking("ShoeGPT consults the ancient scrolls…")` and shows Discord "thinking" indicator
- [ ] **EXPLORE-04**: For combat-relevant turns, bot calls `dm20__party_get_prefetch(turn_id, outcome, roll, damage, target_hp)` for narrative speedup
- [ ] **EXPLORE-05**: Narrative returned via `dm20__party_resolve_action` → rendered in Discord embed
- [ ] **EXPLORE-06**: Action-batching: when multiple players have unresolved actions, bot waits up to 30s or until all party members have submitted before resolving, producing a single batched narrative
- [ ] **EXPLORE-07**: Combat trigger detected from dm20's game state transition → bot switches view to combat embed

### Combat State (COMBAT)

- [ ] **COMBAT-01**: On combat start (`dm20__start_combat`), bot reads `dm20__get_game_state` for initiative order, renders combat embed
- [ ] **COMBAT-02**: Combat embed shows turn order, HP/AC, conditions; supports 8+ initiative rows; refreshed via coalescer
- [ ] **COMBAT-03**: Action buttons `[⚔️ Attack]`, `[🧙 Cast Spell]`, `[🛡️ Dodge]`, `[⏭️ End Turn]` rendered with `custom_id` including current actor's user_id
- [ ] **COMBAT-04**: Turn gatekeeper validates clicker's Discord user_id == current actor (mapped via `channel_sessions` + `dm20__get_character.player_id`); else ephemeral warning
- [ ] **COMBAT-05**: Attack → weapon select modal → `dm20__combat_action(action="attack", weapon=..., target=...)`; narrative resolved via party-mode flow
- [ ] **COMBAT-06**: Dodge → `dm20__apply_effect(target=self, effect="dodging")` (verify dm20 supports this; else shim via condition); ends turn
- [ ] **COMBAT-07**: End Turn → `dm20__next_turn`
- [ ] **COMBAT-08**: 8-player Discord load test: combat embed updates 4× per round, zero 429 rate-limit errors
- [ ] **COMBAT-09**: Riposte detection: on monster attack resolution where target is eligible (Fighter/Battle Master, Rogue Swashbuckler — verified via `dm20__validate_character_rules`) and target has `has_reaction=true`, bot surfaces timed Riposte button
- [ ] **COMBAT-10**: Riposte button persists 8s with `deadline_ts` in `riposte_timers`; on click, bot calls `dm20__combat_action(reaction=true, weapon=primary)` (or shim if dm20 lacks reaction flag) — only target player can click
- [ ] **COMBAT-11**: Riposte timer survives bot restart — `riposte_timers` row drives a background task that cleans expired buttons on restart and any time before expiry
- [ ] **COMBAT-12**: Combat end detected from dm20 state transition; bot returns to EXPLORATION embed

### Sanitization & Safety (SAN)

- [ ] **SAN-01**: All player free-text (modals, chat) passes through `sanitize_player_input(raw) -> SanitizedInput` before reaching any MCP call
- [ ] **SAN-02**: Sanitizer strips control tokens: `<tool_call>`, `<|im_start|>`, `<|im_end|>`, `SYSTEM:`, `ASSISTANT:`, `<player_action>`, `</player_action>`
- [ ] **SAN-03**: 500-char hard cap on modal input; over-cap truncates with a flag
- [ ] **SAN-04**: Sanitizer wraps output in `<player_action speaker="..." user_id="...">…</player_action>` for downstream consumption
- [ ] **SAN-05**: Audit row written to `sanitizer_audit` whenever stripping occurs
- [ ] **SAN-06**: Adversarial test corpus (≥30 scenarios) for sanitizer in CI: injection attempts, tool-call forgery, sentinel breakout

### Self-Host (HOST)

- [ ] **HOST-01**: README with prerequisites: oMLX running on `:8765`, dm20 MCP exposed, ShoeGPT model loaded, Discord bot token
- [ ] **HOST-02**: `.env.example` documents `DISCORD_TOKEN`, `OMLX_ENDPOINT` (default `http://localhost:8765/v1`), `OMLX_MODEL` (default `ShoeGPT`), `MCP_EXECUTE_URL` (default `http://localhost:8765/v1/mcp/execute`), `ELDRITCH_DB_PATH`, log level
- [ ] **HOST-03**: `python -m eldritch_dm.bootstrap` initializes local Discord-state SQLite schema; pings oMLX + dm20 to verify
- [ ] **HOST-04**: `run.py` entrypoint validates env, pings oMLX, lists available dm20 tools, launches bot
- [ ] **HOST-05**: `pyproject.toml` pins all deps; `requirements.txt` generated for non-uv users
- [ ] **HOST-06**: Test suite runnable via `pytest`: MCP client tests (with httpx mock), sanitizer adversarial corpus, persistent-view restart drill, repository CRUD
- [ ] **HOST-07**: README covers macOS-primary install; Linux/CUDA "best effort" notes
- [ ] **HOST-08**: README documents launchd recipe for the Discord bot itself (parallel to existing `com.user.omlx`)

### Operational (OPS)

- [ ] **OPS-01**: Resume drill — kill bot mid-combat, restart, confirm turn order/HP/buttons all functional from `channel_sessions` + `dm20__get_claudmaster_session_state`
- [ ] **OPS-02**: Circuit breaker on dm20 unreachable: bot replies to all interactions with ephemeral "DM is offline, try again shortly" embed; auto-recovers on health-check restoration
- [ ] **OPS-03**: Per-channel rate-limit on MCP calls (max 1 mutating call per 200ms) to prevent dm20 thrashing under spam clicks
- [x] **OPS-04**: Graceful shutdown: cancel pending riposte timers, flush sanitizer audit, close DB

## v2 Requirements

Deferred to future release.

### Reactions Beyond Riposte
- **REACT-01**: Shield (reaction to attack)
- **REACT-02**: Counterspell
- **REACT-03**: Hellish Rebuke

### Expanded UI
- **EXUI-01**: Voice/TTS narration to voice channels (dm20 has `narrated`/`immersive` modes — needs Discord voice integration)
- **EXUI-02**: Map/grid visuals (dm20 has `show_map` — needs Discord rendering layer)
- **EXUI-03**: Per-player private DMs from the DM (`dm20__send_private_message` → Discord DM)
- **EXUI-04**: Mixed Discord + browser party (since we bind to Party Mode, this becomes plausible)

### Advanced Workflows
- **ADV-01**: `/load_adventure` polished UX with adventure browser
- **ADV-02**: Character sheet sync flow (`check_sheet_changes` / `approve_sheet_change`)
- **ADV-03**: Compendium pack import/export through Discord commands

## Out of Scope

| Feature | Reason |
|---------|--------|
| Own combat/dice/rules engine | dm20 + dice MCP already provide it — rebuild rejected after architectural review |
| Own SQLite schema for characters/sessions/monsters/memory | dm20 owns `~/.omlx/dm.db`; our DB is Discord-specific only |
| Own campaign memory / summarization | `dm20__add_session_note`, `summarize_session`, `party_knowledge` cover it |
| Own SRD lookups | `dm20__search_rules`, `get_*_info`, `dnd__*` cover it |
| LLM-computed math, dice, HP | The thesis — never |
| LLM-as-judge for rule disputes | Inconsistent; defer to dm20 + human table |
| Image/map generation | Scope; competes with inference for unified memory |
| Cross-server character portability | Local-first |
| Voice/TTS narration in v1 | Wrong surface for v1 |
| OAuth/SSO | Discord identity is the user model |
| Building our own MCP tools that overlap dm20 | If dm20 has a tool, we use it |

## Traceability

Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| (pending re-roadmap) | — | Pending |

**Coverage:**
- v1 requirements: ~55 total
- Mapped to phases: 0 (pending re-roadmap)
- Unmapped: ~55 ⚠️ (resolved by gsd-roadmapper after pivot)

---
*Requirements defined: 2026-05-21*
*Last updated: 2026-05-21 after MCP-hybrid pivot*
