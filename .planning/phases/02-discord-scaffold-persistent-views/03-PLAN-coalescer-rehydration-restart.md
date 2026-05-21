---
phase: 02-discord-scaffold-persistent-views
plan: 03
type: execute
wave: 3
depends_on: ["01", "02"]
files_modified:
  - src/eldritch_dm/bot/coalescer.py
  - src/eldritch_dm/bot/setup_hook.py
  - src/eldritch_dm/bot/bot.py
  - src/eldritch_dm/lint/__init__.py
  - src/eldritch_dm/lint/edm001.py
  - tools/lint_defer_discipline.py
  - .pre-commit-config.yaml
  - tests/bot/test_coalescer.py
  - tests/bot/test_setup_hook.py
  - tests/bot/test_restart_drill.py
  - tests/bot/test_defer_discipline.py
  - .planning/phases/02-discord-scaffold-persistent-views/02-SUMMARY.md
autonomous: true
requirements: [BOT-02, BOT-05, BOT-06, BOT-08, OPS-04]

must_haves:
  truths:
    - "`EmbedCoalescer(message)` batches rapid updates into ≤1 `message.edit` per `embed_edit_rate_limit` seconds; latest-value semantics — mid-sleep overwrites are not lost."
    - "`setup_hook` rehydrates `persistent_views` rows: for each row, builds a View with the right DynamicItems and calls `bot.add_view(view, message_id=int(row.message_id))`."
    - "After a simulated restart (fresh bot, same DB), a dispatched Interaction with a matching `custom_id` reaches the corresponding DynamicItem's `callback` (BOT-08, D-36)."
    - "EDM001 lint rule catches interaction callbacks whose first non-trivial statement is NOT `await interaction.response.defer(...)` (or `send_modal`); it ignores `# noqa: EDM001` exceptions (D-12)."
    - "EDM001 is wired into `.pre-commit-config.yaml`; CI will fail on violations."
    - "`bot.close()` does a proper graceful shutdown (OPS-04): cancels health task, drains WriterQueue with a 5s timeout, closes MCP httpx pool, closes DB connections."
  artifacts:
    - path: "src/eldritch_dm/bot/coalescer.py"
      provides: "EmbedCoalescer class with asyncio Event-driven render loop"
    - path: "src/eldritch_dm/bot/setup_hook.py"
      provides: "rehydrate_persistent_views(bot, repo) callable in isolation"
    - path: "src/eldritch_dm/lint/edm001.py"
      provides: "AST-based defer-discipline checker"
    - path: "tests/bot/test_restart_drill.py"
      provides: "kill-and-restart integration proof of BOT-08"
    - path: ".pre-commit-config.yaml"
      provides: "EDM001 hook wired"
  key_links:
    - from: "src/eldritch_dm/bot/setup_hook.py"
      to: "src/eldritch_dm/persistence/persistent_views_repo.py"
      via: "PersistentViewRepo.list_by_channel for each active channel session (or list-all helper)"
    - from: "src/eldritch_dm/bot/bot.py:setup_hook"
      to: "src/eldritch_dm/bot/setup_hook.py:rehydrate_persistent_views"
      via: "called after add_dynamic_items, before tree.sync"
    - from: ".pre-commit-config.yaml"
      to: "src/eldritch_dm/lint/edm001.py"
      via: "language: python, entry: eldritch_dm.lint.edm001:main"
---

<objective>
Close out Phase 2 with the three deliverables that prove the scaffold is production-credible: (1) the embed update **coalescer** that prevents Phase 4 combat from rate-limiting Discord, (2) **persistent-view rehydration** wired into `setup_hook` so buttons survive bot restarts, and (3) the **EDM001 defer-discipline lint rule** that makes the project's most important Discord-correctness invariant impossible to violate silently. Crown the phase with a **kill-and-restart drill** test that exercises rehydration end-to-end. Tighten `bot.close()` graceful-shutdown to fully satisfy OPS-04. Write Phase 2 SUMMARY.

Purpose: BOT-02, BOT-05, BOT-06, BOT-08, and OPS-04 all land here. Without this plan, Phase 2 cannot ship.

