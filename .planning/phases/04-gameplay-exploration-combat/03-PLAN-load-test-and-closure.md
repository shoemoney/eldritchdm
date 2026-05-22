---
phase: 04-gameplay-exploration-combat
plan: 03
type: execute
wave: 3
depends_on:
  - 04-01
  - 04-02
files_modified:
  - tests/integration/test_8player_load.py
  - tests/integration/test_restart_mid_combat.py
  - tests/conftest.py
  - pyproject.toml
  - .planning/phases/04-gameplay-exploration-combat/04-SUMMARY.md
  - .planning/REQUIREMENTS.md
  - .planning/ROADMAP.md
  - .planning/STATE.md
autonomous: true
requirements:
  - COMBAT-08
tags: [gameplay, load-test, integration, closure, phase-summary]

must_haves:
  truths:
    - "An 8-actor load test runs in CI in < 30s with mocked Discord HTTP + mocked dm20 MCP"
    - "Load test simulates 5 rounds × 4 embed updates/round = 160 edit attempts and asserts: zero 429-equivalent HTTPException raises, zero `database is locked`, EmbedCoalescer per-message rate never exceeds 1 edit/sec, ChannelEditBudget per-channel rate never exceeds 5 edits/5s"
    - "Restart-mid-combat drill (extends BOT-08) seeds channel_sessions.state=COMBAT and a combat persistent_views row, kills the orchestrator (cancel task), restarts bot, verifies combat buttons still dispatch and orchestrator resumes from get_game_state"
    - "Phase 4 SUMMARY exists summarizing Plans 01-03 deliverables, decisions, deviations, and next-phase readiness"
    - "All EXPLORE-01..07, COMBAT-01..08, COMBAT-12, OPS-03 are marked [x] in REQUIREMENTS.md"
    - "Phase 4 marked [x] in ROADMAP.md; Plans 01/02/03 marked [x]"
    - "STATE.md updated: completed_phases=4, percent=80, current_phase=05-reactions-self-host-polish, current_plan=05-01"
  artifacts:
    - path: "tests/integration/test_8player_load.py"
      provides: "8-actor combat load test (COMBAT-08 headline)"
      min_lines: 200
    - path: "tests/integration/test_restart_mid_combat.py"
      provides: "Restart-mid-combat drill (BOT-08 extension, D-35)"
      min_lines: 80
    - path: ".planning/phases/04-gameplay-exploration-combat/04-SUMMARY.md"
      provides: "Phase 4 closure summary"
      min_lines: 100
  key_links:
    - from: "tests/integration/test_8player_load.py"
      to: "src/eldritch_dm/bot/coalescer.py"
      via: "Counts EmbedCoalescer + ChannelEditBudget acquire calls and asserts cadence"
      pattern: "EmbedCoalescer|ChannelEditBudget"
    - from: "tests/integration/test_8player_load.py"
      to: "src/eldritch_dm/gameplay/party_mode.py"
      via: "Drives the full orchestrator loop end-to-end with mocked MCPClient"
      pattern: "PartyModeOrchestrator|orchestrator"
    - from: "tests/integration/test_restart_mid_combat.py"
      to: "src/eldritch_dm/bot/setup_hook.py"
      via: "Triggers setup_hook rehydration after simulated restart"
      pattern: "rehydrate_persistent_views|setup_hook"
---

<objective>
Deliver the Phase 4 headline proof — the 8-actor combat load test — plus the restart-mid-combat drill and the Phase 4 closure paperwork (SUMMARY, REQUIREMENTS [x], ROADMAP [x], STATE.md cursor advance).

Purpose: COMBAT-08 is the gate that proves multiplayer combat is correct AND that the coalescer + ChannelEditBudget + ChannelRateLimiter actually prevent Discord 429 errors under realistic 8-player flux. Without this test passing, we cannot claim Phase 4 done.

Output:
- `tests/integration/test_8player_load.py` — runs in < 30s, marked `@pytest.mark.slow` and gated behind `RUN_LOAD=1` env (so CI default doesn't run it but contributors / nightly DOES). Hard assertions: zero 429-equivalent raises, zero `database is locked`, ≤1 edit/sec/message, ≤5 edits/5s/channel.
- `tests/integration/test_restart_mid_combat.py` — kill-and-restart drill extending BOT-08 to combat state.
- Phase 4 SUMMARY + REQUIREMENTS + ROADMAP + STATE updates.
- ~10-15 new tests (mostly assertions inside the two integration tests + supporting fixtures).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md
@.planning/phases/04-gameplay-exploration-combat/04-CONTEXT.md
@.planning/phases/04-gameplay-exploration-combat/04-01-SUMMARY.md
@.planning/phases/04-gameplay-exploration-combat/04-02-SUMMARY.md
@src/eldritch_dm/gameplay/party_mode.py
@src/eldritch_dm/gameplay/exploration_batch.py
@src/eldritch_dm/mcp/rate_limit.py
@src/eldritch_dm/bot/cogs/exploration.py
@src/eldritch_dm/bot/cogs/combat.py
@src/eldritch_dm/bot/coalescer.py
@src/eldritch_dm/bot/setup_hook.py
@tests/integration/test_phase3_smoke.py

<interfaces>
<!-- Contracts the executor must reuse — all delivered by Plans 01 + 02. -->

From src/eldritch_dm/gameplay/party_mode.py (Plan 01):
```python
class PartyModeOrchestrator:
    def __init__(self, mcp, rate_limiter, batch_coordinator, channel_sessions,
                 *, poll_interval_ms=250, clock=time.monotonic, sleep=asyncio.sleep) -> None
    async def start_orchestrator_for_channel(self, channel_id, campaign_name, session_id) -> asyncio.Task
    async def stop_orchestrator_for_channel(self, channel_id) -> None
    async def stop_all(self) -> None
    def register_resolution_callback(self, fn) -> None
    def register_state_change_callback(self, fn) -> None
```

From src/eldritch_dm/mcp/rate_limit.py (Plan 01):
```python
class ChannelRateLimiter:
    def __init__(self, min_interval_ms=200, clock=time.monotonic, sleep=asyncio.sleep) -> None
    async def acquire(self, channel_id: str) -> None
```

From src/eldritch_dm/bot/coalescer.py (Plan 01 updated):
```python
class ChannelEditBudget:
    def __init__(self, *, max_edits=5, window_seconds=5.0,
                 clock=time.monotonic, sleep=asyncio.sleep) -> None
    async def acquire(self, message_id: int) -> None
class EmbedCoalescer:
    def __init__(self, message, *, rate_limit_seconds, channel_budget=None,
                 clock=time.monotonic, sleep=asyncio.sleep) -> None
```

From src/eldritch_dm/bot/setup_hook.py:
```python
def build_view_for_row(row: PersistentView) -> discord.ui.View | None
async def rehydrate_persistent_views(bot, *, channel_sessions, persistent_views) -> int
```

From Phase 2 test infrastructure (precedent we follow):
- `tests/integration/test_phase3_smoke.py` uses `respx` for HTTP layer mocking
- `tests/bot/test_coalescer.py` mocks `discord.Message.edit` with `AsyncMock` and asserts call cadence via `monotonic()` injection
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: 8-actor combat load test (COMBAT-08 headline)</name>
  <files>
    tests/integration/test_8player_load.py,
    tests/conftest.py,
    pyproject.toml
  </files>
  <action>
    Create `tests/integration/test_8player_load.py`. This test is the headline deliverable of Phase 4 — design for clarity, hard assertions, and CI-runnability in < 30 seconds with NO real Discord and NO real dm20.

    **Pytest marks:** mark the test with `@pytest.mark.slow` AND gate execution behind a `RUN_LOAD=1` env var (skipif). Default CI runs do NOT execute it; the nightly job and contributors with `RUN_LOAD=1 pytest -m slow` do. This mirrors the Phase 1 stress-test convention.

    Add a `slow` marker registration to `pyproject.toml` under `[tool.pytest.ini_options]` (verify if already present from Phase 1 — likely yes for the 4-channel write stress test). If absent, add:

    ```
    [tool.pytest.ini_options]
    markers = [
      "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    ]
    ```

    **Test scenario (mirrors D-34):**

    1. Construct an in-memory SQLite DB + WriterQueue + ChannelSessionRepo + PersistentViewRepo (re-use Phase 1 fixtures from `tests/conftest.py` if available, else build inline).
    2. Insert a single `channel_sessions` row with state=COMBAT, channel_id="999999999000000001".
    3. Construct a fully mocked `MCPClient` (use `respx.mock` with route handlers — preferred — OR `AsyncMock` on `MCPClient.call`):
       - `dm20__get_game_state` → returns a synthetic 8-combatant game_state (4 PCs with player_ids "200000001"..."200000004", 4 monsters with player_id=None); current_actor rotates per call.
       - `dm20__combat_action` → returns `{"outcome": "hit", "damage": 6, "target_hp_remaining": 22}` for attacks.
       - `dm20__next_turn` → mutates which combatant is "current" in the next get_game_state response.
       - `dm20__apply_effect` → returns success.
       - `dm20__party_pop_action` → empty for the first 2 calls, then returns a narration request, then empty again. Cycle.
       - `dm20__party_thinking` and `dm20__party_resolve_action` → return empty success.
    4. Construct `ChannelRateLimiter(min_interval_ms=200, clock=fake_clock.now, sleep=fake_clock.advance)` with an INJECTABLE virtual clock (so we don't actually sleep).
    5. Construct `ChannelEditBudget(max_edits=5, window_seconds=5.0, clock=fake_clock.now, sleep=fake_clock.advance)`.
    6. Construct `PartyModeOrchestrator(...)` wired against the mocks.
    7. Mock `discord.Message.edit` as an `AsyncMock` that records (timestamp, message_id) into a list when called. The mock NEVER raises — that's the point of the budget.
    8. Spin up 8 in-process EmbedCoalescer instances (one per combatant's "row" — though the spec is one coalescer per combat embed message, simulate 4 distinct "embed messages" each updated when its row changes; this is the realistic v1 layout where the SINGLE combat_embed is updated each turn, so really one coalescer per channel). Use ONE coalescer with the shared ChannelEditBudget for the channel — that's what production does.
    9. **Drive the scenario:**
       - 5 rounds, each round walks through 8 combatants in initiative order.
       - For each combatant turn, fire 4 simulated "embed update" events: turn-start (D-12 says state change after `next_turn`), action-result (after `combat_action`), effects-applied (after `apply_effect`), turn-end (after `next_turn`).
       - For PC turns (4 of 8), additionally simulate an AttackButton click that goes through ChannelRateLimiter.acquire then combat_action.
       - Use the injectable clock to ADVANCE time deterministically (no real sleep).
    10. **Assertions (hard fails):**
        - **A.** Mock `discord.Message.edit` was called >= some number of times (≤160 due to coalescing). The COALESCED count MUST be ≤ 25 (i.e., 5 rounds × 5 edits/window when rate-limited). Confirm via timestamps.
        - **B.** No two consecutive `Message.edit` calls on the SAME message_id occur < 1.0s apart in virtual time (EmbedCoalescer per-message rate).
        - **C.** Within any rolling 5s virtual-time window, no more than 5 `Message.edit` calls occurred for the same channel (ChannelEditBudget).
        - **D.** `ChannelRateLimiter.acquire` was called with `channel_id="999999999000000001"` >= some minimum number of times; the MIN delta between consecutive acquire timestamps for that channel is ≥ 0.2s virtual.
        - **E.** `database is locked` never appears in captured logs / never raises from any persistence call. (Even though the load test uses in-memory SQLite, this catches any regression in the writer-queue serialization.)
        - **F.** Total test runtime in REAL time < 30s. Assert via `time.monotonic()` at start/end of the test body.
        - **G.** `discord.HTTPException` with status=429 NEVER raised by the mocked `Message.edit`. The mock is configured to assert-fail if called too rapidly per the budget — this is a SECONDARY check on B/C.

    11. Use `pytest.fixture` to keep the test body readable; the scenario-driver should be a separate helper coroutine `_drive_combat_load_scenario(orchestrator, edit_mock, fake_clock, rounds=5)`.

    **Acceptance bar:** the test author MUST be able to run `RUN_LOAD=1 uv run pytest tests/integration/test_8player_load.py -v` and see the test pass in < 30 seconds wall-clock; the test output should include a summary line of how many edits were attempted vs how many were coalesced, e.g.:

    ```
    8-player load test summary:
      Embed update events scheduled: 160
      Message.edit calls actually issued: 23
      Coalescer suppression ratio: 85.6%
      ChannelRateLimiter mutating-call gates: 40 PC actions + 40 next_turn = 80
      Min delta between mutating MCP calls: 0.200s
      No 429s. No database-is-locked. Runtime: 4.2s.
    ```

    Print this summary via `print(...)` (pytest captures + shows on success when `-v` is passed) so future contributors can see at a glance whether the test is healthy.

    Open question: if `respx` setup costs are high for the volume of mocked calls, use `AsyncMock(side_effect=...)` directly on `MCPClient.call` with a side_effect function that branches on `tool_name`. This is the easier path; respx is preferred but optional.
  </action>
  <verify>
    <automated>RUN_LOAD=1 uv run pytest tests/integration/test_8player_load.py -v</automated>
  </verify>
  <done>
    Load test passes in < 30s; prints the summary line; satisfies COMBAT-08; assertions A-G all hold.
  </done>
</task>

<task type="auto">
  <name>Task 2: Restart-mid-combat drill (BOT-08 extension, D-35)</name>
  <files>
    tests/integration/test_restart_mid_combat.py
  </files>
  <action>
    Create `tests/integration/test_restart_mid_combat.py`. This extends the Phase 2 BOT-08 kill-and-restart drill to the COMBAT state per D-35.

    **Scenario:**

    1. Set up an in-memory SQLite DB + WriterQueue + ChannelSessionRepo + PersistentViewRepo.
    2. Seed `channel_sessions` with a row: `channel_id="999999999000000002"`, state=COMBAT, campaign_name="testcamp", claudmaster_session_id="cm-1".
    3. Seed `persistent_views` with rows representing a posted combat embed's buttons (AttackButton, DodgeButton, EndTurnButton, CastSpellButton custom_ids for a known actor_id + round=2).
    4. Construct mocked `MCPClient` + `PartyModeOrchestrator` + `ExplorationCog` + `CombatCog` (similar to Plan 02's Task 3 integration test scaffolding — re-use any helpers exported there).
    5. Start orchestrator for the channel. Confirm task is running. Cancel the orchestrator task via `await orchestrator.stop_orchestrator_for_channel(...)` — simulating a crash.
    6. Construct a FRESH bot instance (new `PartyModeOrchestrator`, new cogs) — simulating the restart.
    7. Run `setup_hook` rehydration logic explicitly (or call the helper directly):
       - `await rehydrate_persistent_views(bot, channel_sessions=repo, persistent_views=pv_repo)` — re-registers DynamicItems.
       - For each channel_sessions row with state ∈ {EXPLORATION, COMBAT}: `await orchestrator.start_orchestrator_for_channel(...)`.
    8. **Assertions:**
       - `add_dynamic_items` was called with all 4 combat button classes after rehydration.
       - The orchestrator task for our test channel is running.
       - Simulate an AttackButton click via a mocked `discord.Interaction` matching the persisted custom_id pattern (`attack:999999999000000002:<actor_id>:2`). Assert the callback dispatches (finds the class via the regex template), the turn-gatekeeper runs, and if the clicker matches current_actor.player_id the rate-limited combat_action call happens.
       - The mocked dm20's `get_game_state` shows the combat is still at round 2 (state survived).
       - No exceptions raised during rehydration.

    Use the same in-memory DB pattern as Phase 1/2 stress tests. Re-use `eldritch_dm.persistence.bootstrap.bootstrap` to ensure tables exist on the fresh DB.

    **Open question:** if `discord.Client.add_dynamic_items` cannot be invoked in tests without a real gateway connection, mock it: `bot.add_dynamic_items = MagicMock()` before setup_hook, then assert call_count==1 with the right classes tuple. Phase 2's `tests/bot/test_dynamic_items_real.py` likely already establishes this pattern — re-use.

    This test does NOT need the `slow` marker — it should run in < 5s in CI.
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_restart_mid_combat.py -x -v</automated>
  </verify>
  <done>
    Restart drill passes; rehydration re-registers DynamicItems; orchestrator restarts; mocked AttackButton click dispatches correctly after the simulated restart; no exceptions; runtime < 5s.
  </done>
</task>

<task type="auto">
  <name>Task 3: Phase 4 closure — SUMMARY + REQUIREMENTS + ROADMAP + STATE</name>
  <files>
    .planning/phases/04-gameplay-exploration-combat/04-SUMMARY.md,
    .planning/REQUIREMENTS.md,
    .planning/ROADMAP.md,
    .planning/STATE.md
  </files>
  <action>
    **Step 1 — Write `.planning/phases/04-gameplay-exploration-combat/04-SUMMARY.md`** following the standard SUMMARY template (mirror `03-03-SUMMARY.md`'s structure). Required sections:

    - **Frontmatter:** phase, plan_count=3, all tags, requires (Phase 3), provides (orchestrator, combat UI, load proof), affects (Phase 5), tech-stack (no new packages), key-files (consolidated across Plans 01-03), key-decisions (D-22 dodge resolution, D-17 monster turn behavior — pull from 04-02-SUMMARY), patterns-established (PartyModeOrchestrator, BatchCoordinator, ChannelRateLimiter, turn_gatekeeper as pure helper, asyncio.gather(return_exceptions=True) for cog callback bus), requirements-completed (full EXPLORE-* + COMBAT-01..08 + COMBAT-12 + OPS-03 list), duration, completed date.
    - **Accomplishments** — bulleted list of the major outputs of all three plans.
    - **Task Commits** — one bullet per task across all three plans with commit shorthand.
    - **Files Created/Modified** — consolidated list with one-liner purposes.
    - **Decisions Made** — at minimum: D-22 (dodge resolution), D-17 (monster turn), D-29 (mutating decorator scope), the bus-style cog callback registry, the load-test gating via `RUN_LOAD=1`.
    - **Deviations from Plan** — anything that diverged from CONTEXT D-XX; auto-fixed bugs (Rule 1) and missing-critical adjustments (Rule 2) following the precedent of `03-03-SUMMARY.md`.
    - **Issues Encountered** — anything notable.
    - **Known Stubs** — CastSpellButton (intentional v1 stub).
    - **Threat Flags** — none new; reaffirm T-04-09..T-04-16 mitigations active in code.
    - **Next Phase Readiness** — Phase 5 (Reactions + Self-Host Polish) can begin immediately. Specifically note the Reaction shim seam: the file + function in `dynamic_items.py` (AttackButton.callback) where the attack-miss + has_reaction check will surface the RiposteButton (per Plan 02 Task 3's documentation seam).
    - **Performance Snapshot** — 8-player load test runtime, suppression ratio, total test count, etc.

    **Step 2 — Mark requirements complete in `.planning/REQUIREMENTS.md`:**

    Change each of the following from `- [ ]` to `- [x]`:
    - EXPLORE-01, EXPLORE-02, EXPLORE-03, EXPLORE-04, EXPLORE-05, EXPLORE-06, EXPLORE-07
    - COMBAT-01, COMBAT-02, COMBAT-03, COMBAT-04, COMBAT-05, COMBAT-06, COMBAT-07, COMBAT-08, COMBAT-12
    - OPS-03

    DO NOT mark COMBAT-09 / COMBAT-10 / COMBAT-11 (Phase 5 Riposte).

    Update the Traceability table at the bottom of REQUIREMENTS.md if it has gained more entries; if the table is still placeholder ("pending re-roadmap"), leave it.

    **Step 3 — Mark Phase 4 + Plans complete in `.planning/ROADMAP.md`:**

    1. In the "Phases" bulleted list near the top, change `- [ ] **Phase 4: Gameplay — Exploration + Combat (Party Mode)**` to `- [x] ...`.
    2. In the Phase 4 detail section, under `**Plans**: TBD`, replace with:
       ```
       **Plans**:
       - [x] 01-PLAN-orchestrator-and-exploration.md — PartyModeOrchestrator, ExplorationCog, BatchCoordinator, ChannelRateLimiter, ChannelEditBudget — COMPLETE
       - [x] 02-PLAN-combat-cog-and-turn-gatekeeping.md — CombatCog, turn_gatekeeper, AttackButton/DodgeButton/EndTurnButton/CastSpellButton, WeaponSelectModal — COMPLETE
       - [x] 03-PLAN-load-test-and-closure.md — 8-actor load test, restart-mid-combat drill, Phase 4 closure — COMPLETE
       ```

    **Step 4 — Update `.planning/STATE.md`:**

    The STATE.md fields that must change (read existing file first to learn the exact key names — likely YAML frontmatter or similar):
    - `completed_phases`: 4 (was 3)
    - `percent_complete`: 80 (was ~60)
    - `current_phase`: `05-reactions-self-host-polish`
    - `current_plan`: `05-01`
    - `last_updated`: today's date (2026-05-21 or whatever date the task runs)
    - Append to any decisions/notes log: "Phase 4 closed — combat works end-to-end; 8-player load test green; reaction shim seam documented for Phase 5."

    If STATE.md doesn't exist yet, create it with the schema implied by the precedent (likely simple YAML frontmatter + markdown body with timeline + decisions). Verify against any STATE.md format used by gsd-sdk tooling.
  </action>
  <verify>
    <automated>grep -c '\- \[x\] \*\*EXPLORE-' .planning/REQUIREMENTS.md && grep -c '\- \[x\] \*\*COMBAT-0[1-8]' .planning/REQUIREMENTS.md && grep '\- \[x\] \*\*Phase 4' .planning/ROADMAP.md && grep 'completed_phases.*4\|completed_phases: 4' .planning/STATE.md && test -s .planning/phases/04-gameplay-exploration-combat/04-SUMMARY.md && echo "all closure checks passed"</automated>
  </verify>
  <done>
    Phase 4 SUMMARY exists with all required sections; REQUIREMENTS has [x] on all Phase 4 requirements; ROADMAP shows Phase 4 [x] and all three plans [x]; STATE.md cursor advances to 05-reactions-self-host-polish / 05-01; the verification grep returns expected counts.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| test_8player_load.py virtual clock → actual sleep | The injectable clock means the test never blocks on real time; assertion correctness depends on the clock advancing in lockstep with code-under-test's expectations. |
| Mocked discord.Message.edit → assertion oracle | The mock is the ground truth for "did we hit Discord too fast"; if the mock is wrong, the test passes falsely. Mitigation: assert at two layers — per-message rate (≤1/sec) AND per-channel budget (≤5/5s). |
| In-memory SQLite WAL behavior vs real WAL | In-memory mode does NOT exactly model WAL contention, but writer-queue serialization is the actual mitigation we're testing, and that runs identically against both. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-17 | Tampering | Future contributor disables the slow marker / RUN_LOAD gate | mitigate | Test prints a summary line on success that future contributors will notice; CI nightly job runs it; SUMMARY documents the gate. |
| T-04-18 | Repudiation | "I never broke the load test" | mitigate | Test failure output includes the specific assertion that failed (A through G) + the captured edit timeline. |
| T-04-19 | Information Disclosure | Test exposes mock dm20 responses | accept | All payloads are synthetic; no real PII or campaign data. |
| T-04-20 | DoS | Load test itself takes too long in CI nightly | mitigate | Virtual clock means the test runs in wall-clock < 30s regardless of simulated time. Assertion F enforces this. |
| T-04-SC | Tampering | Supply-chain (no new packages this plan) | accept | Plan 03 introduces NO new third-party packages — only new test files + closure paperwork. |
</threat_model>

<verification>
**Plan-level checks:**

1. `RUN_LOAD=1 uv run pytest tests/integration/test_8player_load.py -v` — passes in < 30s wall-clock; summary line printed.
2. `uv run pytest tests/integration/test_restart_mid_combat.py -x -v` — passes in < 5s.
3. `uv run pytest -m "not slow"` — full suite green (Phase 4 closure does not introduce new failures).
4. `grep -c '\\- \\[x\\] \\*\\*EXPLORE-' .planning/REQUIREMENTS.md` — returns 7 (EXPLORE-01..07).
5. `grep -c '\\- \\[x\\] \\*\\*COMBAT-0[1-8]' .planning/REQUIREMENTS.md` — returns 8.
6. `grep '\\- \\[x\\] \\*\\*COMBAT-12' .planning/REQUIREMENTS.md` — returns 1 match.
7. `grep '\\- \\[x\\] \\*\\*OPS-03' .planning/REQUIREMENTS.md` — returns 1 match.
8. `grep '\\- \\[x\\] \\*\\*Phase 4' .planning/ROADMAP.md` — returns 1 match.
9. `test -s .planning/phases/04-gameplay-exploration-combat/04-SUMMARY.md` — SUMMARY exists and is non-empty.
10. STATE.md `current_phase` is now `05-reactions-self-host-polish`.

**Risks:**
- **Virtual clock drift:** If the executor uses `time.monotonic()` somewhere internally instead of the injected `clock`, virtual time and real time diverge — the test could pass in virtual time but actually hang in wall time. Mitigation: assertion F (wall-clock < 30s) catches this; if it fires, audit for un-injected sleeps.
- **Mock-fidelity gap:** A mocked `discord.Message.edit` never returns 429s naturally — we have to ASSERT 429-would-have-happened by checking the cadence. If the assertion logic is wrong, the test passes vacuously. Mitigation: add a NEGATIVE control assertion — run a parallel scenario that DELIBERATELY violates the budget (e.g., 10 edits/3s) and confirm the assertion FAILS. (This control test stays in the file, marked `xfail`.)
- **STATE.md schema unknown:** If STATE.md uses a schema the executor doesn't recognize, the writer should `Read` the file FIRST to learn the schema, then `Edit` field-by-field. Do NOT rewrite the whole file from scratch.

**Open question:**
- Whether to emit a final `gsd-sdk query commit` for the closure docs as a SEPARATE commit from the test code commits, or batch all three task commits at the end. Lean separate commits — easier `git revert` granularity if any closure paperwork has issues.
</verification>

<success_criteria>
- 8-actor combat load test passes in < 30s wall-clock with virtual clock injection; assertions A-G hold; summary line prints.
- Restart-mid-combat drill passes; rehydration re-registers DynamicItems; orchestrator restarts; clicks dispatch.
- Phase 4 SUMMARY exists, follows the standard template, summarizes Plans 01-03 deliverables + decisions + deviations + next-phase readiness.
- REQUIREMENTS.md: EXPLORE-01..07, COMBAT-01..08, COMBAT-12, OPS-03 all marked [x].
- ROADMAP.md: Phase 4 marked [x]; all three plans marked [x].
- STATE.md: `completed_phases=4`, `percent_complete=80`, `current_phase=05-reactions-self-host-polish`, `current_plan=05-01`.
- No new failing tests in the broader suite.
- `RUN_LOAD=1 pytest` shows the load test passing; default `pytest` skips it (slow marker default-deselected).
- Requirements COMBAT-08 satisfied.
</success_criteria>

<output>
On completion, the closing commit message should be:
```
docs(04-gameplay-exploration-combat): phase 4 complete — orchestrator+combat+load test+closure
```
and should bundle the SUMMARY, REQUIREMENTS, ROADMAP, STATE updates. Test-file commits should be separate (`test(04): ...`).
</output>
