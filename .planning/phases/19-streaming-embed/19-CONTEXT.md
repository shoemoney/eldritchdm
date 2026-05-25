---
phase: 19-streaming-embed
milestone: v1.6
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - STREAM-01 (thinking embed during oracle call)
  - STREAM-02 (hidden fallback transition)
  - STREAM-03 (STREAM_ENABLED opt-out)
---

# Phase 19 — Streaming "monster is thinking" embed (CONTEXT)

## Mission

When SmartMonsterDriver invokes the LLM oracle (up to 1500ms per v1.1 D-54), update the combat embed with a brief "🤔 The {monster_name} is sizing up the party..." indicator. The current behavior is silent: players see nothing until the resolved target appears. This adds intentional UX visibility for the smart-driver code path without exposing fallback events.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-140** | **Thinking indicator goes through Phase 2's `EmbedCoalescer`** (≤1 edit/sec/message rate limit). The indicator is a single embed edit with a `🤔 {monster_name} is sizing up the party...` line appended. NO new Discord API rate-limit code. | Phase 2 already solved this — reuse |
| **D-141** | **Indicator fires BEFORE oracle call**, completes AFTER (transitions to resolved-target embed). Operator's user-visible budget is the existing 2s embed-stall (Phase 4 invariant) — 1500ms LLM + ~300ms coalescer overhead fits within it. | Time budget unchanged |
| **D-142** | **Hidden fallback transition (STREAM-02)**: when SmartMonsterDriver falls back to random (timeout/refusal/hallucination), the embed transitions DIRECTLY from "thinking" to "resolved target" with NO intermediate "fallback" message visible to players. The structured log (Phase 7 `eldritch.smart_driver_fallback` event) is still emitted for operators. Players see clean combat; operators see what happened. | Player UX preserves immersion; operator observability via separate channel |
| **D-143** | **STREAM_ENABLED env (default true)**. When false, no indicator — embed shows only the resolved target (v1.5 behavior). Opt-out for operators who find the thinking indicator distracting (5-7 INT mixed-mode monsters trigger it 50% of the time — could feel noisy). | Operator control |
| **D-144** | **NO new dependencies**. Pure Discord embed edit calls through the existing `EmbedCoalescer.update()` path. The "thinking" line is a localized template string in `gameplay/monster_driver_factory.py` (or a sibling helper). | Scope discipline |
| **D-145** | **Cancellation safety**: if the LLM call's wait_for() raises TimeoutError, the embed-update path MUST not raise — wrap in `contextlib.suppress(Exception)` around the embed call (the coalescer's queue may have closed in shutdown scenarios). Combat continues unconditionally. | Same fail-soft as v1.1 D-58 |
| **D-146** | **Test surface**: 8+ tests covering (a) indicator fires on smart-path call, (b) indicator hidden on STREAM_ENABLED=false, (c) fallback transitions cleanly without "fallback" wording, (d) coalescer rate limit honored, (e) cancellation-safe path. Use existing `EmbedCoalescer` mock from Phase 2 tests. | Coverage of the 3 reqs |
| **D-147** | **Module location**: extension to `src/eldritch_dm/gameplay/smart_monster_driver.py` adding an `embed_update_callback` constructor kwarg + helper in `src/eldritch_dm/bot/cogs/combat.py` to bind the coalescer. Tests at `tests/gameplay/test_smart_monster_driver_streaming.py`. | Single-purpose extension; bot cog owns the coalescer binding |
| **D-148** | **2 plans**: 19-01 = thinking indicator + coalescer integration (STREAM-01). 19-02 = hidden fallback transition + STREAM_ENABLED opt-out (STREAM-02, STREAM-03). | ROADMAP plans section |

## Implementation Sketch

**Plan 01:** SmartMonsterDriver takes optional `embed_update_callback: Callable[[str], Awaitable[None]] | None = None`. Before LLM call, if callback set + STREAM_ENABLED, calls `await callback(f"🤔 {monster.name} is sizing up the party...")`. After call (regardless of outcome), no further callback — the bot cog's existing resolved-action embed update fires. Tests: callback fires with correct string; STREAM_ENABLED=false suppresses it.

**Plan 02:** Bot cog binds coalescer to driver factory: `make_monster_driver(env_override=..., embed_update_callback=coalescer.update_message)`. Fallback path verified via existing fail-soft tests (Phase 10 corpus already covers timeout/hallucination — extend to check embed state). Add `STREAM_ENABLED` to Settings (env-gated, default true).

## Success Criteria
1. Indicator appears in combat embed during smart-driver oracle call
2. Indicator does NOT appear when STREAM_ENABLED=false
3. Fallback transitions silently — no "AI failed" / "fallback" wording visible to players
4. Coalescer rate limit honored (Phase 2 invariant preserved)
5. Cancellation-safe (embed update wrapped in `contextlib.suppress`)
6. ≥8 new tests; ruff + lint-imports clean
7. Existing 51 smart_monster_driver tests + 16 corpus tests still pass
