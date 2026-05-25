---
phase: 20-aoe-targeting
milestone: v1.6
generated: 2026-05-25
mode: auto-generated (autonomous-flow)
source_requirements:
  - AOE-01 (MonsterTacticChoice target_pc_ids)
  - AOE-02 (system prompt + available_actions context)
  - AOE-03 (10-scenario adversarial corpus)
---

# Phase 20 — AOE / multi-target tactic selection (CONTEXT)

## Mission

Extend SmartMonsterDriver from single-target to multi-target tactics (AOE spells, breath weapons, cone attacks, multi-attack). Preserve v1.1 fail-soft + meta-knowledge guards. Add 10 corpus scenarios.

## Locked Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| **D-149** | **MonsterTacticChoice gains `target_pc_ids: list[str]`** (NEW). Existing `target_pc_id: str` field kept as a derived property `@property def target_pc_id(self) -> str: return self.target_pc_ids[0]` for backwards compatibility with existing single-target call sites. ALL ids in the list must be in the candidate set (validator); hallucination → fallback. | API additive; old call sites work unchanged |
| **D-150** | **`tactic_kind: Literal["single", "aoe", "multi_attack", "breath", "cone"]`** new field. Tells the bot/embed how to render the resolution. Validator enforces `tactic_kind == "single"` → `len(target_pc_ids) == 1`; AOE/breath/cone → 2..len(candidates); multi_attack → 1..N (single monster hits multiple targets). | Constraints encoded in the model |
| **D-151** | **Slimmed candidate context gains `available_actions: list[ActionDescriptor]`** where `ActionDescriptor = {name, kind: Literal["single", "aoe", ...], range_ft, save_dc: int | None}`. Monster's actions surfaced to LLM — but range_ft is included for tactical reasoning, NOT for HP/AC leakage. | Meta-knowledge guard preserved |
| **D-152** | **System prompt addendum** at `src/eldritch_dm/gameplay/prompts/aoe_addendum.txt` (versioned like Phase 12's judge prompt — SemVer header). Explains AOE scoring heuristic: "prefer single-target on lone PC; prefer AOE when 2+ PCs are within range_ft." | Versioned prompt; reproducible |
| **D-153** | **Fail-soft same as v1.1 D-58**: any exception (timeout, schema invalid, hallucinated id, empty list) → fallback to RANDOM SINGLE-TARGET (existing path). NEVER expose exception to combat orchestrator. | Combat continues unconditionally |
| **D-154** | **10 corpus scenarios** added to existing `tests/gameplay/test_monster_driver_corpus.py`: 3 cluster-AOE-optimal (e.g., dragon with breath, party clustered), 3 anti-cluster-AOE (PCs spread out, single-target preferred), 2 mixed-tactic (multi-attack on lone PC), 2 adversarial (LLM proposes AOE with hallucinated id, AOE with 0 ids). Total corpus = 26 (was 16). | Coverage of new behavior |
| **D-155** | **Existing single-target call paths unchanged.** Battle cogs that use `choice.target_pc_id` get the first element via the @property. Tests verify backwards compat — the 51 existing smart_monster_driver tests + 16 corpus + 10 factory MUST still pass. | Zero regression |
| **D-156** | **2 plans**: 20-01 = MonsterTacticChoice schema extension + validator. 20-02 = prompt + ActionDescriptor + 10-scenario corpus + integration test. | ROADMAP plans section |

## Success Criteria
1. MonsterTacticChoice has target_pc_ids (validator) + tactic_kind (5 literals)
2. Backwards compat: choice.target_pc_id property returns first element
3. ActionDescriptor schema; available_actions field in slimmed context
4. Versioned aoe_addendum.txt at src/eldritch_dm/gameplay/prompts/
5. ≥10 new corpus scenarios; total corpus ≥26
6. Fail-soft on any failure → random single-target
7. Existing 51+16+10 tests still pass (zero regression)
8. ≥15 new tests; ruff + lint-imports clean
