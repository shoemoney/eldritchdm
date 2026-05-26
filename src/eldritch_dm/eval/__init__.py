"""eldritch_dm.eval — LLM-as-judge tactical scoring (Phase 12).

Public surface:
    JudgeVerdict      — pydantic model with dimension-mean validator (D-73).
    TacticalJudge     — AsyncOpenAI wrapper that scores (scenario, choice) pairs.
    ScenarioEntry     — pydantic schema for one corpus entry.
    load_scenarios    — JSONL streaming loader. Fails loud on corruption.
    load_judge_prompt — versioned prompt loader (D-72 SemVer header).

Locked decisions (CONTEXT D-71..D-82). See 12-CONTEXT.md and 12-01-PLAN.md.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from eldritch_dm.eval.judge import JudgeVerdict, TacticalJudge
from eldritch_dm.eval.judge_prompt import JudgePromptError, load_judge_prompt
from eldritch_dm.eval.scenarios import (
    MonsterStats,
    PCEntry,
    ScenarioEntry,
    ScenarioLoadError,
    load_scenarios,
)

__all__ = [
    "JudgePromptError",
    "JudgeVerdict",
    "MonsterStats",
    "PCEntry",
    "ScenarioEntry",
    "ScenarioLoadError",
    "TacticalJudge",
    "load_judge_prompt",
    "load_scenarios",
]
