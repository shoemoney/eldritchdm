---
phase: 04-gameplay-exploration-combat
plan: "02"
subsystem: combat-ui
tags: [combat, dynamic-items, turn-gatekeeping, attack, dodge, embed, cog]
dependency_graph:
  requires:
    - 04-01  # PartyModeOrchestrator + ChannelRateLimiter + ExplorationCog
  provides:
    - CombatCog with EXPLORATION<->COMBAT lifecycle
    - AttackButton + DodgeButton + CastSpellButton + EndTurnButton (real callbacks)
    - WeaponSelectModal with field validation
    - combat_embed with AC-inline + turn markers
    - turn_gatekeeper pure helpers
    - combat_conditions shim table (D-22)
  affects:
    - bot.py (load CombatCog, cross-cog helpers)
    - party_mode.py (asyncio.gather dispatch, COMBAT cadence=1)
    - setup_hook.py (combat button classes in rehydration map)
tech_stack:
  added: []
  patterns:
    - DynamicItem with attrs-before-super pattern
    - combat_button_prelude shared helper for defer+session+round+is_actor gates
    - _get_enriched_game_state as testable seam on DynamicItem subclasses
    - CombatCog._fetch_game_state as testable seam (patchable in tests)
    - asyncio.gather(return_exceptions=True) for isolated callback dispatch
    - COMBAT cadence acceleration (poll every tick vs every 4 ticks in EXPLORATION)
key_files:
  created:
    - src/eldritch_dm/gameplay/turn_gatekeeper.py
    - src/eldritch_dm/bot/cogs/combat.py
    - src/eldritch_dm/persistence/combat_conditions_repo.py
    - tests/gameplay/test_turn_gatekeeper.py
    - tests/bot/test_embeds_combat_enriched.py
    - tests/bot/test_dynamic_items_combat_real.py
    - tests/bot/test_modals_weapon_select.py
    - tests/bot/cogs/test_combat_cog.py
    - tests/integration/test_combat_flow.py
  modified:
    - src/eldritch_dm/bot/dynamic_items.py (EndTurnButton promoted + 3 new combat buttons)
    - src/eldritch_dm/bot/modals.py (WeaponSelectModal added)
    - src/eldritch_dm/bot/embeds.py (combat_embed v2: AC-inline + turn markers)
    - src/eldritch_dm/bot/bot.py (CombatCog load + cross-cog helpers)
    - src/eldritch_dm/gameplay/party_mode.py (gather dispatch + cadence)
    - src/eldritch_dm/bot/setup_hook.py (combat button rehydration)
    - database/schema.sql (combat_conditions table)
    - tests/bot/fixtures/embed_combat.json (rebaselined for v2 format)
decisions:
  - "D-22 Dodge shim: dm20 has no native dodging condition (04-RESEARCH.md Q2). Used combat_conditions local table + apply_effect(effect=dodging) for ShoeGPT narrative context. Mechanical disadvantage is v1-narrative-only; Phase 5 will wire actual to-hit math."
  - "D-17 Monster turns: dm20 does NOT auto-resolve monster turns on next_turn (RESEARCH.md Q3). CombatCog renders no player buttons when current_actor.player_id is None. Orchestrator's pop/resolve loop handles monster narration automatically."
  - "EndTurnButton BREAKING CHANGE: Phase 2 used actor_id=Discord snowflake (digit-only), Phase 4 uses actor_id=dm20 character UUID (lowercase+dash) + round_n. setup_hook._PARAM_REMAP translates regex group 'round' to __init__ param 'round_n'."
  - "CastSpellButton is rendered-and-stubbed (not hidden): returns ephemeral v2 message. Gated by is_actor for defense-in-depth. Real spell flow deferred to Phase 5."
  - "asyncio.gather(return_exceptions=True) for state_change callbacks: one cog raising cannot block others. ExplorationCog + CombatCog both subscribe to same bus."
  - "Cross-cog handoff via bot helpers: bot.close_exploration_coalescer_for() / bot.close_combat_coalescer_for() avoid cog->cog imports. Delegates to respective cog's on_state_change or coalescer lookup."
metrics:
  duration_minutes: 180
  completed_date: "2026-05-21"
  tasks_completed: 3
  files_created: 9
  files_modified: 8
  tests_added: 176
  tests_total: 726
---

# Phase 4 Plan 02: Combat UI + Turn Gatekeeping Summary

Combat turns end-to-end: AttackButton/DodgeButton/EndTurnButton/CastSpellButton wired with is_actor gating, rate limiter, and WeaponSelectModal; CombatCog manages EXPLORATION<->COMBAT lifecycle via EmbedCoalescer; orchestrator dispatches state_change callbacks concurrently via asyncio.gather.

## Tasks Completed

### Task 1: turn_gatekeeper + combat_embed enrichment (commit 3884e13)

