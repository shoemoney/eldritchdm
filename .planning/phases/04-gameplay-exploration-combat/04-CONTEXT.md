# Phase 4: Gameplay — Exploration + Combat (Party Mode) - Context

**Gathered:** 2026-05-21
**Status:** Ready for research + planning (prepped in advance while Phase 3 ships)
**Mode:** Synthesized from REQUIREMENTS (EXPLORE-01..07, COMBAT-01..08, COMBAT-12, OPS-03) + Phase 1-3 deliverables + ddmcpskills.md (dm20 party-mode + combat tools)

<domain>
## Phase Boundary

The actual game. After this phase, a Discord channel with a started session and loaded characters is fully playable end-to-end through the **exploration → encounter trigger → combat → next round** loop. ShoeGPT narrates via dm20's Party Mode queue; the bot enforces turn order by Discord `user_id`; the 8-player Discord load test passes with zero `429 Too Many Requests`.

**In scope:**
1. **Party Mode bind** — bot polls/subscribes to `dm20__party_pop_action`, drives the `party_thinking → party_get_prefetch → party_resolve_action` cycle, renders narratives in Discord
2. **EXPLORATION embed + declare-action modal** — players type their intent (≤500 chars), sanitizer strips control tokens, action is queued as a `dm20__player_action`
3. **Action batching** — when multiple players submit within a 30s window, narratives coalesce into one batched response
4. **Combat trigger** — bot detects dm20 state transition to COMBAT via `get_game_state` polling and renders the combat embed
5. **Combat embed** — turn order, HP/AC, conditions, supports 8+ initiative rows, refreshed via the Phase 2 EmbedCoalescer
6. **Turn gatekeeping** — Discord `user_id` of the clicker must match the actor whose turn it is; mismatch → ephemeral `❌ Not your turn`
7. **Attack flow** — `[⚔️ Attack]` button → weapon select modal → `dm20__combat_action(action="attack", weapon=..., target=...)` → narrative back via party mode
8. **Dodge** — `[🛡️ Dodge]` → `dm20__apply_effect(target=self, effect="dodging")` (or documented shim) → ends turn
9. **End Turn** — `[⏭️ End Turn]` → `dm20__next_turn`
10. **Combat end** — bot detects dm20 state transition out of COMBAT and returns to EXPLORATION embed
11. **OPS-03** — per-channel rate limit on mutating MCP calls: max 1 per 200ms (token bucket)

**NOT in scope:**
- Riposte and other reactions (Phase 5)
- `Cast Spell` button beyond a stub (full spell flow — slot tracking, concentration — is v2)
- Action-batch UX beyond the 30s window mechanic (smarter "first to submit triggers, others get private response" — v2)
- Combat narration prefetch optimization beyond `party_get_prefetch` happy path

</domain>

<decisions>
## Implementation Decisions

### New cogs and modules
- **D-01:** Two new cogs:
  - `src/eldritch_dm/bot/cogs/exploration.py` — EXPLORATION state handler: room embed lifecycle, declare-action button callback, modal submit handler, action-batching coordinator, encounter-trigger watcher
  - `src/eldritch_dm/bot/cogs/combat.py` — COMBAT state handler: combat embed lifecycle, action buttons (Attack / Dodge / End Turn / Cast Spell stub), turn gatekeeping, weapon select modal, combat-end watcher
- **D-02:** Cogs share a `PartyModeOrchestrator` module living at `src/eldritch_dm/gameplay/party_mode.py`. Holds the per-channel pop/resolve loop. One orchestrator per active EXPLORATION/COMBAT channel; lifecycle managed by `setup_hook` + state transitions.

### Party Mode pop/resolve loop
- **D-03:** Architecture:
  ```
  PartyModeOrchestrator (per-channel task):
    while session_state in {EXPLORATION, COMBAT, ...}:
        action = await mcp.party_pop_action(session_id)
        if action.is_empty:
            await asyncio.sleep(PARTY_POLL_INTERVAL_MS / 1000)
            continue
        await mcp.party_thinking(session_id, message="ShoeGPT consults the ancient scrolls…")
        if action.is_combat_turn:
            prefetch = await mcp.party_get_prefetch(turn_id, outcome, roll, damage, target_hp)
        narrative = await claudmaster_resolve(session_id, action)
        await mcp.party_resolve_action(action_id, narrative, private_messages=..., dm_notes=...)
        await render_in_discord(narrative)
  ```
- **D-04:** `PARTY_POLL_INTERVAL_MS` env var (already documented in `.env.example`, default 250). Polling, not WebSocket — Party Mode is HTTP-only per dm20 docs.
- **D-05:** One orchestrator task per channel. Lifecycle:
  - Started by `/start_game` lobby transition to EXPLORATION (Phase 3 may need a hook here — verify in Phase 3 SUMMARY)
  - Started by `setup_hook` for every `channel_sessions` row whose `state != 'LOBBY'` (restart survival)
  - Cancelled by `dm20__end_combat` + transition out of COMBAT to LOBBY (out of scope for v1 — assume "campaign always running until /end_game"; v2 may add explicit end)
- **D-06:** Orchestrator-to-Discord renderer: takes the `(narrative, action_metadata)` tuple, looks up the active embed message for the channel via `persistent_views` (or in-memory `ChannelMessageMap`), calls the right coalescer to update.

### Action batching (EXPLORE-06)
- **D-07:** Batching coordinator inside the exploration cog. Per-channel state:
  ```python
  @dataclass
  class ExplorationBatch:
      first_submission_ts: datetime
      submissions: list[PlayerIntent]  # PlayerIntent { user_id, sanitized_action, ts }
      deadline_ts: datetime  # = first_submission_ts + 30s
  ```
- **D-08:** Flow:
  1. Player clicks `[ 💬 Declare Action ]` → modal opens
  2. Submit → sanitizer runs → if no batch in progress, start one with deadline = now + 30s
  3. Else add to existing batch
  4. If `len(submissions) == active_party_size` OR `deadline_ts` reached → flush: post all sanitized intents to dm20 as ONE party_action with a structured payload like `<batch><player_action ...>…</player_action><player_action ...>…</player_action></batch>`
  5. Wait for ShoeGPT narrative via party_resolve_action → render in Discord
