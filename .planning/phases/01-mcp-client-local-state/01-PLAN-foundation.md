---
phase: 01-mcp-client-local-state
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - .gitignore
  - src/eldritch_dm/__init__.py
  - src/eldritch_dm/config.py
  - src/eldritch_dm/logging.py
  - database/schema.sql
  - src/eldritch_dm/persistence/__init__.py
  - src/eldritch_dm/persistence/connection.py
  - src/eldritch_dm/persistence/locks.py
  - src/eldritch_dm/persistence/bootstrap.py
  - src/eldritch_dm/persistence/models.py
  - src/eldritch_dm/persistence/checkpoint.py
  - tests/__init__.py
  - tests/conftest.py
  - tests/persistence/__init__.py
  - tests/persistence/test_connection.py
  - tests/persistence/test_bootstrap.py
  - tests/persistence/test_models.py
autonomous: true
requirements:
  - LOC-01
  - LOC-02
  - LOC-03
  - LOC-04
  - LOC-06
  - MCP-06
  - OPS-04
must_haves:
  truths:
    - "pyproject.toml exists with deps pinned exactly to install.sh's set; `uv pip install -e .[dev]` succeeds"
    - "`python -m eldritch_dm.persistence.bootstrap` creates `./eldritch.sqlite3` with the four tables and indexes from D-18"
    - "Every aiosqlite connection emits the four pragmas (foreign_keys=ON, journal_mode=WAL, busy_timeout=5000, synchronous=NORMAL) before any other statement"
    - "A WriterQueue task serializes all writes; submitting two concurrent writes both succeed in order with zero `database is locked`"
    - "import-linter contract enforces module boundary discipline (mcp / safety / persistence are hermetic w.r.t. each other; bot may import everything)"
    - "structlog emits JSON in production mode and ConsoleRenderer in dev mode based on LOG_FORMAT"
  artifacts:
    - path: "pyproject.toml"
      provides: "Build metadata, pinned deps, dev extras, ruff config, pytest config, import-linter config"
      contains: "discord.py"
    - path: "src/eldritch_dm/config.py"
      provides: "pydantic-settings Settings class loading every .env var"
      exports: ["Settings", "get_settings"]
    - path: "src/eldritch_dm/logging.py"
      provides: "structlog configuration switching on LOG_FORMAT"
      exports: ["configure_logging", "get_logger"]
    - path: "database/schema.sql"
      provides: "DDL for channel_sessions, persistent_views, riposte_timers, sanitizer_audit + indexes"
      contains: "CREATE TABLE IF NOT EXISTS channel_sessions"
    - path: "src/eldritch_dm/persistence/connection.py"
      provides: "open_connection, WriterQueue, pragmas helper"
      exports: ["open_connection", "WriterQueue", "apply_pragmas"]
    - path: "src/eldritch_dm/persistence/locks.py"
      provides: "SessionLocks asyncio.Lock registry keyed by channel_id"
      exports: ["SessionLocks"]
    - path: "src/eldritch_dm/persistence/bootstrap.py"
      provides: "Idempotent schema application via database/schema.sql"
      exports: ["bootstrap", "main"]
    - path: "src/eldritch_dm/persistence/models.py"
      provides: "pydantic v2 frozen models for the four tables"
      exports: ["ChannelSession", "PersistentView", "RiposteTimer", "SanitizerAuditRow", "ChannelState", "RiposteStatus"]
    - path: "src/eldritch_dm/persistence/checkpoint.py"
      provides: "Periodic PRAGMA wal_checkpoint(TRUNCATE) background task"
      exports: ["CheckpointTask"]
  key_links:
    - from: "src/eldritch_dm/persistence/bootstrap.py"
      to: "database/schema.sql"
      via: "open() + executescript()"
      pattern: "schema\\.sql"
    - from: "src/eldritch_dm/persistence/connection.py"
      to: "aiosqlite"
      via: "WriterQueue task pattern, BEGIN IMMEDIATE for writes"
      pattern: "BEGIN IMMEDIATE"
    - from: "src/eldritch_dm/config.py"
      to: ".env"
      via: "pydantic-settings + python-dotenv"
      pattern: "BaseSettings"
