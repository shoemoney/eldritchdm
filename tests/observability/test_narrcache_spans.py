"""Span emission tests for traced_narrcache + _to_row mapping (Phase 18)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel as _BM

from eldritch_dm.observability import span_buffer
from eldritch_dm.observability.instrumentation import traced_narrcache
from eldritch_dm.observability.narration_cache import NarrCache
from eldritch_dm.observability.span_buffer import init_buffer, reset_for_tests


@pytest.fixture
def buffer_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    reset_for_tests()
    p = tmp_path / "spans.sqlite"
    monkeypatch.setenv("ELDRITCH_SPAN_BUFFER_PATH", str(p))
    yield p
    reset_for_tests()


def _query_narrcache_rows(path: Path) -> list[span_buffer.BufferRow]:
    buf = init_buffer(path=path)
    buf.flush(timeout_s=1.0)
    return buf.query(
        since=datetime.now(UTC) - timedelta(hours=1),
        until=datetime.now(UTC) + timedelta(minutes=1),
        span_name="eldritch.narrcache.call",
    )


# ── Test doubles ────────────────────────────────────────────────────────────


@dataclass
class _Msg:
    content: str


@dataclass
class _Choice:
    message: _Msg


@dataclass
class _Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class _Comp:
    choices: list[_Choice]
    usage: _Usage | None = None


def _comp(text: str) -> _Comp:
    return _Comp(
        choices=[_Choice(message=_Msg(content=text))],
        usage=_Usage(prompt_tokens=120, completion_tokens=80),
    )


class _Client:
    def __init__(self, responses: list[Any]) -> None:
        self._r = list(responses)
        self.chat = self

    @property
    def completions(self) -> _Client:
        return self

    async def create(self, **_kw: Any) -> Any:
        return self._r.pop(0)


class _Settings(_BM):
    narrcache_enabled: bool = True
    narrcache_l1_size: int = 256
    narrcache_l1_ttl_s: int = 3600


_MSGS = [
    {"role": "system", "content": "You are a dungeon master."},
    {"role": "user", "content": "Describe the road."},
]


# ── traced_narrcache standalone ─────────────────────────────────────────────


def test_traced_narrcache_writes_row(buffer_path: Path) -> None:
    with traced_narrcache(model="ShoeGPT") as span:
        span.set_attribute("eldritch.narrcache.layer", "miss")
        span.set_attribute("eldritch.narrcache.size", 1)
        span.set_attribute("eldritch.narrcache.latency_ms", 42)
        span.set_attribute("eldritch.tokens.input", 100)
        span.set_attribute("eldritch.tokens.output", 50)

    rows = _query_narrcache_rows(buffer_path)
    assert len(rows) == 1
    row = rows[0]
    assert row.span_name == "eldritch.narrcache.call"
    assert row.model == "ShoeGPT"
    assert row.driver_path == "miss"
    assert row.latency_ms == 42
    assert row.tokens_input == 100
    assert row.tokens_output == 50
    assert row.combat_round == 1  # size → combat_round


def test_traced_narrcache_records_savings_on_hit(buffer_path: Path) -> None:
    with traced_narrcache(model="ShoeGPT") as span:
        span.set_attribute("eldritch.narrcache.layer", "hit")
        span.set_attribute("eldritch.narrcache.size", 7)
        span.set_attribute("eldritch.narrcache.latency_ms", 2)
        span.set_attribute("eldritch.narrcache.savings_usd", 0.00042)
        span.set_attribute("eldritch.tokens.input", 0)
        span.set_attribute("eldritch.tokens.output", 0)

    rows = _query_narrcache_rows(buffer_path)
    assert len(rows) == 1
    row = rows[0]
    assert row.driver_path == "hit"
    assert row.overall_score == pytest.approx(0.00042)


# ── End-to-end NarrCache.acompletion span emission ──────────────────────────


@pytest.mark.asyncio
async def test_acompletion_emits_miss_span(buffer_path: Path) -> None:
    cache = NarrCache(settings=_Settings())
    client = _Client([_comp("The road winds north through pale grass.")])
    await cache.acompletion(client, model="ShoeGPT", messages=_MSGS, max_tokens=64, temperature=0.7)
    rows = _query_narrcache_rows(buffer_path)
    assert len(rows) == 1
    assert rows[0].driver_path == "miss"
    assert rows[0].model == "ShoeGPT"
    # tokens_in/out reflect the upstream usage
    assert rows[0].tokens_input == 120
    assert rows[0].tokens_output == 80


@pytest.mark.asyncio
async def test_acompletion_emits_hit_span_with_savings(buffer_path: Path) -> None:
    cache = NarrCache(settings=_Settings())
    client = _Client([_comp("The road winds north through pale grass.")])
    # Two identical calls; second is HIT.
    await cache.acompletion(client, model="ShoeGPT", messages=_MSGS, max_tokens=64, temperature=0.7)
    await cache.acompletion(client, model="ShoeGPT", messages=_MSGS, max_tokens=64, temperature=0.7)
    rows = _query_narrcache_rows(buffer_path)
    layers = [r.driver_path for r in rows]
    assert "miss" in layers
    assert "hit" in layers
    # The hit row should have a non-None overall_score (savings_usd reuse).
    hit_row = next(r for r in rows if r.driver_path == "hit")
    assert hit_row.overall_score is not None
    assert hit_row.overall_score >= 0.0  # ShoeGPT is $0.00 in pricing.yaml
    # tokens_in/out for HIT are 0 (no upstream call). Note: _to_row's `or`
    # fallback maps 0 → None on the input side; we accept either as the
    # "no upstream call" signal.
    assert hit_row.tokens_input in (None, 0)
    assert hit_row.tokens_output in (None, 0)


@pytest.mark.asyncio
async def test_acompletion_emits_gate_reject_store_span(buffer_path: Path) -> None:
    cache = NarrCache(settings=_Settings())
    client = _Client([_comp("The orc deals 8 damage with a heavy swing.")])
    await cache.acompletion(client, model="ShoeGPT", messages=_MSGS, max_tokens=64, temperature=0.7)
    rows = _query_narrcache_rows(buffer_path)
    assert len(rows) == 1
    assert rows[0].driver_path == "gate_reject_store"


@pytest.mark.asyncio
async def test_acompletion_emits_bypass_span_when_disabled(buffer_path: Path) -> None:
    cache = NarrCache(settings=_Settings(narrcache_enabled=False))
    client = _Client([_comp("Smoke drifts from the chimney.")])
    await cache.acompletion(client, model="ShoeGPT", messages=_MSGS, max_tokens=64, temperature=0.7)
    rows = _query_narrcache_rows(buffer_path)
    assert len(rows) == 1
    assert rows[0].driver_path == "bypass"
