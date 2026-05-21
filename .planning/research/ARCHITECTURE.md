# Architecture Research

**Domain:** Discord bot orchestrating local LLM + deterministic rules engine + persistent multi-channel game state
**Researched:** 2026-05-21
**Confidence:** HIGH (discord.py persistence, asyncio patterns, SQLite WAL semantics), MEDIUM (mlx-lm tool-calling — ecosystem is actively shifting), HIGH (general three-tier separation)

## Standard Architecture

EldritchDM is a **single-process async Python application** with one Discord client connection, one HTTP client to a co-located inference server, and one SQLite file. There is no microservice split; the "three brains" metaphor in the PRD is a *logical* boundary, not a network boundary. Putting Voice/Brain/Orchestrator in separate processes would be premature and would force IPC where a function call suffices.

The hard architectural problems are not about distributing work — they are:

1. Keeping the asyncio loop responsive while EasyOCR (CPU/GPU-bound, blocking) and LLM HTTP calls (latency-bound, awaitable) run.
2. Rehydrating Discord UI (Views with buttons) after a restart so a campaign mid-combat does not lose its interactive controls.
3. Serializing per-session writes to SQLite without serializing all sessions globally.
4. Making the LLM produce reliably parseable tool calls when the chosen backend (`mlx-lm.server`) has incomplete OpenAI function-calling parity.

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                          DISCORD (external)                          │
│   Gateway WebSocket  |  REST API  |  Interactions (buttons/modals)   │
└──────────────────────┬─────────────────────────────▲─────────────────┘
                       │ events                edits │