---

<objective>
Lay the project's foundation: build metadata, configuration, logging, the local SQLite persistence engine (connection management with pragmas, single-writer queue, schema bootstrap, frozen pydantic models, WAL checkpoint task), and the module-boundary firewall (import-linter). No repositories, no MCP client, no sanitizer in this plan — those land in plans 02 and 03.

Purpose: Every later module imports from `eldritch_dm.config`, `eldritch_dm.logging`, and `eldritch_dm.persistence.connection`. Get these right first; nothing builds on quicksand.

Output:
- A working `pyproject.toml` installable as editable with `[dev]` extras
- A bootstrappable SQLite DB at `./eldritch.sqlite3`
- A WriterQueue idiom that the repositories in plan 02 will use unchanged
- An import-linter contract that fails CI if anyone violates the hermetic boundary
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-mcp-client-local-state/01-CONTEXT.md
@.planning/REQUIREMENTS.md
@.planning/PROJECT.md
@.env.example
@install.sh
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Project scaffolding — pyproject.toml, config, logging, import-linter contract</name>
  <files>
    pyproject.toml,
    .gitignore,
    src/eldritch_dm/__init__.py,
    src/eldritch_dm/config.py,
    src/eldritch_dm/logging.py,
    tests/__init__.py,
    tests/conftest.py,
    tests/test_config.py,
    tests/test_logging.py
  </files>
  <behavior>
    - `from eldritch_dm.config import get_settings; get_settings()` loads from env + .env and returns a frozen Settings instance with all `.env.example` fields (per D-31..D-33)
    - Missing `DISCORD_TOKEN` raises a clear ValidationError mentioning the missing field
    - `OMLX_HEALTH_INTERVAL` defaults to 60; `OMLX_CIRCUIT_BREAKER_THRESHOLD` defaults to 3; `MAX_MODAL_INPUT_CHARS` defaults to 500; `ELDRITCH_DB_PATH` defaults to `./eldritch.sqlite3`
    - Shell env wins over `.env` file (D-33 — document in README and assert in test by setting both)
    - `configure_logging(format='json')` returns a structlog logger that emits JSON dict events; `configure_logging(format='console')` returns a ConsoleRenderer logger (per D-09)
    - `get_logger(__name__)` returns a bound logger; calling `.bind(channel_id='123').info('x')` includes channel_id in the event
    - Running `python -m importlinter --config pyproject.toml` succeeds against the skeleton (one forbidden import inserted in a test fixture is detected — see test_logging.py harness)
  </behavior>
  <action>
    Create `pyproject.toml` with PEP 621 metadata for the `eldritch_dm` package:
    - `name = "eldritch-dm"`, `version = "0.1.0"`, `requires-python = ">=3.11,<3.13"`
    - `dependencies = [...]` matching install.sh exactly: `discord.py>=2.7.1,<3.0`, `httpx[http2]>=0.27,<0.29`, `aiosqlite>=0.20,<0.22`, `pydantic>=2.8,<3.0`, `pydantic-settings>=2.4,<3.0`, `tenacity>=8.5,<10.0`, `structlog>=24.4,<26.0`, `PyMuPDF>=1.24,<2.0`, `pypdf>=4.3,<6.0`, `openai>=1.55,<2.0`, `python-dotenv>=1.0,<2.0`
    - `[project.optional-dependencies] dev = [...]` with `pytest>=8.0,<9.0`, `pytest-asyncio>=0.23,<1.0`, `pytest-cov>=5.0,<6.0`, `ruff>=0.6,<1.0`, `respx>=0.21,<1.0`, `import-linter>=2.0,<3.0`, `pyyaml>=6.0,<7.0` (used by sanitizer corpus in plan 03)
    - `[project.optional-dependencies] mac-ocr = ["ocrmac>=1.0,<2.0"]` and `linux-ocr = ["easyocr>=1.7,<2.0"]` (planned for later phases; declare now to keep extras stable)
    - `[build-system] requires = ["hatchling"]`, `build-backend = "hatchling.build"`, `[tool.hatch.build.targets.wheel] packages = ["src/eldritch_dm"]`
    - `[tool.ruff]` line-length=100, `target-version = "py311"`, `select = ["E","F","I","UP","B","ASYNC","TCH"]`
    - `[tool.pytest.ini_options]` asyncio_mode = "auto", markers = ["slow: gated by RUN_STRESS=1"], `testpaths = ["tests"]`
    - `[tool.importlinter]` root_package = "eldritch_dm", contracts as four `type = "forbidden"` blocks: (a) `mcp` may not import `persistence` or `safety`; (b) `safety` may not import `mcp` or `persistence`; (c) `persistence` may not import `mcp` or `safety`; (d) `config` and `logging` may not import any of the three subsystems. The `bot` submodule is unrestricted (will be created in phase 2; mention in a TODO comment).

    Create `.gitignore` additions (append, don't overwrite if present): `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/`, `*.sqlite3`, `*.sqlite3-journal`, `*.sqlite3-wal`, `*.sqlite3-shm`, `eldritch.log`, `dist/`, `build/`, `*.egg-info/`.

    Create `src/eldritch_dm/__init__.py` with just `__version__ = "0.1.0"`.

    Create `src/eldritch_dm/config.py`:
    - `from pydantic_settings import BaseSettings, SettingsConfigDict`
    - `Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True)`
    - Fields (typed with sensible defaults matching `.env.example`): `discord_token: str`, `discord_application_id: int | None = None`, `discord_guild_ids: str = ""` (CSV; provide a `guild_ids_list` property), `omlx_endpoint: AnyHttpUrl = "http://localhost:8765/v1"`, `omlx_model: str = "ShoeGPT"`, `mcp_execute_url: AnyHttpUrl = "http://localhost:8765/v1/mcp/execute"`, `mcp_tools_url: AnyHttpUrl = "http://localhost:8765/v1/mcp/tools"`, `omlx_health_interval: PositiveInt = 60`, `omlx_circuit_breaker_threshold: PositiveInt = 3`, `omlx_ingest_model: str | None = None`, `eldritch_db_path: str = "./eldritch.sqlite3"`, `eldritch_db_busy_timeout_ms: PositiveInt = 5000`, `eldritch_db_checkpoint_interval: NonNegativeInt = 600`, `log_level: Literal["DEBUG","INFO","WARNING","ERROR"] = "INFO"`, `log_format: Literal["json","console"] = "console"`, `log_file: str | None = None`, `riposte_ttl_seconds: PositiveInt = 8`, `embed_edit_rate_limit: PositiveFloat = 1.0`, `max_modal_input_chars: PositiveInt = 500`, `explore_batch_window_seconds: PositiveInt = 30`, `party_mode_port: PositiveInt = 8080`, `party_poll_interval_ms: PositiveInt = 250`, `run_stress: bool = False`, `sanitizer_verbose_audit: bool = False`.
    - `@lru_cache(maxsize=1) def get_settings() -> Settings: return Settings()` — single instance per process (D-32).
    - DO NOT import `eldritch_dm.persistence`, `eldritch_dm.mcp`, or `eldritch_dm.safety`. This file is import-clean.

    Create `src/eldritch_dm/logging.py`:
    - `configure_logging(level: str, fmt: Literal["json","console"], log_file: str | None = None) -> None` — calls `structlog.configure(...)` with `processors=[add_log_level, TimeStamper(fmt="iso"), structlog.contextvars.merge_contextvars, …]` and a final renderer of `JSONRenderer()` or `ConsoleRenderer()` based on `fmt`. Routes to stderr by default; if `log_file` set, also configures stdlib logging FileHandler that structlog forwards to.
    - `get_logger(name: str = "eldritch_dm")` returns `structlog.get_logger(name)`.
    - Document key naming: lowercase snake_case (D-09 + discretion).

    Create `tests/__init__.py` (empty) and `tests/conftest.py`:
    - `@pytest.fixture` `tmp_env(monkeypatch, tmp_path)` that sets minimal required env (`DISCORD_TOKEN=test-token`, `ELDRITCH_DB_PATH=<tmp_path>/eldritch.sqlite3`) and clears `get_settings` cache before yielding, then clears again on teardown.
    - `@pytest.fixture` `frozen_settings(tmp_env)` returns `get_settings()` and is the canonical way tests obtain a Settings.

    Tests:
    - `tests/test_config.py`: (a) defaults load when only `DISCORD_TOKEN` is set; (b) missing `DISCORD_TOKEN` raises ValidationError; (c) shell env overrides `.env` file content (write a temp .env, set env var, assert env wins); (d) `guild_ids_list` parses CSV; (e) `Settings` instance is frozen (set attribute raises).
    - `tests/test_logging.py`: (a) `configure_logging(level='INFO', fmt='json')` then `get_logger('x').info('event', k='v')` writes a JSON dict to captured stderr containing `"event": "event"` and `"k": "v"`; (b) `console` format writes human-readable output (no JSON); (c) bound context (`contextvars.bind_contextvars(channel_id='123')`) appears in subsequent log events; (d) `python -m importlinter --config pyproject.toml` returns exit 0 on the skeleton (run via `subprocess` in test; mark `@pytest.mark.skipif(not import_linter_available)`).

    Initialize git tracking for new files but do NOT commit yet.
  </action>
  <verify>
    <automated>uv pip install -e ".[dev]" && python -c "from eldritch_dm.config import get_settings; import os; os.environ.setdefault('DISCORD_TOKEN','t'); print(get_settings().eldritch_db_path)" && pytest tests/test_config.py tests/test_logging.py -x && python -m importlinter --config pyproject.toml</automated>
  </verify>
  <done>
    - `uv pip install -e .[dev]` succeeds and `eldritch_dm.config:get_settings()` returns a Settings with `eldritch_db_path` resolved
    - `pytest tests/test_config.py tests/test_logging.py -x` is green
    - `python -m importlinter --config pyproject.toml` exits 0
    - Atomic commit: `feat(01-mcp-client-local-state): scaffold pyproject, config, logging, import-linter contract`
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Schema + connection layer — pragmas, WriterQueue, SessionLocks, models</name>
  <files>
    database/schema.sql,
    src/eldritch_dm/persistence/__init__.py,
    src/eldritch_dm/persistence/connection.py,
    src/eldritch_dm/persistence/locks.py,
    src/eldritch_dm/persistence/models.py,
    tests/persistence/__init__.py,
    tests/persistence/test_connection.py,
    tests/persistence/test_models.py
  </files>
  <behavior>
    - `apply_pragmas(conn)` runs (in order) `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, `PRAGMA synchronous=NORMAL` (per D-15) and `journal_mode` returns "wal"
    - `open_connection(db_path)` is an `@asynccontextmanager` yielding an aiosqlite.Connection with pragmas applied; closes cleanly on exit
    - `WriterQueue.start()` spawns one background task owning a single long-lived writer connection; `submit(fn)` schedules a coroutine that takes the writer connection and returns its result; submissions execute in FIFO order; `stop(drain_timeout=5.0)` drains pending submissions then closes the writer connection (per D-14, D-16, D-22)
    - All writes via WriterQueue use `BEGIN IMMEDIATE` (D-17) — assert no plain `BEGIN` in connection.py via grep test
    - 50 concurrent `submit(write)` calls all complete with zero exceptions and rows appear in the order submitted
    - `SessionLocks().get('chan-1')` returns an `asyncio.Lock`; calling twice returns the same lock instance; different channel ids return different locks; locks are never garbage-collected during process lifetime (D-10, D-11)
    - The pydantic models for the four tables are frozen, `extra='forbid'`, and round-trip cleanly via `.model_dump(mode='json')` / `model_validate` (D-20)
  </behavior>
  <action>
    Create `database/schema.sql` verbatim per D-18 (the four CREATE TABLE statements with their CHECK constraints, foreign keys, timestamps, and the four indexes). Include `PRAGMA foreign_keys = ON;` and `PRAGMA journal_mode = WAL;` at the top.

    Create `src/eldritch_dm/persistence/__init__.py` exporting the public surface to be filled in across plans 01 + 02: `from .connection import open_connection, WriterQueue, apply_pragmas`, `from .locks import SessionLocks`, `from .models import ChannelSession, PersistentView, RiposteTimer, SanitizerAuditRow, ChannelState, RiposteStatus`. (Repositories added by plan 02 will extend this `__all__`.)

    Create `src/eldritch_dm/persistence/connection.py`:
    - `async def apply_pragmas(conn: aiosqlite.Connection, busy_timeout_ms: int = 5000) -> None` — issues the four pragmas in the order from D-15, awaits commit. Logs at DEBUG.
    - `@asynccontextmanager async def open_connection(db_path: str | os.PathLike, busy_timeout_ms: int = 5000) -> AsyncIterator[aiosqlite.Connection]` — opens, applies pragmas, yields, closes in finally.
    - `class WriterQueue`:
        - `__init__(self, db_path: str, busy_timeout_ms: int = 5000, drain_timeout: float = 5.0)`
        - Internal: `self._queue: asyncio.Queue[tuple[Coroutine[...], asyncio.Future[Any]]]`, `self._task: asyncio.Task | None`, `self._conn: aiosqlite.Connection | None`, `self._closed: bool`
        - `async def start(self) -> None` — opens one writer connection, applies pragmas, spawns `_run()`.
        - `async def _run(self) -> None` — loops `fn, fut = await self._queue.get()`; runs `async with self._conn.execute("BEGIN IMMEDIATE"): result = await fn(self._conn); await self._conn.commit()`; sets fut.set_result/exception; sentinel `None` exits the loop.
        - `async def submit(self, fn: Callable[[aiosqlite.Connection], Awaitable[T]]) -> T` — wraps fn in a future, awaits result. Raises `RuntimeError` if `_closed` is True.
        - `async def stop(self) -> None` — sets `_closed = True`, puts sentinel, awaits task with `drain_timeout`, then closes connection.
        - `def qsize(self) -> int` — exposes pending count (used by checkpoint task).
    - DO NOT call `await` between `BEGIN IMMEDIATE` and `COMMIT` for anything other than the user fn — keep transactions tight (D-17).

    Create `src/eldritch_dm/persistence/locks.py`:
    - `class SessionLocks: def __init__(self) -> None: self._locks: dict[str, asyncio.Lock] = {}` ; `def get(self, channel_id: str) -> asyncio.Lock:` — lazy create, never evict (D-11). Document that cardinality is bounded by Discord channel count.

    Create `src/eldritch_dm/persistence/models.py`:
    - `from enum import StrEnum`
    - `class ChannelState(StrEnum): LOBBY = "LOBBY"; EXPLORATION = "EXPLORATION"; COMBAT_INIT = "COMBAT_INIT"; COMBAT = "COMBAT"; NPC_DLG = "NPC_DLG"; PAUSED = "PAUSED"`
    - `class RiposteStatus(StrEnum): PENDING = "pending"; CONSUMED = "consumed"; EXPIRED = "expired"; CANCELLED = "cancelled"`
    - Models (`pydantic.BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`):
        - `ChannelSession`: channel_id, campaign_name, claudmaster_session_id: str | None, dm20_party_token: str | None, state: ChannelState = ChannelState.LOBBY, created_at: datetime, updated_at: datetime
        - `PersistentView`: custom_id, view_class, message_id, channel_id, payload: dict[str, Any] = Field(default_factory=dict), created_at: datetime — note `payload` (Python dict) maps to `payload_json` (TEXT) in the DB (D-20)
        - `RiposteTimer`: id: int | None, channel_id, character_id, user_id, monster_uuid: str | None, weapon_used: str | None, message_id, custom_id, deadline_ts: datetime, status: RiposteStatus = RiposteStatus.PENDING, created_at: datetime
        - `SanitizerAuditRow`: id: int | None, channel_id, user_id, raw_input, stripped_tokens: list[str] = Field(default_factory=list), redacted_output, truncated: bool, ts: datetime
    - DO NOT import from `eldritch_dm.mcp` or `eldritch_dm.safety` (boundary discipline).

    Tests:
    - `tests/persistence/__init__.py` (empty).
    - `tests/persistence/test_connection.py`:
        - `test_pragmas_set(tmp_path)`: open connection, query `PRAGMA journal_mode`, `PRAGMA foreign_keys`, `PRAGMA busy_timeout`, `PRAGMA synchronous` — assert values are `wal`, `1`, `5000`, `1` (NORMAL).
        - `test_open_connection_closes_on_exit(tmp_path)`: enter and exit the context manager; assert connection is closed (`conn._connection is None` or equivalent aiosqlite signal).
        - `test_writer_queue_serializes(tmp_path)`: create a `_kv(k TEXT PRIMARY KEY, v INTEGER)` table; submit 50 concurrent `INSERT INTO _kv VALUES (?, ?)` via `asyncio.gather(*[wq.submit(...) for ...])`; assert all 50 rows exist; assert no exception was raised.
        - `test_writer_queue_uses_begin_immediate()`: a static-source grep test — read `connection.py` and assert `"BEGIN IMMEDIATE"` appears and the regex `r"\bBEGIN(?!\s+IMMEDIATE)\b"` matches zero non-comment lines.
        - `test_writer_queue_stop_drains(tmp_path)`: submit two slow writes (sleep 0.05s each inside fn), call `stop()`, assert both completed.
        - `test_writer_queue_raises_after_stop(tmp_path)`: stop then `submit` raises RuntimeError.
    - `tests/persistence/test_models.py`:
        - `test_channel_session_frozen()`: constructing with all fields works; attempting `obj.state = ChannelState.PAUSED` raises ValidationError.
        - `test_extra_forbid()`: `ChannelSession(channel_id='1', campaign_name='c', ..., extra_field=True)` raises ValidationError.
        - `test_persistent_view_payload_roundtrip()`: payload={'foo': [1, 'two']}, dump to JSON via `model_dump(mode='json')`, reload, assert equal.
        - `test_sanitizer_audit_row_defaults()`: stripped_tokens defaults to `[]`, truncated defaults handled.
        - `test_state_check_constraints_documented()`: not a runtime test — assert that `ChannelState` enum values match the SQL CHECK constraint in schema.sql (read schema.sql, regex-extract the CHECK list, assert set equality).
  </behavior>
  <action>
    Implement the files per the behavior block. Use `aiosqlite` exclusively (no sync `sqlite3` calls in async paths). Use `from __future__ import annotations` at top of each module. Type hints everywhere; no `Any` except where JSON column payloads truly are dynamic. Logging via `eldritch_dm.logging.get_logger`, bound with `db_path` context where relevant. WriterQueue logs `q_depth` at DEBUG on every submit/dequeue.
  </action>
  <verify>
    <automated>pytest tests/persistence/test_connection.py tests/persistence/test_models.py -x -v</automated>
  </verify>
  <done>
    - All persistence tests pass
    - `grep -nE "\bBEGIN(?!\s+IMMEDIATE)\b" src/eldritch_dm/persistence/connection.py | grep -v "^[^:]*:[[:space:]]*#"` returns no results (no plain BEGIN outside comments)
    - import-linter still passes
    - Atomic commit: `feat(01-mcp-client-local-state): schema + connection layer + writer queue + models`
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Bootstrap + WAL checkpoint task</name>
  <files>
    src/eldritch_dm/persistence/bootstrap.py,
    src/eldritch_dm/persistence/checkpoint.py,
    tests/persistence/test_bootstrap.py,
    tests/persistence/test_checkpoint.py
  </files>
  <behavior>
    - `python -m eldritch_dm.persistence.bootstrap` creates the DB file at ELDRITCH_DB_PATH and applies `database/schema.sql` idempotently (running it twice does not raise) — per D-13, LOC-06
    - After bootstrap, all four tables exist with the expected columns and the four indexes from D-18
    - `CheckpointTask` periodically runs `PRAGMA wal_checkpoint(TRUNCATE)`; skips when `writer_queue.qsize() > 0` (per D-21)
    - `CheckpointTask.stop()` cancels cleanly and runs one final checkpoint
  </behavior>
  <action>
    Create `src/eldritch_dm/persistence/bootstrap.py`:
    - `SCHEMA_PATH = Path(__file__).resolve().parents[3] / "database" / "schema.sql"` — locate schema.sql relative to project root (the file is checked into the repo, not bundled in the wheel; for editable installs this works. For wheel installs we'd `importlib.resources`-ify later — leave a TODO comment).
    - `async def bootstrap(db_path: str | None = None) -> Path`: resolves db_path from arg or `get_settings().eldritch_db_path`; opens connection (applies pragmas); reads SCHEMA_PATH; executes via `await conn.executescript(sql)`; commits; closes; returns the Path. Logs at INFO with `db_path` and `tables_present` (queried via `sqlite_master`).
    - `def main() -> None`: `asyncio.run(bootstrap())` with `configure_logging` called first. Print a success line and the loaded model from oMLX is OUT OF SCOPE — bootstrap only handles the local DB (oMLX ping lives in run.py in Phase 5 per HOST-03).

    Create `src/eldritch_dm/persistence/checkpoint.py`:
    - `class CheckpointTask`:
        - `__init__(self, db_path: str, writer_queue: WriterQueue | None, interval_seconds: int = 600)`
        - `async def start(self) -> None`: spawns `_run()`.
        - `async def _run(self) -> None`: loop — sleep `interval_seconds`; if writer_queue and writer_queue.qsize() > 0, skip (log at DEBUG); else `async with open_connection(self.db_path) as c: await c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); await c.commit()`; catches `CancelledError` to break loop.
        - `async def stop(self, final: bool = True) -> None`: cancel task; if final, run one more checkpoint.
    - Document: interval of 0 disables the task (D-21); honor `get_settings().eldritch_db_checkpoint_interval`.

    Tests:
    - `tests/persistence/test_bootstrap.py`:
        - `test_bootstrap_creates_tables(tmp_path, monkeypatch)`: set ELDRITCH_DB_PATH to tmp; `await bootstrap(str(tmp_path / "eld.sqlite3"))`; open the DB, query `sqlite_master`, assert table names == {channel_sessions, persistent_views, riposte_timers, sanitizer_audit, sqlite_sequence}. Assert all four expected indexes exist.
        - `test_bootstrap_idempotent(tmp_path)`: run bootstrap twice; second run does not raise; row counts in tables remain 0.
        - `test_check_constraints_enforced(tmp_path)`: bootstrap; insert `channel_sessions` row with `state='BOGUS'`; assert IntegrityError.
        - `test_foreign_key_cascade(tmp_path)`: insert channel_sessions row + persistent_views row referencing it; DELETE channel_sessions; assert persistent_views row is gone (ON DELETE CASCADE).
        - `test_bootstrap_main_runs(tmp_path, monkeypatch, capsys)`: monkeypatch `get_settings().eldritch_db_path`, call `bootstrap.main()`, assert DB file exists and stdout contains a success line.
    - `tests/persistence/test_checkpoint.py`:
        - `test_checkpoint_runs(tmp_path)`: bootstrap; start CheckpointTask with interval=0.05; sleep 0.2s; stop; assert a log event with `wal_checkpoint` was emitted (capture via structlog testing fixture or by monkeypatching the logger).
        - `test_checkpoint_skips_when_queue_busy(tmp_path)`: writer_queue.qsize stub returns 3; start CheckpointTask; sleep; stop; assert checkpoint was NOT executed (no PRAGMA call ran — verify by inspecting WAL file size or by a recording-mock around open_connection).
        - `test_checkpoint_stop_final(tmp_path)`: start, immediately stop with final=True; assert one final checkpoint ran.
  </behavior>
  <action>
    Implement per behavior. Bootstrap must be re-runnable. Checkpoint task must shut down cleanly on CancelledError. Use structured logging for every state transition.
  </action>
  <verify>
    <automated>pytest tests/persistence/test_bootstrap.py tests/persistence/test_checkpoint.py -x -v && python -c "import asyncio, os; os.environ.setdefault('DISCORD_TOKEN','t'); os.environ['ELDRITCH_DB_PATH']='/tmp/eld-smoke.sqlite3'; from eldritch_dm.persistence.bootstrap import bootstrap; asyncio.run(bootstrap()); import sqlite3; c=sqlite3.connect('/tmp/eld-smoke.sqlite3'); print(sorted(r[0] for r in c.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall())); os.remove('/tmp/eld-smoke.sqlite3')"</automated>
  </verify>
  <done>
    - Bootstrap + checkpoint tests green
    - Smoke command prints `['channel_sessions', 'persistent_views', 'riposte_timers', 'sanitizer_audit', 'sqlite_sequence']` (order-insensitive)
    - Running bootstrap twice does not raise
    - import-linter still passes
    - Atomic commit: `feat(01-mcp-client-local-state): bootstrap + WAL checkpoint task`
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| env → process | `.env` values and shell env enter `Settings`; treated as trusted operator input (D-31, D-33) |
| filesystem → process | `database/schema.sql` is read and executed; treated as trusted (in-repo, code-reviewed) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-01 | Tampering | `database/schema.sql` | mitigate | Schema file shipped in-repo, code-reviewed; bootstrap reads from package-relative path (no user-provided path). Add test confirming schema.sql sha256 is logged at bootstrap so tampering is observable in audit logs. |
| T-01-02 | Information disclosure | `Settings` containing `DISCORD_TOKEN` | mitigate | `Settings.__repr__` overridden to redact `discord_token`; structlog config has a processor that scrubs any key matching `*token*`, `*secret*`, `*key*` before render. Add unit test asserting redaction. |
| T-01-03 | Denial of service | `WriterQueue` unbounded growth | accept | Single-process v1, queue depth bounded by Discord interaction rate which is itself rate-limited upstream; observable via `qsize()`. Reconsider with a maxsize bound if v2 sees >10 concurrent sessions. |
| T-01-04 | Tampering | `eldritch.sqlite3` file at rest | accept | Local-first / single-host project (PROJECT.md); SQLite at filesystem trust level. Documented in README. v2 may add age/sops encryption (D-deferred). |
| T-01-05 | Repudiation | bootstrap actions | mitigate | structlog INFO event on every bootstrap with db_path + table list + schema sha256; logs are durable per `LOG_FILE`. |
| T-01-SC | Tampering | pip/uv installs of pinned deps | mitigate | All packages in pyproject.toml are well-known PyPI projects (discord.py, httpx, aiosqlite, pydantic, tenacity, structlog, openai, python-dotenv, PyMuPDF, pypdf, ocrmac, easyocr, pytest et al.) — all `[OK]` per legitimacy heuristic (downloads in the millions, official maintainers). No `[ASSUMED]` or `[SUS]` packages introduced in this plan. RESEARCH.md does not contain a Package Legitimacy Audit table; install pipeline trust deferred to a future audit task — note in commit message. |
</threat_model>

<verification>
End-of-plan checks:
1. `uv pip install -e .[dev]` is idempotent and succeeds
2. `pytest tests/test_config.py tests/test_logging.py tests/persistence/ -x` green
3. `python -m importlinter --config pyproject.toml` exit 0
4. `python -c "import asyncio; from eldritch_dm.persistence.bootstrap import bootstrap; asyncio.run(bootstrap())"` creates the DB and the four tables on a fresh tmp path
5. `grep -nE '\bBEGIN(?!\s+IMMEDIATE)\b' src/eldritch_dm/persistence/connection.py | grep -v '^[^:]*:[[:space:]]*#' | wc -l` is 0
6. `python -m ruff check src/ tests/` exits 0
</verification>

<success_criteria>
- pyproject.toml installs editably with `[dev]` extras matching install.sh's pinned set exactly
- All connections set the four pragmas in D-15 order
- WriterQueue serializes writes with BEGIN IMMEDIATE; 50 concurrent submits succeed
- SessionLocks lazily creates per-channel locks that survive forever in-process
- Pydantic models for the four tables are frozen with `extra='forbid'`
- `python -m eldritch_dm.persistence.bootstrap` creates the schema idempotently
- CheckpointTask runs every interval and skips when writer queue is busy
- import-linter contract enforces hermetic boundaries (mcp / safety / persistence don't cross-import)
- DISCORD_TOKEN is redacted in logs
</success_criteria>

<output>
Create `.planning/phases/01-mcp-client-local-state/01-01-SUMMARY.md` when done, listing: created files, test counts, any deviations from plan, and the import-linter contract details (so plan 02 + 03 inherit them without re-reading pyproject.toml).
</output>
