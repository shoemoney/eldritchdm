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
from pydantic import ValidationError

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


# ── MonsterTacticChoice AOE/multi-target schema (Phase 20 / D-149..D-150) ────


def test_choice_accepts_new_shape_target_pc_ids() -> None:
    c = MonsterTacticChoice.model_validate_json(
        '{"target_pc_ids": ["pc-1", "pc-2"], "tactic_kind": "aoe"}'
    )
    assert c.target_pc_ids == ["pc-1", "pc-2"]
    assert c.tactic_kind == "aoe"
    # Backwards-compat property returns the first id.
    assert c.target_pc_id == "pc-1"


def test_choice_legacy_target_pc_id_still_works() -> None:
    c = MonsterTacticChoice.model_validate_json('{"target_pc_id": "pc-1"}')
    assert c.target_pc_ids == ["pc-1"]
    assert c.tactic_kind == "single"
    assert c.target_pc_id == "pc-1"


def test_choice_kwargs_legacy_target_pc_id_still_works() -> None:
    # The Phase 10 regex-extractor path constructs via kwargs (line 459 prior
    # to Phase 20). Legacy coercion must accept this shape.
    c = MonsterTacticChoice(target_pc_id="pc-1")  # type: ignore[call-arg]
    assert c.target_pc_ids == ["pc-1"]
    assert c.tactic_kind == "single"


def test_choice_single_kind_rejects_multi_ids() -> None:
    with pytest.raises(ValidationError):
        MonsterTacticChoice.model_validate_json(
            '{"target_pc_ids": ["a", "b"], "tactic_kind": "single"}'
        )


def test_choice_aoe_kind_rejects_single_id() -> None:
    with pytest.raises(ValidationError):
        MonsterTacticChoice.model_validate_json(
            '{"target_pc_ids": ["a"], "tactic_kind": "aoe"}'
        )


def test_choice_breath_kind_requires_two_or_more() -> None:
    with pytest.raises(ValidationError):
        MonsterTacticChoice.model_validate_json(
            '{"target_pc_ids": ["a"], "tactic_kind": "breath"}'
        )


def test_choice_cone_kind_requires_two_or_more() -> None:
    with pytest.raises(ValidationError):
        MonsterTacticChoice.model_validate_json(
            '{"target_pc_ids": ["a"], "tactic_kind": "cone"}'
        )


def test_choice_multi_attack_accepts_single_id() -> None:
    # Single-monster multi-attack pile-on-one-PC is RAW-legal.
    c = MonsterTacticChoice.model_validate_json(
        '{"target_pc_ids": ["a"], "tactic_kind": "multi_attack"}'
    )
    assert c.tactic_kind == "multi_attack"
    assert c.target_pc_ids == ["a"]


def test_choice_multi_attack_accepts_two_ids() -> None:
    # Cleave-style multi-attack across two adjacent PCs.
    c = MonsterTacticChoice.model_validate_json(
        '{"target_pc_ids": ["a", "b"], "tactic_kind": "multi_attack"}'
    )
    assert c.target_pc_ids == ["a", "b"]


def test_choice_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        MonsterTacticChoice.model_validate_json(
            '{"target_pc_ids": ["a", "a"], "tactic_kind": "aoe"}'
        )


def test_choice_empty_list_rejected() -> None:
    with pytest.raises(ValidationError):
        MonsterTacticChoice.model_validate_json(
            '{"target_pc_ids": [], "tactic_kind": "aoe"}'
        )


def test_choice_property_returns_first_element() -> None:
    c = MonsterTacticChoice.model_validate_json(
        '{"target_pc_ids": ["x", "y", "z"], "tactic_kind": "aoe"}'
    )
    assert c.target_pc_id == "x"


def test_choice_tactic_kind_invalid_literal_rejected() -> None:
    with pytest.raises(ValidationError):
        MonsterTacticChoice.model_validate_json(
            '{"target_pc_ids": ["a", "b"], "tactic_kind": "fireball"}'
        )


def test_choice_new_shape_wins_when_both_keys_present() -> None:
    # If LLM dual-emits both, the new shape wins; legacy key dropped.
    c = MonsterTacticChoice.model_validate_json(
        '{"target_pc_id": "ignored", "target_pc_ids": ["real"], "tactic_kind": "single"}'
    )
    assert c.target_pc_ids == ["real"]


# ── LLM oracle AOE integration (Phase 20 / regex extractor + fallback) ──────


@pytest.mark.asyncio
async def test_pick_target_llm_new_aoe_shape_success() -> None:
    pcs = _make_pcs(3)
    aoe_ids = [pcs[0]["character_id"], pcs[1]["character_id"]]
    content = (
        '{"target_pc_ids": ["' + aoe_ids[0] + '", "' + aoe_ids[1] + '"], '
        '"tactic_kind": "aoe"}'
    )
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion(content)
    )
    driver = _make_driver(openai_client=openai_client)
    chosen = await driver._pick_target_llm(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "dragon", "name": "Adult Red"},
        bound_log=driver._log.bind(),
    )
    # Plan 20-01 keeps single-target return signature → first id's PC.
    assert chosen is not None
    assert chosen["character_id"] == aoe_ids[0]


@pytest.mark.asyncio
async def test_pick_target_llm_aoe_regex_extractor() -> None:
    pcs = _make_pcs(3)
    aoe_ids = [pcs[0]["character_id"], pcs[1]["character_id"]]
    # Prose-wrapped JSON; strict parse fails → list-shape regex fires.
    content = (
        f'Choice: "target_pc_ids": ["{aoe_ids[0]}", "{aoe_ids[1]}"], '
        '"tactic_kind": "aoe". Done.'
    )
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion(content)
    )
    driver = _make_driver(openai_client=openai_client)
    chosen = await driver._pick_target_llm(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "dragon"},
        bound_log=driver._log.bind(),
    )
    assert chosen is not None
    assert chosen["character_id"] == aoe_ids[0]


@pytest.mark.asyncio
async def test_pick_target_llm_aoe_partial_hallucination_falls_back() -> None:
    pcs = _make_pcs(3)
    real_id = pcs[0]["character_id"]
    content = (
        f'{{"target_pc_ids": ["{real_id}", "ghost-id"], "tactic_kind": "aoe"}}'
    )
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion(content)
    )
    driver = _make_driver(openai_client=openai_client)
    chosen = await driver._pick_target_llm(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "dragon"},
        bound_log=driver._log.bind(),
    )
    # ALL ids must be in candidate set; partial → fallback (None).
    assert chosen is None


@pytest.mark.asyncio
async def test_choose_target_aoe_partial_hallucination_random_fallback() -> None:
    pcs = _make_pcs(3)
    real_id = pcs[0]["character_id"]
    content = (
        f'{{"target_pc_ids": ["{real_id}", "ghost-id"], "tactic_kind": "aoe"}}'
    )
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion(content)
    )
    fallback = MagicMock(return_value=pcs[2])
    driver = _make_driver(openai_client=openai_client, random_choice=fallback)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "dragon", "intelligence": 16},
    )
    # Fail-soft: random fallback used (D-58 / D-153).
    assert fallback.called
    assert chosen == pcs[2]
