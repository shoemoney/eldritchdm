---
phase: 04-gameplay-exploration-combat
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eldritch_dm/gameplay/__init__.py
  - src/eldritch_dm/gameplay/party_mode.py
  - src/eldritch_dm/gameplay/exploration_batch.py
  - src/eldritch_dm/mcp/rate_limit.py
  - src/eldritch_dm/bot/cogs/exploration.py
  - src/eldritch_dm/bot/dynamic_items.py
  - src/eldritch_dm/bot/coalescer.py
  - src/eldritch_dm/bot/bot.py
  - pyproject.toml
  - tests/gameplay/__init__.py
  - tests/gameplay/test_party_mode.py
  - tests/gameplay/test_exploration_batch.py
  - tests/gameplay/test_rate_limit.py
  - tests/bot/cogs/test_exploration_cog.py
  - tests/bot/test_dynamic_items_declare_real.py
autonomous: true
requirements:
  - EXPLORE-01
  - EXPLORE-02
  - EXPLORE-03
  - EXPLORE-04
  - EXPLORE-05
  - EXPLORE-06
  - EXPLORE-07
  - OPS-03
tags: [gameplay, exploration, party-mode, batching, rate-limit]

must_haves:
  truths:
    - "A new module `eldritch_dm.gameplay` exists and is allowed by import-linter (bot may import it; it may import mcp/persistence/safety)"
    - "PartyModeOrchestrator runs one asyncio.Task per active EXPLORATION/COMBAT channel and drives pop → thinking → (optional prefetch) → resolve"
    - "A player clicking [💬 Declare Action] opens a modal, the submission is sanitized and enqueued into the per-channel ExplorationBatch"
    - "When 4 players submit within the 30s window, exactly one batched payload is sent to dm20 via party_action / party_resolve_action"
    - "A 5th submission after batch flush starts a new batch (does not lose the action)"
    - "Mutating MCP calls go through a per-channel token bucket that ratelimits to ≤1 per 200ms; reads (get_*/list_*/search_*) bypass it"
    - "Exploration cog detects dm20 transition to COMBAT (game_state.combat_active true OR state == 'COMBAT') and signals the orchestrator to swap UI"
    - "Orchestrator lifecycle wires into EldritchBot.setup_hook (start tasks for every non-LOBBY channel_sessions row on boot)"
  artifacts:
    - path: "src/eldritch_dm/gameplay/__init__.py"
      provides: "Package marker for the new gameplay layer"
    - path: "src/eldritch_dm/gameplay/party_mode.py"
      provides: "PartyModeOrchestrator class + start_orchestrator_for_channel / stop_orchestrator_for_channel"
      contains: "class PartyModeOrchestrator"
    - path: "src/eldritch_dm/gameplay/exploration_batch.py"
      provides: "ExplorationBatch dataclass + BatchCoordinator (per-channel state machine, 30s window, party-size flush)"
      contains: "class ExplorationBatch"
    - path: "src/eldritch_dm/mcp/rate_limit.py"
      provides: "Per-channel token-bucket rate limiter for mutating MCP calls"
      contains: "class ChannelRateLimiter"
    - path: "src/eldritch_dm/bot/cogs/exploration.py"
      provides: "ExplorationCog (room_embed lifecycle, declare-action callback, batch coordinator wiring)"
      contains: "class ExplorationCog"
  key_links:
    - from: "src/eldritch_dm/bot/dynamic_items.py"
      to: "src/eldritch_dm/gameplay/party_mode.py"
      via: "DeclareActionButton.callback opens DeclareActionModal whose on_submit pushes a PlayerIntent into BatchCoordinator"
      pattern: "DeclareActionModal|BatchCoordinator\\.submit"
    - from: "src/eldritch_dm/gameplay/party_mode.py"
      to: "src/eldritch_dm/mcp/tools.py"
      via: "party_pop_action / party_thinking / party_get_prefetch / party_resolve_action wrappers"
      pattern: "party_pop_action|party_resolve_action"
    - from: "src/eldritch_dm/gameplay/party_mode.py"
      to: "src/eldritch_dm/mcp/rate_limit.py"
      via: "Mutating MCP calls awaited through ChannelRateLimiter"
      pattern: "rate_limit|ChannelRateLimiter"
    - from: "src/eldritch_dm/bot/bot.py"
      to: "src/eldritch_dm/gameplay/party_mode.py"
      via: "setup_hook starts an orchestrator task for every channel_sessions row whose state in {EXPLORATION, COMBAT}"
      pattern: "PartyModeOrchestrator|start_orchestrator_for_channel"
---

<objective>
Stand up the `eldritch_dm.gameplay` layer, deliver the PartyModeOrchestrator pop/resolve loop, wire the EXPLORATION cog with action batching, and add the per-channel token-bucket rate limiter for mutating MCP calls.

Purpose: Phase 4's headline loop is "players declare actions → ShoeGPT narrates via Party Mode." Plan 01 builds that engine end-to-end for the EXPLORATION state. Plan 02 layers combat on top using the same orchestrator + rate limiter. Plan 03 load-tests it.

Output:
- `src/eldritch_dm/gameplay/` package with `party_mode.py` (orchestrator) and `exploration_batch.py` (BatchCoordinator)
- `src/eldritch_dm/mcp/rate_limit.py` (per-channel token bucket, OPS-03)
- `src/eldritch_dm/bot/cogs/exploration.py` (room embed lifecycle + declare-action modal)
- Promoted `DeclareActionButton.callback` from Phase 2 stub to real
- `ChannelEditBudget` (Phase 2 stub) fully implemented as a per-channel coalescer budget
- Updated import-linter contracts for the new `gameplay` layer
- Updated `EldritchBot.setup_hook` to load the exploration cog and start orchestrators for active sessions on boot
- ~25-30 new tests under `tests/gameplay/` + `tests/bot/cogs/`
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/04-gameplay-exploration-combat/04-CONTEXT.md
@.planning/phases/03-lobby-character-ingest/03-03-SUMMARY.md
@src/eldritch_dm/bot/bot.py
@src/eldritch_dm/bot/cogs/lobby.py
@src/eldritch_dm/bot/dynamic_items.py
@src/eldritch_dm/bot/coalescer.py
@src/eldritch_dm/bot/embeds.py
@src/eldritch_dm/bot/warnings.py
@src/eldritch_dm/mcp/tools.py
@src/eldritch_dm/persistence/channel_sessions_repo.py
@src/eldritch_dm/safety/sanitizer.py

**Open question (resolve via 04-RESEARCH.md if present, else use CONTEXT default):**
- D-04: PARTY_POLL_INTERVAL_MS default 250 is in `Settings.party_poll_interval_ms`. Keep the env-driven cadence; do not hardcode.
- D-22 (Dodge shim) — researched in Plan 02. Plan 01 does NOT touch combat; OK to ignore.

<interfaces>
<!-- Already-existing contracts the executor must reuse. Do NOT redefine these. -->

From src/eldritch_dm/mcp/tools.py:
```python
async def party_pop_action(client: MCPClient, *, campaign_name: str) -> dict[str, Any]
async def party_thinking(client: MCPClient, *, campaign_name: str, message: str) -> dict[str, Any]
async def party_get_prefetch(client: MCPClient, *, turn_id: str, outcome: str | None = None,
                              roll: int | None = None, damage: int | None = None,
                              target_hp: int | None = None) -> dict[str, Any]
async def party_resolve_action(client: MCPClient, *, turn_id: str, narration: str) -> dict[str, Any]
async def player_action(client: MCPClient, *, session_id: str, action: str, context: str = "") -> dict[str, Any]
async def get_game_state(client: MCPClient, *, campaign_name: str) -> dict[str, Any]
async def list_characters(client: MCPClient, *, campaign_name: str) -> dict[str, Any]
```

From src/eldritch_dm/persistence/channel_sessions_repo.py:
```python
class ChannelSessionRepo:
    async def get(self, channel_id: str) -> ChannelSession | None
    async def list_active(self) -> list[ChannelSession]  # returns rows where state != 'PAUSED'
    async def set_state(self, channel_id: str, state: ChannelState) -> ChannelSession
```

From src/eldritch_dm/persistence/models.py:
```python
class ChannelState(StrEnum):
    LOBBY = "LOBBY"
    EXPLORATION = "EXPLORATION"
    COMBAT = "COMBAT"
    PAUSED = "PAUSED"
```

From src/eldritch_dm/bot/warnings.py:
```python
async def send_warning(interaction: discord.Interaction, kind: WarningKind, **ctx) -> None
# WarningKind.RATE_LIMITED, WarningKind.DM_OFFLINE, WarningKind.INVALID_ACTION
```

From src/eldritch_dm/safety/sanitizer.py (verify exact API in code):
- `sanitize_player_input(raw: str, *, speaker: str, user_id: str) -> SanitizedInput`
- SanitizedInput has `.wrapped` (the `<player_action ...>…</player_action>` form) and `.audit` (the stripped-token list)

From src/eldritch_dm/bot/dynamic_items.py:
```python
class DeclareActionButton(discord.ui.DynamicItem[discord.ui.Button],
                          template=r"^declare:(?P<channel_id>\d+)$"):
    def __init__(self, channel_id: int) -> None: ...
    async def callback(self, interaction: discord.Interaction) -> None  # currently Phase 2 stub
```

