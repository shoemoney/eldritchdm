"""Tests for gameplay.monster_driver_factory (Phase 10 Plan 02 — D-52)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from eldritch_dm.gameplay.monster_driver import MonsterDriver
from eldritch_dm.gameplay.monster_driver_factory import (
    _resolve_mode,
    make_monster_driver,
)
from eldritch_dm.gameplay.smart_monster_driver import SmartMonsterDriver


def _common_kwargs() -> dict[str, Any]:
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
    }


def test_resolve_mode_explicit_smart() -> None:
    assert _resolve_mode("smart") == "smart"


def test_resolve_mode_explicit_random() -> None:
    assert _resolve_mode("random") == "random"


def test_resolve_mode_explicit_mixed() -> None:
    assert _resolve_mode("mixed") == "mixed"


def test_resolve_mode_garbage_falls_back_to_smart() -> None:
    assert _resolve_mode("garbage-from-typo") == "smart"


def test_resolve_mode_case_insensitive() -> None:
    assert _resolve_mode("SMART") == "smart"
    assert _resolve_mode("Random") == "random"


def test_factory_random_returns_v1_driver() -> None:
    kwargs = _common_kwargs()
    driver = make_monster_driver(
        env_override="random",
        openai_client=MagicMock(),  # extra smart-only kwarg — must be ignored
        **kwargs,
    )
    assert isinstance(driver, MonsterDriver)
    assert not isinstance(driver, SmartMonsterDriver)


def test_factory_smart_returns_smart_driver() -> None:
    kwargs = _common_kwargs()
    driver = make_monster_driver(
        env_override="smart",
        openai_client=MagicMock(),
        **kwargs,
    )
    assert isinstance(driver, SmartMonsterDriver)


def test_factory_mixed_returns_smart_driver() -> None:
    """Per CONTEXT D-52, 'mixed' is an alias for 'smart' — the INT-gating
    inside _route_path does the actual mixing per monster."""
    kwargs = _common_kwargs()
    driver = make_monster_driver(
        env_override="mixed",
        openai_client=MagicMock(),
        **kwargs,
    )
    assert isinstance(driver, SmartMonsterDriver)


def test_factory_unknown_mode_falls_back_to_smart(
    caplog: pytest.LogCaptureFixture,
) -> None:
    kwargs = _common_kwargs()
    driver = make_monster_driver(
        env_override="banana",
        openai_client=MagicMock(),
        **kwargs,
    )
    assert isinstance(driver, SmartMonsterDriver)


def test_factory_settings_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When env_override is None, factory reads Settings().monster_driver."""
    # Force a fresh Settings() with MONSTER_DRIVER=random
    monkeypatch.setenv("MONSTER_DRIVER", "random")
    from eldritch_dm.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    try:
        kwargs = _common_kwargs()
        driver = make_monster_driver(
            openai_client=MagicMock(),
            **kwargs,
        )
        assert isinstance(driver, MonsterDriver)
        assert not isinstance(driver, SmartMonsterDriver)
    finally:
        get_settings.cache_clear()  # type: ignore[attr-defined]


# ── Phase 21 / MEM-02: factory accepts monster_memory kwarg ───────────────────


def test_factory_threads_monster_memory_to_smart_driver() -> None:
    """When constructing a smart driver, monster_memory kwarg flows through."""
    from eldritch_dm.gameplay.monster_memory import MonsterMemoryRegistry

    registry = MonsterMemoryRegistry()
    kwargs = _common_kwargs()
    driver = make_monster_driver(
        env_override="smart",
        openai_client=MagicMock(),
        monster_memory=registry,
        **kwargs,
    )
    assert isinstance(driver, SmartMonsterDriver)
    assert driver._monster_memory is registry


def test_factory_random_mode_strips_monster_memory_kwarg() -> None:
    """The random mode must accept and silently strip the monster_memory kwarg."""
    from eldritch_dm.gameplay.monster_memory import MonsterMemoryRegistry

    registry = MonsterMemoryRegistry()
    kwargs = _common_kwargs()
    # Random mode should not blow up when monster_memory is passed; the strip
    # list pops it before the MonsterDriver(...) call.
    driver = make_monster_driver(
        env_override="random",
        openai_client=MagicMock(),
        monster_memory=registry,
        **kwargs,
    )
    assert isinstance(driver, MonsterDriver)
    assert not isinstance(driver, SmartMonsterDriver)
