---
phase: 19-streaming-embed
plan: 19-02
subsystem: config + gameplay/monster_driver_factory + bot/bot
tags: [streaming, embed, settings, opt-out, fail-soft]
requires: [19-01 (SmartMonsterDriver hook)]
provides: [STREAM_ENABLED setting, bot-level closure routing thinking embed to CombatCog coalescer]
affects: [bot.py setup_hook, .env.example, REQUIREMENTS.md]
key-files:
  created: []
  modified:
    - src/eldritch_dm/config/__init__.py
    - src/eldritch_dm/gameplay/monster_driver_factory.py
    - src/eldritch_dm/bot/bot.py
    - .env.example
    - tests/gameplay/test_smart_monster_driver_streaming.py
    - .planning/REQUIREMENTS.md
decisions: [D-142, D-143, D-145, D-148]
metrics:
  tasks: 6
  duration_minutes: ~25
  date: 2026-05-25
requirements_completed:
  - STREAM-02
  - STREAM-03
---

# Phase 19 Plan 02: Hidden fallback + STREAM_ENABLED opt-out + cog wiring

## One-liner

Added `Settings.stream_enabled` (default True, env-gated `STREAM_ENABLED`),
forwarded `embed_update_callback` through the monster_driver factory,
wired a `bot.py` closure that routes the thinking indicator through
`CombatCog._coalescers` per channel, and verified via tests that the
fallback path (timeout / hallucinated id) never emits "fallback"-style
wording to players.

## What Changed

- `src/eldritch_dm/config/__init__.py` — `stream_enabled: bool = Field(default=True, alias="STREAM_ENABLED", ...)`.
- `src/eldritch_dm/gameplay/monster_driver_factory.py` — added
  `"embed_update_callback"` to the kwargs popped before constructing
  `MonsterDriver` in `"random"` mode. Smart/mixed receive it via
  `**driver_kwargs`.
- `src/eldritch_dm/bot/bot.py`:
  - Added `import contextlib` and `EmbedColor` import.
  - Constructed `_emit_thinking_indicator(channel_id, text)` closure that
    looks up the `CombatCog._coalescers[channel_id]` instance and posts a
    `discord.Embed(title="⚔️ Combat", description=text, color=EmbedColor.COMBAT)`
    via the coalescer's `update(embed)` API. Closure wrapped in
    `contextlib.suppress(Exception)` (D-145).
  - When `settings.stream_enabled` is false, passes `embed_update_callback=None`
    to the factory (STREAM-03 opt-out).
- `.env.example` — documented `STREAM_ENABLED` with operator opt-out rationale.
- `tests/gameplay/test_smart_monster_driver_streaming.py` — 5 additional
  tests covering STREAM-02 and STREAM-03 (callback=None silent path,
  factory forwarding, random-mode kwarg popping, timeout fallback no leak,
  hallucinated-id fallback no leak).

## Decisions Made

- **D-142 honored**: tests assert that on TimeoutError + hallucinated-id
  fallback the callback is invoked exactly once — with the "sizing up"
  text only. Verified absence of `fallback`, `failed`, `ai failed`,
  `error` substrings in the player-visible text. The structured log
  (`smart_driver_timeout`, `smart_driver_invalid_choice`) is still emitted
  for operator observability (unchanged from Phase 10).
- **D-143 honored**: `STREAM_ENABLED=false` ⇒ bot passes `None`
  callback ⇒ driver stays silent (`v1.5 behavior`).
- **D-145 honored**: bot-level closure wrapped in
  `contextlib.suppress(Exception)`, layered on top of the driver's own
  `contextlib.suppress` from Plan 01. Defense in depth.
- **D-148 honored**: 2-plan split as planned.

## Tests

- 5 new tests in this plan + 4 from Plan 01 = **9 streaming tests total**
  (exceeds the ≥8 bar).
- `pytest tests/gameplay/` → **285 passed**. Zero regression in:
  - 41 smart_monster_driver + corpus tests
  - all coalescer tests
  - all config tests

## Architectural Notes

- The `bot.py` closure binds at `setup_hook` time and captures `self` via
  `bot_self` (closure capture). It looks up the cog lazily on every call
  so a cog reload doesn't strand a stale reference.
- The closure is intentionally tolerant: missing cog, missing coalescer,
  or any coalescer/Discord error degrades silently to "no indicator" —
  combat continues to resolve via the deterministic Python path.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED
