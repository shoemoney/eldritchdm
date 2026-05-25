"""
Adversarial corpus for SmartMonsterDriver (Phase 10 Plan 02 — COMBAT-14).

15 scenarios proving fail-soft behaviour across the entire LLM oracle surface.
Each scenario:
  - Asserts no exception propagates to the caller
  - Asserts the driver still picks a valid candidate (or skips cleanly when
    the candidate list is empty)
  - For paths that go through the orchestrator's full `drive()`, asserts that
    `next_turn` was invoked — combat MUST keep moving even when the LLM
    misbehaves

Mirrors the v1.0 sanitizer corpus pattern (one test function per scenario;
easier to read than one mega-parametrize and easier to add new cases).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.gameplay.smart_monster_driver import (
    ActionDescriptor,
    MonsterTacticChoice,
    SmartMonsterDriver,
)

# ── Test infrastructure ──────────────────────────────────────────────────────


def _make_pcs(n: int = 3) -> list[dict[str, Any]]:
    return [
        {
            "character_id": f"pc-{i:03d}",
            "user_id": 1000 + i,
            "player_id": str(1000 + i),
            "name": f"Hero{i}",
            "primary_weapon": "longsword",
            "hp_current": 20 - i * 4,
            "hp_max": 20,
            "ac": 14 + (i % 3),
            "active_conditions": [],
        }
        for i in range(n)
    ]


def _make_completion(content: str) -> MagicMock:
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
        random_choice=random_choice
        if random_choice is not None
        else (lambda xs: xs[0]),
    )


# ── 1. Malformed JSON → random fallback ──────────────────────────────────────


@pytest.mark.asyncio
async def test_corpus_malformed_json() -> None:
    pcs = _make_pcs(3)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion("not json at all -- definitely garbage from a sleepy LLM")
    )
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1", "intelligence": 12},
    )
    # LLM was tried, parse failed, random_choice picked the first
    assert chosen == pcs[0]


# ── 2. Hallucinated target id → random fallback ──────────────────────────────


@pytest.mark.asyncio
async def test_corpus_hallucinated_target_id() -> None:
    pcs = _make_pcs(3)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "ghost-of-elvis"}')
    )
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1", "intelligence": 12},
    )
    # Membership check failed → random fallback to pcs[0]
    assert chosen == pcs[0]


# ── 3. Timeout exceeded → random fallback + warning logged ───────────────────


@pytest.mark.asyncio
async def test_corpus_timeout_exceeded(caplog: pytest.LogCaptureFixture) -> None:
    pcs = _make_pcs(3)

    async def slow_create(**kwargs):
        await asyncio.sleep(5.0)
        return _make_completion('{"target_pc_id": "pc-000"}')

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=slow_create)

    driver = _make_driver(openai_client=client, llm_timeout_seconds=0.02)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1", "intelligence": 14},
    )
    # No exception leaked; got a valid PC
    assert chosen in pcs


# ── 4. Empty candidate list — driver `drive()` no-eligible-target path ──────


@pytest.mark.asyncio
async def test_corpus_empty_candidate_list() -> None:
    """When `targets` is empty the driver's drive() warns and advances turn.

    `_choose_target` is never called in the empty case (drive() short-circuits
    on `not targets`). Here we verify the orchestrator-level guarantee via
    the public `drive` entrypoint.
    """
    # Set up a state_provider returning an empty PC list
    async def empty_state_provider(channel_id, campaign_name):
        return {"round_number": 1, "pcs": []}

    client = MagicMock()
    client.chat.completions.create = AsyncMock()

    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock()

    def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
        return discord.ui.Button(label="r", custom_id=f"r:{timer_id}:{user_id}")

    def channel_resolver(channel_id: str) -> Any:
        return None

    driver = SmartMonsterDriver(
        mcp=MagicMock(),
        rate_limiter=rate_limiter,
        pc_classes_repo=MagicMock(),
        riposte_timers_repo=MagicMock(),
        button_factory=button_factory,
        state_provider=empty_state_provider,
        channel_resolver=channel_resolver,
        openai_client=client,
        llm_model="ShoeGPT",
    )

    # Patch mcp_tools.next_turn so drive() can call it without errors
    from unittest.mock import patch

    with patch(
        "eldritch_dm.gameplay.monster_driver.mcp_tools.next_turn",
        new_callable=AsyncMock,
    ) as mock_next_turn:
        await driver.drive(
            channel_id="c",
            campaign_name="test",
            current_actor={
                "character_id": "m1",
                "player_id": None,
                "intelligence": 12,
            },
        )

    # No LLM call (no candidates to ask about)
    assert client.chat.completions.create.call_count == 0
    # next_turn was called — combat keeps moving
    assert mock_next_turn.called


# ── 5. Sub-INT bypass: INT <= 4 skips LLM entirely ───────────────────────────


@pytest.mark.asyncio
async def test_corpus_sub_int_bypass() -> None:
    pcs = _make_pcs(3)
    client = MagicMock()
    client.chat.completions.create = AsyncMock()
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "ogre-1", "intelligence": 2},
    )
    assert client.chat.completions.create.call_count == 0
    assert chosen in pcs


# ── 6. INT=12 with a downed PC — no exception, valid pick ────────────────────


@pytest.mark.asyncio
async def test_corpus_int12_with_downed_pc() -> None:
    pcs = _make_pcs(3)
    pcs[0]["hp_current"] = 0  # downed
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{pcs[1]["character_id"]}"}}')
    )
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1", "intelligence": 12},
    )
    # Anti-griefing is aspirational — here we just assert the call worked
    # and produced a valid candidate (not the downed one in this case).
    assert chosen["character_id"] == pcs[1]["character_id"]


# ── 7. INT=18 with a concentration holder — LLM is consulted ─────────────────


@pytest.mark.asyncio
async def test_corpus_int18_with_concentration_holder() -> None:
    pcs = _make_pcs(3)
    pcs[2]["active_conditions"] = ["concentrating"]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{pcs[2]["character_id"]}"}}')
    )
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "lich", "intelligence": 18},
    )
    assert client.chat.completions.create.call_count == 1
    assert chosen["character_id"] == pcs[2]["character_id"]


# ── 8. Invisible PC — no exception (driver does not enforce RAW itself) ──────


@pytest.mark.asyncio
async def test_corpus_invisible_pc() -> None:
    pcs = _make_pcs(3)
    pcs[1]["active_conditions"] = ["invisible"]
    client = MagicMock()
    # LLM still picks; the engine (not the driver) is responsible for RAW
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{pcs[0]["character_id"]}"}}')
    )
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1", "intelligence": 10},
    )
    assert chosen in pcs


# ── 9. Refusal path (empty content) → random fallback ────────────────────────


@pytest.mark.asyncio
async def test_corpus_refusal_path() -> None:
    pcs = _make_pcs(3)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_completion(""))
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1", "intelligence": 12},
    )
    assert chosen == pcs[0]  # random fallback to first


# ── 10. Rate limit 429 (OpenAI/oMLX raises) → random fallback ────────────────


@pytest.mark.asyncio
async def test_corpus_rate_limit_429() -> None:
    pcs = _make_pcs(3)

    class FakeRateLimit(Exception):
        """Stand-in for openai.RateLimitError (avoids hard SDK dependency in test)."""

    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=FakeRateLimit("429: too many requests")
    )
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": "m1", "intelligence": 12},
    )
    assert chosen == pcs[0]


# ── 11. Cache hit: same (c, r, m) → mock called exactly once ────────────────


@pytest.mark.asyncio
async def test_corpus_cache_hit_same_key() -> None:
    pcs = _make_pcs(3)
    target_id = pcs[1]["character_id"]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{target_id}"}}')
    )
    driver = _make_driver(openai_client=client)
    actor = {"character_id": "m1", "intelligence": 12}

    a = await driver._choose_target(
        pcs, channel_id="c", round_number=1, current_actor=actor
    )
    b = await driver._choose_target(
        pcs, channel_id="c", round_number=1, current_actor=actor
    )
    assert a == b
    # Second call hit the cache → only one LLM call
    assert client.chat.completions.create.call_count == 1


# ── 12. PC death between calls: different round → cache miss, new pick ───────


@pytest.mark.asyncio
async def test_corpus_pc_death_between_calls() -> None:
    pcs = _make_pcs(3)
    target_first = pcs[1]["character_id"]
    target_second = pcs[2]["character_id"]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            _make_completion(f'{{"target_pc_id": "{target_first}"}}'),
            _make_completion(f'{{"target_pc_id": "{target_second}"}}'),
        ]
    )
    driver = _make_driver(openai_client=client)
    actor = {"character_id": "m1", "intelligence": 12}

    a = await driver._choose_target(
        pcs, channel_id="c", round_number=1, current_actor=actor
    )
    # Simulate PC death: drop pcs[1] from candidates
    survivors = [pcs[0], pcs[2]]
    b = await driver._choose_target(
        survivors, channel_id="c", round_number=2, current_actor=actor
    )
    assert a["character_id"] == target_first
    assert b["character_id"] == target_second
    # Two distinct LLM calls (different round → cache miss)
    assert client.chat.completions.create.call_count == 2


# ── 13. Cross-channel isolation: same (round, monster) different channel ─────


@pytest.mark.asyncio
async def test_corpus_cross_channel_isolation() -> None:
    pcs = _make_pcs(3)
    target_id = pcs[0]["character_id"]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{target_id}"}}')
    )
    driver = _make_driver(openai_client=client)
    actor = {"character_id": "m1", "intelligence": 12}

    await driver._choose_target(
        pcs, channel_id="chan-A", round_number=1, current_actor=actor
    )
    await driver._choose_target(
        pcs, channel_id="chan-B", round_number=1, current_actor=actor
    )
    # Different channels → no cache hit, two LLM calls
    assert client.chat.completions.create.call_count == 2


# ── 14. Mixed-mode INT=5 seeded determinism ──────────────────────────────────


@pytest.mark.asyncio
async def test_corpus_mixed_mode_seeded_determinism() -> None:
    """INT in [5,7] is seeded by (c, r, m); the route choice must be stable
    across independent driver instances."""
    pcs = _make_pcs(3)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{pcs[0]["character_id"]}"}}')
    )

    routes = {
        SmartMonsterDriver._route_path(
            6, channel_id="chan-X", round_number=4, monster_id="gob-1"
        )
        for _ in range(20)
    }
    assert len(routes) == 1  # always the same route across 20 evaluations

    # Sanity: the picked driver still produces a valid PC
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="chan-X",
        round_number=4,
        current_actor={"character_id": "gob-1", "intelligence": 6},
    )
    assert chosen in pcs


# ── 15. Self-target attempt — LLM returns the monster's own id → fallback ────


@pytest.mark.asyncio
async def test_corpus_self_target_attempt() -> None:
    pcs = _make_pcs(3)
    monster_id = "m1"  # not in pc candidate set
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{monster_id}"}}')
    )
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={"character_id": monster_id, "intelligence": 14},
    )
    # Membership check fails → random fallback to first
    assert chosen == pcs[0]


# ── Bonus: cache FIFO eviction at the max-size boundary ──────────────────────


@pytest.mark.asyncio
async def test_corpus_cache_fifo_eviction() -> None:
    """When cache exceeds max_size, the oldest entry is evicted."""
    pcs = _make_pcs(3)
    target_id = pcs[0]["character_id"]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion(f'{{"target_pc_id": "{target_id}"}}')
    )

    # Small cache for the test
    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock()

    def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
        return discord.ui.Button(label="r", custom_id=f"r:{timer_id}:{user_id}")

    async def state_provider(channel_id, campaign_name):
        return {"round_number": 1, "pcs": []}

    driver = SmartMonsterDriver(
        mcp=MagicMock(),
        rate_limiter=rate_limiter,
        pc_classes_repo=MagicMock(),
        riposte_timers_repo=MagicMock(),
        button_factory=button_factory,
        state_provider=state_provider,
        channel_resolver=lambda c: None,
        openai_client=client,
        cache_max_size=3,
        random_choice=lambda xs: xs[0],
    )

    actor = {"character_id": "m1", "intelligence": 12}
    # Fill cache to capacity with distinct rounds
    for r in range(3):
        await driver._choose_target(
            pcs, channel_id="c", round_number=r, current_actor=actor
        )
    assert len(driver._cache) == 3

    # Add one more → oldest evicted, size stays at 3
    await driver._choose_target(
        pcs, channel_id="c", round_number=99, current_actor=actor
    )
    assert len(driver._cache) == 3
    # Round 0 (oldest) should be gone
    assert ("c", 0, "m1") not in driver._cache
    assert ("c", 99, "m1") in driver._cache


# ── Sanity: corpus size meets requirement ─────────────────────────────────────


def test_corpus_size_meets_requirement() -> None:
    """COMBAT-14 demands ≥15 adversarial scenarios. Counted manually here so
    a future drop of a test triggers a loud test failure rather than a silent
    coverage regression."""
    import inspect
    import sys

    module = sys.modules[__name__]
    corpus_tests = [
        name
        for name, _ in inspect.getmembers(module, inspect.isfunction)
        if name.startswith("test_corpus_")
    ]
    # Phase 20 / D-154: bumped to ≥25 — original COMBAT-14 ≥15 + Phase 20 AOE-03 +10.
    assert len(corpus_tests) >= 25, (
        f"corpus must have ≥25 scenarios per COMBAT-14 + AOE-03; "
        f"found {len(corpus_tests)}"
    )


# ── Schema dual-use: corpus exercises MonsterTacticChoice indirectly ──────────


def test_corpus_uses_monster_tactic_choice() -> None:
    """Smoke: confirm the corpus path exercises the production schema."""
    c = MonsterTacticChoice.model_validate_json('{"target_pc_id": "pc-x"}')
    assert isinstance(c, MonsterTacticChoice)


# ── Phase 20 / AOE-03: 10 multi-target / AOE scenarios ──────────────────────


def _breath_action() -> dict[str, Any]:
    return {"name": "fire breath", "kind": "cone", "range_ft": 30, "save_dc": 17}


def _fireball_action() -> dict[str, Any]:
    return {"name": "fireball", "kind": "aoe", "range_ft": 120, "save_dc": 15}


def _multi_attack_action() -> dict[str, Any]:
    return {"name": "claw/claw/bite", "kind": "multi_attack", "range_ft": 5, "save_dc": None}


# Cluster-optimal AOE (3) ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_corpus_aoe_dragon_breath_cluster() -> None:
    """INT=16 dragon with breath; LLM picks AOE on all 3 clustered PCs."""
    pcs = _make_pcs(3)
    ids = [p["character_id"] for p in pcs]
    content = (
        '{"target_pc_ids": ["' + ids[0] + '", "' + ids[1] + '", "' + ids[2] + '"], '
        '"tactic_kind": "breath", "rationale": "all in cone"}'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_completion(content))
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "dragon",
            "intelligence": 16,
            "available_actions": [_breath_action()],
        },
    )
    # Plan 20-01 single-target return signature → first id's PC.
    assert chosen["character_id"] == ids[0]


@pytest.mark.asyncio
async def test_corpus_aoe_fireball_caster_cluster() -> None:
    """INT=18 wizard fireballs 4 clustered PCs."""
    pcs = _make_pcs(4)
    ids = [p["character_id"] for p in pcs]
    content = (
        '{"target_pc_ids": ' + str(ids).replace("'", '"') + ', '
        '"tactic_kind": "aoe", "rationale": "tight cluster"}'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_completion(content))
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "wizard",
            "intelligence": 18,
            "available_actions": [_fireball_action()],
        },
    )
    assert chosen["character_id"] == ids[0]
    # All 4 ids stored in cache + validator passed → tactic_kind preserved.
    cached = driver._cache[("c", 1, "wizard")]
    assert cached.tactic_kind == "aoe"
    assert len(cached.target_pc_ids) == 4


@pytest.mark.asyncio
async def test_corpus_aoe_breath_cluster_with_validator_arity() -> None:
    """aoe with 2 ids passes; aoe with 1 id raises → fail-soft fallback."""
    pcs = _make_pcs(3)
    ids = [p["character_id"] for p in pcs]
    # First: valid 2-id aoe
    content_ok = (
        '{"target_pc_ids": ["' + ids[0] + '", "' + ids[1] + '"], '
        '"tactic_kind": "aoe"}'
    )
    # Second: invalid 1-id aoe → validator rejects → caller's random_choice fires
    content_bad = '{"target_pc_ids": ["' + ids[2] + '"], "tactic_kind": "aoe"}'
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[_make_completion(content_ok), _make_completion(content_bad)]
    )
    driver = _make_driver(openai_client=client, random_choice=lambda xs: xs[-1])
    actor = {
        "character_id": "drake",
        "intelligence": 14,
        "available_actions": [_breath_action()],
    }
    ok = await driver._choose_target(pcs, channel_id="c", round_number=1, current_actor=actor)
    bad = await driver._choose_target(pcs, channel_id="c", round_number=2, current_actor=actor)
    assert ok["character_id"] == ids[0]  # valid aoe → first id
    assert bad == pcs[-1]  # arity-violation → random_choice last


# Anti-cluster (3) ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_corpus_anti_cluster_single_target_preferred() -> None:
    """Lone PC scenario: LLM correctly emits tactic_kind='single'."""
    pcs = _make_pcs(1)
    content = (
        '{"target_pc_ids": ["' + pcs[0]["character_id"] + '"], '
        '"tactic_kind": "single", "rationale": "only target"}'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_completion(content))
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "dragon",
            "intelligence": 16,
            "available_actions": [_breath_action()],
        },
    )
    assert chosen == pcs[0]
    cached = driver._cache[("c", 1, "dragon")]
    assert cached.tactic_kind == "single"


@pytest.mark.asyncio
async def test_corpus_anti_cluster_aoe_with_one_in_range_falls_back() -> None:
    """LLM erroneously emits aoe with 1 id → ValidationError → random fallback."""
    pcs = _make_pcs(3)
    content = (
        '{"target_pc_ids": ["' + pcs[0]["character_id"] + '"], '
        '"tactic_kind": "aoe"}'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_completion(content))
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": [_breath_action()],
        },
    )
    # Schema rejected the aoe-with-1-id → fallback to first PC (random_choice).
    assert chosen == pcs[0]


@pytest.mark.asyncio
async def test_corpus_anti_cluster_mixed_kind_rejection() -> None:
    """{'single', [a, b]} → ValidationError → fallback."""
    pcs = _make_pcs(3)
    ids = [p["character_id"] for p in pcs]
    content = (
        '{"target_pc_ids": ["' + ids[0] + '", "' + ids[1] + '"], '
        '"tactic_kind": "single"}'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_completion(content))
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "m1",
            "intelligence": 12,
            "available_actions": [_multi_attack_action()],
        },
    )
    assert chosen == pcs[0]  # random fallback


# Mixed-tactic (2) ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_corpus_multi_attack_pile_on_one_pc() -> None:
    """multi_attack with 1 id (pile-on) is RAW-legal."""
    pcs = _make_pcs(3)
    content = (
        '{"target_pc_ids": ["' + pcs[1]["character_id"] + '"], '
        '"tactic_kind": "multi_attack"}'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_completion(content))
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "ogre",
            "intelligence": 10,
            "available_actions": [_multi_attack_action()],
        },
    )
    assert chosen == pcs[1]
    cached = driver._cache[("c", 1, "ogre")]
    assert cached.tactic_kind == "multi_attack"


@pytest.mark.asyncio
async def test_corpus_multi_attack_spread_across_two_pcs() -> None:
    """Cleave-style multi_attack across two adjacent PCs."""
    pcs = _make_pcs(3)
    ids = [p["character_id"] for p in pcs]
    content = (
        '{"target_pc_ids": ["' + ids[0] + '", "' + ids[1] + '"], '
        '"tactic_kind": "multi_attack"}'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_completion(content))
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "horror",
            "intelligence": 10,
            "available_actions": [_multi_attack_action()],
        },
    )
    assert chosen["character_id"] == ids[0]
    cached = driver._cache[("c", 1, "horror")]
    assert cached.target_pc_ids == ids[:2]


# Adversarial (2) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_corpus_aoe_with_one_hallucinated_id() -> None:
    """AOE with one real id + one ghost id → membership fail → random fallback."""
    pcs = _make_pcs(3)
    content = (
        '{"target_pc_ids": ["' + pcs[0]["character_id"] + '", "ghost-of-elvis"], '
        '"tactic_kind": "aoe"}'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_completion(content))
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": [_breath_action()],
        },
    )
    assert chosen == pcs[0]  # random fallback (random_choice picks first)


@pytest.mark.asyncio
async def test_corpus_aoe_with_empty_list() -> None:
    """target_pc_ids=[] rejected by min_length → schema fail → random fallback."""
    pcs = _make_pcs(3)
    content = '{"target_pc_ids": [], "tactic_kind": "aoe"}'
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_completion(content))
    driver = _make_driver(openai_client=client)
    chosen = await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": [_breath_action()],
        },
    )
    assert chosen == pcs[0]


# ── Plan 20-02 addendum + ActionDescriptor wiring ───────────────────────────


@pytest.mark.asyncio
async def test_aoe_addendum_injected_when_available_actions_present() -> None:
    """Phase 23 / D-180: addendum is injected ONLY when ≥2 AOE-class actions
    are present on the actor. Single-AOE / no-AOE actors keep the legacy
    single-target prompt (bit-identical to Phase 10)."""
    pcs = _make_pcs(2)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )
    driver = _make_driver(openai_client=client)

    # With ≥2 AOE-class actions → addendum injected (D-180)
    await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": [_breath_action(), _fireball_action()],
        },
    )
    call_with = client.chat.completions.create.call_args_list[0]
    sys_msg = call_with.kwargs["messages"][0]["content"]
    assert "EXTENSION: multi-target tactic selection." in sys_msg
    assert "aoe-addendum-version: 1.0.0" in sys_msg

    # Without available_actions → legacy prompt verbatim (no addendum)
    client.chat.completions.create.reset_mock(return_value=True)
    client.chat.completions.create.return_value = _make_completion(
        '{"target_pc_id": "pc-000"}'
    )
    await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=2,
        current_actor={"character_id": "drake", "intelligence": 14},
    )
    call_without = client.chat.completions.create.call_args_list[0]
    sys_msg_legacy = call_without.kwargs["messages"][0]["content"]
    assert "EXTENSION:" not in sys_msg_legacy


@pytest.mark.asyncio
async def test_available_actions_validated_and_appears_in_user_payload() -> None:
    """ActionDescriptor coerces dicts; malformed entries silently dropped."""
    import json as _json

    pcs = _make_pcs(2)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )
    driver = _make_driver(openai_client=client)

    raw_actions = [
        _breath_action(),  # valid
        {"name": "bogus", "kind": "telepathy", "range_ft": 30},  # invalid Literal
        {"missing": "everything"},  # malformed
    ]
    await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": raw_actions,
        },
    )
    call = client.chat.completions.create.call_args_list[0]
    user_content = call.kwargs["messages"][1]["content"]
    payload = _json.loads(user_content)
    assert len(payload["available_actions"]) == 1
    assert payload["available_actions"][0]["name"] == "fire breath"


def test_action_descriptor_constructs_and_rejects_invalid_kind() -> None:
    """ActionDescriptor schema sanity."""
    a = ActionDescriptor(name="claw", kind="single", range_ft=5)
    assert a.save_dc is None
    from pydantic import ValidationError as _VE

    with pytest.raises(_VE):
        ActionDescriptor(name="bad", kind="telepathy", range_ft=30)


# ── Phase 23 / WIRE-03: tightened AOE addendum predicate + OTel version attr ─


def _capture_traced_decision(monkeypatch, captured: list[Any]) -> None:
    """Monkey-patch ``traced_decision`` in the smart driver module so tests
    can inspect the span instance produced for each decision."""
    from contextlib import contextmanager

    from eldritch_dm.gameplay import smart_monster_driver as _smd

    real = _smd.traced_decision

    @contextmanager
    def _wrapper(**kwargs):
        with real(**kwargs) as span:
            captured.append(span)
            yield span

    monkeypatch.setattr(_smd, "traced_decision", _wrapper)


def _single_action() -> dict[str, Any]:
    return {"name": "slam", "kind": "single", "range_ft": 5, "save_dc": None}


@pytest.mark.asyncio
async def test_addendum_skipped_with_one_aoe_action(monkeypatch) -> None:
    """D-180: exactly one AOE-class action → addendum NOT injected, no version attr."""
    pcs = _make_pcs(2)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )
    driver = _make_driver(openai_client=client)
    spans: list[Any] = []
    _capture_traced_decision(monkeypatch, spans)

    await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": [_breath_action(), _single_action()],
        },
    )

    sys_msg = client.chat.completions.create.call_args_list[0].kwargs["messages"][0]["content"]
    assert "EXTENSION: multi-target tactic selection." not in sys_msg
    assert "aoe-addendum-version" not in sys_msg
    assert "eldritch.aoe.addendum_version" not in spans[0]._attrs


@pytest.mark.asyncio
async def test_addendum_skipped_with_zero_aoe_actions(monkeypatch) -> None:
    """D-180: only single/multi_attack actions → no addendum, no version attr."""
    pcs = _make_pcs(2)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )
    driver = _make_driver(openai_client=client)
    spans: list[Any] = []
    _capture_traced_decision(monkeypatch, spans)

    await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": [_single_action(), _multi_attack_action()],
        },
    )

    sys_msg = client.chat.completions.create.call_args_list[0].kwargs["messages"][0]["content"]
    assert "EXTENSION:" not in sys_msg
    assert "eldritch.aoe.addendum_version" not in spans[0]._attrs


@pytest.mark.asyncio
async def test_addendum_injected_with_two_aoe_actions(monkeypatch) -> None:
    """D-180: two AOE-class actions → addendum injected + version attr stamped."""
    pcs = _make_pcs(2)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )
    driver = _make_driver(openai_client=client)
    spans: list[Any] = []
    _capture_traced_decision(monkeypatch, spans)

    await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": [_breath_action(), _fireball_action()],
        },
    )

    sys_msg = client.chat.completions.create.call_args_list[0].kwargs["messages"][0]["content"]
    assert "EXTENSION: multi-target tactic selection." in sys_msg
    # D-181: version attribute stamped on the SAME decision span
    assert spans[0]._attrs.get("eldritch.aoe.addendum_version") == "1.0.0"


@pytest.mark.asyncio
async def test_addendum_version_attr_only_set_when_injected(monkeypatch) -> None:
    """D-181: version attr is set IFF addendum is appended — single-AOE turn
    skips both. Mixed back-to-back turns prove the per-turn boundary."""
    pcs = _make_pcs(2)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )
    driver = _make_driver(openai_client=client)
    spans: list[Any] = []
    _capture_traced_decision(monkeypatch, spans)

    # Round 1: only single-AOE → no version attr
    await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": [_breath_action()],
        },
    )
    assert "eldritch.aoe.addendum_version" not in spans[0]._attrs

    # Round 2: ≥2 AOE → version attr present (round changes to bust the cache)
    await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=2,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": [_breath_action(), _fireball_action()],
        },
    )
    assert spans[1]._attrs.get("eldritch.aoe.addendum_version") == "1.0.0"


@pytest.mark.asyncio
async def test_addendum_load_failure_no_injection(monkeypatch) -> None:
    """D-153 fail-soft: addendum loader raises → driver still constructs, but
    even with ≥2 AOE actions no addendum is appended and no version attr is
    stamped (cached empty body)."""
    def _bad_loader() -> tuple[str, str]:
        raise RuntimeError("addendum file gone walkabout")

    pcs = _make_pcs(2)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )

    # Build driver directly with the bad loader (bypass _make_driver to inject the kwarg)
    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock()
    driver = SmartMonsterDriver(
        mcp=MagicMock(),
        rate_limiter=rate_limiter,
        pc_classes_repo=MagicMock(),
        riposte_timers_repo=MagicMock(),
        button_factory=lambda t, u: discord.ui.Button(label="r", custom_id=f"r:{t}:{u}"),
        state_provider=AsyncMock(return_value={"round_number": 1, "pcs": []}),
        channel_resolver=lambda c: None,
        openai_client=client,
        llm_model="ShoeGPT",
        random_choice=lambda xs: xs[0],
        aoe_addendum_loader=_bad_loader,
    )
    assert driver._aoe_addendum_text == ""
    assert driver._aoe_addendum_version == ""

    spans: list[Any] = []
    _capture_traced_decision(monkeypatch, spans)

    await driver._choose_target(
        pcs,
        channel_id="c",
        round_number=1,
        current_actor={
            "character_id": "drake",
            "intelligence": 14,
            "available_actions": [_breath_action(), _fireball_action()],
        },
    )

    sys_msg = client.chat.completions.create.call_args_list[0].kwargs["messages"][0]["content"]
    assert "EXTENSION:" not in sys_msg
    assert "eldritch.aoe.addendum_version" not in spans[0]._attrs


def test_get_addendum_version_returns_semver() -> None:
    """Direct unit test of the new aoe_addendum.get_addendum_version helper."""
    from eldritch_dm.gameplay.prompts.aoe_addendum import get_addendum_version

    version = get_addendum_version()
    assert version == "1.0.0"


def test_get_addendum_version_raises_on_missing_file(tmp_path) -> None:
    """Fail-loud surface: missing file → AoeAddendumError (caller chooses fail-soft)."""
    from eldritch_dm.gameplay.prompts.aoe_addendum import (
        AoeAddendumError,
        get_addendum_version,
    )

    missing = tmp_path / "does_not_exist.txt"
    with pytest.raises(AoeAddendumError):
        get_addendum_version(missing)
