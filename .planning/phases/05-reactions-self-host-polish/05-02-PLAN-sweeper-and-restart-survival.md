---
phase: 05-reactions-self-host-polish
plan: 02
type: execute
wave: 2
depends_on:
  - 05-01
files_modified:
  - src/eldritch_dm/gameplay/riposte_sweeper.py
  - src/eldritch_dm/gameplay/reactions.py
  - src/eldritch_dm/bot/bot.py
  - src/eldritch_dm/bot/session_locks.py
  - tests/gameplay/test_riposte_sweeper.py
  - tests/gameplay/test_session_locks.py
  - tests/integration/test_riposte_restart.py
autonomous: true
requirements:
  - COMBAT-11
tags: [reactions, riposte, sweeper, restart-survival, asyncio-lock, ops-01]

must_haves:
  truths:
    - "A background `RiposteSweeper` asyncio.Task started in `EldritchBot.setup_hook` (after persistence comes online) loops on `riposte_timers.list_pending`, marks expired any row whose deadline_ts has passed, and best-effort deletes the corresponding public Discord message."
    - "The sweeper's `mark_expired` call AND the RiposteButton callback's `mark_consumed_with_round` call BOTH acquire the same per-channel `asyncio.Lock` from a shared `SessionLocks` registry, scoped by namespace `riposte:{channel_id}` — eliminating the click-at-deadline race (RESEARCH Pitfall 3)."
    - "On bot restart, the sweeper picks up any pending row whose deadline is still in the future and leaves the public Discord message intact (Discord persists components server-side; DynamicItem registry from Phase 2 routes incoming clicks). Rows past their deadline are marked expired on the first sweep iteration after startup."
    - "OPS-01 resume drill — `tests/integration/test_riposte_restart.py` — proves: build bot A on a temp DB → seed channel_session (COMBAT) + persistent_views (combat embed + riposte button) + pending riposte_timer (5s deadline) → `bot_a.close()` → build bot B on the SAME DB → bot B's `setup_hook` rehydrates persistent views, starts sweeper, sweeper sees the pending row → simulate Discord interaction with matching custom_id → callback fires, marks consumed; separately, an already-expired row gets marked expired by bot B's sweeper on first iteration."
    - "Graceful shutdown (OPS-04) cancels the sweeper task; `await bot.close()` awaits sweeper drain ≤ 1s; no orphaned background tasks."
    - "The sweeper wake-up cadence per RESEARCH Pattern 4: sleep until `min(next_deadline, 30s)`, minimum 0.1s. With 8s Riposte TTLs, the practical sleep is bounded above by 8s; an empty queue sleeps the full 30s."
  artifacts:
    - path: "src/eldritch_dm/gameplay/riposte_sweeper.py"
      provides: "RiposteSweeper class — async start()/stop() lifecycle, deadline-driven loop, shared SessionLocks integration, best-effort message deletion"
      contains: "class RiposteSweeper"
    - path: "src/eldritch_dm/bot/session_locks.py"
      provides: "SessionLocks — namespaced per-channel asyncio.Lock registry; `acquire(namespace, channel_id) -> asyncio.Lock` returns the same Lock for the same (namespace, channel_id) tuple"
      contains: "class SessionLocks"
    - path: "src/eldritch_dm/gameplay/reactions.py"
      provides: "EXTENDED: handle_riposte_click wraps its read-then-mark-consumed sequence in the shared SessionLocks lock for `riposte:{channel_id}` — replacing the PLAN-02-LOCK-SEAM marker placed in Plan 01"
      contains: "session_locks"
    - path: "tests/integration/test_riposte_restart.py"
      provides: "OPS-01 resume drill — kill bot mid-combat-with-pending-riposte, restart fresh bot on same DB, prove timer survives and callback works"
      contains: "test_pending_riposte_survives_restart"
  key_links:
    - from: "src/eldritch_dm/gameplay/riposte_sweeper.py"
      to: "src/eldritch_dm/bot/session_locks.py"
      via: "Sweeper acquires lock `riposte:{channel_id}` before marking a row expired — symmetric with RiposteButton.callback"
      pattern: "session_locks\\.acquire\\([\"']riposte"
    - from: "src/eldritch_dm/gameplay/reactions.py"
      to: "src/eldritch_dm/bot/session_locks.py"
      via: "handle_riposte_click wraps the gate-and-mutate sequence in the same `riposte:{channel_id}` lock"
      pattern: "session_locks\\.acquire\\([\"']riposte"
    - from: "src/eldritch_dm/bot/bot.py"
      to: "src/eldritch_dm/gameplay/riposte_sweeper.py"
      via: "EldritchBot.setup_hook constructs RiposteSweeper, calls .start() AFTER persistence + DynamicItem rehydration; EldritchBot.close awaits .stop()"
      pattern: "RiposteSweeper|riposte_sweeper"
    - from: "tests/integration/test_riposte_restart.py"
      to: "src/eldritch_dm/gameplay/riposte_sweeper.py"
      via: "Drill instantiates two bots on the same temp DB; the second bot's sweeper observes rows the first bot left behind"
      pattern: "RiposteSweeper|list_pending"
