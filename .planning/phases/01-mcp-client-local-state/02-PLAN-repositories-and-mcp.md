---
phase: 01-mcp-client-local-state
plan: 02
type: execute
wave: 2
depends_on:
  - 01-01
files_modified:
  - src/eldritch_dm/persistence/channel_sessions_repo.py
  - src/eldritch_dm/persistence/persistent_views_repo.py
  - src/eldritch_dm/persistence/riposte_timers_repo.py
  - src/eldritch_dm/persistence/sanitizer_audit_repo.py
  - src/eldritch_dm/persistence/__init__.py
  - src/eldritch_dm/mcp/__init__.py
  - src/eldritch_dm/mcp/errors.py
  - src/eldritch_dm/mcp/client.py
  - src/eldritch_dm/mcp/health.py
  - src/eldritch_dm/mcp/tools.py
  - tools/gen_mcp_wrappers.py
  - tests/persistence/test_channel_sessions_repo.py
  - tests/persistence/test_persistent_views_repo.py
  - tests/persistence/test_riposte_timers_repo.py
  - tests/persistence/test_sanitizer_audit_repo.py
  - tests/mcp/__init__.py
  - tests/mcp/test_client.py
  - tests/mcp/test_health.py
  - tests/mcp/test_tools.py
autonomous: true
requirements:
  - LOC-05
  - MCP-01
  - MCP-02
  - MCP-03
  - MCP-04
  - MCP-05
  - MCP-06
  - MCP-07
  - OPS-02
must_haves:
  truths:
    - "Four repositories provide CRUD for their tables; writes go through WriterQueue (BEGIN IMMEDIATE); reads use lock-free aiosqlite connections"
    - "Repositories return frozen pydantic models, never raw rows or dicts"
    - "MCPClient.call(tool_name, **arguments) POSTs to MCP_EXECUTE_URL with `{tool_name, arguments}`, applies tenacity retry on timeout/network/5xx (3 attempts, 0.5s/1s/2s backoff), surfaces 4xx as MCPToolError without retry"
    - "Circuit breaker trips OPEN after 3 consecutive HealthCheck failures; first success returns to CLOSED; while OPEN, MCPClient.call raises MCPCircuitOpen without hitting the network"
    - "Typed wrapper functions for the 28-tool first wave exist in mcp/tools.py and route through MCPClient.call"
    - "Every MCP call binds structlog context: tool_name, attempt_n, duration_ms, channel_id/campaign/session when supplied as kwargs"
    - "respx-mocked tests cover happy path, retry-on-timeout, no-retry-on-4xx, circuit-open, and one happy-path per typed wrapper"
  artifacts:
    - path: "src/eldritch_dm/persistence/channel_sessions_repo.py"
      provides: "ChannelSessionRepo with get/upsert/list_active/set_state/delete"
      exports: ["ChannelSessionRepo"]
    - path: "src/eldritch_dm/persistence/persistent_views_repo.py"
      provides: "PersistentViewRepo with insert/get/list_by_channel/delete_for_message"
      exports: ["PersistentViewRepo"]
    - path: "src/eldritch_dm/persistence/riposte_timers_repo.py"
      provides: "RiposteTimerRepo with insert/mark_consumed/mark_expired/list_pending"
      exports: ["RiposteTimerRepo"]
    - path: "src/eldritch_dm/persistence/sanitizer_audit_repo.py"
      provides: "SanitizerAuditRepo append-only insert"
      exports: ["SanitizerAuditRepo"]
    - path: "src/eldritch_dm/mcp/errors.py"
      provides: "Structured MCP exception hierarchy"
      exports: ["MCPError", "MCPTimeoutError", "MCPNetworkError", "MCPToolError", "MCPCircuitOpen"]
    - path: "src/eldritch_dm/mcp/client.py"
      provides: "MCPClient with httpx.AsyncClient + tenacity retry + circuit breaker integration"
      exports: ["MCPClient"]
    - path: "src/eldritch_dm/mcp/health.py"
      provides: "HealthCheck async loop + CircuitBreaker state machine"
      exports: ["HealthCheck", "CircuitBreaker", "CircuitState", "get_circuit_state"]
    - path: "src/eldritch_dm/mcp/tools.py"
      provides: "Typed wrapper functions for first-wave dm20 tools"
      exports: ["create_campaign", "load_campaign", "list_campaigns", "get_campaign_info", "create_character", "update_character", "import_from_dndbeyond", "start_claudmaster_session", "end_claudmaster_session", "start_party_mode", "stop_party_mode", "party_pop_action", "party_thinking", "party_get_prefetch", "party_resolve_action", "start_combat", "end_combat", "next_turn", "combat_action", "apply_effect", "remove_effect", "get_game_state", "get_claudmaster_session_state", "validate_character_rules", "load_rulebook", "search_rules", "roll_dice", "dice_roll", "verify_with_api"]
    - path: "tools/gen_mcp_wrappers.py"
      provides: "Optional generator parsing ddmcpskills.md → stub wrappers"
      exports: ["main"]
  key_links:
    - from: "repositories"
      to: "WriterQueue.submit"
      via: "all mutating methods enqueue work via writer_queue"
      pattern: "writer_queue\\.submit"
    - from: "MCPClient.call"
      to: "CircuitBreaker.state"
      via: "raises MCPCircuitOpen when state == OPEN before any network call"
      pattern: "MCPCircuitOpen"
    - from: "mcp/tools.py wrappers"
      to: "MCPClient.call"
      via: "kwargs → arguments dict → client.call(tool_name, **arguments)"
      pattern: "client\\.call\\("
