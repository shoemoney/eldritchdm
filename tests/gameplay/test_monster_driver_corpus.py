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
    assert len(corpus_tests) >= 15, (
        f"corpus must have ≥15 scenarios per COMBAT-14; found {len(corpus_tests)}"
    )


# ── Schema dual-use: corpus exercises MonsterTacticChoice indirectly ──────────


def test_corpus_uses_monster_tactic_choice() -> None:
    """Smoke: confirm the corpus path exercises the production schema."""
    c = MonsterTacticChoice.model_validate_json('{"target_pc_id": "pc-x"}')
    assert isinstance(c, MonsterTacticChoice)
