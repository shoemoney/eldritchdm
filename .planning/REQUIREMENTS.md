# Requirements: EldritchDM

**Defined:** 2026-05-21
**Core Value:** Mechanically honest AI DM — narration is evocative, but every die roll, HP change, AC check, and turn boundary is enforced by deterministic Python code; the LLM never touches the math.

## v1 Requirements

### Infrastructure (INFRA)

- [ ] **INFRA-01**: Project scaffolded with `pyproject.toml`, pinned dependencies, `requirements.txt`, `.env.example`
- [ ] **INFRA-02**: Inference backend client targets oMLX (`omlx serve`) OpenAI-compatible API at `http://localhost:8765/v1`
- [ ] **INFRA-03**: Default model id is `ShoeGPT` (Gemma 4 4-bit quantized); endpoint and model are config-driven via env
- [ ] **INFRA-04**: `httpx` async client with timeouts (connect=2s, read=20s, write=5s) and tenacity-based retry
- [ ] **INFRA-05**: Health-check ping every 60s; circuit-breaker fallback to templated narration on consecutive failures
- [ ] **INFRA-06**: `structlog` JSON logging with bound session/channel context
- [ ] **INFRA-07**: README documents `launchd`/`tmux+watchdog` supervisor recipes for `omlx serve`

### Persistence (DB)

- [ ] **DB-01**: SQLite schema for `game_sessions`, `characters`, `combat_monsters`, `campaign_memory` matches PRD
- [ ] **DB-02**: WAL journal mode + `busy_timeout=5000` set on every connection
- [ ] **DB-03**: Single-writer asyncio queue funnels all write transactions (no writer/writer contention)
- [ ] **DB-04**: Per-session `asyncio.Lock` for read-modify-write windows; pure reads are lock-free
- [ ] **DB-05**: `BEGIN IMMEDIATE` for every write transaction; transactions never span `await llm_call()`
- [ ] **DB-06**: Repository layer per aggregate (Session, Character, Monster, Memory) using `aiosqlite`
- [ ] **DB-07**: Periodic `PRAGMA wal_checkpoint(TRUNCATE)`
- [ ] **DB-08**: Multi-channel concurrent stress test passes with zero `database is locked` errors

### Engine — Pure Rules (ENG)

- [ ] **ENG-01**: Dice parser supports notation `NdM+K`, advantage, disadvantage, reroll
- [ ] **ENG-02**: D20 attack resolver: natural 20 → crit (double damage dice), natural 1 → auto-miss, else sum vs AC
- [ ] **ENG-03**: Damage rolled with modifiers; HP applied to target via repository
- [ ] **ENG-04**: Dodge sets `is_dodging=1`, forces disadvantage on incoming attacks against that entity
- [ ] **ENG-05**: Dodge auto-clears on the dodger's next turn start
- [ ] **ENG-06**: Initiative roll = `1d20 + DEX modifier`, sorted desc, ties broken by DEX then random
- [ ] **ENG-07**: Riposte eligibility check (Fighter/Battle Master, Rogue Swashbuckler at v1)
- [ ] **ENG-08**: Riposte deducts `has_reaction=0`, rolls counter-attack with primary weapon
- [ ] **ENG-09**: Reactions recharge (`has_reaction=1`) at start of each actor's turn
- [ ] **ENG-10**: Skill check resolver: `1d20 + ability mod + proficiency` for relevant skill
- [ ] **ENG-11**: Engine module is hermetic — no imports from orchestrator, persistence, or inference layers
- [ ] **ENG-12**: 100% unit test coverage for crit/miss/dodge/riposte paths

### Inference (INF)