Created `turn_gatekeeper.py` as a pure helper (no Discord/MCP imports):
- `is_actor(user_id, actor)` -- returns True only when user_id matches actor.player_id
- `player_id_for_actor(actor)` -- str or None coercion
- `current_actor_from_game_state(game_state)` -- looks up current_actor_id in combatants list

Extended `combat_embed` to accept 6-tuples `(name, init, hp_cur, hp_max, ac, conditions)` with backward-compat shim for 5-tuples (ac defaults to 10). Turn markers: `▶️` for current actor, `▫️` for others. Field title format: `{marker} {name} ({hp}/{max} HP, AC {ac})`.

Added `combat_conditions` table to `database/schema.sql` for dodge shim (D-22).

Tests: 94 tests (64-combo 8-actor matrix + embed enrichment tests).

### Task 2: AttackButton + DodgeButton + CastSpellButton + EndTurnButton.callback + WeaponSelectModal (commit 5f469c6)

Promoted `EndTurnButton.callback` from Phase 2 stub: real is_actor + stale-round + rate_limiter + next_turn flow. **BREAKING CHANGE** to custom_id format: now `endturn:{channel_id}:{actor_id}:{round}` (3 segments, actor_id is dm20 UUID not Discord snowflake).

Added 3 new DynamicItem subclasses (all with attrs-before-super pattern):
- `AttackButton`: 2-step WeaponSelectModal launch, rate_limiter.acquire on modal submit, `_maybe_surface_riposte` Phase 5 seam (no-op)
- `DodgeButton`: combat_conditions row + apply_effect("dodging") + next_turn, both MCP calls rate-limited
- `CastSpellButton`: v1 stub, still gated by is_actor

Added `WeaponSelectModal` with field validation (`weapon`: alphanumeric+space+`'+`; `target_id`: lowercase+digits+dash). Injection chars (T-04-11) rejected with INVALID_ACTION.

Added `_combat_button_prelude` shared helper: defer+session+stale_round+is_actor gates.

Tests: 38 tests in test_dynamic_items_combat_real.py + 10 tests in test_modals_weapon_select.py.

### Task 3: CombatCog + state-change wiring + integration tests (commit 05c8458)

Created `CombatCog`:
- `on_state_change(EXPLORATION->COMBAT)`: fetch game_state, post combat_embed, build buttons for PC (no buttons for monster turn), register EmbedCoalescer, close ExplorationCog's coalescer
- `on_state_change(COMBAT->EXPLORATION)`: edit message with view=None, close coalescer, clear state (COMBAT-12)
- `on_resolved_combat`: re-fetch game_state, rebuild embed + view for new current actor, coalescer.update

Updated `EldritchBot`:
- Load CombatCog extension after ExplorationCog
- `close_exploration_coalescer_for(channel_id)`: delegates to ExplorationCog.on_state_change(EXPLORATION, COMBAT)
- `close_combat_coalescer_for(channel_id)`: directly pops and closes the combat coalescer

Updated `PartyModeOrchestrator`:
- State_change callbacks dispatch via `asyncio.gather(return_exceptions=True)` -- one cog raising cannot block others
- `_get_poll_cadence(state)`: returns 1 in COMBAT (every tick), 4 in EXPLORATION (every 4 ticks) for fast COMBAT->EXPLORATION detection (COMBAT-12)
- `_last_channel_state` dict tracks cadence per channel

Updated `setup_hook.py`:
- Added AttackButton/DodgeButton/CastSpellButton to class_map
- Added `_PARAM_REMAP` dict translating `round` capture group to `round_n` init param for all combat buttons

Tests: 43 tests in test_combat_cog.py + test_combat_flow.py.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] setup_hook.py EndTurnButton rehydration broke with Phase 4 template**
- **Found during:** Task 3 GREEN run
- **Issue:** Phase 2 EndTurnButton tests used old 2-segment format `endturn:333:444`; Phase 4's new 3-segment template `endturn:channel:actor:round` didn't match. The generic `build_view_for_row` also passed `round=1` to `__init__` but the parameter is `round_n`.
- **Fix:** Updated test fixtures to use Phase 4 format; added `_PARAM_REMAP` dict to setup_hook.py for all combat buttons; added combat buttons to the class_map.
- **Files modified:** `src/eldritch_dm/bot/setup_hook.py`, `tests/bot/test_setup_hook.py`
- **Commit:** 05c8458

**2. [Rule 1 - Bug] test_bootstrap_creates_tables missing combat_conditions table**
- **Found during:** Task 3 full suite run
- **Issue:** `combat_conditions` table was added to schema.sql in Task 1 but bootstrap test's expected set didn't include it.
- **Fix:** Added `combat_conditions` to expected_tables set in test.
- **Files modified:** `tests/persistence/test_bootstrap.py`
- **Commit:** 05c8458

