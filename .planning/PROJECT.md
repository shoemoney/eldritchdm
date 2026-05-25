# EldritchDM

## Current State

**Current Milestone:** v1.4 Writer-Queue Reliability — **HALT-DEFERRED** (premises invalidated; rescope needed)
**What happened:** Phase 15 agent ran empirical reproduction and found:
  - HANG-01 (`test_writer_queue_drain_timeout`) and HANG-02 (`test_close_cleanly_shuts_down`) **do NOT reproduce** at HEAD — they pass in isolation AND in the full suite.
  - `src/eldritch_dm/persistence/connection.py:WriterQueue` **already implements** the exact `asyncio.Event` + sentinel-value pattern v1.4 CONTEXT proposed adding.
  - The real residual bug is HANG-03 / FLAKE-02 — a test-isolation issue in `tests/bot/conftest.py:bot_factory` (loads cogs via `load_extension`, doesn't unload, pollutes `tests/integration/test_phase3_smoke.py` mock.patch chain).
  - Agent halt-and-reported per HARD CONSTRAINT. Halt-report: `.planning/phases/15-writer-queue-fix/15-HALT-REPORT.md`.
**Orchestrator attempted inline fix** (autouse sys.modules-clear fixture) — caused pytest hangs in 3 separate verification runs. Reverted untested.

**Rescope for v1.5:** Single focused phase — "FLAKE-02 closure via test-isolation fix". Three candidate approaches (see halt-report §3): (a) `bot_factory` teardown with `unload_extension`, (b) dependency-inject the mocked `ingest` into `IngestCog`, (c) `importlib.reload` at phase3 test setup. Approach (a) is cleanest. **Needs fresh-context session** since this orchestrator session has degraded test-runner stability (3 pytest hangs).

**Shipped:** v1.3 Hygiene Sweep · 2026-05-25 · `v1.3` · 2.5/3 (FLAKE-02 partial — still partial after v1.4)
**Recent hotfix:** v1.2.1 · 2026-05-24 · pricing.yaml verified
**Earlier:** v1.2 Quality Flywheel · `v1.2` 8/8 / v1.1 Polish · `v1.1` 10/10 / v1.0 MVP · `v1.0` 71/73
**Repo:** https://github.com/shoemoney/eldritchdm
**License:** Apache 2.0

## Next Milestone Recommendation (v1.4)

**WRITER-QUEUE-HANG-01 (top priority)** — Phase 14 surfaced two pre-existing pytest HANGS that cannot be killed by `pytest-timeout` (C-level thread boundary in the bot's writer-queue shutdown path). Until these are fixed, full-suite green is blocked. Predates v1.3 — last touched Phase 5 + Phase 6.

Affected files:
- `tests/bot/test_setup_hook.py::test_writer_queue_drain_timeout` (Phase 5, eb4e0f7)
- `tests/bot/test_bot_lifecycle.py::test_close_cleanly_shuts_down` (Phase 6, d6e87c4)

Approach: rewrite the bot's writer-queue shutdown to be cleanly cancellable (likely needs an asyncio.Event-based stop signal in the writer thread loop). Once unblocked, FLAKE-02's residual phase3_smoke pollution should resolve in the same pass.

Other v1.4 candidates (per prior PROJECT.md):
- **Cache architecture** (user's original hint from v1.2.1 turn): multi-level dm20 MCP query cache + persistent character cache + narration response cache + embedding cache. 3-4 phases.
- **UX/feature expansion**: streaming "monster is thinking" embed + AOE/multi-target tactic selection + cross-round monster memory + hot-reload eligibility.yaml + Discord DM-to-owner on budget breach.

<details>
<summary>v1.3 milestone retrospective</summary>

**Wins:**
- FLAKE-01 ✓ OCR + prometheus_client skip-gates ship clean
- FLAKE-03 ✓ All 14 v1.1+v1.2 SUMMARYs backfilled with `requirements_completed:` frontmatter; CI gate prevents drift
- Test failures dropped 75% (8→2)
- Backfill script + CI gate are reusable tools for future milestones

**Partial:**
- FLAKE-02: 1 of 2 polluters root-caused and fixed (structlog/stdlib logging via `tests/conftest.py` autouse reset). Second polluter is downstream of writer-queue hangs → properly scoped to v1.4 as WRITER-QUEUE-HANG-01.

**Honest reporting:** executor honored the HARD CONSTRAINT halt-report contract rather than silently marking green.

</details>

## Next Milestone Candidates (v1.3 themes)

- **v1.2.1 hotfix (recommended first)**: Refresh `database/pricing.yaml` with live 2026 vendor pricing (current ships PLACEHOLDER values; cost-guard alerts depend on this being accurate). Should be a 1-task patch within 2 weeks of v1.2 GA.
- **Discord-native monitoring UX**: Discord DM-to-owner on budget breach / degraded mode trip (deferred from Phase 13); /admin slash command for live KPIs + cost summary.
- **Webhook + multi-day cost rollups**: Phase 13 alerts.yaml currently does file/syslog only; v1.3 adds webhook routing + weekly/monthly cost aggregation.
- **Eval expansion**: Crowd-sourced corpus contributions via GitHub PRs, inter-judge agreement studies (Cohen's kappa across multiple judge models), auto-detect judge-model drift.
- **Pre-existing test flakes**: OCR backend env tests + `test_phase3_smoke` test-pollution flake — same items carried since v1.1; deserve a focused cleanup phase.
- **UX layer**: Streaming "monster is thinking" embed (Phase 10 deferral); AOE/multi-target tactic selection (Phase 10 deferral); cross-round monster memory.
- **Homebrew expansion**: Hot-reload `eligibility.yaml` (Phase 8 deferral — currently restart-to-apply); YAML-configurable spell-component requirements.

<details>
<summary>v1.2 milestone retrospective</summary>

**Goal:** Close the loop on v1.1's SmartMonsterDriver — answer "are monsters fair AND smart" with data, not just compiles.

**Shipped (8/8 requirements):**
- OBS-01/02: OTel instrumentation (D-65 8-attribute schema, lazy-import zero-cost-when-disabled) + opt-in docker-compose Phoenix stack with 3 default dashboards
- EVAL-01/02/03: TacticalJudge with SemVer-versioned prompt; 50-scenario Apache-2.0 corpus across 5 archetypes; `eldritch-dm-eval` CLI with `--baseline` diff (regression-detection exit codes)
- MON-01/02/03: 5 KPI live monitors + opt-in Prometheus `:9090/metrics`; alerts.yaml degraded-mode trigger at P99>1500ms for 5min with auto-recover at <1200ms (hysteresis); cost guard with `ELDRITCH_DAILY_LLM_BUDGET_USD` cap + `eldritch-dm-cost-report` CLI

**Cross-phase wiring:** P11 `traced_decision` → P12 judge spans → P13 KPI monitors → degraded-mode trigger. Each phase explicitly verifies its upstream link.

**Critical follow-up:** `database/pricing.yaml` ships PLACEHOLDER token prices; v1.2.1 patch must refresh with live 2026 vendor pricing before operators rely on cost-guard alerts.

</details>

<details>
<summary>v1.1 milestone retrospective</summary>

**Goal:** Close v1.0 audit deferrals, add homebrew extensibility (YAML Riposte eligibility), close the v1.0 → v1.1 upgrade gap (`pc_classes` backfill), and level up combat AI from random to Claudmaster-routed targeting.

**Shipped (10/10 requirements):**
- DEBT-01/02: ruff debt zeroed (79→0); cold-start E2E regression guard with historical RED/GREEN proof at v1.0 commit `7d307a1`
- SAFETY-01/02/03: modal sanitization across 3 modals; DM_OFFLINE warning + 30s debouncer + `@catch_circuit_open` decorator; shared `config.token_guard` helper
- HOMEBREW-01/02: 3-tier YAML eligibility loader (env > user > repo default); `gameplay/normalize.py` extracted
- UPGRADE-01: `eldritch-dm-backfill-pc-classes` CLI with `--dry-run` + `--force` + idempotent default
- COMBAT-13/14: SmartMonsterDriver via existing AsyncOpenAI/oMLX client (no new MCP deps); INT-gated; 1500ms hard timeout with fail-soft to random; per-round FIFO cache; 16-scenario adversarial corpus

</details>

Candidate v1.2 themes (refine in `/gsd-new-milestone`):

- **Quality flywheel for SmartMonsterDriver** — LLM-as-judge tactical-scoring rubric + Arize Phoenix observability (deferred from Phase 10 per D-59); needed to close the loop on "are monsters fair AND smart"
- **Streaming "monster is thinking" embed** — UX nicety once Phoenix tracing is live
- **AOE + multi-target tactic selection** — current scope is single-target only
- **Cross-round monster memory** — session-level state for monsters that remember prior-round actions
- **dm20 schema extension** for subclass — closes Phase 9 C-1 workaround (currently writes `subclass=''` with operator hand-edit recipe in INSTALL.md)
- **PID-file concurrent-backfill guard** — Phase 9 C-2 deferral
- **Address pre-existing test flakes** — OCR backend env tests + `test_phase3_smoke` test-pollution flake; predate v1.1, deserve a focused cleanup phase
- **Hot-reload for eligibility.yaml** — Phase 8 explicitly deferred to v1.2 (currently restart-to-apply)

<details>
<summary>v1.1 milestone retrospective</summary>

**Goal:** Close v1.0 audit deferrals, add homebrew extensibility (YAML Riposte eligibility), close the v1.0 → v1.1 upgrade gap (`pc_classes` backfill), and level up combat AI from random to Claudmaster-routed targeting.

**Shipped (10/10 requirements):**
- DEBT-01/02: ruff debt zeroed (79→0); cold-start E2E regression guard with historical RED/GREEN proof at v1.0 commit `7d307a1`
- SAFETY-01/02/03: modal sanitization across 3 modals; DM_OFFLINE warning + 30s debouncer + `@catch_circuit_open` decorator; shared `config.token_guard` helper
- HOMEBREW-01/02: 3-tier YAML eligibility loader (env > user > repo default); `gameplay/normalize.py` extracted
- UPGRADE-01: `eldritch-dm-backfill-pc-classes` CLI with `--dry-run` (SQLite read-only) + `--force` + idempotent default
- COMBAT-13/14: SmartMonsterDriver via existing AsyncOpenAI/oMLX client (no new MCP deps); INT-gated (≤4 random, ≥8 LLM, 5-7 mixed); 1500ms hard timeout with fail-soft to random; per-round FIFO cache; 16-scenario adversarial corpus

**Strategy note for v1.2:** the Phase-10 SmartMonsterDriver lands the largest behavioral change in v1.1 but ships without an evaluation rubric or production tracing. v1.2 should prioritize the quality flywheel (LLM-as-judge + Arize Phoenix) before adding more autonomous-AI surface area.

</details>

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
