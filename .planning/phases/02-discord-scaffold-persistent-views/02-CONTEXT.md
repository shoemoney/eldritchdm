# Phase 2: Discord Scaffold + Persistent Views - Context

**Gathered:** 2026-05-21
**Status:** Ready for research + planning
**Mode:** Synthesized from REQUIREMENTS (BOT-01..08, OPS-04) + Phase 1 deliverables + ddmcpskills.md

<domain>
## Phase Boundary

Stand up a running `discord.py` bot whose:

1. **Slash command tree** is registered and dispatching (`/ping`, `/status` only — gameplay commands come in Phase 3)
2. **Interaction discipline** is rigorous: every callback's first line is `await interaction.response.defer(thinking=True)` (enforced by a custom ruff rule that fails CI)
3. **Embed renderers** for the four templates we'll need across all later phases (`lobby_embed`, `room_embed`, `combat_embed`, `character_confirm_embed`) — stable shape, swappable content
4. **Persistent View infrastructure** uses `discord.ui.DynamicItem[discord.ui.Button]` with regex `custom_id` templates, registered in `setup_hook` against rows in our `persistent_views` table (LOC-02 schema, already shipped Phase 1)
5. **Embed update coalescer** caps message edits at ≤1/sec per message via a per-message `asyncio.Queue` + render task — so Phase 4 combat doesn't 429 the Discord API
6. **Ephemeral warning helper** produces standardized `❌ Not your turn`, `❌ Riposte expired`, `❌ DM is thinking…` cards
7. **Kill-and-restart drill** is in the test suite: bot killed mid-flight, restarted, persistent buttons still functional (matching `custom_id` dispatches to handler with state restored from DB)

ZERO gameplay logic. ZERO MCP tool invocations beyond `/ping` calling `MCPClient`'s health endpoint. ZERO character/session creation flows. The bot wires up its own scaffolding, then yields to Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Library version + entry point
- **D-01:** Pin `discord.py>=2.7.1,<3.0` (already in `pyproject.toml` from Phase 1)
- **D-02:** Bot lives at `src/eldritch_dm/bot/`. Entry point class `EldritchBot(discord.ext.commands.Bot)`. App command tree via `bot.tree` (default).
- **D-03:** Process entrypoint = `src/eldritch_dm/bot/__main__.py` — reads `Settings`, builds bot, calls `bot.start(token)`. Phase 5's `run.py` will wrap this.
- **D-04:** Intents: minimal — `Intents.default()` plus `Intents.message_content = False` (we never read raw messages; modals + slash commands only). Document this as a security choice — bot can't be used to scrape DMs.

### Module layout
- **D-05:** Source layout:
  ```
  src/eldritch_dm/bot/
    __init__.py
    __main__.py              # process entrypoint
    bot.py                   # EldritchBot(commands.Bot) + setup_hook (rehydration)
    embeds.py                # lobby_embed, room_embed, combat_embed, character_confirm_embed
    warnings.py              # ephemeral helper: send_warning(interaction, kind, **ctx)
    coalescer.py             # MessageRenderQueue + EmbedCoalescer (per-message ≤1 edit/sec)
    dynamic_items.py         # DynamicItem subclasses with regex custom_id templates
    cogs/
      __init__.py
      diagnostics.py         # /ping, /status
    setup_hook.py            # extracted rehydration helpers (callable from tests)
  tests/bot/
    __init__.py
    conftest.py              # bot fixtures, dpytest harness if used
    test_bot_lifecycle.py    # startup/shutdown, intents, app command sync
    test_embeds.py           # snapshot tests for each renderer
    test_warnings.py         # ephemeral payload shape
    test_coalescer.py        # rate-limit math, queue drain semantics
    test_dynamic_items.py    # custom_id regex parsing, payload extraction
    test_setup_hook.py       # rehydration: seed DB, build bot, assert add_view called
    test_restart_drill.py    # kill-and-restart integration test
  ```

### Slash commands (Phase 2 scope only)
- **D-06:** `/ping` — replies (ephemeral) with MCP health status from `get_circuit_state()` + last successful ping timestamp + tool count from `MCPClient`. Defers first, then followups.
- **D-07:** `/status` — replies (ephemeral) with current channel session row from `ChannelSessionRepo` (state, campaign_name, created_at) — or "No active session in this channel" if not found.
- **D-08:** Gameplay commands (`/start_game`, `/upload_character_url`, etc.) are explicitly **NOT** in Phase 2. They're declared as TODOs in `cogs/diagnostics.py` doctring to make scope boundaries clear.

