# Phase 1: Persistence Foundation - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning
**Mode:** Synthesized from prescriptive PRD + research SUMMARY.md (autonomous YOLO mode)

<domain>
## Phase Boundary

Deliver a correct, single-writer SQLite persistence layer supporting concurrent multi-channel D&D game sessions with zero writer contention. Covers schema creation, connection management, write-transaction serialization, repository layer, and a stress test that proves the design under load. Does NOT include game engine logic, state machine, Discord wiring, or inference — those live in later phases. Repositories should expose enough surface for the engine and FSM to land on top in phases 2 and 4 without retrofitting persistence.

</domain>

<decisions>
## Implementation Decisions

### Schema delivery
- **D-01:** Schema lives in `database/schema.sql` as raw DDL (matches PRD §3 verbatim)
- **D-02:** A `bootstrap` module reads `schema.sql` and runs it idempotently against the target DB file via `CREATE TABLE IF NOT EXISTS`. No migrations framework (alembic/yoyo) in v1 — schema evolution is manual.
- **D-03:** Schema includes the four PRD tables (`game_sessions`, `characters`, `combat_monsters`, `campaign_memory`) and the three performance indices (`idx_chars_channel`, `idx_monsters_channel`, `idx_memory_channel`). `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL` declared at the top of `schema.sql` and re-applied per connection.

### Connection management
- **D-04:** Use `aiosqlite` (pinned `>=0.20,<0.22`); each connection runs in its own thread under the hood.
- **D-05:** A single **writer connection** is held by a dedicated `WriterQueue` asyncio task. All write operations are submitted to this queue as coroutines; the writer task drains and executes them serially.
- **D-06:** **Reader connections** are short-lived per-coroutine; readers do not contend on locks (WAL allows non-blocking reads against the snapshot).
- **D-07:** Every new connection (reader or writer) sets, in this order on first acquisition:
  ```sql
  PRAGMA foreign_keys = ON;
  PRAGMA journal_mode = WAL;
  PRAGMA busy_timeout = 5000;
  PRAGMA synchronous = NORMAL;
  ```
- **D-08:** Every write transaction uses `BEGIN IMMEDIATE`. Never `BEGIN DEFERRED`-then-upgrade. Transactions never span an `await` to anything other than aiosqlite itself (no `llm_call` inside a txn, no HTTP).

### Locking strategy
- **D-09:** A `SessionLocks` registry hands out an `asyncio.Lock` per `channel_id` (lazy create, weakref-friendly). Acquire the session lock around any read-modify-write that touches a single session's aggregate.
- **D-10:** Cross-session writes (e.g., the WAL checkpoint task) acquire the global writer queue but no session locks.

### Repository pattern
- **D-11:** One repository per aggregate:
  - `SessionRepo` — `game_sessions` rows (state, turn_sequence, active_idx, round_number, current_room_id, campaign_blueprint)
  - `CharacterRepo` — `characters` rows
  - `MonsterRepo` — `combat_monsters` rows
  - `MemoryRepo` — `campaign_memory` rows
- **D-12:** Repository methods accept and return **pydantic v2 dataclasses** (frozen models with `model_config = ConfigDict(frozen=True)`). JSON columns (`turn_sequence`, `weapons`, `skills`, `spells`, `inventory`, `campaign_blueprint`) are serialized via `pydantic.TypeAdapter` on write and parsed on read — repositories never expose raw strings of JSON to callers.
- **D-13:** Repository write methods submit to the writer queue. Read methods bypass it. Public API is async even when underlying call is sync.

### Filesystem layout
- **D-14:** Source modules under `src/persistence/`:
  ```
  src/persistence/__init__.py
  src/persistence/connection.py    # aiosqlite + pragmas + writer queue
  src/persistence/locks.py         # SessionLocks asyncio.Lock registry
  src/persistence/models.py        # pydantic dataclasses mirroring schema
  src/persistence/session_repo.py
  src/persistence/character_repo.py
  src/persistence/monster_repo.py
  src/persistence/memory_repo.py
  src/persistence/bootstrap.py     # reads database/schema.sql, applies idempotently
  src/persistence/checkpoint.py    # periodic PRAGMA wal_checkpoint(TRUNCATE)
  database/schema.sql              # raw DDL (verbatim from PRD §3)
  tests/persistence/               # see test plan below
  ```
- **D-15:** DB file path is env-configurable: `ELDRITCH_DB_PATH` (default: `./eldritch.sqlite3`). Path passes through `bootstrap.ensure_schema(path)`.

### Checkpoint / housekeeping
- **D-16:** A background task runs `PRAGMA wal_checkpoint(TRUNCATE)` every 10 minutes (configurable). Skipped if writer queue is non-empty (to avoid stalling writers).
- **D-17:** Graceful shutdown: writer task drains its queue, runs a final checkpoint, closes the writer connection.

### Hermetic boundary
- **D-18:** `src/persistence/` imports only stdlib + `aiosqlite` + `pydantic` + `structlog`. No imports from `engine/`, `orchestrator/`, `inference/`, or any discord-related package. Enforced by `import-linter` config in Phase 11 packaging, but already a discipline now.

### Stress test (DB-08 verification)
- **D-19:** `tests/persistence/test_concurrent_writes.py` spawns N=4 (configurable up to 8) simulated channels each performing 60 seconds of mixed read/write traffic against `SessionRepo` + `CharacterRepo`. Pass criteria:
  - Zero `database is locked` errors
  - Zero `SQLITE_BUSY` returns
  - All writes successfully serialized (final row count matches expected)
  - Median write latency under 50ms, p99 under 250ms
- **D-20:** Stress test is marked `@pytest.mark.slow` and gated behind `RUN_STRESS=1` env var so default `pytest` runs stay fast.

### Test framework
- **D-21:** `pytest` + `pytest-asyncio` (`mode = "auto"` in `pyproject.toml`). Each test gets a fresh tmp_path DB via fixture.
- **D-22:** Unit tests for each repository's CRUD methods. Integration test for cascade deletes (FK ON DELETE CASCADE from `game_sessions`). Round-trip tests for JSON column serialization.

### Claude's Discretion
- Exact pydantic model field constraints (validators, max lengths) — derive from schema CHECK constraints and reasonable bounds
- Internal layout of the writer queue (single `asyncio.Queue` vs `Channel` pattern)
- Logging key names — follow research SUMMARY structlog convention: bind `channel_id`, `actor`, `op`
- Whether to expose a context manager (`async with repo.transaction():`) helper or rely on writer-queue submission semantics

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements
- `.planning/REQUIREMENTS.md` § Persistence (DB) — requirements DB-01 through DB-08
- `.planning/ROADMAP.md` § Phase 1 — goal + 5 success criteria

### Architectural context
- `.planning/research/SUMMARY.md` § Architecture — async model (asyncio loop + ThreadPoolExecutor split), restart-recovery flow
- `.planning/research/SUMMARY.md` § Concurrency (single-writer) — exact pattern this phase implements
- `.planning/research/SUMMARY.md` § Pitfalls → Phase Mapping — Pitfall #6 (SQLite writer contention)
- `.planning/research/ARCHITECTURE.md` — Layered diagram; persistence layer position
- `.planning/research/PITFALLS.md` — Concrete WAL/`BEGIN IMMEDIATE`/`busy_timeout` discussion

### Project-level constraints
- `.planning/PROJECT.md` § Constraints — pinned versions, performance budgets
- `.planning/PROJECT.md` § Key Decisions — three-brain logical boundary

### Schema authority
- D&D PRD § 3 (in conversation history) — schema is verbatim copy; do not redesign columns
- Future `database/schema.sql` (to be created by this phase) — single source of truth post-phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Greenfield
This is a brand-new project. No prior code exists. `git log` shows only the four planning commits from project initialization.

### Reusable Assets
None — first phase building first module.

### Established Patterns
None to inherit yet. This phase establishes:
- Async repository pattern (pydantic v2 dataclasses ↔ aiosqlite rows)
- Single-writer queue idiom (used by all future write paths)
- Per-aggregate lock registry (used by FSM and engine in later phases)
- Hermetic module boundary discipline (template for engine/, inference/, orchestrator/)

### Integration Points
- Future Phase 2 (`engine/`) will import only `persistence.models` (read-only types) — engine never holds connections or transactions.
- Future Phase 3 (`inference/`) will import nothing from persistence — inference is fed pre-resolved data.
- Future Phase 4 (`orchestrator/state_machine`) is the primary consumer of repositories; designs around the writer-queue API.
- Future Phase 5 (`orchestrator/bot`) calls `SessionRepo.list_active()` in `setup_hook` to rehydrate persistent Views — that method must exist by end of Phase 1.

</code_context>

<specifics>
## Specific Ideas

- Treat the persistence layer like infrastructure code, not feature code — overengineering "for future flexibility" (multi-DB support, ORM abstraction) is explicitly out of scope. SQLite is the only target.
- The writer-queue pattern is non-negotiable: a future maintainer should look at write paths and immediately see "all writes funnel through one task" — no clever per-aggregate-writer fanout.
- Tests should be runnable on a laptop in <5s for the default suite (stress test gated separately).
- The JSON column round-trip (e.g., `turn_sequence` as `list[str]`) needs to be invisible to repo callers — they pass and receive typed pydantic models, never JSON strings.

</specifics>

<deferred>
## Deferred Ideas

- Database backup / point-in-time recovery — not v1, add to backlog if a user requests it
- Read replicas / horizontal scaling — explicitly not happening; SQLite is the limit
- Schema migrations framework (alembic) — defer to v2 if/when schema changes happen post-ship; idempotent `CREATE TABLE IF NOT EXISTS` is enough for v1
- ORM (SQLAlchemy Core/ORM, encode/databases) — explicitly rejected per research SUMMARY's "Do NOT use" list; raw SQL keeps the layer transparent
- Multi-tenant DB-per-server isolation — single SQLite file is sufficient for v1's self-host scope

</deferred>

---

*Phase: 01-persistence-foundation*
*Context gathered: 2026-05-21*
