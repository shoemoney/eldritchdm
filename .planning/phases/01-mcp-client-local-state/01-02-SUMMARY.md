---
phase: 01-mcp-client-local-state
plan: 02
subsystem: persistence-repos, mcp
tags: [sqlite, aiosqlite, pydantic-v2, httpx, tenacity, circuit-breaker, mcp-client, repository-pattern]
dependency_graph:
  requires:
    - eldritch_dm.persistence.WriterQueue
    - eldritch_dm.persistence.open_connection
    - eldritch_dm.persistence.models
    - eldritch_dm.persistence.bootstrap
  provides:
    - eldritch_dm.persistence.ChannelSessionRepo
    - eldritch_dm.persistence.PersistentViewRepo
    - eldritch_dm.persistence.RiposteTimerRepo
    - eldritch_dm.persistence.SanitizerAuditRepo
    - eldritch_dm.mcp.MCPClient
    - eldritch_dm.mcp.CircuitBreaker
    - eldritch_dm.mcp.CircuitState
    - eldritch_dm.mcp.HealthCheck
    - eldritch_dm.mcp.get_circuit_state
    - eldritch_dm.mcp.errors (MCPError, MCPTimeoutError, MCPNetworkError, MCPToolError, MCPCircuitOpen)
    - eldritch_dm.mcp.tools (28 typed wrappers + TOOL_TO_FUNCTION registry)
  affects: []
tech_stack:
  added:
    - httpx[http2]>=0.27 (async HTTP client for MCP)
    - tenacity>=8.5 (retry/backoff for MCPClient)
    - respx==0.23.1 (httpx mock for tests)
  patterns:
    - Repository pattern: writes via writer_queue.submit(), reads via open_connection()
    - BEGIN IMMEDIATE for all writes (no plain BEGIN)
    - Circuit breaker CLOSED/OPEN (threshold=3 consecutive failures)
    - MCPClient: lazy httpx.AsyncClient, tenacity 3-attempt exponential backoff
    - Retry on timeout/network/5xx; no retry on 4xx (raises MCPToolError immediately)
    - TOOL_TO_FUNCTION registry as single source of truth for wrapper coverage
key_files:
  created:
    - src/eldritch_dm/persistence/channel_sessions_repo.py
    - src/eldritch_dm/persistence/persistent_views_repo.py
    - src/eldritch_dm/persistence/riposte_timers_repo.py
    - src/eldritch_dm/persistence/sanitizer_audit_repo.py
    - src/eldritch_dm/mcp/errors.py
    - src/eldritch_dm/mcp/client.py
    - src/eldritch_dm/mcp/health.py
    - src/eldritch_dm/mcp/tools.py
    - tools/gen_mcp_wrappers.py
    - tests/persistence/conftest.py
    - tests/persistence/test_writes_use_queue.py
    - tests/mcp/test_errors.py
    - tests/mcp/test_client.py
    - tests/mcp/test_health.py
    - tests/mcp/test_tools.py
  modified:
    - src/eldritch_dm/persistence/__init__.py
    - src/eldritch_dm/mcp/__init__.py
    - pyproject.toml (import-linter relaxation: safety→persistence.models allowed)
decisions:
  - "Repository writes all go through WriterQueue.submit() — zero direct aiosqlite.connect() calls in write paths"
  - "CircuitBreaker is CLOSED/OPEN only (no HALF_OPEN) — simpler for Phase 1; HALF_OPEN can be added in Phase 3+"
  - "MCPClient._execute_url = base_url/v1/mcp/execute — hardcoded path matching dm20 server convention"
  - "tenacity before_sleep_log removed — structlog logger incompatible with tenacity's stdlib-log-compatible hook"
  - "httpx.Timeout(5.0, connect=2.0) — must provide default; Timeout(connect=2.0, read=5.0) raises ValueError"
  - "import-linter safety contract relaxed to allow safety→persistence.models (for SanitizerAuditRow construction)"
  - "28 first-wave wrappers chosen; not all 116 dm20 tools wrapped — TOOL_TO_FUNCTION is the drift-detection registry"
metrics:
  duration_minutes: 45
  completed_date: "2026-05-21"
  tasks_completed: 5
  tests_passing: 105
  files_created: 15
---

# Phase 1 Plan 02: Repositories and MCP Client Summary

Four SQLite repositories on the WriterQueue pattern plus the httpx+tenacity MCP client, circuit breaker, health check, and 28 typed tool wrappers.

## What Was Built

**persistence/channel_sessions_repo.py** — `ChannelSessionRepo`: upsert (INSERT ... ON CONFLICT DO UPDATE), get, set_state, list_active, delete. All writes through WriterQueue.submit(). Returns frozen pydantic ChannelSession.

**persistence/persistent_views_repo.py** — `PersistentViewRepo`: insert, get, list_by_channel, delete_for_message (returns row count). payload_json column serialized via json.dumps/loads.

**persistence/riposte_timers_repo.py** — `RiposteTimerRepo`: insert (AUTOINCREMENT id via lastrowid), mark_consumed, mark_expired, list_pending, get. deadline_ts/created_at stored as ISO strings.

**persistence/sanitizer_audit_repo.py** — `SanitizerAuditRepo`: append-only insert + count(). stripped_tokens serialized as JSON. truncated as INTEGER 0/1.

**mcp/errors.py** — Error hierarchy: MCPError (base) → MCPTimeoutError, MCPNetworkError, MCPToolError(tool_name, arguments, response_payload), MCPCircuitOpen(tool_name).

**mcp/health.py** — `CircuitState(StrEnum): CLOSED, OPEN`. `CircuitBreaker(threshold=3)`: record_success() resets; record_failure() trips OPEN at threshold. `HealthCheck`: pings {endpoint}/models, updates breaker on response.

**mcp/client.py** — `MCPClient(base_url, *, circuit_breaker, timeout_connect, timeout_read)`. POST to `/v1/mcp/execute`. Lazy httpx.AsyncClient. tenacity AsyncRetrying: 3 attempts, exponential 0.5→2s. Retries timeout/network/5xx; immediate MCPToolError on 4xx. Records success/failure on circuit breaker.

**mcp/tools.py** — 28 typed async wrappers (all return `dict[str, Any]`). Key mappings: search_rules→dnd__search_all_categories, roll_dice→dice__dice_roll, verify_with_api→dnd__verify_with_api. `TOOL_TO_FUNCTION` registry for drift detection.

**tools/gen_mcp_wrappers.py** — `--check` mode exits 1 on orphaned wrappers (we have it, ddmcpskills.md doesn't list it). Drift-detection only; does not generate code.

## Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| test_writes_use_queue.py | 2 | PASSED |
| test_errors.py (mcp) | 12 | PASSED |
| test_client.py (mcp) | 12 | PASSED |
| test_health.py (mcp) | 12 | PASSED |
| test_tools.py (mcp) | 28 | PASSED |
| **Plan 02 Total** | **66** | **PASSED** |

Full suite (plans 01+02): 105 passing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] tenacity before_sleep_log incompatible with structlog**
- **Found during:** MCPClient implementation
- **Issue:** `tenacity.before_sleep_log(logger, logging.WARNING)` raised `TypeError: '<' not supported between instances of 'method' and 'int'` — structlog's logger interface differs from stdlib's
- **Fix:** Removed `before_sleep` parameter from AsyncRetrying; retry events logged via manual warning in the _TransientHTTPError handler path
- **Files modified:** src/eldritch_dm/mcp/client.py

**2. [Rule 1 - Bug] httpx.Timeout requires default value**
- **Found during:** MCPClient implementation  
- **Issue:** `httpx.Timeout(connect=2.0, read=5.0)` raises `ValueError: httpx.Timeout must either include a default...`
- **Fix:** Changed to `httpx.Timeout(5.0, connect=2.0)` which sets default=5.0 then overrides connect=2.0
- **Files modified:** src/eldritch_dm/mcp/client.py, src/eldritch_dm/mcp/health.py

**3. [Rule 2 - Missing critical functionality] import-linter contract relaxation**
- **Found during:** Safety subpackage implementation
- **Issue:** Sanitizer needs to construct SanitizerAuditRow (from persistence.models) to pass to audit callbacks, but strict contract forbade all safety→persistence imports
- **Fix:** Relaxed safety contract to allow safety→persistence.models specifically; explicitly forbids persistence.connection, persistence.bootstrap, persistence.checkpoint, and all *_repo modules
- **Files modified:** pyproject.toml

## Known Stubs

None — all repository methods are fully wired to real SQLite. TOOL_TO_FUNCTION contains 28 real wrappers.

## Self-Check: PASSED

- channel_sessions_repo.py: FOUND
- persistent_views_repo.py: FOUND
- riposte_timers_repo.py: FOUND
- sanitizer_audit_repo.py: FOUND
- mcp/errors.py: FOUND
- mcp/client.py: FOUND
- mcp/health.py: FOUND
- mcp/tools.py: FOUND
- Tests: 105 passed, 0 failed
- import-linter: 4 contracts KEPT
- ruff: 0 errors
- Commits: 1b17ee1, cd8e3a9/d3b851a, 4f3a801