┌──────────────────────▼─────────────────────────────┴─────────────────┐
│                      ORCHESTRATOR LAYER  (asyncio)                    │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────────────┐  │
│  │  Cogs        │  │  View Registry │  │  Interaction Router       │  │
│  │ (/start_game │  │ (persistent    │  │ (custom_id -> handler)    │  │
│  │  /upload …)  │  │  views, rehyd.)│  │                           │  │
│  └──────┬───────┘  └────────┬───────┘  └────────────┬──────────────┘  │
│         │                   │                       │                 │
│         └───────────────────┼───────────────────────┘                 │
│                             ▼                                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │            SESSION MANAGER  (one Session per channel)           │  │
│  │  state machine • turn gate • embed render queue • lock per ssn  │  │
│  └────────────────────────────────────────────────────────────────┘  │
├───────────────────────────────────────────────────────────────────────┤
│                         ENGINE LAYER  (pure Python, sync)             │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │ Dice / RNG │  │ Combat Rules │  │ Init Order  │  │ Condition FX │ │
│  └────────────┘  └──────────────┘  └─────────────┘  └──────────────┘ │
│  ┌────────────────────────┐  ┌───────────────────────────────────┐   │
│  │ Skill Check Resolver   │  │ Action Batching (EXPLORATION)     │   │
│  └────────────────────────┘  └───────────────────────────────────┘   │
├───────────────────────────────────────────────────────────────────────┤
│                       INFERENCE LAYER  (I/O-bound)                    │
│  ┌──────────────────┐  ┌─────────────────┐  ┌──────────────────────┐ │
│  │ MLX Client       │  │ Prompt Assembler│  │ Tool-Call Dispatcher │ │
│  │ (httpx, async)   │  │ (Jinja2 templ.) │  │ (parse + execute)    │ │
│  └──────────────────┘  └─────────────────┘  └──────────────────────┘ │
├───────────────────────────────────────────────────────────────────────┤
│                       INGEST LAYER  (run_in_executor)                 │
│  ┌──────────────────┐  ┌─────────────────┐  ┌──────────────────────┐ │
│  │ EasyOCR worker   │  │ pypdf worker    │  │ Sheet -> JSON (LLM)  │ │
│  │ (thread pool)    │  │ (thread pool)   │  │ (async)              │ │
│  └──────────────────┘  └─────────────────┘  └──────────────────────┘ │
├───────────────────────────────────────────────────────────────────────┤
│                       PERSISTENCE LAYER                               │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  aiosqlite connection  •  WAL journal  •  per-session asyncio   │ │
│  │  Lock for writes  •  repositories: SessionRepo, CharacterRepo,  │ │
│  │  CombatRepo, MemoryRepo                                          │ │
│  └─────────────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────────────┤
│                       EXTERNAL SERVICES                               │
│  ┌──────────────────┐  ┌─────────────────┐  ┌──────────────────────┐ │
│  │ mlx-lm.server    │  │ Open5e REST     │  │ Local fallback cache │ │
│  │ :8080/v1         │  │ api.open5e.com  │  │ (JSON on disk)       │ │
│  └──────────────────┘  └─────────────────┘  └──────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| **Cogs** | Discord slash commands, lifecycle (`/start_game`, `/upload_sheet`, `/ready`) | `discord.ext.commands.Cog` subclasses, one per feature area |
| **View Registry** | Tracks all persistent Views, re-registers them on `setup_hook`, rebuilds dynamic content from DB | Singleton service with `register_view(message_id, view_factory, state)` |
| **Interaction Router** | Maps `custom_id` patterns to handlers; the only thing that needs to be stable across deploys | `discord.ui.DynamicItem` with regex `custom_id` templates |
| **Session Manager** | Owns one `Session` object per active channel; holds the FSM, current turn, render queue, and a per-session `asyncio.Lock` | Dict[channel_id, Session]; sessions self-persist on every transition |
| **Engine Layer** | Pure, synchronous, deterministic D&D 5e math. Knows nothing about Discord or LLMs. | Plain Python modules, fully unit-testable, no I/O |
| **MLX Client** | Async HTTP client to `mlx-lm.server`. Handles streaming, retries, timeout. | `httpx.AsyncClient` with connection pooling |
| **Prompt Assembler** | Constructs system + user messages from templates + dynamic context | Jinja2 templates in `prompts/` directory, loaded at startup |
| **Tool-Call Dispatcher** | Parses LLM output for tool invocations, calls Python functions, feeds results back | Two-mode: native `tool_calls` if available, structured-JSON fallback if not |
| **Ingest Workers** | EasyOCR / pypdf execution. Heavy and blocking; must not block the event loop. | `loop.run_in_executor(ThreadPoolExecutor, …)` |
| **Persistence Layer** | All SQLite I/O. Repositories per aggregate. WAL mode. Per-session write lock. | `aiosqlite` for non-blocking access |
| **Open5e Client** | Rules/monster lookup with local fallback cache | `httpx.AsyncClient`, JSON cache on disk |

## Recommended Project Structure