---

<objective>
Stack the second tier on top of plan 01's foundation: the four repositories that mediate every read/write against the local SQLite, and the MCP client that mediates every call to dm20 at oMLX. Repositories use plan 01's `WriterQueue` for writes and read-only connections for reads. MCP client wraps `httpx.AsyncClient` with `tenacity` retry, structured exceptions, and a health-driven circuit breaker. The typed wrapper layer in `tools.py` is what every later phase imports — code never calls `MCPClient.call("dm20__create_campaign", ...)` directly.

Purpose: All gameplay state lives in dm20 (we never touch `~/.omlx/dm.db`); all Discord-state lives behind these four repositories. The MCP wrapper layer is the only door between EldritchDM and dm20.

Output: Repositories + MCP client + 28 typed wrappers + an optional generator script. Fully unit-tested with respx-mocked HTTP and tmp_path SQLite.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-mcp-client-local-state/01-CONTEXT.md
@.planning/phases/01-mcp-client-local-state/01-01-SUMMARY.md
@.planning/REQUIREMENTS.md
@ddmcpskills.md
@src/eldritch_dm/persistence/connection.py
@src/eldritch_dm/persistence/models.py

<interfaces>
<!-- From plan 01's persistence layer — executor uses these directly. -->

From src/eldritch_dm/persistence/connection.py:
- async def open_connection(db_path: str | os.PathLike, busy_timeout_ms: int = 5000) -> AsyncContextManager[aiosqlite.Connection]
- class WriterQueue:
    async def start(self) -> None
    async def submit(self, fn: Callable[[aiosqlite.Connection], Awaitable[T]]) -> T
    async def stop(self) -> None
    def qsize(self) -> int

From src/eldritch_dm/persistence/models.py:
- ChannelSession, PersistentView, RiposteTimer, SanitizerAuditRow (frozen pydantic)
- ChannelState (StrEnum: LOBBY, EXPLORATION, COMBAT_INIT, COMBAT, NPC_DLG, PAUSED)
- RiposteStatus (StrEnum: pending, consumed, expired, cancelled)

From src/eldritch_dm/config.py:
- Settings.mcp_execute_url, .mcp_tools_url, .omlx_endpoint, .omlx_health_interval, .omlx_circuit_breaker_threshold
- get_settings() -> Settings (cached)

