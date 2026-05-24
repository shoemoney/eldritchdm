"""
Tests for gameplay/smart_monster_driver.py (Phase 10 Plan 01).

Covers (per plan):
  - MonsterTacticChoice model validation
  - INT-gating routing (`_route_path`)
  - Deterministic mixed-mode seeding for INT in [5,7]
  - LLM oracle success path
  - 1500ms timeout fallback
  - Malformed JSON → fallback
  - Hallucinated target_pc_id → fallback
  - Regex extractor for JSON-in-prose
  - Empty content / refusal → fallback
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.gameplay.smart_monster_driver import (
    MonsterTacticChoice,
    SmartMonsterDriver,
    _extract_monster_int,
    _slim_candidate,
)

# ── Fixtures / helpers ───────────────────────────────────────────────────────


def _make_pcs(n: int = 2) -> list[dict[str, Any]]:
    """Build n synthetic PC dicts."""
    return [
        {
            "character_id": f"pc-{i:03d}",
            "user_id": 1000 + i,
            "player_id": str(1000 + i),
            "name": f"Hero{i}",
            "primary_weapon": "longsword",
            "hp_current": 20 - i,
            "hp_max": 20,
            "ac": 14,
            "active_conditions": [],
        }
        for i in range(n)
    ]


def _make_completion(content: str) -> MagicMock:
    """Build a mock OpenAI completion shaped like SDK output."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


def _make_driver(
    *,
    openai_client: Any,
    random_choice=None,
    llm_timeout_seconds: float = 1.5,
) -> SmartMonsterDriver:
    """Build a SmartMonsterDriver with AsyncMock collaborators."""
    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock()

    def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
        return discord.ui.Button(label="r", custom_id=f"r:{timer_id}:{user_id}")

    def channel_resolver(channel_id: str) -> Any:
        return None

    async def state_provider(channel_id, campaign_name):
        return {"round_number": 1, "pcs": []}

    return SmartMonsterDriver(
        mcp=MagicMock(),
        rate_limiter=rate_limiter,
        pc_classes_repo=MagicMock(),
        riposte_timers_repo=MagicMock(),
        button_factory=button_factory,
        state_provider=state_provider,
        channel_resolver=channel_resolver,
        openai_client=openai_client,
        llm_model="ShoeGPT",
        llm_timeout_seconds=llm_timeout_seconds,
        ttl_seconds=8,
        random_choice=random_choice if random_choice is not None else (lambda xs: xs[0]),
    )


# ── MonsterTacticChoice schema ───────────────────────────────────────────────


def test_choice_required_target_pc_id() -> None:
    c = MonsterTacticChoice.model_validate_json('{"target_pc_id": "pc-001"}')
    assert c.target_pc_id == "pc-001"
    assert c.rationale is None


def test_choice_with_rationale() -> None:
    c = MonsterTacticChoice.model_validate_json(
        '{"target_pc_id": "pc-002", "rationale": "low ac"}'
    )
    assert c.rationale == "low ac"


def test_choice_extra_keys_ignored() -> None:
    # Local models sometimes emit extra fields — we tolerate them.
    c = MonsterTacticChoice.model_validate_json(
        '{"target_pc_id": "pc-003", "confidence": 0.9, "alt": "pc-004"}'
    )
    assert c.target_pc_id == "pc-003"


# ── _slim_candidate / _extract_monster_int ───────────────────────────────────


def test_slim_candidate_omits_class_subclass() -> None:
    pc = {
        "character_id": "pc-9",
        "name": "X",
        "hp_current": 10,
        "hp_max": 20,
        "ac": 15,
        "active_conditions": ["concentrating"],
        "class": "wizard",  # MUST be stripped
        "subclass": "divination",
    }
    slim = _slim_candidate(pc)
    assert "class" not in slim
    assert "subclass" not in slim
    assert slim["id"] == "pc-9"
    assert slim["active_conditions"] == ["concentrating"]


def test_extract_monster_int_top_level() -> None:
    assert _extract_monster_int({"intelligence": 10}) == 10


def test_extract_monster_int_nested_stats() -> None:
    assert _extract_monster_int({"stats": {"intelligence": 6}}) == 6


def test_extract_monster_int_missing_returns_none() -> None:
    assert _extract_monster_int({}) is None


def test_extract_monster_int_malformed_returns_none() -> None:
    assert _extract_monster_int({"intelligence": "garbage"}) is None


# ── _route_path INT-gating (D-53) ────────────────────────────────────────────


def test_route_low_int_is_random() -> None:
    assert SmartMonsterDriver._route_path(
        2, channel_id="c", round_number=1, monster_id="m"
    ) == "random"


def test_route_high_int_is_llm() -> None:
    assert SmartMonsterDriver._route_path(
        10, channel_id="c", round_number=1, monster_id="m"
    ) == "llm"


def test_route_boundary_4_random() -> None:
    assert SmartMonsterDriver._route_path(
        4, channel_id="c", round_number=1, monster_id="m"
    ) == "random"