- **D-09:** Active party size = count of characters in the campaign with a player_id set, per `dm20__list_characters`. Cached per-channel; invalidated on character add/remove (Phase 3's responsibility to notify).
- **D-10:** If a player submits after the batch flushes, the next batch starts with their submission.

### Combat embed
- **D-11:** `combat_embed(initiative, current_actor, hp_table, conditions_table, round_number) -> discord.Embed` — Phase 2 already has the renderer signature; Phase 4 populates dynamic content.
- **D-12:** Refresh strategy: on every dm20 state change (after `combat_action`, `next_turn`, `apply_effect`, etc.), pull `dm20__get_game_state` and re-render via the per-message coalescer.
- **D-13:** 8+ initiative rows: layout is a single `discord.Embed` field per actor (no inline split). Field title format: `{turn_marker}{actor_name} ({hp}/{max_hp} HP, AC {ac})`. Max embed fields = 25, so 8 actors fits comfortably with room for conditions.
- **D-14:** Turn marker uses `▶️` for current actor, `▫️` for others.

### Action buttons + turn gatekeeping
- **D-15:** Action buttons rendered via `DynamicItem` subclasses (extending the Phase 2 set):
  - `AttackButton` — custom_id `attack:(?P<channel_id>\d+):(?P<actor_id>\d+):(?P<round>\d+)` — actor_id is the dm20 character.id (uuid), the round is for cache-busting (different round = different button instance)
  - `DodgeButton` — `dodge:(?P<channel_id>\d+):(?P<actor_id>\d+):(?P<round>\d+)`
  - `EndTurnButton` — already exists (Phase 2 stub); promote callback to real
  - `CastSpellButton` — stub for v1 ("Spellcasting coming soon" ephemeral); real impl is v2
- **D-16:** Turn gatekeeper check: `interaction.user.id` matched against `current_actor.player_id` (mapped via `dm20__get_character`). On mismatch → `send_warning(interaction, WarningKind.NOT_YOUR_TURN, actor_name=...)`.
- **D-17:** Actions on monster turns (where dm20 controls the actor, no PC has `player_id` = the actor's id): bot fast-forwards via dm20 — calls `combat_action(action="monster_default")` or similar (depending on dm20's auto-combat API). No Discord buttons for monster turns; the embed shows narrative-only.

### Attack flow
- **D-18:** Click `[⚔️ Attack]` → defer-first → open WeaponSelectModal: dropdown of `dm20__get_character.weapons` (or text input if dm20 doesn't expose weapons cleanly — verify) + dropdown of valid targets from `dm20__get_game_state.combatants`
- **D-19:** Modal submit → `dm20__combat_action(action="attack", weapon=..., target=...)` → response is the mechanical outcome (hit/miss/damage)
- **D-20:** Bot enqueues `party_action` for narrative: "Attack resolved: {attacker} {weapon} {target} → {outcome}: {damage_or_miss}. Narrate."
- **D-21:** ShoeGPT narrative comes back via party_resolve_action → rendered in Discord (new message OR coalesced edit, depending on Phase 2 coalescer behavior — verify D-30 from Phase 2 CONTEXT)

### Dodge
- **D-22:** Click `[🛡️ Dodge]` → defer → `dm20__apply_effect(target_id=current_actor.id, effect="dodging")` (verify exact field — `effect_name`?). If dm20 doesn't have a built-in "dodging" condition, shim:
  - Use `apply_effect(target_id=..., effect_name="custom:dodging", custom_data={...})`
  - Set local marker in `riposte_timers` (re-use the table — it has `character_id` + `status` columns we can repurpose for "active dodge")
  - Phase 4 RESEARCH must verify this — if shim is needed, document precisely in the plan
- **D-23:** Dodge ends turn immediately: chain into `dm20__next_turn` after `apply_effect` succeeds
- **D-24:** Dodge auto-clears on dodger's next turn start (Phase 1 Engine spec — but engine is dm20, so check if dm20 clears it automatically or we need to). Probably automatic in dm20; verify.

### Combat trigger detection
- **D-25:** A watcher task polls `dm20__get_game_state(session_id)` every 1s while in EXPLORATION. When `game_state.combat_active == true` OR `state == 'COMBAT'` → switch the channel's UI to combat mode (post a new combat_embed message, register it in persistent_views, kill the exploration message OR keep it as scrollback).
- **D-26:** Symmetric watcher in COMBAT for the transition back to EXPLORATION.
- **D-27:** Watcher is part of PartyModeOrchestrator (same task) — minor optimization: piggyback on each `party_pop_action` cycle so we don't have two polls per channel.

### Rate limiting (OPS-03)
- **D-28:** Token bucket per channel: max 1 mutating MCP call per 200ms. Lives in `src/eldritch_dm/mcp/rate_limit.py`. The Phase 1 per-channel `asyncio.Lock` doesn't rate-limit, just serializes; this is additive.
- **D-29:** "Mutating" = any MCP call except `get_*`, `list_*`, `search_*`, `validate_*`. Wrapper functions in `mcp/tools.py` are tagged via decorator: `@mutating` vs `@read_only`.
- **D-30:** On rate-limit hit, the wrapper awaits the bucket — does NOT raise. UX-side: if the player is hammering buttons, they'll feel slight back-pressure (~200ms) but the bot never says "rate limited."

### Testing
- **D-31:** Mocked PartyModeOrchestrator loop — use respx + manufactured pop/resolve responses; verify the full pop→thinking→prefetch→resolve sequence is dispatched exactly once per action.
- **D-32:** Action-batching tests: 4 mock submissions across the deadline boundary, verify exactly one batched payload is sent to dm20.
- **D-33:** Turn-gatekeeper test: 8-actor synthetic combat, every actor's "Attack" button clicked by every other actor's user_id; assert ephemeral NOT_YOUR_TURN sent N×(N-1) times, accepted clicks exactly N times.
- **D-34:** **8-player Discord load test (COMBAT-08)** — single channel, 8 actors, 5 rounds, 4 embed updates per round = 160 edit attempts. Use respx to mock dm20; use a discord.HTTPClient mock + assertion to confirm the coalescer never violates the 1 edit/sec/message limit. Counted via mock call count + timestamps.
- **D-35:** Restart-mid-combat drill (BOT-08 extension): seed `channel_sessions.state = 'COMBAT'`, kill orchestrator, restart bot, verify orchestrator resumes from `get_game_state` and the active turn buttons still dispatch.

### Logging
- **D-36:** Bind context per action: `channel_id`, `session_id`, `actor_id`, `actor_name`, `action_kind`, `round_number`, `turn_idx`. Log entry on every pop_action, party_thinking, party_get_prefetch, party_resolve_action, combat_action, next_turn, apply_effect.

### Claude's Discretion
- Exact polling cadence inside `PartyModeOrchestrator` (250ms is the env default; tune in plan if MEM/CPU shows issues)
- Whether `riposte_timers` table is re-used for dodge state or we add a tiny new `combat_conditions` table (re-use is simpler; new table is cleaner; lean re-use)
- Whether the orchestrator task is one-per-channel asyncio.Task or one-per-process worker with a queue (per-channel task is simpler; per-process worker is more efficient at scale — go per-channel for v1)
- Cast Spell button copy + ephemeral message ("⚗️ Spellcasting is coming in v2. Use Attack with weapon='spell' for now"? Or just hide the button?)

</decisions>

<canonical_refs>
## Canonical References

### Phase scope
- `.planning/REQUIREMENTS.md` § Exploration (EXPLORE-01..07), § Combat (COMBAT-01..08, COMBAT-12), § Operational (OPS-03)
- `.planning/ROADMAP.md` § Phase 4 — goal + 6 success criteria

### Phase 1-3 deliverables (interfaces this phase consumes)
- `src/eldritch_dm/mcp/tools.py` — party-mode + combat wrappers: `party_pop_action`, `party_thinking`, `party_get_prefetch`, `party_resolve_action`, `start_combat`, `end_combat`, `next_turn`, `combat_action`, `apply_effect`, `remove_effect`, `get_game_state`, `get_character`, `list_characters`, `get_claudmaster_session_state`
- `src/eldritch_dm/mcp/health.py` — circuit breaker for graceful "DM offline" when oMLX is down
- `src/eldritch_dm/persistence/channel_sessions_repo.py` — read state, update state on transitions
- `src/eldritch_dm/persistence/persistent_views_repo.py` — register combat embed messages
- `src/eldritch_dm/persistence/riposte_timers_repo.py` — re-used for active dodge state (or new table per D-23)
- `src/eldritch_dm/safety/sanitizer.py` — sanitize every modal submit before LLM exposure
- `src/eldritch_dm/bot/embeds.py` — `room_embed`, `combat_embed` — populate dynamic content
- `src/eldritch_dm/bot/dynamic_items.py` — Phase 4 extends with `AttackButton`, `DodgeButton`, `CastSpellButton`; promotes `EndTurnButton` and `DeclareActionButton` stubs to real callbacks
- `src/eldritch_dm/bot/coalescer.py` — used for every combat embed edit
- `src/eldritch_dm/bot/warnings.py` — `NOT_YOUR_TURN`, `INVALID_ACTION`, `RATE_LIMITED`
- `src/eldritch_dm/bot/bot.py` — `setup_hook` cog loading + orchestrator-task lifecycle hooks

### MCP tool reference
- `ddmcpskills.md` § dm20 § Party Mode (`party_pop_action`, `party_thinking`, `party_get_prefetch`, `party_resolve_action`, `start_party_mode`, `stop_party_mode`, `get_party_status`)
- `ddmcpskills.md` § dm20 § Combat (`start_combat`, `end_combat`, `next_turn`, `combat_action`, `apply_effect`, `remove_effect`, `build_encounter_tool`)
- `ddmcpskills.md` § dm20 § Game state (`get_game_state`, `update_game_state`)
- `ddmcpskills.md` § dm20 § Claudmaster (`get_claudmaster_session_state`, `player_action`)

### External
- [discord.py 2.7.1 Modals + Select Menus](https://discordpy.readthedocs.io/en/v2.7.1/) — for weapon/target select inside attack flow
- [Discord API rate limits (2026)](https://discord.com/developers/docs/topics/rate-limits) — 5 edits / 5s per channel bucket (verified Phase 2 RESEARCH); inform OPS-03 + coalescer interaction

</canonical_refs>

<code_context>
## Existing Code Insights

### Phase 1-3 delivered (this phase composes from)
- 28 MCP wrappers, MCPClient with retry + circuit breaker, per-channel `asyncio.Lock` registry from Phase 1
- 4 DynamicItem subclasses (callbacks stubbed in Phase 2) — Phase 4 makes 3 of them real (`AttackButton` is new; `DeclareActionButton`, `EndTurnButton` get real callbacks)
- EmbedCoalescer (Phase 2 Plan 03) — Phase 4 is the heavy user
- `lobby_embed`, `room_embed`, `combat_embed`, `character_confirm_embed` renderers from Phase 2
- ChannelSessionRepo, PersistentViewRepo writes through WriterQueue
- sanitize_player_input — used on every modal submission
- `ChannelMessageMap` (assumed pattern; Phase 3 may introduce — verify in SUMMARY)

### Reusable Assets
- `Settings.party_mode_port`, `Settings.party_poll_interval_ms`, `Settings.embed_edit_rate_limit` — all already in env
- structlog context binding pattern

### New Modules This Phase Introduces
- `src/eldritch_dm/gameplay/` — module for `PartyModeOrchestrator`, batching coordinator. Update import-linter to allow `bot → gameplay → {mcp, persistence, safety}` but not the inverse.
- `src/eldritch_dm/mcp/rate_limit.py` — token bucket per channel
- `tests/gameplay/` — orchestrator tests, batching tests, load test

### Integration Points
- Phase 5 (Riposte) adds reactive UI **inside** the combat flow — when `combat_action(action="attack")` returns `outcome=miss` and target is eligible, surface a timed button. Phase 4 must emit a hook event the riposte system listens for.
- Phase 5 (Self-host) needs Phase 4's docs in the README — "what playing a session feels like end-to-end."

</code_context>

<specifics>
## Specific Ideas

- The **8-player load test is the most important deliverable in Phase 4**. Without it we cannot claim multiplayer correctness. Make it visible in CI output.
- Combat narration prefetch (`dm20__party_get_prefetch`) is a UX speed feature — if it works, players get instant narrative; if it misses cache we fall back to full generation. Don't make this a critical path — it's an optimization.
- Verify dm20's "monster turns" behavior empirically — does dm20 auto-resolve monster actions when we call `next_turn`, or do we need to drive each monster turn manually? Affects the orchestrator's behavior on non-PC turns.
- The dodge shim is the most uncertain part. If dm20 has a clean "dodging" condition, great; if not, we need a small in-bot effect table. Plan should call out which is correct after a 30-min spike.
- Combat embed updates 4× per round in the load test (start of turn, action result, effects applied, end of turn) — this is a high-flux UI. Coalescer must work; if it doesn't we see the embed flicker badly during play.

</specifics>

<deferred>
## Deferred Ideas

- Spellcasting beyond stub (slots, concentration, area effects) — v2
- Initiative reroll mid-combat — v2
- Player-DM private DMs from the AI (`dm20__send_private_message`) — v2
- Combat undo / rewind — v2 (would require dm20 to support state snapshots)
- Real-time spectator mode for non-party members — v2
- Voice channel announcements ("Thorin is up!") — v2

</deferred>

---

*Phase: 04-gameplay-exploration-combat*
*Context gathered: 2026-05-21 (prepped in advance during Phase 2 Plan 03 / Phase 3 research)*
