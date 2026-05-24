---
phase: 10-smart-monsterdriver
milestone: v1.1
generated: 2026-05-24
mode: auto-generated (autonomous-flow, discuss skipped; AI-SPEC already drafted)
source_requirements:
  - COMBAT-13 (smart driver core)
  - COMBAT-14 (adversarial corpus + cache + closure)
companion:
  - 10-AI-SPEC.md (LLM design contract — read in conjunction with this file)
---

# Phase 10 — Smart MonsterDriver (CONTEXT)

## Mission

Replace v1.0's random monster target selection with INT-gated, LLM-routed
targeting via the existing AsyncOpenAI client. The LLM acts as a tactical
oracle; deterministic Python enforces the hard timeout, candidate-ID
validation, per-round cache, and INT-gating. Mechanical honesty is preserved
— LLM never computes math; it just picks among Python-supplied candidates.

## Locked Decisions (autonomous, reconciling AI-SPEC with project stack)

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-50** | **LLM endpoint = local oMLX (`http://localhost:8765/v1`, model `ShoeGPT`)**, NOT hosted OpenAI. Reuse the existing `AsyncOpenAI` client pattern from the bot's narration path. The AI-SPEC's `gpt-4o-mini` reference is illustrative — production uses ShoeGPT. | PROJECT.md constraint: "Inference backend: oMLX exposing OpenAI-compatible API"; ROADMAP "using the existing AsyncOpenAI client, no new MCP dependencies" |
| **D-51** | **Schema enforcement via Pydantic + post-parse validation**, NOT OpenAI's `.beta.chat.completions.parse` strict mode. Local oMLX/ShoeGPT may not honor `response_format=PydanticModel` reliably; use `response_format={"type": "json_object"}` then `MonsterTacticChoice.model_validate_json()`, fall back to a regex extractor only if JSON parse fails. The structured-output fallback parser the project already has remains the safety net. | PROJECT.md: "Structured-output fallback parser remains as a defensive safety net but native tool_calls is the primary path"; conservative interop with local model |
| **D-52** | **MONSTER_DRIVER env var**: values `smart` (default), `random` (escape hatch), `mixed` (per-INT). Read once at orchestrator factory construction, cached on the MonsterDriver instance. | ROADMAP success criterion 1; mirrors `ELDRITCH_ELIGIBILITY_YAML` pattern from Phase 8 |
| **D-53** | **INT thresholds: `INT <= 4` → random; `INT >= 8` → LLM oracle; `INT in [5, 7]` → 50/50 random sample seeded by `(channel_id, round, monster_id)`** for reproducible determinism. | ROADMAP criterion 2; deterministic seed avoids flake in tests |
| **D-54** | **1500ms hard deadline** via `asyncio.wait_for`. On timeout: log structured WARNING (`event=smart_driver_timeout`, `latency_ms=`, `monster_id=`, `channel_id=`, `round=`), fall back to random target. Player-visible embed never blocks > 2s end-to-end. | ROADMAP criterion 3 |
| **D-55** | **`MonsterTacticChoice` pydantic model**: `target_pc_id: str` (required), `rationale: str` (optional, ≤120 chars, NOT exposed to players in v1.1 — for trace logs only). Field validator at the *post-parse* layer rejects `target_pc_id` not in the candidate set; hallucinated IDs trigger fallback (not exception). | ROADMAP criterion 4 + AI-SPEC §1b "Meta-knowledge Guardrails" |
| **D-56** | **Per-round cache**: `dict[tuple[channel_id, round, monster_id], MonsterTacticChoice]` on the driver instance; expires when round advances. Same `(c, r, m)` returns cached choice — assert in test that mock LLM called once across two reads. | ROADMAP criterion 5 |
| **D-57** | **Candidate slimming**: pass only `id`, `name`, `hp_current`, `hp_max`, `ac`, `active_conditions[]` to the LLM. NEVER pass class/subclass (avoids meta-knowledge violation per AI-SPEC Tactical Intent dimension). | AI-SPEC §1b "Meta-knowledge Guardrails" + Context Window Strategy |
| **D-58** | **Fail-soft**: ANY exception in the smart path (network, schema, validator, timeout) → log + fall back to random. NEVER propagate to combat orchestrator. The whole point is monsters become smarter, not that combat breaks. | AI-SPEC §6 Error Handling |
| **D-59** | **Telemetry (v1.1 lite)**: structlog with bound `monster_id`, `channel_id`, `round`, `path=smart|random|cache`, `latency_ms`. Defer Arize Phoenix / OpenTelemetry (AI-SPEC §7) to v1.2 — out of v1.1 scope. | Roadmap goal "no new MCP dependencies" extends to no new observability platform deps in v1.1 |
| **D-60** | **Module shape**: `src/eldritch_dm/gameplay/smart_monster_driver.py` exports `SmartMonsterDriver` class (sibling of v1.0's `MonsterDriver`); a `make_monster_driver(env_override: str | None = None) -> MonsterDriverProtocol` factory in `gameplay/monster_driver_factory.py` reads MONSTER_DRIVER and instantiates the right class. Tests can inject `env_override=` directly. | ROADMAP criterion 1; testability |
| **D-61** | **2 plans (matches ROADMAP)**: Plan 01 — dm20 contract verification + smart driver core (INT-gating, LLM oracle, pydantic validation, 1500ms timeout, random fallback). Plan 02 — adversarial corpus (15 scenarios) + per-round cache + MONSTER_DRIVER env-var integration + Phase 10 closure (REQUIREMENTS [x], SUMMARY, VERIFICATION). | ROADMAP plans section |

## Implementation Sketch

**Plan 01 (10-01-PLAN.md) — Core smart driver:**
1. Verify whether `dm20__get_claudmaster_session_state` returns `next_target` (research open question per ROADMAP) — if YES, MonsterDriver subscribes to it; if NO, MonsterDriver computes locally
2. Implement `SmartMonsterDriver` class with `_pick_target()` mirroring `MonsterDriver`'s signature
3. Pydantic model `MonsterTacticChoice` + post-parse validator
4. 1500ms `asyncio.wait_for` with structured-log fallback
5. INT-gating + factory (D-52, D-53, D-60)

**Plan 02 (10-02-PLAN.md) — Corpus + cache + closure:**
1. Per-round cache (D-56) with test
2. 15+ adversarial corpus tests:
   - malformed JSON
   - hallucinated target_pc_id
   - timeout > 1500ms
   - empty candidate list
   - INT=2 (sub-INT bypass)
   - INT=12 with downed PC (anti-griefing — should NOT focus-fire)
   - INT=18 with concentration holder (should target high-impact)
   - cover/invisibility (RAW)
   - refusal (`message.refusal` populated path)
   - 429 rate limit handling
   - duplicate (c, r, m) cache hit
   - mid-round PC death (candidates change between calls)
   - cross-channel cache isolation
   - mixed mode INT=5 seeded determinism
   - recursive decision (monster targets itself or summon)
3. MONSTER_DRIVER env var wired through orchestrator factory
4. Closure artifacts: REQUIREMENTS COMBAT-13/14 ticked, 10-01/10-02-SUMMARY.md, 10-VERIFICATION.md

## Success Criteria (from ROADMAP)

1. New `src/eldritch_dm/gameplay/smart_monster_driver.py` replaces `monster_driver.py`'s random `_pick_target`; MONSTER_DRIVER env var wired
2. INT-gating verified (≤4 random, ≥8 LLM, 5-7 mixed)
3. 1500ms hard deadline + structured-log fallback verified
4. Pydantic post-parse validation: hallucinated IDs → fallback, NOT exception
5. Per-round cache: (channel_id, round, monster_id) returns cached value; mock asserted called once
6. 15+ adversarial corpus tests pass
7. Full v1.1 suite green; pc_classes populated by Phase 9

## Deferred (post-v1.1)

- Arize Phoenix observability (AI-SPEC §7) — out of v1.1 scope
- LLM-as-judge tactical scoring rubric (AI-SPEC §5 Evaluation) — needed for v1.2 quality flywheel
- Streaming output for player-visible "monster is thinking" embed — UX nicety
- Multi-target / AOE selection (current scope: single-target choice)
- Cross-round memory (monsters remembering previous round's actions) — would need session-level state
