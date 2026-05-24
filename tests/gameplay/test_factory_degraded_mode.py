"""Factory honors degraded-mode override (Phase 13 / MON-02 / Task 02).

R-13-02-a: monster_driver_factory consults
``observability.degraded_mode.is_active()`` BEFORE the env or env_override,
so a degraded-mode trip during a real outage forces the random driver
regardless of operator config.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.gameplay.monster_driver import MonsterDriver
from eldritch_dm.gameplay.monster_driver_factory import make_monster_driver
from eldritch_dm.gameplay.smart_monster_driver import SmartMonsterDriver
from eldritch_dm.observability.degraded_mode import get_degraded_mode


def _common_kwargs() -> dict[str, Any]:
    """Mirror tests/gameplay/test_monster_driver_factory.py::_common_kwargs."""
    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock()

    def button_factory(timer_id: int, user_id: int) -> discord.ui.Button:
        return discord.ui.Button(label="r", custom_id=f"r:{timer_id}:{user_id}")

    async def state_provider(channel_id, campaign_name):
        return {"round_number": 1, "pcs": []}

    return {
        "mcp": MagicMock(),
        "rate_limiter": rate_limiter,
        "pc_classes_repo": MagicMock(),
        "riposte_timers_repo": MagicMock(),
        "button_factory": button_factory,
        "state_provider": state_provider,
        "channel_resolver": lambda c: None,
        "openai_client": MagicMock(),
    }


@pytest.fixture(autouse=True)
def _reset_degraded_mode():
    get_degraded_mode().reset_for_tests()
    yield
    get_degraded_mode().reset_for_tests()


def test_factory_smart_when_degraded_inactive():
    driver = make_monster_driver(**_common_kwargs())
    assert isinstance(driver, SmartMonsterDriver)


def test_factory_returns_random_when_degraded_active():
    get_degraded_mode().trip("test_latency_breach")
    driver = make_monster_driver(**_common_kwargs())
    assert isinstance(driver, MonsterDriver)
    assert not isinstance(driver, SmartMonsterDriver)


def test_degraded_overrides_explicit_env_override():
    """Even when caller explicitly asks for 'smart', degraded mode wins."""
    get_degraded_mode().trip("budget_exceeded")
    driver = make_monster_driver(env_override="smart", **_common_kwargs())
    assert isinstance(driver, MonsterDriver)
    assert not isinstance(driver, SmartMonsterDriver)


def test_degraded_overrides_mixed_env_override():
    get_degraded_mode().trip("fallback_storm")
    driver = make_monster_driver(env_override="mixed", **_common_kwargs())
    assert isinstance(driver, MonsterDriver)
    assert not isinstance(driver, SmartMonsterDriver)


def test_factory_recovers_after_degraded_recover():
    """After recover(), factory returns to smart on the next call."""
    get_degraded_mode().trip("latency_breach")
    d1 = make_monster_driver(**_common_kwargs())
    assert isinstance(d1, MonsterDriver)
    assert not isinstance(d1, SmartMonsterDriver)

    get_degraded_mode().recover()
    d2 = make_monster_driver(**_common_kwargs())
    assert isinstance(d2, SmartMonsterDriver)
