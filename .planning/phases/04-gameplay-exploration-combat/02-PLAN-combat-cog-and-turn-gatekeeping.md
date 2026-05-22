---
phase: 04-gameplay-exploration-combat
plan: 02
type: execute
wave: 2
depends_on:
  - 04-01
files_modified:
  - src/eldritch_dm/gameplay/turn_gatekeeper.py
  - src/eldritch_dm/gameplay/party_mode.py
  - src/eldritch_dm/bot/cogs/combat.py
  - src/eldritch_dm/bot/dynamic_items.py
  - src/eldritch_dm/bot/modals.py
  - src/eldritch_dm/bot/embeds.py
  - src/eldritch_dm/bot/bot.py
  - tests/gameplay/test_turn_gatekeeper.py
  - tests/bot/cogs/test_combat_cog.py
  - tests/bot/test_dynamic_items_combat_real.py
  - tests/integration/test_combat_flow.py
autonomous: true
requirements:
  - COMBAT-01
  - COMBAT-02
  - COMBAT-03
  - COMBAT-04
  - COMBAT-05
  - COMBAT-06
  - COMBAT-07
  - COMBAT-12
tags: [gameplay, combat, turn-gatekeeping, dynamic-items, attack, dodge]

must_haves:
  truths:
    - "When dm20 transitions to COMBAT, the orchestrator (Plan 01) fires on_state_change(EXPLORATION→COMBAT) and the CombatCog posts a fresh combat_embed message in the channel"
    - "The combat_embed renders all 8+ initiative rows with current-actor turn marker (▶️), HP/AC, and conditions"
    - "Action buttons (Attack, Dodge, EndTurn, CastSpell stub) render with the current actor's dm20 character_id encoded in custom_id along with channel_id and round_number"
    - "Turn gatekeeper rejects clicks where interaction.user.id != current_actor.player_id with ephemeral NOT_YOUR_TURN warning"
    - "Attack flow: button → defer → WeaponSelectModal → dm20.combat_action(action='attack', weapon=..., target=...) → narrative resolves via the orchestrator's pop/resolve loop"
    - "Dodge flow: button → defer → dm20.apply_effect (D-22 shim if needed) → dm20.next_turn"
    - "End Turn flow: button → defer → dm20.next_turn"
    - "Cast Spell button is a v1 stub returning an ephemeral 'coming in v2' message"
    - "Combat-end watcher (transition back to EXPLORATION) is wired and tested"
  artifacts:
    - path: "src/eldritch_dm/gameplay/turn_gatekeeper.py"
      provides: "Pure helper: is_actor(interaction_user_id, current_actor) -> bool + player_id_for_actor(actor) -> str | None"
      contains: "def is_actor"
    - path: "src/eldritch_dm/bot/cogs/combat.py"
      provides: "CombatCog: combat_embed lifecycle, on_state_change handlers, refresh on dm20 state changes"
      contains: "class CombatCog"
    - path: "src/eldritch_dm/bot/dynamic_items.py"
      provides: "AttackButton + DodgeButton + CastSpellButton + promoted EndTurnButton.callback"
      contains: "class AttackButton"
    - path: "src/eldritch_dm/bot/modals.py"
      provides: "WeaponSelectModal (single-component packed format, ≤5 components)"
      contains: "class WeaponSelectModal"
  key_links:
    - from: "src/eldritch_dm/bot/dynamic_items.py"
      to: "src/eldritch_dm/gameplay/turn_gatekeeper.py"
      via: "AttackButton/DodgeButton/EndTurnButton callbacks call is_actor() before dispatching"
      pattern: "is_actor|turn_gatekeeper"
    - from: "src/eldritch_dm/bot/cogs/combat.py"
      to: "src/eldritch_dm/gameplay/party_mode.py"
      via: "PartyModeOrchestrator.on_state_change(EXPLORATION→COMBAT) callback registered in cog_load"
      pattern: "register_state_change_callback|on_state_change"
    - from: "src/eldritch_dm/bot/dynamic_items.py (AttackButton)"
      to: "src/eldritch_dm/mcp/tools.py (combat_action)"
      via: "Through ChannelRateLimiter.acquire — D-29 mutating gate"
      pattern: "combat_action.*action=\"attack\""
    - from: "src/eldritch_dm/bot/cogs/combat.py"
      to: "src/eldritch_dm/bot/coalescer.py"
      via: "Per-message EmbedCoalescer keyed on the combat message id; shares ChannelEditBudget with ExplorationCog"
      pattern: "EmbedCoalescer|channel_edit_budget"
---

<objective>
Layer combat-state UI and turn-gatekept action buttons on top of the orchestrator + rate limiter delivered by Plan 01. Promote `EndTurnButton.callback`, add `AttackButton` / `DodgeButton` / `CastSpellButton` to the DynamicItem set, ship `WeaponSelectModal`, and implement the COMBAT↔EXPLORATION state-transition handlers in the new `CombatCog`.

