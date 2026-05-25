---
phase: 19-streaming-embed
plan: 19-01
subsystem: gameplay/smart_monster_driver
tags: [streaming, embed, llm, smart-driver]
requires: [Phase 10 SmartMonsterDriver, Phase 2 EmbedCoalescer]
provides: [embed_update_callback hook on SmartMonsterDriver]
affects: [Phase 19 Plan 02 (factory + cog wiring)]
key-files:
  created: [tests/gameplay/test_smart_monster_driver_streaming.py]
  modified: [src/eldritch_dm/gameplay/smart_monster_driver.py]
decisions: [D-140, D-141, D-145]
metrics:
  tasks: 3
  duration_minutes: ~25
  date: 2026-05-25
---

# Phase 19 Plan 01: Thinking indicator + EmbedCoalescer integration Summary

## One-liner

Added an optional `embed_update_callback` constructor kwarg to
`SmartMonsterDriver` that fires `"🤔 {monster_name} is sizing up the
party..."` BEFORE the LLM oracle call (and only on the smart path —
suppressed on random routes and cache hits), wrapped in
`contextlib.suppress(Exception)` for D-145 cancellation safety.

## What Changed

- `src/eldritch_dm/gameplay/smart_monster_driver.py`
  - Added `import contextlib`.
  - New optional constructor kwarg
    `embed_update_callback: Callable[[str, str], Awaitable[None]] | None = None`
    stored on `self._embed_update_callback`.
  - In `_pick_target_llm`, after cache-hit short-circuit, before
    `asyncio.wait_for(LLM)`, the callback is invoked with
    `(channel_id, "🤔 {monster_name} is sizing up the party...")` inside
    `contextlib.suppress(Exception)`.
- `tests/gameplay/test_smart_monster_driver_streaming.py` — new test
  suite (9 tests total across both plans; 4 for STREAM-01).

## Decisions Made

- **D-140 honored**: indicator routes through the bot's per-channel
  EmbedCoalescer (Plan 02 supplies the closure that implements the actual
  Discord edit; this plan only defines the contract).
- **D-141 honored**: indicator fires BEFORE the LLM call. The resolved-
  action embed is the bot cog's existing responsibility — this plan adds
  no second callback after the LLM returns.
- **D-145 honored**: callback invocation wrapped in
  `contextlib.suppress(Exception)`. A closed coalescer queue, lost message
  reference, or any other failure cannot crash combat. Same fail-soft
  contract as the Phase 10 D-58 driver-fallback rule.

## Tests

- 4 new tests directly covering STREAM-01:
  - `test_thinking_indicator_fires_on_llm_route`
  - `test_thinking_indicator_no_fire_on_random_route`
  - `test_thinking_indicator_no_fire_on_cache_hit`
  - `test_thinking_indicator_swallows_exception`
- All 41 existing smart_monster_driver + corpus tests pass unchanged.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED
