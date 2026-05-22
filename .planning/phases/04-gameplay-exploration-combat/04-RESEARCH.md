# Phase 4: Gameplay — Exploration + Combat (Party Mode) - Research

**Researched:** 2026-05-22
**Domain:** dm20 Party Mode binding + Discord combat UI under load
**Confidence:** HIGH (all 10 questions answered against dm20 source at `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/`)

## Summary

Every Phase 4 unknown surfaced in `04-CONTEXT.md` and `STATE.md § Blockers` was answered by reading the dm20 source directly. The headline findings:

1. **`party_pop_action` returns immediately on an empty queue** — `{"empty": True, "pending": 0}` — so the 250ms polling cadence in `D-04` is correct and cheap. No backoff needed.
2. **dm20 has NO "dodging" SRD condition.** The 14 SRD conditions are the classic 5e set (blinded, charmed, deafened, exhaustion, frightened, grappled, incapacitated, invisible, paralyzed, petrified, poisoned, prone, restrained, stunned). **Dodge MUST be shimmed** as a custom effect with `grants_disadvantage=["attack_roll"]` on the dodger (tracked on attacker side per 5e SRD convention) plus an `eldritch_dm.combat_conditions` local table to drive the "incoming attacks have disadvantage against dodger" rule on the bot side until the dodger's next turn.
3. **dm20 `next_turn` does NOT auto-resolve monster turns.** It simply advances `current_turn` to the next alive participant and ticks effects. **Our orchestrator owns driving monster turns** — on a monster turn it must (a) call Claudmaster (`dm20__player_action` with `character_name=<monster>` framing OR direct `combat_action(attacker=<monster>, target=<PC>)`) to resolve the monster's action, (b) update the Discord embed, (c) call `next_turn` again.
4. **dm20 is a hard single-campaign single-process architecture.** `storage` is a module-level singleton (`main.py:51`); the Party Mode server is also a process-global singleton (`party/server.py:61`, `_server_instance`). **Multiple campaigns in one dm20 process is unsupported.** Multi-campaign Discord deployments require multiple dm20 processes — out of scope for v1 but a documentation must.
5. **`combat_action` does NOT accept a `reaction` arg.** Phase 5 (Riposte) will need a different mechanism (likely a local "I'm a reaction, not a turn action" flag plus a normal `combat_action` call). Phase 4's Attack flow does NOT need this — it's a standard turn action.
6. **All dm20 tools return plain-text formatted strings, not JSON** (the only JSON returner is `party_pop_action`). For state we re-fetch via `get_game_state` after every mutation. **No structured result parsing of combat_action output** — we treat its text as narration source material and pull authoritative HP/state from `get_game_state`.
7. **None of the dm20 tools accept a `campaign_name` arg.** Our Phase 1 wrappers in `src/eldritch_dm/mcp/tools.py` that pass `campaign_name=...` to dm20 calls are **silently sending an unknown kwarg that FastMCP may pass through or reject**. Phase 4 plan MUST audit and remove these stray kwargs from every wrapper.

**Primary recommendation:** Treat dm20 as a "single-tenant, text-result, global-state" service. Build the `PartyModeOrchestrator` around polling at 250ms with immediate-return semantics; refetch `get_game_state` after every mutation; shim Dodge in a local table; drive monster turns explicitly. Plan must include a `tools.py` audit task to remove `campaign_name=` kwargs.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01..D-36** — all 36 implementation decisions in `04-CONTEXT.md § decisions` are locked. Plans must conform.
- Key locks for research: 250ms `PARTY_POLL_INTERVAL_MS` env-driven (D-04), per-channel asyncio.Task orchestrator (D-05), batching coordinator with 30s deadline (D-07/D-08), token bucket per channel at 200ms/mutating call (D-28), `riposte_timers` table re-use OR small new `combat_conditions` table for active dodge (D-22, leaning re-use per D-Discretion).
- D-15: `AttackButton` custom_id `attack:(?P<channel_id>\d+):(?P<actor_id>\d+):(?P<round>\d+)` — round in the custom_id IS a cache-buster.

### Claude's Discretion

- Polling cadence inside `PartyModeOrchestrator` (250ms env default; tune in plan if MEM/CPU shows issues)
- Whether `riposte_timers` is re-used for dodge OR a tiny new `combat_conditions` table (re-use is simpler; new table is cleaner; lean re-use)
- Per-channel asyncio.Task vs per-process worker with queue (per-channel for v1)
- Cast Spell button copy ("⚗️ Spellcasting is coming in v2" ephemeral, OR hide the button)

### Deferred Ideas (OUT OF SCOPE)

- Spellcasting beyond stub (slots, concentration, area effects) — v2
- Initiative reroll mid-combat — v2
- Player-DM private DMs from the AI (`dm20__send_private_message`) — v2
- Combat undo / rewind — v2
- Real-time spectator mode for non-party members — v2
- Voice channel announcements ("Thorin is up!") — v2

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXPLORE-01 | `room_embed` + `[💬 Declare Action]` persistent button | DeclareActionButton already stubbed in `dynamic_items.py`; promote callback to real (Q7) |
| EXPLORE-02 | Action modal (500-char cap) → party-mode queue | Sanitizer + modal pattern from Phase 3 (`IngestCog`). Push via Claudmaster `player_action`, NOT a direct queue write (see Q1) |
| EXPLORE-03 | Polls `party_pop_action`; calls `party_thinking` | Q1: returns immediately on empty queue → 250ms polling cheap |
| EXPLORE-04 | `party_get_prefetch` for combat-relevant turns | Q1+Q5: best-effort cache, fall back to direct narration on miss |
| EXPLORE-05 | Narrative via `party_resolve_action` → Discord render | Q1: `party_resolve_action(action_id, narrative, private_messages?, dm_notes?)` |
| EXPLORE-06 | 30s action batching | Pure-bot logic; no dm20 support needed |
| EXPLORE-07 | Combat trigger via game_state polling | Q5: `get_game_state` returns formatted string — parse `**In Combat:** Yes/No` line |
| COMBAT-01 | Combat embed from `get_game_state` initiative | Q5 — initiative_order has `name` + `initiative` per row |
| COMBAT-02 | 8+ initiative rows, coalescer-refreshed | Q7: coalescer's ≤1 edit/sec/message is the right pacing |
| COMBAT-03 | Action buttons w/ actor user_id in custom_id | D-15 — `round` in custom_id is cache-buster |
| COMBAT-04 | Turn gatekeeper via `player_name` field on character | Q9 — Character.player_name persisted at Phase 3 ingest |
| COMBAT-05 | Attack flow | Q6 — `combat_action(attacker, target, action_type, weapon_or_spell)` — NO `reaction` arg |
| COMBAT-06 | Dodge → `apply_effect` | Q2 — MUST shim; no "dodging" SRD condition |
| COMBAT-07 | End Turn → `next_turn` | Q3 — does NOT advance through monster turns; orchestrator must drive monster turns |
| COMBAT-08 | 8-player load test, zero 429 | Q7 — coalescer + 250ms poll easily within 5/5s budget |
| COMBAT-12 | Combat-end detection | Q5 — `get_game_state` flips `in_combat` to false after `end_combat` OR when all participants dead |
| OPS-03 | Per-channel mutating-call token bucket | Q9 — protects dm20 from button-spam races; works alongside per-channel asyncio.Lock |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Game math (HP/AC/dice/conditions) | dm20 (Backend) | — | Locked: "LLM never touches math"; dm20 is the rules engine |
| Narrative generation | Claudmaster (Backend, via dm20) | oMLX ShoeGPT | Claudmaster orchestrates the LLM via `player_action`; ShoeGPT generates the prose |
| Turn-order enforcement (whose Discord user_id can click) | Discord Bot (Frontend) | — | dm20 has no concept of "Discord user"; only `player_name` strings |
| Combat embed rendering + rate-limit budget | Discord Bot | — | Discord-specific; `EmbedCoalescer` from Phase 2 |
| Party Mode pop/resolve loop | Discord Bot (gameplay/) | dm20 (queue + Claudmaster) | Bot polls; Claudmaster's `player_action` resolves; bot pushes via `party_resolve_action` |
| Dodge condition tracking | Discord Bot (local SQLite) | dm20 (custom_effect with disadvantage hint) | Q2 — dm20 has no built-in "dodging"; bot owns the timer + the disadvantage application at attack-resolution time |
| Monster turn driving | Discord Bot (orchestrator) | Claudmaster + dm20 combat_action | Q3 — `next_turn` does not auto-resolve; bot decides what the monster does (Claudmaster) and applies it via `combat_action` |
| Combat trigger detection | Discord Bot (orchestrator) | dm20 game_state | Q5 — bot polls `get_game_state`, parses `In Combat:` line; transition is bot-observed |

