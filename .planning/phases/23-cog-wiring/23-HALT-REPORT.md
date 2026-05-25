---
phase: 23-cog-wiring
status: HALTED — scope-decision required
generated: 2026-05-25
trigger: HARD CONSTRAINT — "If the resolved-damage event handler doesn't exist or is ambiguous, HALT and report — don't invent a new event surface."
---

# Phase 23 HALT Report — WIRE-01 cannot be wired without inventing a new event surface

## TL;DR

WIRE-01 (`MonsterMemoryRegistry.observe_hit` cog-side call) requires a structured
post-resolution `(attacker, target, damage)` event from dm20. **No such event surface
exists in this repo.** Wiring it would require either (a) dm20 emitting a new structured
event the bot does not currently receive, or (b) parsing damage out of dm20's
markdown-narration text — which violates D-176 ("NEVER invent/infer damage") and the
EldritchDM integrity rule ("LLM never touches the math; narration is text").

The concentration half of WIRE-02 has the same problem (no concentration-cast event
surface).

The **purge-on-end_game** half of WIRE-02 and all of WIRE-03 are independently
executable and do not require the missing event surface. I have NOT touched those —
this report asks the user to decide scope before any code is written.

## Evidence (grep + read trail, all verified)

### Finding 1 — `register_resolution_callback` fires PRE-resolution player_intents, not post-resolution damage events

`src/eldritch_dm/gameplay/party_mode.py:141-151` defines the callback contract:

```python
def register_resolution_callback(
    self,
    cb: Callable[[str, dict[str, Any]], Awaitable[None]],
) -> None:
    """Register a callback invoked when a narrative is resolved.

    Args:
        cb: Async callable(channel_id: str, action: dict) → None.
            Called with the popped action dict after party_resolve_action.
    """
```

The `action` dict passed to the callback is the raw `party_pop_action` payload —
i.e., a queued **player_intent**, NOT a resolved damage event. Verified at
`party_mode.py:298-347`:

```python
action = pop_result.get("action", pop_result)
action_id = action.get("id") or action.get("turn_id")
action_kind = action.get("action_type", "player_intent")
...
for cb in self._resolution_callbacks:
    await asyncio.shield(cb(channel_id, action))
```

### Finding 2 — `dm20__combat_action` returns markdown text, not a damage tuple

`src/eldritch_dm/mcp/tools.py:283-294`:

```python
async def combat_action(client, *, action, **extra):
    """...
    Returns formatted text narration — NOT JSON. Re-fetch get_game_state for HP.
    """
```

The downstream parser at `src/eldritch_dm/gameplay/combat_outcome_parser.py` extracts
ONLY `HIT / CRITICAL / MISS / NATURAL_ONE` from the markdown header — it does NOT
extract a damage value (and intentionally so per Phase 5 design).

### Finding 3 — Existing on_resolved_combat tests pass opaque sentinels for the action dict

`tests/bot/cogs/test_combat_cog.py:366,379,392,553`:

```python
await cog.on_resolved_combat("500", {"type": "action_resolved"})
await cog.on_resolved_combat("500", {})
await cog.on_resolved_combat("500", {"type": "monster_action"})
```

The opaque payloads prove no production code currently reads a damage field from the
callback's `action` dict — because none has ever been there to read.

### Finding 4 — `get_game_state` returns markdown summary, not per-event damage deltas

`src/eldritch_dm/bot/cogs/combat.py:96-98`:

```python
# NOTE: The lightweight parse does not include per-actor HP/AC/conditions
# (dm20's get_game_state returns markdown, not JSON). CombatCog synthesizes
# combatant dicts from the initiative_order list with default HP/AC.
```

Even periodic game-state diffing would yield only HP deltas, not the `(attacker,
target, damage)` tuple `observe_hit(channel_id, session_id, monster_id, pc_id, damage)`
requires. Attributing a delta to a specific attacker requires either (a) the bot
tracking turn order + assuming the actor whose turn it was caused the delta (fragile
under AOE, riposte, reaction-damage), or (b) inventing a new event surface.

### Finding 5 — No concentration-cast event either

`grep -rn "concentration" src/eldritch_dm/{bot/cogs,gameplay/party_mode.py,mcp/tools.py}`
returns zero hits. dm20's tool catalog visible in `mcp/tools.py` exposes no
`on_concentration_cast`-style event.

## What CANNOT be done without violating constraints