**3. [Rule 1 - Bug] ParsedGameState had no current_hp/max_hp/conditions fields**
- **Found during:** Task 3 RED test writing
- **Issue:** Test incorrectly used `current_hp`, `max_hp`, `conditions` kwargs that don't exist on `ParsedGameState` dataclass.
- **Fix:** Updated test to use actual fields (`campaign_name`, `raw`).
- **Files modified:** `tests/bot/cogs/test_combat_cog.py`
- **Commit:** RED test commit, then fixed inline.

**4. [Rule 1 - Bug] WeaponSelectModal patch path wrong in integration tests**
- **Found during:** Task 3 GREEN run
- **Issue:** Tests patched `eldritch_dm.bot.dynamic_items.WeaponSelectModal` but it's imported inside the callback via `from eldritch_dm.bot.modals import WeaponSelectModal`, so the module-level attribute doesn't exist. Correct patch target is `eldritch_dm.bot.modals.WeaponSelectModal`.
- **Fix:** Updated patch path in two integration tests.
- **Files modified:** `tests/integration/test_combat_flow.py`
- **Commit:** Inline fix in GREEN phase.

## D-22 Dodge Shim Documentation

Per 04-RESEARCH.md Q2: dm20 has NO native "dodging" SRD condition. The dodge implementation:

1. **Local shim**: Insert a row in `combat_conditions` table with `condition_kind="dodging"`, `applied_round=N`, `expires_round=N+1` (expires on dodger's next turn).
2. **Narrative hint**: Call `apply_effect(target=actor_id, effect="dodging")` so ShoeGPT receives "Thorin is dodging" context in narration.
3. **V1 limitation**: The mechanical disadvantage on incoming attacks is **narrative-only**. `combat_action` has no `advantage/disadvantage` parameter in Phase 4. Phase 5 will wire actual to-hit math when dm20 supports it.

The `combat_conditions` table also serves as the seam for Phase 5 to implement condition expiry, condition stacking, and mechanically-enforced effects.

## D-17 Monster Turn Documentation

Per 04-RESEARCH.md Q3: dm20 does NOT auto-resolve monster turns on `next_turn`. The orchestrator's pop/resolve loop handles the narrative (ShoeGPT decides the monster's action), but player UI is suppressed:

- `CombatCog._build_combat_view` returns `None` when `current_actor.player_id is None`
- `channel.send(view=None)` or `view={}` with 0 children is used for monster turns
- Orchestrator's existing pop/resolve loop naturally handles monster narration
- No explicit `combat_action(action="monster_default")` call is needed in Phase 4

## Phase 5 Riposte Seam

The Riposte seam for Phase 5 is at:

**File:** `src/eldritch_dm/bot/dynamic_items.py`
**Method:** `AttackButton._maybe_surface_riposte(interaction, mech_result, target_id)`
**Trigger:** `mech_result["outcome"] == "miss" AND target["has_reaction"] is True`
**Action:** Phase 5 RiposteCog will call `await riposte_cog.surface_riposte_button(interaction, target_id, timer_id)` here.

Current implementation is a documented no-op (intentional for Phase 4). The method is called after every `combat_action(action="attack")` returns, so Phase 5 just needs to implement the method body.

## Plan-Level Verification

| Check | Result |
|-------|--------|
| `grep "phase2_stub_callback_invoked"` returns ONLY RiposteButton | PASS (line 1207, class RiposteButton) |
| `grep -c "is_actor" dynamic_items.py` >= 4 | PASS (12 matches) |
| `grep "rate_limiter.acquire" dynamic_items.py` actual calls >= 4 | PASS (4 actual awaits: lines 633, 801, 991, 1008) |
| `uv run ruff check src/ tests/` | PASS (clean) |
| `uv run lint-imports` | PASS (7 contracts, 0 broken) |
| `is_actor` pure helper has no Discord/MCP imports | PASS (verified via lint-imports) |
| Total tests: 726 | PASS (462 bot+gameplay+integration pass, 0 fail) |

## Next-Phase Readiness Signal

Plan 03 (load test + restart drill) may now run against the fully wired orchestrator + combat cog + rate limiter. The 8-actor combat scenario is tested and working. CombatCog and ExplorationCog coexist on the same orchestrator bus with isolated callback errors. RehydrateAndRestart from persistent_views now correctly handles all 7 DynamicItem classes including the Phase 4 combat buttons.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `src/eldritch_dm/bot/cogs/combat.py` | FOUND |
| `src/eldritch_dm/gameplay/turn_gatekeeper.py` | FOUND |
| `src/eldritch_dm/persistence/combat_conditions_repo.py` | FOUND |
| `04-02-SUMMARY.md` | FOUND |
| Commit `3884e13` (Task 1) | FOUND |
| Commit `5f469c6` (Task 2) | FOUND |
| Commit `05c8458` (Task 3) | FOUND |
| 462+ tests pass, 0 fail | VERIFIED |
| ruff clean | VERIFIED |
| lint-imports clean | VERIFIED |