def test_route_boundary_8_llm() -> None:
    assert SmartMonsterDriver._route_path(
        8, channel_id="c", round_number=1, monster_id="m"
    ) == "llm"


def test_route_mixed_is_deterministic() -> None:
    a = SmartMonsterDriver._route_path(
        6, channel_id="chan-1", round_number=3, monster_id="goblin-7"
    )
    b = SmartMonsterDriver._route_path(
        6, channel_id="chan-1", round_number=3, monster_id="goblin-7"
    )
    assert a == b
    assert a in ("mixed_random", "mixed_llm")


def test_route_none_int_is_random() -> None:
    assert SmartMonsterDriver._route_path(
        None, channel_id="c", round_number=1, monster_id="m"
    ) == "random"


# ── LLM oracle success path ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pick_target_llm_success() -> None:
    pcs = _make_pcs(3)
    target_id = pcs[1]["character_id"]

    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{target_id}", "rationale": "low hp"}}')
    )

    driver = _make_driver(openai_client=openai_client)
    bound = driver._log.bind(test=True)

    chosen = await driver._pick_target_llm(
        pcs,
        channel_id="chan-1",
        round_number=1,
        current_actor={"character_id": "mon-1", "name": "Goblin"},
        bound_log=bound,
    )
    assert chosen is not None
    assert chosen["character_id"] == target_id


# ── Timeout fallback ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pick_target_llm_timeout() -> None:
    pcs = _make_pcs(2)

    async def slow_create(**kwargs):
        await asyncio.sleep(5.0)  # way past 1.5s
        return _make_completion('{"target_pc_id": "pc-000"}')

    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(side_effect=slow_create)

    driver = _make_driver(openai_client=openai_client, llm_timeout_seconds=0.05)
    bound = driver._log.bind()

    chosen = await driver._pick_target_llm(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1"},
        bound_log=bound,
    )
    assert chosen is None


# ── Malformed JSON → fallback ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pick_target_llm_malformed_json() -> None:
    pcs = _make_pcs(2)
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion("not json at all, definitely garbage")
    )

    driver = _make_driver(openai_client=openai_client)
    chosen = await driver._pick_target_llm(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1"},
        bound_log=driver._log.bind(),
    )
    assert chosen is None


# ── Hallucinated target_pc_id → fallback ─────────────────────────────────────


@pytest.mark.asyncio
async def test_pick_target_llm_hallucinated_id() -> None:
    pcs = _make_pcs(2)
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "ghost-of-christmas-past"}')
    )

    driver = _make_driver(openai_client=openai_client)
    chosen = await driver._pick_target_llm(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1"},
        bound_log=driver._log.bind(),
    )
    assert chosen is None  # Membership check fails → random fallback at caller


# ── Regex extractor for JSON-in-prose ────────────────────────────────────────


@pytest.mark.asyncio
async def test_pick_target_llm_regex_extractor() -> None:
    pcs = _make_pcs(3)
    target_id = pcs[2]["character_id"]
    # LLM emits JSON wrapped in prose — strict parse will fail, regex saves us
    content = f'Sure! Here is my choice: "target_pc_id": "{target_id}". Cheers.'

    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion(content)
    )

    driver = _make_driver(openai_client=openai_client)
    chosen = await driver._pick_target_llm(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1"},
        bound_log=driver._log.bind(),
    )
    assert chosen is not None
    assert chosen["character_id"] == target_id


# ── Empty / refusal content → fallback ───────────────────────────────────────


@pytest.mark.asyncio
async def test_pick_target_llm_empty_content() -> None:
    pcs = _make_pcs(2)
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion("")
    )

    driver = _make_driver(openai_client=openai_client)
    chosen = await driver._pick_target_llm(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1"},
        bound_log=driver._log.bind(),
    )
    assert chosen is None


# ── _choose_target integration: routing dispatches correctly ─────────────────


@pytest.mark.asyncio
async def test_choose_target_low_int_skips_llm() -> None:
    pcs = _make_pcs(2)
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )

    driver = _make_driver(openai_client=openai_client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "ogre-1", "intelligence": 2},
    )
    # Random fallback path — LLM should NOT have been called
    assert openai_client.chat.completions.create.call_count == 0
    assert chosen in pcs


@pytest.mark.asyncio
async def test_choose_target_high_int_uses_llm() -> None:
    pcs = _make_pcs(3)
    target_id = pcs[0]["character_id"]
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{target_id}"}}')
    )

    driver = _make_driver(openai_client=openai_client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "lich-1", "intelligence": 18},
    )
    assert openai_client.chat.completions.create.call_count == 1
    assert chosen["character_id"] == target_id


@pytest.mark.asyncio
async def test_choose_target_llm_failure_falls_back_to_random() -> None:
    pcs = _make_pcs(2)
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion("garbage not json")
    )

    fallback = MagicMock(return_value=pcs[1])
    driver = _make_driver(openai_client=openai_client, random_choice=fallback)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "wraith", "intelligence": 14},
    )
    # LLM was tried (and failed), then random_choice picked pc-001
    assert openai_client.chat.completions.create.call_count == 1
    assert fallback.called
    assert chosen == pcs[1]
