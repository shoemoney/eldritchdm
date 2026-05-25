"""Unit tests for NarrCacheRuntimeOverride (Phase 18 / NARRCACHE-03 / D-134)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest

from eldritch_dm.observability.narrcache_runtime import (
    NarrCacheRuntimeOverride,
    get_narrcache_override,
)


@pytest.fixture
def fresh_override() -> NarrCacheRuntimeOverride:
    ov = get_narrcache_override()
    ov.reset_for_tests()
    yield ov
    ov.reset_for_tests()


def test_default_state_is_enabled(fresh_override: NarrCacheRuntimeOverride) -> None:
    assert fresh_override.is_disabled() is False
    snap = fresh_override.snapshot()
    assert snap.disabled is False
    assert snap.reason is None
    assert snap.last_change_utc is None


def test_disable_flips_state(fresh_override: NarrCacheRuntimeOverride) -> None:
    fresh_override.disable(reason="operator_request")
    assert fresh_override.is_disabled() is True
    snap = fresh_override.snapshot()
    assert snap.disabled is True
    assert snap.reason == "operator_request"
    assert snap.last_change_utc is not None


def test_disable_is_idempotent(fresh_override: NarrCacheRuntimeOverride) -> None:
    fresh_override.disable(reason="first")
    first_change = fresh_override.snapshot().last_change_utc
    fresh_override.disable(reason="second")  # still disabled, last_change updates
    snap = fresh_override.snapshot()
    assert snap.disabled is True
    assert snap.reason == "second"
    assert snap.last_change_utc >= first_change


def test_enable_flips_back(fresh_override: NarrCacheRuntimeOverride) -> None:
    fresh_override.disable(reason="x")
    fresh_override.enable()
    assert fresh_override.is_disabled() is False
    snap = fresh_override.snapshot()
    assert snap.disabled is False
    assert snap.reason is None


def test_enable_is_idempotent(fresh_override: NarrCacheRuntimeOverride) -> None:
    fresh_override.enable()  # already enabled
    assert fresh_override.is_disabled() is False


def test_singleton_identity(fresh_override: NarrCacheRuntimeOverride) -> None:
    assert get_narrcache_override() is fresh_override


def test_disable_under_explicit_timestamp() -> None:
    ov = NarrCacheRuntimeOverride()
    when = datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC)
    ov.disable(reason="t", now=when)
    snap = ov.snapshot()
    assert snap.last_change_utc == when


def test_threadsafe_disable_under_contention() -> None:
    """Many threads alternately flip; final state is well-defined."""
    ov = NarrCacheRuntimeOverride()

    def worker(disable_first: bool) -> None:
        for _ in range(100):
            if disable_first:
                ov.disable(reason="t")
                ov.enable()
            else:
                ov.enable()
                ov.disable(reason="t")

    threads = [threading.Thread(target=worker, args=(i % 2 == 0,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # We don't pin the final value (race-determined) — only that no
    # exception was raised and snapshot still works.
    snap = ov.snapshot()
    assert isinstance(snap.disabled, bool)


def test_acompletion_bypasses_when_runtime_override_disabled() -> None:
    """Smoke test: NarrCache.acompletion sees the override singleton."""
    import asyncio
    from dataclasses import dataclass
    from typing import Any

    from pydantic import BaseModel as _BM

    from eldritch_dm.observability.narration_cache import NarrCache

    class _Settings(_BM):
        narrcache_enabled: bool = True
        narrcache_l1_size: int = 256
        narrcache_l1_ttl_s: int = 3600

    @dataclass
    class _Msg:
        content: str

    @dataclass
    class _Choice:
        message: _Msg

    @dataclass
    class _Comp:
        choices: list[_Choice]
        usage: Any = None

    class _Client:
        def __init__(self) -> None:
            self.calls = 0
            self.chat = self

        @property
        def completions(self) -> _Client:
            return self

        async def create(self, **_kwargs: Any) -> _Comp:
            self.calls += 1
            return _Comp(choices=[_Choice(message=_Msg(content="The hearth glows."))])

    ov = get_narrcache_override()
    ov.reset_for_tests()
    try:
        ov.disable(reason="test")
        cache = NarrCache(settings=_Settings())
        client = _Client()
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
        ]
        # Two calls: both should bypass and hit upstream → call_count == 2.
        asyncio.run(
            cache.acompletion(client, model="m", messages=msgs, max_tokens=10, temperature=0.7)
        )
        asyncio.run(
            cache.acompletion(client, model="m", messages=msgs, max_tokens=10, temperature=0.7)
        )
        assert client.calls == 2
        snap = cache.metrics_snapshot()
        assert snap.bypass_count == 2
        assert snap.hits == 0
    finally:
        ov.reset_for_tests()
