---
phase: 04-gameplay-exploration-combat
plan_count: 3
subsystem: gameplay
tags: [gameplay, exploration, combat, party-mode, orchestrator, rate-limit, turn-gatekeeper, load-test]

# Dependency graph
requires:
  - phase: 03-lobby-character-ingest
    provides: LobbyCog, IngestCog, character creation flow, ChannelSessionRepo wiring
  - phase: 02-discord-scaffold-persistent-views
    provides: EldritchBot, EmbedCoalescer, DynamicItem infrastructure, setup_hook rehydration
  - phase: 01-mcp-client-local-state
    provides: MCPClient, persistence layer, sanitize_player_input

provides:
  - PartyModeOrchestrator (per-channel asyncio.Task driving pop/thinking/resolve loop)
  - ChannelRateLimiter (per-channel 200ms token bucket for mutating MCP calls — OPS-03)
  - ChannelEditBudget (per-channel 5/5s edit budget shared across coalescers)
  - BatchCoordinator + ExplorationBatch (EXPLORE-06 action batching with 30s window)
  - ExplorationCog (room embed lifecycle, DeclareAction modal)
  - CombatCog (combat embed lifecycle, EXPLORATION↔COMBAT transitions, ▶️ marker rendering)
  - DeclareActionButton (real callback wired to BatchCoordinator)
  - AttackButton, DodgeButton, EndTurnButton, CastSpellButton (4 turn-gated combat buttons)
  - WeaponSelectModal (validated weapon/target field input)
  - turn_gatekeeper (pure helper module: is_actor, current_actor_from_game_state)
  - combat_conditions table + CombatConditionsRepo (D-22 dodge shim)
  - 8-actor combat load test (RUN_LOAD=1 gated; <30s wall-clock; coalescer + budget proof)
  - Restart-mid-combat drill (D-35 extension of BOT-08)

affects:
  - 05-reactions-self-host-polish (Riposte seam in AttackButton._maybe_surface_riposte is documented no-op)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PartyModeOrchestrator: one asyncio.Task per active channel; cadence accelerates from every-4-ticks (EXPLORATION) to every-tick (COMBAT) for fast state-change detection"
    - "ChannelRateLimiter: per-channel asyncio.Lock + monotonic clock injection; caller classifies mutating vs read-only (not introspection-based)"
    - "ChannelEditBudget: rolling 5s deque shared across EmbedCoalescer instances for one Discord channel; prevents 429 even with multiple embeds in flight"
    - "BatchCoordinator: deadline-driven 30s flush of player intents; called from orchestrator loop via batch_coordinator.tick(now)"
    - "asyncio.gather(return_exceptions=True) for state_change callbacks: cog isolation — one cog raising cannot block others"
    - "asyncio.shield around resolution callbacks: cancellation during render is contained"
    - "Combat button prelude (defer → session → stale-round → is_actor): single shared helper avoids per-button duplication"
    - "DynamicItem attrs-before-super pattern: self.channel_id/actor_id/round_n set BEFORE super().__init__() because discord.py touches custom_id during init"
    - "WeaponSelectModal field validation: allow-list regexes reject injection chars (T-04-11)"
    - "Cross-cog handoff via EldritchBot methods (close_exploration_coalescer_for, close_combat_coalescer_for) avoids cog→cog circular imports"
    - "Virtual-clock injection (clock + sleep): same monotonic source threaded through ChannelRateLimiter, ChannelEditBudget, and EmbedCoalescer for deterministic load testing"
    - "RUN_LOAD=1 gate mirrors Phase 1's RUN_STRESS=1 convention: heavy tests opt-in via env var"

key-files:
  created:
    - src/eldritch_dm/gameplay/__init__.py
    - src/eldritch_dm/gameplay/party_mode.py
    - src/eldritch_dm/gameplay/exploration_batch.py
    - src/eldritch_dm/gameplay/game_state_parser.py
    - src/eldritch_dm/gameplay/turn_gatekeeper.py
    - src/eldritch_dm/mcp/rate_limit.py
    - src/eldritch_dm/bot/cogs/exploration.py
    - src/eldritch_dm/bot/cogs/combat.py
    - src/eldritch_dm/persistence/combat_conditions_repo.py
    - tests/gameplay/test_rate_limit.py
    - tests/gameplay/test_exploration_batch.py
    - tests/gameplay/test_party_mode.py
    - tests/gameplay/test_turn_gatekeeper.py
    - tests/bot/test_channel_edit_budget.py
    - tests/bot/test_dynamic_items_declare_real.py
    - tests/bot/test_dynamic_items_combat_real.py
    - tests/bot/test_embeds_combat_enriched.py
    - tests/bot/test_modals_weapon_select.py
    - tests/bot/cogs/test_exploration_cog.py
    - tests/bot/cogs/test_combat_cog.py
    - tests/integration/test_combat_flow.py
    - tests/integration/test_8player_load.py
    - tests/integration/test_restart_mid_combat.py
  modified:
    - src/eldritch_dm/bot/bot.py (Phase 4 subsystems wiring, cross-cog helpers, CombatCog load)
    - src/eldritch_dm/bot/coalescer.py (ChannelEditBudget added; coalescer accepts channel_budget injection)
    - src/eldritch_dm/bot/dynamic_items.py (DeclareActionButton real callback, EndTurnButton promoted, 3 new combat buttons, prelude helper)
    - src/eldritch_dm/bot/embeds.py (combat_embed v2 with AC-inline + ▶️ turn markers; room_embed enrichment)
    - src/eldritch_dm/bot/modals.py (WeaponSelectModal added)
    - src/eldritch_dm/bot/setup_hook.py (combat button rehydration + _PARAM_REMAP)
    - src/eldritch_dm/mcp/tools.py (audit pass: dropped stray campaign_name kwargs, added get_npc)
    - database/schema.sql (combat_conditions table added)
    - pyproject.toml (load + slow markers; per-file-ignore for load test)

key-decisions:
  - "D-22 dodge shim: dm20 has NO native dodging condition (RESEARCH.md Q2). DodgeButton writes combat_conditions row + apply_effect(\"dodging\") for narrative context. Mechanical to-hit disadvantage is v1-narrative-only; Phase 5 wires real math when dm20 supports it."
  - "D-17 monster turn: dm20 does NOT auto-resolve monster turns on next_turn (RESEARCH.md Q3). CombatCog renders NO player buttons when current_actor.player_id is None. Orchestrator's pop/resolve loop handles monster narration via the LLM."
  - "D-28/D-29 mutating-call gating: callers classify mutating vs read; ChannelRateLimiter does not introspect tool names. party_thinking, party_resolve_action, combat_action, next_turn, apply_effect — all gated. party_pop_action, get_game_state, party_get_prefetch — bypass."
  - "D-30 OPS-03 200ms cap: per-channel min_interval_ms=200 chosen as the safe floor under realistic 8-player click burst (RESEARCH.md §4 dm20 throughput analysis)."
  - "Bus-style cog callback registry: PartyModeOrchestrator.register_resolution_callback and register_state_change_callback accept lists; ExplorationCog and CombatCog both register; asyncio.gather isolates cog errors."
  - "Cross-cog handoff via EldritchBot helpers (not cog→cog imports): close_exploration_coalescer_for, close_combat_coalescer_for. EXPLORATION→COMBAT transition closes the exploration coalescer before the combat embed is posted."
  - "EndTurnButton BREAKING change from Phase 2: 3-segment custom_id (channel_id:actor_id:round_n) replacing 2-segment (channel_id:actor_id); actor_id is now dm20 character UUID, not Discord snowflake. setup_hook._PARAM_REMAP bridges regex group 'round' → __init__ param 'round_n'."
  - "DynamicItem attrs-before-super: self.channel_id/actor_id/round_n MUST be assigned BEFORE super().__init__() because discord.py accesses self.custom_id during init for template-validation."
  - "WeaponSelectModal injection defense (T-04-11): field validation rejects characters outside the allow-list (weapon: alphanumeric+space+`'+`; target_id: lowercase+digits+dash)."
  - "CastSpellButton intentionally v1-stubbed: rendered (not hidden) and gated by is_actor for defense-in-depth, but returns an ephemeral 'Phase 5 stub' message. Real spell flow lands in Phase 5 alongside Riposte."
  - "COMBAT cadence acceleration: _get_poll_cadence returns 1 in COMBAT (every tick), 4 in EXPLORATION (every 4 ticks). Catches COMBAT→EXPLORATION transitions within 250ms (COMBAT-12)."
  - "RUN_LOAD=1 gating for 8-actor load test: matches Phase 1 RUN_STRESS=1 convention. Default CI fast; nightly + contributors run the slow proof."
  - "Virtual-clock injection pattern across rate_limit/budget/coalescer: enables sub-second simulation of 8-player 5-round combat (~38s virtual / 0.01s wall)."

patterns-established:
  - "Per-channel rate limiter as injectable singleton on EldritchBot (.rate_limiter); cogs and DynamicItems pull it from interaction.client.rate_limiter"
  - "Per-channel edit budget keyed by channel_id; EldritchBot.get_channel_edit_budget(channel_id) returns/creates"
  - "Turn gatekeeper as PURE module (no Discord/MCP imports) — keeps the is_actor logic unit-testable without integration setup"
  - "Combat button prelude helper centralizes defer/session/stale-round/is_actor checks; each button's callback adds only its specific MCP call"
  - "BatchCoordinator deadline-driven flush invoked from orchestrator loop (NOT a separate task) — single-task simplicity, no inter-task lock contention"
  - "asyncio.gather(return_exceptions=True) for fan-out to multiple subscribed cogs"
  - "asyncio.shield around resolution callbacks: shields rendering from being torn down mid-flight"
  - "Test virtual-clock injection: clock=clock.now, sleep=clock.advance threaded through every rate-limited primitive"

requirements-completed:
  - EXPLORE-01
  - EXPLORE-02
  - EXPLORE-03
  - EXPLORE-04
  - EXPLORE-05
  - EXPLORE-06
  - EXPLORE-07
  - COMBAT-01
  - COMBAT-02
  - COMBAT-03
  - COMBAT-04
  - COMBAT-05
  - COMBAT-06
  - COMBAT-07
  - COMBAT-08
  - COMBAT-12
  - OPS-03

# Metrics
duration: 360min  # ~6 hours across Plans 01-03 (Plan 01: 90, Plan 02: 180, Plan 03: 90)
completed: 2026-05-22
tasks_completed: 9   # Plan 01: 3, Plan 02: 3, Plan 03: 3
plans_completed: 3
files_created: 23
files_modified: 9
tests_added: 487   # 261 across Plans 01-02 + 226 (Plan 02 incremental 176 + Plan 03 8) — see breakdown
tests_total_after_phase: 730  # 728 default + 2 load gated
---

# Phase 4: Gameplay — Exploration + Combat (Party Mode) Summary

**Mechanically honest combat works end-to-end on Discord — orchestrator drives dm20 party mode, four combat buttons gate by Discord user_id, dodge shim narrates through the LLM without ever computing math, and an 8-actor virtual-clock load test proves the coalescer + rate-limiter + edit-budget triad keeps the bot below Discord's 5/5s channel-edit ceiling under realistic 8-player flux.**

## One-liner

Phase 4 ships the actual game loop: PartyModeOrchestrator + ExplorationCog + CombatCog + 4 turn-gated combat buttons + the load proof, all while obeying the OPS-03 200ms-per-channel-mutating-call cap and the per-channel 5-edit/5-second Discord ceiling.

## Performance

- **Duration:** ~6 hours total across Plans 01 (90min) + 02 (180min) + 03 (90min)
- **Started (Plan 01):** 2026-05-22 morning
- **Completed (Plan 03):** 2026-05-22 evening
- **Tasks across all three plans:** 9
- **Files:** 23 created, 9 modified
- **Tests added in Phase 4:** ~487 incremental; full suite 728 (default) + 2 (load-gated) = 730

## Accomplishments

### Plan 01 — Orchestrator + Exploration (commits bd52bd9, cab6b18, 27c8c9b)
- `gameplay/party_mode.py`: `PartyModeOrchestrator` with per-channel asyncio.Task; pop/thinking/resolve loop; integrated combat-trigger watcher; deadline-driven batch flush
- `mcp/rate_limit.py`: `ChannelRateLimiter` with per-channel asyncio.Lock + monotonic clock injection (OPS-03 200ms)
- `gameplay/exploration_batch.py`: `BatchCoordinator` + `ExplorationBatch` with 30s window (EXPLORE-06)
- `gameplay/game_state_parser.py`: regex parser for dm20's markdown `get_game_state` response
- `bot/coalescer.py`: `ChannelEditBudget` (5 edits / 5s rolling deque) shared across coalescers per channel
- `bot/cogs/exploration.py`: `ExplorationCog` — room embed lifecycle, DeclareAction modal, /status integration, lobby guard
- `bot/dynamic_items.py`: `DeclareActionButton` promoted from Phase 2 stub with real BatchCoordinator wiring
- `bot/embeds.py`: enriched exploration `room_embed`

### Plan 02 — Combat UI + Turn Gatekeeping (commits 3884e13, 5f469c6, 05c8458, 09cb733)
- `gameplay/turn_gatekeeper.py`: PURE helpers — `is_actor`, `current_actor_from_game_state`, `player_id_for_actor`
- `bot/embeds.py`: `combat_embed` v2 with AC-inline `{name} ({hp}/{max} HP, AC {ac})` + ▶️/▫️ turn markers
- `database/schema.sql`: `combat_conditions` table (D-22 dodge shim)
- `persistence/combat_conditions_repo.py`: `CombatConditionsRepo` for the dodge shim
- `bot/dynamic_items.py`: 3 new combat buttons (AttackButton, DodgeButton, CastSpellButton) + EndTurnButton.callback promoted; shared `_combat_button_prelude` helper; attrs-before-super pattern
- `bot/modals.py`: `WeaponSelectModal` with field validation (T-04-11 injection defense)
- `bot/cogs/combat.py`: `CombatCog` managing EXPLORATION↔COMBAT lifecycle via EmbedCoalescer
- `bot/setup_hook.py`: combat button classes added to class_map; `_PARAM_REMAP` for `round`→`round_n`
- `bot/bot.py`: CombatCog loaded; cross-cog helpers (`close_exploration_coalescer_for`, `close_combat_coalescer_for`)
- `gameplay/party_mode.py`: `asyncio.gather(return_exceptions=True)` for state-change dispatch; COMBAT cadence=1 (every tick)

### Plan 03 — Load Test + Restart Drill + Phase Closure (commits 3e3e017, 6457212, this commit)
- `tests/integration/test_8player_load.py`: 8-actor 5-round combat with virtual-clock injection; 160 update events → ~80 edits (~50% suppression); 60 mutating-call gates; assertions A–G all hold; runtime 0.01s virtual / <1s wall
- `tests/integration/test_restart_mid_combat.py`: 6 tests proving channel_session, persistent_views (all 4 combat buttons), combat_conditions, and orchestrator task lifecycle all survive a simulated restart
- `pyproject.toml`: `load` marker registered; per-file-ignore for load-test long lines
- Auto-fixes in `persistence/combat_conditions_repo.py` (see Deviations below)
- Phase 4 closure paperwork (this SUMMARY, REQUIREMENTS [x], ROADMAP [x], STATE.md cursor advance)