| Approach | Why blocked |
|---|---|
| Parse damage out of dm20's narration text | Violates D-176 "NEVER invent/infer damage". The narration is LLM-generated; trusting it for damage values inverts the integrity contract (LLM feeds math back to deterministic state). |
| Diff `get_game_state` HP between rounds and attribute to current actor | Fragile — riposte, AOE, reactions, environmental damage all break the attribution. Also still requires inventing an event-emission boundary the cog doesn't currently have. |
| Add a new "post_resolve_event" callback to PartyModeOrchestrator that fabricates damage | Would require dm20 to emit damage — it doesn't. So the orchestrator would have to invent the value too. Out of scope (other repo) AND violates D-176. |
| Wire `observe_hit` on `combat_action` call site in MonsterDriver | The `combat_action` invocation has `(attacker, target)` but the `damage` is rolled INSIDE dm20 and returned only as embedded text in markdown. We never see the integer. |

## What CAN be done (independently — and is ready to plan/execute)

### WIRE-02 (lobby `/end_game → purge_session`) — UNBLOCKED

`MonsterMemoryRegistry.purge_session(channel_id, session_id)` does NOT need a
damage event. `/end_game` only needs:

1. Read `channel_sessions.get(channel_id)` to obtain `(channel_id, claudmaster_session_id)`.
2. Call `dm20__end_claudmaster_session(session_id=...)`.
3. Call `monster_memory_registry.purge_session(channel_id, session_id)` (fail-soft).
4. Upsert `channel_sessions` to LOBBY state.
5. Ephemeral confirmation embed.

Prerequisite: `MonsterMemoryRegistry` must be exposed on `EldritchBot` (currently
only constructed deep inside the smart driver via the factory). A new top-level
attribute `bot.monster_memory_registry` is a straightforward addition that does
NOT violate any constraint.

### WIRE-03 (AOE addendum live prompt assembly + OTel version attr) — UNBLOCKED

Current state at `src/eldritch_dm/gameplay/smart_monster_driver.py:576-579`:

```python
if action_descriptors and self._aoe_addendum_text:
    system_prompt = legacy_system_prompt + "\n\n" + self._aoe_addendum_text
else:
    system_prompt = legacy_system_prompt
```

Two changes deliver D-180/D-181:

1. Tighten predicate to `sum(1 for a in action_descriptors if a["kind"] in {"aoe","cone","breath"}) >= 2` (currently fires on any single descriptor).
2. When addendum is appended, `span.set_attribute("eldritch.aoe.addendum_version", self._aoe_addendum_version)`.
3. Add a thin `get_addendum_version()` helper to `prompts/aoe_addendum.py` (light wrapper over `load_aoe_addendum`'s second return — purely for the API surface D-182 requested; no behavioral change).

No event-surface dependency. Tests covering injection-on / injection-off / version-attr-present are straightforward driver-level tests.

## Decision asked of the user

Pick one:

**Option A — Full halt.** Defer Phase 23 entirely until dm20 ships a structured
post-resolve event (PC-dealt-damage-to-monster + concentration-cast). No code
written. Phase 23 enters BLOCKED state in ROADMAP. STATE.md untouched per task spec.

**Option B — Partial execute (RECOMMENDED).** Execute only the unblocked half:
- 23-01-PLAN.md: WIRE-02 `/end_game → purge_session` (drop the concentration half;
  re-scope as "session-close hook only").
- 23-02-PLAN.md: WIRE-03 AOE addendum tightening + OTel version attr.
- Defer WIRE-01 + concentration to a future phase with a `requires: dm20-resolved-damage-event` blocker note in REQUIREMENTS.md.

**Option C — Override the HARD CONSTRAINT.** User explicitly authorizes one of the
"CANNOT" approaches above (e.g., "trust the narration parser, accept the integrity
risk"). This is the user's call to make, not mine — flagging because the constraint
file said "HALT and report" not "halt unless tempted".

## What I did NOT do (mechanically honest about the work boundary)

- Did NOT write 23-01-PLAN.md or 23-02-PLAN.md (waiting on scope decision).
- Did NOT edit any source file under `src/`.
- Did NOT edit STATE.md, ROADMAP.md, or REQUIREMENTS.md.
- Did NOT touch tests.
- Did read: 23-CONTEXT.md, monster_memory.py, smart_monster_driver.py (lines 1-780),
  monster_driver.py (lines 170-250), party_mode.py (lines 100-360), combat.py (full),
  lobby.py (lines 1-100), combat_outcome_parser.py (full), aoe_addendum.py (full),
  mcp/tools.py (lines 175-294), and grepped tests/ for the on_resolved_combat call shape.

## Next step

User responds with A / B / C. On B, I will write both plans and execute them in the
same agent session (or you can re-spawn — either works). On A or C, you decide what
state mutation if any.
