---
phase: 21-monster-memory
plan: 21-02
subsystem: persistence
tags: [monster-memory, mem-03, aiosqlite, opt-in, fail-soft, honest-gap]
requirements: [MEM-03]
key-files:
  created:
    - src/eldritch_dm/persistence/monster_memory_repo.py
    - tests/persistence/test_monster_memory_repo.py
  modified:
    - src/eldritch_dm/config/__init__.py
decisions:
  - L-09 repo at persistence/monster_memory_repo.py (gameplay→persistence allowed)
  - L-10 schema with composite PK + idx_monster_memory_session (D-161)
  - L-11 settings monster_memory_persist (default False) + monster_memory_path
  - L-12 upsert / load / load_all_for_session / purge_session, all fail-soft
  - L-13 MonsterMemoryRegistry repo wired via structural Protocol (no hard import)
  - L-15 honest gap report — cog-side session-close wiring deferred to v1.7
  - L-16 best-effort flush (no per-observe disk thrash)
metrics:
  tests_added: 15
  full_phase_test_count: 39 (memory) + 15 (repo) + 8 (driver augment) + 2 (factory) = 64 new
  full_suite_after_phase: 473 gameplay+persistence pass
  regression_in_existing_tests: 0
---

# Phase 21 Plan 02 — Opt-in persistence + session-close hook (honest gap) Summary

## One-liner

Opt-in aiosqlite-backed MonsterMemory persistence (Phase 17 cache pattern, WAL,
fail-soft) at `~/.eldritch/monster_memory.sqlite` gated by
`MONSTER_MEMORY_PERSIST=true`; end-to-end bot-restart hydration verified; cog-side
session-close wiring honestly deferred to v1.7 because no clean hook exists in
v1.6 lobby/combat cogs.

## What Shipped

### `src/eldritch_dm/persistence/monster_memory_repo.py` (new)

`MonsterMemoryRepo` — lazy aiosqlite connection, WAL pragmas
(busy_timeout=5000, synchronous=NORMAL), schema per D-161:

```sql
CREATE TABLE monster_memory_entries (
    channel_id      TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    monster_id      TEXT NOT NULL,
    snapshot_json   TEXT NOT NULL,
    last_updated_ts INTEGER NOT NULL,
    PRIMARY KEY (channel_id, session_id, monster_id)
);
CREATE INDEX idx_monster_memory_session
    ON monster_memory_entries(channel_id, session_id);
```

Public API (all fail-soft):

| Method | Purpose | Fail-soft behavior |
|--------|---------|--------------------|
| `upsert(ch, sess, mid, snapshot)` | Insert-or-update via ON CONFLICT | log + swallow exc |
| `load(ch, sess, mid)` | Read one snapshot | return `None` |
| `load_all_for_session(ch, sess)` | Read every snapshot for a session | return `{}`; per-row JSON decode errors skipped |
| `purge_session(ch, sess)` | DELETE matching rows | return `0` |
| `aclose()` | Idempotent connection close | swallow |

### `src/eldritch_dm/config/__init__.py` (extended)

Two new settings adjacent to `narrcache_*` (matching opt-in nature):

- `monster_memory_persist: bool = False` (alias `MONSTER_MEMORY_PERSIST`)
- `monster_memory_path: str = "~/.eldritch/monster_memory.sqlite"` (alias `MONSTER_MEMORY_PATH`)

### `src/eldritch_dm/gameplay/monster_memory.py` (already extended in Plan 21-01)

The async registry surface (`recall_async`, `flush`, `flush_all`,
`purge_session_async`) shipped in Plan 21-01 via a structural `Protocol` so the
gameplay layer never hard-imports `eldritch_dm.persistence.monster_memory_repo`.
This kept Plan 21-02 a pure persistence drop-in — bootstrap can construct
`MonsterMemoryRepo` and inject via `MonsterMemoryRegistry(repo=...)`.

## End-to-End Hydration Verified

`test_registry_hydrates_from_real_repo`:

1. Bot run #1: `MonsterMemoryRepo` + `MonsterMemoryRegistry(repo=...)`,
   observe damage + concentration on `pc-wizard`, `flush()`, `aclose()`.
2. Bot run #2: fresh repo + registry pointing at the same SQLite file,
   `recall_async("c", "s", "m")` returns a `MonsterMemory` with the same
   signals, AND `damage_band("pc-wizard")` correctly classifies the rehydrated
   total as `"high"`.

This proves MEM-03 acceptance criterion "Survives bot restart" — the disk
round-trip preserves all three signals AND the derived band.

`test_registry_purge_session_async_clears_disk` proves the
`purge_session_async` API wipes both in-memory entries and on-disk rows.