```
eldritchdm/
├── bot.py                          # entrypoint: bot instance, setup_hook, cog loader
├── config.py                       # env/config loading (token, MLX URL, DB path)
├── cogs/
│   ├── lobby.py                    # /start_game, /upload_sheet, /ready, /leave
│   ├── exploration.py              # action modal triggers, batch flush command
│   ├── combat.py                   # combat lifecycle, turn advance, /end_combat
│   └── admin.py                    # /resume, /debug_state, /reload_prompt
├── orchestrator/
│   ├── session.py                  # Session dataclass + FSM transitions
│   ├── session_manager.py          # active session registry, per-channel locks
│   ├── view_registry.py            # persistent view registration + rehydration
│   ├── interaction_router.py       # custom_id parsing, DynamicItem patterns
│   └── render.py                   # embed builders, rate-limited message editor
├── engine/                         # PURE PYTHON, NO I/O. Fully synchronous.
│   ├── dice.py                     # d20, advantage/disadvantage, crit rules
│   ├── combat.py                   # attack resolution, damage, AC/HP math
│   ├── initiative.py               # initiative order, turn gating
│   ├── skill_check.py              # ability checks, DC resolution
│   ├── conditions.py               # dodge, prone, frightened, etc.
│   └── reactions.py                # riposte eligibility + window
├── inference/
│   ├── mlx_client.py               # httpx async client to mlx-lm.server
│   ├── prompt_assembler.py         # Jinja2 template loader + context builder
│   ├── tool_dispatcher.py          # parse tool calls, execute, feed back
│   └── schemas.py                  # pydantic models for tool I/O
├── prompts/
│   ├── system_shoegpt.j2           # ShoeGPT persona system prompt
│   ├── exploration_batch.j2        # "here are 4 player actions + roll outcomes"
│   ├── combat_event.j2             # "Goblin hit for 7, Bard missed, narrate"
│   └── tool_call_fallback.j2       # structured-JSON instruction block
├── ingest/
│   ├── ocr_worker.py               # EasyOCR; runs in thread pool
│   ├── pdf_worker.py               # pypdf; runs in thread pool
│   └── sheet_translator.py         # raw text -> character JSON via LLM
├── persistence/
│   ├── db.py                       # aiosqlite connection, WAL pragmas, migrations
│   ├── schema.sql                  # canonical schema
│   ├── repositories/
│   │   ├── session_repo.py
│   │   ├── character_repo.py
│   │   ├── combat_repo.py
│   │   └── memory_repo.py
│   └── locks.py                    # per-session asyncio.Lock registry
├── external/
│   ├── open5e_client.py            # rules/monsters with local cache fallback
│   └── cache/                      # cached open5e responses
└── tests/
    ├── test_local_inference.py
    ├── test_database.py
    ├── test_gameplay_cycles.py
    └── test_recovery.py
```

### Structure Rationale

- **`engine/` is hermetic.** No imports from `orchestrator/`, `persistence/`, or `inference/`. This is the integrity boundary — every die roll and HP change lives here, and it must be unit-testable without a Discord token or LLM running.
- **`cogs/` is thin.** Cogs are routing surfaces. Business logic lives in `orchestrator/session.py`. This avoids the common discord.py mistake of putting state machines inside cog methods.
- **`prompts/` is data, not code.** Jinja templates can be hot-reloaded via `/reload_prompt` for tuning ShoeGPT's voice without restarts.
- **`ingest/` separate from `inference/`.** Ingest workers are blocking and live in a thread pool; inference is async HTTP. Different concurrency model, different lifecycle.
- **`persistence/repositories/` per aggregate** keeps SQL contained and makes per-session locking enforceable in one place.

## Architectural Patterns

### Pattern 1: Three-Tier Logical Separation (Voice / Brain / Orchestrator)

**What:** All math runs in `engine/`. All narration runs through `inference/`. All Discord I/O runs through `orchestrator/`. Dependencies flow one direction: Orchestrator → Engine, Orchestrator → Inference. Engine and Inference do not know each other exists.

**When:** Always. This is the architectural thesis of the project.

**Trade-offs:** Adds indirection — a single attack roll touches three layers. The win is that you can `import engine.combat` in a test and verify every crit/miss/dodge path with zero mocks.

**Example:**
```python
# In orchestrator/session.py — the conductor
async def resolve_attack(self, attacker_id: int, target_id: int) -> None:
    # ENGINE: deterministic math, no I/O
    outcome = engine.combat.resolve_attack(
        attacker=self.combatants[attacker_id],
        target=self.combatants[target_id],
        rng=self.rng,
    )
    # PERSISTENCE: write the new state
    async with self.lock:
        await combat_repo.apply_outcome(self.id, outcome)
    # INFERENCE: ask Voice to narrate the *facts* the engine produced
    narration = await self.llm.narrate_combat_event(outcome)
    # ORCHESTRATOR: render to Discord
    await self.render.append_combat_log(outcome, narration)
```

### Pattern 2: Asyncio Loop + Thread Pool for Blocking Work

**What:** `discord.py` and `httpx` give you async I/O for free. EasyOCR and pypdf are CPU/GPU-bound and synchronous — they MUST be offloaded with `loop.run_in_executor(executor, fn, *args)`. Otherwise a single character sheet upload freezes every concurrent session.

**When:** Any synchronous call > ~50ms. OCR, PDF parsing, heavy regex, image decoding.

**Trade-offs:** Threads have GIL but release it during native code (which is what EasyOCR/PyTorch do most of). Use a dedicated `ThreadPoolExecutor(max_workers=2)` to cap memory pressure — running 8 EasyOCR jobs in parallel will OOM.

**Example:**
```python
# In ingest/ocr_worker.py
_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr")
_reader = None  # lazy, expensive to construct

def _ocr_sync(image_bytes: bytes) -> str:
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["en"], gpu=True)
    return "\n".join(_reader.readtext(image_bytes, detail=0))

async def ocr_image(image_bytes: bytes) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_OCR_EXECUTOR, _ocr_sync, image_bytes)
```

### Pattern 3: Persistent Views with Dynamic `custom_id`

**What:** For a `discord.ui.View` to survive a restart, every component must have a `custom_id` and the View must use `timeout=None`. On startup, the bot calls `bot.add_view(view_instance)` in `setup_hook`. Discord then routes any interaction whose `custom_id` matches a registered View's items to that View's callbacks.

The subtlety: registering the View tells the router which Python class handles the buttons. It does *not* restore the View's internal Python state (initiative order, current HP, whose turn). That state must be reconstructed from the database, keyed off either the `message.id` or fields encoded into the `custom_id` itself.

**When:** Always for buttons that need to keep working after restart — initiative tracker, end-of-turn button, riposte button, "I'm ready" lobby button.

**Trade-offs:** Forces you to design `custom_id` schemes carefully. `custom_id` is capped at 100 chars and is the only thing Discord sends you when a stranger clicks a button hours after restart. Encode the minimum needed to find the rest in DB.

**Example:**
```python
# Encode session and combatant into the custom_id; recover state from DB
class EndTurnButton(discord.ui.DynamicItem[discord.ui.Button],
                    template=r"endturn:(?P<session_id>\d+):(?P<user_id>\d+)"):

    def __init__(self, session_id: int, user_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="End Turn",
                style=discord.ButtonStyle.primary,
                custom_id=f"endturn:{session_id}:{user_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["session_id"]), int(match["user_id"]))

    async def callback(self, interaction: discord.Interaction):
        session = await session_manager.get_or_load(int(self.item.custom_id.split(":")[1]))
        await session.advance_turn(invoker_id=interaction.user.id)
```

### Pattern 4: Tool-Call Dispatch with Structured-Output Fallback

**What:** `mlx-lm.server` advertises OpenAI compatibility but its `tool_calls` parsing is model-dependent and historically flaky — see open issues for Gemma 4 native tool calls not being parsed and the unmerged tool-use PR for the server. The dispatcher must therefore be backend-agnostic.

Strategy: try native `tool_calls` first; if the response comes back with `tool_calls=None` but `content` contains a recognized JSON envelope, parse that. The system prompt always includes the structured-output instruction so the model can hit the fallback path regardless of backend support.

**When:** Whenever the LLM may need to look something up (`lookup_open5e_rule`, `search_monster_guide`, `save_session_memory`).

**Trade-offs:** Two parsing paths to maintain. The fallback adds tokens to every prompt. The win is that the bot doesn't break the day someone swaps in `llama.cpp` or upgrades MLX and the parser regresses.

**Example:**
```python
# inference/tool_dispatcher.py
TOOL_ENVELOPE = re.compile(r"<tool_call>\s*(?P<json>\{.*?\})\s*</tool_call>", re.DOTALL)

async def execute_with_tools(client, messages, tools):
    while True:
        resp = await client.chat_completion(messages=messages, tools=tools)
        choice = resp.choices[0].message

        # Native path
        if choice.tool_calls:
            calls = choice.tool_calls
        # Fallback: structured-output in content
        elif (m := TOOL_ENVELOPE.search(choice.content or "")):
            calls = [_parse_envelope(m.group("json"))]
        else:
            return choice.content  # final narration

        for call in calls:
            result = await TOOL_REGISTRY[call.name](**call.arguments)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
```