Purpose: This is the "combat works end-to-end with multiple players, gated by Discord user_id" deliverable. Plan 03 then load-tests it.

Output:
- `src/eldritch_dm/gameplay/turn_gatekeeper.py` (pure helper)
- `src/eldritch_dm/bot/cogs/combat.py` (CombatCog)
- `src/eldritch_dm/bot/dynamic_items.py` extended with AttackButton, DodgeButton, CastSpellButton; EndTurnButton callback promoted
- `src/eldritch_dm/bot/modals.py` extended with WeaponSelectModal
- `src/eldritch_dm/bot/embeds.py` — enhanced `combat_embed` (turn marker per D-13/D-14, AC included, 8+ rows verified)
- `EldritchBot` wires the cog + the COMBAT state-change handler bus
- ~25-30 new tests including the 8-actor turn-gatekeeper matrix and an end-to-end combat-flow integration test
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@.planning/phases/04-gameplay-exploration-combat/04-CONTEXT.md
@.planning/phases/04-gameplay-exploration-combat/04-01-SUMMARY.md
@src/eldritch_dm/gameplay/party_mode.py
@src/eldritch_dm/gameplay/exploration_batch.py
@src/eldritch_dm/mcp/rate_limit.py
@src/eldritch_dm/bot/dynamic_items.py
@src/eldritch_dm/bot/coalescer.py
@src/eldritch_dm/bot/embeds.py
@src/eldritch_dm/bot/modals.py
@src/eldritch_dm/bot/warnings.py
@src/eldritch_dm/mcp/tools.py

**Open question (resolve at task start via 04-RESEARCH.md if committed; else use CONTEXT default):**
- **D-22 (Dodge shim):** Does dm20 expose a native "dodging" condition via `apply_effect(target, effect="dodging")`, or do we need the custom-effect shim (D-22)? The author MUST verify with a 30-minute spike:
  1. Run a real dm20 instance, start combat, call `apply_effect(target=<id>, effect="dodging")` and inspect `get_game_state` for a condition entry.
  2. If a "dodging" condition appears with auto-clear on next turn → use plain `apply_effect(effect="dodging")`. Document in summary.
  3. If not → use shim: `apply_effect(effect_name="custom:dodging", custom_data={...})` AND insert a row into `riposte_timers` repurposed as a generic combat-condition tracker (`status` column = "dodging-active"). Document the shim in summary; flag for Phase 5 to refactor `riposte_timers` → `combat_conditions` if it becomes confusing.
- **D-17 (Monster turns):** Whether dm20 auto-resolves monster actions on `next_turn` or requires explicit `combat_action(action="monster_default")` per monster — verify in the same spike. The orchestrator's combat-mode behavior depends on this: if auto, the orchestrator does nothing special on monster turns and just waits for the narrative; if manual, the orchestrator must issue the monster_default call.

If 04-RESEARCH.md addresses these, use its findings. If not, the executor performs the spike and writes the result into `04-02-SUMMARY.md`.

<interfaces>
<!-- Contracts the executor must reuse from Plan 01. -->

From src/eldritch_dm/gameplay/party_mode.py (Plan 01):
```python
class PartyModeOrchestrator:
    def register_resolution_callback(self, fn: Callable[[str, dict], Awaitable[None]]) -> None
    def register_state_change_callback(self, fn: Callable[[str, ChannelState, ChannelState], Awaitable[None]]) -> None
    async def start_orchestrator_for_channel(self, channel_id, campaign_name, session_id) -> asyncio.Task
    async def stop_orchestrator_for_channel(self, channel_id) -> None
```

From src/eldritch_dm/mcp/rate_limit.py (Plan 01):
```python
class ChannelRateLimiter:
    async def acquire(self, channel_id: str) -> None
```

From src/eldritch_dm/mcp/tools.py (already exists):
```python
async def combat_action(client: MCPClient, *, campaign_name: str, action: str, **extra) -> dict
async def apply_effect(client: MCPClient, *, campaign_name: str, target: str, effect: str, **extra) -> dict
async def next_turn(client: MCPClient, *, campaign_name: str) -> dict
async def get_game_state(client: MCPClient, *, campaign_name: str) -> dict
async def get_character(client: MCPClient, *, character_id_or_name: str) -> dict   # confirm signature in tools.py
```

From src/eldritch_dm/bot/coalescer.py (Plan 01 updates):
```python
class ChannelEditBudget: ...
class EmbedCoalescer:
    def __init__(self, message, *, rate_limit_seconds, channel_budget=None) ...
    async def update(self, embed, *, view=None) -> None
    async def close(self) -> None
```

From src/eldritch_dm/bot/embeds.py:
```python
def combat_embed(*, round_n: int, current_actor: str,
                 initiative: Sequence[tuple[str, int, int, int, list[str]]]) -> discord.Embed
# Phase 4 EXTENDS this — see Task 1 to add AC + the ▶️ / ▫️ turn markers (D-13/D-14)
```

