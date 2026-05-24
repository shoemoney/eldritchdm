# EldritchDM

## Current State

**Shipped:** v1.0 MVP — Mechanically Honest AI Dungeon Master · 2026-05-23
**Tag:** `v1.0` · **Audit:** passed (71/73 reqs, 97%) · **Tests:** 864 passing / 873 collected
**Repo:** https://github.com/shoemoney/eldritchdm
**License:** Apache 2.0 (flipped from MIT at v1.0 close — adds explicit patent grant)

## Current Milestone: v1.1 Polish

**Goal:** Close v1.0 audit deferrals, level up combat AI from random-targeting to Claudmaster-routed, and add homebrew extensibility — preparing the v1.0 release for production self-hosters.

**Target features:**
- Close SAN-01 (sanitizer in `WeaponSelectModal` + `CharacterReviewModal`)
- Close OPS-02 (`DM_OFFLINE` ephemeral warning on circuit-breaker open)
- `__main__` token-fix parity (friendly error for `python -m eldritch_dm.bot`)
- Ruff cleanup (79 errors / 23 files — 43 auto-fixable)
- Smart MonsterDriver (Claudmaster-routed combat AI)
- YAML-configurable Riposte eligibility (homebrew extensibility)
- `pc_classes` ingest-backfill script (v1.0→v1.1 upgrade tool)

**Strategy note:** Ruff cleanup likely first to clear the 23-file noise that complicated v1.0 audit. Smart MonsterDriver is the largest item; YAML eligibility the smallest. Research will inform whether Claudmaster targeting has known patterns/pitfalls to leverage.

## What This Is

EldritchDM is a local-first, self-hostable **Discord adapter** that exposes the `dm20` MCP server (a complete D&D 5e DM toolkit with autonomous "Claudmaster" mode) through Discord — turning any text channel into a multiplayer 5e table run by an AI Dungeon Master persona called **ShoeGPT**. We do not build a DM engine; we build the Discord skin on top of one that already exists, plus the Discord-specific affordances (timed reactive buttons, turn gatekeeping by user ID, persistent Views across restarts, photo/PDF character ingest for non-D&D-Beyond sheets). It's for tabletop players who want a "forever DM" running entirely on their own hardware with zero API spend and the rule integrity that makes 5e actually feel like 5e.

## Core Value

**Mechanically honest AI DM, on Discord, fully local.** Narration is evocative, but every die roll, HP change, AC check, and turn boundary is enforced by `dm20`'s Python — the LLM (oMLX/`ShoeGPT`) never touches the math. Players never leave Discord; we never leave the laptop.

This held through v1.0. The architecture forces it: every mechanical effect routes through dm20's MCP tools, the LLM only sees narration prompts with pre-computed facts. The 873-test suite includes an adversarial corpus that proves the boundary holds even under malicious player input.

## Architecture — Three-Brain via Existing Infrastructure

- **Voice** → oMLX server (`omlx serve`, port 8765, launchd-supervised as `com.user.omlx`) running model id `ShoeGPT` (Gemma 4 4-bit).
- **Brain** → `dm20` MCP server (97 tools, exposed by oMLX at `:8765/v1/mcp/execute`). Provides: campaigns, characters, multiclass/level-up, combat, encounters, rulebook indexing, Claudmaster autonomous-DM loop, party mode HTTP/WS multiplayer queue, D&D Beyond import, prebuilt adventures.
- **Orchestrator** → **This project.** Discord bot that:
  1. Binds to `dm20`'s Party Mode queue per channel (pop/think/prefetch/resolve)
  2. Owns Discord-specific state (channel → campaign mapping, riposte deadlines, persistent View `custom_id`s, sanitization audit, combat conditions, pc subclass) in a small local SQLite
  3. Provides the timed reactive UI (8s Riposte button) that dm20 doesn't natively model
  4. Enforces turn gatekeeping by Discord user_id (dm20 doesn't know about Discord identities)
  5. Drives monster turns via a minimal `MonsterDriver` (random-target v1; smart Claudmaster targeting → v2)
  6. Ingests non-DDB character sheets via OCR/PDF → schema translation → `dm20__update_character`

## Requirements

### Validated (shipped in v1.0)

- ✓ MCP client to dm20 at `http://localhost:8765/v1/mcp/execute` (async, retry, timeout, error mapping) — v1.0
- ✓ Local SQLite (WAL) for Discord-specific state — v1.0 (6 tables: `channel_sessions`, `persistent_views`, `riposte_timers`, `sanitizer_audit`, `combat_conditions`, `pc_classes`)
- ✓ Discord bot scaffold (discord.py 2.7.1+), slash command tree, defer-discipline lint (EDM001) — v1.0
- ✓ Persistent View infrastructure with `DynamicItem` regex `custom_id`s — v1.0
- ✓ Embed renderers with ≤1-edit/sec coalescer + 5/5s channel budget — v1.0
- ✓ `/start_game` → campaign + Claudmaster + Party Mode + lobby embed + QR — v1.0
- ✓ Ready-check via persistent button → EXPLORATION transition + orchestrator start — v1.0 (G-1 fix landed at audit close)
- ✓ D&D Beyond character ingest — v1.0
- ✓ OCR (ocrmac/easyocr) + PDF (PyMuPDF/pypdf) ingest → schema translate → manual-review modal — v1.0
- ✓ EXPLORATION action batching with 30s window — v1.0
- ✓ COMBAT turn gatekeeping by Discord user_id — v1.0
- ✓ Action buttons → `dm20__combat_action` / weapon select modal — v1.0
- ✓ Dodge shim via `combat_conditions` table — v1.0
- ✓ Riposte 8-second timed reactive button (Battle Master Fighter RAW only) — v1.0
- ✓ Riposte execution → `dm20__combat_action(reaction=true)` shim — v1.0
- ✓ Player input sanitizer with 35-scenario adversarial corpus — v1.0 (SAN-05 audit trail wired at audit close)
- ✓ Health check + 3-strike circuit breaker against oMLX/dm20 — v1.0
- ✓ 8-player Discord session support (verified via virtual-clock load test) — v1.0
- ✓ Full resume across bot restart (persistent Views + riposte timers + active orchestrators) — v1.0
- ✓ Self-hostable: README + .env.example + bootstrap.py + run.py + launchd plist + systemd unit — v1.0

### Active (v1.1 candidates)

- [ ] **SAN-01 completion** — wire `sanitize_player_input` into `WeaponSelectModal` and `CharacterReviewModal` free-text fields (currently only `exploration.py` is covered)
- [ ] **OPS-02 surface** — catch `MCPCircuitOpen` in cog/button callbacks and dispatch `WarningKind.DM_OFFLINE` ephemeral; auto-recover on health restoration
- [ ] **`eldritch_dm.bot.__main__` token-fix parity** — port the friendly missing-token error from `run.py` to `python -m eldritch_dm.bot`
- [ ] **`pc_classes` ingest-backfill script** — one-shot tool for self-hosters upgrading from Phase 4 deployments
- [ ] **Ruff cleanup pass** — 79 pre-existing errors across 23 files (43 auto-fixable, mostly import ordering + `Optional` → `| None`)
- [ ] **Smart `MonsterDriver`** — route monster targeting decisions through Claudmaster instead of random
- [ ] **YAML-configurable Riposte eligibility** — let homebrewers add subclasses without code edits

### Out of Scope

- Building our own combat/dice/rules engine (dm20 + dice MCP already do this — rebuild rejected)
- Building our own campaign memory / summarization (`dm20__add_session_note`/`summarize_session`/`party_knowledge` cover it)
- Building our own SRD/monster/spell lookups
- Game-state SQLite schema for characters/sessions/monsters/memory (dm20 owns `~/.omlx/dm.db`)
- LLM-as-judge for rule disputes
- Image/map generation
- Voice/TTS narration
- Cross-server character portability / cloud sync
- Multiclass mechanics beyond what dm20 already supports
- "Auto-DM mode" without players
- Hosted SaaS variant (local-first is the value prop)
- Mobile clients

## Context

- **Author profile:** Senior dev (Jeremy / Shoemoney). Apple Silicon workstation. Comfortable with Python, async, Discord bots, local LLMs.
- **Hardware:** M-series Mac, oMLX already running on `:8765` with launchd supervisor (`com.user.omlx`). dm20 already exposed via oMLX MCP. Model `ShoeGPT` already loaded.
- **Why local-first:** No API bills, no rate limits, no data leaving the machine.
- **Why MCP-first:** dm20 implements ~70% of the original PRD. Rebuilding would waste months. Bot becomes a focused Discord adapter.
- **Self-hostable goal:** Anyone with oMLX + dm20 should be able to clone this repo, set a Discord token, point at their oMLX endpoint, and run.
- **Codebase shape (post-v1.0):** ~16k LOC Python across `src/eldritch_dm/{config,logging,mcp,persistence,safety,bot,ingest,gameplay,lint}/`. 873 tests. 7 import-linter contracts enforcing layered architecture. Zero new pip deps in Phase 5 — built v1.0 on the pins chosen in Phase 0 research.

## Constraints

- **Runtime:** Python 3.11+
- **Platform:** macOS Apple Silicon primary (Linux best-effort via systemd unit + easyocr extra)
- **Inference / MCP endpoint:** oMLX at `http://localhost:8765/v1` and `/v1/mcp/execute`. Model id `ShoeGPT`. Tool calls reliable.
- **Discord library:** `discord.py` 2.7.1+ (Views, Modals, Select Menus, DynamicItem)
- **Local DB:** SQLite3 WAL — small Discord-state DB only (not gameplay)
- **OCR:** `ocrmac` (Apple Vision) primary on macOS; `easyocr` as `linux-ocr` extra
- **PDF:** `PyMuPDF` (AGPL) primary, `pypdf` MIT fallback
- **Performance:** Discord interaction acks within 3s (EDM001 defer-discipline AST lint enforced); narration ≤150 words; rate-limit-aware embed updates (≤1 edit/sec/msg, 5/5s channel budget)
- **Reliability:** Full resume across bot restart
- **Integrity rule:** Bot never computes game math. All mechanical effects flow through dm20 MCP tools.
- **External dependency:** `dm20` MCP server must be running and reachable via oMLX. If unreachable, bot circuit-breaks to a degraded state instead of guessing.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hybrid: MCP for content, ours for state | dm20 is feature-complete for DM mechanics; rebuilding rejected | ✓ Good |
| oMLX (`omlx serve`) + model `ShoeGPT` | Already deployed, tool calls reliable, launchd-supervised | ✓ Good |
| Discord ↔ dm20 via Party Mode queue | Future-proofs for mixed Discord+browser sessions | ✓ Good |
| Riposte timed UI in v1 | Our differentiator; dm20 doesn't have timed Discord reactions | ✓ Good — shipped with restart-survival drill |
| OCR/PDF ingest in v1 | DDB import covers some users; paper/handwritten sheets matter | ✓ Good |
| Local SQLite for Discord state only | Game state stays in dm20's DB | ✓ Good |
| Player input sanitizer + sentinels | Untrusted text reaches LLM via dm20 | ✓ Good — adversarial corpus protects boundary |
| Three-brain logical boundary preserved | Voice / Brain / Orchestrator still hold | ✓ Good |
| Drop our own DB/engine/memory phases | Direct consequence of pivot | ✓ Good |
| D-A (Phase 5): Delete Phase 4's `_maybe_surface_riposte` (wrong direction) | Trigger should fire on monster-miss-PC, not PC-miss-monster | ✓ Good |
| D-B (Phase 5): Minimal random-target `MonsterDriver` for v1 | Unblocked Riposte testability without scope creep | ✓ Good — v2 will route via Claudmaster |
| D-C (Phase 5): Strict RAW Battle Master only | By-the-book accuracy; v2 YAML for homebrew | ✓ Good |
| D-26 (Phase 5): `Settings.discord_token` Optional | Preflight runs token-free per README | ✓ Good |
| D-F (Phase 5): Sweeper shares `SessionLocks` with click callback | Eliminates click-at-deadline race | ✓ Good |
| Audit: Public Riposte button (not ephemeral) | Required for restart-survival | ✓ Good |
| v1.0 close: License flip MIT → Apache 2.0 | Explicit patent grant matters for AI/LLM project | ✓ Good |

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
*Last updated: 2026-05-23 after v1.0 milestone close*
