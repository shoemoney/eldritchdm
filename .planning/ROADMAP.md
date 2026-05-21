# Roadmap: EldritchDM

**Created:** 2026-05-21
**Granularity:** fine
**Total phases:** 11
**Coverage:** 87/87 v1 requirements mapped

## Core Value

Mechanically honest AI DM — narration is evocative, but every die roll, HP change, AC check, and turn boundary is enforced by deterministic Python code; the LLM never touches the math.

## Phases

- [ ] **Phase 1: Persistence Foundation** - SQLite WAL schema, single-writer queue, repositories, per-session locks
- [ ] **Phase 2: Pure Rules Engine** - Hermetic dice, attack, dodge, riposte, initiative, skill check resolvers
- [ ] **Phase 3: Inference Layer** - oMLX client, prompt assembler, tool dispatcher, no-math validator, injection sanitizer, ShoeGPT persona
- [ ] **Phase 4: Session Manager & State Machine** - FSM (LOBBY/EXPLORATION/COMBAT_INIT/COMBAT) wired to persistence + engine + inference, driven by synthetic tests
- [ ] **Phase 5: Discord Scaffold** - Bot, cogs, embed renderers, defer discipline, persistent View infrastructure
- [ ] **Phase 6: Lobby Flow** - `/start_game`, ready-check, transition to EXPLORATION with 3-room blueprint
- [ ] **Phase 7: Character Ingest** - ocrmac/PyMuPDF pipeline, LLM JSON translation, manual-entry fallback
- [ ] **Phase 8: Exploration State** - Action-batching modals, keyword skill checks, unified narration
- [ ] **Phase 9: Combat State** - CR-budgeted encounters, initiative, turn gating, attack flow, 8-player load proof
- [ ] **Phase 10: Memory & Open5e Rules** - Campaign memory ACL, rolling summarization, Open5e cache-first lookup, reactions
- [ ] **Phase 11: Self-Host Packaging** - README, .env.example, bootstrap, run.py, supervisor recipes, full test suite

## Phase Details

### Phase 1: Persistence Foundation
**Goal**: A correct, single-writer SQLite persistence layer that supports concurrent multi-channel sessions with zero writer contention
**Depends on**: Nothing (foundation)
**Requirements**: DB-01, DB-02, DB-03, DB-04, DB-05, DB-06, DB-07, DB-08
**Success Criteria** (what must be TRUE):
  1. The four tables (`game_sessions`, `characters`, `combat_monsters`, `campaign_memory`) exist with PRD-correct columns and constraints
  2. Every connection sets `journal_mode=WAL` and `busy_timeout=5000`; a single asyncio writer task drains all write transactions
  3. Every write uses `BEGIN IMMEDIATE`; no transaction ever spans an `await` to an external service
  4. The multi-channel concurrent stress test (≥4 channels writing simultaneously for ≥60s) completes with zero `database is locked` errors
  5. Repository classes exist per aggregate (Session, Character, Monster, Memory) using `aiosqlite`, and pure reads take no per-session lock
**Plans**: TBD

### Phase 2: Pure Rules Engine
**Goal**: A hermetic, fully unit-tested Python module that resolves every 5e mechanical outcome the bot will ever need — with zero coupling to Discord, persistence, or inference
**Depends on**: Phase 1 (engine writes flow through repositories)
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-04, ENG-05, ENG-06, ENG-07, ENG-08, ENG-09, ENG-10, ENG-11, ENG-12
**Success Criteria** (what must be TRUE):
  1. Dice notation `NdM+K` plus advantage/disadvantage/reroll resolves correctly across a property-based test suite
  2. Attack resolver applies natural-20 crit (doubled damage dice), natural-1 auto-miss, and AC comparison; damage application updates HP via repository
  3. Dodge sets `is_dodging=1`, forces disadvantage on incoming attacks, and auto-clears on the dodger's next turn start
  4. Initiative sorts by `1d20+DEX mod`, with DEX-then-random tie-breaking; reactions recharge at each actor's turn start; riposte eligibility correctly gates Fighter/Battle Master and Rogue Swashbuckler
  5. `engine/` has no imports from `orchestrator/`, `persistence/`, or `inference/` (enforced by an import-linter rule); crit/miss/dodge/riposte branches have 100% unit-test coverage
**Plans**: TBD

### Phase 3: Inference Layer
**Goal**: A hardened oMLX client that produces ShoeGPT narration with zero math leakage, zero prompt-injection vectors, and reliable tool-call dispatch — even when the inference server crashes
**Depends on**: Phase 1 (memory writes), Phase 2 (tool-call return shapes)
**Requirements**: INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, INF-01, INF-02, INF-03, INF-04, INF-05, INF-06, INF-07, INF-08, INF-09, INF-10, INF-11, INF-12
**Success Criteria** (what must be TRUE):
  1. `httpx` async client targets `http://localhost:8765/v1` with `ShoeGPT` model id, env-configurable, with `(connect=2s, read=20s, write=5s)` timeouts and tenacity retries
  2. Native `response.tool_calls` is the primary dispatch path; structured `<tool_call>{json}</tool_call>` parser is wired as a fallback but disabled for turns containing user free-text
  3. No-math validator rejects/strips unsanctioned digits, HP/AC keywords, and out-of-context entity names on every narration; the ≥50-scenario adversarial corpus passes in CI
  4. Player free-text is wrapped in `<player_action>` sentinels, capped at 500 chars, with control tokens (`<tool_call>`, `<|im_start|>`, `SYSTEM:`, `ASSISTANT:`) stripped before prompt assembly
  5. 60s health-check ping runs in background; on consecutive failures the circuit breaker falls back to templated narration and a `bound` structlog context records the degradation
  6. `asyncio.Semaphore(1)` serializes inference calls and a "ShoeGPT is thinking…" hook is exposed for the orchestrator to surface to Discord
**Plans**: TBD

### Phase 4: Session Manager & State Machine
**Goal**: A persistence-driven FSM that wires Engine + Inference + Persistence into a coherent session lifecycle, verifiable end-to-end without Discord
**Depends on**: Phases 1, 2, 3
**Requirements**: STATE-01, STATE-02, STATE-03, STATE-04, STATE-05
**Success Criteria** (what must be TRUE):
  1. Every FSM transition (LOBBY → EXPLORATION → COMBAT_INIT → COMBAT → EXPLORATION) is persisted to `game_sessions.state` immediately and atomically
  2. On startup, the SessionManager rehydrates every `state != 'LOBBY'` session — characters, combatants, initiative, conditions, and active timers (riposte deadlines)
  3. Active reaction timers resume from stored expiry timestamps and fire correctly post-restart (or clean themselves if expired)
  4. A synthetic test harness can drive a full LOBBY → COMBAT → EXPLORATION cycle without instantiating a Discord client, asserting every mechanical outcome
  5. The "kill bot mid-combat, restart, click next button" drill resolves the click correctly against the restored state
**Plans**: TBD

### Phase 5: Discord Scaffold
**Goal**: A `discord.py 2.7.1` bot wired with slash commands, persistent Views, embed coalescer, and lint-enforced defer discipline — so no callback ever trips the 3s ack cliff
**Depends on**: Phase 4
**Requirements**: INFRA-06, BOT-01, BOT-02, BOT-03, BOT-04, BOT-05, BOT-06, BOT-07, BOT-08
**Success Criteria** (what must be TRUE):
  1. Bot boots, registers the slash-command tree, and a CI lint rule enforces `await interaction.response.defer(thinking=True)` as the first line of every interaction callback
  2. `DynamicItem` regex `custom_id` templates (EndTurn, Riposte, Ready) are registered in `setup_hook`; active sessions are reloaded from DB and `bot.add_view(view, message_id=...)` is called per persisted message
  3. Embed renderer templates exist for lobby card, room state, combat tracker, and character confirmation; the per-message coalescer limits edits to ≤1/sec
  4. Out-of-turn or otherwise invalid clicks return an ephemeral warning card and never reach Engine
  5. The kill-and-restart-mid-combat drill succeeds: buttons on existing Discord messages continue to function after a fresh bot process
**Plans**: TBD
**UI hint**: yes

### Phase 6: Lobby Flow
**Goal**: A polished `/start_game` flow that gets players from "command invoked" to "EXPLORATION engaged with a 3-room blueprint" with zero ambiguity
**Depends on**: Phase 5
**Requirements**: LOBBY-01, LOBBY-02, LOBBY-03, LOBBY-04
**Success Criteria** (what must be TRUE):
  1. `/start_game` initializes a new session row in the calling channel and posts the lobby embed with upload instructions
  2. Players mark ready via a persistent button; the lobby card updates within ≤1s of each ready click
  3. When all joined players are marked ready, the session transitions to EXPLORATION atomically and a 3-room campaign blueprint is generated and persisted
  4. Restarting the bot mid-lobby leaves the ready buttons functional and preserves who-is-ready state
**Plans**: TBD
**UI hint**: yes

### Phase 7: Character Ingest
**Goal**: A robust character sheet pipeline that converts PNG/JPG/PDF uploads into validated character rows in under 6 seconds — with manual entry as a first-class fallback
**Depends on**: Phase 5 (Discord upload surface), Phase 3 (LLM JSON translation)
**Requirements**: INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06, INGEST-07, INGEST-08, INGEST-09
**Success Criteria** (what must be TRUE):
  1. `ocrmac` is the primary OCR path on macOS; `easyocr` is reachable via the `linux-ocr` extra; OCR/PDF work runs on `ThreadPoolExecutor(max_workers=2)`
  2. `PyMuPDF` is the primary PDF parser with `pypdf` as MIT-licensed fallback; raw text flows to the LLM with `temperature=0.05`, `response_format=json_object`
  3. Pydantic validates the LLM JSON against the character schema with range checks on ability scores; invalid fields surface a structured error
  4. Low OCR confidence triggers a manual-entry modal as a first-class path (not a buried error); the modal collects every required stat with validation
  5. End-to-end ingest of a standard sheet completes in <6s; uploads are restricted to the DM role and confirmations are ephemeral
**Plans**: TBD
**UI hint**: yes

### Phase 8: Exploration State
**Goal**: The first end-to-end gameplay loop — players declare intents through modals, engine rolls skill checks, and ShoeGPT narrates a unified room outcome with zero math leakage
**Depends on**: Phases 4, 6, 7
**Requirements**: EXPLORE-01, EXPLORE-02, EXPLORE-03, EXPLORE-04, EXPLORE-05, EXPLORE-06, EXPLORE-07
**Success Criteria** (what must be TRUE):
  1. Each room renders a state embed and a `[💬 Declare Action]` button that opens a 500-char-capped text modal
  2. The keyword scanner detects skill-check intents (`steal`, `search`, `strike`, `sneak`, `run`, `climb`, `inspect`) and the engine auto-rolls `1d20 + relevant skill modifier`
  3. When all active players have submitted, intents + cached rolls are batched into one narration prompt; ShoeGPT renders atmospheric prose (<180 words) describing simultaneous actions
  4. Encounter triggers (auto-trap, hostile NPC, narrative choice) transition the session to COMBAT_INIT atomically
  5. No narration in this loop ever contains LLM-computed dice or HP — the validator gates every output
**Plans**: TBD
**UI hint**: yes

### Phase 9: Combat State
**Goal**: A rule-rigid combat loop that handles ≥8 simultaneous initiative rows, gates turns by user ID, and never produces a Discord 429 — the heaviest orchestration surface in the bot
**Depends on**: Phase 8
**Requirements**: COMBAT-01, COMBAT-02, COMBAT-03, COMBAT-04, COMBAT-05, COMBAT-06, COMBAT-07, COMBAT-08, COMBAT-09, COMBAT-12, COMBAT-13
**Success Criteria** (what must be TRUE):
  1. COMBAT_INIT computes a CR budget from party levels, queries the monster guide, mounts monsters into `combat_monsters` with full stat blocks, and rolls initiative for all actors (persisted to `turn_sequence`)
  2. The combat embed renders turn order, HP/AC per actor, and active conditions, and remains correct for 8+ initiative rows
  3. Action buttons (`Attack`, `Cast Spell`, `Dodge`, `End Turn`) function; the turn gatekeeper validates `interaction.user.id == turn_sequence[active_idx]` and ephemeral-warns otherwise
  4. Attack flow drops mechanical outcome from Engine within ~1s and follows with narration (<150 words); combat ends when all monsters reach HP≤0 or the party is defeated, transitioning back to EXPLORATION
  5. The 8-player load test sustains a full combat without any Discord 429 rate-limit errors (coalescer + 300–500ms debouncer holds)
**Plans**: TBD
**UI hint**: yes

### Phase 10: Memory & Open5e Rules
**Goal**: Campaign memory that survives 100-turn sessions plus a cache-first Open5e integration that lets the bot run fully offline — including the timed riposte reaction
**Depends on**: Phases 3, 9
**Requirements**: COMBAT-10, COMBAT-11, MEM-01, MEM-02, MEM-03, MEM-04, MEM-05, MEM-06, RULES-01, RULES-02, RULES-03, RULES-04, RULES-05
**Success Criteria** (what must be TRUE):
  1. `save_session_memory` persists ShoeGPT-detected plot events to `campaign_memory` with `entity_key`, `factual_note`, and `visibility` (`public` / `dm_only` / `user_id`); recall filters by requester
  2. Rolling summarization keeps the prompt under ~16k tokens through a 100-turn synthetic session with no context overflow
  3. The Open5e client uses a 2s timeout with tenacity retries; the local SRD cache ships with the project and is consulted first, so a full offline session completes end-to-end
  4. `lookup_open5e_rule` and `search_monster_guide` tools resolve spells/conditions/class features and return stat blocks usable directly by Combat
  5. On a monster miss against an eligible PC, the `[↩️ Riposte]` button surfaces for that PC only with an 8s TTL; the deadline is persisted in DB so the timer survives bot restart and the button cleans up on expiry
**Plans**: TBD

### Phase 11: Self-Host Packaging
**Goal**: A stranger can clone the repo, set two env vars, run one bootstrap command, and have a working EldritchDM pointed at their own oMLX server
**Depends on**: Phases 1–10
**Requirements**: INFRA-01, INFRA-07, HOST-01, HOST-02, HOST-03, HOST-04, HOST-05, HOST-06
**Success Criteria** (what must be TRUE):
  1. `pyproject.toml`, pinned `requirements.txt`, and `.env.example` exist; `.env.example` documents `DISCORD_TOKEN`, `OMLX_ENDPOINT` (default `http://localhost:8765/v1`), `OMLX_MODEL` (default `ShoeGPT`), and log level
  2. `python -m eldritch_dm.bootstrap` initializes the DB schema and downloads/refreshes the SRD cache idempotently
  3. `run.py` validates env, pings the inference server, and launches the bot — failing fast with a clear error if any precondition is missing
  4. README covers hardware tiers (M1/M2 16 GB → 7B model; M3/M4 36 GB+ → Gemma 4 default), macOS-primary install, Linux/CUDA "best effort" notes, and documents `launchd`/`tmux+watchdog` supervisor recipes for `omlx serve`
  5. The three test suites (`test_database.py`, `test_local_inference.py`, `test_gameplay_cycles.py`) run via `pytest` and pass on a clean clone
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Persistence Foundation | 0/0 | Not started | - |
| 2. Pure Rules Engine | 0/0 | Not started | - |
| 3. Inference Layer | 0/0 | Not started | - |
| 4. Session Manager & State Machine | 0/0 | Not started | - |
| 5. Discord Scaffold | 0/0 | Not started | - |
| 6. Lobby Flow | 0/0 | Not started | - |
| 7. Character Ingest | 0/0 | Not started | - |
| 8. Exploration State | 0/0 | Not started | - |
| 9. Combat State | 0/0 | Not started | - |
| 10. Memory & Open5e Rules | 0/0 | Not started | - |
| 11. Self-Host Packaging | 0/0 | Not started | - |

---
*Roadmap created: 2026-05-21*
