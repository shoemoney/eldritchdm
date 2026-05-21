# EldritchDM

## What This Is

EldritchDM is a local-first, self-hostable **Discord adapter** that exposes the `dm20` MCP server (a complete D&D 5e DM toolkit with autonomous "Claudmaster" mode) through Discord — turning any text channel into a multiplayer 5e table run by an AI Dungeon Master persona called **ShoeGPT**. We do not build a DM engine; we build the Discord skin on top of one that already exists, plus the Discord-specific affordances (timed reactive buttons, turn gatekeeping by user ID, persistent Views across restarts, photo/PDF character ingest for non-D&D-Beyond sheets). It's for tabletop players who want a "forever DM" running entirely on their own hardware with zero API spend and the rule integrity that makes 5e actually feel like 5e.

## Core Value

**Mechanically honest AI DM, on Discord, fully local.** Narration is evocative, but every die roll, HP change, AC check, and turn boundary is enforced by `dm20`'s Python — the LLM (oMLX/`ShoeGPT`) never touches the math. Players never leave Discord; we never leave the laptop.

## Architecture — Three-Brain via Existing Infrastructure

- **Voice** → oMLX server (`omlx serve`, port 8765, launchd-supervised as `com.user.omlx`) running model id `ShoeGPT` (Gemma 4 4-bit). Already deployed.
- **Brain** → `dm20` MCP server (97 tools, exposed by oMLX at `:8765/v1/mcp/execute`). Already deployed. Provides: campaigns, characters, multiclass/level-up, combat (start/next_turn/combat_action), encounters, rulebook indexing, Claudmaster autonomous-DM loop, party mode HTTP/WS multiplayer queue, D&D Beyond import, prebuilt adventures.
- **Orchestrator** → **This project.** Discord bot that:
  1. Binds to `dm20`'s Party Mode queue per channel (pop/think/prefetch/resolve)
  2. Owns Discord-specific state (channel → campaign mapping, riposte deadlines, persistent View `custom_id`s, sanitization audit) in a small local SQLite
  3. Provides the timed reactive UI (8s Riposte button) that dm20 doesn't natively model
  4. Enforces turn gatekeeping by Discord user_id (dm20 doesn't know about Discord identities)
  5. Ingests non-DDB character sheets via OCR/PDF → schema translation → `dm20__update_character`

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] MCP client to dm20 at `http://localhost:8765/v1/mcp/execute` (async, retry, timeout, error mapping)
- [ ] Small local SQLite (WAL) for Discord-specific state: channel↔campaign, riposte deadlines, view registry, sanitizer audit
- [ ] Discord bot scaffold (discord.py 2.7.1+), slash command tree, defer discipline lint
- [ ] Persistent View infrastructure: `DynamicItem` custom_id templates, `bot.add_view()` in `setup_hook`, survive restart
- [ ] Embed renderers (lobby, room, combat tracker, character confirm) with ≤1-edit/sec coalescer
- [ ] `/start_game` → `dm20__create_campaign` + `start_claudmaster_session` + `start_party_mode`
- [ ] Ready-check via persistent button → transition to EXPLORATION
- [ ] D&D Beyond character ingest via `dm20__import_from_dndbeyond(url)`
- [ ] OCR (ocrmac) + PDF (PyMuPDF) ingest for non-DDB sheets → oMLX schema translate → manual-review modal → `dm20__update_character`
- [ ] EXPLORATION action batching: collect modal intents, post as one `party_action` via `dm20__party_pop_action`/`party_resolve_action` flow
- [ ] COMBAT turn gatekeeping: only the current actor's Discord user_id can click action buttons
- [ ] Action buttons → `dm20__combat_action` / `use_spell_slot` / `apply_effect`
- [ ] Dodge button → `dm20__apply_effect("dodging")` (or shim if dm20 lacks native dodge condition)
- [ ] Riposte 8-second timed reactive button after eligible monster miss; deadline persists locally for restart survival
- [ ] Riposte execution → `dm20__combat_action(reaction=true)` (or shim)
- [ ] Player input sanitizer: control-token strip, `<player_action>` sentinel wrapping, 500-char cap
- [ ] Health check + circuit breaker against oMLX/dm20
- [ ] Up to 8+ Discord players per session (initiative UI accommodates)
- [ ] Full resume across bot restart: channel sessions rehydrated, persistent Views re-registered, riposte timers resume
- [ ] Self-hostable: README, `.env.example`, bootstrap script, run.py