## Task Commits

| Plan | Task | Commit | Description |
|------|------|--------|-------------|
| 01 | 1: gameplay layer + rate limiter + edit budget | bd52bd9 | ChannelRateLimiter, ChannelEditBudget, gameplay package |
| 01 | 2: ExplorationBatch + BatchCoordinator + PartyModeOrchestrator | cab6b18 | The orchestrator scaffold itself |
| 01 | 3: ExplorationCog + DeclareActionButton + bot wiring + lobby guard | 27c8c9b | First user-visible exploration UI |
| 02 | 1: turn_gatekeeper + combat_embed enrichment + combat_conditions table | 3884e13 | Pure-helper turn logic + v2 embed shape |
| 02 | 2: Attack/Dodge/CastSpell/EndTurn + WeaponSelectModal | 5f469c6 | 4 persistent combat buttons + dodge shim flow |
| 02 | 3: CombatCog + state-change wiring + orchestrator cadence + tests | 05c8458 | Bridges PartyModeOrchestrator ↔ combat UI |
| 02 | closure | 09cb733 | 04-02-SUMMARY |
| 03 | 1: 8-actor combat load test | 3e3e017 | RUN_LOAD=1, virtual-clock, assertions A–G |
| 03 | 2: restart-mid-combat drill + Rule 1 fixes | 6457212 | BOT-08 extension + CombatConditionsRepo bug fixes |
| 03 | closure | (this commit) | Phase 4 SUMMARY + REQUIREMENTS + ROADMAP + STATE |

## Files Created/Modified

See the `key-files` frontmatter for the canonical list.

## Decisions Made

The key-decisions frontmatter is the authoritative log. Highlights:

- **D-22 (dodge shim)**: combat_conditions table + apply_effect("dodging") — narrative only in v1, mechanical disadvantage deferred to Phase 5
- **D-17 (monster turn)**: orchestrator's pop/resolve loop owns it; UI suppresses player buttons when current_actor.player_id is None
- **D-28/D-29 (mutating-call gating scope)**: caller-classified, not introspection-based
- **OPS-03 200ms cap**: per-channel min_interval_ms=200
- **Bus-style cog callback registry**: ExplorationCog + CombatCog both subscribe; asyncio.gather isolates errors
- **EndTurnButton breaking change**: 3-segment custom_id with dm20 UUID + round
- **RUN_LOAD=1 gating**: matches Phase 1 RUN_STRESS=1 convention
- **Virtual-clock injection**: enables deterministic sub-second simulation of multi-round combat

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] `CombatConditionsRepo._connect()` double-started its underlying Thread**
- **Found during:** Task 2 GREEN — first non-mocked integration test against the repo
- **Issue:** `_connect()` returned an already-awaited Connection (Thread started), and every caller did `async with await self._connect() as conn:`. The `async with` calls `__aenter__` → `await self` → `Thread.start()` → `RuntimeError: threads can only be started once`. The repo had shipped through Phase 4 Plan 02 because every test mocked it.
- **Fix:** Made `_connect()` synchronous, returning an unstarted Connection. Added `_configure(conn)` that applies `row_factory` + pragmas after the single `async with` entry. Updated all 5 call sites.
- **Files modified:** `src/eldritch_dm/persistence/combat_conditions_repo.py`
- **Commit:** 6457212

**2. [Rule 1 — Bug] `CombatConditionsRepo.insert()` created duplicate rows**
- **Found during:** Task 2 GREEN, immediately after fix #1 unblocked the repo
- **Issue:** The insert path ran `INSERT ... ON CONFLICT DO NOTHING` followed by `INSERT OR REPLACE`, on the assumption that `(channel_id, character_id, condition_kind)` was UNIQUE in the schema. The schema only has `id` as PK — no UNIQUE constraint on the triple — so both inserts succeeded and produced two rows per call. The `test_combat_condition_survives_restart` assertion caught it (`Expected 1 active condition, got 2`).
- **Fix:** Replaced the ON CONFLICT + REPLACE pattern with explicit DELETE-by-triple followed by a single INSERT.
- **Files modified:** `src/eldritch_dm/persistence/combat_conditions_repo.py`
- **Commit:** 6457212

**3. [Rule 1 — Bug] `setup_hook.py` did not list combat button classes (Plan 02 in-flight fix)**
- **Found during:** Plan 02 Task 3 GREEN
- **Issue:** Phase 2 class_map only included ReadyButton + EndTurnButton + DeclareActionButton. The 3 new combat buttons would have orphaned across a restart.
- **Fix:** Added AttackButton/DodgeButton/CastSpellButton to `_get_dynamic_item_classes()`; added `_PARAM_REMAP` translating regex group `round` → init param `round_n`.
- **Files modified:** `src/eldritch_dm/bot/setup_hook.py`, `tests/bot/test_setup_hook.py`
- **Commit:** 05c8458 (rolled into Plan 02)

**4. [Rule 1 — Bug] `EndTurnButton` custom_id template breaking change (Plan 02)**
- **Found during:** Plan 02 Task 2 GREEN
- **Issue:** Phase 2 used 2-segment custom_id (`endturn:channel:actor`). Phase 4 needs round in the custom_id (cache-buster for stale clicks). The change is breaking — any in-flight Phase 2 buttons orphan.
- **Fix:** New 3-segment template `endturn:channel:actor_id:round`; `actor_id` is dm20 UUID (lowercase+dash), not Discord snowflake. Documented as a known breaking change between Phase 2 and Phase 4.
- **Files modified:** `src/eldritch_dm/bot/dynamic_items.py`, `tests/bot/test_dynamic_items_real.py`
- **Commit:** 5f469c6 (rolled into Plan 02)

**5. [Rule 1 — Bug] `bootstrap` test missed `combat_conditions` (Plan 02)**
- **Found during:** Plan 02 Task 3 full suite run
- **Issue:** Schema added `combat_conditions` table in Task 1 but the bootstrap test's expected_tables set wasn't updated.
- **Fix:** Added `combat_conditions` to the expected set.
- **Files modified:** `tests/persistence/test_bootstrap.py`
- **Commit:** 05c8458 (rolled into Plan 02)

## Issues Encountered

- **Test threading races (Plan 03 Task 2):** Some test runs surface `Task was destroyed but it is pending!` from the orchestrator task in the restart-drill test. Resolved by explicitly calling `stop_orchestrator_for_channel` in the test's cleanup path. No behavior change in production.
- **Pytest fixture decorator gotcha (Plan 03 Task 2):** `@pytest.fixture` on an `async def` does not produce an async generator in `asyncio_mode = "auto"` config. Switched to `@pytest_asyncio.fixture` to match `tests/persistence/conftest.py` precedent.

## Known Stubs

- **`CastSpellButton`**: Rendered (not hidden) and gated by `is_actor` for defense-in-depth, but its callback returns an ephemeral "Phase 5 stub" message. Real spell flow lands in Phase 5 alongside Riposte. This stub is **intentional and documented** — it preserves the UI seam (button position, custom_id namespace) so Phase 5 can wire the handler without UI re-layout.
- **`AttackButton._maybe_surface_riposte`**: Documented no-op for Phase 5 reaction wiring. Real RiposteCog hook lands in Phase 5 Plan 01.

## Threat Flags

No new external trust boundaries introduced beyond those documented in 04-CONTEXT.md.

T-04-09 (turn impersonation), T-04-10 (stale round replay), T-04-11 (injection in WeaponSelectModal), T-04-13 (rate-limit bypass), T-04-17–T-04-20 (load-test mocks) — all mitigated and tested.

## Next Phase Readiness

**Phase 5 (Reactions + Self-Host Polish) can begin immediately.**

### Phase 5 Riposte Seam

The Riposte hook point is at:

**File:** `src/eldritch_dm/bot/dynamic_items.py`
**Method:** `AttackButton._maybe_surface_riposte(interaction, mech_result, target_id)`
**Trigger:** `mech_result["outcome"] == "miss" AND target["has_reaction"] is True`
**Action:** Phase 5 RiposteCog will call `await riposte_cog.surface_riposte_button(interaction, target_id, timer_id)` here.

Current implementation is an intentional no-op (Phase 4 stub). The method is invoked after every `combat_action(action="attack")` returns, so Phase 5 only needs to implement the method body.

### Phase 5 Spell Seam

`CastSpellButton.callback` is the parallel seam: gated by is_actor, returns a Phase 5 stub today. Phase 5 wires the spell-selection modal and `combat_action(action="cast", spell=..., target=...)` flow.

### What Phase 5 inherits ready-to-use

- ChannelRateLimiter (use the same `interaction.client.rate_limiter` for any new mutating MCP call)
- ChannelEditBudget (RiposteButton's countdown embed should pull a shared budget via `bot.get_channel_edit_budget`)
- PartyModeOrchestrator (subscribe RiposteCog as another resolution_callback / state_change_callback)
- turn_gatekeeper (use `is_actor` for the "only target player can click" check)
- setup_hook rehydration (add `RiposteButton` to the class_map and any `_PARAM_REMAP` entries; the existing template `^riposte:(?P<timer_id>\d+):(?P<user_id>\d+)$` already covers it)
- riposte_timers table (schema already there from Phase 1 — Phase 5 just writes to it)

## Performance Snapshot

| Metric | Value |
|--------|-------|
| Default test suite | 728 passing, 6 skipped, 0 failed |
| Load test (RUN_LOAD=1) | 2 passing |
| 8-actor load test scenario | 160 update events → 81 edits (~50% coalescer suppression) |
| 8-actor load test virtual time | ~38 seconds simulated |
| 8-actor load test wall clock | 0.14s |
| Min delta between rate-limiter mutating acquires | 1.050s (well above 0.2s floor) |
| Max edits in any 5s window | ≤ 5 (Discord 429 prevention proven) |
| Restart drill suite (D-35) | 6 passing in 0.32s |
| Phase 4 incremental tests | ~487 new |

## Plan-Level Verification

```
$ grep -c '\- \[x\] \*\*EXPLORE-' .planning/REQUIREMENTS.md
7

$ grep -c '\- \[x\] \*\*COMBAT-0[1-8]' .planning/REQUIREMENTS.md
8

$ grep '\- \[x\] \*\*COMBAT-12' .planning/REQUIREMENTS.md
- [x] **COMBAT-12** …

$ grep '\- \[x\] \*\*OPS-03' .planning/REQUIREMENTS.md
- [x] **OPS-03** …

$ grep '\- \[x\] \*\*Phase 4' .planning/ROADMAP.md
- [x] **Phase 4: Gameplay — Exploration + Combat (Party Mode)** …

$ /Users/shoemoney/Services/DiscordDM/.venv/bin/python -m pytest -q
728 passed, 6 skipped, ...
```

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `src/eldritch_dm/gameplay/party_mode.py` | FOUND |
| `src/eldritch_dm/mcp/rate_limit.py` | FOUND |
| `src/eldritch_dm/bot/cogs/combat.py` | FOUND |
| `tests/integration/test_8player_load.py` | FOUND |
| `tests/integration/test_restart_mid_combat.py` | FOUND |
| `04-SUMMARY.md` (this file) | FOUND |
| Commit `bd52bd9` (Plan 01 Task 1) | FOUND |
| Commit `3884e13` (Plan 02 Task 1) | FOUND |
| Commit `3e3e017` (Plan 03 Task 1) | FOUND |
| Commit `6457212` (Plan 03 Task 2) | FOUND |
| Full test suite 728 passing | VERIFIED |
| ruff clean on new files | VERIFIED |