### Pattern 5: Per-Session asyncio.Lock + WAL

**What:** SQLite WAL allows many concurrent readers and one writer at a time *globally*. With 4 channels each writing on every turn, you would still serialize all writes — but only briefly. The harder rule: within a single session, transactions must be ordered (you cannot apply damage and advance the turn in interleaved order). Solution: one `asyncio.Lock` per session covering the read-modify-write window, plus aiosqlite for non-blocking access.

**When:** Every write that depends on a prior read (HP changes, turn advances, condition application). Pure reads do not need the lock.

**Trade-offs:** Cross-session writes still queue at the SQLite level — fine at expected scale (2-4 channels). If contention ever shows up, the answer is "one DB file per session" not "switch to Postgres."

**Example:**
```python
# orchestrator/session.py
class Session:
    def __init__(self, session_id: int):
        self.id = session_id
        self.lock = asyncio.Lock()  # serializes this session's writes

    async def apply_damage(self, target_id: int, amount: int) -> Combatant:
        async with self.lock:
            target = await combat_repo.get_combatant(self.id, target_id)
            target.hp = max(0, target.hp - amount)
            await combat_repo.update_combatant(target)
            return target
```

## Data Flow

### Exploration Batch Flow

```
[Player clicks "Take Action" button]
        ↓
[Modal: "What do you do?"]                              (Discord -> orchestrator)
        ↓
[Session.queue_action(user_id, intent_text)]            (orchestrator)
        ↓
[Engine.skill_check_resolve(intent, character)]         (engine, sync)
        ↓
[Persist intent + roll outcome to DB]                   (persistence)
        ↓
[Wait for N players OR timeout]                         (orchestrator, asyncio.Event)
        ↓
[PromptAssembler.build_exploration_batch(intents,rolls)](inference)
        ↓
[MLXClient.complete(messages, tools=[lookup_rule…])]    (inference, async HTTP)
        ↓
[ToolDispatcher: maybe call lookup_open5e_rule]         (inference)
        ↓
[Render single narration embed for the batch]           (orchestrator)
        ↓
[Save narration to campaign_memory]                     (persistence)
```

### Combat Turn Flow

```
[It's Bard's turn — gate by user_id]
        ↓
[ActionMenu View shown (Attack/Dodge/Riposte/…)]
        ↓
[Bard clicks "Attack Goblin"]
        ↓
[Engine.combat.resolve_attack(bard, goblin)]            (engine, sync)
        ↓
[Persist HP change + condition updates]                 (persistence + session.lock)
        ↓
[Render combat log (rate-limited edit)]                 (orchestrator)
        ↓
[LLM narrate the resolved facts]                        (inference, async)
        ↓
[Append narration to combat embed]                      (orchestrator)
        ↓
[If monster turn next: schedule monster action]
[If riposte eligible: arm 8s timed button]
        ↓
[Advance initiative pointer]
```

### State Recovery Flow (THE hard problem)

```
[Bot starts]
        ↓
[bot.setup_hook() runs ONCE before connecting]
        ↓
[Persistence.connect() → PRAGMA journal_mode=WAL, busy_timeout=5000]
        ↓
[SessionRepo.list_active() → all sessions not in TERMINATED]
        ↓
For each active session:
    ↓
    [Load FSM state, characters, combatants, initiative, conditions]
    ↓
    [Reconstruct Session object in memory]
    ↓
    [SessionManager.register(session)]
    ↓
    For each persistent message_id stored in session.ui_messages:
        ↓
        [Build the appropriate View class with restored state]
        ↓
        [bot.add_view(view, message_id=message_id)]
            └─ tells Discord: "interactions on this message route to this View"
        ↓
        [Optionally fetch the message and re-edit its embed to reflect current state]
        ↓
[Register DynamicItem templates: EndTurnButton, RiposteButton, ReadyButton …]
        ↓
[bot.connect() — Discord is now live; old buttons just work]
```

