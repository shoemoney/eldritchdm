"""TacticalJudge AsyncOpenAI wrapper tests (T-12-01-04).

Uses ``MagicMock(spec=AsyncOpenAI)`` to mock the OpenAI client — no real
LLM calls. The judge is fail-soft (returns ``None`` on any error), so
each test exercises one error path.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import AsyncOpenAI

from eldritch_dm.eval.judge import JudgeVerdict, TacticalJudge
from eldritch_dm.eval.scenarios import ScenarioEntry


def _scenario() -> ScenarioEntry:
    return ScenarioEntry.model_validate(
        {
            "scenario_id": "brute-001",
            "archetype": "brute",
            "monster_stats": {
                "name": "Ogre",
                "intelligence": 5,
                "hp": 59,
                "ac": 11,
                "traits": ["brutish"],
            },
            "pc_list": [
                {
                    "character_id": "pc-1",
                    "name": "Aria",
                    "hp_current": 30,
                    "hp_max": 30,
                    "ac": 16,
                    "active_conditions": [],
                },
                {
                    "character_id": "pc-2",
                    "name": "Borin",
                    "hp_current": 25,
                    "hp_max": 25,
                    "ac": 18,
                    "active_conditions": [],
                },
            ],
            "environment": "dungeon corridor",
            "expected_target_pool": ["pc-2"],
            "expected_avoidance": [],
            "rationale": "Ogre INT 5 picks the closest melee threat.",
        }
    )


def _valid_verdict_json(*, overall: float = 0.75) -> str:
    return json.dumps(
        {
            "overall_score": overall,
            "per_dimension": {
                "tactical_intent": overall,
                "meta_knowledge": overall,
                "narrative_fairness": overall,
                "edge_case": overall,
            },
            "reasoning": "Reasonable choice.",
            "would_a_veteran_dm_approve": overall >= 0.7,
        }
    )


def _mock_completion(content: str, *, usage_in: int = 50, usage_out: int = 25) -> Any:
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message = MagicMock()
    completion.choices[0].message.content = content
    completion.usage = MagicMock(prompt_tokens=usage_in, completion_tokens=usage_out)
    return completion


def _mock_client(completion: Any) -> Any:
    client = MagicMock(spec=AsyncOpenAI)
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=completion)
    return client


@pytest.mark.asyncio
async def test_judge_happy_path() -> None:
    client = _mock_client(_mock_completion(_valid_verdict_json(overall=0.8)))
    judge = TacticalJudge(openai_client=client, model="ShoeGPT")
    verdict = await judge.score(
        _scenario(),
        driver_choice_pc_id="pc-2",
        driver_rationale="Closest melee threat.",
        driver_model="ShoeGPT",
    )
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.overall_score == 0.8
    assert verdict.would_a_veteran_dm_approve is True
    assert judge.prompt_version == "1.0.0"


@pytest.mark.asyncio
async def test_judge_timeout_returns_none() -> None:
    client = MagicMock(spec=AsyncOpenAI)
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=TimeoutError())
    judge = TacticalJudge(openai_client=client, model="ShoeGPT", timeout_seconds=0.01)
    assert await judge.score(
        _scenario(), driver_choice_pc_id="pc-2", driver_rationale=None
    ) is None


@pytest.mark.asyncio
async def test_judge_malformed_json_returns_none() -> None:
    client = _mock_client(_mock_completion("This is not JSON at all"))
    judge = TacticalJudge(openai_client=client)
    assert await judge.score(
        _scenario(), driver_choice_pc_id="pc-2", driver_rationale=None
    ) is None


@pytest.mark.asyncio
async def test_judge_dimension_mean_violation_returns_none() -> None:
    bad = json.dumps(
        {
            "overall_score": 0.5,
            "per_dimension": {
                "tactical_intent": 0.9,
                "meta_knowledge": 0.9,
                "narrative_fairness": 0.9,
                "edge_case": 0.9,
            },
            "reasoning": "bad math",
            "would_a_veteran_dm_approve": True,
        }
    )
    client = _mock_client(_mock_completion(bad))
    judge = TacticalJudge(openai_client=client)
    assert await judge.score(
        _scenario(), driver_choice_pc_id="pc-2", driver_rationale=None
    ) is None


@pytest.mark.asyncio
async def test_judge_missing_dimension_returns_none() -> None:
    bad = json.dumps(
        {
            "overall_score": 0.75,
            "per_dimension": {
                "tactical_intent": 0.75,
                "meta_knowledge": 0.75,
                "narrative_fairness": 0.75,
            },
            "reasoning": "missing edge_case",
            "would_a_veteran_dm_approve": True,
        }
    )
    client = _mock_client(_mock_completion(bad))
    judge = TacticalJudge(openai_client=client)
    assert await judge.score(
        _scenario(), driver_choice_pc_id="pc-2", driver_rationale=None
    ) is None


@pytest.mark.asyncio
async def test_judge_refusal_empty_content_returns_none() -> None:
    client = _mock_client(_mock_completion(""))
    judge = TacticalJudge(openai_client=client)
    assert await judge.score(
        _scenario(), driver_choice_pc_id="pc-2", driver_rationale=None
    ) is None


@pytest.mark.asyncio
async def test_judge_none_content_returns_none() -> None:
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message = MagicMock()
    completion.choices[0].message.content = None
    completion.usage = MagicMock(prompt_tokens=10, completion_tokens=0)
    client = _mock_client(completion)
    judge = TacticalJudge(openai_client=client)
    assert await judge.score(
        _scenario(), driver_choice_pc_id="pc-2", driver_rationale=None
    ) is None


@pytest.mark.asyncio
async def test_judge_usage_none_defensive() -> None:
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message = MagicMock()
    completion.choices[0].message.content = _valid_verdict_json(overall=0.75)
    completion.usage = None  # MLX/ShoeGPT may omit usage
    client = _mock_client(completion)
    judge = TacticalJudge(openai_client=client)
    verdict = await judge.score(
        _scenario(), driver_choice_pc_id="pc-2", driver_rationale=None
    )
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.overall_score == 0.75


@pytest.mark.asyncio
async def test_judge_generic_exception_returns_none() -> None:
    client = MagicMock(spec=AsyncOpenAI)
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("network is on fire")
    )
    judge = TacticalJudge(openai_client=client)
    assert await judge.score(
        _scenario(), driver_choice_pc_id="pc-2", driver_rationale=None
    ) is None
