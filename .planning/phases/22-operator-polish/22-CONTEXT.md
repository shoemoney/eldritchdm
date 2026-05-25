---
phase: 22-operator-polish
milestone: v1.6
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - OPQOL-01 (hot-reload eligibility.yaml)
  - OPQOL-02 (Discord DM-to-owner on budget breach)
  - OPQOL-03 (Phase 16 schema-poller → Phase 17 invalidation wire)
---

# Phase 22 — Operator quality-of-life bundle (CONTEXT)

## Mission

Close three deferred operator-UX items as one bundled phase:
1. Hot-reload `eligibility.yaml` (Phase 8 deferral)
2. Discord DM-to-owner on budget breach (Phase 13 deferral)
3. Wire Phase 16 schema-version poller to fire Phase 17 character_cache invalidation (v1.5 connect-the-dots)

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-167** | **Hot-reload eligibility.yaml**: extend Phase 8's `EligibilityLoader` with a `reload()` method + an `EligibilityFileWatcher` background task that polls file mtime every 60s. On mtime change → call `reload()`. On bad YAML → keep last-known-good frozenset + log `eldritch.eligibility.reload_failed` event. Fail-soft (Phase 8 D-31 contract preserved). | Pattern proven; just add mtime poll |
| **D-168** | **Watcher lifecycle**: started in bot's `setup_hook` after the initial eligibility load; stopped in `bot.close()` (or via async-task cancellation in shutdown). NO new dependencies (use `asyncio.create_task` + `pathlib.stat().st_mtime`). | Stdlib only |
| **D-169** | **Discord DM-to-owner**: extend Phase 13's `BudgetEvaluator` / degraded-mode triggers with a Discord-DM emitter. New `BudgetOwnerNotifier` class that consumes events `budget_breached`, `degraded_mode_entered`, `degraded_mode_exited` and sends a Discord DM to `DISCORD_OWNER_ID` (env, optional). | Decouples notification mechanism from triggers |
| **D-170** | **DM rate limit**: 1 DM per event-type per hour (in-memory counter, NOT persistent — short interval is fine). If `DISCORD_OWNER_ID` unset → no-op (today's behavior). Bot uses `bot.fetch_user(owner_id).send(msg)` with `discord.Forbidden` swallowed via fail-soft. | Owner doesn't get DM-bombed by flapping degraded-mode |
| **D-171** | **Schema-poller → invalidation wire (OPQOL-03)**: Phase 16's `start_schema_version_poller` already runs every 60s. On detected schema change, it currently wipes ONLY the MCP cache. Extend the callback to ALSO call Phase 17's `CharacterCacheRepo.purge_all()` atomically (transaction or simply sequential — partial-wipe acceptable since they're independent caches). | Composition: existing components, new connection |
| **D-172** | **Test for atomicity (OPQOL-03)**: integration test simulates schema-version-bump → asserts BOTH cache tables are empty after the wipe completes. If one succeeds and the other fails, log `eldritch.cache.partial_wipe` and degrade — but NOT a fatal error. | Honest failure mode disclosure |
| **D-173** | **Module locations**:<br>- Hot-reload: extend `src/eldritch_dm/gameplay/eligibility_loader.py` (add `reload()` + `EligibilityFileWatcher` class)<br>- DM notifier: `src/eldritch_dm/observability/budget_dm.py` (new — sibling of budget_guard.py)<br>- Schema-poller extension: extend `src/eldritch_dm/mcp/cache.py` (callback hook) | Minimal sprawl; reuse existing surfaces |
| **D-174** | **Fail-soft (consistent v1.0 contract)**: ANY failure in: (a) file mtime check, (b) YAML reload, (c) Discord DM send, (d) cache wipe — should log + continue, never raise into the bot's main loop. | Same contract as every other v1.x phase |
| **D-175** | **2 plans**: 22-01 = hot-reload eligibility.yaml + file watcher (OPQOL-01). 22-02 = Discord DM-to-owner notifier + Phase 16↔17 invalidation wire (OPQOL-02 + OPQOL-03). | ROADMAP plans section |

## Success Criteria
1. EligibilityFileWatcher polls every 60s; reloads on mtime change; preserves last-known-good on bad YAML
2. NO bot restart needed for eligibility.yaml changes
3. BudgetOwnerNotifier sends Discord DM on budget_breached / degraded_mode_entered / degraded_mode_exited
4. DISCORD_OWNER_ID unset → zero behavior change (no-op)
5. DM rate limit: 1 per event-type per hour
6. Schema-version change wipes BOTH MCP cache + character cache atomically (or logs partial_wipe and continues)
7. All extensions fail-soft (no exception propagates to bot main loop)
8. ≥15 new tests; ruff + lint-imports clean
9. Zero regression in Phase 8 / Phase 13 / Phase 16 / Phase 17 existing tests