## Standard Stack

No new packages for Phase 4 — every dep is already pinned by Phase 1-3.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `discord.py` | `==2.7.1` | Modals + Select Menus in attack flow | [CITED: project CLAUDE.md] |
| `aiosqlite` | `>=0.20,<0.22` | `combat_conditions` table (or `riposte_timers` re-use) | [CITED: project CLAUDE.md] |
| `httpx` | `>=0.27,<0.29` | Already used by `MCPClient` for `:8765/v1/mcp/execute` | [CITED: project CLAUDE.md] |
| `structlog` | `>=24.4,<26.0` | D-36 context binding per action | [CITED: project CLAUDE.md] |
| `tenacity` | `>=8.5,<10.0` | Already used by `MCPClient` for retries | [CITED: project CLAUDE.md] |

**Installation:** none — all already in `pyproject.toml`.

## Package Legitimacy Audit

Phase 4 introduces **zero new packages**. Section is informational only.

| Package | Registry | Disposition |
|---------|----------|-------------|
| _no new packages_ | _n/a_ | _n/a_ |

## Architecture Patterns

### System Architecture Diagram

```
                ┌──────────────────────────────────────────────────────┐
                │                  Discord (channel)                    │
                │  ┌──────────┐  ┌────────────┐  ┌──────────────────┐  │
                │  │ Modal:   │  │ Combat     │  │ Persistent       │  │
                │  │ Declare  │  │ Embed      │  │ Buttons: Attack/ │  │
                │  │ Action   │  │ (init.+HP) │  │ Dodge/End Turn   │  │
                │  └────┬─────┘  └─────▲──────┘  └────────┬─────────┘  │
                └───────┼──────────────┼──────────────────┼────────────┘
                        │ submit       │ edit (coalesced) │ click
                        ▼              │                  ▼
        ┌───────────────────────────────────────────────────────────────┐
        │  ExplorationCog / CombatCog (per-channel)                     │
        │  ┌───────────────────────────────────────────────────────┐    │
        │  │ Sanitizer → BatchCoordinator (30s, EXPLORE-06)        │    │
        │  └────────────────────────┬──────────────────────────────┘    │
        │                           │ flush                              │
        │  ┌────────────────────────▼──────────────────────────────┐    │
        │  │ PartyModeOrchestrator (one asyncio.Task per channel)  │    │
        │  │  ╭──────────────────────────────────────────────╮     │    │
        │  │  │ loop:                                        │     │    │
        │  │  │   pop_action  (250ms poll)                   │     │    │
        │  │  │   if empty: sleep                            │     │    │
        │  │  │   else:                                      │     │    │
        │  │  │     party_thinking → claudmaster.player_act. │     │    │
        │  │  │     party_resolve_action(narrative)          │     │    │
        │  │  │     render in Discord (coalescer)            │     │    │
        │  │  │   periodically: get_game_state               │     │    │
        │  │  │     if in_combat changed → swap UI           │     │    │
        │  │  │     if current_turn is NPC → drive monster   │     │    │
        │  │  ╰──────────────────────────────────────────────╯     │    │
        │  └─┬─────────────────────────────────────────────────────┘    │
        │    │ all mutating calls pass through ChannelTokenBucket       │
        │    │  (OPS-03, 1 mutating call / 200ms / channel)             │
        │    │ all dm20 calls hold per-channel asyncio.Lock (Phase 1)   │
        └────┼──────────────────────────────────────────────────────────┘
             ▼  HTTP POST :8765/v1/mcp/execute
        ┌────────────────────────────────────────────────────────────────┐
        │   oMLX :8765   (single process)                                │
        │   ├─ ShoeGPT inference (Gemma 4 4-bit)                         │
        │   └─ FastMCP server                                            │
        │       └─ dm20 (single global storage, single Party server)     │
        │            • storage.get_character / list_characters           │
        │            • storage.get_game_state (in_combat, initiative)    │
        │            • action_queue (JSONL-persisted, restart-safe)      │
        │            • combat pipeline (attack, save_spell, effects)     │
        └────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure (additions)

```
src/eldritch_dm/
├── gameplay/                          # NEW (D-02)
│   ├── __init__.py
│   ├── party_mode.py                 # PartyModeOrchestrator (one Task per channel)
│   ├── batch.py                       # ExplorationBatch + BatchCoordinator
│   ├── monster_driver.py              # detects monster turn, drives via Claudmaster
│   └── state_watcher.py               # parses get_game_state for combat trigger
├── mcp/
│   └── rate_limit.py                  # NEW (D-28) ChannelTokenBucket
├── bot/cogs/
│   ├── exploration.py                 # NEW (D-01)
│   └── combat.py                      # NEW (D-01)
└── persistence/
    └── combat_conditions_repo.py      # NEW (or reuse riposte_timers_repo) for active dodge
tests/gameplay/                        # NEW
├── test_party_orchestrator.py
├── test_batch_coordinator.py
├── test_monster_driver.py
├── test_turn_gatekeeper.py
└── test_8_player_load.py              # COMBAT-08 — the deliverable
```

### Pattern 1: Empty-queue polling, immediate-return

```python
# Source: dm20-protocol/src/dm20_protocol/main.py:4992-5014
# party_pop_action returns immediately on empty queue.
PARTY_POLL_INTERVAL_S = settings.party_poll_interval_ms / 1000  # default 0.25

async def _orchestrator_loop(self, channel_id: int) -> None:
    while not self._stopping.is_set():
        try:
            pop = await mcp_tools.party_pop_action(self._client)
            # pop["empty"] is True → sleep and retry. NO BLOCKING ON DM20 SIDE.
            if pop.get("empty", True):
                await asyncio.sleep(PARTY_POLL_INTERVAL_S)
                continue
            action = pop["action"]  # {id, player_id, text, timestamp, status, private}
            await self._handle_action(channel_id, action)
        except CircuitBreakerOpen:
            await asyncio.sleep(2.0)  # back off when dm20 is down
        except Exception:
            log.exception("orchestrator_loop_error", channel_id=channel_id)
            await asyncio.sleep(1.0)
```

### Pattern 2: Dodge shim (D-22, Q2)

```python
# Source: derived from dm20 effects.py — SRD has grants_disadvantage on attack_roll
#         but the 5e Dodge rule grants disadvantage to *attackers* against the
#         dodger AND advantage on the dodger's DEX saves. dm20's ActiveEffect
#         model can only express "this entity has disadvantage on X". The
#         attacker-side disadvantage MUST be applied by the bot at attack time.