---

<objective>
Close the restart-survival half of COMBAT-09/10/11 by shipping the deadline-driven RiposteSweeper background task, a shared per-channel asyncio.Lock registry that eliminates the click-vs-sweeper race, and the OPS-01 resume drill that proves the entire reaction system survives a bot kill.

Purpose: Plan 01 made the Riposte feature *work*. Plan 02 makes it *survive*. The sweeper is small (one background task), the SessionLocks registry is tiny, but together they're the difference between "looks like it works" and "passes the killer demo of restarting the bot mid-game." OPS-01 is the marketing-grade proof that EldritchDM does what it says.

Output:
- `src/eldritch_dm/bot/session_locks.py` — namespaced per-channel `asyncio.Lock` registry
- `src/eldritch_dm/gameplay/riposte_sweeper.py` — RESEARCH Pattern 4 verbatim
- Plan 01's PLAN-02-LOCK-SEAM filled in: `reactions.handle_riposte_click` now `async with session_locks.acquire("riposte", channel_id):`
- Sweeper started in `setup_hook` after persistence + rehydration; stopped in `EldritchBot.close()` (OPS-04 chain)
- `tests/integration/test_riposte_restart.py` — full OPS-01 drill with two bot instances on the same temp DB
- ~15 new tests
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@.planning/phases/05-reactions-self-host-polish/05-CONTEXT.md
@.planning/phases/05-reactions-self-host-polish/05-RESEARCH.md
@.planning/phases/05-reactions-self-host-polish/05-01-PLAN-riposte-and-monster-driver.md
@src/eldritch_dm/bot/bot.py
@src/eldritch_dm/gameplay/reactions.py
@src/eldritch_dm/persistence/riposte_timers_repo.py
@src/eldritch_dm/persistence/bootstrap.py
@tests/integration/test_restart_mid_combat.py
@tests/persistence/conftest.py

**Side findings baked in (from RESEARCH + user clarification):**
- The sweeper and click callback MUST share the per-channel asyncio.Lock — namespaced as `riposte:{channel_id}` to coexist with Phase 4's `ChannelRateLimiter` per-channel locks (which are separate concerns; do not reuse the rate_limiter's Lock instances).
- Sweeper polls `riposte_timers.list_pending()` only — does NOT poll oMLX or dm20. oMLX downtime must not delay timer expiry (RESEARCH anti-pattern callout).
- `View(timeout=8.0)` is forbidden — the View is persistent (timeout=None); deadline is enforced by (a) sweeper marking expired, (b) callback's `deadline_ts > now()` check rejecting late clicks. RESEARCH anti-pattern.
- Sweeper uses the `idx_riposte_pending_deadline` partial index that already exists in schema.sql (Phase 1).

<interfaces>
<!-- Already-existing contracts the executor must reuse. -->

From src/eldritch_dm/persistence/riposte_timers_repo.py (post-Plan 01):
```python
class RiposteTimerRepo:
    async def list_pending(self) -> list[RiposteTimer]              # uses idx_riposte_pending_deadline
    async def mark_expired(self, id_: int) -> None
    async def mark_consumed_with_round(self, id_: int, round_n: int) -> None
    async def get(self, id_: int) -> RiposteTimer | None
```