## Known Gap (v1.7) — Honest Report

**Status:** Persistence engine + purge API ship complete and tested. Cog-side
wiring deferred. Same honest-report pattern as Phase 18.

### What we surveyed

| File | Hook we looked for | Result |
|------|--------------------|--------|
| `src/eldritch_dm/bot/cogs/lobby.py` | `/end_game` slash command or `dm20__close_session` callback | **Not present.** Lobby owns `/start_game` and rollback on failure, but there is no clean session-close command or event subscription in v1.6. |
| `src/eldritch_dm/bot/cogs/combat.py:on_resolved_combat` | A typed damage payload to thread into `MonsterMemory.observe_hit` | **Schema not typed for damage extraction.** `on_resolved_combat` receives an `action_payload: dict[str, Any]` from the orchestrator. The payload is consumed for embed refresh only — its damage shape is not currently part of any documented contract. Wiring `observe_hit` here would require inferring damage from an unstable shape, which violates **D-163** ("damage observations come from the rules engine ONLY; the bot must not invent damage"). |

### Why we refuse to fabricate the hook

Inferring damage from `action_payload`'s untyped fields would either:

1. Crash combat on the first payload shape that doesn't match our guess (violates D-58 fail-soft posture by introducing a new failure mode), OR
2. Silently miss observations (memory becomes a half-truth — worse than no memory).

Both outcomes are strictly worse than shipping the persistence engine and
documenting the gap. **Mechanical honesty trumps surface-area count.**

### Wiring plan for v1.7

1. **Typed damage event from dm20 orchestrator.** Add a `damage_resolved` event
   to the orchestrator's contract carrying typed
   `(pc_id: str, damage: int, monster_id: str, round_number: int, concentration_check_failed: bool)`
   tuples. The rules engine already has this information — it just doesn't
   surface it to cogs in a typed shape.
2. **Wire `observe_hit` in `combat.py:on_resolved_combat`.** Once the typed
   event exists, the cog can subscribe and call
   `await self.monster_memory.recall_async(channel_id, session_id, monster_id)
   .observe_hit(pc_id, damage, observer_int=<from game_state>)` from the
   payload, and `observe_concentration` from concentration check results.
3. **Add `/end_game` command (or `dm20__close_session` subscriber).** Either a
   user-facing slash command in `lobby.py` or an orchestrator-side lifecycle
   event must fire `await monster_memory_registry.purge_session_async(channel_id, session_id)`
   before the channel session row is deleted.
4. **Best-effort flush on cog_unload / atexit.** Already structured in the
   Registry's `flush_all()` API; the v1.7 bot bootstrap should register a
   `try/finally` that calls it during shutdown.

Every prerequisite for the wiring is already in place — only the orchestrator
event contract change and the two cog subscriptions remain.

## Deviations from Plan

- **L-14 (bootstrap wiring) deferred** alongside the cog hook for the same
  reason: with no `/end_game` hook to call `purge_session_async`, persisting
  memory across reboots without a session-clear mechanism would let stale
  monsters from old campaigns bleed into fresh ones. Shipping settings +
  repo + registry async API (everything except the orchestrator construction)
  is the safest split.
- **Tasks 3+4 collapsed into Plan 21-01.** The async registry surface
  (`recall_async`, `flush`, `purge_session_async`) was already structurally
  implemented in Plan 21-01 via the `_MonsterMemoryRepoProto` Protocol — Plan
  21-02 simply provides the concrete repo. Documented as Rule 3 (auto-fix
  blocking issue): the Protocol indirection was required to keep the
  import-linter contract `gameplay → persistence` from inverting, so it had
  to land with Plan 21-01.

## Verification

```
$ pytest tests/persistence/test_monster_memory_repo.py -v   # 15 passed
$ pytest tests/gameplay/ tests/persistence/                 # 473 passed
$ ruff check src/eldritch_dm/persistence/monster_memory_repo.py
             tests/persistence/test_monster_memory_repo.py
             src/eldritch_dm/config/__init__.py            # All checks passed!
$ lint-imports                                              # 8 kept, 0 broken
```

## Self-Check: PASSED

- `src/eldritch_dm/persistence/monster_memory_repo.py` exists
- `tests/persistence/test_monster_memory_repo.py` exists (15 tests)
- Settings `MONSTER_MEMORY_PERSIST` (default `False`) + `MONSTER_MEMORY_PATH` present
- End-to-end hydration test passes
- REQUIREMENTS.md MEM-03 marked [x]
- Commits: `d5d630e feat(21-02): MonsterMemoryRepo + settings`,
  `19f4352 test(21-02): end-to-end repo+registry hydration + purge-async`