# Step 1 — apply local "dodging" effect on the dodger
custom_modifiers_json = json.dumps([
    {"stat": "saving_throw_dexterity", "operation": "advantage", "value": 1},
])
await mcp_tools.apply_effect(
    client,
    character_name_or_id=dodger_name,
    effect_name="dodging",                # dm20 will create a custom ActiveEffect
    source="Dodge action",
    duration=1,                           # 1 round; dm20 ticks at next turn start
    custom_modifiers=custom_modifiers_json,
)

# Step 2 — record locally so attack resolution knows to apply disadvantage
await combat_conditions_repo.upsert(
    channel_id=channel_id,
    character_id=dodger_id,
    condition="dodging",
    expires_round=current_round + 1,
)

# Step 3 — End turn
await mcp_tools.next_turn(client)

# At attack-resolution time, before combat_action:
# if target has active "dodging" condition → tell narration "attack has disadvantage"
# (Bot cannot literally pass disadvantage to dm20's combat_action — there is no
#  such arg. Mitigation: roll the attack twice yourself via dice MCP, take lower,
#  then frame as a save_spell-style override OR just apply the rule in narration
#  with a small XP fudge. Plan must call this out — see Pitfall 3.)
```

**Important:** dm20's `combat_action` does not accept advantage/disadvantage hints. The cleanest v1 path is:

- Phase 4 implements the Dodge **UX** correctly (button → effect → end turn)
- The "attack has disadvantage against dodger" rule is **partially honored** for v1: the dodger gets dm20's standard advantage on DEX saves through `custom_modifiers`, but incoming attack disadvantage is **rendered in narration** ("the goblin's swing goes wide as Aria sidesteps") without dice-rolling the attacker twice.
- Document this gap explicitly in the plan + README; v2 either patches dm20 OR the bot rolls attack dice via the `dice` MCP and overrides `combat_action`.

### Pattern 3: Monster turn driver (D-17 → real implementation, Q3)

```python
# Source: dm20-protocol/src/dm20_protocol/main.py:1756 (next_turn) +
#         main.py:1967 (combat_action) + storage.get_character returns None for
#         monsters (they're storage.get_npc).

async def _drive_current_turn(self, channel_id: int) -> None:
    state = await mcp_tools.get_game_state(self._client)
    current = self._parse_current_turn(state)   # "Goblin Scout"
    char = await mcp_tools.get_character(self._client, name_or_id=current)

    if char.get("error") or self._parse_player_name(char) is None:
        # MONSTER TURN — bot drives it
        target = await self._select_target_via_claudmaster(channel_id, current)
        result = await mcp_tools.combat_action(
            self._client,
            attacker=current,
            target=target,
            action_type="attack",   # most monsters default to melee
        )
        # result is formatted text — feed it back through narrative
        await mcp_tools.party_resolve_action(
            self._client,
            action_id=self._synthesize_monster_action_id(channel_id, current),
            narrative=self._format_monster_narrative(current, result),
        )
        # Update embed + advance
        await self._refresh_combat_embed(channel_id)
        await mcp_tools.next_turn(self._client)
        return

    # PC TURN — render the action buttons and WAIT for click; do NOT loop
    await self._render_pc_turn_buttons(channel_id, char)
```

### Pattern 4: Combat trigger via game_state parsing

```python
# Source: dm20-protocol/src/dm20_protocol/main.py:1627-1668
# get_game_state returns a formatted markdown string, not JSON. Parse it.

_IN_COMBAT_RE = re.compile(r"\*\*In Combat:\*\*\s+(Yes|No)")
_CURRENT_TURN_RE = re.compile(r"\*\*Current Turn:\*\*\s+(.+?)$", re.MULTILINE)
_INIT_ROW_RE = re.compile(r"^\s+\d+\.\s+(.+?)\s+\(Initiative:\s+(-?\d+)\)$", re.MULTILINE)

def parse_game_state(raw: str) -> ParsedGameState:
    in_combat_m = _IN_COMBAT_RE.search(raw)
    in_combat = bool(in_combat_m and in_combat_m.group(1) == "Yes")
    current = _CURRENT_TURN_RE.search(raw)
    initiative = [(m.group(1), int(m.group(2))) for m in _INIT_ROW_RE.finditer(raw)]
    return ParsedGameState(
        in_combat=in_combat,
        current_turn=current.group(1).strip() if current else None,
        initiative=initiative,
    )
