---
phase: 05-reactions-self-host-polish
plan: 01
subsystem: combat
tags: [reactions, riposte, monster-driver, pc-classes, schema-migration, sqlite, discord-py, persistent-views]

# Dependency graph
requires:
  - phase: 04-gameplay-exploration-combat
    provides: PartyModeOrchestrator + ChannelRateLimiter + AttackButton (whose stub seam we delete)
  - phase: 03-character-ingest-and-lobby
    provides: dm20__create_character ingest path that we hook to populate pc_classes
  - phase: 02-discord-scaffold-persistent-views
    provides: DynamicItem rehydration + RiposteButton class stub (Phase 2)
  - phase: 01-mcp-client-local-state
    provides: WriterQueue, schema bootstrap, RiposteTimer model
provides:
  - Idempotent ALTER TABLE riposte_timers ADD COLUMN consumed_in_round INTEGER (reaction-budget shim)
  - pc_classes table + PCClassesRepo (subclass at ingest for eligibility)
  - combat_outcome_parser (regex over dm20 _format_combat_result headers)
  - gameplay.reactions module (eligibility + surface_riposte_button + handle_riposte_click)
  - gameplay.monster_driver (random-target driver per D-B; v2 deferral TODO documented)
  - RiposteButton.callback promoted from Phase 2 stub to real handler
  - PartyModeOrchestrator.maybe_drive_monster_turn idempotent dispatch helper
  - Ingest-time pc_classes upsert for both manual and URL paths
  - PLAN-02-LOCK-SEAM marker handoff for Plan 02 sweeper integration
affects: [05-sweeper-and-restart-survival, 05-self-host-polish-and-closure, future REACT-* v2 work]

# Tech tracking
tech-stack:
  added: []  # zero new pip dependencies
  patterns:
    - "Reaction-budget shim via additive ALTER TABLE — no schema-rebuild migration cost"
    - "Per-character subclass persisted at bot side (dm20 text omits subclass)"
    - "Dependency-inject bot/ symbols (send_warning, WarningKind, RiposteButton) into gameplay/ to satisfy import-linter"
    - "Lazy-import pattern for bot/ ↔ gameplay/ cycle avoidance"
    - "Post-channel.send deadline recompute (RESEARCH Pitfall 1) — TTL accounts for Discord API latency"

key-files:
  created:
    - src/eldritch_dm/persistence/pc_classes_repo.py (174 LOC) — PCClassesRepo + PCClassInfo pydantic frozen model
    - src/eldritch_dm/gameplay/combat_outcome_parser.py (77 LOC) — AttackOutcome StrEnum + parse_combat_outcome
    - src/eldritch_dm/gameplay/reactions.py (399 LOC) — eligibility + surface_riposte_button + handle_riposte_click + PLAN-02-LOCK-SEAM marker
    - src/eldritch_dm/gameplay/monster_driver.py (289 LOC) — minimal random-target driver per D-B
    - tests/persistence/test_pc_classes_repo.py (144 LOC) — 5 tests
    - tests/gameplay/test_combat_outcome_parser.py (65 LOC) — 8 tests
    - tests/gameplay/test_reactions.py (418 LOC) — 14 tests
    - tests/gameplay/test_monster_driver.py (471 LOC) — 14 tests (incl. 3 PartyMode dispatch)
    - tests/gameplay/test_riposte_callback.py (403 LOC) — 9 tests
    - tests/integration/test_riposte_smoke.py (310 LOC) — 3 happy-path scenarios
    - .planning/phases/05-reactions-self-host-polish/deferred-items.md — pre-existing exploration_batch ruff issues out of scope
  modified:
    - database/schema.sql — added pc_classes table + documented additive ALTER for consumed_in_round
    - src/eldritch_dm/persistence/bootstrap.py — idempotent ALTER guarded by try/except OperationalError
    - src/eldritch_dm/persistence/models.py — RiposteTimer gains consumed_in_round: int | None = None
    - src/eldritch_dm/persistence/riposte_timers_repo.py — list_for_character, mark_cancelled, update_message_ref, mark_consumed_with_round
    - src/eldritch_dm/persistence/__init__.py — export PCClassesRepo + PCClassInfo
    - src/eldritch_dm/gameplay/party_mode.py — monster_driver constructor kwarg + maybe_drive_monster_turn helper
    - src/eldritch_dm/bot/dynamic_items.py — DELETED _maybe_surface_riposte (D-A); promoted RiposteButton.callback
    - src/eldritch_dm/bot/bot.py — pc_classes + riposte_timers + monster_driver in setup_hook + current_round_for_channel helper
    - src/eldritch_dm/bot/cogs/ingest.py — pc_classes.upsert in both _on_character_submit and upload_character_url
    - src/eldritch_dm/bot/cogs/combat.py — docstring update (stale Phase 5 hook note removed)
    - tests/persistence/test_bootstrap.py — pc_classes + 5 migration tests
    - tests/persistence/test_riposte_timers_repo.py — 8 extension tests for new repo methods
    - tests/bot/test_dynamic_items.py — drop RiposteButton from _STUB_CLASSES (now real)
    - tests/bot/test_setup_hook.py — 5 Phase 5 wiring tests
    - pyproject.toml — per-file E501 waiver for reactions.py PLAN-02-LOCK-SEAM marker