The key insight: **`bot.add_view()` does not require the message to still exist or be re-sent.** It tells the router "if a `custom_id` matches my items, dispatch here." For Views with restored Python state (current HP shown on labels, etc.), you pass `message_id=...` so the router knows the View binds to that specific message; you then call `message.edit(view=restored_view)` to refresh the visible labels.

For purely structural buttons (End Turn, Riposte) that encode all state in `custom_id`, `DynamicItem` with a regex template is even better — no per-message registration needed; the bot reconstructs the handler from the `custom_id` on demand.

## Async Boundaries

| Operation | Runs On | Why |
|-----------|---------|-----|
| Discord gateway events | asyncio loop | discord.py is async-native |
| HTTP to `mlx-lm.server` | asyncio loop (httpx) | network I/O, fully awaitable |
| HTTP to Open5e | asyncio loop (httpx) | network I/O, fully awaitable |
| Engine math (dice, combat) | asyncio loop (sync calls) | microsecond-scale; offloading would cost more than it saves |
| SQLite reads/writes | asyncio loop (aiosqlite) | aiosqlite manages a worker thread internally |
| EasyOCR | `ThreadPoolExecutor(max_workers=2)` | CPU/GPU-bound, seconds-scale, releases GIL |
| pypdf | `ThreadPoolExecutor` | Synchronous, can be slow on large PDFs |
| Embed rate-limit pacing | `asyncio.Queue` + render task | Coalesce rapid updates into ≤1/sec per channel |

**Rule:** Anything that takes > 50ms and isn't already async gets `run_in_executor`. The event loop should never block long enough for Discord heartbeats (~41s window) to be at risk, but practically you want every handler to yield within 100ms.

## Scaling Considerations

| Scale | Adjustments |
|-------|-------------|
| 1 server, 1-2 sessions | Default config. Single MLX server, single SQLite file. |
| 1 server, 4-8 sessions | Confirm `ThreadPoolExecutor(max_workers=2)` doesn't bottleneck OCR; consider per-session render rate limiter. |
| 1 server, 10+ sessions | MLX server becomes the bottleneck (one inference at a time on Apple Silicon). Queue LLM requests; show "ShoeGPT is thinking…" embed. |
| Multi-host (out of scope) | Would require Postgres + Redis for shared state — outside the local-first thesis. |

### Scaling Priorities

1. **First bottleneck: MLX inference throughput.** A 4-bit Qwen MoE on M-series produces ~30-60 tok/s. With 4 active combats, narration calls queue up. Mitigation: a global semaphore around the MLX client (`asyncio.Semaphore(1)`) plus optimistic UI ("ShoeGPT is rolling for narration…") so users see progress.
2. **Second bottleneck: Discord rate limits on embed edits.** The bucket is 5 edits / 5s per message. Combat with many quick events will exceed this. Mitigation: a per-message render queue that coalesces updates into ≤1 edit/sec, with a "final" flush at end of turn.
3. **Third bottleneck: EasyOCR cold start.** First image takes 5-10s to load the model. Mitigation: warm the reader at startup if `--preload-ocr` flag is set, or accept the first-upload latency.

## Anti-Patterns

### Anti-Pattern 1: Letting the LLM Do Math

**What people do:** Pass the LLM the character sheet and battle state and let it narrate `"The bard rolled a 17, hitting AC 15 for 8 damage."`
**Why it's wrong:** It will silently fabricate HP, forget conditions, advance turns illegally. This is the entire reason the project exists.
**Do instead:** Engine computes the outcome as a typed object. LLM receives the *result* as text and is instructed to narrate *only* what's in that result. The prompt template never contains raw numbers the LLM has to interpret — it contains pre-resolved facts.