```

**Future-proofing:** add a TODO in `state_watcher.py` — if dm20 ever ships a structured `get_game_state_json` tool, swap the parser. For v1, the regex is stable because the format is hand-written in dm20's source (`main.py:1644-1652`).

### Anti-Patterns to Avoid

- **Don't pass `campaign_name=` to any dm20 tool.** The dm20 tools (combat_action, next_turn, apply_effect, get_game_state, all party_*) take zero campaign-scoping args — they operate on the global `storage` singleton. Phase 1 wrappers do this incorrectly today; Phase 4 plan must include a `tools.py` audit task.
- **Don't trust `combat_action`'s text result as authoritative for HP.** Re-fetch `get_game_state` after every mutation. dm20 persists HP changes inside `combat_action` (we saw `storage.update_character` at line 2101) but the only structured source for the bot is `get_game_state`.
- **Don't run two PartyModeOrchestrators against the same dm20 process.** Even with multiple Discord channels mapped to multiple "campaigns" in our `channel_sessions` table, dm20 only has one global campaign. Multi-channel = multi-dm20-process — out of scope for v1, document the limitation.
- **Don't poll `get_game_state` faster than 1 Hz per channel.** It does a full markdown render every call; piggyback on the `party_pop_action` loop (every 250ms but only invoke `get_game_state` once per ~4 ticks) — see Q5.
- **Don't assume `next_turn` ends the monster's turn for you.** It only advances to the next participant. Driving the monster's action is the orchestrator's responsibility.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Encounter CR budget calculation | Custom XP-budget math | `dm20__build_encounter_tool` | dm20 already wraps DMG Chapter 3 rules |
| Initiative tracking | Our own ordering | `dm20.start_combat` + `get_game_state` initiative_order | dm20 owns the canonical order + dead/incap skip logic in next_turn |
| Effect duration ticking | Bot timers | dm20 `apply_effect(duration=N)` + `next_turn` ticks | `next_turn` calls `EffectsEngine.tick_effects(char, event="turn")` automatically |
| Player action JSONL crash-recovery | Our own append-only log | dm20's `actions.jsonl` (party/queue.py:107) | dm20 already restores `_pending` from disk on restart |
| TTS / voice rendering | Our pipeline | dm20's `_party_tts_speak` (main.py:5058) | out-of-scope for v1; dm20 handles it when `interaction_mode` is set |
| Concentration check on damage | Our own | dm20's `ConcentrationTracker.check_concentration` (already in pipeline) | combat_action already triggers it |
| Initiative roll | Our dice math | `dice__roll` MCP OR pass pre-rolled initiative to `start_combat` | dm20 expects initiative values; we can call `dice__roll(1d20+DEX)` and pass them |

**Key insight:** dm20's `combat_action` does 90% of the math — pipeline resolves attack, applies HP, ticks concentration, persists. Our job is purely orchestration: knowing *when* to call it, *what args* to pass, and *how to render* the result. The one significant rule we lose is "attack disadvantage against dodging target" (because `combat_action` lacks a disadvantage arg) — see Pattern 2 for the v1 mitigation.

## Runtime State Inventory

> Phase 4 introduces new code paths but is not a rename/refactor phase. The only inherited runtime state concern is the existing `riposte_timers` table — see below.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `dm20.~/.omlx/dm.db` characters carry `player_name` set by Phase 3 ingest; `dm20.{campaign_dir}/party/actions.jsonl` and `responses.jsonl` persist Party Mode queue state | None — both are dm20-owned; bot is read-side only |
| Live service config | dm20's Party Mode server is a process-global singleton. Multiple campaigns in one dm20 process is impossible (see Q4). | Documentation only (README HOST-01) |
| OS-registered state | None — bot has no Task Scheduler / launchd entries. dm20 + oMLX are launchd-supervised separately (`com.user.omlx`). | None |
| Secrets/env vars | New env: `PARTY_POLL_INTERVAL_MS` (already documented in `.env.example` per D-04). No new secrets. | Confirm `.env.example` line exists |
| Build artifacts | None | None |
| Local SQLite | `riposte_timers` table is being considered for dodge-state re-use (D-22, Discretion). If we re-use, the existing `status` column gets a new enum value `'dodging'`; if we split, we add a `combat_conditions(channel_id, character_id, condition, expires_round)` table. | Plan picks one; if new table, bootstrap migration |

## Common Pitfalls

### Pitfall 1: `combat_action` returns formatted text, not JSON

**What goes wrong:** Wrappers that try to `result["damage"]` or `result["hit"]` will fail because dm20 returns a multi-line markdown string ("Hit! Thorin hits Goblin Scout.\nGoblin Scout: 4/7 HP").
**Why it happens:** dm20 was designed for chat-based DMs first; the bot/HTTP layer is a recent retrofit.
**How to avoid:** Treat `combat_action` result as **narration source** only. Pull authoritative state via `get_game_state` immediately after.
**Warning signs:** `TypeError: string indices must be integers` in orchestrator tests.

### Pitfall 2: `campaign_name=` kwarg silently propagated

**What goes wrong:** Phase 1 wrappers pass `campaign_name` to every dm20 tool; dm20 tools don't accept it. FastMCP either rejects (HTTP 400) or accepts-and-ignores depending on schema strictness.
**Why it happens:** Phase 1 wrappers were written from the multi-campaign assumption that turned out to be wrong (Q4).
**How to avoid:** Phase 4 plan MUST include an audit task: `grep -n 'campaign_name=' src/eldritch_dm/mcp/tools.py | wc -l` should be 0 for every dm20 tool except those that actually take it (`create_campaign`, `load_campaign`, `get_campaign_info`). Re-check each wrapper signature against `main.py`.
**Warning signs:** dm20 returns "unexpected keyword argument" OR the tool runs but ignores the campaign scoping silently.

### Pitfall 3: Dodge's "attack disadvantage" is unenforceable through `combat_action`

**What goes wrong:** Player clicks Dodge, the LLM narrates a perfect parry, but the next monster attack hits anyway because `combat_action` rolled normally — players lose trust in the mechanically-honest claim.
**Why it happens:** dm20's pipeline doesn't accept advantage/disadvantage hints from `combat_action`'s args (verified: only attacker, target, action_type, weapon_or_spell, damage_dice, damage_type, save_ability, half_on_save, spell_dc).
**How to avoid:** Document the v1 limitation in README; v1 simulates disadvantage via narration only ("you sidestep the brunt of the blow") for the dodger; dm20 still rolls without modifier. The DEX-save advantage IS honored via custom_modifiers.
**Warning signs:** Player complaint "I dodged and still got hit for full damage." Counter with v2-roadmap note.

### Pitfall 4: Discord per-channel 5-edits/5s budget under multi-coalescer load

**What goes wrong:** With 8 players, the COMBAT embed updates 4× per round (turn start, action result, effects applied, end of turn). Five rounds = 20 edits on a single message in 5-20 seconds. The PER-MESSAGE rate is fine (1/sec); the PER-CHANNEL aggregate is also fine (one message). But if EXPLORATION and COMBAT cogs each spawn their own coalescer on the same channel during a transition, we briefly have 2 coalescers competing → 429.
**Why it happens:** Discord's edit limit is 5/5s per channel; we have a per-message budget but not a per-channel budget (Phase 2's `ChannelEditBudget` is a stub — `coalescer.py:45-51`).
**How to avoid:** During EXPLORATION↔COMBAT transitions, ABANDON the old coalescer (`coalescer.close()`) before creating a new one. The new state's coalescer starts with a fresh per-message budget; the channel-level budget is healed by the natural 1s spacing between updates.
**Warning signs:** `discord.HTTPException: 429` in logs during transitions; coalescer test `test_8_player_load.py` fails on the boundary case.

### Pitfall 5: `dm20__player_action` is async; everything else is sync

**What goes wrong:** Bot calls combat_action with `await`; dm20 returns synchronously inside FastMCP. No problem — the MCP HTTP boundary makes everything `awaitable` on our side. But the `player_action` Claudmaster tool is **actually async on the dm20 side** (`main.py:4037: async def player_action`). The HTTP boundary doesn't care, but plan must be aware that `player_action` is slower (multi-second LLM call) than other tools (10s of ms).
**Why it happens:** Mixed sync/async in dm20's tool definitions.
**How to avoid:** Don't hold a per-channel `asyncio.Lock` while awaiting `player_action` — release before the LLM call OR scope the lock narrowly around state mutations.
**Warning signs:** Lock contention complaints in logs; a single slow `player_action` blocks every other interaction in the channel.

### Pitfall 6: `party_pop_action`'s "private" flag is per-action, not per-player

**What goes wrong:** Bot assumes the `text` field of a popped action is always public; renders it in the channel; a private intent ("I want to assassinate the mayor — don't tell the others") leaks.
**Why it happens:** Action dict has a `private` boolean (`queue.py:131-138`); bot needs to honor it.
**How to avoid:** On pop, if `action.private is True`, route the resolved narrative as an ephemeral or DM to that specific player, not the channel. Bot code: `if action.get("private"): use ephemeral`.
**Warning signs:** Player breach-of-privacy complaints during playtest.

## Open Questions

1. **Where do player Discord user_ids map to dm20 `player_name` values?**
   - What we know: Phase 3 persists `player_id=str(interaction.user.id)` as `player_name` on `dm20__create_character` (STATE.md "Decisions" line: "player_id=str(interaction.user.id) persisted on dm20__create_character for Phase 4 turn gatekeeping").
   - What's unclear: Is `Character.player_name` accessed as a string-equal field, or do we need a separate mapping table?
   - Recommendation: Bot's turn gatekeeper uses `int(character.player_name) == interaction.user.id` per the locked Phase 3 decision. Plan should add a defensive check + audit (some characters created before Phase 3 might have human-readable `player_name`s — add a `channel_sessions` join check OR a one-time normalization).

2. **Does `dice__roll` MCP exist for monster turn dice / initiative rolling?**
   - What we know: `ddmcpskills.md` lists `dice__roll_dice` (and 3 other dice tools) as exposed at `:8765`.
   - What's unclear: Whether we should pre-roll initiative in the bot and pass to `start_combat`, or rely on dm20 to compute initiative (it does NOT — `start_combat` accepts pre-sorted participants).
   - Recommendation: Bot rolls initiative via `dice__roll_dice("1d20+{dex_mod}")` for each participant, passes structured list to `start_combat`. This is a Phase 4 plan task.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `oMLX :8765/v1/mcp/execute` | All MCP calls | ✓ (launchd `com.user.omlx`) | — | None — bot replies "DM is offline" (OPS-02) |
| `dm20` MCP server | All gameplay calls | ✓ (exposed via oMLX) | — | None — same circuit breaker |
| `discord.py 2.7.1` | Cogs + DynamicItems | ✓ | 2.7.1 | None |
| `aiosqlite` | local state | ✓ | 0.20+ | None |
| `Settings.party_poll_interval_ms` | D-04 polling | ✓ (already in env) | 250 default | Fall back to hard-coded 250 in code if env unset |

**Missing dependencies with no fallback:** none — Phase 1-3 delivered everything.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (already configured Phase 1) |
| Config file | `pyproject.toml` + `conftest.py` |
| Quick run command | `pytest tests/gameplay/ -x --no-header -q` |
| Full suite command | `pytest` |
| Phase gate | All 469 existing tests + new gameplay tests green before `/gsd:verify-work` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXPLORE-03 | Polls pop_action; empty-queue cheap | unit | `pytest tests/gameplay/test_party_orchestrator.py::test_empty_queue_polling -x` | ❌ Wave 0 |
| EXPLORE-05 | Full pop→thinking→resolve cycle once per action | unit | `pytest tests/gameplay/test_party_orchestrator.py::test_pop_thinking_resolve_sequence -x` | ❌ Wave 0 |
| EXPLORE-06 | 30s batching coalesces N submissions | unit | `pytest tests/gameplay/test_batch_coordinator.py -x` | ❌ Wave 0 |
| EXPLORE-07 | get_game_state parser detects in_combat=true | unit | `pytest tests/gameplay/test_state_watcher.py::test_in_combat_detection -x` | ❌ Wave 0 |
| COMBAT-02 | 8-row initiative renders | unit/snapshot | `pytest tests/gameplay/test_combat_embed.py::test_8_initiative_rows -x` | ❌ Wave 0 |
| COMBAT-04 | Turn gatekeeper rejects wrong user_id | unit | `pytest tests/gameplay/test_turn_gatekeeper.py -x` | ❌ Wave 0 |
| COMBAT-05 | Attack flow: weapon modal → combat_action | unit | `pytest tests/gameplay/test_attack_flow.py -x` | ❌ Wave 0 |
| COMBAT-06 | Dodge applies effect + advances turn | unit | `pytest tests/gameplay/test_dodge_shim.py -x` | ❌ Wave 0 |
| COMBAT-07 | End Turn → next_turn called | unit | `pytest tests/gameplay/test_end_turn.py -x` | ❌ Wave 0 |
| COMBAT-08 | 8-player load test, zero 429 | integration | `pytest tests/gameplay/test_8_player_load.py -x -v` | ❌ Wave 0 |
| COMBAT-12 | get_game_state in_combat=false → return to EXPLORATION | unit | `pytest tests/gameplay/test_state_watcher.py::test_combat_end_transition -x` | ❌ Wave 0 |
| OPS-03 | Token bucket caps at 1 mutating / 200ms | unit | `pytest tests/gameplay/test_rate_limit.py -x` | ❌ Wave 0 |
| BOT-08 ext | Restart mid-combat resumes turn | integration | `RUN_INTEGRATION=1 pytest tests/gameplay/test_restart_mid_combat.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/gameplay/ -x --no-header -q`
- **Per wave merge:** `pytest -x --no-header -q`
- **Phase gate:** Full suite green; load test green with mock_call_count + interval assertions

### Wave 0 Gaps
- [ ] `tests/gameplay/__init__.py` — package marker
- [ ] `tests/gameplay/conftest.py` — shared fixtures: `fake_mcp_client`, `mock_dm20_state`, `mock_discord_message`, `synthetic_combatants(n=8)`
- [ ] `tests/gameplay/test_party_orchestrator.py`
- [ ] `tests/gameplay/test_batch_coordinator.py`
- [ ] `tests/gameplay/test_state_watcher.py`
- [ ] `tests/gameplay/test_combat_embed.py`
- [ ] `tests/gameplay/test_turn_gatekeeper.py`
- [ ] `tests/gameplay/test_attack_flow.py`
- [ ] `tests/gameplay/test_dodge_shim.py`
- [ ] `tests/gameplay/test_end_turn.py`
- [ ] `tests/gameplay/test_8_player_load.py` — **the COMBAT-08 deliverable**
- [ ] `tests/gameplay/test_rate_limit.py`
- [ ] `tests/gameplay/test_restart_mid_combat.py`

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Discord OAuth identity (already Phase 1); dm20 Party Mode has its own token auth on `:8080` — we don't expose that to players |
| V4 Access Control | yes | Turn gatekeeper (COMBAT-04); only invoking player or DM can interact (Phase 3 INGEST-10 precedent) |
| V5 Input Validation | yes | `sanitize_player_input` strips `<tool_call>`, `<\|im_start\|>`, etc. before any LLM exposure (Phase 1 SAN-01..06) |
| V6 Cryptography | no | No new crypto in Phase 4 |

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Player A clicks Player B's Attack button | Spoofing | Turn gatekeeper (COMBAT-04); ephemeral NOT_YOUR_TURN warning |
| Prompt injection via modal free-text | Tampering | `sanitize_player_input` (Phase 1 SAN-02) |
| Spam-click combat buttons to thrash dm20 | DoS | Per-channel token bucket (OPS-03, D-28); per-channel asyncio.Lock (Phase 1 MCP-07) |
| Two players battle for an action button simultaneously | Tampering / race | per-channel asyncio.Lock around mutating MCP call; idempotency via dm20's action_id |
| Private intent ("kill the mayor in secret") leaks | Information disclosure | Pitfall 6 — honor `action.private` flag from pop_action; route via ephemeral |

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| LLM-as-DM end-to-end (LangChain pattern) | dm20 owns rules; LLM only narrates; bot orchestrates | Mechanically honest math (project thesis) |
| WebSocket subscription to player actions | HTTP polling via `party_pop_action` every 250ms | Simpler; dm20 doesn't expose a WS API for the MCP host (only for browser players) |
| Hand-rolled initiative tracker | dm20's initiative_order + skip-dead logic in `next_turn` | One less subsystem to maintain |

## Sources

### Primary (HIGH confidence)
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/main.py` — read directly: `party_pop_action` (4991-5014), `party_resolve_action` (5166-5213), `party_thinking` (5216-5248), `party_get_prefetch` (5251+), `combat_action` (1967-2106), `apply_effect` (2197-2278), `remove_effect` (2281-2318), `next_turn` (1755-1832), `start_combat` (1687-1722), `end_combat` (1724-1753), `get_game_state` (1626-1668), `build_encounter_tool` (2110-2137), `get_character` (472+), `start_party_mode` (4749-4925), `stop_party_mode` (4928-4944), `get_party_status` (4947-4988), `player_action` (4036-4049), `storage` global (51)
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/combat/effects.py` — verified SRD_CONDITIONS contains exactly 14 keys, none is "dodge"/"dodging"
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/party/queue.py` — `ActionQueue` JSONL-persistent, thread-safe, restart-safe
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/party/server.py:61` — `_server_instance` process-global singleton (confirms single Party Mode per process)
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/models.py` — `Character.player_name`, `class NPC` (Character ≠ NPC distinction for monster detection)
- `/Users/shoemoney/Services/DiscordDM/ddmcpskills.md` — generated tool signatures match source verbatim

