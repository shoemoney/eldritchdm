"""
Tests for Phase 19 streaming "monster is thinking" embed (STREAM-01/02/03).

Covers:
  - Plan 01 (STREAM-01):
      * thinking indicator fires on smart route (`llm`)
      * suppressed on random route
      * suppressed on cache hit
      * callback exception swallowed (D-145 cancellation safety)
  - Plan 02 (STREAM-02, STREAM-03):
      * suppressed when callback is None (STREAM_ENABLED=false equivalent)
      * factory forwards callback to smart driver
      * factory pops callback for random mode
      * fallback path (timeout) emits only the "sizing up" indicator — no
        "fallback"/"AI failed" wording reaches the player
      * fallback path (hallucinated id) — same invariant
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.gameplay.monster_driver import MonsterDriver
from eldritch_dm.gameplay.monster_driver_factory import make_monster_driver
from eldritch_dm.gameplay.smart_monster_driver import SmartMonsterDriver

# ── Helpers (mirror test_smart_monster_driver.py) ─────────────────────────────


def _make_pcs(n: int = 2) -> list[dict[str, Any]]:
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
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    return completion


def _make_driver(
    *,
    openai_client: Any,
    embed_update_callback: Any = None,
    random_choice=None,
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
        llm_timeout_seconds=1.5,
        ttl_seconds=8,
        random_choice=random_choice if random_choice is not None else (lambda xs: xs[0]),
        embed_update_callback=embed_update_callback,
    )


def _smart_monster(monster_int: int = 12) -> dict[str, Any]:
    return {
        "character_id": "mon-001",
        "name": "Goblin",
        "intelligence": monster_int,
    }


# ── STREAM-01: indicator fires on smart route ─────────────────────────────────


@pytest.mark.asyncio
async def test_thinking_indicator_fires_on_llm_route() -> None:
    """INT≥8 monster with callback set: indicator fires exactly once with the
    expected text BEFORE the LLM call resolves."""
    cb = AsyncMock()
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )
    driver = _make_driver(openai_client=openai_client, embed_update_callback=cb)

    chosen = await driver._choose_target(
        _make_pcs(2),
        channel_id="ch-1",
        round_number=1,
        current_actor=_smart_monster(monster_int=12),
    )

    assert chosen["character_id"] == "pc-000"
    cb.assert_awaited_once()
    args, _ = cb.call_args
    assert args[0] == "ch-1"
    assert "🤔" in args[1]
    assert "Goblin" in args[1]
    assert "sizing up the party" in args[1]


# ── STREAM-01: random route never fires ───────────────────────────────────────


@pytest.mark.asyncio
async def test_thinking_indicator_no_fire_on_random_route() -> None:
    """INT≤4 monster: no LLM call, no indicator."""
    cb = AsyncMock()
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock()  # should never be hit
    driver = _make_driver(openai_client=openai_client, embed_update_callback=cb)

    pcs = _make_pcs(2)
    await driver._choose_target(
        pcs,
        channel_id="ch-1",
        round_number=1,
        current_actor=_smart_monster(monster_int=3),
    )

    cb.assert_not_awaited()
    openai_client.chat.completions.create.assert_not_awaited()


# ── STREAM-01: cache hit suppresses indicator ─────────────────────────────────


@pytest.mark.asyncio
async def test_thinking_indicator_no_fire_on_cache_hit() -> None:
    """Second call with same key hits cache → no second indicator, no LLM."""
    cb = AsyncMock()
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )
    driver = _make_driver(openai_client=openai_client, embed_update_callback=cb)
    pcs = _make_pcs(2)
    monster = _smart_monster(monster_int=12)

    # First call — primes the cache + fires indicator
    await driver._choose_target(pcs, channel_id="ch-X", round_number=7, current_actor=monster)
    assert cb.await_count == 1
    assert openai_client.chat.completions.create.await_count == 1

    # Second call — same key → cache hit, no indicator, no LLM
    await driver._choose_target(pcs, channel_id="ch-X", round_number=7, current_actor=monster)
    assert cb.await_count == 1  # unchanged
    assert openai_client.chat.completions.create.await_count == 1  # unchanged


# ── STREAM-01 + D-145: callback exception is swallowed ────────────────────────


@pytest.mark.asyncio
async def test_thinking_indicator_swallows_exception() -> None:
    """Callback raises → combat resolves to a valid target anyway (D-145)."""
    cb = AsyncMock(side_effect=RuntimeError("coalescer closed"))
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-001"}')
    )
    driver = _make_driver(openai_client=openai_client, embed_update_callback=cb)

    chosen = await driver._choose_target(
        _make_pcs(2),
        channel_id="ch-1",
        round_number=1,
        current_actor=_smart_monster(monster_int=10),
    )

    assert chosen is not None
    assert chosen["character_id"] in {"pc-000", "pc-001"}
    cb.assert_awaited_once()  # tried, but exception swallowed


# ── STREAM-03: callback=None suppresses indicator ─────────────────────────────


@pytest.mark.asyncio
async def test_thinking_indicator_suppressed_when_callback_none() -> None:
    """STREAM_ENABLED=false → bot passes callback=None → driver stays silent
    but the LLM still runs and the chosen target is still resolved."""
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-000"}')
    )
    driver = _make_driver(openai_client=openai_client, embed_update_callback=None)

    chosen = await driver._choose_target(
        _make_pcs(2),
        channel_id="ch-2",
        round_number=1,
        current_actor=_smart_monster(monster_int=14),
    )

    assert chosen["character_id"] == "pc-000"
    # No callback object exists — sanity: the LLM was still consulted
    openai_client.chat.completions.create.assert_awaited_once()


# ── STREAM-03: factory forwards callback to smart driver ──────────────────────


def test_factory_forwards_stream_callback_to_smart_driver() -> None:
    """make_monster_driver(env_override='smart', embed_update_callback=cb)
    must produce a SmartMonsterDriver with the callback wired through."""
    cb = AsyncMock()
    rate_limiter = MagicMock()

    def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
        return discord.ui.Button(label="r")

    async def state_provider(channel_id, campaign_name):
        return {}

    def channel_resolver(channel_id):
        return None

    driver = make_monster_driver(
        env_override="smart",
        mcp=MagicMock(),
        rate_limiter=rate_limiter,
        pc_classes_repo=MagicMock(),
        riposte_timers_repo=MagicMock(),
        button_factory=button_factory,
        state_provider=state_provider,
        channel_resolver=channel_resolver,
        openai_client=MagicMock(),
        llm_model="ShoeGPT",
        embed_update_callback=cb,
    )

    assert isinstance(driver, SmartMonsterDriver)
    assert driver._embed_update_callback is cb


# ── STREAM-03: factory pops callback for random mode ──────────────────────────


def test_factory_random_mode_pops_stream_callback() -> None:
    """In random mode, the callback kwarg must be popped — MonsterDriver
    doesn't accept it and would raise TypeError otherwise."""
    cb = AsyncMock()
    rate_limiter = MagicMock()

    def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
        return discord.ui.Button(label="r")

    async def state_provider(channel_id, campaign_name):
        return {}

    def channel_resolver(channel_id):
        return None

    driver = make_monster_driver(
        env_override="random",
        mcp=MagicMock(),
        rate_limiter=rate_limiter,
        pc_classes_repo=MagicMock(),
        riposte_timers_repo=MagicMock(),
        button_factory=button_factory,
        state_provider=state_provider,
        channel_resolver=channel_resolver,
        embed_update_callback=cb,
    )

    assert isinstance(driver, MonsterDriver)
    assert not isinstance(driver, SmartMonsterDriver)