- [ ] **INF-01**: ShoeGPT persona system prompt loaded from `config/shoe_gpt_prompt.txt`
- [ ] **INF-02**: Jinja2 (or equivalent) prompt assembler templates exploration batches, combat events, NPC dialog
- [ ] **INF-03**: Tool-call dispatcher trusts native `response.tool_calls` (primary path on mlx-omni-server + Gemma 4)
- [ ] **INF-04**: Structured `<tool_call>{json}</tool_call>` content-string parser remains as defensive fallback
- [ ] **INF-05**: Tool registry exposes `lookup_open5e_rule`, `search_monster_guide`, `save_session_memory`
- [ ] **INF-06**: JSON-mode prompts (temperature 0.05) for character-sheet schema translation
- [ ] **INF-07**: Narration responses capped at 150 words; token cap enforced server-side and client-side
- [ ] **INF-08**: No-math output validator: regex strips/rejects unsanctioned digits, HP/AC keywords, out-of-context entity names
- [ ] **INF-09**: Adversarial test corpus (≥50 scenarios) for no-math validator runs in CI
- [ ] **INF-10**: Player free-text wrapped in `<player_action>` sentinels; control tokens stripped; 500-char cap per input
- [ ] **INF-11**: Tool-call content-string fallback disabled for turns containing user free-text (injection mitigation)
- [ ] **INF-12**: `asyncio.Semaphore(1)` around inference client; "ShoeGPT is thinking…" surfaced when held

### Discord UI (BOT)

- [ ] **BOT-01**: `discord.py 2.7.1` bot scaffolded with slash command tree
- [ ] **BOT-02**: Every interaction callback's first line is `await interaction.response.defer(thinking=True)` (lint-enforced)
- [ ] **BOT-03**: Rich embed renderer templates: lobby card, room state, combat tracker, character confirmation
- [ ] **BOT-04**: Persistent View infrastructure: `DynamicItem` regex `custom_id` templates registered in `setup_hook`
- [ ] **BOT-05**: On startup, active sessions are reloaded from DB and `bot.add_view(view, message_id=...)` called per persisted message
- [ ] **BOT-06**: Embed update coalescer: per-message `asyncio.Queue` + render task limits edits to ≤1/sec
- [ ] **BOT-07**: Ephemeral warning card for invalid actions (e.g., out-of-turn click): `❌ It is not your turn yet.`
- [ ] **BOT-08**: Kill-and-restart-mid-combat test: views remain functional after bot process restart

### Lobby (LOBBY)

- [ ] **LOBBY-01**: `/start_game` slash command initializes a new session in calling channel
- [ ] **LOBBY-02**: Lobby embed instructs players to upload character sheets (PNG/JPG/PDF)
- [ ] **LOBBY-03**: Ready check: players mark ready via persistent button; all-ready transitions to EXPLORATION
- [ ] **LOBBY-04**: On EXPLORATION transition, a 3-room campaign blueprint is generated and stored

### Character Ingest (INGEST)

- [ ] **INGEST-01**: `ocrmac` (Apple Vision) is the primary OCR path on macOS
- [ ] **INGEST-02**: `easyocr` available via `linux-ocr` extra for non-macOS hosts
- [ ] **INGEST-03**: `PyMuPDF` is primary PDF parser; `pypdf` retained as MIT-licensed fallback
- [ ] **INGEST-04**: OCR/PDF work runs on `ThreadPoolExecutor(max_workers=2)` via `run_in_executor`
- [ ] **INGEST-05**: Raw text passed to LLM for JSON-schema translation (temperature 0.05, response_format=json_object)
- [ ] **INGEST-06**: Pydantic validates LLM output against schema; range checks on ability scores
- [ ] **INGEST-07**: OCR confidence gate: low confidence triggers manual-entry modal as first-class path
- [ ] **INGEST-08**: Character upload restricted to DM role; confirmations are ephemeral
- [ ] **INGEST-09**: End-to-end ingest completes in <6s for standard sheets

### Exploration (EXPLORE)

- [ ] **EXPLORE-01**: Each room renders a state embed + `[ 💬 Declare Action ]` button
- [ ] **EXPLORE-02**: Action button opens text modal (500-char cap); user submission marks player Registered
- [ ] **EXPLORE-03**: Keyword scanner detects skill-check intents (`steal`, `search`, `strike`, `sneak`, `run`, `climb`, `inspect`)
- [ ] **EXPLORE-04**: Engine auto-rolls `1d20 + relevant skill modifier`; result cached against player intent
- [ ] **EXPLORE-05**: When all active players have submitted, intents + rolls batched into a single narration prompt
- [ ] **EXPLORE-06**: ShoeGPT renders unified atmospheric prose (<180 words) describing the simultaneous actions
- [ ] **EXPLORE-07**: Encounter triggers (auto-trap, hostile NPC, narrative choice) transition state to COMBAT_INIT

### Combat (COMBAT)

- [ ] **COMBAT-01**: COMBAT_INIT calculates CR budget from party levels, queries monster guide for matching threats
- [ ] **COMBAT-02**: Monsters mounted into `combat_monsters` with full stat blocks
- [ ] **COMBAT-03**: Initiative rolls for all actors; sequence persisted to `game_sessions.turn_sequence`
- [ ] **COMBAT-04**: Combat embed shows turn order, HP/AC per actor, active conditions; supports 8+ initiative rows
- [ ] **COMBAT-05**: Action buttons `[⚔️ Attack]`, `[🧙 Cast Spell]`, `[🛡️ Dodge]`, `[⏭️ End Turn]`
- [ ] **COMBAT-06**: Turn gatekeeper validates clicker's user ID == `turn_sequence[active_idx]`; otherwise ephemeral warning
- [ ] **COMBAT-07**: Attack: weapon select via dropdown, target select, engine resolves crit/dodge/AC math
- [ ] **COMBAT-08**: Engine returns event payload to inference layer; narration follows mechanical outcome (<150 words)
- [ ] **COMBAT-09**: Dodge button: marks `is_dodging=1`, ends turn, advances `active_idx`
- [ ] **COMBAT-10**: On monster miss against eligible PC, timed `[↩️ Riposte]` button surfaces for that PC only (8s TTL)
- [ ] **COMBAT-11**: Riposte deadline persists in DB so timeout survives restart; expiry cleans the button
- [ ] **COMBAT-12**: Combat ends when all monsters at HP≤0 or party defeated; transition back to EXPLORATION
- [ ] **COMBAT-13**: 8-player load test passes with zero Discord 429 rate-limit errors

### Memory (MEM)

- [ ] **MEM-01**: `campaign_memory` table stores `entity_key` + `factual_note` per channel
- [ ] **MEM-02**: `save_session_memory` tool invocation persists ShoeGPT-detected plot events
- [ ] **MEM-03**: Rolling context summarization keeps prompt under model's token budget (~16k working window)
- [ ] **MEM-04**: Memory recall surfaces relevant entries when entity keys appear in current prompt context
- [ ] **MEM-05**: Memory visibility tag: `public` / `dm_only` / `user_id`; recall filters by requester
- [ ] **MEM-06**: 100-turn synthetic session test: token count remains bounded; no context overflow

### Rules Database (RULES)

- [ ] **RULES-01**: Open5e REST client with 2s timeout, tenacity retry, structured error handling
- [ ] **RULES-02**: Local SRD cache shipped with project; first-look is cache, network only refreshes
- [ ] **RULES-03**: `lookup_open5e_rule` tool resolves spells, conditions, class features
- [ ] **RULES-04**: `search_monster_guide` returns stat blocks usable directly by combat engine
- [ ] **RULES-05**: Offline-mode session completes end-to-end using cache only

### State Recovery (STATE)

- [ ] **STATE-01**: All FSM transitions persisted to `game_sessions.state` immediately on change
- [ ] **STATE-02**: On bot restart, all `state != 'LOBBY'` sessions are rehydrated
- [ ] **STATE-03**: Persisted message IDs are re-registered with their views; existing Discord messages keep working
- [ ] **STATE-04**: Active timers (riposte deadlines) resume from stored expiry timestamps
- [ ] **STATE-05**: Resume drill: kill bot mid-combat, restart, confirm next button click resolves correctly

### Self-Host (HOST)

- [ ] **HOST-01**: README with hardware tiers (M1/M2 16 GB → 7B model; M3/M4 36 GB+ → Gemma 4 default)
- [ ] **HOST-02**: `.env.example` documents `DISCORD_TOKEN`, `OMLX_ENDPOINT` (default `http://localhost:8765/v1`), `OMLX_MODEL` (default `ShoeGPT`), log level
- [ ] **HOST-03**: `python -m eldritch_dm.bootstrap` initializes DB schema + downloads SRD cache
- [ ] **HOST-04**: `run.py` entrypoint validates env, pings inference server, launches bot
- [ ] **HOST-05**: Test suites runnable via `pytest`: `test_database.py`, `test_local_inference.py`, `test_gameplay_cycles.py`
- [ ] **HOST-06**: README covers macOS-primary install + Linux/CUDA "best effort" notes

## v2 Requirements

Deferred to future release.

### Spell Mechanics
- **SPELL-01**: Spell slot tracking
- **SPELL-02**: Concentration mechanics
- **SPELL-03**: Counterspell as a reaction

### Rest & Recovery
- **REST-01**: Short rest hit-die spend
- **REST-02**: Long rest full recovery

### Character Progression
- **PROG-01**: Level-up flow
- **PROG-02**: Multiclassing

### Expanded UI
- **EXUI-01**: Voice/TTS narration to voice channel
- **EXUI-02**: Map/grid visuals
- **EXUI-03**: Human-DM override dashboard

## Out of Scope

| Feature | Reason |
|---------|--------|
| Free-form "chat-as-DM" without state machine | Bypasses the three-brain integrity contract; reverts to ChatGPT-as-DM failure mode |
| LLM-computed math, dice, or HP | The architectural thesis — never |
| LLM-as-judge for rule disputes | Inconsistent rulings break trust; defer to Open5e + human table |
| Image/map generation | Scope explosion; competes with inference for unified memory |
| Cross-server character portability / cloud sync | Local-first; contradicts the privacy guarantee |
| Voice / TTS narration in v1 | Wrong surface for v1; Discord text is the medium |
| "Auto-DM mode" that plays without players | Defeats the point of the tool |
| Unbounded narration length | Hard 150-word cap; LLM rambling is a known anti-pattern |
| OAuth/SSO for bot access | Discord identity is the user model |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 11 | Pending |
| INFRA-02 | Phase 3 | Pending |
| INFRA-03 | Phase 3 | Pending |
| INFRA-04 | Phase 3 | Pending |
| INFRA-05 | Phase 3 | Pending |
| INFRA-06 | Phase 3 / Phase 5 | Pending |
| INFRA-07 | Phase 11 | Pending |
| DB-01 | Phase 1 | Pending |
| DB-02 | Phase 1 | Pending |
| DB-03 | Phase 1 | Pending |
| DB-04 | Phase 1 | Pending |
| DB-05 | Phase 1 | Pending |
| DB-06 | Phase 1 | Pending |
| DB-07 | Phase 1 | Pending |
| DB-08 | Phase 1 | Pending |
| ENG-01 | Phase 2 | Pending |
| ENG-02 | Phase 2 | Pending |
| ENG-03 | Phase 2 | Pending |
| ENG-04 | Phase 2 | Pending |
| ENG-05 | Phase 2 | Pending |
| ENG-06 | Phase 2 | Pending |
| ENG-07 | Phase 2 | Pending |
| ENG-08 | Phase 2 | Pending |
| ENG-09 | Phase 2 | Pending |
| ENG-10 | Phase 2 | Pending |
| ENG-11 | Phase 2 | Pending |
| ENG-12 | Phase 2 | Pending |
| INF-01 | Phase 3 | Pending |
| INF-02 | Phase 3 | Pending |
| INF-03 | Phase 3 | Pending |
| INF-04 | Phase 3 | Pending |
| INF-05 | Phase 3 | Pending |
| INF-06 | Phase 3 | Pending |
| INF-07 | Phase 3 | Pending |
| INF-08 | Phase 3 | Pending |
| INF-09 | Phase 3 | Pending |
| INF-10 | Phase 3 | Pending |
| INF-11 | Phase 3 | Pending |
| INF-12 | Phase 3 | Pending |
| BOT-01 | Phase 5 | Pending |
| BOT-02 | Phase 5 | Pending |
| BOT-03 | Phase 5 | Pending |
| BOT-04 | Phase 5 | Pending |
| BOT-05 | Phase 5 | Pending |
| BOT-06 | Phase 5 | Pending |
| BOT-07 | Phase 5 | Pending |
| BOT-08 | Phase 5 | Pending |
| LOBBY-01 | Phase 6 | Pending |
| LOBBY-02 | Phase 6 | Pending |
| LOBBY-03 | Phase 6 | Pending |
| LOBBY-04 | Phase 6 | Pending |
| INGEST-01 | Phase 7 | Pending |
| INGEST-02 | Phase 7 | Pending |
| INGEST-03 | Phase 7 | Pending |
| INGEST-04 | Phase 7 | Pending |
| INGEST-05 | Phase 7 | Pending |
| INGEST-06 | Phase 7 | Pending |
| INGEST-07 | Phase 7 | Pending |
| INGEST-08 | Phase 7 | Pending |
| INGEST-09 | Phase 7 | Pending |
| EXPLORE-01 | Phase 8 | Pending |
| EXPLORE-02 | Phase 8 | Pending |
| EXPLORE-03 | Phase 8 | Pending |
| EXPLORE-04 | Phase 8 | Pending |
| EXPLORE-05 | Phase 8 | Pending |
| EXPLORE-06 | Phase 8 | Pending |
| EXPLORE-07 | Phase 8 | Pending |
| COMBAT-01 | Phase 9 | Pending |
| COMBAT-02 | Phase 9 | Pending |
| COMBAT-03 | Phase 9 | Pending |
| COMBAT-04 | Phase 9 | Pending |
| COMBAT-05 | Phase 9 | Pending |
| COMBAT-06 | Phase 9 | Pending |
| COMBAT-07 | Phase 9 | Pending |
| COMBAT-08 | Phase 9 | Pending |
| COMBAT-09 | Phase 9 | Pending |
| COMBAT-10 | Phase 10 | Pending |
| COMBAT-11 | Phase 10 | Pending |
| COMBAT-12 | Phase 9 | Pending |
| COMBAT-13 | Phase 9 | Pending |
| MEM-01 | Phase 10 | Pending |
| MEM-02 | Phase 10 | Pending |
| MEM-03 | Phase 10 | Pending |
| MEM-04 | Phase 10 | Pending |
| MEM-05 | Phase 10 | Pending |
| MEM-06 | Phase 10 | Pending |
| RULES-01 | Phase 10 | Pending |
| RULES-02 | Phase 10 | Pending |
| RULES-03 | Phase 10 | Pending |
| RULES-04 | Phase 10 | Pending |
| RULES-05 | Phase 10 | Pending |
| STATE-01 | Phase 4 | Pending |
| STATE-02 | Phase 4 | Pending |
| STATE-03 | Phase 4 | Pending |
| STATE-04 | Phase 4 | Pending |
| STATE-05 | Phase 4 | Pending |
| HOST-01 | Phase 11 | Pending |
| HOST-02 | Phase 11 | Pending |
| HOST-03 | Phase 11 | Pending |
| HOST-04 | Phase 11 | Pending |
| HOST-05 | Phase 11 | Pending |
| HOST-06 | Phase 11 | Pending |

**Coverage:**
- v1 requirements: 87 total
- Mapped to phases: 87 ✓
- Unmapped: 0

Note: INFRA-06 (structlog) is foundational in Phase 3 (inference client uses bound context first) and reinforced in Phase 5 (Discord interaction routing adopts the same logger), but its single owning phase is **Phase 3**.

---
*Requirements defined: 2026-05-21*
*Last updated: 2026-05-21 — traceability populated by gsd-roadmapper*