key-decisions:
  - "D-A — Deleted AttackButton._maybe_surface_riposte (wrong RAW path)"
  - "D-B — MonsterDriver uses uniformly-random PC targeting; smart Claudmaster targeting deferred to v2"
  - "D-C — Strict RAW eligibility: Battle Master Fighter only (Swashbuckler correctly excluded)"
  - "Public-message + permission-gate (not ephemeral) — restart-survival demands it"
  - "Subclass captured at ingest in pc_classes; dm20 get_character text omits it"
  - "Dependency-inject send_warning + WarningKind into gameplay/reactions so import-linter contract holds"
  - "consumed_in_round added via additive ALTER (not schema rewrite) for backwards-compat"

patterns-established:
  - "PLAN-02-LOCK-SEAM marker convention — deliberate string in source code for cross-plan grep handoff"
  - "Public-message + permission-gate pattern for restart-surviving timed interactions"
  - "Additive ALTER TABLE migration in bootstrap.py guarded by try/except for idempotency"
  - "button_factory dependency injection: pass discord.ui.Item factory from bot/ into gameplay/ helpers so gameplay/ stays free of bot/ imports"

requirements-completed: [COMBAT-09, COMBAT-10]

# Metrics
duration: 70 min
completed: 2026-05-22
---

# Phase 5 Plan 01: Riposte + MonsterDriver Summary

**Battle Master Riposte ships end-to-end on the corrected RAW trigger path: MonsterDriver detects monster-attack misses, eligibility-gates against pc_classes + consumed_in_round budget shim, and surfaces a public-message persistent-View button that the RiposteButton.callback resolves through dm20__combat_action with reaction-budget mark.**

## Performance

- **Duration:** 70 min
- **Started:** 2026-05-22T09:22:14Z
- **Completed:** 2026-05-22T10:32:00Z
- **Tasks:** 3 (plus the standalone D-A deletion commit)
- **Files created:** 11 (4 source + 6 tests + 1 deferred-items doc)
- **Files modified:** 16

## Accomplishments