### Anti-Pattern 2: Putting State in Cogs

**What people do:** `self.combat_state = {}` inside a `Cog` subclass.
**Why it's wrong:** Cogs reload, can be unloaded, and don't survive restarts. State stuck in cogs is state you cannot rehydrate.
**Do instead:** Cogs are *thin command surfaces.* All state lives in `Session` objects owned by `SessionManager`, persisted to SQLite on every transition.

### Anti-Pattern 3: Awaiting Blocking Calls

**What people do:** `text = easyocr_reader.readtext(image)` inside an async handler.
**Why it's wrong:** Freezes the entire bot — heartbeats, other sessions, button clicks — for the duration of OCR. Discord will eventually disconnect.
**Do instead:** `run_in_executor` with a dedicated thread pool. Same rule for pypdf, image resize, regex on huge strings.

### Anti-Pattern 4: One Global Lock for SQLite

**What people do:** A single `asyncio.Lock` around every DB call.
**Why it's wrong:** Serializes reads against writes for unrelated sessions. WAL already handles reader/writer isolation; the global lock throws it away.
**Do instead:** Per-session locks for read-modify-write sequences. No lock for pure reads. Trust WAL to handle the rest.

### Anti-Pattern 5: One Embed Edit Per State Change

**What people do:** Edit the combat embed on every HP tick, every condition application.
**Why it's wrong:** Burns through the 5-per-5s rate limit in two seconds of fast combat.
**Do instead:** Render queue. Coalesce changes into ≤1 edit/sec per message. Edit once on turn end for a guaranteed final state.

### Anti-Pattern 6: Trusting `tool_calls` to Always Be Populated

**What people do:** Read `response.choices[0].message.tool_calls` and crash when it's `None` for a model whose parser failed.
**Why it's wrong:** `mlx-lm`'s OpenAI parity is per-model and changes between releases.
**Do instead:** The fallback parser pattern in Pattern 4. Always look at `content` for the structured envelope as a backup.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| `mlx-lm.server` | `httpx.AsyncClient` POST to `/v1/chat/completions` | OpenAI-compatible-ish; tool_calls parsing is model-dependent — always have the structured-output fallback ready |
| Open5e REST | `httpx.AsyncClient` GET with on-disk JSON cache | Cache aggressively — rules don't change. Local fallback file shipped in the repo for fully-offline play |
| Discord Gateway | `discord.py` Client | One connection per process. `setup_hook` is the recovery seam |
| Discord REST | `discord.py` Client internal | Built-in rate-limit handling; respect 5/5s on edits |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Cog → Session | Direct method call | Cog is the routing layer only |
| Session → Engine | Direct sync function call | Engine is pure; no awaits needed |
| Session → Persistence | `await repo.method(...)` | aiosqlite under the hood |
| Session → Inference | `await llm.method(...)` | httpx under the hood |
| Inference → Engine | NEVER | Strict one-way: orchestrator passes engine results into inference; inference never calls engine |
| Inference → Persistence | Only via tool calls (`save_session_memory`) | Keeps memory write paths auditable |

## Suggested Build Order

The build order minimizes rework by exercising each architectural seam as early as possible.

