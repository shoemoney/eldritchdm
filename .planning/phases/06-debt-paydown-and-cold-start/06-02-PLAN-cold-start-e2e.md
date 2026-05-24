---
phase: 06-debt-paydown-and-cold-start
plan: 02
type: tdd
wave: 2
depends_on:
  - 06-01
files_modified:
  - tests/integration/test_cold_start_e2e.py
  - .planning/REQUIREMENTS.md
autonomous: true
requirements:
  - DEBT-02
tags: [debt, cold-start, integration, e2e, smoke, regression-guard]

must_haves:
  truths:
    - "`tests/integration/test_cold_start_e2e.py` exists and is committed"
    - "The test uses ZERO fixtures (no `conftest.py` imports that pre-create channel_sessions / persistent_views / orchestrator state)"
    - "The test exercises the documented quickstart path: settings → bootstrap → EldritchBot construction → setup_hook → simulate /start_game → simulate ready-up → assert `bot.orchestrator._tasks[channel_id]` exists AND `.done() is False`"
    - "Everything happens in ONE process lifetime (no `bot.run`, no subprocess, no restart between setup_hook and the ready-up click)"
    - "External dependencies (oMLX, dm20, Discord) are stubbed at the MCP client boundary OR the AsyncMock layer — Discord network is NEVER touched"
    - "When applied against commit `7d307a1` (Phase 5 Plan 03 closure, pre-G-1-fix), the test FAILS (the assertion `_tasks[channel_id]` not present in dict)"
    - "When applied against current `main` (post-G-1-fix `4c15641`), the test PASSES"
    - "Test runs in <5s wall-clock (no real `asyncio.sleep`, no real Discord, no real DB beyond tmp SQLite)"
  artifacts:
    - path: "tests/integration/test_cold_start_e2e.py"
      provides: "Cold-start lobby→ready→orchestrator-alive regression guard (DEBT-02 / META meta-pitfall mitigation)"
      contains: "async def test_cold_start_e2e_orchestrator_alive_after_ready"
      min_lines: 100
    - path: ".planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md"
      provides: "Plan closure summary with the historical-regression verification protocol's RED/GREEN output captured"
  key_links:
    - from: "tests/integration/test_cold_start_e2e.py"
      to: "src/eldritch_dm/bot/dynamic_items.py:ReadyButton.callback (all-ready branch)"
      via: "Direct invocation of the callback with a MagicMock Interaction, mirroring test_lobby_to_exploration_flow.py's pattern"
      pattern: "ReadyButton.*callback"
    - from: "tests/integration/test_cold_start_e2e.py"
      to: "src/eldritch_dm/bot/bot.py:EldritchBot.setup_hook"
      via: "Test calls `await bot.setup_hook()` directly (no `bot.run`)"
      pattern: "setup_hook\\(\\)"
    - from: ".planning/REQUIREMENTS.md DEBT-02"
      to: "this plan"
      via: "DEBT-02 ticked [x] at plan closure"
      pattern: 'DEBT-02.*\[x\]'
---

<objective>
Add `tests/integration/test_cold_start_e2e.py` — a single integration test that exercises the documented quickstart path end-to-end in one process lifetime with zero pre-existing state, and prove it would have caught G-1 by running it against commit `7d307a1` (pre-G-1-fix, expect FAIL) and current `main` (expect PASS).

Purpose: The v1.0 audit's G-1 BLOCKER (orchestrator never starts on cold-start ready-up) shipped because 870 tests passed, all of which either constructed the orchestrator directly or routed through the `setup_hook` RESUME path. RETROSPECTIVE.md tagged this gap `NEEDS IMPROVEMENT v1.1`. Research/PITFALLS.md elevated it to the META meta-pitfall: every v1.1 feature introduces a new opportunity for the same bug class (Smart MonsterDriver wires to Claudmaster, YAML eligibility wires to riposte path, backfill wires to dm20 + DB). This plan installs the regression guard.

Output:
- 1 new test file: `tests/integration/test_cold_start_e2e.py` (~150-250 LOC including the mock scaffolding)
- 1 RED→GREEN commit (`test(06-cold-start): regression guard for cold-start orchestrator wiring (DEBT-02)`)
- 1 verification-protocol commit OR explicit SUMMARY.md section capturing the historical RED/GREEN proof from `git checkout 7d307a1 → run → FAIL → git checkout main → run → PASS`
- 1 paperwork commit ticking DEBT-02 in `.planning/REQUIREMENTS.md`
- `.planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md`
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/RETROSPECTIVE.md
@.planning/phases/06-debt-paydown-and-cold-start/06-CONTEXT.md
@.planning/milestones/v1.0-MILESTONE-AUDIT.md
@.planning/research/PITFALLS.md
@src/eldritch_dm/bot/bot.py
@src/eldritch_dm/bot/dynamic_items.py
@src/eldritch_dm/config/settings.py
@src/eldritch_dm/gameplay/party_mode.py
@tests/integration/test_lobby_to_exploration_flow.py

<interfaces>
<!-- The new test depends on EXISTING interfaces. The executor MUST reuse these -->
<!-- and not redefine them. The signatures below are the ones the test will call. -->

## EldritchBot construction + setup_hook (from src/eldritch_dm/bot/bot.py)

```python
class EldritchBot(discord.Client):
    def __init__(self, *, settings: Settings, ...) -> None: ...
    async def setup_hook(self) -> None:
        # Order:
        #   (a) await bootstrap(settings.eldritch_db_path)
        #   (b) WriterQueue + start
        #   (c) CircuitBreaker + MCPClient
        #   (d) HealthCheck + start
        #   (e) ChannelSessionRepo, PersistentViewRepo, SanitizerAuditRepo
        #   (e2) add_dynamic_items + rehydrate_persistent_views
        #   (e3) ChannelRateLimiter, BatchCoordinator
        #   (e3b) Phase 5: PCClassesRepo, RiposteTimerRepo, MonsterDriver
        #   (e3c) Phase 5: PartyModeOrchestrator
        #   (f) load cogs (Diagnostics, Lobby, Ingest, Exploration, Combat, Reactions)
        #   (g) start orchestrator tasks for existing EXPLORATION/COMBAT rows (RESUME)
        #   (h) sync app command tree

    orchestrator: PartyModeOrchestrator  # populated by setup_hook
    channel_sessions_repo: ChannelSessionRepo
    persistent_views_repo: PersistentViewRepo
    mcp: MCPClient
    health: HealthCheck
    writer_queue: WriterQueue
```

## ReadyButton (from src/eldritch_dm/bot/dynamic_items.py)

```python
class ReadyButton(discord.ui.DynamicItem[discord.ui.Button],
                  template=r"^ready:(?P<channel_id>\d+)$"):
    def __init__(self, channel_id: int) -> None: ...
    async def callback(self, interaction: discord.Interaction) -> None:
        # All-ready branch at lines ~325-388:
        #   1. await channel_sessions_repo.set_state(channel_id_str, ChannelState.EXPLORATION)
        #   2. G-1 FIX (post-4c15641):
        #      orchestrator = getattr(bot, "orchestrator", None)
        #      if orchestrator is not None:
        #          await orchestrator.start_orchestrator_for_channel(
        #              channel_id=channel_id_str,
        #              campaign_name=session.campaign_name,
        #              session_id=session.claudmaster_session_id or "",
        #          )
        #   3. await mcp_tools.player_action(...)  # best-effort, suppressed
        #   4. await interaction.message.edit(embed=transition_embed)  # best-effort
        #   5. await interaction.followup.send(content="...", ephemeral=True)
```

## PartyModeOrchestrator (from src/eldritch_dm/gameplay/party_mode.py)

```python
class PartyModeOrchestrator:
    _tasks: dict[str, asyncio.Task]  # keyed by channel_id_str
    async def start_orchestrator_for_channel(
        self, *, channel_id: str, campaign_name: str, session_id: str,
    ) -> asyncio.Task: ...
    async def stop_orchestrator_for_channel(self, channel_id: str) -> None: ...
    async def stop_all(self) -> None: ...
```