From src/eldritch_dm/gameplay/reactions.py (post-Plan 01):
```python
async def handle_riposte_click(
    *, interaction, timer_id, expected_user_id, repo, mcp, rate_limiter,
    log, current_round_provider,
) -> None
# Contains a `# PLAN-02-LOCK-SEAM:` marker comment indicating where to wrap.
```

From discord.py:
```python
bot.get_channel(channel_id: int) -> discord.TextChannel | None         # cache-only lookup
await bot.fetch_channel(channel_id: int) -> discord.abc.GuildChannel   # API call
await channel.fetch_message(message_id: int) -> discord.Message
await message.delete() -> None
# All of the above raise discord.NotFound / Forbidden / HTTPException on failure.
```

From src/eldritch_dm/bot/bot.py (Phase 4 setup_hook structure):
```python
class EldritchBot(commands.Bot):
    async def setup_hook(self) -> None:
        # 1. Persistence/MCP/sanitizer wiring (Phase 1)
        # 2. DynamicItem registration (Phase 2)
        # 3. add_view rehydration (Phase 2)
        # 4. Cog loads (Phase 3-4)
        # 5. Phase 4 wiring: rate_limiter, batch_coordinator, orchestrator
        # 6. Phase 5 Plan 01 wiring: pc_classes, monster_driver
        # NEW THIS PLAN: 7. session_locks + riposte_sweeper construction; start sweeper
    async def close(self) -> None:
        # OPS-04 graceful shutdown:
        # 1. Stop orchestrator (Phase 4)
        # 2. NEW: Stop riposte_sweeper
        # 3. Close MCP client, flush sanitizer audit, close DB (Phase 1)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: SessionLocks registry + RiposteSweeper + lock-seam plug-in (RED→GREEN)</name>
  <files>
    src/eldritch_dm/bot/session_locks.py,
    src/eldritch_dm/gameplay/riposte_sweeper.py,
    src/eldritch_dm/gameplay/reactions.py,
    src/eldritch_dm/bot/bot.py,
    tests/gameplay/test_session_locks.py,
    tests/gameplay/test_riposte_sweeper.py
  </files>
  <behavior>
    SessionLocks (src/eldritch_dm/bot/session_locks.py):
      - Test 1: `SessionLocks().acquire("riposte", "channel123")` returns an `asyncio.Lock` instance.
      - Test 2: Calling `acquire("riposte", "channel123")` twice returns the SAME Lock instance (identity check `is`).
      - Test 3: `acquire("riposte", "channelA")` and `acquire("riposte", "channelB")` return DIFFERENT Lock instances (per-channel isolation).
      - Test 4: `acquire("riposte", "channelA")` and `acquire("rate_limit", "channelA")` return DIFFERENT Lock instances (namespace isolation — sweeper's lock doesn't accidentally serialize with the rate_limiter's lock).
      - Test 5: Lock acquisition order is deterministic: two `async with locks.acquire("riposte", "X")` blocks serialize (the second awaits while the first holds).
      - Test 6: A `SessionLocks` instance is thread-safe in the sense that creation under asyncio.gather of 100 concurrent `acquire(...)` calls for the same key returns exactly one Lock (verified via `id(...)` set of size 1). Use a tiny internal asyncio.Lock around the dict mutation.

    RiposteSweeper (src/eldritch_dm/gameplay/riposte_sweeper.py — RESEARCH Pattern 4 verbatim):
      - Test 7: `RiposteSweeper.start()` creates an asyncio.Task; `RiposteSweeper.stop()` cancels it and awaits clean shutdown (suppresses CancelledError).
      - Test 8: Sweeper iteration with no pending rows sleeps for `default_sleep_s` (30.0); injectable clock+sleep allow assertion.
      - Test 9: Sweeper iteration with one pending row whose `deadline_ts > now()` sleeps `(deadline - now).total_seconds()` (capped between min_sleep and default_sleep).
      - Test 10: Sweeper iteration with one pending row whose `deadline_ts <= now()` calls `repo.mark_expired(row.id)` and then attempts `bot.get_channel(int(row.channel_id)).fetch_message(int(row.message_id))` → `.delete()`. AsyncMock the chain.
      - Test 11: Message deletion failures (discord.NotFound, Forbidden, HTTPException) are caught and logged at WARNING; sweeper loop continues.
      - Test 12: Sweeper acquires `session_locks.acquire("riposte", row.channel_id)` BEFORE calling `repo.mark_expired(...)` (test asserts lock was entered before the repo call via mock ordering).
      - Test 13: Sweeper raises `asyncio.CancelledError` is re-raised (cooperative cancellation works).
      - Test 14: Unexpected exceptions in the loop body (e.g. repo raises) are caught, logged as EXCEPTION, and the loop continues after a 1.0s defensive sleep.

    Lock-seam in reactions.handle_riposte_click (gameplay/reactions.py):
      - Test 15: The PLAN-02-LOCK-SEAM marker comment from Plan 01 is REPLACED by a real `async with session_locks.acquire("riposte", channel_id):` wrapper around the read-then-mark-consumed sequence.
      - Test 16: With a synthetic concurrent-click test (two clicks for the same timer_id fired via asyncio.gather), exactly ONE completes the mark_consumed path and the other observes `status='consumed'` and emits RIPOSTE_EXPIRED — under load this is now deterministic (not just lucky as in Plan 01).
      - Test 17: With a synthetic race test (sweeper marks expired at T=8.000s, click arrives at T=7.999s), the sweeper waits for the click's lock to release; the click completes successfully and the sweeper THEN sees status='consumed' and skips its mark_expired (the mark_expired SQL is conditional on `status='pending'` — see Action below).
  </behavior>
  <action>
    Create `src/eldritch_dm/bot/session_locks.py`:
      - Module docstring cites RESEARCH Pitfall 3 + Pattern 4.
      - `class SessionLocks`:
        ```python
        def __init__(self) -> None:
            self._locks: dict[tuple[str, str], asyncio.Lock] = {}
            self._guard = asyncio.Lock()  # serializes dict mutation

        def _key(self, namespace: str, channel_id: str) -> tuple[str, str]:
            return (namespace, str(channel_id))

        async def acquire(self, namespace: str, channel_id: str) -> asyncio.Lock:
            key = self._key(namespace, channel_id)
            async with self._guard:
                lock = self._locks.get(key)
                if lock is None:
                    lock = asyncio.Lock()
                    self._locks[key] = lock
            return lock
        ```
      - Usage convention: `lock = await session_locks.acquire("riposte", channel_id); async with lock: ...`
      - Add a context-manager helper for ergonomics: `def lock_for(self, namespace: str, channel_id: str) -> AbstractAsyncContextManager[None]` that combines acquire + `async with`. (Executor's call on whether the underlying API or the helper is canonical; document both in the module docstring.)

    Create `src/eldritch_dm/gameplay/riposte_sweeper.py` per RESEARCH Pattern 4 verbatim with one addition: every `mark_expired` call is wrapped in `async with session_locks.lock_for("riposte", row.channel_id):`. The mark_expired SQL in the repo is `UPDATE riposte_timers SET status='expired' WHERE id=? AND status='pending'` — conditional on still-pending, so if the callback already raced to consumed, the sweeper's UPDATE affects 0 rows (idempotent + correct).

    Sweeper constructor: `RiposteSweeper(repo: RiposteTimerRepo, bot: discord.Client, session_locks: SessionLocks, default_sleep_s: float = 30.0, min_sleep_s: float = 0.1, clock=datetime.utcnow, sleep=asyncio.sleep, log: BoundLogger)`. Inject clock + sleep for deterministic tests.

    Update `src/eldritch_dm/gameplay/reactions.py`:
      - Replace the `# PLAN-02-LOCK-SEAM:` marker block with the actual lock wrapper.
      - Pass `session_locks: SessionLocks` as a new required keyword arg of `handle_riposte_click`.
      - Update `bot/dynamic_items.py` `RiposteButton.callback` to pass `session_locks=interaction.client.session_locks` to the helper.
      - Update Plan 01's tests for `handle_riposte_click` to inject a real `SessionLocks()` instance (cheap; no mocking needed since asyncio.Lock works fine in test event loop).

    Update `EldritchBot.setup_hook` (bot/bot.py):
      - After Plan 01's `monster_driver` construction, add:
        ```python
        self.session_locks = SessionLocks()
        self.riposte_sweeper = RiposteSweeper(
            repo=self.riposte_timers,
            bot=self,
            session_locks=self.session_locks,
            log=get_logger("eldritch_dm.gameplay.riposte_sweeper"),
        )
        await self.riposte_sweeper.start()
        ```
      - Order matters: sweeper starts AFTER `rehydrate_persistent_views` (Phase 2) so DynamicItems are registered before any race-window pending timers are touched.

    Update `EldritchBot.close()` (OPS-04 chain — bot/bot.py):
      - BEFORE existing `await self.orchestrator.stop_all()`, add `await self.riposte_sweeper.stop()` with `with contextlib.suppress(asyncio.CancelledError)`. Document why the sweeper stops first: pending mark_expired calls during shutdown need the session_locks to still be alive (they are, but the sweeper task draining first means no half-finished sweeper iterations).

    Update `src/eldritch_dm/persistence/riposte_timers_repo.py`:
      - Verify `mark_expired` SQL has `WHERE id=? AND status='pending'` (the conditional form). If Phase 1 shipped it as unconditional `WHERE id=?`, update it to be conditional. Add a test in `tests/persistence/test_riposte_timers_repo.py` asserting an idempotent second `mark_expired(id)` on an already-consumed row is a no-op (0 rows affected).

    Write the 17 tests across `tests/gameplay/test_session_locks.py` and `tests/gameplay/test_riposte_sweeper.py`. Use injectable clock pattern from Phase 4's `test_rate_limit.py` (precedent).
  </action>
  <verify>
    <automated>uv run pytest tests/gameplay/test_session_locks.py tests/gameplay/test_riposte_sweeper.py tests/gameplay/test_reactions.py tests/gameplay/test_riposte_callback.py tests/persistence/test_riposte_timers_repo.py -x -v && grep -v '^#' src/eldritch_dm/gameplay/reactions.py | grep -c 'PLAN-02-LOCK-SEAM' | tee /tmp/gate.txt && [ "$(cat /tmp/gate.txt)" = "0" ]</automated>
  </verify>
  <done>
    SessionLocks registry returns identity-equal Locks per (namespace, channel_id); RiposteSweeper expires past-deadline rows under the shared lock; `handle_riposte_click` wraps its read-then-mark sequence in the same lock; PLAN-02-LOCK-SEAM marker is GONE (gate proves it); concurrent click + race-with-sweeper tests are deterministic; 17+ tests green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: OPS-01 resume drill — two-bot integration test (RED→GREEN)</name>
  <files>
    tests/integration/test_riposte_restart.py,
    tests/integration/conftest.py
  </files>
  <behavior>
    test_riposte_restart.py — OPS-01 resume drill. All tests use a shared temp eldritch.sqlite3 file, mocked MCPClient (respx + AsyncMock), and a fake `discord.Client`-like shim (re-use the existing fixture pattern from `tests/integration/test_restart_mid_combat.py` from Phase 4 Plan 03).

      - Test 1 (`test_pending_riposte_survives_restart`): Seed DB with channel_session (state=COMBAT, round=2), persistent_view rows for the combat embed AND a riposte:42:99 row, and a riposte_timers row id=42 (pending, deadline 5s in future, user_id=99, character_id="thorin", monster_uuid="goblin-scout", weapon_used="longsword"). Build bot A, run setup_hook (mocked). Assert: bot_a.riposte_sweeper.is_running() is True; bot_a's add_view was called with a view containing a RiposteButton matching custom_id `riposte:42:99`. Call `await bot_a.close()`. Build bot B on the SAME temp DB. Run bot_b.setup_hook. Assert: bot_b.riposte_sweeper sees row 42 in list_pending; row 42 is STILL `status='pending'` (deadline hasn't expired yet); the sweeper's next sleep would be ≤ remaining-deadline-seconds. Simulate an interaction with custom_id `riposte:42:99` and user_id=99; assert RiposteButton.callback runs through to mark_consumed_with_round, and combat_action mock was called once with the expected args.

      - Test 2 (`test_expired_timer_cleaned_on_restart`): Seed DB with a riposte_timers row that's ALREADY past deadline (deadline = now() - 1s, status='pending'). Build bot B, run setup_hook. Tick the sweeper one iteration (advance the injected clock). Assert: row is now status='expired'; the message_delete mock was called once. Subsequent sweeper iterations don't re-process the row.

      - Test 3 (`test_setup_hook_orders_sweeper_after_rehydration`): Spy on the order of calls during setup_hook. Assert: `rehydrate_persistent_views` is awaited BEFORE `riposte_sweeper.start()`. Critical because Phase 2's DynamicItem registry must be in place before any sweeper-triggered Discord interactions could route.

      - Test 4 (`test_consumed_in_round_survives_restart`): Seed a riposte_timers row with status='consumed', consumed_in_round=3. Build bot B, run setup_hook. Construct a synthetic eligibility check for the same character_id in round 3. Assert: `check_riposte_eligibility(..., current_round=3)` returns None (reaction budget exhausted in round 3). When `current_round=4`, returns RiposteEligibility (new round, budget refreshed). Proves the reaction-budget shim is restart-stable.

      - Test 5 (`test_graceful_shutdown_cancels_sweeper`): Build bot, setup_hook, capture `bot.riposte_sweeper._task`. Call `await bot.close()`. Assert: the task is done() AND its exception is None OR CancelledError (clean cancellation). Total close() wall-clock < 2s.

      - Test 6 (`test_sweeper_handles_orphaned_message`): Seed a row whose message_id points to a non-existent Discord message (mock raises discord.NotFound on fetch_message). Tick sweeper past deadline. Assert: row is marked expired; sweeper logs `riposte_message_delete_skipped`; sweeper does NOT crash.

    All 6 tests must complete in < 5s wall-clock combined (RESEARCH Q12 + Q10 budget).
  </behavior>
  <action>
    Reuse the test infrastructure from `tests/integration/test_restart_mid_combat.py` (Phase 4 Plan 03's BOT-08 extension drill):
      - `temp_db_path` fixture (tmp_path / "eldritch.sqlite3")
      - `bootstrap_temp_db` async fixture that runs `persistence.bootstrap.bootstrap(temp_db_path)`
      - `fake_mcp_client` fixture (respx-backed)
      - `make_bot` factory that constructs an EldritchBot with the temp DB and mocked MCP — see existing `test_restart_mid_combat.py` for the exact pattern; if generalization is needed extract to `tests/integration/conftest.py`.

    Build the six tests:
      - Seed helpers: `seed_channel_session(conn, channel_id, state, round_n)`, `seed_persistent_view(conn, custom_id, view_class, message_id, channel_id, payload_json)`, `seed_riposte_timer(conn, **fields)`. Put these in `tests/integration/conftest.py` so future plans can reuse.
      - Use AsyncMock for `bot.get_channel`, `channel.fetch_message`, `message.delete`. Verify call counts + args.
      - Use `pytest.mark.asyncio` (mode="auto" already configured per Phase 4 Plan 03 deviation #2 — use `@pytest_asyncio.fixture` for fixtures).
      - For the sweeper-tick injection, construct the sweeper with `clock=lambda: fake_now` and `sleep=fake_sleep` so tests can drive iterations deterministically (precedent: tests/gameplay/test_riposte_sweeper.py from Task 1).

    The drill MUST mock `combat_action`'s response with a realistic dm20 outcome text so the parser exercise is end-to-end (e.g. `"**Hit!** Thorin hits Goblin Scout."` for the successful riposte path in Test 1).

    Make Test 1's interaction simulation as realistic as possible without spinning up a real Discord gateway: construct a fake `discord.Interaction` with `user.id=99`, `channel_id=...`, `data={"custom_id": "riposte:42:99"}`. Manually invoke `RiposteButton.callback(interaction)` via the registered DynamicItem's `from_custom_id` factory pattern that Phase 2 established. If the existing `test_restart_mid_combat.py` already has a `simulate_button_click(bot, custom_id, user_id)` helper, reuse it; if not, add one to `tests/integration/conftest.py`.

    Document the drill as the **OPS-01 acceptance gate**: a comment block at the top of test_riposte_restart.py spelling out which lines satisfy which subclaim of OPS-01 (kill bot → sweeper picks up → callback works → expired cleaned → graceful shutdown).
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_riposte_restart.py -x -v && uv run pytest tests/integration/test_restart_mid_combat.py -x -v</automated>
  </verify>
  <done>
    OPS-01 resume drill green: pending timer survives bot-A → bot-B handoff with the same DB; expired timer auto-cleaned on restart; sweeper starts after rehydration; graceful shutdown cancels sweeper cleanly; consumed_in_round persists across restart (reaction budget is restart-stable); orphaned messages handled gracefully. 6 tests in < 5s combined wall-clock; Phase 4's restart-mid-combat drill still passes (no regression).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Sweeper (background task) ↔ RiposteButton.callback | Race-prone seam; mitigated by shared SessionLocks. |
| Bot A's DB writes ↔ Bot B's DB reads (across process restart) | SQLite WAL + Phase 1 single-writer queue make this safe; sweeper only reads + atomic-updates. |
| Discord HTTP (fetch_message, delete_message) ↔ sweeper | Untrusted (Discord may 404/403/500); all errors caught + logged. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-10 | Tampering | Click-vs-sweeper race (RESEARCH Pitfall 3) | mitigate | Shared `SessionLocks.lock_for("riposte", channel_id)` wraps both code paths; `mark_expired` SQL is conditional `WHERE status='pending'` so a lost race produces no-op (correct outcome). Tests 15-17 prove. |
| T-05-11 | DoS | Sweeper busy-loop if `next_deadline` is in the past forever | mitigate | `max(min_sleep_s, ...)` floor of 0.1s; loop body always advances state (marks expired) so no infinite hang. |
| T-05-12 | Information Disclosure | Sweeper logs row contents (user_id, channel_id, message_id) | accept | Structured log binds those fields; no raw player text touches the sweeper path. Self-host log files are operator-controlled. |
| T-05-13 | Denial of Service | Discord HTTP failures cascade and stop the sweeper | mitigate | `try/except (discord.NotFound, Forbidden, HTTPException, ValueError):` per RESEARCH Pattern 4; sweeper logs and proceeds. |
| T-05-14 | Tampering | Bot B inherits Bot A's pc_classes / riposte_timers tables — what if Bot A wrote corrupt rows? | accept | Plan 01's pc_classes upsert + repo unit tests prove writes are well-formed. Cross-bot corruption is out of scope for v1; v2 may add a schema-checksum check at bootstrap. |
| T-05-15 | Elevation of Privilege | Sweeper attempts to delete messages in a channel the bot no longer has access to | mitigate | `discord.Forbidden` is caught + logged; row is still marked expired so it doesn't loop. |
| T-05-SC | Supply chain | No new third-party packages | accept | Plan 02 introduces zero new pip dependencies — `contextlib.suppress`, `asyncio`, `datetime` are stdlib. |
</threat_model>

<verification>
**Plan-level checks (in addition to per-task `<verify>`):**

1. `uv run pytest tests/gameplay/test_session_locks.py tests/gameplay/test_riposte_sweeper.py tests/integration/test_riposte_restart.py -v` — all green.
2. Full prior test suite still green: `uv run pytest -q` — Phase 4's 728 + Plan 01's ~30 + this plan's ~17 = ~775 passing tests.
3. `grep -v '^#' src/eldritch_dm/gameplay/reactions.py | grep -c 'PLAN-02-LOCK-SEAM'` — returns 0 (marker is replaced by real implementation).
4. `grep -c 'await self.riposte_sweeper.start()' src/eldritch_dm/bot/bot.py` — returns ≥1.
5. `grep -c 'await self.riposte_sweeper.stop()' src/eldritch_dm/bot/bot.py` — returns ≥1 (in close()).
6. `uv run ruff check src/eldritch_dm/gameplay/riposte_sweeper.py src/eldritch_dm/bot/session_locks.py` — clean.
7. `uv run lint-imports` — passes (`bot.session_locks` may be imported by `gameplay.reactions` since gameplay is allowed to import from `bot`'s LEAF utility modules; if import-linter contracts disallow this, MOVE session_locks under `src/eldritch_dm/gameplay/session_locks.py` instead — the executor's call. Document the move if it happens.)

**Risks:**
- **Import-linter contract for bot/session_locks.py:** Phase 4 added a contract preventing `gameplay` from importing `bot`. SessionLocks is bot-flavored (lives in bot/) but is used by gameplay. Executor must either (a) move it under `gameplay/` (cleaner — recommended) or (b) explicitly carve an exception in the contract. Recommendation: rename file to `src/eldritch_dm/gameplay/session_locks.py` — semantically it's a gameplay primitive (per-channel synchronization), not a Discord primitive. Update all references in this plan accordingly when implementing. The frontmatter lists the bot/ path; if you move it, also update frontmatter via a self-correction note in the SUMMARY.
- **Sweeper start ordering:** Tests must guarantee setup_hook calls `rehydrate_persistent_views` BEFORE `riposte_sweeper.start()`. If the executor refactors setup_hook for clarity, they must preserve the ordering — assert via Test 3.
- **OPS-01 reuse from Phase 4:** Phase 4's `test_restart_mid_combat.py` (Plan 03) is the precedent for two-bot drill mechanics. Reuse, don't reinvent. Any divergence is a yellow flag.
- **Sweeper cadence under high-throughput:** With many concurrent pending timers, the `min(next_deadline, 30s)` heuristic can keep the sweeper awake at high frequency. Acceptable for v1's single-table single-game scope; v2 may add per-channel sweepers if multi-server load matters.

**Open question (resolve via implementation, document in SUMMARY):**
- Should `RiposteSweeper.stop()` flush in-flight `mark_expired` calls or just cancel? Lean cancel (clean shutdown semantics); document the choice.
- Should `RiposteSweeper` log `sweeper_woken` at INFO or DEBUG? Lean DEBUG (otherwise log spam in long-running self-host); document the choice.
</verification>

<success_criteria>
- `SessionLocks` registry returns identity-equal asyncio.Lock per (namespace, channel_id); namespace isolation verified.
- `RiposteSweeper` expires past-deadline rows under the shared lock; best-effort deletes Discord messages; survives Discord HTTP errors.
- `reactions.handle_riposte_click` and the sweeper's mark_expired path BOTH acquire the same `riposte:{channel_id}` lock — click-at-deadline race is deterministic.
- `EldritchBot.setup_hook` starts the sweeper AFTER persistent-view rehydration; `EldritchBot.close()` stops the sweeper cleanly within the OPS-04 chain.
- `tests/integration/test_riposte_restart.py` proves: pending timer survives bot-A → bot-B handoff with the same DB; expired timer auto-cleaned on restart; consumed_in_round persists across restart; graceful shutdown is clean; orphaned Discord messages are handled.
- PLAN-02-LOCK-SEAM marker from Plan 01 is fully replaced.
- 15+ new tests pass; existing tests still pass; ruff + lint-imports clean.
- Requirement COMBAT-11 and OPS-01 are functionally satisfied (final [x] marks happen in Plan 03's closure).
</success_criteria>

<output>
On completion, create `.planning/phases/05-reactions-self-host-polish/05-02-SUMMARY.md` per the standard template, including:
- new files + LOC counts (session_locks.py, riposte_sweeper.py, test_riposte_restart.py)
- decisions made (especially: did session_locks land under bot/ or gameplay/? did sweeper.stop flush or cancel?)
- test count delta (~15-17 new)
- next-plan readiness signal: "Plan 03 may now wrap the Phase 5 closure work — README, run.py, launchd plist, env audit, REQUIREMENTS/ROADMAP/STATE updates — with full confidence that the reaction system is correct AND restart-safe."
</output>