From src/eldritch_dm/bot/coalescer.py:
```python
class ChannelEditBudget:  # stub today — Plan 01 implements
class EmbedCoalescer:
    def __init__(self, message: discord.Message, *, rate_limit_seconds: float = 1.0,
                 channel_budget: ChannelEditBudget | None = None) -> None
    async def update(self, embed: discord.Embed, *, view: discord.ui.View | None = None) -> None
    async def close(self) -> None
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create the gameplay layer + ChannelRateLimiter + ChannelEditBudget (RED→GREEN)</name>
  <files>
    src/eldritch_dm/gameplay/__init__.py,
    src/eldritch_dm/mcp/rate_limit.py,
    src/eldritch_dm/bot/coalescer.py,
    pyproject.toml,
    tests/gameplay/__init__.py,
    tests/gameplay/test_rate_limit.py,
    tests/bot/test_channel_edit_budget.py
  </files>
  <behavior>
    `ChannelRateLimiter` (src/eldritch_dm/mcp/rate_limit.py):
      - Test 1: A single `acquire(channel_id)` returns immediately when bucket has tokens.
      - Test 2: Two `acquire` calls within `min_interval_ms=200` cause the second to await ~200ms (use an injectable clock + injectable sleep so the test is deterministic; assert sleep was called with ~0.2s).
      - Test 3: Per-channel isolation — channel "A" being rate-limited does NOT block channel "B".
      - Test 4: `min_interval_ms` is constructor-configurable; default = 200 per OPS-03.
      - Test 5: `acquire` never raises; it awaits — UX requirement D-30.
      - Test 6: Adversarial — `acquire` is safe under asyncio.gather contention from 4 tasks against the same channel; resulting timestamps are monotonically ≥200ms apart.

    `ChannelEditBudget` (src/eldritch_dm/bot/coalescer.py — replace Phase 2 stub):
      - Test 7: `acquire(message_id)` is non-blocking when the per-channel edit budget has capacity (default budget = 5 edits / 5s, derived from Discord's per-channel limit).
      - Test 8: When 5 edits have happened on different messages within 5s for the same channel, the 6th `acquire` awaits until the rolling window clears.
      - Test 9: `EmbedCoalescer` is updated to call `await self._channel_budget.acquire(self._message.id)` BEFORE issuing `message.edit(...)`, when `channel_budget is not None`.
      - Test 10: Coalescer with `channel_budget=None` (Phase 2 behavior) remains unchanged — no regression.
  </behavior>
  <action>
    Create the `eldritch_dm.gameplay` package skeleton (empty `__init__.py`).

    Implement `ChannelRateLimiter` (src/eldritch_dm/mcp/rate_limit.py) per D-28/D-29/D-30 as a per-channel token-bucket using `dict[str, float]` mapping channel_id → next-allowed-monotonic-time. The class:
      - Constructor: `min_interval_ms: int = 200`, `clock: Callable[[], float] = time.monotonic`, `sleep: Callable[[float], Awaitable[None]] = asyncio.sleep` — both injectable for testing.
      - `async def acquire(self, channel_id: str) -> None` — computes `wait = max(0.0, next_allowed[channel_id] - clock())`; if `wait > 0` await `sleep(wait)`; then set `next_allowed[channel_id] = clock() + min_interval_ms/1000`. Use an `asyncio.Lock()` per channel to serialize the read-modify-write under contention.
      - Mutating-vs-read classification is the CALLER's responsibility; this module does not introspect tool names. (D-29's `@mutating` decorator is a Plan 02 concern when wired into combat wrappers; for Plan 01, the orchestrator decides what to gate.)
      - Bind structlog context: `rate_limit_acquire` log lines bind channel_id + wait_ms (D-36).

    Implement `ChannelEditBudget` (src/eldritch_dm/bot/coalescer.py) replacing the Phase 2 stub. Reference: Discord's per-channel limit is 5 message edits per 5 seconds (Phase 2 RESEARCH verified). Use a deque of recent edit timestamps per channel_id; `acquire(message_id)` pops timestamps older than 5s, and if the deque is ≥5 it awaits until the oldest is >5s old. Inject the same `clock` / `sleep` for tests. Update `EmbedCoalescer._render_loop` to `await self._channel_budget.acquire(...)` BEFORE `message.edit` when `channel_budget` is not None — this is additive to per-message rate limit, not a replacement.

    Update `pyproject.toml` import-linter to add the new layer:

    ```
    [[tool.importlinter.contracts]]
    name = "gameplay must not import bot"
    type = "forbidden"
    source_modules = ["eldritch_dm.gameplay"]
    forbidden_modules = ["eldritch_dm.bot"]

    [[tool.importlinter.contracts]]
    name = "gameplay may import mcp/persistence/safety only"
    type = "forbidden"
    source_modules = ["eldritch_dm.gameplay"]
    forbidden_modules = ["eldritch_dm.ingest"]
    ```

    Add `gameplay` to the existing "nothing outside bot may import from bot" contract's source_modules list (so gameplay can not reach into bot).

    Write tests as enumerated in `<behavior>`.
  </action>
  <verify>
    <automated>uv run pytest tests/gameplay/test_rate_limit.py tests/bot/test_channel_edit_budget.py -x -v && uv run lint-imports</automated>
  </verify>
  <done>
    `ChannelRateLimiter.acquire` enforces ≥200ms between mutating calls per channel under deterministic clock-mocked tests; `ChannelEditBudget` enforces 5-edits/5s per channel and is wired into `EmbedCoalescer`; import-linter passes with `gameplay` layer added; 10+ tests green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: ExplorationBatch + BatchCoordinator + PartyModeOrchestrator (RED→GREEN)</name>
  <files>
    src/eldritch_dm/gameplay/exploration_batch.py,
    src/eldritch_dm/gameplay/party_mode.py,
    tests/gameplay/test_exploration_batch.py,
    tests/gameplay/test_party_mode.py
  </files>
  <behavior>
    `ExplorationBatch` dataclass (src/eldritch_dm/gameplay/exploration_batch.py) per D-07:
      - Frozen-ish (mutable `submissions` list; `first_submission_ts` + `deadline_ts` immutable per batch instance).
      - `PlayerIntent(user_id: str, sanitized_wrapped: str, character_id: str | None, ts: datetime)` — the unit the modal feeds in.

    `BatchCoordinator` (src/eldritch_dm/gameplay/exploration_batch.py) per D-07..D-10:
      - Test 1: First `submit(channel_id, intent)` starts a new ExplorationBatch with deadline = first_submission_ts + 30s; returns `flushed=False`.
      - Test 2: Subsequent submits within window append to the same batch; `flushed=False`.
      - Test 3: When `len(submissions) == active_party_size`, submit returns `flushed=True` and the batch is removed from the coordinator (D-08 step 4).
      - Test 4: Deadline-driven flush: a `tick(now)` method returns the list of channel_ids whose batches have expired; coordinator removes them on flush.
      - Test 5: A submission AFTER flush starts a new batch (D-10).
      - Test 6: `set_active_party_size(channel_id, n)` is callable; coordinator caches it; if not set, defaults to `unknown` and only deadline-flushes (degraded but safe).
      - Test 7: Concurrent submit calls from 4 asyncio tasks against the same channel produce exactly one flushed=True (no double-flush race).

    `PartyModeOrchestrator` (src/eldritch_dm/gameplay/party_mode.py) per D-03/D-05/D-06/D-25/D-27:
      - Class state: per channel_id one asyncio.Task plus references to its MCPClient, ChannelRateLimiter, BatchCoordinator, ChannelSessionRepo, on_combat_transition callback, on_resolved_narrative callback.
      - Test 8: `start_orchestrator_for_channel(channel_id, campaign_name, session_id)` creates exactly one task; calling again is a no-op (returns existing task).
      - Test 9: `stop_orchestrator_for_channel(channel_id)` cancels the task and removes it from the registry; idempotent.
      - Test 10: Loop sequence with `party_pop_action` returning a non-empty action: `party_thinking` is called next, then `party_resolve_action` (with the narrative from the on_resolved_narrative callback). Asserted via respx mock + call ordering.
      - Test 11: Empty pop → orchestrator sleeps `PARTY_POLL_INTERVAL_MS/1000` (use injectable sleep and assert it was called with `0.250`).
      - Test 12: `party_get_prefetch` is called only when the popped action has `is_combat_turn=True` (or similar flag — verify against ddmcpskills.md; if dm20 puts `turn_id` + `outcome` keys on the action, treat the presence of `turn_id` as the gate). Test both branches.
      - Test 13: When the loop calls `party_resolve_action` it goes THROUGH `ChannelRateLimiter.acquire(channel_id)` (mutating). Reads (`get_game_state`, `party_pop_action`) do NOT.
      - Test 14: Combat-transition watcher — when `get_game_state` returns `combat_active=True` (or `state="COMBAT"`), the `on_combat_transition(EXPLORATION→COMBAT)` callback fires exactly once; symmetric on transition back (D-26).
      - Test 15: `party_pop_action` raising `MCPError` does not crash the loop; logs and retries after sleep.
      - Test 16: Cancellation: orchestrator task awaits cleanly on `asyncio.CancelledError`; no orphaned background tasks.
  </behavior>
  <action>
    Implement `ExplorationBatch` + `PlayerIntent` + `BatchCoordinator` exactly per D-07..D-10. The coordinator holds `dict[str, ExplorationBatch]` keyed by channel_id and a `dict[str, int | None]` for active_party_size. A `BatchCoordinator.submit` returns a dataclass `SubmitResult(flushed: bool, batch: ExplorationBatch | None)`; flushed=True means the caller is responsible for serializing the batch payload into the dm20 `player_action` call. The orchestrator is the caller — exploration_cog only submits intents.

    Batch payload serialization: D-08 step 4 says `<batch><player_action ...>...</player_action>...</batch>`. Use the already-wrapped `sanitized_wrapped` strings from each PlayerIntent (sanitizer outputs them in `<player_action ...>` form already — verify in `eldritch_dm/safety/sanitizer.py`) and join inside a `<batch>...</batch>` envelope. Helper: `serialize_batch_payload(batch: ExplorationBatch) -> str`.

    Implement `PartyModeOrchestrator`:
      - Constructor: `mcp: MCPClient`, `rate_limiter: ChannelRateLimiter`, `batch_coordinator: BatchCoordinator`, `channel_sessions: ChannelSessionRepo`, `poll_interval_ms: int = 250`, `on_resolved: Callable[[str, dict], Awaitable[None]]`, `on_state_change: Callable[[str, ChannelState, ChannelState], Awaitable[None]]`, optional `clock` + `sleep` for tests.
      - Public methods: `async def start_orchestrator_for_channel(channel_id, campaign_name, claudmaster_session_id) -> asyncio.Task`, `async def stop_orchestrator_for_channel(channel_id) -> None`, `async def stop_all() -> None`.
      - Internal coroutine `async def _loop(channel_id, campaign_name, session_id)` implementing D-03's pseudocode, with each mutating dm20 call gated via `await self._rate_limiter.acquire(channel_id)`.
      - Combat-transition watcher per D-25/D-26/D-27: piggyback on the same loop — every K-th iteration (where K = `combat_check_every_n_polls`, default 4 → ~1s when poll=250ms) call `get_game_state` and compare to last-seen state; fire `on_state_change` callback on transitions; update `channel_sessions` state via repo.
      - Deadline-driven batch flush: between pop attempts the loop also calls `batch_coordinator.tick(now)`; for each expired channel batch, sends the serialized payload via `player_action(session_id, action="batch_intents", context=serialize_batch_payload(batch))` then continues the pop/resolve loop.

    Use structlog binding `channel_id`, `session_id`, `action_kind`, `round_number` per D-36. All log lines INFO-level on success, WARNING on transient errors, EXCEPTION on unexpected.

    Write tests as enumerated. Use `respx` for the MCP HTTP layer (preferred per phase tooling convention) OR mock `MCPClient.call` directly with `AsyncMock` if respx setup costs too much. Use `asyncio.wait_for` with timeouts ≤1s in tests; never sleep real time.
  </action>
  <verify>
    <automated>uv run pytest tests/gameplay/test_exploration_batch.py tests/gameplay/test_party_mode.py -x -v</automated>
  </verify>
  <done>
    `BatchCoordinator` flushes on party-size OR deadline; PartyModeOrchestrator pop→thinking→(prefetch)→resolve loop verified via mocked MCPClient; combat-transition watcher fires exactly once per transition; 16+ tests green; orchestrator clean-cancels on task cancellation.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: ExplorationCog + DeclareActionModal + promoted DeclareActionButton + setup_hook wiring</name>
  <files>
    src/eldritch_dm/bot/cogs/exploration.py,
    src/eldritch_dm/bot/dynamic_items.py,
    src/eldritch_dm/bot/bot.py,
    tests/bot/cogs/test_exploration_cog.py,
    tests/bot/test_dynamic_items_declare_real.py
  </files>
  <behavior>
    `DeclareActionModal` (defined inside `exploration.py` OR added to `src/eldritch_dm/bot/modals.py` — author's call; lean toward exploration.py to keep modals.py focused on character ingest):
      - Test 1: 1 component (single TextInput, max_length=500, label "What do you do?"); stays under the 5-component cap automatically.
      - Test 2: `on_submit` calls `sanitize_player_input(raw, speaker=interaction.user.display_name, user_id=str(interaction.user.id))` and pushes the resulting wrapped string into BatchCoordinator.

    `DeclareActionButton.callback` (promote from Phase 2 stub in `src/eldritch_dm/bot/dynamic_items.py`):
      - Test 3: Stub log line "phase2_stub_callback_invoked" is GONE; log line is now "declare_action_button_invoked".
      - Test 4: Reads `bot.channel_sessions.get(str(self.channel_id))`; if no session OR session.state != EXPLORATION, sends ephemeral via `send_warning(WarningKind.INVALID_ACTION, reason="Exploration is not active in this channel.")` instead of opening the modal.
      - Test 5: When session.state == EXPLORATION, opens the DeclareActionModal via the `_ModalLaunchView` 2-step pattern Phase 3 established (defer ephemeral → button → send_modal). Re-use Phase 3's pattern; do not reinvent. EDM001 noqa documented on the modal-launch button (precedent: ingest.py).

    `ExplorationCog` (src/eldritch_dm/bot/cogs/exploration.py):
      - Test 6: Cog loads cleanly via `await bot.load_extension("eldritch_dm.bot.cogs.exploration")`.
      - Test 7: Cog exposes `async def render_room_for_channel(channel_id, room_title, narration, party_hp) -> discord.Message` that posts a fresh room_embed with a DeclareActionButton attached, and registers an EmbedCoalescer for that message (Phase 2 coalescer; share the `ChannelEditBudget` registered per channel on the bot).
      - Test 8: Cog exposes `async def update_room_for_channel(channel_id, room_title, narration, party_hp) -> None` that calls the existing coalescer.update — never posts a new message. This is what `on_resolved_narrative` will call back into.
      - Test 9: Listens to PartyModeOrchestrator's `on_resolved` callback (registered via bot wiring in setup_hook); on EXPLORATION-state narrative resolutions, calls `update_room_for_channel(...)`.
      - Test 10: `on_state_change(EXPLORATION→COMBAT)` callback unregisters the exploration coalescer for that channel (cleans up; combat cog from Plan 02 will register its own combat embed).

    `EldritchBot.setup_hook` extension:
      - Test 11: `load_extension("eldritch_dm.bot.cogs.exploration")` is called.
      - Test 12: A single shared `ChannelRateLimiter` instance is attached as `bot.rate_limiter`.
      - Test 13: A single shared `BatchCoordinator` instance is attached as `bot.batch_coordinator`.
      - Test 14: A single shared `PartyModeOrchestrator` instance is attached as `bot.orchestrator`.
      - Test 15: On boot, for every `channel_sessions` row whose state ∈ {EXPLORATION, COMBAT}, the orchestrator's `start_orchestrator_for_channel` is called. Restart-survival drill (no real Discord — mocked).
      - Test 16: LobbyCog's existing all-ready transition (which calls `set_state(EXPLORATION)`) now ALSO triggers `bot.orchestrator.start_orchestrator_for_channel(...)`. Verify by patching ReadyButton.callback's path-of-call and asserting orchestrator.start was awaited. (Cross-cog integration — keep it small: a single bus-style hook on the bot, e.g., `bot.on_session_state_change(channel_id, new_state)`.)
  </behavior>
  <action>
    Implement `DeclareActionModal` (single TextInput component). Submission flow:
      1. `await interaction.response.defer(thinking=True, ephemeral=True)` (EDM001).
      2. `sanitized = sanitize_player_input(raw, speaker=interaction.user.display_name, user_id=str(interaction.user.id))`.
      3. `intent = PlayerIntent(user_id=..., sanitized_wrapped=sanitized.wrapped, character_id=None, ts=datetime.now(UTC))`.
      4. `result = await bot.batch_coordinator.submit(channel_id, intent)`.
      5. Send ephemeral followup: if `result.flushed` → "✅ Action submitted. Resolving the party's turn..."; else → "✅ Action submitted. Waiting for the party (deadline: {remaining}s)."
      6. If `result.flushed`, the orchestrator's tick will pick it up — DO NOT call dm20 directly from the modal.

    Promote `DeclareActionButton.callback` from the Phase 2 stub. Use the same `_ModalLaunchView` 2-step pattern that `IngestCog` uses in Phase 3 (defer → ephemeral button → button click sends modal). State guard: refuse to open the modal if session state is not EXPLORATION (sends `INVALID_ACTION` warning).

    Implement `ExplorationCog`:
      - Holds `dict[str, EmbedCoalescer]` keyed by channel_id (current room message coalescer).
      - `render_room_for_channel`: posts the message via the channel's Discord channel object (`bot.get_channel(int(channel_id))`); attaches a View containing `DeclareActionButton(channel_id=int(channel_id))`; persists a `PersistentView` row keyed `declare:{channel_id}` (audit only; dispatch is via `add_dynamic_items`); installs an `EmbedCoalescer` with the per-channel ChannelEditBudget.
      - `update_room_for_channel`: re-renders the embed via `room_embed(...)` and calls `coalescer.update(embed)`.
      - Callback registration: in `cog_load`, call `bot.orchestrator.register_resolution_callback(self.on_resolved)` and `bot.orchestrator.register_state_change_callback(self.on_state_change)`. Use list-of-callbacks pattern inside the orchestrator (so combat cog from Plan 02 can also register its own).

    Update `EldritchBot.setup_hook` AFTER existing cog loads:
      1. Construct `self.rate_limiter = ChannelRateLimiter(min_interval_ms=settings.mcp_rate_limit_ms)` (add `mcp_rate_limit_ms: int = 200` to `Settings` + `.env.example` if not present — verify; if missing add it).
      2. Construct `self.batch_coordinator = BatchCoordinator(window_seconds=30)`.
      3. Construct `self.channel_edit_budgets: dict[str, ChannelEditBudget] = {}` and a helper `get_channel_edit_budget(channel_id) -> ChannelEditBudget` that lazily creates and caches.
      4. Construct `self.orchestrator = PartyModeOrchestrator(...)` wiring all of the above.
      5. `await self.load_extension("eldritch_dm.bot.cogs.exploration")`.
      6. After `rehydrate_persistent_views`, iterate `await self.channel_sessions.list_active()` and for each row with state ∈ {EXPLORATION, COMBAT} call `await self.orchestrator.start_orchestrator_for_channel(row.channel_id, row.campaign_name, row.claudmaster_session_id)`.
      7. `bot.on_session_state_change` bus: add a tiny method that the LobbyCog's ReadyButton can call when transitioning to EXPLORATION; the bus starts the orchestrator. Update `dynamic_items.ReadyButton.callback` to call `await interaction.client.on_session_state_change(str(self.channel_id), ChannelState.LOBBY, ChannelState.EXPLORATION)` immediately after the existing `set_state(EXPLORATION)` call.

    All MCP calls in this plan that mutate dm20 state MUST go through `self.rate_limiter.acquire(channel_id)`. Reads do not. The orchestrator is the only thing that pops/resolves — modals do not call dm20 directly (D-08 step 4 enforces).

    Update `EldritchBot.close` (graceful shutdown) to call `await self.orchestrator.stop_all()`.

    Write tests as enumerated; reuse Phase 3's existing async fixtures and mocking patterns. Use `pytest-asyncio` and `respx` (already in dev deps).
  </action>
  <verify>
    <automated>uv run pytest tests/bot/cogs/test_exploration_cog.py tests/bot/test_dynamic_items_declare_real.py -x -v && uv run ruff check src/ tests/ && uv run lint-imports</automated>
  </verify>
  <done>
    Promoted DeclareActionButton no longer reports "phase2_stub"; clicking it through a real-looking mocked Interaction opens the modal; submitting routes through sanitizer → BatchCoordinator → flushes to orchestrator; setup_hook starts orchestrators for all EXPLORATION/COMBAT rows on boot; all 16+ exploration-cog/dynamic-item tests pass; ruff + lint-imports clean.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Player → DeclareActionModal | Untrusted free text (≤500 chars) crosses into the system; must be sanitized BEFORE any MCP-layer exposure. |
| ExplorationCog → BatchCoordinator → Orchestrator → dm20 | Server-internal; trusted but rate-limited (OPS-03). |
| Orchestrator → on_resolved_narrative callback → ExplorationCog → Discord | Trusted; payload is dm20's narration, rendered via `room_embed` which only consumes plain strings. |
| EldritchBot.setup_hook restart path | Reads channel_sessions rows from DB (trusted, written by our own code). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-01 | Spoofing | DeclareActionButton | mitigate | Sanitizer wraps with `user_id="<interaction.user.id>"` (already done by SAN-04); ExplorationCog reads `interaction.user.id` directly, never trusts modal content for identity. |
| T-04-02 | Tampering | Batched payload to dm20 | mitigate | Serializer builds `<batch>…</batch>` from already-wrapped sanitized strings; never re-renders raw input. Sanitizer's `<player_action>` envelope is the integrity boundary. |
| T-04-03 | Repudiation | "I never submitted that action" | mitigate | structlog `declare_action_submitted` log line binds `channel_id`, `user_id`, `len(raw)`, `audit_stripped_tokens` (D-36); sanitizer audit row already persists raw + stripped tokens. |
| T-04-04 | Information Disclosure | Orchestrator log lines | accept | Logs include sanitized payload, not raw player text; sanitizer audit is the only place raw text lands and is access-controlled at the filesystem level. |
| T-04-05 | Denial of Service | Player hammers DeclareActionButton | mitigate | Two layers: (a) BatchCoordinator dedupes within a 30s window (only one batch per channel); (b) ChannelRateLimiter (200ms gap on mutating MCP calls) prevents dm20 thrashing. |
| T-04-06 | Denial of Service | Player submits 1000-char prompt-injection payload | mitigate | Sanitizer enforces 500-char cap (SAN-03) BEFORE wrapping; over-cap truncates with audit flag. Modal also has `max_length=500` enforced client-side. |
| T-04-07 | Elevation of Privilege | Player A tries to flush Player B's batch | mitigate | BatchCoordinator stores submissions keyed by channel_id, not user_id; players within the same channel are the same trust domain — that's the design. Cross-channel is impossible because the button's custom_id encodes channel_id. |
| T-04-08 | DoS (timing) | A long-running on_resolved callback blocks the orchestrator | mitigate | Orchestrator awaits callbacks but logs `slow_callback_warn` when > 2s; tests assert callbacks return < 100ms in mocked scenarios. Each callback is wrapped in `asyncio.shield` so cancellation doesn't tear down the loop. |
| T-04-SC | Tampering | Supply-chain (no new packages this plan) | accept | Plan 01 introduces NO new third-party packages — only stdlib + already-pinned discord.py/aiosqlite/structlog. No package-legitimacy gate needed. |
</threat_model>

<verification>
**Plan-level checks (in addition to per-task `<verify>`):**

1. `uv run pytest tests/gameplay tests/bot/cogs/test_exploration_cog.py tests/bot/test_dynamic_items_declare_real.py tests/bot/test_channel_edit_budget.py -v` — all green.
2. `uv run ruff check src/ tests/` — clean.
3. `uv run lint-imports` — all import-linter contracts pass, including the new `gameplay` layer.
4. `grep -nE "phase2_stub_callback_invoked" src/eldritch_dm/bot/dynamic_items.py` — returns ONLY the `EndTurnButton` and `RiposteButton` lines (Plan 02 and Plan 05 will retire those). The `DeclareActionButton` stub line MUST be gone.
5. `grep -n "ChannelRateLimiter\|BatchCoordinator\|PartyModeOrchestrator" src/eldritch_dm/bot/bot.py` — at least three matches showing setup_hook wiring.

**Risks:**
- **Combat-transition race:** The orchestrator polls `get_game_state` every K-th iteration. If dm20 transitions to COMBAT between polls, the exploration UI lingers briefly (≤1s). Acceptable for v1; Plan 02 may shorten K under combat to ~1 poll per tick.
- **dm20's `party_pop_action` shape ambiguity:** CONTEXT D-03 pseudocode assumes a `turn_id` field exists on combat-relevant actions. If RESEARCH or actual dm20 calls disagree, treat presence of any of `{turn_id, combat_turn_id, encounter_action}` as the prefetch gate. Tests should mock both shapes.
- **Orchestrator lifecycle vs Discord intents:** discord.py intents (`message_content=False`) do NOT affect orchestrator behavior; orchestrator is pure HTTP to dm20.
- **`_ModalLaunchView` precedent:** Phase 3 established the 2-step modal launch in `bot/cogs/ingest.py`. Re-use that pattern verbatim; if any divergence is needed, document why in `04-01-SUMMARY.md`.

**Open question (flag for Plan 02 / executor if RESEARCH absent):**
- D-22 dodge shim — Plan 02 owns this; Plan 01 unaffected.
- Whether `bot.on_session_state_change` should be a discord.py listener (`@bot.event`) or a plain method. Lean plain method (simpler; no event dispatch overhead).
</verification>

<success_criteria>
- `eldritch_dm/gameplay/` package exists; import-linter recognizes it; bot may import it, it may import mcp/persistence/safety; cannot import bot or ingest.
- `ChannelRateLimiter.acquire("X")` blocks a second call within 200ms; per-channel isolation verified.
- `ChannelEditBudget` enforces 5 edits / 5s per channel and is wired into `EmbedCoalescer`.
- `BatchCoordinator` flushes on party-size OR 30s deadline; 4-player synthetic test exercises both; concurrent-submit race is safe.
- `PartyModeOrchestrator` runs the pop → thinking → (prefetch) → resolve loop; mutating calls gated by ChannelRateLimiter; combat-state transitions trigger registered callbacks.
- `DeclareActionButton.callback` is no longer a Phase 2 stub; opens a real DeclareActionModal via the 2-step launch pattern; submission routes through sanitizer → BatchCoordinator.
- `ExplorationCog` posts the room_embed + DeclareActionButton, owns a per-channel coalescer, and registers callbacks on the orchestrator.
- `EldritchBot.setup_hook` starts orchestrators for all EXPLORATION/COMBAT rows on boot; close() cleanly stops all orchestrators.
- 25+ new tests pass; `ruff check` and `lint-imports` clean.
- Requirements EXPLORE-01..07 and OPS-03 are satisfied. (COMBAT-* and the load test are Plans 02/03.)
</success_criteria>

<output>
On completion, create `.planning/phases/04-gameplay-exploration-combat/04-01-SUMMARY.md` per the standard template, including:
- new files + counts
- decisions made (any divergence from CONTEXT D-XX with justification)
- next-phase readiness signal: "Plan 02 may now layer the combat cog on top of the orchestrator + rate limiter + ChannelEditBudget already wired here."
</output>