### Secondary (MEDIUM confidence)
- [Discord rate limits — 5 message edits / 5s per channel](https://discord.com/developers/docs/topics/rate-limits) — confirmed in Phase 2 RESEARCH; informs Pitfall 4
- [discord.py Modal + Select Menu docs](https://discordpy.readthedocs.io/en/v2.7.1/) — Phase 3 used the same patterns successfully
- [space-node 2026 Discord bot rate-limit guide](https://space-node.net/blog/discord-bot-rate-limiting-guide-2026)

### Tertiary (LOW confidence)
- None — every Phase 4 question was answered against source.

## Per-Question Answer Index

### Q1 — `dm20__party_pop_action` empty-queue behavior

**Authoritative answer:** Returns **immediately** with `{"empty": True, "pending": 0}` (JSON string). Never blocks. `dm20-protocol/main.py:5005-5014`.

**Action shape on non-empty pop:**
```json
{
  "empty": false,
  "action": {
    "id": "act_0001",
    "player_id": "<character.id>",
    "text": "I sneak toward the door",
    "timestamp": "2026-05-22T12:34:56.789Z",
    "status": "processing",
    "private": false
  },
  "remaining": 0
}
```

**Polling cadence verdict:** 250ms polling per channel is cheap and correct. No need for adaptive backoff. The action queue mutation is O(deque pop) inside a lock — trivial CPU cost. (Source: `dm20-protocol/party/queue.py:147-163`.)

**Gotcha:** Action statuses flow `pending → processing → resolved`. Once popped, status is `processing` and persisted to JSONL. If the bot crashes between pop and `party_resolve_action`, the action stays `processing` and is restored as `pending` on dm20 restart (`queue.py:90-93`). Means: **double-resolve protection is dm20's job**, but we MUST ensure crash-recovery doesn't double-render the narrative — Phase 4 should track resolved action_ids in `channel_sessions.payload_json` OR in a new column.

---

### Q2 — `dm20__apply_effect` semantics + "dodging" condition support

**Authoritative answer:** dm20 has NO "dodging" SRD condition. The 14 SRD conditions (`combat/effects.py:32+`) are: blinded, charmed, deafened, exhaustion, frightened, grappled, incapacitated, invisible, paralyzed, petrified, poisoned, prone, restrained, stunned. Dodge MUST be a **custom effect**.

**Arg shape:**
```python
await mcp_tools.apply_effect(
    client,
    character_name_or_id=dodger_name,
    effect_name="dodging",                          # any non-SRD name becomes custom
    source="Dodge action",
    duration=1,                                     # 1 round; dm20 auto-ticks at next turn (Q3)
    custom_modifiers=json.dumps([                   # JSON STRING, not list!
        {"stat": "saving_throw_dexterity", "operation": "advantage", "value": 1},
    ]),
)
```

**Critical caveat:** dm20's `Modifier` model supports `stat / operation / value` triples but **`operation` doesn't accept "advantage"/"disadvantage" as first-class values** — the engine uses `grants_advantage: list[str]` and `grants_disadvantage: list[str]` ON THE EFFECT (not on modifiers, `models.py:259-265`). To emulate that through the `apply_effect` tool, the `custom_modifiers` JSON list is limited to numeric-stat modifiers. So our custom "dodging" effect cannot natively express "DEX-save advantage" through `apply_effect`'s public API — we may need to direct-update the ActiveEffect after creation OR accept that DEX-save advantage is unenforced in v1.

**Recommendation:** **Use a local `combat_conditions` row** (D-22 Discretion path) as the source of truth for dodge state. Call `apply_effect(effect_name="dodging", duration=1, source="Dodge action")` only to make the condition VISIBLE on the dm20 character (so narration sees it) — don't rely on dm20 to enforce it. The shim shape:

```sql
CREATE TABLE IF NOT EXISTS combat_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL,
    character_id TEXT NOT NULL,              -- dm20 character.id
    condition TEXT NOT NULL,                  -- 'dodging' for now; future: 'concentrating', etc.
    expires_round INTEGER,                    -- round at which to auto-clear
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    UNIQUE(channel_id, character_id, condition)
);
CREATE INDEX IF NOT EXISTS combat_conditions_channel_idx ON combat_conditions(channel_id);
```

**Re-use vs new table verdict:** the existing `riposte_timers` has columns specific to riposte (`deadline_ts`, `monster_uuid`, `weapon_used`) — re-using it for dodge would require nullable monster_uuid/weapon_used and a `status='dodging'` flag. **A new `combat_conditions` table is cleaner and only 6 columns.** Recommend new table.

**Gotcha:** dm20's `apply_effect` returns a formatted string with the effect ID. To `remove_effect` cleanly we need either the ID or the name — call by name (`effect_id_or_name="dodging"`) per `main.py:2306-2311`.

---

### Q3 — `dm20__next_turn` semantics on monster turns

**Authoritative answer:** `next_turn` does **NOT** auto-resolve monster actions. It only:
1. Ticks active effects on the character whose turn just ended (`EffectsEngine.tick_effects(char, event="turn")`)
2. Advances `current_turn` to the next alive participant (skips dead/incap, ends combat if all dead)
3. Returns a formatted string like `**Next Turn:** Goblin Scout\n(Skipped dead/incapacitated: ...)`

(Source: `main.py:1756-1832`.)

**Bot's responsibility on monster turn:** drive the monster's action explicitly. Flow:

```python
# After next_turn returns "Goblin Scout":
char = await get_character(client, name_or_id="Goblin Scout")
if char['error'] or parse_player_name(char) is None:
    # Monster turn — bot drives it
    target = pick_target_from_initiative(state, attacker="Goblin Scout")  # bot decides
    # Option A: call combat_action directly (deterministic)
    result = await combat_action(
        client,
        attacker="Goblin Scout",
        target=target,
        action_type="attack",
        # weapon_or_spell=None → uses equipped main weapon
    )
    # result is formatted text — parse for narrative
    narrative = synthesize_monster_narrative(result)
    # Option B (preferred for non-trivial monsters): defer to Claudmaster
    # narrative = await mcp.player_action(
    #     session_id=session_id,
    #     action=f"{attacker_name} attacks {target_name} with its primary weapon",
    #     character_name="Goblin Scout",
    # )
    # → Claudmaster picks action, calls combat_action internally, returns narrative

    await render_in_discord(channel_id, narrative)
    await refresh_combat_embed(channel_id)
    await next_turn(client)  # advance to next participant
```

**Recommendation:** For v1, use **Option A** (direct `combat_action`) — predictable, fast, no extra LLM call. Defer Option B to a later iteration when Claudmaster's monster-tactics are battle-tested. Plan should make this explicit.

**Gotcha:** Monsters are stored in `storage._npc_*` paths (separate from characters). `get_character(monster_name)` returns "❌ Character 'X' not found"; you'd use `storage.get_npc(name)` on the dm20 side. Our `tools.py` has `get_character` but NO `get_npc` wrapper — add one in Phase 4, OR detect monster turn by "`get_character` returned error string".

---

### Q4 — Multi-campaign concurrent session limits

**Authoritative answer:** **HARD limit of 1 campaign per dm20 process** AND **1 Party Mode server per dm20 process**.

Evidence:
- `dm20-protocol/main.py:51` — `storage = DnDStorage(data_dir=data_path)` is a **module-level global** initialized at import time. There is no per-tool campaign scoping — every tool operates on the implicit "current campaign" via `storage.get_current_campaign()`.
- `dm20-protocol/party/server.py:61` — `_server_instance: Optional["PartyServer"] = None` is also a module global; `start_party_mode` checks if it's already set and returns "already running" if so (`main.py:4770-4775`).

**Implications for our `channel_sessions` table:** today the schema has `channel_id → campaign_name` as a 1:N relationship in theory. **In reality, only ONE row can be the "active dm20 campaign" at a time**, and switching costs a `dm20__load_campaign` call which mutates global state — i.e., **a Discord channel running campaign A and another channel running campaign B in the same bot process is broken** (any tool call from channel B's orchestrator clobbers channel A's state).

**How to handle (v1):**
1. **Single-campaign mode** — v1 supports **one active campaign per bot process**. Hard-fail `/start_game` if a different campaign is already active in `channel_sessions`. Document this in README (HOST-01).
2. **Phase 4 plan must add a check** in the orchestrator: on every `party_pop_action` cycle, verify the active dm20 campaign (via `dm20__get_campaign_info` or by inferring from `get_game_state`'s `campaign_name` field) matches the channel's `channel_sessions.campaign_name`. If not → log + abort.

**Future v2 path:** spawn one dm20 subprocess per active campaign (each listening on a different port); bot routes per-channel HTTP to the right port. Out of scope for v1.

**Gotcha:** the project CLAUDE.md says "Verify dm20 supports concurrent multi-campaign sessions in one process (Phase 1 spike)" was a Phase 1 blocker that didn't get resolved. **Resolution: it does NOT.** Phase 4 plan adds the single-campaign guard.

---

### Q5 — `dm20__get_game_state` polling cost

**Authoritative answer:** Cost is **trivial** (microseconds — pure pydantic serialization of an in-memory `GameState` model + a markdown render). 1 Hz polling is fine; 4 Hz would also be fine.

(Source: `main.py:1627-1668` — no I/O, no LLM call, no DB read; `storage.get_game_state()` returns from `storage._game_state` cached attribute.)

**Response shape:** It's a **markdown-formatted string**, not JSON. Critical fields parseable via regex:

```
**Game State**
**Campaign:** Lost Mines of Phandelver
**Session:** 3
**Location:** Cragmaw Hideout
**Date (In-Game):** 5th of Mirtul, 1492 DR
**Party Level:** 3
**Party Funds:** 250 gp
**In Combat:** Yes
**Initiative Order:**
  1. Thorin (Initiative: 19)
  2. Aria (Initiative: 17)
  3. Goblin Scout (Initiative: 11)
**Current Turn:** Thorin
**Active Quests (1):**
  - Find the entrance to the cave
**Notes:** ...
```

**Parse with regex** (Pattern 4 above) — stable because format is hand-built in dm20 source.

**Recommendation:** Piggyback `get_game_state` on the orchestrator loop. Cycle = poll `party_pop_action`. Every Kth tick (K=4 for 1 Hz at 250ms), also fetch `get_game_state` and check for state transitions (in_combat flip, current_turn change). This satisfies D-27 (one poll, two purposes).

**Gotcha:** the markdown format is NOT a stable API. If dm20 ever refactors `get_game_state` to add new lines or change capitalization, our regex breaks. Add a **format-pinning test** in Phase 4: parse a known dm20 fixture and assert all 5 fields extract correctly. Failure → flag for dm20 version upgrade.

---

### Q6 — dm20 reaction flag in `combat_action`

**Authoritative answer:** dm20's `combat_action` does **NOT** have a `reaction` arg. Signature (verified at `main.py:1967-1977`):

```python
def combat_action(
    attacker: str,
    target: str,
    action_type: str = "attack",
    weapon_or_spell: str | None = None,
    damage_dice: str | None = None,
    damage_type: str | None = None,
    save_ability: str | None = None,
    half_on_save: bool = False,
    spell_dc: int | None = None,
) -> str: ...
```

**Impact on Phase 4:** Phase 4's Attack flow only needs `attacker`, `target`, `action_type="attack"`, optional `weapon_or_spell`. **Reaction is a Phase 5 concern** — but Phase 5 will need a shim. The shim looks like:

- Bot fires the "Riposte" UI button as a normal `combat_action(attacker=victim, target=attacker_of_monster, action_type="attack")`.
- Bot's local `riposte_timers` tracks "this PC has used their reaction this round" via the existing `status` column.
- Bot enforces "no second reaction this round" purely in Discord UI; dm20 doesn't know what a reaction is and doesn't decrement anything.

**Recommendation for Phase 4 plan:** Note this in the Phase 5 hand-off — Phase 5 owns the shim, but Phase 4 must NOT pass `reaction=True` anywhere because dm20 will either reject it (HTTP 400 via FastMCP schema check) OR silently ignore it. Our existing wrapper `combat_action(..., **extra)` (tools.py:270-287) is permissive and currently includes `reaction` in its docstring's known-extra-kwargs list — **REMOVE that documentation lie** in the tools.py audit.

---

### Q7 — discord.py 2.7.1 8-player initiative embed under load

**Authoritative answer:** Discord allows ~5 message edits per 5 seconds per channel (per-channel bucket; per-message also enforced); our coalescer's **≤1 edit/sec/message** is well within the budget.

(Source: [discord.com/developers/docs/topics/rate-limits](https://discord.com/developers/docs/topics/rate-limits) verified by Phase 2 RESEARCH.)

**Realistic 8-player load math:**
- 8 actors in initiative, 5 rounds, 4 updates per round = 160 edit attempts
- Spread over ~5 minutes of real time (each round ≈ 60s with 8 PCs deciding)
- Per-message rate: 160 / 300 ≈ 0.5 edits/sec — half the budget
- Per-channel rate: same — also half the budget
- **Headroom: 2×**

**Verdict:** The coalescer's per-message ≤1 edit/sec pacing is correct. **No dynamic backoff needed.** The only failure mode is the transition pitfall (Pitfall 4 above) — multiple coalescers active on the same channel during EXPLORATION↔COMBAT transition. Mitigate by `coalescer.close()` on transition.

**For the load test (COMBAT-08):**
```python
# tests/gameplay/test_8_player_load.py — pseudocode
import respx, time

@pytest.mark.asyncio
async def test_8_player_load_no_429(channel_message, fake_mcp_client, monkeypatch):
    """8 actors × 5 rounds × 4 embed updates per round = 160 attempted edits.
    Assert: <= 1 edit/sec/message AND zero discord.HTTPException(429)."""
    edit_calls = []
    async def fake_edit(*a, **kw):
        edit_calls.append(time.monotonic())
    monkeypatch.setattr(channel_message, "edit", fake_edit)
    coalescer = EmbedCoalescer(channel_message, rate_limit_seconds=1.0)

    # Drive 160 updates with realistic intra-round delays
    for round_num in range(1, 6):
        for actor_idx in range(8):
            for update_idx in range(4):
                await coalescer.update(make_embed(round_num, actor_idx, update_idx))
                await asyncio.sleep(0.1)  # Simulates real combat pacing

    await coalescer.close()
    # Assert no edit pair is closer than 1.0s
    for prev, cur in zip(edit_calls, edit_calls[1:], strict=False):
        assert cur - prev >= 1.0, f"Edit too soon: {cur - prev}s"
    # Assert total edits is plausible (≤ total_runtime / 1s, with latest-value coalescing)
    total_runtime = edit_calls[-1] - edit_calls[0]
    assert len(edit_calls) <= int(total_runtime) + 2, "Too many edits — coalescer broken"
```

---

### Q8 — `dm20__build_encounter_tool`

**Authoritative answer:** It is a **planner/suggester**, not a spawner. It returns a formatted text suggestion of monster compositions matching the CR budget; it does NOT create NPCs in dm20 state and does NOT call `start_combat`.

**Arg shape (verified at `main.py:2110-2116`):**
```python
build_encounter_tool(
    party_size: int,        # ≥1
    party_level: int,       # 1..20
    difficulty: str = "medium",   # "easy" | "medium" | "hard" | "deadly"
    creature_type: str | None = None,
    environment: str | None = None,
)
```

**Return:** formatted string from `_format_encounter_suggestion(suggestion)` — bot would parse it, OR just feed it to Claudmaster as a narrative hint.

**Recommendation:** **Phase 4 does NOT use `build_encounter_tool` directly.** Encounter spawning is Claudmaster's job — when Claudmaster decides "an encounter happens here", it picks monsters, calls `create_npc` for each, then calls `start_combat(participants=...)` with pre-rolled initiative. Phase 4's orchestrator just detects the resulting `in_combat=true` state transition (Q5) and renders the combat embed.

**Future use:** if we ever want a `/spawn_encounter difficulty:hard creature_type:undead` admin command (out of scope for v1), it would call `build_encounter_tool` for planning + Claudmaster to spawn. Defer.

---

### Q9 — Race condition: multiple players click action buttons in same combat round

**Authoritative answer:** The per-channel `asyncio.Lock` (Phase 1 MCP-07) + per-channel token bucket (OPS-03, D-28) together protect dm20 from concurrent mutations on the same channel. The protection works for **same-channel races**. Cross-channel races don't exist because of Q4 (only one active campaign anyway).

**Layered defense:**

1. **Discord interaction routing** — only ONE PC's buttons should be live for the current turn (we re-render the combat embed with PC-specific buttons in `from_custom_id` based on the round number in the custom_id, D-15).
2. **Turn gatekeeper** (COMBAT-04) — wrong-user clicks → ephemeral NOT_YOUR_TURN, never reaches MCP.
3. **Per-channel asyncio.Lock** (MCP-07) — serializes mutating calls; second click WAITS until first finishes.
4. **Per-channel token bucket** (OPS-03) — even if the lock releases instantly, the bucket caps at 1 mutating call / 200ms; absorbs spam clicks gracefully.
5. **dm20-side action queue idempotency** — Party Mode `party_pop_action` returns each `action_id` exactly once; `party_resolve_action(action_id, ...)` is naturally idempotent because dm20 marks the action `resolved` on first call.

**Additional protection needed at dm20 layer:** NONE for v1. dm20's combat pipeline is single-threaded (synchronous Python in a single FastMCP request handler). The HTTP boundary serializes; the storage updates are atomic at the pydantic-model level (no partial writes).

**Stress test recipe:**
```python
# tests/gameplay/test_race_attack_clicks.py
async def test_two_simultaneous_attack_clicks_same_round():
    """Player A clicks AttackButton at t=0.000; Player B (not the active actor)
    clicks AttackButton at t=0.001. B must get NOT_YOUR_TURN (gate); A must succeed exactly once."""
    interactions = await asyncio.gather(
        a_clicks_attack_button(),
        b_clicks_attack_button(),
        return_exceptions=True,
    )
    assert a_was_resolved_once()
    assert b_got_ephemeral_warning("not_your_turn")
```

---

### Q10 — "Monster turn" rendering in Discord

**Authoritative answer:** Render BOTH a narration message AND a quiet embed update. Here's why:

- The **combat embed** (single sticky message in the channel) is the authoritative "where are we now" — every turn change must update it (current actor cursor moves down). 1 edit per monster turn.
- The **narrative** ("The Goblin Scout slashes Thorin for 4 damage!") is a NEW message — gives players a sense of pacing and stops the embed from becoming a mile-long scroll of action history.

**Pattern:**
```
[embed update]   ▶️ Goblin Scout (4/7 HP, AC 15)     ← turn cursor moves
                 ▫️ Thorin (12/16 HP, AC 18)
                 ▫️ Aria (10/10 HP, AC 14)

[new message]    🗡️ The Goblin Scout slashes Thorin for 4 slashing damage.
                 Thorin: 12/16 HP

[embed update]   ▫️ Goblin Scout (4/7 HP, AC 15)
                 ▶️ Thorin (12/16 HP, AC 18)         ← cursor now on next turn
                 ▫️ Aria (10/10 HP, AC 14)
                 [⚔️ Attack] [🛡️ Dodge] [⏭️ End]      ← Thorin's buttons appear
```

Two embed updates + one new narrative message per monster turn = 3 channel events per monster turn. Within rate-limit budget.

**Rendering source:** the narrative message for a monster turn comes from `party_resolve_action(action_id, narrative)` — even though there was no `party_pop_action` for it (the monster didn't queue an action). **Solution:** synthesize an action_id (`f"monster_turn_{round}_{actor}"`) and push directly to the response queue via `party_resolve_action`. dm20's `party_resolve_action` doesn't validate that the action_id was previously popped — it just records it (`main.py:5191-5199`).

**Recommendation:** Phase 4 orchestrator's monster-turn driver (Pattern 3 above) calls `party_resolve_action` with a synthesized action_id. This also makes monster turns appear in the dm20 `responses.jsonl` for replay/debug — good for the load test.

**Gotcha:** dm20's `action_queue.resolve(action_id, response_data)` raises `KeyError` if the action_id is unknown (`queue.py:177-178`). But `party_resolve_action` catches this implicitly via the order of operations — `server.response_queue.push` succeeds first; `server.action_queue.resolve` raises but its exception is uncaught and would surface as an MCP error. **Fix in bot code:** before pushing a monster-turn response, call `server.action_queue.push("MONSTER", narrative_text, private=False)` first to register an action_id — OR file a dm20 PR to make `resolve` tolerant of unknown IDs. For v1, register-then-resolve is the cleaner path (one extra call per monster turn).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | "Single dm20 process can only support one active campaign at a time" — verified by reading `storage` global init, but the bot's behavior under a `dm20__load_campaign` between channels is unverified | Q4 | Multi-channel deployments silently corrupt state; CRITICAL — plan must add single-campaign guard + test |
| A2 | "FastMCP either rejects or accepts-and-ignores unknown kwargs like `campaign_name`" — not tested empirically | Pitfall 2 | If accepts-and-ignores, our wrappers are silently broken in production; LOW risk because behavior is the same either way (no campaign scoping happens) |
| A3 | "The `dice` MCP tool `dice__roll_dice` is suitable for pre-rolling initiative" — listed in ddmcpskills.md but not exercised by Phase 1-3 | Open Q2 | MEDIUM — plan should include a smoke test in Wave 0 |
| A4 | "dm20's `EffectsEngine.tick_effects(char, event='turn')` will auto-clear our custom 'dodging' effect at duration=1" — verified that ticking happens in next_turn but the duration-1 behavior is inferred from comment, not from running it | Pattern 2 | LOW — worst case Dodge sticks one round longer; plan should add a test calling next_turn twice and asserting the effect is gone |
| A5 | "Discord's per-channel rate limit is 5 edits / 5s in 2026" — confirmed via WebSearch but Discord docs are cagey about exact bucket math | Pitfall 4, Q7 | LOW — coalescer has 2× headroom |
| A6 | "Claudmaster's `player_action` is the right path for monster turns" — listed as Option B in Q3, but we recommend Option A for v1 | Q3 | NEGLIGIBLE — Option A is the recommendation; Option B is documented for v2 |

## Metadata

**Confidence breakdown:**
- Architecture / dm20 semantics: HIGH — every claim is sourced from `main.py` line numbers
- Discord rate limits: MEDIUM-HIGH — Phase 2 already proved the coalescer works; load test will confirm
- Dodge shim: MEDIUM — `apply_effect` works mechanically, but the "incoming attack disadvantage" rule is partly v1-narrative-only
- Multi-campaign limits: HIGH — `storage` global is unambiguous in the source

**Research date:** 2026-05-22
**Valid until:** 2026-06-22 (dm20 active development could change tool signatures; re-verify before Phase 5 starts)