Output: Coalescer module, extracted setup_hook helpers, EDM001 lint + pre-commit hook, integration test for restart drill, Phase 2 SUMMARY.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/02-discord-scaffold-persistent-views/02-CONTEXT.md
@.planning/phases/02-discord-scaffold-persistent-views/02-RESEARCH.md
@.planning/phases/02-discord-scaffold-persistent-views/02-01-SUMMARY.md
@.planning/phases/02-discord-scaffold-persistent-views/02-02-SUMMARY.md
@src/eldritch_dm/bot/bot.py
@src/eldritch_dm/bot/dynamic_items.py
@src/eldritch_dm/bot/embeds.py
@src/eldritch_dm/bot/warnings.py
@src/eldritch_dm/persistence/persistent_views_repo.py
@src/eldritch_dm/persistence/channel_sessions_repo.py
@src/eldritch_dm/config.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: EmbedCoalescer — per-message rate-limited update queue</name>
  <files>
    src/eldritch_dm/bot/coalescer.py,
    tests/bot/test_coalescer.py
  </files>
  <behavior>
    Module exports (`coalescer.py`):

    - `class EmbedCoalescer`:
      Constructor: `__init__(self, message: discord.Message, *, rate_limit_seconds: float = 1.0, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None`. (Inject `clock`/`sleep` for testability; default to monotonic + asyncio.sleep.)

      State: `_pending: tuple[discord.Embed, discord.ui.View | None] | None = None`, `_dirty: asyncio.Event`, `_render_task: asyncio.Task | None = None`, `_abandoned: bool = False`, `_last_edit_t: float = -inf`.

      API:
      - `async def update(self, embed: discord.Embed, *, view: discord.ui.View | None = None) -> None` — overwrites `_pending`; sets `_dirty`. If `_abandoned`, no-op. Starts the render task lazily if not yet running.
      - `async def close(self) -> None` — cancel render task; await its completion; do NOT issue further edits.
      - Internal `_render_loop(self)`:
        ```
        while not self._abandoned:
            await self._dirty.wait()
            self._dirty.clear()
            # If we edited too recently, sleep just enough to respect the rate
            elapsed = self._clock() - self._last_edit_t
            if elapsed < self._rate_limit_seconds:
                await self._sleep(self._rate_limit_seconds - elapsed)
            payload = self._pending
            if payload is None:
                continue
            embed, view = payload
            try:
                await self._message.edit(embed=embed, view=view)
                self._last_edit_t = self._clock()
            except discord.NotFound:
                self._abandoned = True
                logger.warning("coalescer_message_gone", message_id=self._message.id)
                return
            except discord.Forbidden:
                self._abandoned = True
                logger.warning("coalescer_message_forbidden", message_id=self._message.id)
                return
            except discord.HTTPException as exc:
                logger.warning("coalescer_http_error", status=getattr(exc, "status", None), error=str(exc))
                # do NOT abandon on transient HTTP errors; loop will retry on next dirty signal
                continue
        ```
      Latest-value semantics (D-28): a `_pending` overwrite during the sleep window is picked up on the NEXT iteration — not skipped, not lost. The Event-based design ensures this.

    Tests (`test_coalescer.py`) — fake clock + fake sleep:
    - Test 1 — first-update-immediate: with `_last_edit_t = -inf`, an `update` triggers `message.edit` after one event-loop tick, no sleep needed.
    - Test 2 — rate-limit: two rapid `update` calls (0s and 0.1s apart) produce TWO `edit` calls but the SECOND is delayed until ~1s has passed since the first. Use a fake `clock`/`sleep` to assert sleep was called with ~0.9s.
    - Test 3 — latest-value: 5 rapid updates within the rate-limit window result in: first edit fires immediately, then exactly ONE more edit (with the 5th payload) after rate_limit_seconds — not 5 edits. Earlier 2nd/3rd/4th payloads are overwritten before being sent.
    - Test 4 — abandoned-on-NotFound: `message.edit` raises `discord.NotFound`; coalescer flips `_abandoned=True`; subsequent `update` calls do nothing; render task exits cleanly.
    - Test 5 — abandoned-on-Forbidden: same shape as Test 4 but with `discord.Forbidden`.
    - Test 6 — transient-HTTP-error: `message.edit` raises `discord.HTTPException(status=503)`; coalescer does NOT abandon; the next `update` produces an edit attempt. (Use a side-effect list that raises once then succeeds.)
    - Test 7 — close-cancels: starting a render task then calling `close()` cancels it within 100ms; no edits happen after close.
    - Test 8 — env-driven rate: `EmbedCoalescer(message, rate_limit_seconds=settings.embed_edit_rate_limit)` — verify the default Settings value 1.0 is respected.

    Use a custom `FakeMessage` class with an `AsyncMock` `.edit` and `.id = 12345`. Inject `clock`/`sleep` as fakes so tests are deterministic and fast (<1s total).
  </behavior>
  <action>
    Implement per `<behavior>`. Critical bug to avoid: do NOT use a queue (D-28 explicitly says overwrite, not enqueue). Use an `asyncio.Event` + a single `_pending` slot.

    Race condition to avoid: between `_dirty.clear()` and reading `_pending`, a new `update` could fire. That's fine — `_pending` will be the newer payload. If a new `update` arrives during `await self._message.edit(...)`, it will set `_dirty` again, and the next iteration picks it up. This is the correct latest-value semantics.

    Commit 1 (RED): `test(02-discord-scaffold-persistent-views): add failing EmbedCoalescer tests`
    Commit 2 (GREEN): `feat(02-discord-scaffold-persistent-views): EmbedCoalescer with latest-value rate limiting`
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM && pytest tests/bot/test_coalescer.py -x -q</automated>
  </verify>
  <done>All 8 coalescer tests pass; full test suite still green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Persistent-view rehydration in setup_hook + graceful shutdown</name>
  <files>
    src/eldritch_dm/bot/setup_hook.py,
    src/eldritch_dm/bot/bot.py,
    tests/bot/test_setup_hook.py
  </files>
  <behavior>
    New module `setup_hook.py` extracts testable helpers:

    - `def build_view_for_row(row: PersistentView) -> discord.ui.View | None`:
      Inspects `row.view_class` (one of `"ReadyButton"`, `"DeclareActionButton"`, `"EndTurnButton"`, `"RiposteButton"`) and constructs an empty `discord.ui.View(timeout=None)` containing a single DynamicItem of that class with fields parsed from `row.custom_id` via the class's `template.fullmatch`. Returns `None` and logs `WARNING rehydration_unknown_class` if the class name isn't recognized — the view is skipped, the bot still boots.

    - `async def rehydrate_persistent_views(bot: discord.Client, repo: PersistentViewRepo, channel_sessions_repo: ChannelSessionRepo) -> int`:
      1. `sessions = await channel_sessions_repo.list_active()`
      2. For each session: `rows = await repo.list_by_channel(session.channel_id)`
      3. For each row: `view = build_view_for_row(row)`; if not None: `bot.add_view(view, message_id=int(row.message_id))`; increment counter
      4. Log INFO `"rehydrated N persistent views from M channel sessions"` (D-39).
      5. Return total view count.

    Update `bot.py:EldritchBot.setup_hook` (touching the Plan 03 placeholder):
    - After loading cogs and constructing `self.channel_sessions_repo`, also construct `self.persistent_views_repo = PersistentViewRepo(settings.eldritch_db_path, self.writer_queue)`.
    - Call `self.add_dynamic_items(*DYNAMIC_ITEM_CLASSES)` (the registry call from D-24 step 4).
    - Call `count = await rehydrate_persistent_views(self, self.persistent_views_repo, self.channel_sessions_repo)`.
    - Then sync tree (D-24 step 6); the final log line in setup_hook should match D-39: `"setup_hook_ok"`, `rehydrated_views=count`, `sessions=len(sessions)`, `synced_commands=...`.

    Tighten `EldritchBot.close()` (OPS-04 — D-26 full version):
    - `await self.health.stop()` (if exists)
    - `await asyncio.wait_for(self.writer_queue.stop(drain=True), timeout=5.0)` — catch `TimeoutError`, log `writer_queue_drain_timeout`, continue
    - `await self.mcp.aclose()` (if exists)
    - `await super().close()`
    - Each step inside try/except to ensure subsequent steps still run; log each step's outcome.

    (NOTE: the actual kwarg name for WriterQueue.stop — `drain` vs `wait` vs none — must match the Phase 1 API. If `WriterQueue.stop()` doesn't take a `drain` flag, just call `await self.writer_queue.stop()` inside `wait_for(..., timeout=5.0)`. Check the existing signature before writing the call.)

    Tests (`test_setup_hook.py`):
    - Test 1 — `build_view_for_row` parametric over all 4 view_class strings: produces a View whose single child is the expected DynamicItem subclass with the expected captured fields.
    - Test 2 — `build_view_for_row` with unknown view_class string: returns None, logs a warning, does not raise.
    - Test 3 — `rehydrate_persistent_views` happy path: seed `channel_sessions` with 2 active rows; seed `persistent_views` with 3 rows total (2 in channel A, 1 in channel B); spy on `bot.add_view`; call helper; assert `add_view` called 3 times with the correct `message_id` int values; returned count == 3.
    - Test 4 — empty DB: helper returns 0; `add_view` never called.
    - Test 5 — bot graceful shutdown: build bot via `bot_factory`, mock-spy `writer_queue.stop`, `health.stop`, `mcp.aclose`; call `bot.close()`; assert each was awaited; assert ordering (health stopped BEFORE writer_queue drains BEFORE mcp closes).
    - Test 6 — writer_queue drain timeout: monkeypatch `writer_queue.stop` to sleep 10s; `bot.close()` returns within ~5s (use `asyncio.wait_for` assert) and logs the timeout warning.
  </behavior>
  <action>
    Implement per `<behavior>`.

    For Test 5 ordering assertion: attach a single `call_order: list[str]` list shared across mocks; each mock's side_effect appends its name. Assert the list equals `["health", "writer_queue", "mcp"]` (super().close ordering follows).

    Commit 1 (RED): `test(02-discord-scaffold-persistent-views): add failing setup_hook rehydration + graceful-shutdown tests`
    Commit 2 (GREEN): `feat(02-discord-scaffold-persistent-views): persistent-view rehydration + tightened bot.close (OPS-04)`
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM && pytest tests/bot/test_setup_hook.py tests/bot/test_bot_lifecycle.py -x -q</automated>
  </verify>
  <done>All 6 setup_hook tests pass; Plan 01's lifecycle tests still pass (the close-ordering change must not regress them — adjust those tests if needed); count log line present.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: EDM001 defer-discipline lint rule + pre-commit hook</name>
  <files>
    src/eldritch_dm/lint/__init__.py,
    src/eldritch_dm/lint/edm001.py,
    tools/lint_defer_discipline.py,
    .pre-commit-config.yaml,
    tests/bot/test_defer_discipline.py
  </files>
  <behavior>
    Implementation form: **AST-based standalone script** (per 02-RESEARCH.md Q4 guidance — the leading candidate; if research recommends a true ruff plugin and that proves <1 hr to wire, prefer the plugin; otherwise stick with AST script).

    Module `eldritch_dm/lint/edm001.py`:

    - `def main(argv: list[str] | None = None) -> int`:
      Accepts file paths (or globs) as argv; default `["src/eldritch_dm/bot/**/*.py", "src/eldritch_dm/bot/cogs/**/*.py"]`. Parses each with `ast.parse`. For each `AsyncFunctionDef`:
      - Check if it is an interaction callback. Heuristic (per D-10):
        - Decorated with `@app_commands.command(...)` / `@discord.app_commands.command(...)` / `@<bot>.tree.command(...)` (Name/Attribute decorator ending in `.command`)
        - OR decorated with `@discord.ui.button(...)` / `@discord.ui.select(...)` / etc.
        - OR is named `callback` AND its enclosing class subclasses something with `Item`, `Button`, `Modal`, `View`, or `DynamicItem` in its bases (string-match the base names — we don't resolve symbols)
      - Skip if any decorator's qualified text contains `"autocomplete"` (D-12 exception).
      - Find the first non-Expr-docstring statement in the body. Acceptable forms:
        - `await interaction.response.defer(...)`
        - `await <name>.response.defer(...)` (first arg-of-callback may be named anything — discord.py convention is `interaction`, but be liberal)
        - `await <name>.response.send_modal(...)` (D-12 exception)
      - If the first non-docstring stmt does NOT match → report violation: `path:line:col: EDM001 first statement of interaction callback must be `await <interaction>.response.defer(...)`; use `# noqa: EDM001` with reason for exceptions`.
      - Honor `# noqa: EDM001` on the function `def` line or first body line (use `ast.get_source_segment` + raw-line regex).

      Return code: 0 if no violations; 1 if any. Print violations to stdout in the standard `<file>:<line>:<col>: <message>` form.

    `tools/lint_defer_discipline.py`: thin wrapper that calls `eldritch_dm.lint.edm001.main()` so pre-commit can invoke it via `python tools/lint_defer_discipline.py` without needing the package installed in the hook env.

    `.pre-commit-config.yaml` — ADD a new repo block (preserve existing ruff hook):
    ```
    - repo: local
      hooks:
        - id: edm001-defer-discipline
          name: EDM001 - first await must be defer
          entry: python -m eldritch_dm.lint.edm001
          language: system
          types: [python]
          files: ^src/eldritch_dm/bot/.*\.py$
          pass_filenames: true
    ```
    (If `.pre-commit-config.yaml` does not exist yet, create it with the ruff hook from Phase 1 + this new hook. Check existing state before writing.)

    Tests (`test_defer_discipline.py`) — corpus-driven:

    A test corpus lives inline in the test file as strings (or as small fixture files in `tests/bot/_edm001_corpus/{good,bad}/*.py`). For each:
    - Good cases (must NOT trigger EDM001):
      1. App command whose first body stmt is `await interaction.response.defer(thinking=True)`
      2. Button callback whose first stmt is `await interaction.response.defer(ephemeral=True)`
      3. Modal `on_submit` whose first stmt is `await interaction.response.send_modal(...)` (D-12 exception)
      4. App command with a docstring THEN defer — passes (docstring is ignored)
      5. App command with `# noqa: EDM001 — autocomplete` on its def line AND no defer → passes (explicit waiver)
      6. Plain non-callback async function with no defer → passes (not subject to the rule)
    - Bad cases (must trigger EDM001):
      1. App command whose first stmt is a DB read, not defer
      2. Button callback whose first stmt is `print(...)` (lol)
      3. App command whose first await is `await some_helper()` (defer NOT first)
      4. Modal on_submit whose first stmt is a non-send_modal/non-defer call
      5. Button callback that defers in an `if` branch but not unconditionally first

    Test runner: import `main` and call it with each corpus path; assert return code 0 (good) / 1 (bad); for bad cases, assert stdout contains `"EDM001"` and the function name.

    Bonus integration test:
    - `test_real_codebase_passes_edm001`: run `main(["src/eldritch_dm/bot"])` against the actual codebase; assert exit 0. This MUST pass — meaning Plan 01's `/ping` and `/status` AND Plan 02's DynamicItem stubs all already defer correctly. If this test fails, fix the source first.
  </behavior>
  <action>
    Implement per `<behavior>`.

    Heuristic resilience: false positives are tolerable IF they can be silenced with `# noqa: EDM001`. False negatives (missing a real violation) are NOT tolerable — when in doubt, flag. The lint is allowed to be conservative.

    Run the lint against the existing `bot/` code BEFORE committing — if it flags anything, that's a Plan 01/02 defer-discipline bug we need to fix in this commit. (We pre-wrote them correctly in Plans 01 + 02, so this should be clean — but verify.)

    Commit 1 (RED): `test(02-discord-scaffold-persistent-views): add EDM001 corpus tests (good + bad)`
    Commit 2 (GREEN): `feat(02-discord-scaffold-persistent-views): EDM001 defer-discipline AST lint rule`
    Commit 3 (CHORE): `chore(02-discord-scaffold-persistent-views): wire EDM001 into pre-commit`
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM && pytest tests/bot/test_defer_discipline.py -x -q && python -m eldritch_dm.lint.edm001 src/eldritch_dm/bot</automated>
  </verify>
  <done>All EDM001 tests pass; running the linter against the live `src/eldritch_dm/bot` tree exits 0; pre-commit hook wired; `pre-commit run --all-files` succeeds.</done>
</task>

<task type="auto">
  <name>Task 4: Kill-and-restart drill (BOT-08) + Phase 2 SUMMARY</name>
  <files>
    tests/bot/test_restart_drill.py,
    .planning/phases/02-discord-scaffold-persistent-views/02-SUMMARY.md
  </files>
  <action>
    Write `tests/bot/test_restart_drill.py` implementing D-36 exactly:

    1. **Gating**: top of file: `pytestmark = pytest.mark.skipif(not os.environ.get("RUN_INTEGRATION"), reason="restart-drill integration test; set RUN_INTEGRATION=1 to run")`. Document in the module docstring that CI sets `RUN_INTEGRATION=1`.

    2. **Test `test_persistent_view_survives_restart`**:
       a. `tmp_db = tmp_path / "drill.sqlite3"` — fresh DB.
       b. `bot_a = await bot_factory(eldritch_db_path=str(tmp_db))` (extend conftest's `bot_factory` to accept overrides). Run `setup_hook`.
       c. Seed: upsert a `channel_sessions` row (`channel_id="111"`, `campaign_name="Drill"`, state=COMBAT); insert a `persistent_views` row representing an EndTurnButton: `custom_id="endturn:111:222"`, `view_class="EndTurnButton"`, `message_id="333"`, `channel_id="111"`.
       d. Build a mock `Interaction` with `data={"custom_id": "endturn:111:222", "component_type": 2}`, `channel_id=111`, `user.id=222`, `message.id=333`.
       e. Invoke the dispatch path: call `await bot_a._dispatch_dynamic_item(...)` if that internal exists; otherwise simulate the registry lookup directly: `view = bot_a._connection._view_store...` — INSTEAD, prefer constructing the DynamicItem fresh via the registry: `match = EndTurnButton.__discord_ui_template__.fullmatch("endturn:111:222")`; `item = await EndTurnButton.from_custom_id(interaction, None, match)`; `await item.callback(interaction)`. Assert `interaction.followup.send` was called with the Phase 2 stub message.
       f. **Kill**: `await bot_a.close()`; del bot_a; gc collect to be paranoid.
       g. **Restart**: build a fresh `bot_b = await bot_factory(eldritch_db_path=str(tmp_db))` — same DB path, new process-equivalent (new asyncio task tree, new EldritchBot instance, new MCP/health stack).
       h. Spy on `bot_b.add_view`. Re-run `setup_hook` (if not already done by factory). Assert `add_view` was called at least once with `message_id=333` and a View containing an `EndTurnButton` with `channel_id=111`, `actor_id=222`.
       i. Re-dispatch the same Interaction shape against bot_b — assert the callback again produced the stub message.
       j. Cleanup: `await bot_b.close()`.

    3. **Test `test_expired_riposte_cleanup_on_restart`** (optional smoke for Phase 5 prep — gated behind the same RUN_INTEGRATION; mark `@pytest.mark.xfail(strict=False, reason="riposte cleanup lands in Phase 5; smoke only")`): seed a `riposte_timers` row with `deadline_ts` in the past; build bot; assert no error during setup_hook. (This is a forward-compat smoke; Phase 5 will replace `xfail` with the real cleanup assertion.)

    Then write `.planning/phases/02-discord-scaffold-persistent-views/02-SUMMARY.md` using `$HOME/.claude/get-shit-done/templates/summary.md`. Cover:
    - Plans 01, 02, 03 deliverables.
    - Requirement IDs satisfied: BOT-01..08, OPS-04.
    - Tech additions: `pytest-mock`, `syrupy`, optionally `dpytest`.
    - Patterns established (for Phases 3-5):
      - Cogs pattern (`cogs/<name>.py` with `setup(bot)`)
      - DynamicItem regex template pattern
      - EmbedCoalescer per-message use
      - send_warning helper for any "❌ ..." response
      - EDM001 lint discipline
      - `RUN_INTEGRATION=1` gating for restart-drill-style tests
    - Decisions: locked the EmbedColor palette, 100-char custom_id rule, AST-based EDM001 over ruff plugin (if that's what shipped), `dpytest` decision per research.
    - Open items / TODOs for Phase 3: replace stub callbacks (ReadyButton in Phase 3 lobby cog, DeclareActionButton in Phase 4 exploration cog, etc.).
    - Test totals: Phase 1's 177 + new bot tests = NNN.

    Commit 1: `test(02-discord-scaffold-persistent-views): kill-and-restart drill (BOT-08)`
    Commit 2: `docs(02-discord-scaffold-persistent-views): Phase 2 SUMMARY`
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM && RUN_INTEGRATION=1 pytest tests/bot/test_restart_drill.py -x -q && pytest tests -x -q && lint-imports && python -m eldritch_dm.lint.edm001 src/eldritch_dm/bot</automated>
  </verify>
  <done>Restart drill passes under `RUN_INTEGRATION=1`; full `pytest tests` green without the env var (drill skipped); `lint-imports` and EDM001 both green; `02-SUMMARY.md` written with all 5 phase success criteria checked off.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Discord gateway → rehydrated DynamicItem | Untrusted custom_id matched against template regex; persistent across restarts |
| SQLite `persistent_views` table → setup_hook | Trusted (only the bot writes); but malformed rows from a corrupted DB could crash setup |
| Developer source → CI | Untrusted in the sense that any contributor could land a non-deferred callback; EDM001 is the gatekeeper |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-12 | Tampering | `persistent_views.view_class` value | mitigate | `build_view_for_row` returns None (skips row, logs warning) on unknown class names — bot still boots; never executes arbitrary class names |
| T-02-13 | Denial of service | Coalescer + Discord 429 | mitigate | Rate limit fixed at `embed_edit_rate_limit` (default 1.0s/edit) per message; on HTTPException(429) the loop continues without abandoning (Test 6) |
| T-02-14 | Denial of service | setup_hook partial DB corruption | mitigate | `list_by_channel` errors propagate (D-25); bot does not connect with half-rehydrated state |
| T-02-15 | Repudiation | Defer discipline | mitigate | EDM001 enforced in pre-commit AND CI (Task 3); violations cannot land in main |
| T-02-16 | Denial of service | `bot.close()` hanging on writer_queue drain | mitigate | `asyncio.wait_for(stop, timeout=5.0)` (Task 2); log on timeout but still proceed to MCP close |
| T-02-17 | Tampering | Rehydrated EndTurnButton clicked by wrong user | accept-for-phase | Phase 2 callbacks are stubs (D-23); Phase 4 will gate by Discord user_id. Plan-03 explicitly does NOT add real authorization. |
| T-02-SC | Tampering | No new package installs in Plan 03 | accept | Reuses pytest-mock/syrupy installed in Plan 01 Task 1. No fresh `[ASSUMED]`/`[SUS]` packages to gate. |
</threat_model>

<verification>
- `pytest tests -x -q` is green (drill skipped without env var); 11 (Plan 01) + 16 (Plan 02) + 8 (coalescer) + 6 (setup_hook) + 11+ (EDM001 corpus) new bot tests pass.
- `RUN_INTEGRATION=1 pytest tests/bot/test_restart_drill.py -x -q` is green.
- `python -m eldritch_dm.lint.edm001 src/eldritch_dm/bot` exits 0.
- `pre-commit run --all-files` is green (ruff + import-linter + EDM001).
- `lint-imports` clean (all five contracts hold).
- `02-SUMMARY.md` exists and ticks all 5 Phase 2 success criteria.
</verification>

<success_criteria>
- BOT-02 ✅ EDM001 enforced, CI fails on violation.
- BOT-05 ✅ setup_hook rehydrates persistent_views → bot.add_view per row.
- BOT-06 ✅ EmbedCoalescer enforces ≤1 edit/sec/message with latest-value semantics.
- BOT-08 ✅ Kill-and-restart drill passes; persistent buttons functional after restart.
- OPS-04 ✅ `bot.close()` cancels health, drains writer_queue (5s timeout), closes MCP, closes super.
- All Phase 2 success criteria from ROADMAP.md ticked in 02-SUMMARY.md.
</success_criteria>

<output>
Create `.planning/phases/02-discord-scaffold-persistent-views/02-03-SUMMARY.md` AND `.planning/phases/02-discord-scaffold-persistent-views/02-SUMMARY.md` when done. The former is this plan's SUMMARY; the latter is the Phase 2 rollup.
</output>
