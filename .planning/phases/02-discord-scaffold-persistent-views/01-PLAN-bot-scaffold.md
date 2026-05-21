---
phase: 02-discord-scaffold-persistent-views
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - src/eldritch_dm/bot/__init__.py
  - src/eldritch_dm/bot/__main__.py
  - src/eldritch_dm/bot/bot.py
  - src/eldritch_dm/bot/cogs/__init__.py
  - src/eldritch_dm/bot/cogs/diagnostics.py
  - tests/bot/__init__.py
  - tests/bot/conftest.py
  - tests/bot/test_bot_lifecycle.py
  - tests/bot/test_cog_diagnostics.py
autonomous: true
requirements: [BOT-01, OPS-04]

must_haves:
  truths:
    - "An `EldritchBot(commands.Bot)` class exists and can be instantiated against a `Settings` instance without contacting Discord."
    - "A process entrypoint `python -m eldritch_dm.bot` is wired and reads `Settings`."
    - "`/ping` and `/status` slash commands are registered on the tree and resolve via real repos / MCP client (mocked in tests)."
    - "`setup_hook` boots persistence (schema bootstrap + WriterQueue) and the MCP health task — failures are fatal."
    - "Graceful `close()` cancels health task + WriterQueue cleanly (OPS-04 scaffolding in place; full drain wired in Plan 03)."
    - "`bot/` may import from `mcp/`, `persistence/`, `safety/`, `config`, `logging` and NOTHING outside `bot/` may import from `bot/` — enforced by import-linter."
  artifacts:
    - path: "src/eldritch_dm/bot/bot.py"
      provides: "EldritchBot class with setup_hook + close override"
    - path: "src/eldritch_dm/bot/__main__.py"
      provides: "Process entrypoint"
    - path: "src/eldritch_dm/bot/cogs/diagnostics.py"
      provides: "/ping + /status cog"
    - path: "tests/bot/conftest.py"
      provides: "bot_factory + interaction_factory fixtures"
    - path: "pyproject.toml"
      provides: "dev deps + bot import-linter contract"
  key_links:
    - from: "src/eldritch_dm/bot/bot.py"
      to: "src/eldritch_dm/persistence/connection.py"
      via: "PersistenceManager / WriterQueue start in setup_hook"
    - from: "src/eldritch_dm/bot/cogs/diagnostics.py"
      to: "src/eldritch_dm/mcp/health.py"
      via: "get_circuit_state(bot.circuit_breaker) call in /ping"
    - from: "src/eldritch_dm/bot/cogs/diagnostics.py"
      to: "src/eldritch_dm/persistence/channel_sessions_repo.py"
      via: "ChannelSessionRepo.get(channel_id) in /status"
---

<objective>
Stand up the `discord.py` bot scaffold for EldritchDM: an `EldritchBot(commands.Bot)` subclass, process entrypoint, extensible cogs subpackage, and a `diagnostics` cog with `/ping` (MCP health) and `/status` (channel session readout). Wire `setup_hook` to boot persistence (schema, WriterQueue) and the MCP health-check task; wire `close()` to shut them down. Add a `bot/`-scoped import-linter contract. NO gameplay commands. NO persistent views yet (Plan 02 + 03).

Purpose: Phases 3-5 attach cogs and persistent views to a running bot. This plan provides the bone structure they hang off of, plus the testing harness future phases will reuse.

Output: Importable `eldritch_dm.bot` subpackage; runnable `python -m eldritch_dm.bot`; lifecycle + diagnostics tests green.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/02-discord-scaffold-persistent-views/02-CONTEXT.md
@.planning/phases/02-discord-scaffold-persistent-views/02-RESEARCH.md
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@src/eldritch_dm/config.py
@src/eldritch_dm/logging.py
@src/eldritch_dm/mcp/client.py
@src/eldritch_dm/mcp/health.py
@src/eldritch_dm/persistence/__init__.py
@src/eldritch_dm/persistence/connection.py
@src/eldritch_dm/persistence/bootstrap.py
@src/eldritch_dm/persistence/channel_sessions_repo.py
@pyproject.toml

<interfaces>
Key Phase 1 exports the bot composes:

From `eldritch_dm.config`:
  - `class Settings(BaseSettings)` with `discord_token: str`, `discord_application_id: int | None`,
    `discord_guild_ids: str` (use `.guild_ids_list` -> `list[int]`), `omlx_endpoint: AnyHttpUrl`,
    `mcp_execute_url: AnyHttpUrl`, `omlx_health_interval: PositiveInt`,
    `omlx_circuit_breaker_threshold: PositiveInt`, `eldritch_db_path: str`,
    `embed_edit_rate_limit: PositiveFloat`.
  - `get_settings() -> Settings` (lru_cached).

