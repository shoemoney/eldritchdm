"""Unit tests for NarrCache (Phase 18 / NARRCACHE-01).

Covers: bypass when disabled, key-construction edge cases, HIT path, MISS
path stores when safe, MISS path REJECTS storage when response contains
mechanical text, HIT path re-rejects when gate tightens, LRU eviction
order, TTL expiry, asyncio.Lock contention.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from eldritch_dm.observability.narration_cache import (
    NarrCache,
    NarrCacheGate,
    _cache_key,
    _extract_completion_text,
    _extract_system_user,
)

# ── Test doubles ────────────────────────────────────────────────────────────


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class _FakeCompletion:
    choices: list[_FakeChoice]
    usage: _FakeUsage | None = None


def _make_completion(text: str, p: int = 100, c: int = 50) -> _FakeCompletion:
    return _FakeCompletion(
        choices=[_FakeChoice(message=_FakeMessage(content=text))],
        usage=_FakeUsage(prompt_tokens=p, completion_tokens=c),
    )


class _FakeClient:
    """Async OpenAI-compatible stub. Calls are scripted by ``responses``."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.call_count = 0
        self.chat = self  # so client.chat.completions.create works

    @property
    def completions(self) -> _FakeClient:
        return self

    async def create(self, **_kwargs: Any) -> Any:
        self.call_count += 1
        if not self._responses:
            raise RuntimeError("FakeClient ran out of scripted responses")
        return self._responses.pop(0)


# ── Settings stub (frozen=True elsewhere; we only need attributes here) ─────


class _Settings(BaseModel):
    narrcache_enabled: bool = True
    narrcache_l1_size: int = 256
    narrcache_l1_ttl_s: int = 3600


# ── Helpers ─────────────────────────────────────────────────────────────────


_MSGS = [
    {"role": "system", "content": "You are a dungeon master."},
    {"role": "user", "content": "Describe the tavern."},
]


def _new_cache(**settings_overrides: Any) -> NarrCache:
    return NarrCache(settings=_Settings(**settings_overrides))  # type: ignore[arg-type]


# ── _extract_system_user / _cache_key ───────────────────────────────────────


def test_extract_system_user_happy() -> None:
    s, u = _extract_system_user(_MSGS)
    assert s == "You are a dungeon master."
    assert u == "Describe the tavern."


def test_extract_system_user_rejects_wrong_len() -> None:
    with pytest.raises(ValueError, match="exactly 2"):
        _extract_system_user([_MSGS[0]])
    with pytest.raises(ValueError, match="exactly 2"):
        _extract_system_user([*_MSGS, {"role": "assistant", "content": "..."}])


def test_extract_system_user_rejects_wrong_roles() -> None:
    with pytest.raises(ValueError, match="role='system'"):
        _extract_system_user([{"role": "user", "content": "x"}, {"role": "user", "content": "y"}])
    with pytest.raises(ValueError, match="role='user'"):
        _extract_system_user(
            [{"role": "system", "content": "x"}, {"role": "assistant", "content": "y"}]
        )


def test_cache_key_stable_across_calls() -> None:
    k1 = _cache_key(model="m", system="s", user="u", max_tokens=100, temperature=0.7)
    k2 = _cache_key(model="m", system="s", user="u", max_tokens=100, temperature=0.7)
    assert k1 == k2
    assert len(k1) == 64  # sha256 hex


def test_cache_key_differs_per_input() -> None:
    base = _cache_key(model="m", system="s", user="u", max_tokens=100, temperature=0.7)
    assert _cache_key(model="m2", system="s", user="u", max_tokens=100, temperature=0.7) != base
    assert _cache_key(model="m", system="s2", user="u", max_tokens=100, temperature=0.7) != base
    assert _cache_key(model="m", system="s", user="u2", max_tokens=100, temperature=0.7) != base
    assert _cache_key(model="m", system="s", user="u", max_tokens=200, temperature=0.7) != base
    assert _cache_key(model="m", system="s", user="u", max_tokens=100, temperature=0.8) != base


# ── _extract_completion_text ───────────────────────────────────────────────


def test_extract_completion_text_with_usage() -> None:
    c = _make_completion("hello", p=42, c=17)
    text, p, q = _extract_completion_text(c)
    assert text == "hello"
    assert p == 42
    assert q == 17


def test_extract_completion_text_missing_usage() -> None:
    c = _FakeCompletion(choices=[_FakeChoice(message=_FakeMessage(content="hi"))], usage=None)
    text, p, q = _extract_completion_text(c)
    assert text == "hi"
    assert p == 0
    assert q == 0


def test_extract_completion_text_malformed() -> None:
    # No choices at all → returns ('', 0, 0)
    c = _FakeCompletion(choices=[], usage=None)
    text, p, q = _extract_completion_text(c)
    assert text == ""
    assert p == 0
    assert q == 0


# ── Bypass paths ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bypass_when_disabled_via_env() -> None:
    cache = _new_cache(narrcache_enabled=False)
    client = _FakeClient([_make_completion("a tavern, warm and quiet")])

    out = await cache.acompletion(
        client, model="ShoeGPT", messages=_MSGS, max_tokens=100, temperature=0.7
    )
    assert out.choices[0].message.content == "a tavern, warm and quiet"
    assert client.call_count == 1
    snap = cache.metrics_snapshot()
    assert snap.bypass_count == 1
    assert snap.hits == 0
    assert snap.misses == 0
    assert snap.size == 0


@pytest.mark.asyncio
async def test_bypass_when_runtime_disabled() -> None:
    cache = _new_cache()
    cache._runtime_disabled = True  # mimic Plan 18-02 runtime override
    client = _FakeClient([_make_completion("the tavern is warm")])

    await cache.acompletion(
        client, model="ShoeGPT", messages=_MSGS, max_tokens=100, temperature=0.7
    )
    assert cache.metrics_snapshot().bypass_count == 1


@pytest.mark.asyncio
async def test_bypass_when_messages_not_two() -> None:
    cache = _new_cache()
    client = _FakeClient([_make_completion("a"), _make_completion("b")])
    bad_messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "history"},
    ]
    await cache.acompletion(
        client, model="m", messages=bad_messages, max_tokens=10, temperature=0.7
    )
    snap = cache.metrics_snapshot()
    assert snap.bypass_count == 1
    assert snap.size == 0


# ── HIT path ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_miss_then_hit() -> None:
    cache = _new_cache()
    # Only ONE scripted response — the second call MUST come from cache.
    client = _FakeClient([_make_completion("The tavern smells of hearthsmoke.")])

    a = await cache.acompletion(
        client, model="ShoeGPT", messages=_MSGS, max_tokens=100, temperature=0.7
    )
    b = await cache.acompletion(
        client, model="ShoeGPT", messages=_MSGS, max_tokens=100, temperature=0.7
    )
    assert a is b  # identity: same cached completion object
    assert client.call_count == 1
    snap = cache.metrics_snapshot()
    assert snap.hits == 1
    assert snap.misses == 1
    assert snap.size == 1


# ── MISS path: store-gate rejects mechanical text ───────────────────────────


@pytest.mark.asyncio
async def test_miss_rejects_storage_when_gate_rejects() -> None:
    cache = _new_cache()
    # Response is mechanical ("8 damage") → gate rejects → must NOT store.
    leaky = _make_completion("The orc's axe deals 8 damage.")
    client = _FakeClient([leaky, _make_completion("safer second")])

    await cache.acompletion(
        client, model="ShoeGPT", messages=_MSGS, max_tokens=100, temperature=0.7
    )
    snap = cache.metrics_snapshot()
    assert snap.misses == 1
    assert snap.rejected_by_gate_store == 1
    assert snap.size == 0  # NOT stored

    # Second call hits upstream again (cache empty).
    await cache.acompletion(
        client, model="ShoeGPT", messages=_MSGS, max_tokens=100, temperature=0.7
    )
    assert client.call_count == 2


# ── Double-gate: HIT re-gate rejects when gate tightens ────────────────────


@pytest.mark.asyncio
async def test_hit_rejects_serve_if_gate_tightens(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _new_cache()
    safe_text = "A merchant nods politely as you pass."
    completion = _make_completion(safe_text)
    client = _FakeClient([completion, _make_completion("fresh upstream")])

    # First call → MISS → store (gate accepts).
    await cache.acompletion(
        client, model="ShoeGPT", messages=_MSGS, max_tokens=100, temperature=0.7
    )
    assert cache.metrics_snapshot().size == 1

    # Simulate gate-tightening: monkeypatch the gate to reject the stored text.
    def tightened(_text: str) -> bool:
        return False  # reject everything

    monkeypatch.setattr(NarrCacheGate, "is_pure_narration", staticmethod(tightened))

    # Second call → would-be HIT, but gate rejects on serve → MISS path.
    out = await cache.acompletion(
        client, model="ShoeGPT", messages=_MSGS, max_tokens=100, temperature=0.7
    )
    snap = cache.metrics_snapshot()
    assert snap.rejected_by_gate_serve == 1
    assert snap.hits == 0
    assert snap.misses == 2  # both MISS-paths
    # Cache evicted entry; upstream returned the "fresh upstream" completion
    # but then gate also rejected on store, so size stays 0.
    assert out.choices[0].message.content == "fresh upstream"
    assert snap.size == 0


# ── LRU eviction ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lru_eviction_at_size_limit() -> None:
    cache = _new_cache(narrcache_l1_size=2)
    msgs_a = [_MSGS[0], {"role": "user", "content": "describe A"}]
    msgs_b = [_MSGS[0], {"role": "user", "content": "describe B"}]
    msgs_c = [_MSGS[0], {"role": "user", "content": "describe C"}]
    client = _FakeClient(
        [
            _make_completion("A tale."),
            _make_completion("B tale."),
            _make_completion("C tale."),
            _make_completion("A again."),  # in case A is evicted
        ]
    )
    await cache.acompletion(client, model="m", messages=msgs_a, max_tokens=10, temperature=0.7)
    await cache.acompletion(client, model="m", messages=msgs_b, max_tokens=10, temperature=0.7)
    await cache.acompletion(client, model="m", messages=msgs_c, max_tokens=10, temperature=0.7)
    # A is the LRU and should have been evicted.
    assert cache.size == 2

    # Re-fetching A is a MISS (it was evicted), so upstream is called again.
    pre = client.call_count
    await cache.acompletion(client, model="m", messages=msgs_a, max_tokens=10, temperature=0.7)
    assert client.call_count == pre + 1


# ── TTL ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ttl_expiry_drops_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _new_cache(narrcache_l1_ttl_s=1)
    client = _FakeClient(
        [
            _make_completion("Mist coils through the road."),
            _make_completion("Mist coils through the road (fresh)."),
        ]
    )

    # Use a settable clock so we never run out of values across however many
    # internal time.monotonic() calls the cache makes.
    clock = {"t": 100.0}
    monkeypatch.setattr(
        "eldritch_dm.observability.narration_cache.time.monotonic",
        lambda: clock["t"],
    )
    await cache.acompletion(client, model="m", messages=_MSGS, max_tokens=10, temperature=0.7)
    assert cache.metrics_snapshot().size == 1

    # Advance the clock 100s — TTL is 1s, so the entry is expired → MISS.
    clock["t"] = 200.0
    await cache.acompletion(client, model="m", messages=_MSGS, max_tokens=10, temperature=0.7)
    snap = cache.metrics_snapshot()
    assert snap.misses == 2
    assert snap.hits == 0


# ── asyncio.Lock smoke (two concurrent calls do not corrupt state) ──────────


@pytest.mark.asyncio
async def test_concurrent_get_does_not_corrupt_l1() -> None:
    cache = _new_cache()
    # Two distinct cache keys to ensure concurrent inserts go through.
    msgs_a = [_MSGS[0], {"role": "user", "content": "describe A"}]
    msgs_b = [_MSGS[0], {"role": "user", "content": "describe B"}]
    client = _FakeClient([_make_completion("A tale."), _make_completion("B tale.")])

    async def call(msgs: list[dict[str, str]]) -> Any:
        return await cache.acompletion(
            client, model="m", messages=msgs, max_tokens=10, temperature=0.7
        )

    results = await asyncio.gather(call(msgs_a), call(msgs_b))
    assert len(results) == 2
    assert cache.size == 2


# ── reset_for_tests / metrics_snapshot ──────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_for_tests_clears_counters_and_l1() -> None:
    cache = _new_cache()
    client = _FakeClient([_make_completion("Pretty narrative.")])
    await cache.acompletion(client, model="m", messages=_MSGS, max_tokens=10, temperature=0.7)
    assert cache.size == 1

    cache.reset_for_tests()
    snap = cache.metrics_snapshot()
    assert snap.size == 0
    assert snap.misses == 0
    assert snap.hits == 0


def test_metrics_snapshot_is_immutable() -> None:
    cache = _new_cache()
    snap = cache.metrics_snapshot()
    # NarrCacheMetrics has frozen=True; field assignment raises.
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        snap.hits = 99  # type: ignore[misc]


# ── Internal coverage ──────────────────────────────────────────────────────


def test_l1_is_ordered_dict() -> None:
    cache = _new_cache()
    assert isinstance(cache._l1, OrderedDict)
