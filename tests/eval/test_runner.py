"""Eval runner tests (T-12-02-04)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import AsyncOpenAI

from eldritch_dm.eval.judge import TacticalJudge
from eldritch_dm.eval.runner import _NoopSentinel, build_eval_driver, run_scenario
from eldritch_dm.eval.scenarios import ScenarioEntry


def _scenario(intelligence: int = 5) -> ScenarioEntry:
    return ScenarioEntry.model_validate(
        {
            "scenario_id": "brute-001",
            "archetype": "brute",
            "monster_stats": {
                "name": "Ogre",
                "intelligence": intelligence,
                "hp": 59,
                "ac": 11,
                "traits": [],
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
            "rationale": "Ogre picks the closest melee threat.",
        }
    )


def _mock_completion(content: str) -> Any:
    c = MagicMock()
    c.choices = [MagicMock()]
    c.choices[0].message = MagicMock()
    c.choices[0].message.content = content
    c.usage = MagicMock(prompt_tokens=50, completion_tokens=25)
    return c


def _valid_choice_json(target: str) -> str:
    return json.dumps({"target_pc_id": target, "rationale": "closest threat"})


def _valid_verdict_json(overall: float = 0.8) -> str:
    return json.dumps(
        {
            "overall_score": overall,
            "per_dimension": {
                "tactical_intent": overall,
                "meta_knowledge": overall,
                "narrative_fairness": overall,
                "edge_case": overall,
            },
            "reasoning": "reasonable",
            "would_a_veteran_dm_approve": overall >= 0.7,
        }
    )


def _client_with_dispatch(*, target: str, overall: float) -> Any:
    """Return a mock AsyncOpenAI that routes by system-message content.

    The driver's system prompt mentions "tactical combat oracle"; the
    judge's mentions "tactical combat critic". This lets one client back
    both calls in tests (real CLI may pass two different clients).
    """
    async def create(**kwargs):  # type: ignore[no-untyped-def]
        messages = kwargs.get("messages", [])
        system = messages[0].get("content", "") if messages else ""
        if "oracle" in system:
            return _mock_completion(_valid_choice_json(target))
        if "critic" in system:
            return _mock_completion(_valid_verdict_json(overall))
        raise AssertionError(f"unexpected system msg: {system[:80]!r}")

    client = MagicMock(spec=AsyncOpenAI)
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=create)
    return client


# ── _NoopSentinel ────────────────────────────────────────────────────────────


def test_sentinel_raises_on_attr() -> None:
    s = _NoopSentinel("mcp")
    with pytest.raises(RuntimeError, match="unexpectedly accessed"):
        _ = s.some_method


def test_sentinel_raises_on_call() -> None:
    s = _NoopSentinel("mcp")
    with pytest.raises(RuntimeError, match="unexpectedly called"):
        s(1, 2, 3)


# ── build_eval_driver ────────────────────────────────────────────────────────


def test_build_eval_driver_returns_smart_driver() -> None:
    from eldritch_dm.gameplay.smart_monster_driver import SmartMonsterDriver

    client = MagicMock(spec=AsyncOpenAI)
    driver = build_eval_driver(openai_client=client, model="ShoeGPT")
    assert isinstance(driver, SmartMonsterDriver)


def test_build_eval_driver_sentinels_are_hot() -> None:
    """Accessing the orchestrator deps on the eval driver raises."""
    client = MagicMock(spec=AsyncOpenAI)
    driver = build_eval_driver(openai_client=client, model="ShoeGPT")
    with pytest.raises(RuntimeError, match="unexpectedly accessed"):
        _ = driver._mcp.some_attr  # type: ignore[attr-defined]


# ── run_scenario ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_scenario_happy_path() -> None:
    scenario = _scenario(intelligence=15)  # high-INT → LLM route
    client = _client_with_dispatch(target="pc-2", overall=0.85)
    # NOTE: same client for driver + judge — the dispatcher uses model kwarg.
    # Real eval CLI uses two separate clients but the runner doesn't care.
    driver = build_eval_driver(openai_client=client, model="ShoeGPT")
    judge = TacticalJudge(openai_client=client, model="ShoeGPT")
    result = await run_scenario(
        driver=driver, judge=judge, scenario=scenario,
        driver_model="ShoeGPT", judge_model="ShoeGPT",
    )
    assert result.scenario_id == "brute-001"
    assert result.archetype == "brute"
    assert result.driver_target_pc_id == "pc-2"
    assert result.verdict is not None
    assert result.verdict.overall_score == 0.85
    assert result.judge_error is None


@pytest.mark.asyncio
async def test_run_scenario_judge_failure_recorded() -> None:
    scenario = _scenario(intelligence=15)

    async def create(**kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("model") == "driver":
            return _mock_completion(_valid_choice_json("pc-1"))
        # Judge call returns malformed JSON → score returns None.
        return _mock_completion("not valid JSON")

    client = MagicMock(spec=AsyncOpenAI)
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=create)

    driver = build_eval_driver(openai_client=client, model="driver")
    judge = TacticalJudge(openai_client=client, model="judge")
    result = await run_scenario(
        driver=driver, judge=judge, scenario=scenario,
        driver_model="driver", judge_model="judge",
    )
    assert result.driver_target_pc_id == "pc-1"
    assert result.verdict is None
    assert result.judge_error == "judge_returned_none"


@pytest.mark.asyncio
async def test_run_scenario_low_int_takes_random_path() -> None:
    """Low-INT monster -> random route -> driver_target is one of the PCs."""
    scenario = _scenario(intelligence=3)  # <=4 → random
    client = _client_with_dispatch(target="pc-1", overall=0.8)
    driver = build_eval_driver(openai_client=client, model="ShoeGPT")
    judge = TacticalJudge(openai_client=client, model="ShoeGPT")
    result = await run_scenario(
        driver=driver, judge=judge, scenario=scenario,
        driver_model="ShoeGPT", judge_model="ShoeGPT",
    )
    # The driver picked uniformly at random — must be a valid PC.
    assert result.driver_target_pc_id in {"pc-1", "pc-2"}
    assert result.verdict is not None