### Out of Scope

- Building our own combat/dice/rules engine (dm20 + dice MCP already do this — rebuild rejected)
- Building our own campaign memory / summarization (`dm20__add_session_note`/`summarize_session`/`party_knowledge` cover it)
- Building our own SRD/monster/spell lookups (`dm20__search_rules`/`get_*_info` + `dnd__*` cover it)
- Game-state SQLite schema for characters/sessions/monsters/memory (dm20 owns `~/.omlx/dm.db`)
- LLM-as-judge for rule disputes
- Image/map generation
- Voice/TTS narration in v1
- Cross-server character portability / cloud sync
- Multiclass mechanics beyond what dm20 already supports
- "Auto-DM mode" without players

## Context

- **Author profile:** Senior dev (Jeremy / Shoemoney). Apple Silicon workstation. Comfortable with Python, async, Discord bots, local LLMs.
- **Hardware:** M-series Mac, oMLX already running on `:8765` with launchd supervisor (`com.user.omlx`). dm20 already exposed via oMLX MCP. Model `ShoeGPT` already loaded.
- **Why local-first:** No API bills, no rate limits, no data leaving the machine.
- **Why MCP-first:** dm20 implements ~70% of the original PRD. Rebuilding would waste months. Bot becomes a focused Discord adapter.
- **Self-hostable goal:** Anyone with oMLX + dm20 should be able to clone this repo, set a Discord token, point at their oMLX endpoint, and run.

## Constraints

- **Runtime:** Python 3.11+
- **Platform:** macOS Apple Silicon primary
- **Inference / MCP endpoint:** oMLX at `http://localhost:8765/v1` and `/v1/mcp/execute`. Model id `ShoeGPT`. Tool calls reliable.
- **Discord library:** `discord.py` 2.7.1+ (Views, Modals, Select Menus, DynamicItem)
- **Local DB:** SQLite3 WAL — small Discord-state DB only (not gameplay)
- **OCR:** `ocrmac` (Apple Vision) primary on macOS; `easyocr` as `linux-ocr` extra
- **PDF:** `PyMuPDF` primary, `pypdf` MIT fallback
- **Performance:** Discord interaction acks within 3s (defer-first discipline); narration ≤150 words; rate-limit-aware embed updates (≤1 edit/sec/msg)
- **Reliability:** Full resume across bot restart
- **Integrity rule:** Bot never computes game math. All mechanical effects flow through dm20 MCP tools.
- **External dependency:** `dm20` MCP server must be running and reachable via oMLX. If unreachable, bot circuit-breaks to a degraded "DM is offline" state instead of guessing.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hybrid: MCP for content, ours for state | dm20 is feature-complete for DM mechanics; rebuilding rejected | ✓ Good |
| oMLX (`omlx serve`) + model `ShoeGPT` | Already deployed, tool calls reliable, launchd-supervised | ✓ Good |
| Discord ↔ dm20 via Party Mode queue | Future-proofs for mixed Discord+browser sessions; clean separation | ✓ Good |
| Riposte timed UI in v1 | Our differentiator; dm20 doesn't have timed Discord reactions | — Pending |
| OCR/PDF ingest in v1 | DDB import covers some users; paper/handwritten sheets matter | — Pending |
| Local SQLite for Discord state only | Game state stays in dm20's `~/.omlx/dm.db`; ours holds channel↔campaign, timers, view ids | — Pending |
| Player input sanitizer + sentinels | Even though we don't drive the prompt directly, untrusted text reaches LLM via dm20 | — Pending |
| Three-brain logical boundary preserved | Voice / Brain / Orchestrator still hold — just relocated | ✓ Good |
| Drop our own DB/engine/memory phases | Direct consequence of pivot | ✓ Good |

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
*Last updated: 2026-05-21 after MCP-hybrid pivot*