- Closed the Phase 4 monster-turn driving gap (RESEARCH finding #6) with a minimal random-target MonsterDriver per user decision D-B.
- Deleted Phase 4's misplaced `_maybe_surface_riposte` seam (D-A) — atomic commit `1d2edc8` so a future bisect can isolate it cleanly.
- Reaction-budget shim landed via idempotent ALTER on `riposte_timers.consumed_in_round` — bootstrap re-runs are no-ops.
- New `pc_classes` table + repo persists per-character subclass at ingest time, working around dm20 `get_character` text omitting subclass (RESEARCH Q2).
- `gameplay/reactions.py` ships RAW-only eligibility (Battle Master Fighter, D-C) with explicit v2 YAML-config TODO. Swashbuckler explicitly excluded — corrects CONTEXT.md D-04.
- `RiposteButton.callback` promoted from Phase 2 stub to real handler with full gate→combat_action→mark_consumed sequence; PLAN-02-LOCK-SEAM marker is in place at `src/eldritch_dm/gameplay/reactions.py:280` inside `handle_riposte_click`.
- Pre-Pitfall-1 deadline-recompute pattern: deadline written via `update_message_ref` is captured AFTER `channel.send` returns so the 8s TTL is not consumed by Discord API latency.
- Public-message + permission-gate Riposte button (NOT ephemeral) so it survives bot restart — pre-requisite for Plan 02 COMBAT-11 restart drill.
- Ingest cog upserts `pc_classes` after every successful character creation (manual path + URL path).
- Test suite grew 734 → 798 (+64 net passing tests). lint-imports 7/7 contracts kept. ruff clean on all Plan 01 files.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 schema migration + pc_classes + repo extensions** — `172799c` (feat)
2. **D-A deletion** (split from Task 2 for bisect isolation) — `1d2edc8` (refactor)
3. **Task 2: combat_outcome_parser + reactions + MonsterDriver + RiposteButton wired** — `9c28ea3` (feat)
4. **Task 3: setup_hook wiring + MonsterDriver instantiation + smoke tests** — `eb4e0f7` (feat)

No separate documentation commit yet — this SUMMARY commit will land via the final state-update step.

## Files Created/Modified

### Created

- `src/eldritch_dm/persistence/pc_classes_repo.py` — PCClassesRepo with normalizing PCClassInfo pydantic model
- `src/eldritch_dm/gameplay/combat_outcome_parser.py` — AttackOutcome StrEnum + parse_combat_outcome
- `src/eldritch_dm/gameplay/reactions.py` — RiposteEligibility + check_riposte_eligibility + surface_riposte_button + handle_riposte_click (contains PLAN-02-LOCK-SEAM marker)
- `src/eldritch_dm/gameplay/monster_driver.py` — minimal random-target MonsterDriver
- Six test files (combat_outcome_parser, reactions, monster_driver, riposte_callback, pc_classes_repo, riposte_smoke)
- `.planning/phases/05-reactions-self-host-polish/deferred-items.md`

### Modified

- `database/schema.sql` — pc_classes table + documented additive ALTER pattern
- `src/eldritch_dm/persistence/bootstrap.py` — try/except OperationalError around ALTER
- `src/eldritch_dm/persistence/models.py` — RiposteTimer.consumed_in_round
- `src/eldritch_dm/persistence/riposte_timers_repo.py` — 4 new methods + insert includes new column
- `src/eldritch_dm/persistence/__init__.py` — exports
- `src/eldritch_dm/gameplay/party_mode.py` — monster_driver kwarg + maybe_drive_monster_turn helper
- `src/eldritch_dm/bot/dynamic_items.py` — DELETED `_maybe_surface_riposte` (D-A); promoted RiposteButton.callback
- `src/eldritch_dm/bot/bot.py` — Phase 5 wiring + current_round_for_channel
- `src/eldritch_dm/bot/cogs/ingest.py` — pc_classes.upsert on both ingest paths
- `src/eldritch_dm/bot/cogs/combat.py` — docstring sync
- `tests/persistence/test_bootstrap.py` — pc_classes + migration tests
- `tests/persistence/test_riposte_timers_repo.py` — extension tests
- `tests/bot/test_dynamic_items.py` — RiposteButton removed from _STUB_CLASSES
- `tests/bot/test_setup_hook.py` — Phase 5 wiring tests
- `pyproject.toml` — per-file E501 waiver for reactions.py marker line

## Decisions Made

User-baked decisions (executed as specified, not re-litigated):

1. **D-A — Delete `_maybe_surface_riposte`.** Atomic commit `1d2edc8`. Grep over `src/eldritch_dm/bot/` returns only documentation hits (2 in `dynamic_items.py` module/class docstrings explaining why it's gone, 0 executable code references — verified by Test 31/32 in `tests/gameplay/test_riposte_callback.py`).
2. **D-B — MonsterDriver minimal random targeting.** `monster_driver.py` has the mandated TODO comment block at module docstring + the v2-deferral TODO with REQUIREMENTS REACT-* reference. `random_choice` is dependency-injected for deterministic testing.
3. **D-C — Strict RAW eligibility.** `ELIGIBLE_CLASS_SUBCLASSES = frozenset({("fighter", "battle master")})`. Code comment block above the frozenset explicitly cites the v2 YAML-config plan. CONTEXT.md D-04's Swashbuckler claim is corrected by this plan (not in REQUIREMENTS yet — Plan 03 closure will tidy that up per the plan's own note).

Executor-level decisions made during execution:

4. **Dependency-injection over module relocation.** The plan put `handle_riposte_click` in `gameplay/reactions.py` (callable from `RiposteButton.callback`). That would require `gameplay/` to import `bot.warnings` and `bot.dynamic_items.RiposteButton`, breaking the `gameplay must not import bot or ingest` import-linter contract. Resolved by passing `send_warning`, `WarningKind.*`, and a `button_factory` into the gameplay helpers as callables; the bot layer wires them at call time. This keeps the plan's named location for the PLAN-02-LOCK-SEAM marker while preserving boundary discipline.

5. **`tests/bot/test_dynamic_items.py` _STUB_CLASSES emptied.** When `RiposteButton.callback` was promoted to real, the Phase 2 stub-parametrized test failed (expected message "Phase 2 stub" not present). Emptied the parametrize list and left the test class as a future-stub-extension point.

6. **Per-file E501 waiver for `reactions.py`.** The PLAN-02-LOCK-SEAM marker MUST be one continuous line so Plan 02's executor can grep for it. Wrapping the line would silently break the handoff. Added a narrow `[tool.ruff.lint.per-file-ignores]` entry with a comment explaining why.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] gameplay → bot import would break import-linter contract**
- **Found during:** Task 2 (writing reactions.py)
- **Issue:** The plan's body for `handle_riposte_click` directly imports `bot.warnings.WarningKind` + `bot.warnings.send_warning`. Running `uv run lint-imports` after writing reactions.py reported: `gameplay must not import bot or ingest` BROKEN.
- **Fix:** Restructured `handle_riposte_click` and `surface_riposte_button` to accept `warning_sender`, `invalid_action_kind`, `riposte_expired_kind`, and `button_factory` as callable parameters. `RiposteButton.callback` injects the real `bot/` symbols at call time. The PLAN-02-LOCK-SEAM marker remains exactly where the plan specified (inside `handle_riposte_click` body).
- **Files modified:** `src/eldritch_dm/gameplay/reactions.py`, `src/eldritch_dm/bot/dynamic_items.py`
- **Verification:** `uv run lint-imports` → all 7 contracts kept.
- **Committed in:** `9c28ea3` (Task 2 commit)

**2. [Rule 1 — Bug] Unused `mech_result` variable after `_maybe_surface_riposte` deletion**
- **Found during:** Task 3 ruff sweep
- **Issue:** `AttackButton.callback._on_weapon_submit` captured the dm20 result into `mech_result` solely to pass it to the deleted `_maybe_surface_riposte` seam. After D-A deletion, the variable was unused; ruff flagged F841.
- **Fix:** Drop the assignment — the call is now `await mcp_tools.combat_action(...)`.
- **Files modified:** `src/eldritch_dm/bot/dynamic_items.py`
- **Verification:** ruff clean.
- **Committed in:** `eb4e0f7` (Task 3 commit)

**3. [Rule 2 — Missing Critical] structlog console-mode log capture in bootstrap test**
- **Found during:** Task 1 first test run
- **Issue:** Test 5 (migration-log idempotency) used `caplog.at_level(...)` to capture the `riposte_timers_migrated_consumed_in_round` event. structlog's processor pipeline writes to stdout in console mode, not through stdlib logging; caplog saw nothing.
- **Fix:** Switched the test to `capsys` (captures stdout) and asserts the structlog event line appears in run 1 and is absent in run 2. The actual bootstrap logging is unchanged.
- **Files modified:** `tests/persistence/test_bootstrap.py`
- **Verification:** Both assertions pass.
- **Committed in:** `172799c` (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (1 blocking import-linter, 1 post-deletion unused-var bug, 1 test infrastructure misuse).
**Impact on plan:** All three are mechanical / discipline fixes. No scope creep. The dependency-injection refactor preserves the plan's stated PLAN-02-LOCK-SEAM marker location AND tightens the boundary discipline.

## Known Stubs

None. Both newly-added user-facing surfaces (Riposte button + reaction budget) have full code paths. `MonsterDriver`'s default `state_provider` returns `{"pcs": []}` when no enriched state source is wired — this is INTENTIONAL v1 behavior (smart targeting + richer state assembly is deferred to v2 and CombatCog hookup in a later plan). When the provider returns empty, the driver logs `monster_driver_no_eligible_target` and still calls `next_turn` so combat doesn't deadlock. This is documented in `monster_driver.py` setup_hook wiring comment.

## Threat Flags

None. All new code touches an existing threat surface (`riposte_timers` + Discord interaction permission gate) for which the plan's `<threat_model>` already enumerated mitigations T-05-01..09 + T-05-SC. No new network endpoints, no new auth paths, no new file-access patterns. Zero new third-party dependencies (T-05-SC: accept).

## Issues Encountered

- Background bash output sometimes returned empty in the executor environment; switched to `tee /tmp/<file>` + immediate `cat /tmp/<file>` pattern. No effect on actual test results.
- pre-existing ruff issues in `src/eldritch_dm/gameplay/exploration_batch.py` (Phase 4 residue) surface when `ruff check src/eldritch_dm/gameplay/` runs broadly. Documented in `.planning/phases/05-reactions-self-host-polish/deferred-items.md` per scope-boundary rule. NOT fixed in this plan.

## Next Plan Readiness

**Plan 02 may now wrap `gameplay.reactions.handle_riposte_click` and the sweeper's mark-expired in a shared per-channel `asyncio.Lock`; both code paths exist.**

PLAN-02-LOCK-SEAM marker is at:

```
src/eldritch_dm/gameplay/reactions.py:280
```

Inside the docstring of `handle_riposte_click`. Grep verification:

```bash
grep -n "PLAN-02-LOCK-SEAM" src/eldritch_dm/gameplay/reactions.py
# → 39:  `PLAN-02-LOCK-SEAM` marker to find the exact wrap point.
# → 280:    PLAN-02-LOCK-SEAM: replace status check with `async with session_locks.acquire("riposte", channel_id):` wrapper
```

Plan 02 Task 1 Test 15's grep gate will see exactly one actionable hit (line 280 — line 39 is in the module docstring describing the marker convention).

Other Plan 02 prerequisites confirmed in place:

- `bot.riposte_timers_repo` and `bot.riposte_timers` (alias) exposed for sweeper construction
- `RiposteTimerRepo.list_pending()` (already shipped Phase 1) returns all rows the sweeper needs
- `RiposteTimerRepo.mark_expired(id_)` + `mark_consumed_with_round(id_, round_n)` cover the sweeper's expire path and the click-success path respectively
- Public-message Riposte button (not ephemeral) — survives bot restart; Plan 02 OPS-01 drill can fetch and re-attach via the existing rehydrate path

Self-host polish (Plan 03) prerequisites:

- pc_classes table is populated at ingest. Self-hosters upgrading from a Phase 4 deployment will have empty pc_classes for existing characters — eligibility check returns None for missing rows (silent safe skip). Plan 03 should ship a one-shot backfill script as documented in the plan's RESEARCH risks section.

## Self-Check: PASSED

Verified files exist:

- `src/eldritch_dm/persistence/pc_classes_repo.py` ✓
- `src/eldritch_dm/gameplay/combat_outcome_parser.py` ✓
- `src/eldritch_dm/gameplay/reactions.py` ✓ (contains `PLAN-02-LOCK-SEAM` at line 280)
- `src/eldritch_dm/gameplay/monster_driver.py` ✓
- Six test files ✓

Verified commits exist:

- `172799c` ✓ (Task 1)
- `1d2edc8` ✓ (D-A deletion)
- `9c28ea3` ✓ (Task 2)
- `eb4e0f7` ✓ (Task 3)

Verified `_maybe_surface_riposte` deletion:

```
grep -rn "_maybe_surface_riposte" src/eldritch_dm/bot/
# → src/eldritch_dm/bot/dynamic_items.py:46  (module docstring explaining deletion)
# → src/eldritch_dm/bot/dynamic_items.py:673 (class docstring explaining deletion)
# Zero executable references.
```

Test suite: 798 passed, 9 skipped, 0 failed (baseline was 734 → +64 net new tests). lint-imports 7/7 contracts kept. ruff clean on all Plan 01 source paths.

---
*Phase: 05-reactions-self-host-polish*
*Completed: 2026-05-22*