The load-bearing assertion for DEBT-02 is:
    `assert channel_id_str in bot.orchestrator._tasks`
    `assert not bot.orchestrator._tasks[channel_id_str].done()`

If the G-1 fix is not present, `_tasks` will be empty after the ready-up click.

## Reference pattern (from tests/integration/test_lobby_to_exploration_flow.py)

That test already exercises the G-1 closure narrowly. The DEBT-02 test is BROADER:
- `test_lobby_to_exploration_flow.py` constructs ReadyButton + repos directly and asserts orchestrator start was called.
- `test_cold_start_e2e.py` (this plan) constructs the FULL EldritchBot, runs the FULL setup_hook, then drives the ready-up click — proving the END-TO-END cold-start path works without any pre-existing fixtures saving it.

Read `test_lobby_to_exploration_flow.py` for the mocked-Interaction pattern and the LobbyCog `/start_game` simulation; DO NOT re-derive these from scratch.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write the failing cold-start E2E test (RED phase)</name>
  <files>
    tests/integration/test_cold_start_e2e.py
  </files>
  <behavior>
    `test_cold_start_e2e_orchestrator_alive_after_ready` (single async test, one function):

    - **Phase A — Settings + bootstrap:** Construct a `Settings` instance with `eldritch_db_path=str(tmp_path / "cold_start.sqlite3")`, `discord_token="x" * 50` (placeholder; never used because we never call `bot.run`), `omlx_endpoint="http://localhost:8765/v1"` (stubbed), all other settings at defaults. Confirm `await bootstrap(settings.eldritch_db_path)` is a no-op at this point because EldritchBot.setup_hook will also call it — schema bootstrap is idempotent (Phase 1 D-24).
    - **Phase B — Construct EldritchBot and run setup_hook in-process:** `bot = EldritchBot(settings=settings, ...)`; patch `MCPClient.call` (or use `respx` against `localhost:8765`) so `health.check()` succeeds and `tool_list` returns an empty dict; patch `discord.Client.tree.sync` to a no-op AsyncMock; `await bot.setup_hook()`. After this:
      - `bot.orchestrator` is not None
      - `bot.orchestrator._tasks` is an empty dict (no RESUME — fresh DB)
      - `bot.channel_sessions_repo` is wired
    - **Phase C — Simulate `/start_game`:** Insert a `channel_sessions` row directly via `bot.channel_sessions_repo.create(channel_id=str(_CHANNEL_ID), campaign_name=_CAMPAIGN, claudmaster_session_id=_SESSION_ID, state=ChannelState.LOBBY)` (or the existing create method — verify in the repo). Insert a `persistent_views` row marking ReadyButton as live for the channel (use the same pattern as `test_lobby_to_exploration_flow.py` g1_db fixture's seeding). Insert one player intent (a created character via `dm20__create_character` is NOT needed because we're stubbing dm20; just insert what the ReadyButton.callback reads).

      **Critical:** the test must mock the `list_characters` MCP call so it returns a single character with `player_id=str(_USER_ID)`, so the all-ready branch fires. Mock `player_action(party_ready)` to succeed. Pattern: re-use the same `MCPClient` mock setup as `test_lobby_to_exploration_flow.py`.
    - **Phase D — Drive the ready-up click:** Construct a `MagicMock(spec=discord.Interaction)` with `.user.id = _USER_ID`, `.client = bot`, `.message = MagicMock(spec=discord.Message)`, `.response = AsyncMock()`, `.followup = AsyncMock()`. Construct `ReadyButton(channel_id=_CHANNEL_ID)`. `await ready_button.callback(interaction)`.
    - **Phase E — Load-bearing assertions (THE point of this test):**
      ```python
      channel_id_str = str(_CHANNEL_ID)
      assert channel_id_str in bot.orchestrator._tasks, (
          "G-1 regression: orchestrator task NOT started after all-ready click. "
          "ReadyButton.callback all-ready branch is missing the "
          "start_orchestrator_for_channel call. See "
          ".planning/milestones/v1.0-MILESTONE-AUDIT.md G-1."
      )
      task = bot.orchestrator._tasks[channel_id_str]
      assert not task.done(), (
          f"Orchestrator task for channel {channel_id_str} is already done "
          f"(exception={task.exception() if task.done() else 'n/a'}). "
          "Expected an alive task driving the pop→thinking→resolve loop."
      )
      # Belt-and-suspenders: session state actually flipped to EXPLORATION
      session = await bot.channel_sessions_repo.get(channel_id_str)
      assert session is not None and session.state == ChannelState.EXPLORATION
      ```
    - **Phase F — Cleanup (CRITICAL for test hygiene):** `await bot.orchestrator.stop_all()`; `await bot.health.stop()`; `await bot.writer_queue.stop()`; close any aiosqlite connections; let asyncio garbage-collect the cancelled tasks. Use `try/finally` so failed assertions still clean up.
  </behavior>
  <action>
    Read `tests/integration/test_lobby_to_exploration_flow.py` end-to-end FIRST to absorb the Interaction-mocking and DB-seeding pattern. Do not re-derive these — they're the working blueprint G-1 closure used.

    Read `src/eldritch_dm/bot/bot.py` lines 175-383 to enumerate what setup_hook actually wires (so the test's mocks cover every external surface it touches: MCP `tool_list`, MCP health-check ping, discord.Client.tree.sync).

    Create `tests/integration/test_cold_start_e2e.py`. The file structure:

    1. Module docstring quoting the META meta-pitfall from research/PITFALLS.md and the G-1 root-cause one-liner; explicitly state the regression-guard protocol (verify against `7d307a1` for RED, current `main` for GREEN).
    2. Imports — strictly minimal; reuse `pytest`, `pytest_asyncio`, `discord`, `MagicMock`/`AsyncMock`, the production modules under test.
    3. Test constants (`_CAMPAIGN`, `_USER_ID`, `_CHANNEL_ID`, `_SESSION_ID`).
    4. The single test function `test_cold_start_e2e_orchestrator_alive_after_ready`, decorated `@pytest.mark.asyncio`. Implements Phases A-F above.
    5. NO module-level fixtures. NO `conftest.py` imports beyond what pytest auto-discovers (D-37). Anything the test needs, it constructs inline (in `tmp_path`, in `try/finally`).

    Implementation notes:
    - The MCP mock should be done by patching `eldritch_dm.mcp.client.MCPClient.call` at the class level for the duration of the test (via `mocker.patch.object` or `unittest.mock.patch` context manager). Use `AsyncMock(return_value=...)` and set `.side_effect` only if the mock needs to vary by call.
    - The `discord.Client.tree.sync` patch should similarly be `mocker.patch.object(bot.tree, "sync", new=AsyncMock(return_value=[]))`.
    - DO NOT use `respx` unless the existing MCPClient calls the HTTP layer in a way that bypasses easy AsyncMock injection — verify in `src/eldritch_dm/mcp/client.py`. AsyncMock is preferred for this test because it keeps the mock surface obvious in the test file.
    - The test MUST run in <5s. If any `asyncio.sleep` in setup_hook or in the orchestrator's first poll iteration adds wall-clock time, mock `asyncio.sleep` for the duration of the test OR ensure the orchestrator gets cancelled in Phase F before it does its first real sleep.
    - **Do not import from `eldritch_dm.bot.cogs.lobby`** for the `/start_game` simulation — call the repo methods directly. The test is about ReadyButton.callback's transition, not about LobbyCog's slash command parsing.

    First commit (RED gate proof — the test exists and you ran it against commit `7d307a1`):
    ```bash
    git add tests/integration/test_cold_start_e2e.py
    git commit -m "$(cat <<'EOF'
    test(06-cold-start): regression guard for cold-start orchestrator wiring (DEBT-02)

    Adds tests/integration/test_cold_start_e2e.py — single test that
    exercises the documented quickstart path end-to-end in one process
    lifetime with zero shared fixtures pre-creating state:

      settings → bootstrap → EldritchBot → setup_hook → simulate
      /start_game → simulate ready-up → assert orchestrator task alive
      for the channel.

    Closes the v1.0 audit META meta-pitfall (RETROSPECTIVE.md +
    research/PITFALLS.md). Would have caught G-1 (ReadyButton.callback
    missing start_orchestrator_for_channel) before v1.0 shipped.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    ```

    Then run the test against current main to confirm GREEN:
    ```bash
    uv run pytest tests/integration/test_cold_start_e2e.py -x -v
    # MUST pass — the G-1 fix at 4c15641 is already on main
    ```

    If GREEN on first run: proceed to Task 2 (historical RED proof).
    If RED on first run: debug the test — something is wrong with the mocks or seeding. Do NOT assume the production code is broken; the G-1 fix has been on main since 2026-05-22. Iterate until GREEN.
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_cold_start_e2e.py -x -v; uv run ruff check tests/integration/test_cold_start_e2e.py; uv run lint-imports</automated>
  </verify>
  <done>
    `tests/integration/test_cold_start_e2e.py` exists, contains exactly one async test, uses zero shared fixtures, mocks oMLX/dm20/Discord at the boundary (never touches the network), constructs a real EldritchBot via `setup_hook()` in-process, drives a real `ReadyButton.callback` invocation with a mocked Interaction, and asserts the orchestrator task is alive after the click. Test PASSES against current `main`. Ruff + lint-imports clean.
  </done>
</task>

<task type="auto">
  <name>Task 2: Historical-regression verification + REQUIREMENTS tick + SUMMARY (closes the loop)</name>
  <files>
    .planning/REQUIREMENTS.md,
    .planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md
  </files>
  <action>
    This task PROVES the test catches G-1 by running it against the pre-G-1-fix commit. It does NOT modify production code or change the test file.

    Step 1 — Check git state is clean before the time-travel dance:
    ```bash
    git status --porcelain
    # MUST be empty or contain only known untracked planning files. The test file
    # from Task 1 is already committed. If there are stray modifications, STOP
    # and surface them — we don't want to lose work in the stash/checkout dance.
    ```

    Step 2 — Stash the working tree so we can apply the test on top of the historical commit:
    ```bash
    git stash push -u -m "06-02-cold-start-e2e historical verification stash"
    # If `git stash list` shows multiple stashes by accident, recover the correct
    # one explicitly via `git stash apply stash@{0}` later.
    ```

    Step 3 — Check out the pre-G-1-fix commit (`7d307a1`, Phase 5 Plan 03 closure):
    ```bash
    git checkout 7d307a1
    # If git complains about local changes, you missed step 2. Restore via
    # `git checkout main` + verify stash status, then re-do step 2.
    ```

    Step 4 — Apply just the new test file from the stash onto `7d307a1`'s tree:
    ```bash
    git checkout stash@{0} -- tests/integration/test_cold_start_e2e.py
    # The test file is now present in a tree that does NOT have the G-1 fix.
    ```

    Step 5 — Run the test, EXPECT FAIL:
    ```bash
    uv run pytest tests/integration/test_cold_start_e2e.py -x -v 2>&1 | tee /tmp/cold-start-7d307a1.log
    # MUST exit non-zero. The assertion that fails should be:
    #   `assert channel_id_str in bot.orchestrator._tasks`
    # If it passes against 7d307a1, the test is too weak — it's not actually
    # asserting on the orchestrator-start side-effect. Go back to Task 1 and
    # tighten the assertion. (This is the load-bearing proof of DEBT-02; don't
    # hand-wave past it.)
    ```

    Step 6 — Capture the RED output for the SUMMARY:
    ```bash
    # Extract the failing assertion lines from /tmp/cold-start-7d307a1.log for
    # pasting into the SUMMARY. Look for "FAILED" + the AssertionError traceback.
    grep -E "FAILED|AssertionError|_tasks" /tmp/cold-start-7d307a1.log > /tmp/cold-start-red-evidence.txt
    ```

    Step 7 — Restore main and the working tree:
    ```bash
    git checkout main
    git stash pop
    # If pop conflicts (because the stash also contained the test file), resolve
    # by keeping the version on main (the committed test from Task 1).
    git status
    # Should show a clean tree (test file is committed, nothing else dirty).
    ```

    Step 8 — Re-run the test on main, EXPECT PASS:
    ```bash
    uv run pytest tests/integration/test_cold_start_e2e.py -x -v 2>&1 | tee /tmp/cold-start-main.log
    # MUST exit 0. The test passes because the G-1 fix at 4c15641 is on main.
    ```

    Step 9 — Tick DEBT-02 in `.planning/REQUIREMENTS.md`:
    Edit `.planning/REQUIREMENTS.md`: change `- [ ] **DEBT-02**:` to `- [x] **DEBT-02**:`. Update the Traceability table row: `DEBT-02 | Phase 6 | TBD` → `DEBT-02 | Phase 6 | 06-02-PLAN-cold-start-e2e`.
    ```bash
    git add .planning/REQUIREMENTS.md
    git commit -m "$(cat <<'EOF'
    docs(06-02): tick DEBT-02 in REQUIREMENTS.md

    Cold-start E2E regression guard verified RED at 7d307a1 (pre-G-1-fix)
    and GREEN at main (post-4c15641). See 06-02-SUMMARY.md for the
    historical-verification log excerpts.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    ```

    Step 10 — Write the SUMMARY:
    Create `.planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md` per `@$HOME/.claude/get-shit-done/templates/summary.md`. MUST include:
    - The test file's location and one-paragraph overview
    - The fixture inventory: explicit list of "fixtures used = NONE beyond `tmp_path`"
    - The mock boundary: which production surfaces are mocked (MCP.call, discord tree.sync, etc.)
    - **Historical-regression verification log:** captured RED output excerpt (the failing assertion against `7d307a1`), then the GREEN output excerpt (passing against main). This is the load-bearing artifact proving DEBT-02 is discharged.
    - The commit SHAs: Task 1's RED-GREEN commit + Task 2's REQUIREMENTS tick commit
    - Test wall-clock duration (must be <5s)
    - Closes DEBT-02 statement
    - Handoff signal: "Every subsequent v1.1 phase plan MUST ship one cold-start integration test of the same shape. Phase 6 sets the precedent; Phases 7-10 inherit the discipline (see RETROSPECTIVE.md Lesson 1)."

    Commit the SUMMARY:
    ```bash
    git add .planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md
    git commit -m "$(cat <<'EOF'
    docs(06-02): plan closure summary — cold-start E2E (DEBT-02)

    Historical-regression verification confirmed: test FAILS against
    7d307a1 (pre-G-1-fix) and PASSES against main. DEBT-02 closed.

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
    EOF
    )"
    ```
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_cold_start_e2e.py -x -v; grep -E '^- \[x\] \*\*DEBT-02\*\*' .planning/REQUIREMENTS.md; test -f .planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md; grep -E "7d307a1|RED|FAILED|GREEN|PASS" .planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md</automated>
  </verify>
  <done>
    Test was run against `7d307a1` and FAILED with the expected `_tasks` assertion; test was re-run against current `main` and PASSED; tree is back on `main` with no stash remnants and no detached-HEAD state; DEBT-02 ticked `[x]` in REQUIREMENTS.md with Traceability updated; SUMMARY.md contains the RED/GREEN log excerpts as the load-bearing proof artifact; 7/7 import-linter contracts still KEPT; pytest suite green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Test ↔ EldritchBot construction | Test mocks the external surfaces (MCP HTTP, Discord gateway, tree.sync) but exercises real production code from `setup_hook` through `ReadyButton.callback`. The trust boundary is the AsyncMock/respx layer. |
| Executor ↔ git history | Task 2 performs a `git stash` + `git checkout 7d307a1` + `git checkout main` dance. The stash/restore protocol is the integrity mechanism — losing the working tree would destroy the entire Phase 6 plan. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-02-01 | Tampering | The test passes against `7d307a1` by accident (mocks too forgiving) | mitigate | D-41: the assertion is on `bot.orchestrator._tasks[channel_id_str]` — a dict-key existence check that depends DIRECTLY on the G-1-fixed code path. If the test passes at `7d307a1`, it is broken — Task 2 Step 5 explicitly says to STOP and tighten the assertion. |
| T-06-02-02 | Tampering | The test passes by reading state pre-populated by `setup_hook`'s RESUME loop (not by the click) | mitigate | D-37: zero shared fixtures pre-create channel_sessions rows in EXPLORATION/COMBAT state. The Phase A bootstrap creates an empty DB; the Phase C `/start_game` simulation creates ONLY a LOBBY row. The RESUME loop sees nothing to resume — `_tasks` is empty after setup_hook. The orchestrator MUST start from the click for the assertion to pass. |
| T-06-02-03 | Tampering | `git stash pop` conflict destroys the new test file | mitigate | Task 2 Step 7 explicitly addresses pop conflicts: keep the main version (already committed). The test file IS committed before the stash dance (Task 1 commit), so the stash should not contain it as a modification — only as untracked-then-added. If conflict arises, the committed version wins. |
| T-06-02-04 | Information Disclosure | Test logs PII (player names, message content) | accept | Test constants use `_CAMPAIGN = "Cold Start Pilot"`, `_USER_ID = 4242` — no real PII. Mock returns are synthetic. |
| T-06-02-05 | Denial of Service | Test takes >30s due to a real `asyncio.sleep` in the orchestrator's first poll iteration | mitigate | Phase F cancels the orchestrator immediately after the assertion. The orchestrator may have ticked once (250ms default poll) but cannot accumulate sleep time. If the test approaches 5s wall-clock, mock `asyncio.sleep` for the test duration. |
| T-06-02-06 | Elevation of Privilege | Test accidentally writes to a real DB (~/.eldritchdm/...) | mitigate | All DB paths are derived from `tmp_path` pytest fixture; no env var lookups, no hardcoded paths. Even if `Settings()` accidentally read `.env`, the test overrides `eldritch_db_path` via kwargs. |
| T-06-02-SC | Tampering | Supply-chain | accept | No new packages introduced. `unittest.mock` is stdlib; `pytest`, `pytest_asyncio`, `discord.py` already pinned. No `[ASSUMED]`/`[SUS]`/`[SLOP]` flags. |
</threat_model>

<verification>
**Plan-level checks:**

1. `tests/integration/test_cold_start_e2e.py` exists; one async test function; no top-level fixtures; no `conftest` imports beyond ambient (`tmp_path`, `caplog`).
2. `uv run pytest tests/integration/test_cold_start_e2e.py -x -v` exits 0 (GREEN against main).
3. Test wall-clock <5s.
4. `.planning/REQUIREMENTS.md` line for DEBT-02 starts with `- [x] **DEBT-02**:`.
5. `.planning/REQUIREMENTS.md` Traceability table row reads: `| DEBT-02 | Phase 6 | 06-02-PLAN-cold-start-e2e |`.
6. `.planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md` exists and contains both RED (`FAILED` at `7d307a1`) and GREEN (passing on main) log excerpts.
7. `git status --porcelain` is clean (no leftover stash, no detached HEAD).
8. 7/7 import-linter contracts KEPT.
9. Full pytest suite (`uv run pytest -x -q`) still green; passing count = previous baseline + 1 (the new test).

**Risks identified:**

- **R-1 (MEDIUM):** Mock setup for `MCPClient.call` is brittle — if the production code starts calling a new MCP method during `setup_hook` (e.g., a future phase adds a Phase 6.5 wiring), the AsyncMock returns `MagicMock` for unknown calls, which may silently succeed or produce a misleading failure. Mitigation: use `AsyncMock(spec=MCPClient.call)` or set `side_effect` to a dispatch dict; default-case raises so unmocked calls fail loudly.
- **R-2 (LOW):** The git stash dance leaves the executor in detached HEAD if Step 7 is skipped. Task 2 explicitly checks `git status` after restoration. If the executor's environment somehow loses the test file mid-dance, recover via `git show HEAD:tests/integration/test_cold_start_e2e.py > tests/integration/test_cold_start_e2e.py` (the file IS committed before the dance).
- **R-3 (LOW):** `setup_hook` performs a `tree.sync()` that hits Discord's API even when mocked, IF the mock is applied AFTER `setup_hook` starts. Task 1 explicitly notes the patch must be applied BEFORE `await bot.setup_hook()`.
- **R-4 (LOW):** `EldritchBot.__init__` may require Discord intents that crash without a real gateway. Read the bot's `__init__` signature in `src/eldritch_dm/bot/bot.py` to confirm the keyword arguments the test must pass.
- **R-5 (MEDIUM):** The orchestrator's first poll iteration calls real `party_pop_action` against the mocked MCP. If the mock returns an unexpected shape, the orchestrator's `_loop` may raise inside the task, causing `.done() is True` with an exception. Assertion captures this via the `exception()` call in the failure message — but the test must mock `party_pop_action` to return an empty action so the loop parks at `asyncio.sleep(poll_interval)`. Verify the empty-action shape in `src/eldritch_dm/mcp/tools.py:party_pop_action` and `src/eldritch_dm/gameplay/party_mode.py`.

**Out of scope (explicit deferrals — do NOT add):**

- A second cold-start test exercising the FULL pop → thinking → resolve loop (Phase 10 / Smart MonsterDriver plan's territory; this plan is regression-guard only).
- Testing `bot.run()` end-to-end (requires a real Discord gateway or `dpytest`, both rejected — dpytest caps at discord.py 2.6 per STATE.md).
- Testing `__main__` token-missing path (Phase 7 SAFETY-03 owns it).
- Property-based / fuzz-style cold-start variants (regression-guard is one happy-path test; widening is a future-phase concern).
</verification>

<success_criteria>
- `tests/integration/test_cold_start_e2e.py` exists, contains exactly one async test, uses zero shared fixtures, runs in <5s, and PASSES against current `main`.
- The historical-regression protocol was executed: test was applied against `7d307a1`, FAILED with the expected `_tasks` assertion; restored to `main`, PASSED. Both log excerpts captured in SUMMARY.
- DEBT-02 ticked `[x]` in `.planning/REQUIREMENTS.md`; Traceability table updated.
- `.planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md` committed.
- 7/7 import-linter contracts KEPT.
- Full pytest suite green; passing count = v1.0 baseline + 1.
- Git tree clean post-historical-dance; no detached HEAD, no stash leftovers.
- Two commits added (RED→GREEN test commit + REQUIREMENTS tick commit) plus the SUMMARY commit; all conventional-prefixed.
</success_criteria>

<output>
Create `.planning/phases/06-debt-paydown-and-cold-start/06-02-SUMMARY.md` per the standard template, including:

- **Test file overview:** path, LOC, single-test structure, "zero fixtures used"
- **Mock boundary table:** production surface → mock type (AsyncMock / patch / respx) → return shape
- **Historical-regression verification log (LOAD-BEARING):**
  - **RED (against `7d307a1`):** paste 5-10 lines of pytest output showing `FAILED` + the `_tasks` AssertionError traceback
  - **GREEN (against `main`):** paste the `1 passed in <X>s` line + wall-clock
- **Commits added:** SHA + conventional-prefixed subject for the RED→GREEN commit, the REQUIREMENTS tick, and this SUMMARY
- **DEBT-02 closure statement:** "Closes DEBT-02. Cold-start E2E regression guard installed. Test FAILS at 7d307a1 (pre-G-1-fix), PASSES at main (post-4c15641). META meta-pitfall discharged."
- **Handoff signal for Phase 7+:** "Every v1.1 phase plan MUST ship at least one cold-start integration test of this shape (test name pattern `test_*_cold_start_*` or `test_*_fresh_install_*`). Phase 6 sets the precedent; the pattern is the regression-prevention mechanism for the META meta-pitfall identified in research/PITFALLS.md."
</output>