From src/eldritch_dm/logging.py:
- get_logger(name: str = "eldritch_dm")
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Four repositories (channel_sessions, persistent_views, riposte_timers, sanitizer_audit)</name>
  <files>
    src/eldritch_dm/persistence/channel_sessions_repo.py,
    src/eldritch_dm/persistence/persistent_views_repo.py,
    src/eldritch_dm/persistence/riposte_timers_repo.py,
    src/eldritch_dm/persistence/sanitizer_audit_repo.py,
    src/eldritch_dm/persistence/__init__.py,
    tests/persistence/test_channel_sessions_repo.py,
    tests/persistence/test_persistent_views_repo.py,
    tests/persistence/test_riposte_timers_repo.py,
    tests/persistence/test_sanitizer_audit_repo.py
  </files>
  <behavior>
    - All four repositories take `(db_path: str, writer_queue: WriterQueue)` in `__init__`; reads open lock-free connections via `open_connection(db_path)`; writes go through `writer_queue.submit(...)` so every write is serialized + uses BEGIN IMMEDIATE
    - All methods return pydantic v2 frozen models (never tuples, dicts, or raw rows) — JSON columns deserialized via `json.loads`+`TypeAdapter` so callers see Python dicts/lists (D-20)
    - **ChannelSessionRepo**:
        - `async def upsert(self, *, channel_id, campaign_name, claudmaster_session_id=None, dm20_party_token=None, state=ChannelState.LOBBY) -> ChannelSession` — INSERT … ON CONFLICT(channel_id) DO UPDATE; bumps updated_at to CURRENT_TIMESTAMP
        - `async def get(self, channel_id) -> ChannelSession | None`
        - `async def set_state(self, channel_id, state: ChannelState) -> ChannelSession` — UPDATE state + updated_at; raises KeyError if row absent
        - `async def list_active(self) -> list[ChannelSession]` — WHERE state != 'PAUSED'
        - `async def delete(self, channel_id) -> None`
    - **PersistentViewRepo**:
        - `async def insert(self, view: PersistentView) -> PersistentView` — INSERT with `payload_json = json.dumps(view.payload)`
        - `async def get(self, custom_id) -> PersistentView | None`
        - `async def list_by_channel(self, channel_id) -> list[PersistentView]`
        - `async def delete_for_message(self, message_id) -> int` — returns rows deleted
        - FK cascade tested: delete channel_sessions row → views removed
    - **RiposteTimerRepo**:
        - `async def insert(self, timer: RiposteTimer) -> RiposteTimer` — INSERT (autoincrement id assigned); returns model with id populated
        - `async def mark_consumed(self, id_: int) -> None`
        - `async def mark_expired(self, id_: int) -> None`
        - `async def list_pending(self) -> list[RiposteTimer]` — WHERE status='pending' ORDER BY deadline_ts ASC
        - `async def get(self, id_: int) -> RiposteTimer | None`
    - **SanitizerAuditRepo** (append-only):
        - `async def insert(self, row: SanitizerAuditRow) -> SanitizerAuditRow` — INSERT with `stripped_tokens` JSON-encoded; returns row with id populated
        - No reads in v1 (D-19) — but provide `async def count(self) -> int` for tests
    - Each repository round-trips its model cleanly: `await repo.upsert(...)` then `await repo.get(...)` returns an equivalent model
    - CHECK constraint violations raise `aiosqlite.IntegrityError` and propagate (we do not swallow them)
  </behavior>
  <action>
    For every repository, follow this skeleton (illustrated for ChannelSessionRepo; the others mirror it):

    - Constructor stores `_db_path` and `_writer_queue`; also stores a `_logger` bound with `repo='channel_sessions'`.
    - Writes: define a nested `async def _do(conn): await conn.execute(SQL, params); ...` and submit it via `await self._writer_queue.submit(_do)`. The fn returns whatever the caller needs (e.g. the new model). The WriterQueue wraps it in BEGIN IMMEDIATE / COMMIT automatically (per plan 01 Task 2).
    - For upsert returning the row: after the write fn commits, re-`SELECT` the row inside the same fn (still inside the txn) and return it as a dict / pydantic model. This avoids a second connection.
    - Reads: `async with open_connection(self._db_path) as c: async with c.execute(SQL, params) as cur: row = await cur.fetchone()` ; if row is None return None, else build the pydantic model. Use `conn.row_factory = aiosqlite.Row` so columns are accessible by name.
    - JSON columns: write side `json.dumps(payload)`; read side `json.loads(row["payload_json"])` then `model_validate({**row, "payload": parsed})`.
    - Timestamp columns: DB stores ISO via SQLite's TIMESTAMP DEFAULT CURRENT_TIMESTAMP; aiosqlite returns them as `datetime.datetime` if you set `detect_types=sqlite3.PARSE_DECLTYPES`. Apply that in `open_connection` (update plan 01 helper if needed via the existing module — but DO NOT modify connection.py beyond the minimum needed; if connection.py already does not set PARSE_DECLTYPES, then parse the string in the repo via `datetime.fromisoformat`). Prefer the latter to keep plan 01 unchanged.
    - No raw SQL string interpolation — every parameter is a `?` placeholder.

    Update `src/eldritch_dm/persistence/__init__.py` to also export the four repos.

    Tests — for each repo (fresh tmp_path DB per test via fixture that calls `bootstrap()` + spawns a WriterQueue):
    - `test_<table>_roundtrip`: insert/upsert, get, assert equal
    - `test_<table>_returns_pydantic_model`: assert `isinstance(result, ChannelSession)` etc.
    - `test_<table>_writes_go_through_queue`: monkeypatch `writer_queue.submit` to record calls; assert mutating methods invoke it; assert read methods do NOT
    - For ChannelSession: `test_list_active_excludes_paused`, `test_set_state_updates_timestamp`, `test_check_constraint_rejects_bogus_state`
    - For PersistentView: `test_payload_json_roundtrip` (non-trivial nested dict), `test_fk_cascade_on_channel_delete`, `test_list_by_channel_ordering` (deterministic by created_at ASC)
    - For RiposteTimer: `test_list_pending_ordered_by_deadline`, `test_mark_consumed_idempotent_or_noop_when_already_consumed`, `test_id_autopopulated_on_insert`
    - For SanitizerAudit: `test_stripped_tokens_jsonified`, `test_truncated_boolean_roundtrip`, `test_count_increases_on_insert`
    - Add a single `tests/persistence/conftest.py` providing fixtures `bootstrapped_db(tmp_path)` returning `(db_path, writer_queue)` with WriterQueue started; teardown stops the queue.

    Add a guard test `tests/persistence/test_writes_use_queue.py` that does a static grep: read each repo file; assert every method whose name doesn't start with `get_`/`list_`/`count` mentions `writer_queue.submit` in its body.
  </action>
  <verify>
    <automated>pytest tests/persistence/test_channel_sessions_repo.py tests/persistence/test_persistent_views_repo.py tests/persistence/test_riposte_timers_repo.py tests/persistence/test_sanitizer_audit_repo.py tests/persistence/test_writes_use_queue.py -x -v</automated>
  </verify>
  <done>
    - All four repo test files green
    - `grep -rn "execute.*BEGIN" src/eldritch_dm/persistence/*_repo.py` returns no results (BEGIN IMMEDIATE is owned by WriterQueue, not repos)
    - import-linter still passes (repos depend on persistence + config + logging only)
    - Atomic commit: `feat(01-mcp-client-local-state): four repositories on top of writer queue`
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: MCP errors + httpx-based client + tenacity retry</name>
  <files>
    src/eldritch_dm/mcp/__init__.py,
    src/eldritch_dm/mcp/errors.py,
    src/eldritch_dm/mcp/client.py,
    tests/mcp/__init__.py,
    tests/mcp/test_client.py
  </files>
  <behavior>
    - `MCPClient(base_url: str, *, circuit_breaker: CircuitBreaker | None = None, timeout_connect=2.0, timeout_read=30.0, timeout_write=5.0, user_agent="EldritchDM/0.1 (+https://github.com/shoemoney/eldritchdm)")` — one shared `httpx.AsyncClient` per instance; opens lazily on first call or via `await client.aclose()` for shutdown (D-03, D-04)
    - `async def call(self, tool_name: str, **arguments) -> dict[str, Any]` — POSTs `{"tool_name": tool_name, "arguments": arguments}` to `f"{base_url}/v1/mcp/execute"` (D-04). Returns the parsed JSON response payload.
    - **If `circuit_breaker.state == OPEN`**, raises `MCPCircuitOpen(tool_name=...)` immediately without any HTTP call (D-08)
    - Retry via `tenacity` (D-05): 3 attempts; exponential backoff 0.5s → 1s → 2s; retry only on `httpx.TimeoutException`, `httpx.NetworkError`, and HTTP `5xx` status codes (raise_for_status converted to a retryable signal); **do NOT retry on 4xx** — these surface as `MCPToolError(tool_name, arguments, response_payload)` after attempt 1
    - On all retried failures exhausted, raises `MCPTimeoutError` (for timeout exhaustion) or `MCPNetworkError` (for network exhaustion) — preserve the last underlying exception via `__cause__`
    - Every call binds structlog context (`tool_name`, `attempt_n`, `duration_ms`) and logs at INFO on success, WARNING on retry, ERROR on final failure (with secrets-scrubbed payload — `arguments` may not contain sensitive data in v1, but apply the redaction processor regardless) (D-09, MCP-06)
    - User-Agent header set per D-03; Content-Type: application/json
  </behavior>
  <action>
    Create `src/eldritch_dm/mcp/__init__.py` exporting client + errors + tools (forward-import). Empty for now; finalize in Task 4.

    Create `src/eldritch_dm/mcp/errors.py`:
    - `class MCPError(Exception): pass`
    - `class MCPTimeoutError(MCPError): pass`
    - `class MCPNetworkError(MCPError): pass`
    - `class MCPToolError(MCPError):`
        - `__init__(self, tool_name: str, arguments: dict, response_payload: dict | None, message: str | None = None)`
        - stores all attrs; `__str__` includes tool_name and status info
    - `class MCPCircuitOpen(MCPError):`
        - `__init__(self, tool_name: str)`
        - message: `"MCP circuit breaker is OPEN — refused to call {tool_name}"`

    Create `src/eldritch_dm/mcp/client.py`:
    - Imports: `httpx`, `tenacity` (`retry`, `stop_after_attempt`, `wait_exponential`, `retry_if_exception_type`, `retry_if_exception`, `before_sleep_log`), structlog, `Settings`, `MCPError` + variants, `CircuitBreaker` (forward-imported lazily to avoid import cycle).
    - `class MCPClient`:
        - `__init__(base_url, *, circuit_breaker=None, timeout_connect=2.0, timeout_read=30.0, timeout_write=5.0, user_agent=..., http2=True)`
        - Internal: `self._client: httpx.AsyncClient | None = None`, `self._lock = asyncio.Lock()` (for lazy init).
        - `async def _ensure_client(self) -> httpx.AsyncClient` — under self._lock, create the AsyncClient with `httpx.Timeout(connect=..., read=..., write=..., pool=2.0)`, `headers={"User-Agent": user_agent, "Content-Type": "application/json"}`, `http2=http2`.
        - `async def call(self, tool_name: str, **arguments) -> dict[str, Any]`:
            - check circuit breaker → MCPCircuitOpen if OPEN
            - call `self._invoke(tool_name, arguments)` (the retry-wrapped private method)
        - `async def _invoke(self, tool_name: str, arguments: dict) -> dict`:
            - decorated by tenacity; inside: `client = await self._ensure_client(); start = time.monotonic(); r = await client.post(url, json={"tool_name": tool_name, "arguments": arguments}); duration = time.monotonic() - start`
            - if `r.status_code >= 500`: raise a transient internal `_TransientHTTPError(r)` (custom internal class) — tenacity will retry; on exhaustion, convert in outer wrapper to `MCPNetworkError(f"5xx from MCP: {r.status_code}")`
            - if `400 <= r.status_code < 500`: parse response JSON if possible, raise `MCPToolError(tool_name, arguments, response_payload, message=f"HTTP {r.status_code}")` — NO retry (raise out of tenacity directly by using `retry=retry_if_exception_type(...)` that excludes MCPToolError)
            - on success: log INFO with bound context, return `r.json()`
            - on circuit breaker integration: on success, call `circuit_breaker.record_success()` if provided; on terminal failure, call `circuit_breaker.record_failure()`
        - Tenacity decorator: `@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=2.0), retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, _TransientHTTPError)), reraise=False)` — but we need to convert exhaustion → MCPTimeoutError/MCPNetworkError, so wrap the tenacity-decorated coroutine in an outer try/except that catches `tenacity.RetryError` and converts based on `RetryError.last_attempt.exception()` type.
        - `async def aclose(self) -> None` — close httpx client if open.

    Tests `tests/mcp/test_client.py` (use `respx.mock` fixture):
    - `test_happy_path`: respx routes a 200 with body `{"result": {"ok": true}}`; assert `await client.call("dm20__create_campaign", name="test")` returns the parsed body; assert one HTTP call recorded.
    - `test_retry_on_timeout`: respx side_effect first two = `httpx.TimeoutException`, third = 200; assert call returns; assert 3 calls recorded; assert duration ≥ 0.5 + 1.0 = 1.5s (real waits — use `tenacity` with `wait_none()` swapped via test override OR use `freezegun`/monkeypatch tenacity wait. Simpler: monkeypatch `wait_exponential` via tenacity's `Retrying.wait` attribute to `wait_none()` for tests).
    - `test_retry_on_5xx`: respx returns 503, 503, 200; assert 3 calls; assert final result returned.
    - `test_no_retry_on_4xx`: respx returns 400 with body `{"error": "bad tool args"}`; assert `MCPToolError` raised with `tool_name`, `arguments`, and `response_payload`; assert exactly 1 HTTP call recorded.
    - `test_timeout_exhaustion_raises_mcp_timeout`: all attempts time out; assert `MCPTimeoutError` raised with `__cause__` being `httpx.TimeoutException`.
    - `test_network_exhaustion_raises_mcp_network`: all attempts raise `httpx.NetworkError`; assert `MCPNetworkError` raised.
    - `test_circuit_open_blocks_call`: pass a CircuitBreaker stub whose `state` returns OPEN; call `await client.call("x")`; assert `MCPCircuitOpen` raised and respx recorded zero calls.
    - `test_circuit_success_recorded`: pass CircuitBreaker stub; happy-path call; assert `record_success()` was invoked.
    - `test_circuit_failure_recorded`: terminal failure (timeout exhaustion); assert `record_failure()` invoked.
    - `test_user_agent_header_set`: respx asserts `EldritchDM/0.1` is in the request `User-Agent`.
    - `test_post_body_shape`: respx asserts request JSON equals `{"tool_name": "x", "arguments": {"k": "v"}}`.
    - `test_aclose_closes_httpx_client`.
  </action>
  <verify>
    <automated>pytest tests/mcp/test_client.py -x -v</automated>
  </verify>
  <done>
    - All client tests pass
    - `grep -n "retry" src/eldritch_dm/mcp/client.py` shows tenacity usage with the four required attempts/backoffs
    - import-linter still passes (mcp imports nothing from persistence or safety)
    - Atomic commit: `feat(01-mcp-client-local-state): mcp client with retry, structured errors, circuit-breaker hook`
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Health check loop + circuit breaker state machine</name>
  <files>
    src/eldritch_dm/mcp/health.py,
    tests/mcp/test_health.py
  </files>
  <behavior>
    - `class CircuitState(StrEnum): CLOSED, OPEN` (per "specifics": don't over-engineer HALF_OPEN — 3-strike counter is enough)
    - `class CircuitBreaker(threshold: int = 3)`:
        - `record_success()` → resets failure counter to 0; transitions state to CLOSED
        - `record_failure()` → increments failure counter; if counter ≥ threshold, state becomes OPEN
        - `state: CircuitState` property
        - thread-safe enough for single-loop async (no lock needed — Python asyncio is single-threaded)
    - `class HealthCheck(endpoint: str, *, interval: float = 60.0, breaker: CircuitBreaker, http_client: httpx.AsyncClient | None = None)`:
        - `async def start(self) -> None` spawns `_run()` task
        - `_run()` loops: sleep interval; GET `{endpoint}/models`; on 200, `breaker.record_success()`; on any exception or non-2xx, `breaker.record_failure()`; logs at INFO/WARNING with `circuit_state` after each ping
        - `async def stop(self) -> None` cancels task cleanly
    - `def get_circuit_state(breaker: CircuitBreaker) -> CircuitState` module-level helper (used by Discord layer in later phases to render "🔌 DM is offline")
    - 3 consecutive failures trip OPEN; next single success returns to CLOSED (D-08)
  </behavior>
  <action>
    Create `src/eldritch_dm/mcp/health.py`:
    - `from enum import StrEnum`; `CircuitState(StrEnum): CLOSED="CLOSED"; OPEN="OPEN"`
    - `class CircuitBreaker:`
        - `__init__(self, threshold: int = 3): self._failures = 0; self._state = CircuitState.CLOSED; self._threshold = threshold; self._logger = get_logger(__name__).bind(component="circuit_breaker")`
        - `@property def state(self) -> CircuitState: return self._state`
        - `def record_success(self) -> None: prev = self._state; self._failures = 0; self._state = CircuitState.CLOSED; if prev != self._state: self._logger.info("circuit_closed")`
        - `def record_failure(self) -> None: self._failures += 1; if self._failures >= self._threshold and self._state == CircuitState.CLOSED: self._state = CircuitState.OPEN; self._logger.warning("circuit_opened", failures=self._failures)`
        - `def reset(self) -> None: self._failures = 0; self._state = CircuitState.CLOSED` (for testing)
    - `class HealthCheck:`
        - constructor stores params; owns/borrows an httpx.AsyncClient
        - `async def _run(self) -> None`: `while True: try: await asyncio.sleep(self._interval); r = await self._client.get(f"{self._endpoint}/models", timeout=httpx.Timeout(connect=2.0, read=5.0)); r.raise_for_status(); self._breaker.record_success(); self._logger.info("health_ping_ok") except asyncio.CancelledError: raise except Exception as e: self._breaker.record_failure(); self._logger.warning("health_ping_failed", error=str(e), circuit_state=self._breaker.state)`
        - `async def start(self) -> None`: `self._task = asyncio.create_task(self._run())`
        - `async def stop(self) -> None`: cancel + await with suppress(CancelledError)
    - `def get_circuit_state(breaker: CircuitBreaker) -> CircuitState: return breaker.state`

    Tests `tests/mcp/test_health.py`:
    - `test_circuit_starts_closed`: new breaker; state == CLOSED.
    - `test_three_failures_trip_open`: call record_failure() three times; state == OPEN; record_failure() again → still OPEN, no exception.
    - `test_success_after_open_returns_closed`: trip OPEN; record_success(); state == CLOSED; failures counter reset.
    - `test_isolated_failures_dont_trip`: failure, success, failure, success, failure → state CLOSED (counter resets on each success).
    - `test_threshold_configurable`: breaker(threshold=5); 4 failures CLOSED, 5th OPEN.
    - `test_health_check_records_success(respx_mock)`: GET `/v1/models` returns 200 `{"data":[{"id":"ShoeGPT"}]}`; start HealthCheck with interval=0.05; sleep 0.15s; stop; assert breaker.state CLOSED and at least 1 success ping happened.
    - `test_health_check_trips_on_consecutive_failures(respx_mock)`: GET returns 500 always; interval=0.02; sleep 0.15s; stop; assert breaker.state == OPEN (≥3 failures recorded).
    - `test_health_check_recovers(respx_mock)`: respx side_effect: 500, 500, 500, 200; interval=0.02; assert eventually CLOSED.
    - `test_health_check_stop_clean`: start, stop, no warnings about pending tasks (use `caplog` / structlog test helpers).
    - `test_get_circuit_state_helper`: trip OPEN; `get_circuit_state(breaker) == CircuitState.OPEN`.
  </action>
  <verify>
    <automated>pytest tests/mcp/test_health.py -x -v</automated>
  </verify>
  <done>
    - All health/circuit-breaker tests pass
    - State machine transitions per D-08
    - `get_circuit_state` exposed so Discord layer in Phase 2 can render "🔌 DM is offline"
    - Atomic commit: `feat(01-mcp-client-local-state): health check + circuit breaker state machine`
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Typed wrappers (first wave) + optional generator</name>
  <files>
    src/eldritch_dm/mcp/tools.py,
    src/eldritch_dm/mcp/__init__.py,
    tools/__init__.py,
    tools/gen_mcp_wrappers.py,
    tests/mcp/test_tools.py
  </files>
  <behavior>
    - 28 hand-authored typed wrapper functions in `tools.py` per D-07 first-wave list (see `<exports>` in must_haves above)
    - Each wrapper signature is `async def <name>(client: MCPClient, *, kw1, kw2, ...) -> dict[str, Any]` — accepts the MCPClient explicitly (dependency injection per D-32, no globals), builds the arguments dict, calls `await client.call("dm20__<name>", **arguments)`. The dm20 tool prefix is documented at the top of tools.py.
    - For the first wave, **return types are `dict[str, Any]`** (NOT pydantic models). Document at the top of `tools.py` why: "The full pydantic shape per tool will be added in later phases as we actually consume the data. For Phase 1, the typed-wrapper layer's value is the SIGNATURE (Python-named kwargs, IDE autocomplete, type-checked arg names) — not the return validation. dict[str, Any] is intentional, not lazy."
    - Wrapper functions call MCPClient.call exactly once; do not retry locally (retry lives in the client)
    - Tools that don't take arguments still have a no-arg signature (e.g. `async def end_combat(client) -> dict`)
    - `tools.py` includes a module-level mapping `TOOL_TO_FUNCTION: dict[str, Callable]` for introspection (used by gen_mcp_wrappers.py drift-detection)
    - Optional generator `tools/gen_mcp_wrappers.py` parses ddmcpskills.md and emits stub functions; run manually to spot drift; not part of CI. It's a TOOL, not a build step (D-07 + discretion)
    - For tools whose dm20 name differs from the Python wrapper name, map explicitly (e.g. `roll_dice` and `dice_roll` may both map to `dice__roll_dice` — verify against ddmcpskills.md; if unsure document and use `dice_roll` → `"dice__dice_roll"` per the canonical name)
  </behavior>
  <action>
    Create `src/eldritch_dm/mcp/tools.py`:
    - Module docstring (multi-line): explain the wrapper layer, the dict[str, Any] return-type decision, and the dm20__ prefix convention.
    - For each wrapper in the first-wave list, write the function. Signatures must use Python-friendly param names (snake_case, named kwargs). Examples:
        - `async def create_campaign(client: MCPClient, *, name: str, description: str = "") -> dict[str, Any]: return await client.call("dm20__create_campaign", name=name, description=description)`
        - `async def load_campaign(client: MCPClient, *, name: str) -> dict[str, Any]: ...`
        - `async def list_campaigns(client: MCPClient) -> dict[str, Any]: return await client.call("dm20__list_campaigns")`
        - `async def get_campaign_info(client: MCPClient, *, name: str | None = None) -> dict[str, Any]: ...`
        - `async def create_character(client: MCPClient, *, campaign_name: str, character: dict[str, Any]) -> dict[str, Any]: ...`
        - `async def update_character(client: MCPClient, *, campaign_name: str, character_id: str, updates: dict[str, Any]) -> dict[str, Any]: ...`
        - `async def import_from_dndbeyond(client: MCPClient, *, url_or_id: str, player_name: str | None = None) -> dict[str, Any]: ...`
        - `async def start_claudmaster_session(client: MCPClient, *, campaign_name: str) -> dict[str, Any]: ...`
        - `async def end_claudmaster_session(client: MCPClient, *, session_id: str) -> dict[str, Any]: ...`
        - `async def start_party_mode(client: MCPClient, *, campaign_name: str, port: int | None = None) -> dict[str, Any]: ...`
        - `async def stop_party_mode(client: MCPClient, *, campaign_name: str) -> dict[str, Any]: ...`
        - `async def party_pop_action(client: MCPClient, *, campaign_name: str) -> dict[str, Any]: ...`
        - `async def party_thinking(client: MCPClient, *, campaign_name: str, message: str) -> dict[str, Any]: ...`
        - `async def party_get_prefetch(client: MCPClient, *, turn_id: str, outcome: str | None = None, roll: int | None = None, damage: int | None = None, target_hp: int | None = None) -> dict[str, Any]: ...`
        - `async def party_resolve_action(client: MCPClient, *, turn_id: str, narration: str) -> dict[str, Any]: ...`
        - `async def start_combat(client: MCPClient, *, campaign_name: str, encounter: dict[str, Any] | None = None) -> dict[str, Any]: ...`
        - `async def end_combat(client: MCPClient, *, campaign_name: str) -> dict[str, Any]: ...`
        - `async def next_turn(client: MCPClient, *, campaign_name: str) -> dict[str, Any]: ...`
        - `async def combat_action(client: MCPClient, *, campaign_name: str, action: str, **extra) -> dict[str, Any]:` — passes through `weapon`, `target`, `reaction`, etc. via **extra; document the known options.
        - `async def apply_effect(client: MCPClient, *, campaign_name: str, target: str, effect: str, **extra) -> dict[str, Any]: ...`
        - `async def remove_effect(client: MCPClient, *, campaign_name: str, target: str, effect: str) -> dict[str, Any]: ...`
        - `async def get_game_state(client: MCPClient, *, campaign_name: str) -> dict[str, Any]: ...`
        - `async def get_claudmaster_session_state(client: MCPClient, *, session_id: str) -> dict[str, Any]: ...`
        - `async def validate_character_rules(client: MCPClient, *, character_id: str) -> dict[str, Any]: ...`
        - `async def load_rulebook(client: MCPClient, *, rulebook: str) -> dict[str, Any]: ...`
        - `async def search_rules(client: MCPClient, *, query: str, top_k: int = 5) -> dict[str, Any]: ...`
        - `async def roll_dice(client: MCPClient, *, notation: str) -> dict[str, Any]: return await client.call("dice__roll_dice", notation=notation)` (verify exact tool name against ddmcpskills.md; if it's `dnd__roll_dice` or `dm20__roll_dice` adjust prefix accordingly — document the chosen prefix in a comment).
        - `async def dice_roll(client: MCPClient, *, notation: str) -> dict[str, Any]:` — alias to roll_dice or distinct dm20 tool per the schema; if ddmcpskills.md only has one, mark the other as a Python-level alias and `# noqa: F811`-style comment.
        - `async def verify_with_api(client: MCPClient, *, query: str) -> dict[str, Any]: ...`
    - At bottom of file: `TOOL_TO_FUNCTION: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {"dm20__create_campaign": create_campaign, ...}` (build the map; this gives the generator + tests a single source of truth).

    Update `src/eldritch_dm/mcp/__init__.py`:
    - `from .errors import MCPError, MCPTimeoutError, MCPNetworkError, MCPToolError, MCPCircuitOpen`
    - `from .client import MCPClient`
    - `from .health import HealthCheck, CircuitBreaker, CircuitState, get_circuit_state`
    - `from . import tools` (expose the namespace)
    - `__all__ = [...]`

    Create `tools/__init__.py` (empty) and `tools/gen_mcp_wrappers.py`:
    - Parses `ddmcpskills.md`: identifies tool schema sections (heuristic: lines beginning with `### ` followed by a tool name; argument table immediately after). Extracts (tool_name, [(arg_name, arg_type, default, required)]).
    - For each tool found in ddmcpskills.md, prints a wrapper stub (to stdout or to `tools/_generated.py` if `--write` flag).
    - Cross-checks against `mcp.tools.TOOL_TO_FUNCTION` — reports a "missing wrapper" warning for tools in ddmcpskills.md not present in our map, and an "orphaned wrapper" for the inverse.
    - `if __name__ == "__main__": main()` — simple argparse with `--write` and `--check` modes. `--check` exits non-zero if drift detected.
    - Document at top: "This generator is a developer tool, not a CI step. Its output (`tools/_generated.py`) is committed when run, NOT generated at install. Human curates the typed signatures."

    Tests `tests/mcp/test_tools.py`:
    - For each of the 28 wrappers, a single happy-path test with respx-mocked 200 response. Parametrize:
        ```python
        @pytest.mark.parametrize("wrapper,tool_name,kwargs,expected_args", [
            (tools.create_campaign, "dm20__create_campaign", {"name": "Test"}, {"name": "Test", "description": ""}),
            (tools.load_campaign, "dm20__load_campaign", {"name": "Test"}, {"name": "Test"}),
            ...
        ])
        async def test_wrapper_routes_to_correct_tool(wrapper, tool_name, kwargs, expected_args, respx_mock):
            route = respx_mock.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
            client = MCPClient(BASE_URL)
            await wrapper(client, **kwargs)
            assert route.calls.last.request.json() == {"tool_name": tool_name, "arguments": expected_args}
        ```
    - `test_tool_to_function_complete`: assert `len(TOOL_TO_FUNCTION) >= 28`; assert every wrapper appears in the map.
    - `test_generator_check_runs(tmp_path, monkeypatch)`: run `python tools/gen_mcp_wrappers.py --check` as subprocess against the in-repo ddmcpskills.md; assert exit code is 0 OR documented drift is reported (allow non-zero with a warning — drift between our first-wave 28 and dm20's full 116 is expected and not a test failure; the generator should report "missing: 88 tools" without failing).
  </action>
  <verify>
    <automated>pytest tests/mcp/test_tools.py -x -v && python tools/gen_mcp_wrappers.py --check 2>&1 | head -20</automated>
  </verify>
  <done>
    - All 28 wrappers callable and respx-tested
    - `TOOL_TO_FUNCTION` is the single source of truth for "which tools we expose"
    - Generator script runs and reports drift without crashing
    - import-linter passes
    - Atomic commit: `feat(01-mcp-client-local-state): typed wrappers for first-wave dm20 tools + drift-check generator`
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| process → MCP endpoint | All outbound MCP traffic goes to `MCP_EXECUTE_URL` (localhost in v1; treated as trusted-but-fault-prone — see T-02-04 if v2 makes it remote) |
| MCP response → process | MCP responses contain JSON parsed into `dict[str, Any]`; downstream code is responsible for treating values as untrusted (no Python eval, no SQL interpolation, no path joins with response strings) |
| repo writes → SQLite file | Writes serialized through WriterQueue with BEGIN IMMEDIATE; pragma `foreign_keys=ON` enforces referential integrity at DB layer |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-01 | Spoofing | MCP endpoint identity | accept | v1 localhost only (PROJECT.md constraint). v2 may add mTLS / token auth if remote MCP is ever supported (deferred). |
| T-02-02 | Tampering | response payload from MCP | mitigate | All parsed JSON treated as untrusted; we never `eval`, `subprocess`, or filesystem-write based on MCP response content. SQL repository writes use `?` placeholders only (test_writes_use_queue.py + manual review). |
| T-02-03 | Repudiation | MCP calls | mitigate | structlog binds tool_name + duration_ms + attempt_n + channel_id + caller campaign on every call (D-09, MCP-06). Log retention up to operator. |
| T-02-04 | Information disclosure | MCP request/response in logs | mitigate | structlog processor scrubs any field matching `*token*`, `*secret*`, `*api_key*`. Request `arguments` for first-wave tools do not include credentials (D&D content only); for `import_from_dndbeyond` the URL itself is logged but the URL is not a secret (it's a public DDB share URL — players paste them in Discord, no auth needed). |
| T-02-05 | Denial of service | retry storms on persistent MCP failure | mitigate | Circuit breaker trips OPEN after 3 consecutive ping failures (D-08); MCPClient raises MCPCircuitOpen immediately without re-attempting the network. Per-channel rate limiter (OPS-03) deferred to Phase 4. |
| T-02-06 | Elevation of privilege | repository CHECK constraints | mitigate | DB-level CHECK on `channel_sessions.state` and `riposte_timers.status` (D-18); attempting an invalid state raises IntegrityError. Verified in test_check_constraints_enforced. |
| T-02-07 | Tampering | concurrent writer contention | mitigate | Single-writer WriterQueue (D-16); per-channel asyncio.Lock applied around mutating MCP+DB call chains (D-10) — the lock registry is shared between MCP client and persistence (D-11) via the SessionLocks instance passed in by Phase 2's Discord layer. Stress test in plan 03 verifies. |
| T-02-SC | Tampering | install of `tenacity`, `respx`, `import-linter` (new deps versus plan 01) | mitigate | All three are well-established PyPI packages with millions of downloads each. `[OK]` per legitimacy heuristic. No `[ASSUMED]` or `[SUS]` packages introduced. |
</threat_model>

<verification>
End-of-plan checks:
1. `pytest tests/persistence/ tests/mcp/ -x` green
2. `python -m importlinter --config pyproject.toml` exit 0
3. `python -c "from eldritch_dm.mcp import MCPClient, MCPError, CircuitBreaker, get_circuit_state; from eldritch_dm.mcp import tools; print(len(tools.TOOL_TO_FUNCTION))"` prints ≥ 28
4. `grep -rn "client\.call(" src/eldritch_dm/mcp/tools.py | wc -l` ≥ 28 (every wrapper calls through the client)
5. `python -m ruff check src/ tests/` exit 0
</verification>

<success_criteria>
- Four repositories handle CRUD for the four tables, return frozen pydantic models, write through the WriterQueue
- MCPClient.call posts the right shape, retries on transient errors, surfaces tool errors as structured exceptions, respects the circuit breaker
- CircuitBreaker trips OPEN after 3 consecutive failures and recovers on the next success
- HealthCheck pings `/v1/models` on the configured interval and updates the breaker
- 28 typed wrappers in `tools.py` route to dm20 tools with named kwargs
- Optional generator script reports drift between ddmcpskills.md and our wrapper map
- Every component is unit-tested with respx-mocked HTTP and tmp_path SQLite (zero network in tests)
</success_criteria>

<output>
Create `.planning/phases/01-mcp-client-local-state/01-02-SUMMARY.md` when done, listing: created files, test counts, MCP tool names mapped, any drift between ddmcpskills.md schema and the kwargs we picked. Include a one-line "Phase 2 hook" — how the bot will instantiate `MCPClient`, `CircuitBreaker`, and `HealthCheck` together at startup.
</output>