### Interaction defer discipline (the critical rule)
- **D-09:** **Every interaction callback's first non-trivial line MUST be `await interaction.response.defer(thinking=True)` (or `ephemeral=True` variant).** This is the single most important Discord-correctness rule in the project.
- **D-10:** Enforced by a **custom ruff rule** (`EDM001`) implemented as a `ruff` plugin OR as a regex-based pre-commit hook (whichever is simpler — if ruff plugins prove painful, fall back to grep-based check). The rule:
  - Identifies functions decorated with `@bot.tree.command()`, `@app_commands.command()`, or button/select callbacks (`@discord.ui.button(...)`)
  - Walks the function body
  - Fails if the first statement is not an `await interaction.response.defer(...)` call (or a docstring then defer)
- **D-11:** CI fails the build on EDM001 violations. Local pre-commit hook catches it before push.
- **D-12:** Acceptable exceptions (must be commented `# noqa: EDM001 — <reason>`): autocomplete callbacks, modal submit handlers that respond with a new modal immediately (those use `response.send_modal` instead of defer).

### Embed renderers
- **D-13:** Pure functions: `lobby_embed(campaign_name: str, players: list[PlayerStatus]) -> discord.Embed`. No I/O, no async — easy to snapshot-test.
- **D-14:** Renderers return `discord.Embed` and a `list[discord.ui.View]` tuple when persistent buttons are needed (caller decides which message to post on).
- **D-15:** Color palette: lobby=`0x5865F2` (Discord blurple), exploration=`0x57F287` (green), combat=`0xED4245` (red), character_confirm=`0xFEE75C` (yellow). Defined as `class EmbedColor(IntEnum)`.
- **D-16:** Footer always says `🎲 ShoeGPT · EldritchDM` plus an updated-at timestamp. Standardizes branding.
- **D-17:** Title/description content is **template-driven** via Jinja2 OR f-strings — picking f-strings to avoid adding a templating dep just for this. (We may reach for Jinja2 in Phase 3 for prompt assembly; Phase 2 doesn't need it.)
- **D-18:** Each renderer has a snapshot test (`tests/bot/test_embeds.py` uses `syrupy` or hand-rolled JSON comparison) that pins the output structure. Changing a renderer requires updating the snapshot — keeps changes intentional.

### Persistent Views — the hard problem
- **D-19:** **All persistent buttons inherit `discord.ui.DynamicItem[discord.ui.Button]`** with a `template: str = re.compile(r'...')` class attr.
- **D-20:** Four `DynamicItem` subclasses, one per persistent button kind, each with a regex `custom_id` template that encodes the minimum state needed to dispatch:
  - `ReadyButton` — `ready:(?P<channel_id>\d+)` (lobby ready-up)
  - `DeclareActionButton` — `declare:(?P<channel_id>\d+)` (exploration intent collection)
  - `EndTurnButton` — `endturn:(?P<channel_id>\d+):(?P<actor_id>\d+)` (combat turn yield; gate by actor_id)
  - `RiposteButton` — `riposte:(?P<timer_id>\d+):(?P<user_id>\d+)` (timed reaction; timer_id keys into `riposte_timers` table)
- **D-21:** Each `DynamicItem` overrides `from_custom_id` to parse the regex match and return the constructed instance. `callback` reads only the values encoded in `custom_id` + queries to repos as needed — never relies on Python-side state (which dies with the process).
- **D-22:** **`custom_id` 100-char limit** — keep encodings short. Use Discord snowflake ids (already digits), no JSON in custom_id ever.
- **D-23:** Phase 2 only stubs the callbacks (each logs the dispatch + returns "Phase 2 stub — wired up in Phase N"). Real handlers land in Phase 3 (ready), Phase 4 (declare, endturn), Phase 5 (riposte).

### `setup_hook` rehydration flow
- **D-24:** `setup_hook` runs once before the bot connects to the gateway. Order:
  1. Acquire DB connection pool (PersistenceManager from Phase 1)
  2. Run `bootstrap.ensure_schema(db_path)` (idempotent, cheap)
  3. Start `WriterQueue`, `WalCheckpointTask`, `MCPClient` health task
  4. Register the four `DynamicItem` subclasses on the View Registry: `bot.add_dynamic_items(ReadyButton, DeclareActionButton, EndTurnButton, RiposteButton)`
  5. Query `PersistentViewRepo.list_all()` → for each row, construct a fresh `View` with the right dynamic items and call `bot.add_view(view, message_id=int(row.message_id))`
  6. Sync app command tree (per guild if `DISCORD_GUILD_IDS` set, else global) — log how many commands synced
  7. Bind `structlog` context with `bot_user_id` once bot.user is known (after on_ready)
- **D-25:** `setup_hook` failures are **fatal** — the bot does not connect to Discord if any setup step throws. Log full traceback + exit code 2.
- **D-26:** **Graceful shutdown** (`bot.close()` override): cancel health task, cancel WalCheckpointTask, drain WriterQueue (5s timeout), close MCPClient httpx pool, close DB writer connection. (OPS-04.)

### Embed update coalescer
- **D-27:** Per-message render queue: when N writers want to update the same Discord message rapidly (Phase 4 combat), only one edit lands per second.
- **D-28:** API: `coalescer = EmbedCoalescer(message); await coalescer.update(embed, view=...)`. Coalescer:
  - Stores the latest `(embed, view)` payload (overwrites older pending updates — we always want the freshest state)
  - A render task wakes every ≥1.0s, applies the latest payload via `message.edit(...)`, clears the buffer
  - If a new update arrives mid-sleep, the task picks it up on the next wake
- **D-29:** Rate limit per env var: `EMBED_EDIT_RATE_LIMIT` (default 1.0/sec from `.env.example`).
- **D-30:** Errors from `message.edit` (NotFound, Forbidden, HTTPException 429) are caught, logged, and the coalescer marks the message as "abandoned" (no more edits attempted) — Phase 4 will rebuild the embed in a new message if needed.

### Ephemeral warning helper
- **D-31:** Single function: `async def send_warning(interaction: discord.Interaction, kind: WarningKind, **ctx) -> None`. `WarningKind` is an enum: `NOT_YOUR_TURN`, `RIPOSTE_EXPIRED`, `DM_OFFLINE`, `INVALID_ACTION`, `RATE_LIMITED`.
- **D-32:** Helper picks the right copy from a `dict[WarningKind, str]` table, formats with `ctx`, sends via `interaction.followup.send(content=..., ephemeral=True)`. Assumes defer has already happened (it should — D-09).
- **D-33:** Copy is short and player-facing. Examples:
  - `NOT_YOUR_TURN`: `"❌ It is not your turn, **{actor_name}**. Sit tight!"`
  - `DM_OFFLINE`: `"🔌 ShoeGPT is offline. Health check failed {failure_count} times in a row. Try again in a moment."`

### Testing strategy
- **D-34:** Use **`dpytest`** for in-process Discord harness IF the integration suite stays under 10s — otherwise fall back to mocking `discord.Client` directly. Researcher should evaluate `dpytest` 2.0 compatibility with `discord.py 2.7.1` (this is the only real risk item in Phase 2).
- **D-35:** Snapshot tests for embeds use `syrupy>=4.6,<5.0` (or hand-rolled JSON compare if `syrupy` doesn't like `discord.Embed.to_dict()`).
- **D-36:** **Restart drill** test:
  1. Build bot A, run `setup_hook`, write a `persistent_views` row + corresponding `channel_sessions` row to a tmp DB
  2. Simulate a button-click `Interaction` (mock the Discord-side gateway dispatch) with a matching `custom_id`
  3. Assert the callback fires and produces the expected log line
  4. "Restart": discard bot A entirely, build bot B (fresh process, same DB path)
  5. Run `setup_hook` again — assert `bot.add_view(...)` was called for the original message_id
  6. Re-dispatch the same `Interaction` → still works
- **D-37:** `tests/bot/conftest.py` provides: `bot_factory` fixture (returns a fresh bot bound to a tmp DB), `interaction_factory` fixture (builds mock `discord.Interaction` with the right shape).

### Logging
- **D-38:** Every interaction callback binds `structlog` context: `channel_id`, `guild_id` (or `dm`), `user_id`, `custom_id` (if applicable), `command_name`. Logged on entry + on completion (success/error).
- **D-39:** `setup_hook` logs at INFO: "rehydrated N persistent views from M channel sessions; synced K app commands".

### Claude's Discretion
- Whether the EDM001 ruff rule is a true plugin or a grep-based pre-commit (functional outcome matters, mechanism doesn't)
- Snapshot library choice (syrupy vs hand-rolled)
- Whether `dpytest` is healthy enough for our tests or we mock `discord.Client` directly
- The `EmbedCoalescer`'s internal asyncio mechanism (queue + task vs event + timer)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope
- `.planning/REQUIREMENTS.md` § Discord Scaffold (BOT-01..08), § Operational (OPS-04)
- `.planning/ROADMAP.md` § Phase 2 — goal + 5 success criteria

### Phase 1 deliverables (interfaces this phase consumes)
- `src/eldritch_dm/mcp/client.py` — `MCPClient` (`/ping` will call it)
- `src/eldritch_dm/mcp/health.py` — `get_circuit_state()`, `CircuitState`
- `src/eldritch_dm/persistence/channel_sessions_repo.py` — `ChannelSessionRepo.get_by_channel`, `list_active`
- `src/eldritch_dm/persistence/persistent_views_repo.py` — `PersistentViewRepo.list_all`, `insert`, `delete_for_message`
- `src/eldritch_dm/persistence/riposte_timers_repo.py` — read-only for now; Phase 5 writes
- `src/eldritch_dm/persistence/connection.py` — `PersistenceManager`, `WriterQueue`
- `src/eldritch_dm/safety/sanitizer.py` — `sanitize_player_input` (Phase 3 actually uses; Phase 2 just imports to confirm it loads)
- `src/eldritch_dm/config.py` — `Settings` (DISCORD_TOKEN, DISCORD_GUILD_IDS, EMBED_EDIT_RATE_LIMIT)
- `src/eldritch_dm/logging.py` — structlog setup

### Architectural context
- `.planning/research/SUMMARY.md` § Architecture — async model, persistent View `DynamicItem` pattern, defer discipline
- `.planning/research/PITFALLS.md` — Pitfall #2 (Views vanish), #3 (3s ack cliff), #4 (rate-limit cratering)

### External libraries
- [discord.py 2.7.1 docs](https://discordpy.readthedocs.io/en/v2.7.1/) — Bot, app_commands, ui.Button, ui.View, ui.DynamicItem, Interaction.response, Interaction.followup
- [discord.py persistent.py example](https://github.com/Rapptz/discord.py/blob/master/examples/views/persistent.py) — official pattern
- [discord.py DynamicItem docs](https://discordpy.readthedocs.io/en/v2.7.1/interactions/api.html#dynamicitem) — regex template pattern
- [dpytest docs](https://dpytest.readthedocs.io/) — test harness (verify 2.7 compat)

</canonical_refs>

<code_context>
## Existing Code Insights

### Phase 1 delivered
- Persistence layer (4 tables, WAL, WriterQueue, repositories, pydantic models)
- MCP client (httpx + tenacity + circuit breaker + 28 typed wrappers)
- Sanitizer (control-token strip, 500-char cap, sentinel wrap, adversarial corpus passing)
- Test infrastructure (177 tests, conftests, fixtures)
- pre-commit hooks (ruff) + import-linter contracts

### Reusable Assets
- `Settings.discord_token`, `Settings.discord_guild_ids` — already in `src/eldritch_dm/config.py`
- `Settings.embed_edit_rate_limit` — env var documented, default 1.0
- `structlog` setup with JSON/console renderer toggle
- `tests/conftest.py` has `settings_factory` fixture pattern to extend
- `import-linter` contracts already enforce that `mcp/`, `safety/`, `persistence/` are hermetic. Phase 2 adds `bot/` as the integration layer — its contract allows imports FROM the other three but no module outside `bot/` may import from `bot/`.

### Established Patterns
- Pydantic v2 frozen models for repo I/O
- Async repository methods return models; writes submit through WriterQueue
- Atomic commits per logical unit
- Tests gated behind `RUN_*` env vars when expensive (e.g. `RUN_STRESS=1`); restart-drill should similarly be gated behind `RUN_INTEGRATION=1` if it's slow

### Integration Points
- Phase 3 will register `cogs/lobby.py` and `cogs/ingest.py` against the bot — Phase 2 must make `cogs/` an opt-in subpackage that's straightforward to extend
- Phase 4 will register `cogs/exploration.py`, `cogs/combat.py` — same extensibility constraint
- Phase 5 will subclass `RiposteButton` or extend its callback — keep `DynamicItem` subclasses easy to subclass

</code_context>

<specifics>
## Specific Ideas

- The defer discipline rule (EDM001) is the **single most important deliverable in Phase 2**. If we ship buttons that occasionally hang for 3+ seconds and someone forgets to defer, the bot looks broken to players. Make this loud and impossible to skip.
- The kill-and-restart drill is the proof we have persistent state — without it we can't claim BOT-08. Make it visible (perhaps a `tests/bot/test_restart_drill.py` that gets called out in the CI summary).
- Embed coalescer is small but easy to get wrong. Risk: a race where an update arrives during the sleep window but before the next wake — the next wake should pick it up, not skip a cycle. Researcher should look up `asyncio.Event` vs `asyncio.Condition` patterns for "latest-value pubsub".
- `dpytest` compatibility with discord.py 2.7 is uncertain. If the researcher finds it's broken, we fall back to mocking — but say so explicitly so we don't waste plan time wiring up a broken harness.

</specifics>

<deferred>
## Deferred Ideas

- Multi-server (multi-guild) deployment dashboard — single-guild use case is fine for v1
- Custom Discord audit-log integration — defer to v2
- Slash command localization — defer; English only in v1
- Voice channel integration (TTS narration) — explicitly v2 per PROJECT.md Out of Scope
- Embed coalescer adaptive rate (dynamically slow down on observed 429s) — fixed-rate is fine for v1
- Application emoji registration — use Unicode emoji for v1

</deferred>

---

*Phase: 02-discord-scaffold-persistent-views*
*Context gathered: 2026-05-21*