From `eldritch_dm.logging`:
  - `get_logger(name: str) -> structlog.BoundLogger`
  - Setup function (whatever name it exports) — call once in `__main__.py` before constructing bot.

From `eldritch_dm.persistence`:
  - `WriterQueue` — async writer thread; `await wq.start()` / `await wq.stop()`.
  - `open_connection(db_path)` — read-only context manager (not used directly by bot scaffold).
  - `ChannelSessionRepo(db_path, writer_queue)` — `.get(channel_id) -> ChannelSession | None`,
    `.list_active() -> list[ChannelSession]`.
  - `ChannelSession` (frozen pydantic), `ChannelState` (StrEnum: LOBBY, EXPLORATION, COMBAT_INIT, COMBAT, NPC_DLG, PAUSED).

From `eldritch_dm.persistence.bootstrap`:
  - `ensure_schema(db_path: str) -> None` (idempotent).

From `eldritch_dm.mcp.client`:
  - `MCPClient(base_url, *, circuit_breaker=None, ...)`; `.call(tool_name, **kwargs)`; `.aclose()`.

From `eldritch_dm.mcp.health`:
  - `class CircuitBreaker(threshold=3)`; `.state: CircuitState`; `.record_success() / .record_failure()`.
  - `class CircuitState(StrEnum)` — `CLOSED`, `OPEN`.
  - `class HealthCheck(endpoint, *, interval, breaker, http_client=None)`; `await hc.start()` / `await hc.stop()`.
  - `get_circuit_state(breaker) -> CircuitState`.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add dev deps + bot/ import-linter contract</name>
  <files>pyproject.toml</files>
  <action>
    Update `pyproject.toml`:

    1. Under `[project.optional-dependencies].dev`, add (preserve existing entries):
       - `pytest-mock>=3.12,<4.0` — fixture-style mocker used in bot lifecycle tests
       - `syrupy>=4.6,<5.0` — snapshot library for embed tests in Plan 02 (declare now so Plan 02 doesn't churn pyproject)
       - `dpytest>=0.7,<1.0` — OPTIONAL. Add only if `02-RESEARCH.md` Q3 confirms 2.7.1 compatibility; otherwise omit and leave a `# TODO(02-RESEARCH): dpytest deferred — see Q3` comment in the dev array.

    2. Add a new import-linter contract block AFTER the existing four contracts:
       ```
       [[tool.importlinter.contracts]]
       name = "nothing outside bot may import from bot"
       type = "forbidden"
       source_modules = [
         "eldritch_dm.config",
         "eldritch_dm.logging",
         "eldritch_dm.mcp",
         "eldritch_dm.persistence",
         "eldritch_dm.safety",
       ]
       forbidden_modules = ["eldritch_dm.bot"]
       ```
       Rationale (comment above the block): bot/ is the integration layer; subsystems must remain hermetic and testable without Discord.

    3. Remove the stale `# TODO: bot submodule ...` note in the import-linter section header — it is now obsolete.

    Do NOT add a contract restricting what bot/ imports — it is the integration layer and is allowed to depend on everything in eldritch_dm.

    Commit: `chore(02-discord-scaffold-persistent-views): add bot import-linter contract and dev deps`
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM && uv pip install -e '.[dev]' --quiet && lint-imports</automated>
  </verify>
  <done>`lint-imports` passes with the new contract; dev deps install cleanly.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create EldritchBot + cogs subpackage + entrypoint + diagnostics</name>
  <files>
    src/eldritch_dm/bot/__init__.py,
    src/eldritch_dm/bot/__main__.py,
    src/eldritch_dm/bot/bot.py,
    src/eldritch_dm/bot/cogs/__init__.py,
    src/eldritch_dm/bot/cogs/diagnostics.py
  </files>
  <behavior>
    - `EldritchBot.__init__` accepts a `Settings` and stores it as `self.settings`; constructs an `Intents.default()` with `message_content = False`; passes `command_prefix="!"` (unused but required by `commands.Bot`); passes `application_id=settings.discord_application_id`; no MCP/DB I/O in `__init__`.
    - `EldritchBot.setup_hook` (async) executes IN ORDER (per D-24): (a) `ensure_schema(settings.eldritch_db_path)`, (b) construct + start `WriterQueue` → store on `self.writer_queue`, (c) construct `CircuitBreaker(threshold=settings.omlx_circuit_breaker_threshold)` → store on `self.circuit_breaker`, (d) construct `MCPClient(str(settings.omlx_endpoint).rstrip('/v1').rstrip('/'), circuit_breaker=self.circuit_breaker)` → store on `self.mcp`, (e) construct `HealthCheck(str(settings.omlx_endpoint), interval=settings.omlx_health_interval, breaker=self.circuit_breaker)` → `await health.start()` → store on `self.health`, (f) construct `ChannelSessionRepo(settings.eldritch_db_path, self.writer_queue)` → store on `self.channel_sessions_repo`, (g) load cogs via `await self.load_extension("eldritch_dm.bot.cogs.diagnostics")`, (h) sync app commands: if `settings.guild_ids_list` non-empty, sync per guild; else `await self.tree.sync()`. Log `setup_hook_ok` with counts. (Persistent-view rehydration is deferred to Plan 03 — leave a `# Plan 03: rehydrate persistent_views here` comment placeholder.)
    - `setup_hook` errors propagate (D-25); bot does NOT connect on failure.
    - `EldritchBot.close()` override (D-26 scaffolding): cancel/stop `self.health`, stop `self.writer_queue`, `await self.mcp.aclose()`, then `await super().close()`. Full WriterQueue drain timeout is wired in Plan 03 — for now a best-effort `.stop()` is fine.
    - `__main__.py`: call logging setup, build `Settings`, `bot = EldritchBot(settings)`, `bot.run(settings.discord_token)`. Wrap in `if __name__ == "__main__": main()`.
    - `cogs/diagnostics.py` defines `class Diagnostics(commands.Cog)` and `async def setup(bot: EldritchBot) -> None: await bot.add_cog(Diagnostics(bot))`. Module docstring states `SCOPE WALL: Phase 2 only ships /ping and /status. Gameplay commands (/start_game, /upload_character_*, /declare_action, etc.) land in Phases 3–5 in their own cogs.`
    - `/ping` (app_commands.command): first line `await interaction.response.defer(thinking=True, ephemeral=True)` (D-09 — Plan 03 will lint-enforce, write it correctly NOW); then binds structlog context `command="ping"`, `channel_id`, `user_id`; reads `state = get_circuit_state(self.bot.circuit_breaker)`; reads tool count from `self.bot.mcp` via `len(self.bot.mcp._tools)` if exposed — otherwise just report circuit state + endpoint URL; sends via `interaction.followup.send(content=..., ephemeral=True)`.
    - `/status` (app_commands.command): first line defer (ephemeral); fetch `session = await self.bot.channel_sessions_repo.get(str(interaction.channel_id))`; followup with either "No active session in this channel" or a formatted `state=...; campaign=...; created_at=...`. No embeds yet — those land in Plan 02. Plain text only.
    - Both callbacks: structured log on entry AND exit (D-38).

    Tests (test_cog_diagnostics.py — written FIRST):
    - Test 1: `/ping` callback, with `bot.circuit_breaker.state == CLOSED`, sends followup containing `"CLOSED"` and the endpoint substring.
    - Test 2: `/ping` callback, after forcing `record_failure` × threshold so state == OPEN, sends followup containing `"OPEN"`.
    - Test 3: `/status` with no row → followup contains "No active session".
    - Test 4: `/status` with an upserted ChannelSession (state=EXPLORATION, campaign="Curse of Strahd") → followup contains both strings.
    - Test 5: `/ping` callback's first observable await is `interaction.response.defer(...)` (assert via a mock that records call order — defer must be called before followup).
    Mock `discord.Interaction` via `pytest-mock`'s `MagicMock` with `AsyncMock` for `response.defer` and `followup.send`; set `.channel_id`, `.user.id`, `.guild_id`.

    NEVER call the real Discord API in tests.
  </behavior>
  <action>
    Implement the modules per the `<behavior>` block. Key implementation notes:
    - `bot/__init__.py`: re-export `EldritchBot` and `__all__ = ["EldritchBot"]`.
    - `EldritchBot` subclasses `discord.ext.commands.Bot`.
    - `setup_hook` uses `await self.tree.sync(guild=discord.Object(id=gid))` for each guild in `settings.guild_ids_list`, else global sync. Log count returned by `sync()`.
    - `cogs/__init__.py`: empty module docstring noting future cogs will be auto-loadable here.
    - All callbacks use `app_commands.command(name=..., description=...)`, declared INSIDE the Cog as decorated methods (per discord.py 2.7 pattern). Per D-04: bot intents must have `message_content=False`.
    - When the MCP client doesn't expose `_tools` publicly, omit tool-count from `/ping` output and just include endpoint + circuit state.
    - Run tests via `pytest tests/bot/test_cog_diagnostics.py -x` — should fail until implementation lands, then pass.

    Commit 1 (RED): `test(02-discord-scaffold-persistent-views): add failing diagnostics cog tests`
    Commit 2 (GREEN): `feat(02-discord-scaffold-persistent-views): EldritchBot subclass with diagnostics cog (/ping, /status)`
    Commit 3 (CHORE): `feat(02-discord-scaffold-persistent-views): bot process entrypoint (__main__)`
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM && pytest tests/bot/test_cog_diagnostics.py -x -q</automated>
  </verify>
  <done>All 5 cog tests pass; `python -c "from eldritch_dm.bot import EldritchBot"` succeeds; `python -c "import eldritch_dm.bot.__main__"` does NOT raise (entrypoint module loadable without DISCORD_TOKEN set when not under __main__).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Bot lifecycle test + conftest fixtures for downstream cogs</name>
  <files>
    tests/bot/__init__.py,
    tests/bot/conftest.py,
    tests/bot/test_bot_lifecycle.py
  </files>
  <behavior>
    `tests/bot/conftest.py` provides reusable fixtures consumed across Plans 02/03 and Phases 3-5:

    - `tmp_db_path(tmp_path) -> str` — returns a path string under `tmp_path` for an isolated SQLite file.
    - `bot_settings(tmp_db_path, monkeypatch) -> Settings` — builds a Settings with `discord_token="test-token"`, `discord_guild_ids=""`, `eldritch_db_path=tmp_db_path`, `omlx_health_interval=3600` (effectively disabled in unit tests). Monkeypatches env vars to avoid .env file interference.
    - `bot_factory(bot_settings) -> Callable[[], Awaitable[EldritchBot]]` — async factory that constructs `EldritchBot(bot_settings)`, runs `setup_hook()` against a real tmp DB, returns the bot. Caller is responsible for `await bot.close()` (or use the `running_bot` fixture).
    - `running_bot(bot_factory) -> AsyncIterator[EldritchBot]` — async fixture that yields a bot from `bot_factory()` and cleans up via `await bot.close()` in teardown.
    - `interaction_factory() -> Callable[..., discord.Interaction]` — builds a `MagicMock(spec=discord.Interaction)` with `AsyncMock` for `.response.defer`, `.response.send_message`, `.followup.send`; configurable `channel_id`, `user.id`, `guild_id`, `data` (custom_id payload). Returns a fresh mock per call.

    All fixtures are async-aware where needed (pytest-asyncio `auto` mode is already configured).

    `test_bot_lifecycle.py`:
    - Test 1 — `test_setup_hook_initializes_subsystems`: build bot via `bot_factory`, assert after setup_hook: `bot.writer_queue` is started, `bot.circuit_breaker.state == CircuitState.CLOSED`, `bot.mcp` exists, `bot.health` exists, schema file at `tmp_db_path` has the four tables (query sqlite_master), Diagnostics cog is loaded (`bot.get_cog("Diagnostics") is not None`).
    - Test 2 — `test_close_cleanly_shuts_down`: build bot, call `await bot.close()`, assert `bot.health._task` is None or cancelled, MCP client closed (set a sentinel flag via spy), no warnings emitted to logs. Use `pytest-mock` to spy on `health.stop` / `mcp.aclose` / `writer_queue.stop` to assert each was awaited.
    - Test 3 — `test_setup_hook_failure_is_fatal`: monkeypatch `bootstrap.ensure_schema` to raise RuntimeError; assert calling `await bot.setup_hook()` re-raises (does not swallow). Ensures D-25.
    - Test 4 — `test_intents_are_minimal`: build bot; assert `bot.intents.message_content is False` (D-04 security choice).
    - Test 5 — `test_no_guild_sync_when_empty`: build bot with `discord_guild_ids=""`; spy on `bot.tree.sync`; assert it was called WITHOUT a `guild=` kwarg (global sync path). Use `AsyncMock` on `tree.sync` via monkeypatch (we never want to hit Discord in tests).
    - Test 6 — `test_per_guild_sync_when_configured`: build bot with `discord_guild_ids="123,456"`; spy on `tree.sync`; assert called twice with `guild=` set to a Discord Object whose id is 123 and 456 respectively.
  </behavior>
  <action>
    Implement conftest + lifecycle tests.

    Pattern for spying on `tree.sync` without hitting Discord: replace `bot.tree.sync` with an `AsyncMock(return_value=[])` *before* calling `setup_hook` (a fixture or test-scoped monkeypatch). Same for `health.start` if it would otherwise spawn an unwanted task — set `omlx_health_interval` high enough that the first tick never fires inside the test window.

    For Test 1 schema check: open an `aiosqlite.connect(tmp_db_path)` and `SELECT name FROM sqlite_master WHERE type='table'`; expect `{"channel_sessions", "persistent_views", "riposte_timers", "sanitizer_audit"}` ⊆ result.

    NEVER call `bot.run` or `bot.start` — they would attempt a real gateway connection. Only call `setup_hook` and `close`.

    Commit 1 (RED): `test(02-discord-scaffold-persistent-views): add failing bot lifecycle tests + fixtures`
    Commit 2 (GREEN): if the lifecycle behaviors fail because Task 2 missed an edge case (e.g. close ordering), fix `bot.py` and commit `fix(02-discord-scaffold-persistent-views): tighten EldritchBot.close ordering`. If tests pass against Task 2's implementation as-is, this commit is omitted.
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM && pytest tests/bot -x -q && lint-imports</automated>
  </verify>
  <done>All 6 lifecycle tests pass; all 5 diagnostics tests still pass; `lint-imports` clean; `pytest tests -x -q` shows green (177 existing + new bot tests).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Discord gateway → bot | Untrusted slash-command input crosses here (channel_id, user_id, command name; no free text yet — that's Phase 3) |
| Bot → MCP (dm20) | Internal trust boundary; circuit-breaker protects bot from misbehaving MCP |
| Bot → local SQLite | Trusted; only the bot writes |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-01 | Information disclosure | `/ping` response | mitigate | Send ephemeral (`ephemeral=True` in defer + followup) so circuit state isn't broadcast to the channel |
| T-02-02 | Information disclosure | `/status` response | mitigate | Ephemeral followup; do NOT include `dm20_party_token` in the payload (only state + campaign_name + created_at) |
| T-02-03 | Tampering | `Intents.message_content` | mitigate | Set `message_content=False` (D-04) — bot cannot read raw DMs / messages, can only be invoked via slash commands |
| T-02-04 | Denial of service | `setup_hook` partial failure | mitigate | Failures are fatal (D-25); bot does NOT connect on partial init — prevents a half-up bot accepting interactions it cannot service |
| T-02-05 | Repudiation | Slash command invocations | mitigate | Every callback binds structlog context (`channel_id`, `user_id`, `command`) on entry + exit — auditable trail |
| T-02-06 | Elevation of privilege | `discord_application_id` env var | accept | Self-host model: user controls their own bot token + app id; out-of-band leak is the user's responsibility |
| T-02-SC | Tampering | `pytest-mock`, `syrupy` pip installs | mitigate | Both are well-established packages (>5y on PyPI, millions of downloads); no `[ASSUMED]`/`[SUS]` rating expected. Researcher's Package Legitimacy Audit in 02-RESEARCH.md confirms before install — if either lands `[ASSUMED]`, insert a blocking-human checkpoint before the `uv pip install` in Task 1. |
</threat_model>

<verification>
- `lint-imports` exits 0 with new `bot/` contract.
- `pytest tests -x -q` is green (Phase 1's 177 tests + the 11 new bot tests).
- `python -m eldritch_dm.bot --help` does NOT raise (entrypoint loadable without real Discord token, assuming `__main__` only calls `bot.run` inside `main()`).
- Manual smoke (developer): `DISCORD_TOKEN=... python -m eldritch_dm.bot` connects, `/ping` and `/status` respond ephemerally. This is OPTIONAL for Plan 01 — a real Discord smoke can happen at end of Plan 03 once persistent views are wired.
</verification>

<success_criteria>
- `EldritchBot` exists, importable, instantiable with a `Settings`.
- `setup_hook` boots persistence + MCP health + Diagnostics cog; failures are fatal.
- `/ping` returns ephemeral MCP health (circuit state + endpoint).
- `/status` returns ephemeral channel-session readout or a "no session" message.
- Conftest fixtures (`bot_factory`, `running_bot`, `interaction_factory`) ready for Plans 02/03 + Phases 3-5 to reuse.
- `bot/` is firewalled OUT by import-linter (nothing else imports it).
</success_criteria>

<output>
Create `.planning/phases/02-discord-scaffold-persistent-views/02-01-SUMMARY.md` when done.
</output>