# ── STREAM-02: fallback (timeout) emits ONLY the "sizing up" indicator ────────


@pytest.mark.asyncio
async def test_fallback_path_no_additional_indicator_after_timeout() -> None:
    """LLM times out → driver falls back to random. The callback must have
    been invoked EXACTLY ONCE (the 'sizing up' message). No second invocation
    with 'fallback' / 'AI failed' wording reaches the player."""
    cb = AsyncMock()
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(side_effect=TimeoutError())
    driver = _make_driver(openai_client=openai_client, embed_update_callback=cb)

    chosen = await driver._choose_target(
        _make_pcs(2),
        channel_id="ch-9",
        round_number=1,
        current_actor=_smart_monster(monster_int=12),
    )

    assert chosen is not None
    assert chosen["character_id"] in {"pc-000", "pc-001"}
    assert cb.await_count == 1
    _, text = cb.call_args[0]
    forbidden = ("fallback", "ai failed", "ai_failed", "failed", "error")
    lowered = text.lower()
    for f in forbidden:
        assert f not in lowered, f"forbidden token {f!r} leaked to player: {text!r}"


# ── STREAM-02: fallback (hallucinated id) emits ONLY the "sizing up" indicator


@pytest.mark.asyncio
async def test_fallback_path_no_additional_indicator_after_hallucination() -> None:
    """LLM returns a target_pc_id not in the candidate set → random
    fallback. Callback invoked exactly once with the indicator only."""
    cb = AsyncMock()
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_completion('{"target_pc_id": "pc-999"}')
    )
    driver = _make_driver(openai_client=openai_client, embed_update_callback=cb)

    chosen = await driver._choose_target(
        _make_pcs(2),
        channel_id="ch-10",
        round_number=1,
        current_actor=_smart_monster(monster_int=12),
    )

    assert chosen is not None
    assert chosen["character_id"] in {"pc-000", "pc-001"}
    assert cb.await_count == 1
    _, text = cb.call_args[0]
    assert "fallback" not in text.lower()
    assert "failed" not in text.lower()