From src/eldritch_dm/bot/warnings.py:
```python
WarningKind.NOT_YOUR_TURN     # "❌ It is not your turn, **{actor_name}**. Sit tight!"
WarningKind.INVALID_ACTION    # "❌ Invalid action: {reason}"
WarningKind.DM_OFFLINE
```

From src/eldritch_dm/persistence/models.py:
```python
class ChannelState(StrEnum):
    LOBBY = "LOBBY"
    EXPLORATION = "EXPLORATION"
    COMBAT = "COMBAT"
    PAUSED = "PAUSED"
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: turn_gatekeeper + combat_embed enrichment + 8-actor gatekeeper matrix</name>
  <files>
    src/eldritch_dm/gameplay/turn_gatekeeper.py,
    src/eldritch_dm/bot/embeds.py,
    tests/gameplay/test_turn_gatekeeper.py,
    tests/bot/test_embeds_combat_enriched.py
  </files>
  <behavior>
    `turn_gatekeeper.py` (pure helper module — no I/O, no async, no Discord imports):
      - Test 1: `is_actor(interaction_user_id: str, actor: dict) -> bool` returns True when `str(interaction_user_id) == str(actor.get("player_id"))`; False otherwise.
      - Test 2: `is_actor` returns False when `actor.get("player_id")` is None (monster turn).
      - Test 3: `player_id_for_actor(actor: dict) -> str | None` returns `str(actor["player_id"])` or None.
      - Test 4: `current_actor_from_game_state(game_state: dict) -> dict | None` looks up the actor matching `game_state["current_actor_id"]` from `game_state["combatants"]`; returns None if absent or empty. Use the shape dm20's `get_game_state` actually returns (verify via RESEARCH or live spike during Task 0 of this plan).
      - Test 5: **8-actor gatekeeper matrix.** Synthetic `game_state` with 8 combatants (4 PCs each with distinct player_id, 4 monsters with player_id=None). For each (current_actor, clicker_user_id) pair (64 combos), assert `is_actor(clicker_user_id, current_actor) == (clicker_user_id == current_actor.player_id)`.

    `combat_embed` enrichment in `src/eldritch_dm/bot/embeds.py` (D-11/D-13/D-14):
      - Test 6: Signature accepts AC as a 5-tuple field — extend to `(name, initiative_roll, hp_cur, hp_max, ac, conditions)` per D-13's "field title format: `{turn_marker}{actor_name} ({hp}/{max_hp} HP, AC {ac})`".
      - Test 7: Turn marker uses ▶️ for `current_actor`, ▫️ for others (D-14). Field title format: `f"{marker} {actor_name} ({hp}/{max_hp} HP, AC {ac})"`.
      - Test 8: 8-row case renders cleanly (8 fields ≤ 25 limit; verified by counting `embed.fields`).
      - Test 9: Empty conditions list shows "—" (existing behavior).
      - Test 10: Backward-compat: existing 5-tuple call sites get a deprecation note in docstring but do not crash; supply a thin shim that defaults `ac=10` if the caller passes the old 5-tuple shape. Document this in the SUMMARY.

    Test infrastructure:
      - Add `tests/bot/test_embeds_combat_enriched.py` for the embed changes.
      - Add `tests/gameplay/test_turn_gatekeeper.py` for the helper.
  </behavior>
  <action>
    Create `src/eldritch_dm/gameplay/turn_gatekeeper.py`. It MUST NOT import anything from `discord`, `eldritch_dm.bot`, or `eldritch_dm.mcp`. Pure dict-shape helpers. The shape contract is: `actor` dict has keys `id`, `name`, `player_id` (string or None), `hp_current`, `hp_max`, `ac`, `conditions`. Document the exact shape at the top of the file with a `# Shape: {…}` comment block AND verify it against `ddmcpskills.md` § dm20 § Game state.

    Extend `combat_embed` in `src/eldritch_dm/bot/embeds.py`. Two approaches; pick the one that minimizes blast radius:
      (a) Add a new parameter `initiative` accepts EITHER 5-tuples (legacy) OR 6-tuples (new) and normalize at the top of the function;
      (b) Keep `combat_embed` as-is and add a NEW `combat_embed_v2` that the CombatCog uses; deprecate v1.
    Lean (a) for v1 — fewer call-site updates, snapshot tests can be re-baselined.

    Implement the 8-actor matrix test using parametrize: `@pytest.mark.parametrize("current_actor_idx,clicker_idx", ...)` generates 64 combos; assertions are derived from the actor dict.

    Re-run any existing snapshot tests in `tests/bot/test_embeds.py`; update snapshots once per the new turn-marker rules. Stage snapshot updates in the SAME commit as the embed change.
  </action>
  <verify>
    <automated>uv run pytest tests/gameplay/test_turn_gatekeeper.py tests/bot/test_embeds_combat_enriched.py tests/bot/test_embeds.py -x -v && uv run lint-imports</automated>
  </verify>
  <done>
    `is_actor` and `current_actor_from_game_state` work against the realistic game_state shape; 8-actor matrix passes 64 combos; `combat_embed` renders ▶️/▫️ markers + AC inline; snapshot tests pass; lint-imports unchanged.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: AttackButton + DodgeButton + CastSpellButton + EndTurnButton.callback + WeaponSelectModal</name>
  <files>
    src/eldritch_dm/bot/dynamic_items.py,
    src/eldritch_dm/bot/modals.py,
    tests/bot/test_dynamic_items_combat_real.py,
    tests/bot/test_modals_weapon_select.py
  </files>
  <behavior>
    New DynamicItem subclasses per D-15 — all with `template = re.compile(r"^...$")` regex class attributes:

    **`AttackButton`** — `attack:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)`:
      - Test 1: custom_id round-trip — instance.custom_id parses back via from_custom_id.
      - Test 2: actor_id pattern accepts UUID-style (8-4-4-4-12 hex) and bare lowercase alphanumeric (dm20 sometimes returns short IDs); does NOT accept uppercase or special chars.
      - Test 3: callback path — clicker IS current actor → calls `combat_action(action="attack", ...)` after WeaponSelectModal submission via the 2-step modal launch pattern; mutating MCP call goes through `ChannelRateLimiter`.
      - Test 4: callback path — clicker IS NOT current actor → `send_warning(WarningKind.NOT_YOUR_TURN, actor_name=current_actor["name"])` and NO MCP call.
      - Test 5: When `current_actor.player_id is None` (monster turn), ALL player clicks are rejected with NOT_YOUR_TURN.
      - Test 6: Stale-round detection — if `match["round"] != current_game_state["round_number"]`, send `INVALID_ACTION(reason="This is an old turn.")` (defense-in-depth against zombie clicks after round advanced).

    **`DodgeButton`** — `dodge:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)`:
      - Test 7: custom_id round-trip.
      - Test 8: Active-actor path → `apply_effect(target=actor_id, effect="dodging")` (or shim per D-22 after RESEARCH spike) → `next_turn(...)`. Both calls gated by ChannelRateLimiter.
      - Test 9: Non-active-actor path → NOT_YOUR_TURN.
      - Test 10: If RESEARCH determines the shim path is needed, the dodge button writes a row in `riposte_timers` with `status='dodging-active'` and `deadline_ts = now + 6s` (1 round). Tested with mocked repo.
      - Test 11: Shim-or-native is documented in the SUMMARY; the test file has two parametrized cases gated on `pytest.fixture(params=["native", "shim"])` — only the chosen case runs after the spike.

    **`EndTurnButton.callback`** (promote from Phase 2 stub in dynamic_items.py):
      - Test 12: Active-actor path → `next_turn(...)` via ChannelRateLimiter.
      - Test 13: Non-active-actor path → NOT_YOUR_TURN.
      - Test 14: After Plan 01 changes, the stub log line is gone (assert `"phase2_stub_callback_invoked"` is NOT in the dispatched logs for EndTurnButton).
      - **NOTE:** The Phase 2 EndTurnButton template was `endturn:(?P<channel_id>\d+):(?P<actor_id>\d+)$` — actor_id is a DIGIT (Discord user ID). For Phase 4 this needs to be the dm20 character UUID. Change the template to `endturn:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)` to match the other combat buttons. Document in the SUMMARY that the Phase 2 stub used user_id; the Phase 4 production form uses character_id. This is a BREAKING change to the regex, but Phase 2 only ever emitted stubs so no live custom_ids exist that match the old pattern.

    **`CastSpellButton`** — `cast:(?P<channel_id>\d+):(?P<actor_id>[a-z0-9-]+):(?P<round>\d+)`:
      - Test 15: Stub v1 — returns ephemeral "⚗️ Spellcasting arrives in v2. For now, use Attack with weapon='spell'." Per D-15 + Claude's Discretion section.
      - Test 16: Stub still goes through `is_actor` gatekeeper (defense-in-depth — non-active players don't even see the v2 message).

    **`WeaponSelectModal`** in `src/eldritch_dm/bot/modals.py` (single-step packed format, ≤5-component cap):
      - Test 17: 2 components: TextInput "weapon" (paragraph, max 80 chars) + TextInput "target_id" (short, max 80 chars). Stays well under the 5-cap.
      - Test 18: `on_submit_cb` callback injection (mirrors Phase 3's modal pattern); receives `{"weapon": str, "target_id": str}` parsed dict.
      - Test 19: Sanitization — the `weapon` and `target_id` fields are NOT free-form prose but are still passed through a light validator: weapon name limited to alphanumeric + space + `'`; target_id limited to lowercase + digits + `-`. Reject with INVALID_ACTION otherwise.
  </behavior>
  <action>
    Add three new DynamicItem subclasses (`AttackButton`, `DodgeButton`, `CastSpellButton`) to `src/eldritch_dm/bot/dynamic_items.py` following the established pattern (template + from_custom_id + callback). Update `DYNAMIC_ITEM_CLASSES` registration tuple to include the three new classes.

    Promote `EndTurnButton.callback` from the Phase 2 stub. Replace the stub body with:
      1. `await interaction.response.defer(thinking=True, ephemeral=True)` (EDM001).
      2. Bind structlog: `channel_id`, `actor_id`, `round`, `user_id`, `action_kind="end_turn"`.
      3. Fetch `game_state = await get_game_state(mcp, campaign_name=session.campaign_name)`.
      4. Identify current actor; if `match["round"] != game_state["round_number"]` → INVALID_ACTION.
      5. If `not is_actor(str(interaction.user.id), current_actor)` → NOT_YOUR_TURN via send_warning.
      6. `await rate_limiter.acquire(channel_id)`; `await next_turn(mcp, campaign_name=session.campaign_name)`.
      7. Ephemeral followup: "⏭ Turn ended."

    `AttackButton.callback`:
      1. Defer (EDM001).
      2. Bind structlog + load session + game_state + current_actor + round guard + is_actor guard (same prelude as EndTurn).
      3. Open WeaponSelectModal via `_ModalLaunchView` 2-step pattern (Phase 3 precedent in `cogs/ingest.py`). Inject an `on_submit_cb` that runs the rest of the flow.
      4. `on_submit_cb({"weapon": w, "target_id": t})`:
         - `await rate_limiter.acquire(channel_id)`.
         - `mech_result = await combat_action(mcp, campaign_name=..., action="attack", weapon=w, target=t)`.
         - Build the narrative-prefetch payload per D-20 — enqueue a `party_action(session_id, action="attack_resolved", context=f"<...>{mech_result}</...>")` so the orchestrator's pop/resolve loop picks it up and narrates.
         - Ephemeral confirm: "⚔️ Attack resolved. Awaiting narration..."
         - Combat embed auto-refreshes via CombatCog.on_resolved callback (Task 3).

    `DodgeButton.callback`:
      1. Same prelude.
      2. Per D-22: if RESEARCH says dm20 has native dodging, `apply_effect(effect="dodging", target=actor_id)`; else shim per CONTEXT D-22 (custom_data + riposte_timers row). Author MUST verify before implementing; if blocked, default to shim path and flag in SUMMARY.
      3. `next_turn(...)`.
      4. Both calls through rate_limiter.
      5. Ephemeral: "🛡 Dodge stance. Turn ended."

    `CastSpellButton.callback`:
      1. Defer + is_actor + round guard.
      2. Send `INVALID_ACTION(reason="Spellcasting arrives in v2. Use Attack with weapon='spell' for now.")`.

    `WeaponSelectModal` follows Phase 3's `_CapEnforcedModal` precedent — two TextInput fields, callback injection at construction. Light field validation (regex). Re-use Phase 3's modal scaffolding from `bot/modals.py`.

    All new MCP calls in this task MUST be wrapped by `await bot.rate_limiter.acquire(str(channel_id))` (mutating per D-29). Reads of `get_game_state` are NOT gated.

    Update structlog binding everywhere per D-36: `channel_id`, `session_id`, `actor_id`, `actor_name`, `action_kind`, `round_number`, `turn_idx`, `user_id`.
  </action>
  <verify>
    <automated>uv run pytest tests/bot/test_dynamic_items_combat_real.py tests/bot/test_modals_weapon_select.py -x -v && uv run ruff check src/eldritch_dm/bot/dynamic_items.py src/eldritch_dm/bot/modals.py</automated>
  </verify>
  <done>
    All four combat buttons (Attack, Dodge, EndTurn, CastSpell stub) are real callbacks that gate on `is_actor`, defer first, route mutating calls through ChannelRateLimiter, and emit the right structlog bindings. WeaponSelectModal validates inputs and dispatches via callback injection. 8+ actor matrix tests pass for every button.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: CombatCog + COMBAT↔EXPLORATION state-change wiring + end-to-end combat flow integration test</name>
  <files>
    src/eldritch_dm/bot/cogs/combat.py,
    src/eldritch_dm/bot/bot.py,
    src/eldritch_dm/gameplay/party_mode.py,
    tests/bot/cogs/test_combat_cog.py,
    tests/integration/test_combat_flow.py
  </files>
  <behavior>
    `CombatCog` (src/eldritch_dm/bot/cogs/combat.py):
      - Test 1: Cog loads via `await bot.load_extension("eldritch_dm.bot.cogs.combat")`.
      - Test 2: `cog_load` registers `self.on_state_change` with `bot.orchestrator.register_state_change_callback(...)` AND `self.on_resolved_combat` with `register_resolution_callback(...)`.
      - Test 3: On `on_state_change(channel_id, OLD=EXPLORATION, NEW=COMBAT)`: the cog (a) closes any open ExplorationCog coalescer for that channel via a bot-level hook, (b) posts a fresh combat_embed message in the Discord channel with all current-round buttons attached, (c) creates an EmbedCoalescer for that message sharing the per-channel ChannelEditBudget, (d) persists `persistent_views` rows for each action button (audit only — dispatch is via `add_dynamic_items`).
      - Test 4: On `on_state_change(channel_id, OLD=COMBAT, NEW=EXPLORATION)` (combat ended, COMBAT-12): closes the combat coalescer, removes the combat message's buttons (edits message with `view=None`), and pings ExplorationCog to re-render a room_embed. Persistent_views rows for that channel's combat buttons are deleted from DB.
      - Test 5: `on_resolved_combat(channel_id, action_payload)` while in COMBAT state: re-fetches `get_game_state`, re-renders combat_embed with the new initiative/HP/conditions/round/current_actor, and calls `coalescer.update(embed, view=new_buttons_view)`. The `view` is rebuilt every refresh because the current actor (and therefore which buttons are visible/styled) changes per turn.
      - Test 6: 8-row combat: synthetic game_state with 8 combatants → embed renders 8 fields; buttons are rendered for the current actor's character_id; round_number is encoded in custom_ids.
      - Test 7: Monster turn auto-handling (per D-17 + RESEARCH spike): when `current_actor.player_id is None`, no Discord buttons are rendered (only the embed updates); orchestrator handles auto-resolution (Plan 01's orchestrator already drives the pop/resolve loop; CombatCog just doesn't render player UI for monsters). Verify the rendered View has zero items for monster turns.

    `EldritchBot` wiring updates:
      - Test 8: `setup_hook` calls `await self.load_extension("eldritch_dm.bot.cogs.combat")` AFTER exploration cog load.
      - Test 9: New helper `bot.close_exploration_coalescer_for(channel_id)` / `bot.close_combat_coalescer_for(channel_id)` exist and are awaitable; allows cross-cog handoff without circular imports.
      - Test 10: `on_session_state_change` bus (added in Plan 01) is invoked when LobbyCog sets EXPLORATION; the orchestrator's `on_state_change` callbacks fire — exploration cog renders its room; combat cog is dormant. Verified via end-to-end mocked integration.

    `PartyModeOrchestrator` adjustments (Plan 01 already exposes the callback APIs):
      - Test 11: When the orchestrator's combat-state watcher detects EXPLORATION→COMBAT, all registered `on_state_change` callbacks fire IN ORDER and concurrently-safe (use `asyncio.gather(..., return_exceptions=True)`). One callback raising must not prevent others from running. Log exceptions.
      - Test 12: Once in COMBAT, the orchestrator's poll cadence on `get_game_state` accelerates to every iteration (so a single 250ms cycle catches the COMBAT→EXPLORATION transition fast). Implement this by changing the `combat_check_every_n_polls` from 4 (exploration default) to 1 when state is COMBAT.

    End-to-end integration test (tests/integration/test_combat_flow.py):
      - Test 13: Full mocked flow — start session in EXPLORATION → orchestrator polls → mock dm20 transitions to COMBAT on the 3rd poll → CombatCog posts combat embed → simulate AttackButton click (Interaction-mock pattern matching Phase 3 conventions) → modal submit → combat_action called with sanitized args → orchestrator pops the narration request → resolves → coalescer.update called → state advances → next_turn → second actor's AttackButton works → repeat for 3 rounds → mock dm20 transitions back to EXPLORATION → ExplorationCog re-renders room_embed.
      - Test 14: Same scenario but the 4th actor's DodgeButton is exercised at least once (verifies the dodge shim/native path end-to-end).
      - Test 15: A non-active player clicking AttackButton during round 2 receives NOT_YOUR_TURN; their click is NOT counted against the rate limiter (assertion on rate_limiter.acquire mock call count).
  </behavior>
  <action>
    Implement `CombatCog`. Pattern mirrors ExplorationCog (Plan 01):
      - State: `self._combat_messages: dict[str, discord.Message]` and `self._coalescers: dict[str, EmbedCoalescer]` keyed by channel_id.
      - `async def on_state_change(channel_id, old, new)`: dispatches to `_enter_combat` / `_exit_combat` depending on transition.
      - `async def _enter_combat(channel_id)`:
          1. `game_state = await get_game_state(mcp, campaign_name=session.campaign_name)`.
          2. Build the combat_embed via `combat_embed(...)`.
          3. Build a `discord.ui.View(timeout=None)` with `AttackButton(channel_id, actor_id, round)`, `DodgeButton(...)`, `EndTurnButton(...)`, `CastSpellButton(...)` for the CURRENT actor (skip if monster).
          4. `msg = await channel.send(embed=embed, view=view)`.
          5. Persist `persistent_views` rows for each button (audit; dispatch via `add_dynamic_items`).
          6. Install EmbedCoalescer with shared ChannelEditBudget.
          7. Ping bot to close ExplorationCog's coalescer for this channel.
      - `async def _exit_combat(channel_id)`:
          1. `await msg.edit(view=None)` (remove buttons).
          2. `await coalescer.close()`.
          3. Delete `persistent_views` rows for combat buttons in this channel.
          4. Trigger ExplorationCog to re-render a room_embed (re-use the orchestrator's `on_state_change(COMBAT→EXPLORATION)` callback to also fire ExplorationCog's renderer; both cogs subscribe to the same bus).
      - `async def on_resolved_combat(channel_id, action_payload)`:
          1. Re-fetch `get_game_state` (read-only — no rate limiter).
          2. Re-render embed; rebuild View for new current actor.
          3. `await coalescer.update(embed, view=view)`.

    Wire `EldritchBot.setup_hook`:
      - Add `await self.load_extension("eldritch_dm.bot.cogs.combat")` after the exploration extension.
      - Expose `bot.close_exploration_coalescer_for(channel_id)` and `bot.close_combat_coalescer_for(channel_id)` as small async passthroughs to the respective cog instances (looked up via `self.get_cog("ExplorationCog")` / `"CombatCog"`). This avoids cog→cog imports (preserves import-linter `bot may import everything` while keeping the cog modules independent).

    Update orchestrator (Plan 01's file) — add the COMBAT cadence acceleration:
      ```
      cadence = 1 if last_known_state == ChannelState.COMBAT else self.combat_check_every_n_polls
      ```
      And ensure on_state_change callbacks dispatch via `asyncio.gather(..., return_exceptions=True)`.

    Integration test setup pattern: use the `tests/integration/test_phase3_smoke.py` Phase 3 author wrote as a precedent — patch MCPClient.call to return scripted responses for a sequence of polls. Use `pytest.fixture` to assemble a "mocked dm20 timeline" object that returns different shapes on consecutive calls.

    Reaction-shim documentation seam (per `important_notes` in this plan's spawn context): document in `04-02-SUMMARY.md` where Phase 5's RiposteButton hook will plug in. The seam is: after `combat_action(action="attack")` returns with `outcome="miss"` AND the target has `has_reaction=True`, Phase 5's RiposteCog will surface a timed button. Phase 4 does not implement reactions but the DodgeButton's pattern (apply_effect → next_turn) is the template Phase 5 will follow.
  </action>
  <verify>
    <automated>uv run pytest tests/bot/cogs/test_combat_cog.py tests/integration/test_combat_flow.py -x -v && uv run ruff check src/ tests/ && uv run lint-imports</automated>
  </verify>
  <done>
    CombatCog renders combat_embed on EXPLORATION→COMBAT transition, refreshes on every dm20 state change via the orchestrator's resolution callback, closes cleanly on COMBAT→EXPLORATION (COMBAT-12 satisfied). End-to-end integration test exercises Attack + Dodge + EndTurn across 3 rounds with 4 PCs + 4 monsters; turn gatekeeper rejects all wrong-clicker attempts; rate limiter is invoked only on accepted clicks. 25+ new tests pass; ruff + lint-imports clean.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Player click → combat action button | The custom_id encodes channel_id, actor_id, round; ALL three must be cross-checked against current game_state before any mutating MCP call. |
| WeaponSelectModal → combat_action | Modal text is untrusted; field-level regex validation before serializing into MCP args. |
| Orchestrator state-change callback → CombatCog | Server-internal; trusted. But: callbacks dispatch via asyncio.gather(return_exceptions=True) so one cog raising can't break the bus. |
| persistent_views combat rows → setup_hook rehydration | Rows are written only by our code; on boot, rehydration re-registers buttons that survived a restart-mid-combat. Phase 4 BOT-08 extension (Plan 03) verifies. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-09 | Spoofing | A player clicks another player's AttackButton | mitigate | `is_actor(interaction.user.id, current_actor)` gate in every combat button's callback. NOT_YOUR_TURN warning sent ephemerally; no MCP call issued. (D-16, COMBAT-04). |
| T-04-10 | Tampering | Stale custom_id from a previous round | mitigate | `match["round"]` is checked against `game_state["round_number"]`; mismatch → INVALID_ACTION. (D-15 round encoding is for cache-busting AND defense-in-depth.) |
| T-04-11 | Tampering | WeaponSelectModal field with `<tool_call>` injection | mitigate | Field regex (`weapon`: alphanumeric+space+`'`; `target_id`: lowercase+digits+`-`) rejects injection chars; sanitizer is NOT used because these are structured fields, not free prose. |
| T-04-12 | Repudiation | "The bot dropped my attack" | mitigate | structlog binds `channel_id, session_id, actor_id, action_kind, round_number, turn_idx, user_id` on every combat dispatch (D-36); rate-limit acquire is also logged. |
| T-04-13 | DoS | Player spam-clicks AttackButton | mitigate | Discord defer ensures the bot acks ≤3s; ChannelRateLimiter (Plan 01) caps mutating MCP calls to 1 per 200ms per channel. NOT_YOUR_TURN rejections bypass the rate limiter entirely. |
| T-04-14 | Elevation of Privilege | Player edits custom_id via inspector | accept | Discord verifies custom_id signature on every interaction; client-side modification is not possible without resigning. (Discord's gateway dispatch validates the click source.) The is_actor check is the defense in case Discord's check ever fails. |
| T-04-15 | Information Disclosure | combat_embed exposes monster HP | accept | Showing all combatant HP is intentional D&D 5e convention for our use case. Phase 4 does NOT implement "hidden HP" or "monster stat block redaction"; Phase 5+ may. |
| T-04-16 | DoS | Dodge shim writes runaway rows to riposte_timers | mitigate | DodgeButton inserts AT MOST one row per dodge action; deadline_ts cleanup runs on restart (Phase 5 will own this); Plan 03's restart drill verifies. |
| T-04-SC | Tampering | Supply-chain (no new packages this plan) | accept | Plan 02 introduces NO new third-party packages; only adds new modules and DynamicItem subclasses. No package-legitimacy gate needed. |
</threat_model>

<verification>
**Plan-level checks:**

1. `uv run pytest tests/gameplay tests/bot tests/integration -v` — all green.
2. `uv run ruff check src/ tests/` — clean.
3. `uv run lint-imports` — clean; `gameplay/turn_gatekeeper.py` does NOT import discord, bot, or mcp.
4. `grep -nE "phase2_stub_callback_invoked" src/eldritch_dm/bot/dynamic_items.py` — returns ONLY RiposteButton (Phase 5).
5. `grep -c "is_actor" src/eldritch_dm/bot/dynamic_items.py` — at least 4 (one per combat button callback).
6. `grep -nE "rate_limiter\.acquire" src/eldritch_dm/bot/dynamic_items.py` — at least 4 (mutating gate).

**Risks:**
- **D-22 dodge shim uncertainty:** The biggest unknown in the plan. Mitigate by doing the 30-min RESEARCH spike at the START of Task 2; commit findings to SUMMARY before implementing. If dm20 doesn't support either path cleanly, escalate to user — do not silently down-scope dodge.
- **D-17 monster-turn auto-resolution:** If dm20 does NOT auto-resolve monster turns on `next_turn`, the orchestrator's loop will hang waiting for action. Fallback: detect `current_actor.player_id is None` and `combat_action(action="monster_default")` (or whatever dm20 exposes for "DM resolves NPC turn"). Verify in the same spike.
- **Combat state transition race:** Orchestrator polling means a small (≤250ms) lag between dm20 entering COMBAT and CombatCog posting the embed. Acceptable UX; documented in summary. If RESEARCH suggests a webhook/SSE option, defer to v2.
- **`combat_embed` snapshot tests:** The format change (AC inline, ▶️/▫️ markers) WILL break existing snapshots. Re-baseline in the same commit; reviewer must accept the new snapshots.
- **Cog→cog handoff via bot:** `bot.close_exploration_coalescer_for(...)` and friends are convenient but if someone adds a third coalescer-owning cog, this pattern needs revisiting. Document the convention in `04-02-SUMMARY.md`.

**Open question for executor:**
- Whether CastSpellButton should be HIDDEN entirely (not rendered) in v1 or rendered-and-stubbed. CONTEXT D-15 says rendered-and-stubbed; Claude's Discretion allows hiding. Lean rendered-and-stubbed — sets the expectation for players that v2 is coming.
</verification>

<success_criteria>
- `turn_gatekeeper.py` is a pure helper with no Discord/MCP imports; 8-actor matrix (64 combos) passes.
- `combat_embed` renders 8+ initiative rows with AC inline + ▶️/▫️ turn markers.
- 4 combat buttons (Attack, Dodge, EndTurn, CastSpell stub) exist as real callbacks; all gate on `is_actor` + round-staleness check.
- WeaponSelectModal validates fields with strict regex; injection rejected.
- CombatCog posts combat_embed on EXPLORATION→COMBAT, refreshes on every dm20 state change via the orchestrator resolution callback, closes cleanly on COMBAT→EXPLORATION.
- Per D-17 monster-turn behavior is verified and documented; orchestrator handles auto-resolution correctly.
- D-22 dodge path (native or shim) is verified via 30-min spike and documented in SUMMARY.
- End-to-end integration test exercises 3 rounds of 4 PCs + 4 monsters; turn gatekeeper rejects wrong-clicker attempts; rate limiter is invoked only on accepted mutating calls.
- Requirements COMBAT-01..07, COMBAT-12 satisfied. (COMBAT-08 load test is Plan 03.)
- 25+ new tests pass; ruff + lint-imports clean.
</success_criteria>

<output>
On completion, create `.planning/phases/04-gameplay-exploration-combat/04-02-SUMMARY.md`. Required sections:
- New files + counts
- Decisions made (any divergence from CONTEXT D-XX with justification — especially D-22 dodge native-vs-shim outcome and D-17 monster-turn behavior)
- Reaction shim seam for Phase 5: pinpoint the file + function where RiposteCog will hook into the combat_action attack-miss path
- Next-phase readiness signal: "Plan 03 may now run the 8-actor load test against the fully wired orchestrator + combat cog + rate limiter."
</output>
