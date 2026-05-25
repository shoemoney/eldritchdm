---
phase: 23-cog-wiring
status: PARTIAL CLOSURE (Option B of halt-report)
generated: 2026-05-25
shipped:
  - WIRE-02 (closed by Plan 23-01)
  - WIRE-03 (closed by Plan 23-02)
deferred:
  - WIRE-01 (blocked on dm20 event surface — see 23-HALT-REPORT.md)
---

# Phase 23 Verification — Partial Closure

## Scope of this phase

Phase 23 originally bundled three honest-gap requirements: WIRE-01 (cog-side
`observe_hit`), WIRE-02 (`/end_game → purge_session`), and WIRE-03 (AOE
addendum live injection).

The prior executor halted with `23-HALT-REPORT.md` after determining that
WIRE-01 (and the concentration half originally inferred from D-177) requires
a structured `(attacker, target, damage)` event surface from dm20 that
**does not exist** — dm20 returns markdown narration only, and parsing damage
from LLM text would violate the mechanical-honesty integrity rule (D-176 /
EldritchDM core constraint).

The user chose **Option B** of the halt-report: execute the unblocked
WIRE-02 and WIRE-03; defer WIRE-01 with explicit annotation. This document
records the verification of what shipped and the rationale for what did not.

## Shipped and verified

### WIRE-02 — `/end_game` slash command (Plan 23-01)

- `EldritchBot.monster_memory_registry` exposed at bot scope; threaded into
  `make_monster_driver(...)` so the lobby cog and smart driver share one
  instance.
- `LobbyCog.end_game` runs the D-178 sequence (defer → DM gate → fetch session →
  best-effort dm20 close → best-effort `purge_session` → LOBBY upsert →
  ephemeral 🛑 embed) with full D-179 fail-soft.
- **7 new tests** in `TestEndGame` (defers-first, happy path, no session,
  dm20-close-fails, no-registry-attr, permission-denied, purge-raises).
- All four side-effects (mcp call, registry purge, state upsert, embed send)
  asserted in the happy-path test.

### WIRE-03 — AOE addendum conditional injection (Plan 23-02)

- `aoe_addendum.get_addendum_version()` helper added (D-182).
- `_pick_target_llm` predicate tightened to
  `aoe_count = sum(1 for a in actions if a.kind in {"aoe","cone","breath"}) >= 2`
  (D-180). Loose pre-existing predicate replaced.
- `span.set_attribute("eldritch.aoe.addendum_version", ...)` stamped on the
  OUTER decision span when (and only when) the addendum is injected (D-181).
- **7 new tests** in `test_monster_driver_corpus.py` covering all four
  predicate/attribute combinations + loader-failure fail-soft + helper
  surface contracts.
- 1 pre-existing corpus test (`test_aoe_addendum_injected_when_available_actions_present`)
  updated from single-AOE-action to two-AOE-actions to align with D-180.

## Deferred and annotated

### WIRE-01 — `MonsterMemoryRegistry.observe_hit` cog-side wiring

**Blocker:** `src/eldritch_dm/mcp/tools.py:283` documents that
`dm20__combat_action` "returns formatted text narration — NOT JSON. Re-fetch
get_game_state for HP." The downstream
`src/eldritch_dm/gameplay/combat_outcome_parser.py` extracts only
`HIT / CRITICAL / MISS / NATURAL_ONE` from the markdown header — never a
damage integer (Phase 5 design decision per D-176).

The cog-callback path (`PartyModeOrchestrator.register_resolution_callback`,
`src/eldritch_dm/gameplay/party_mode.py:141`) fires PRE-resolution with the
queued `player_intent` dict — not a post-resolution damage event. Existing
`on_resolved_combat` tests pass opaque sentinels (`{"type":"action_resolved"}`),
proving no production code currently reads damage from the action dict — because
none is there.

**Why we did NOT work around it:** Each candidate workaround violates a
constraint:
1. Parsing damage from narration text → violates D-176 ("NEVER invent/infer
   damage") and the EldritchDM mechanical-honesty contract (LLM never touches
   the math).
2. Diffing `get_game_state` HP between rounds and attributing to the current
   actor → fragile under AOE / riposte / reaction-damage / environmental
   damage; requires inventing an event boundary the cog does not currently
   have.
3. Adding a fabricated damage event in `PartyModeOrchestrator` → would require
   the orchestrator to compute or invent damage values, which violates D-176
   and is out-of-scope (dm20 lives in another repo).

**Resolution path:** Re-open WIRE-01 (and the concentration observation half
originally inferred from D-177) when dm20 ships a structured post-resolve
event surface — e.g. a `(attacker_id, target_id, damage_int, hit_kind)` tuple
emitted as a callback distinct from the queued player_intent.

**Annotation:** `.planning/REQUIREMENTS.md` line 13 carries the deferred-marker
with a direct link to this file and `23-HALT-REPORT.md`.

## Cross-reference

- Halt-report: `.planning/phases/23-cog-wiring/23-HALT-REPORT.md`
- Plan 23-01: `.planning/phases/23-cog-wiring/23-01-PLAN.md`
- Plan 23-02: `.planning/phases/23-cog-wiring/23-02-PLAN.md`
- Plan 23-01 summary: `.planning/phases/23-cog-wiring/23-01-SUMMARY.md`
- Plan 23-02 summary: `.planning/phases/23-cog-wiring/23-02-SUMMARY.md`

## Test surface summary

| Suite | Result | Notes |
|---|---|---|
| `tests/bot/cogs/` | 226 passed | 7 new in `TestEndGame` |
| `tests/gameplay/` | 419 passed | 7 new in `test_monster_driver_corpus.py`, 1 updated |
| `tests/observability/` | 25 passed | no changes |
| **Combined** | **670 passed** | zero regression |
| `ruff check src/ tests/` | clean | — |

## State touched / NOT touched

- ✅ Touched: `src/`, `tests/`, `.planning/REQUIREMENTS.md`,
  `.planning/phases/23-cog-wiring/*.md`.
- ❌ NOT touched: `.planning/STATE.md`, `.planning/ROADMAP.md` (per task spec —
  orchestrator will handle status-page updates after verifying this partial
  closure).

## Recommendation

Phase 23 can be marked **partially complete** in ROADMAP / STATE: ship the
two closed requirements (WIRE-02, WIRE-03) and carry WIRE-01 forward as a
v1.8+ requirement gated on the dm20 event-surface dependency.