| # | Phase | Why This Order |
|---|-------|----------------|
| **1** | **Persistence layer + schema** | Everything else depends on this. Get WAL + repositories + per-session locks working with tests before touching Discord. Cheap to change now, expensive later. |
| **2** | **Engine layer (pure Python)** | No I/O, fully testable, no external deps. You can write the entire 5e combat resolver and have 100% confidence before anyone clicks a button. Catching math bugs here costs minutes; catching them in production costs trust. |
| **3** | **MLX client + prompt assembler + tool dispatcher** | Validates the riskiest external dependency early. If `mlx-lm.server`'s tool-calling doesn't behave, you discover it now (week 2) not after the bot is half-built. Includes the structured-output fallback from day one — do not defer this. |
| **4** | **Session manager + state machine** | Wire engine + persistence + inference together with no Discord. Drive it from tests that simulate "player does X, monster does Y." Proves the orchestration layer in isolation. |
| **5** | **Cogs + basic Views (LOBBY only)** | First Discord surface. Smallest possible UI — `/start_game`, join, ready. Validates that you can hit the gateway, render embeds, and route interactions. |
| **6** | **Persistent View infrastructure + recovery flow** | Build this *before* any complex Views are added. Restart-recovery is much easier to bake in from the start than retrofit. Test by killing the process mid-lobby and confirming buttons still work. |
| **7** | **Character ingest (OCR/PDF)** | Adds the thread-pool seam. Self-contained — can be built and tested independently. Defer until after Views work so you're not debugging two new things at once. |
| **8** | **EXPLORATION state + action batching** | First end-to-end "real" gameplay loop. Exercises modals, batching, LLM narration, memory writes. Restart-recovery already exists from step 6, so persistence is free. |
| **9** | **COMBAT state + initiative + turn gating** | The most complex orchestration. Built on top of the now-proven foundation. Heavy use of Views, embed rate limiting, per-session locks. |
| **10** | **Reactions (dodge, riposte) + Open5e integration** | Polish layer. Adds the timed-button pattern and rules-lookup tool. By now everything underneath is stable. |
| **11** | **Self-host packaging + docs** | Last because the architecture has stabilized and you know what config knobs actually exist. README, requirements.txt, config template. |

**Why this order over the obvious "build features 1-by-1":** Building Discord-first is the natural temptation but leads to throwaway work — every state machine bug requires a Discord client to reproduce, every engine fix requires a button click to verify. By front-loading the layers that have *no Discord dependency* (persistence, engine, inference), you get fast feedback loops on the hardest correctness questions. Discord plumbing is well-understood and goes in last when the underlying behavior is locked.

**Why recovery (step 6) comes before any complex feature:** Retrofitting persistent Views is painful. Every View added before the recovery mechanism has to be re-audited later for `custom_id` schemes, state encoding, and rehydration logic. Building the recovery infrastructure once, early, makes every subsequent feature implicitly resilient.

**Why the LLM fallback parser is in step 3, not later:** If you build the happy path first and "add the fallback later when needed," you'll discover `tool_calls=None` in production. The fallback is cheap to add at the start and means you can swap inference backends without code changes.

## Sources

- [discord.py persistent view example (Rapptz/discord.py)](https://github.com/Rapptz/discord.py/blob/master/examples/views/persistent.py) — HIGH confidence, authoritative
- [Writing Persistent Views — thegamecracks](https://thegamecracks.github.io/discord.py/persistent_views.html) — `bot.add_view(view, message_id=...)` pattern, MEDIUM
- [mlx-lm tool-calling status — Issue #784 (mlx-examples)](https://github.com/ml-explore/mlx-examples/issues/784) — confirms server-side tool-use PR unmerged, HIGH
- [mlx-lm Issue #1096 — Gemma 4 tool_calls field empty](https://github.com/ml-explore/mlx-lm/issues/1096) — confirms parser regressions are real, HIGH
- [mlx-openai-server (alternative backend with --tool-call-parser)](https://github.com/cubist38/mlx-openai-server) — backup option, MEDIUM
- [SQLite WAL locking semantics (sqlite.org)](https://sqlite.org/lockingv3.html) — confirms single-writer + non-blocking-reader model, HIGH
- [aiosqlite (omnilib/aiosqlite)](https://github.com/omnilib/aiosqlite) — async SQLite bridge used in the persistence layer, HIGH
- [discord.py rate limit for message edits — Issue #6073 / API ref](https://discordpy.readthedocs.io/en/stable/api.html) — 5 edits/5s bucket, HIGH

---
*Architecture research for: EldritchDM (local-first Discord D&D bot, three-brain split)*
*Researched: 2026-05-21*
