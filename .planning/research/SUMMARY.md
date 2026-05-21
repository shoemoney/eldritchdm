# Project Research Summary — EldritchDM

**Project:** EldritchDM (ShoeGPT)
**Domain:** Local-first Discord bot orchestrating D&D 5e with a quantized MoE LLM on Apple Silicon
**Researched:** 2026-05-21
**Confidence:** HIGH on stack, architecture, and Discord/SQLite pitfalls; MEDIUM on MLX-specific failure modes and AI-DM competitor feature surface.

## Executive Summary

EldritchDM occupies an empty quadrant in the 2026 AI-DM market: **no shipping product combines local inference + rule-rigid combat + reactive Discord UI + self-host**. Fables.gg leads on memory/UI but is SaaS+LLM-as-judge; Avrae has rule rigor but no AI DM; AI Dungeon has narration but no rules. The three-brain architecture is correct and timely, but the PRD treats several of its hardest correctness questions as prompt-level concerns when they are actually post-generation enforcement, OS-level supervision, and concurrency-control problems.

The stack the PRD specifies is mostly right for 2026, with three concrete corrections: **ocrmac (Apple Vision) replaces EasyOCR as the primary OCR path on macOS**; **PyMuPDF replaces pypdf as the primary PDF parser** (with pypdf retained as an MIT-licensed fallback); and **mlx-lm.server's OpenAI tool-call parity is unreliable enough that a structured-output (`<tool_call>{json}</tool_call>`) fallback parser is mandatory from day one**. Pin `discord.py==2.7.1`, `mlx-lm==0.31.3`, model `mlx-community/Qwen3.5-35B-A3B-MLX-4bit` (with `Qwen3.5-7B-MLX-4bit` for 16 GB Macs).

The riskiest things in the PRD as written: (1) "no math in LLM output" must be a **post-hoc validator** that strips/rejects unsanctioned digits, HP/AC keywords, and out-of-context entity names; (2) "WAL + careful locking" implies WAL solves concurrent writes, which it does not — a **single-writer asyncio.Queue plus `BEGIN IMMEDIATE` plus `busy_timeout=5000`** is required; (3) **prompt injection through the player action modal is not mentioned anywhere** — sentinels and a 500-char cap belong in v1; (4) **persistent Views need DynamicItem-style `custom_id` schemes registered in `setup_hook`**; (5) every interaction callback must **`await interaction.response.defer(thinking=True)` as its first line** — the 3s ack cliff is the most common reason an otherwise correct bot looks broken.

## Key Findings (Top 10, Consequential)

1. **Three-brain is a *logical* boundary, not a process boundary.** Voice/Brain/Orchestrator are layered modules in one async Python process. `engine/` is hermetic — no imports from `orchestrator/`, `persistence/`, or `inference/` — and is the integrity boundary that makes every die roll unit-testable without Discord.
2. **No-math contract requires a post-hoc validator, not a prompt rule.** Regex + entity allowlist runs on every narration; on hit, re-prompt with a hard FORBIDDEN list or rewrite the sentence. Bake an adversarial ≥50-scenario test corpus into CI.
3. **User correction (2026-05-21): backend is `mlx-omni-server` with Gemma 4; tool calls confirmed reliable.** This supersedes the original mlx-lm.server analysis. Dual-parse remains as a defensive safety net but native `response.tool_calls` is trusted as the primary path. Structured `<tool_call>{...}</tool_call>` fallback is no longer mandatory but stays cheap to keep.
4. **WAL is not a writer-concurrency story.** One asyncio writer task draining a queue, `PRAGMA busy_timeout=5000` and `PRAGMA journal_mode=WAL` on every connection, `BEGIN IMMEDIATE` for any txn that will write, never hold a write txn across an `await llm_call()`.
5. **Persistent Views need `discord.ui.DynamicItem` with regex `custom_id` templates** (e.g. `endturn:(?P<session_id>\d+):(?P<user_id>\d+)`). `bot.add_view()` called in `setup_hook` for every active session loaded from DB; encode minimum state in custom_id (100-char cap).
6. **3s defer is non-negotiable.** First line of every callback: `await interaction.response.defer(thinking=True)`. Mechanical outcome lands in ~1s; LLM narration follows as a separate edit/followup. Splitting roll-from-narrate is a *correctness* requirement.
7. **OCR on macOS should be `ocrmac` (Apple Vision via PyObjC), not EasyOCR.** ~100ms/page, no PyTorch dep, no 64 MB model download, uses the Neural Engine. EasyOCR becomes an opt-in `linux-ocr` extra. OCR-confidence gate w/ **manual-entry modal as a first-class path**.
8. **Prompt injection is a v1 concern.** Wrap player free-text in `<player_action speaker="..." user_id="...">…</player_action>` sentinels, strip control tokens (`<tool_call>`, `<|im_start|>`, `SYSTEM:`, `ASSISTANT:`), cap modal input at 500 chars, and **disable the tool-call content-string fallback for turns that include user free-text**.
9. **MLX server is a process that can die — treat it as such.** External supervisor (`launchd`/`pm2`/`tmux+watchdog`), health-check every 60s, circuit breaker that falls back to templated narration, `httpx.Timeout(connect=2, read=20, write=5)`. Memory pressure on Apple Silicon doesn't OOM cleanly — it grinds.
10. **EldritchDM occupies an empty quadrant.** No 2026 product combines (local inference) × (rule-rigid combat) × (reactive Discord UI) × (self-host). Image gen, TTS, cross-server sync, LLM-as-judge — all anti-features.

## Stack (Pinned Versions + PRD Diffs)

### Core (HIGH confidence)

| Library | Pinned | Purpose |
|---|---|---|
| Python | `>=3.11,<3.13` | Runtime |
| `discord.py` | `==2.7.1` | Bot framework — Rapptz active, 2026-03-03 release |
| `mlx-lm` | `==0.31.3` | Local inference + `mlx_lm.server` at `:8080/v1` |
| Model | `mlx-community/Qwen3.5-35B-A3B-MLX-4bit` primary; `Qwen3.5-7B-MLX-4bit` 16 GB fallback | MoE 3B active, ~19.5 GB unified, ~90–108 tok/s on M4 Max |
| `openai` | `>=1.55,<2.0` | Client to mlx-lm.server |
| `aiosqlite` | `>=0.20,<0.22` | Async SQLite; serializes writes through one thread |
| `httpx` | `>=0.27,<0.29` | Async HTTP (Open5e + non-OpenAI) |
| `pydantic` | `>=2.8,<3.0` | LLM JSON output validation |
| `tenacity` | `>=8.5,<10.0` | Retry/backoff on Open5e and LLM |
| `structlog` | `>=24.4,<26.0` | Bound-context JSON logs |
| `ocrmac` | `>=1.0,<2.0` | macOS-primary OCR via Apple Vision |
| `PyMuPDF` | `>=1.24,<2.0` | Primary PDF parser (AGPL, fine for self-host) |
| `pypdf` | `>=4.3,<6.0` | MIT fallback PDF parser |
| `easyocr` (extra `linux-ocr`) | `>=1.7,<2.0` | Linux/CUDA OCR fallback |
| `python-dotenv` | `>=1.0,<2.0` | Config |

### PRD Diffs

| PRD said | Research says | Why |
|---|---|---|
| EasyOCR primary | **ocrmac primary on macOS; EasyOCR via `linux-ocr` extra** | Apple Vision faster, no PyTorch, no 64 MB download, uses ANE |
| pypdf | **PyMuPDF primary; pypdf MIT fallback** | ~10x faster, better multi-column, `get_pixmap()` enables OCR fallback. AGPL caveat |
| discord.py 2.3.2+ | **`==2.7.1`** | Active again, persistent-View ergonomics improved |
| "MLX over Ollama" | Keep mlx-lm.server but reframe rationale | Ollama 0.19+ uses MLX backend; perf gap collapsed. Keep mlx-lm.server for fewer moving parts |
| (omitted) | Add `httpx`/`pydantic`/`tenacity`/`structlog`/`python-dotenv` | Async/runtime support layer |

### Do NOT use

`requests` · `aiohttp` · sync SQLAlchemy · `langchain`/`pydantic-ai`/`instructor` · `pytesseract` · bare `logging` · `nextcord`/`py-cord`.

## Features

### Table stakes (Avrae baseline)
Persistent character storage · dice parser w/ adv/dis/crit · initiative tracker · per-channel concurrent sessions · rich embeds · slash command surface · ephemeral errors · 5e rules/spell/monster lookup · **full resume across restarts**.

### Table stakes (AI-DM baseline)
ShoeGPT persona · **long-term campaign memory** (#1 ChatGPT-as-DM complaint) · narrative continuity · **rule-enforced combat** · HP/AC/condition tracking that sticks · inventory persistence · NPC voice variation · **multiplayer turn discipline** · scene awareness.

### Differentiators (no competitor combines these)
- Mechanically honest narration (engine math, LLM narrates facts only)
- Riposte timed reactive UI (8s class-gated button after monster miss)
- OCR + PDF character ingest
- Action-batching exploration phase
- Local-first, zero API spend
- MCP-style tool registry (`lookup_open5e_rule`, `search_monster_guide`, `save_session_memory`)
- Dodge w/ auto-disadvantage
- 8+ player initiative UI (Fables caps at 6)
- Self-hostable single-binary install

### Anti-features (deliberately NOT built)
1. Free-form "chat with the DM" without state transitions
2. **LLM-computed math/dice/numerical effects** (the thesis)
3. Unbounded narration length (hard 150-word cap)
4. LLM-as-judge for rule disputes (defer to Open5e + human table)
5. Image/map generation
6. Cross-server character portability / cloud sync
7. Voice / TTS narration
8. "Auto-DM mode" that plays without player input

## Architecture

### Layers (one-way deps)
1. **Orchestrator** — Cogs + View Registry + Interaction Router + Session Manager (discord.py, async)
2. **Engine** — pure Python, sync, hermetic. Dice/combat/initiative/skill/conditions/reactions
3. **Inference** — MLX httpx client + Jinja prompt assembler + dual-parse tool dispatcher
4. **Ingest** — OCR/PDF workers on `ThreadPoolExecutor(max_workers=2)`
5. **Persistence** — aiosqlite, WAL, per-session asyncio.Lock, repositories per aggregate
6. **External** — mlx-lm.server (`:8080/v1`), Open5e REST (cache-first), local fallback cache

**Rule:** Inference never calls Engine; Engine never calls Inference or Persistence. Orchestrator conducts.

### Async model

| Op | Runs on |
|---|---|
| Discord gateway, HTTP (mlx-lm/Open5e), SQLite | asyncio loop |
| Engine math | asyncio loop (sync) — microsecond-scale |
| OCR, PyMuPDF/pypdf | `ThreadPoolExecutor(max_workers=2)` |
| Embed updates | `asyncio.Queue` + render task, ≤1 edit/sec/message |

### Tool-call dispatch (dual-parse, mandatory)

```python
if choice.tool_calls:                                  # native
    calls = choice.tool_calls
elif (m := TOOL_ENVELOPE.search(choice.content or "")):  # fallback
    calls = [_parse_envelope(m.group("json"))]
else:
    return choice.content                              # final narration
```

Fallback **disabled for turns containing user free-text** (injection mitigation).

### Restart recovery

In `setup_hook`:
1. Persistence connect → `PRAGMA journal_mode=WAL`, `busy_timeout=5000`.
2. `SessionRepo.list_active()` → reload FSM state, characters, combatants, initiative, conditions.
3. Reconstruct Session objects; `SessionManager.register(session)`.
4. For each persistent `message_id`: build View w/ restored state, `bot.add_view(view, message_id=...)`.
5. Register `DynamicItem` templates (EndTurnButton, RiposteButton, ReadyButton).
6. `bot.connect()` — old buttons just work.

### Concurrency (single-writer)

- Per-session `asyncio.Lock` covers each read-modify-write window.
- Pure reads take no lock — trust WAL.
- All writes funnel through one writer task per process (asyncio.Queue) — eliminates writer/writer SQLITE_BUSY.
- `BEGIN IMMEDIATE` for write txns; never `BEGIN` then upgrade.
- Periodic `PRAGMA wal_checkpoint(TRUNCATE)`.

## Pitfalls → Phase Mapping

| # | Pitfall | Severity | Phase | Verification |
|---|---|---|---|---|
| 1 | LLM math leakage | CRITICAL | Phase 1 (LLM client) | Adversarial 50-scenario corpus; validator on every narration |
| 2 | Persistent Views vanish on restart | CRITICAL | Phase 2 (state machine) | Kill-and-restart mid-combat; buttons still work |
| 3 | Discord 3s ack cliff | CRITICAL | Phase 1 + Phase 3 | Lint: every callback's first line is `interaction.response.defer(...)` |
| 4 | Rate-limit cratering | HIGH | Phase 3 (combat) | 8-player load test, zero 429s, 300-500ms debouncer |
| 5 | Tool-call format drift | HIGH | Phase 1 | `test_tool_calls.py` smoke test; pin model + mlx-lm; dual-parse always |
| 6 | SQLite writer contention | HIGH | Phase 2 (persistence) | Multi-channel stress test; zero `database is locked` |
| 7 | Context-window blowup | MEDIUM | Phase 1 cap + Phase 4 rollup | 100-turn synthetic session; token count bounded |
| 8 | Prompt injection | HIGH | Phase 1 sanitizer + Phase 4 memory ACL | Injection corpus passes; `<player_action>` sentinels; 500-char cap |
| 9 | OCR quality cliff | MEDIUM | Phase 2 (ingest) | Confidence gate; manual-entry modal first-class; stat-range validation |
| 10 | Open5e downtime | MEDIUM | Phase 0 cache + Phase 4 degrade | Offline-mode session completes; 2s timeout; SRD cache shipped |
| 11 | MLX server crashes | HIGH | Phase 1 + infra | `kill -9` drill; supervisor (launchd/pm2); 60s health ping; circuit breaker |
| 12 | Sheet privacy leakage | HIGH (trust) | Phase 2 + Phase 4 | DM-only `/upload_sheet`; `ephemeral=True` confirmations; `visibility` ACL |

## Recommended Build Order (11 steps)

| # | Step | Why this order |
|---|---|---|
| 1 | **Persistence layer + schema** | Everything depends on it. WAL pragmas, repositories, per-session locks, single-writer queue, `BEGIN IMMEDIATE`. |
| 2 | **Engine layer (pure Python)** | No I/O, fully testable. Write the entire 5e combat resolver and unit-test crit/miss/dodge/riposte before anyone clicks a button. |
| 3 | **MLX client + prompt assembler + tool dispatcher (with structured-output fallback from day one)** | Validates riskiest external dep in week 2. Includes no-math validator, token cap, dual-parse, health check, circuit breaker, input sentinels. |
| 4 | **Session manager + state machine** | Wire engine + persistence + inference without Discord. Drive from synthetic tests. |
| 5 | **Cogs + basic Views (LOBBY only)** | Smallest possible Discord UI — validates gateway, embeds, interaction routing. |
| 6 | **Persistent View infrastructure + recovery flow** | Build *before* any complex Views. Retrofitting persistence is painful. Kill-process-mid-lobby test must pass. |
| 7 | **Character ingest (OCR/PDF)** | Thread-pool seam. ocrmac primary, confidence gating, manual-entry modal, DM-only, ephemeral confirmations. |
| 8 | **EXPLORATION state + action batching** | First end-to-end gameplay loop. Modals, intent queue, batched prompts, memory writes. |
| 9 | **COMBAT state + initiative + turn gating** | Heaviest orchestration. Embed coalescer + 8-player load test = phase exit criteria. |
| 10 | **Reactions (dodge, riposte) + Open5e integration** | Timed buttons (with DB-persisted deadlines), cache-first rules lookup, offline mode. |
| 11 | **Self-host packaging + docs** | Last because architecture stabilized. README, requirements.txt, .env template, schema bootstrap, MLX supervisor recipe. |

## Open Questions

1. **Apple Silicon memory tier for the target user.** Default ship as 35B-A3B with 7B documented, or auto-detect at startup?
2. **AGPL acceptability for PyMuPDF.** Fine for open self-hostable; flag for closed forks.
3. **mlx-lm tool-calling parser flag for Qwen3.5/3.6 MoE.** Verify `--tool-call-parser qwen3_5` requirement in Phase 1 smoke test.
4. **Linux/CUDA "secondary target" scope.** README documents Ollama 0.19+MLX + `linux-ocr` extra as "best effort" — not CI-tested.
5. **Per-player memory visibility model.** Proposed: `visibility ∈ {public, dm_only, user_id}` with recall queries filtered by requester.
6. **Concurrent-session ceiling.** Architecture supports 2-4 comfortably; 10+ becomes MLX-bound. Surface "ShoeGPT is thinking…" when inference semaphore held.
7. **Riposte eligibility list.** Which 5e classes/subclasses can riposte? Needs explicit engine spec.
8. **Adversarial test corpus authorship.** Half-day in Phase 1 to handwrite the 50-scenario no-math leakage corpus.

## Confidence Assessment

| Area | Confidence |
|---|---|
| Stack | HIGH — versions verified against PyPI 2026-05-21 |
| Features | MEDIUM-HIGH — Avrae baseline HIGH; Fables/Franz MEDIUM |
| Architecture | HIGH — discord.py persistence + SQLite WAL well-documented; mlx-lm tool-calling MEDIUM |
| Pitfalls | HIGH — Discord/SQLite/LLM-leakage cross-verified; MLX failure modes MEDIUM |

**Overall:** HIGH. MEDIUM areas carry concrete mitigations (supervisor + dual-parse + smoke tests).
