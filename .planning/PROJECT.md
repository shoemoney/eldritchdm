# EldritchDM

## What This Is

EldritchDM is a local-first, self-hostable Discord bot that runs full D&D 5e games end-to-end with an AI Dungeon Master persona called **ShoeGPT**. It splits the DM job across three brains — a local quantized MoE LLM (MLX) for narration, a Python rules engine for math/state, and a `discord.py` orchestrator for real-time UI — so the AI can never hallucinate HP, miscalculate AC, or break turn order. It's for tabletop players who want a "forever DM" available on demand without paying for hosted AI or surrendering the rule integrity that makes 5e actually feel like 5e.

## Core Value

**Mechanically honest AI DM.** Narration is evocative, but every die roll, HP change, AC check, and turn boundary is enforced by deterministic Python code — the LLM never touches the math.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Local inference client (oMLX (`omlx serve`), Gemma 4) with OpenAI-compatible API at `localhost:8080/v1`
- [ ] SQLite (WAL mode) schema: `game_sessions`, `characters`, `combat_monsters`, `campaign_memory`
- [ ] Character ingest via OCR (EasyOCR for PNG/JPG) and PDF (pypdf) → LLM-translated JSON → DB
- [ ] State machine: LOBBY → EXPLORATION → COMBAT_INIT → COMBAT, with persistent state across restarts
- [ ] Discord UI: dynamic Views (buttons, modals, select menus), rich embeds, ephemeral warnings
- [ ] `/start_game` lobby flow with character upload and readiness check
- [ ] EXPLORATION action-batching: collect player intents via modals, auto-roll skill checks, batch into a single narration prompt
- [ ] COMBAT engine: initiative, turn gatekeeping by Discord user ID, attack resolution with crit/fail/dodge math
- [ ] Dodge mechanic: sets `is_dodging`, forces disadvantage on incoming attacks, auto-resets next turn
- [ ] Riposte reaction: 8-second timed button for eligible classes after a missed monster attack
- [ ] MCP-style tool registry exposed to the model: `lookup_open5e_rule`, `search_monster_guide`, `save_session_memory`
- [ ] Open5e API client with graceful local-fallback when offline
- [ ] ShoeGPT persona prompt enforcing strict separation (no math in LLM output) and tactile narration
- [ ] Multi-channel concurrent sessions on one DB without races (WAL + careful locking)
- [ ] Self-hostable: README, `requirements.txt`, config template, schema bootstrap
- [ ] Support up to 8+ players per session in initiative/embed UI
- [ ] Test suites: `test_local_inference.py`, `test_database.py`, `test_gameplay_cycles.py`

### Out of Scope

(To be added if/when scope tradeoffs emerge during planning.)

## Context

- **Author profile:** Senior dev (Jeremy / Shoemoney). Apple Silicon workstation. Comfortable with Python, async, Discord bots, local LLMs.
- **Hardware target:** macOS / Apple Silicon (M-series). Unified memory makes MoE quantization tractable locally.
- **Why local-first:** No API bills, no rate limits, no data leaving the machine; suitable for long campaigns.
- **Why "three brains":** Pure LLM-as-DM systems hallucinate HP, forget conditions, and allow illegal moves. Splitting math out of the LLM is the entire architectural thesis.
- **Self-hostable goal:** Others should be able to clone, install deps, set their Discord token, point at their MLX endpoint, and run.

## Constraints

- **Runtime:** Python 3.11+
- **Platform:** macOS Apple Silicon primary target (Linux/CUDA secondary if not in conflict)
- **Inference backend:** `oMLX (`omlx serve`)` exposing OpenAI-compatible API at `http://localhost:8765/v1` (model id `ShoeGPT`, Gemma 4 4-bit quantized under the hood). Tool calls are reliable on this combo — confirmed by user. Structured-output fallback parser remains as a defensive safety net but native `tool_calls` is the primary path.
- **Discord library:** `discord.py` v2.3.2+ (Views, Modals, Select Menus required)
- **Database:** SQLite3 with WAL journaling — no external DB server
- **Rules source:** Open5e REST API (`https://api.open5e.com/`) with local fallback cache
- **OCR:** EasyOCR (English, GPU/Metal where available)
- **PDF:** pypdf
- **Performance:** Character ingest <6s; narration responses <150 words; Discord interaction acks within 3s; rate-limit-aware embed updates
- **Reliability:** Full resume across bot restarts (room, turn order, HP, memory, views rebuilt from DB)
- **Integrity rule:** The LLM is forbidden from computing math; all numerical effects originate in Python and are passed *to* the LLM as facts to narrate

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Three-brain architecture (Voice / Brain / Orchestrator) | Prevents LLM math hallucination, the #1 failure mode of AI DMs | — Pending |
| oMLX (`omlx serve`) + Gemma 4 (over mlx-lm.server / Ollama / Qwen) | User has working setup; OpenAI-compatible tool calls confirmed reliable | ✓ Good |
| SQLite + WAL over hosted DB | Local-first, zero ops, sufficient for concurrent channel writes | — Pending |
| Self-hostable from day one | Bot is the product; others should be able to run their own | — Pending |
| Full PRD scope as v1 (no slicing) | Spec is internally coherent — sub-MVPs would feel broken | — Pending |
| Full resume across restarts | Long campaigns are the point; ephemeral state would break trust | — Pending |
| Up to 8+ players per session | Larger groups common in home games; initiative UI must handle it | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-21 after initialization*
