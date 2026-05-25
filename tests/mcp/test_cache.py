"""
Tests for MCPCache (Phase 16 / MCPCACHE-01/02).

Covers: args_hash stability, allow-list bypass, L1 hits/misses, LRU
eviction, TTL expiry, master-switch bypass, error propagation, L2
default-off behavior, L2 cross-instance persistence, L2 TTL expiry.

Uses respx to mock the dm20 MCP HTTP endpoint — zero real network traffic.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx

from eldritch_dm.config import Settings, get_settings
from eldritch_dm.mcp.cache import CACHEABLE_TOOLS, MCPCache, _args_hash
from eldritch_dm.mcp.client import MCPClient
from eldritch_dm.mcp.errors import MCPToolError

BASE_URL = "http://localhost:8765"
MCP_URL = f"{BASE_URL}/v1/mcp/execute"


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def env_base(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Reset settings cache and set a minimal env. Tests override individual vars."""
    get_settings.cache_clear()
    monkeypatch.setenv("DISCORD_TOKEN", "t")
    monkeypatch.setenv("ELDRITCH_DB_PATH", str(tmp_path / "eldritch.sqlite3"))
    # Defaults: L1 enabled, L2 disabled.
    monkeypatch.delenv("MCPCACHE_ENABLED", raising=False)
    monkeypatch.delenv("MCPCACHE_L1_SIZE", raising=False)
    monkeypatch.delenv("MCPCACHE_L1_TTL_S", raising=False)
    monkeypatch.delenv("MCPCACHE_L2_ENABLED", raising=False)
    monkeypatch.delenv("MCPCACHE_L2_TTL_S", raising=False)
    monkeypatch.delenv("MCPCACHE_L2_PATH", raising=False)
    yield
    get_settings.cache_clear()


def _make_cache(settings: Settings | None = None) -> tuple[MCPCache, MCPClient]:
    client = MCPClient(base_url=BASE_URL, http2=False)
    cache = MCPCache(client, settings=settings)
    return cache, client


def _fresh_settings() -> Settings:
    get_settings.cache_clear()
    return Settings(_env_file=None)  # type: ignore[call-arg]


# ── args_hash stability ──────────────────────────────────────────────────────


def test_args_hash_order_independent() -> None:
    """Key order in the dict must not affect the hash (sorted JSON)."""
    a = _args_hash({"a": 1, "b": 2})
    b = _args_hash({"b": 2, "a": 1})
    assert a == b


def test_args_hash_value_sensitive() -> None:
    """Different values → different hashes."""
    assert _args_hash({"class_name": "wizard"}) != _args_hash({"class_name": "cleric"})


def test_args_hash_stable_across_processes() -> None:
    """SHA-256(canonical-json) must be PYTHONHASHSEED-independent.

    Spawn a subprocess with a random hash seed and check the hash matches.
    """
    parent = _args_hash({"class_name": "wizard", "subclass": "evoker"})
    script = (
        "import json, hashlib; "
        "args={'class_name':'wizard','subclass':'evoker'}; "
        "c=json.dumps(args, sort_keys=True, separators=(',',':')); "
        "print(hashlib.sha256(c.encode()).hexdigest())"
    )
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "12345"
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True
    )
    child = result.stdout.strip()
    assert parent == child


# ── Allow-list / bypass behavior ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "tool_name",
    [
        "dm20__create_character",
        "dm20__update_character",
        "dm20__apply_effect",
        "dm20__start_combat",
        "dm20__next_turn",
        "dm20__remove_effect",
        "dm20__combat_action",
        "dm20__get_character",  # mutable-state read — must bypass
        "dm20__get_game_state",  # mutable-state read — must bypass
        "dm20__list_characters",  # mutable-state read — must bypass
        "dice__dice_roll",  # RNG — must bypass
    ],
)
@respx.mock
async def test_bypass_for_non_cacheable_tools(
    env_base: None, tool_name: str
) -> None:
    """Mutations, mutable-state reads, and RNG all bypass the cache."""
    route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": 1}))
    cache, client = _make_cache(_fresh_settings())
    try:
        # Two identical calls — both must hit HTTP because tool is not in allow-list.
        await cache.call(tool_name, x=1)
        await cache.call(tool_name, x=1)
        assert route.call_count == 2
        assert cache.bypass_count == 2
        assert cache.l1_hits == 0
        assert cache.l1_misses == 0
    finally:
        await cache.aclose()
        await client.aclose()


def test_allow_list_excludes_mutable_state_reads() -> None:
    """Sanity: the allow-list must NOT include known mutable-state read tools.

    Adding any of these without per-mutation invalidation breaks D-117.
    """
    forbidden = {
        "dm20__get_character",
        "dm20__get_npc",
        "dm20__get_game_state",
        "dm20__get_party_status",
        "dm20__list_characters",
        "dm20__get_claudmaster_session_state",
        "dm20__validate_character_rules",
        "dice__dice_roll",
    }
    assert CACHEABLE_TOOLS.isdisjoint(forbidden), (
        "Allow-list must not include mutable-state reads (D-117 mechanical honesty)."
    )


# ── Cache HIT / MISS for cacheable tools ─────────────────────────────────────


@respx.mock
async def test_cache_hit_for_get_class_info(env_base: None) -> None:
    """Second identical call returns cached value without hitting HTTP."""
    payload = {"class": "wizard", "hit_die": "d6"}
    route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json=payload))
    cache, client = _make_cache(_fresh_settings())
    try:
        r1 = await cache.call("dm20__get_class_info", class_name="wizard")
        r2 = await cache.call("dm20__get_class_info", class_name="wizard")
        assert r1 == payload
        assert r2 == payload
        assert route.call_count == 1
        assert cache.l1_hits == 1
        assert cache.l1_misses == 1
        assert cache.bypass_count == 0
    finally:
        await cache.aclose()
        await client.aclose()


@respx.mock
async def test_cache_hit_for_dnd_search(env_base: None) -> None:
    payload = {"results": ["Fireball"]}
    route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json=payload))
    cache, client = _make_cache(_fresh_settings())
    try:
        await cache.call("dnd__search_all_categories", query="fireball")
        await cache.call("dnd__search_all_categories", query="fireball")
        assert route.call_count == 1
    finally:
        await cache.aclose()
        await client.aclose()


@respx.mock
async def test_different_args_different_entries(env_base: None) -> None:
    """Different arguments produce two distinct cache entries."""
    payload_a = {"class": "wizard"}
    payload_b = {"class": "cleric"}

    def _responder(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        if "wizard" in body:
            return httpx.Response(200, json=payload_a)
        return httpx.Response(200, json=payload_b)

    respx.post(MCP_URL).mock(side_effect=_responder)
    cache, client = _make_cache(_fresh_settings())
    try:
        a = await cache.call("dm20__get_class_info", class_name="wizard")
        b = await cache.call("dm20__get_class_info", class_name="cleric")
        a2 = await cache.call("dm20__get_class_info", class_name="wizard")
        b2 = await cache.call("dm20__get_class_info", class_name="cleric")
        assert a == a2 == payload_a
        assert b == b2 == payload_b
        assert cache.l1_size == 2
        assert cache.l1_hits == 2
        assert cache.l1_misses == 2
    finally:
        await cache.aclose()
        await client.aclose()


# ── L1 eviction & TTL ────────────────────────────────────────────────────────


@respx.mock
async def test_l1_lru_eviction(
    env_base: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When L1 exceeds maxsize, the LRU entry is evicted."""
    monkeypatch.setenv("MCPCACHE_L1_SIZE", "2")
    s = _fresh_settings()
    # Distinct responses per arg
    respx.post(MCP_URL).mock(
        side_effect=lambda req: httpx.Response(200, json={"got": req.read().decode()})
    )
    cache, client = _make_cache(s)
    try:
        await cache.call("dm20__get_class_info", class_name="a")
        await cache.call("dm20__get_class_info", class_name="b")
        await cache.call("dm20__get_class_info", class_name="c")
        # Three entries inserted, max is 2 → "a" should be evicted.
        assert cache.l1_size == 2
        # Re-fetch "a" → MISS (evicted) → inner called again.
        before = cache.l1_misses
        await cache.call("dm20__get_class_info", class_name="a")
        assert cache.l1_misses == before + 1
    finally:
        await cache.aclose()
        await client.aclose()


@respx.mock
async def test_l1_ttl_expiry(
    env_base: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Entries past TTL are dropped on read and treated as MISS."""
    monkeypatch.setenv("MCPCACHE_L1_TTL_S", "1")
    s = _fresh_settings()
    route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    cache, client = _make_cache(s)
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        await cache.call("dm20__get_class_info", class_name="wizard")
        assert route.call_count == 1  # HIT
        # Sleep past TTL.
        await asyncio.sleep(1.05)
        await cache.call("dm20__get_class_info", class_name="wizard")
        assert route.call_count == 2  # MISS after TTL expiry
        assert cache.l1_misses == 2
    finally:
        await cache.aclose()
        await client.aclose()


# ── Master switch ────────────────────────────────────────────────────────────


@respx.mock
async def test_master_switch_disables_cache(
    env_base: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCPCACHE_ENABLED=false: even allow-list tools always hit HTTP."""
    monkeypatch.setenv("MCPCACHE_ENABLED", "false")
    s = _fresh_settings()
    route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    cache, client = _make_cache(s)
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        await cache.call("dm20__get_class_info", class_name="wizard")
        assert route.call_count == 2
        assert cache.bypass_count == 2
        assert cache.l1_hits == 0
    finally:
        await cache.aclose()
        await client.aclose()


# ── Error propagation ────────────────────────────────────────────────────────


@respx.mock
async def test_inner_raises_propagates_and_caches_nothing(env_base: None) -> None:
    """When inner raises MCPToolError, no L1 entry is stored; next call retries."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(400, json={"error": "bad"}))
    cache, client = _make_cache(_fresh_settings())
    try:
        with pytest.raises(MCPToolError):
            await cache.call("dm20__get_class_info", class_name="wizard")
        assert cache.l1_size == 0
        with pytest.raises(MCPToolError):
            await cache.call("dm20__get_class_info", class_name="wizard")
    finally:
        await cache.aclose()
        await client.aclose()


# ── L2 ───────────────────────────────────────────────────────────────────────


@respx.mock
async def test_l2_disabled_by_default(env_base: None, tmp_path: Path) -> None:
    """No SQLite file is created when L2 is disabled."""
    db_file = tmp_path / "mcp_cache.sqlite"
    # Default settings have L2 disabled; just sanity-check no I/O.
    s = _fresh_settings()
    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    cache, client = _make_cache(s)
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        assert not db_file.exists()
    finally:
        await cache.aclose()
        await client.aclose()


@respx.mock
async def test_l2_persists_across_instances(
    env_base: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With L2 enabled, value survives across MCPCache instances on the same DB."""
    db_file = tmp_path / "mcp_cache.sqlite"
    monkeypatch.setenv("MCPCACHE_L2_ENABLED", "true")
    monkeypatch.setenv("MCPCACHE_L2_PATH", str(db_file))
    s = _fresh_settings()
    route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))

    # Instance A: populate.
    cache_a, client_a = _make_cache(s)
    try:
        await cache_a.call("dm20__get_class_info", class_name="wizard")
        assert db_file.exists()
        assert route.call_count == 1
    finally:
        await cache_a.aclose()
        await client_a.aclose()

    # Instance B: same DB, fresh L1 — first call should be L2 HIT (no new HTTP).
    s2 = _fresh_settings()
    cache_b, client_b = _make_cache(s2)
    try:
        before = route.call_count
        result = await cache_b.call("dm20__get_class_info", class_name="wizard")
        assert result == {"v": 1}
        assert route.call_count == before  # No new HTTP call
        assert cache_b.l2_hits == 1
    finally:
        await cache_b.aclose()
        await client_b.aclose()


@respx.mock
async def test_l2_ttl_expiry(
    env_base: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Past L2 TTL: row is dropped on read; new instance gets MISS."""
    db_file = tmp_path / "mcp_cache.sqlite"
    monkeypatch.setenv("MCPCACHE_L2_ENABLED", "true")
    monkeypatch.setenv("MCPCACHE_L2_TTL_S", "1")
    monkeypatch.setenv("MCPCACHE_L2_PATH", str(db_file))
    s = _fresh_settings()
    route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))

    cache_a, client_a = _make_cache(s)
    try:
        await cache_a.call("dm20__get_class_info", class_name="wizard")
    finally:
        await cache_a.aclose()
        await client_a.aclose()

    # Sleep past TTL. Use 2.1s because L2 created_ts and now both go through
    # int(time.time()) — a 1.05s wall-clock gap can produce a 1-second integer
    # diff which is NOT strictly greater than ttl=1.
    await asyncio.sleep(2.1)

    s2 = _fresh_settings()
    cache_b, client_b = _make_cache(s2)
    try:
        before = route.call_count
        await cache_b.call("dm20__get_class_info", class_name="wizard")
        assert route.call_count == before + 1  # L2 expired → MISS → HTTP call
        assert cache_b.l2_misses == 1
    finally:
        await cache_b.aclose()
        await client_b.aclose()


# ── Misc ─────────────────────────────────────────────────────────────────────


@respx.mock
async def test_reset_counters(env_base: None) -> None:
    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    cache, client = _make_cache(_fresh_settings())
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        await cache.call("dm20__get_class_info", class_name="wizard")
        assert cache.l1_hits == 1
        assert cache.l1_misses == 1
        cache.reset_counters()
        assert cache.l1_hits == 0
        assert cache.l1_misses == 0
        # Storage untouched — next call is still HIT.
        await cache.call("dm20__get_class_info", class_name="wizard")
        assert cache.l1_hits == 1
    finally:
        await cache.aclose()
        await client.aclose()


def test_cacheable_tools_is_frozenset() -> None:
    """CACHEABLE_TOOLS is a frozenset (immutable) — defensive type check."""
    assert isinstance(CACHEABLE_TOOLS, frozenset)


def test_cacheable_tools_membership_snapshot() -> None:
    """Pin the allow-list contents so accidental additions trip a test.

    Updating this set REQUIRES updating 16-01-SUMMARY.md and reviewing
    D-117 mechanical-honesty implications.
    """
    assert CACHEABLE_TOOLS == frozenset(
        {
            "dm20__get_class_info",
            "dm20__get_race_info",
            "dm20__list_campaigns",
            "dm20__get_campaign_info",
            "dnd__search_all_categories",
            "dnd__verify_with_api",
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plan 16-02 — invalidation + schema-version polling + KPI emission
# ─────────────────────────────────────────────────────────────────────────────


from eldritch_dm.mcp.cache import MCPCacheMetrics  # noqa: E402  (post-snapshot tests)
from eldritch_dm.observability import span_buffer as _span_buffer  # noqa: E402


@pytest.fixture
def isolated_span_buffer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point the span buffer at a tmp file and reset it before each test."""
    monkeypatch.setenv("ELDRITCH_SPAN_BUFFER_PATH", str(tmp_path / "spans.sqlite"))
    _span_buffer.reset_for_tests()
    yield
    _span_buffer.reset_for_tests()


# ── invalidate() ─────────────────────────────────────────────────────────────


@respx.mock
async def test_invalidate_all_clears_both_layers(
    env_base: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MCPCACHE_L2_ENABLED", "true")
    monkeypatch.setenv("MCPCACHE_L2_PATH", str(tmp_path / "mcp_cache.sqlite"))
    s = _fresh_settings()
    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    cache, client = _make_cache(s)
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        await cache.call("dm20__get_class_info", class_name="cleric")
        assert cache.l1_size == 2
        snap_before = await cache.metrics_snapshot()
        assert snap_before.size_l1 == 2
        assert snap_before.size_l2 == 2

        removed = await cache.invalidate()
        # L1 + L2 each had 2 entries → 4 total removals.
        assert removed == 4
        snap_after = await cache.metrics_snapshot()
        assert snap_after.size_l1 == 0
        assert snap_after.size_l2 == 0
        assert snap_after.invalidations_total == 1
    finally:
        await cache.aclose()
        await client.aclose()


@respx.mock
async def test_invalidate_by_tool_only_clears_that_tool(env_base: None) -> None:
    """Invalidating one tool must leave entries for other tools intact."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    cache, client = _make_cache(_fresh_settings())
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        await cache.call("dm20__get_race_info", race="elf")
        assert cache.l1_size == 2
        removed = await cache.invalidate(tool_name="dm20__get_class_info")
        assert removed == 1
        assert cache.l1_size == 1  # get_race_info entry survives
    finally:
        await cache.aclose()
        await client.aclose()


@respx.mock
async def test_invalidate_by_tool_and_args_single_entry(env_base: None) -> None:
    """Invalidating a specific (tool, args) leaves siblings intact."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    cache, client = _make_cache(_fresh_settings())
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        await cache.call("dm20__get_class_info", class_name="cleric")
        assert cache.l1_size == 2
        removed = await cache.invalidate(
            tool_name="dm20__get_class_info", args={"class_name": "wizard"}
        )
        assert removed == 1
        assert cache.l1_size == 1
    finally:
        await cache.aclose()
        await client.aclose()


@respx.mock
async def test_invalidate_args_without_tool_raises(env_base: None) -> None:
    """Calling invalidate(args=...) without tool_name is a programmer error."""
    cache, client = _make_cache(_fresh_settings())
    try:
        with pytest.raises(ValueError):
            await cache.invalidate(args={"class_name": "wizard"})
    finally:
        await cache.aclose()
        await client.aclose()


# ── Schema-version poller ────────────────────────────────────────────────────


@respx.mock
async def test_schema_version_poller_wipes_on_change(env_base: None) -> None:
    """On version change the poller invalidates everything."""
    # Two different tool routes:
    #   dm20__get_class_info → cacheable data
    #   dm20__schema_version → control plane

    state = {"calls": 0}

    def _responder(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        if "dm20__schema_version" in body:
            state["calls"] += 1
            # First call: v1; subsequent: v2 (triggers wipe).
            version = "1" if state["calls"] == 1 else "2"
            return httpx.Response(200, json={"version": version})
        return httpx.Response(200, json={"v": 1})

    respx.post(MCP_URL).mock(side_effect=_responder)
    cache, client = _make_cache(_fresh_settings())
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        assert cache.l1_size == 1

        task = cache.start_schema_version_poller(client, interval_s=0.05)
        # Wait long enough for the second poll (>0.05s) to fire and detect
        # the change, then invalidate.
        await asyncio.sleep(0.25)
        await cache.stop_schema_version_poller()
        assert task.done()

        assert cache.l1_size == 0
        snap = await cache.metrics_snapshot()
        assert snap.invalidations_total >= 1
    finally:
        await cache.aclose()
        await client.aclose()


@respx.mock
async def test_schema_version_poller_disables_on_404(env_base: None) -> None:
    """If dm20__schema_version returns 4xx, the poller exits cleanly."""
    def _responder(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        if "dm20__schema_version" in body:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json={"v": 1})

    respx.post(MCP_URL).mock(side_effect=_responder)
    cache, client = _make_cache(_fresh_settings())
    try:
        task = cache.start_schema_version_poller(client, interval_s=0.05)
        # Initial call 404s → task should exit on its own within a few ms.
        await asyncio.sleep(0.1)
        assert task.done()
        # Subsequent cacheable calls still work normally.
        result = await cache.call("dm20__get_class_info", class_name="wizard")
        assert result == {"v": 1}
    finally:
        await cache.aclose()
        await client.aclose()


@respx.mock
async def test_stop_poller_is_idempotent(env_base: None) -> None:
    """Calling stop without start, or twice, must not raise."""
    cache, client = _make_cache(_fresh_settings())
    try:
        await cache.stop_schema_version_poller()  # never started
        await cache.stop_schema_version_poller()  # again
    finally:
        await cache.aclose()
        await client.aclose()


# ── Metrics snapshot ─────────────────────────────────────────────────────────


@respx.mock
async def test_metrics_snapshot_shape(env_base: None) -> None:
    """metrics_snapshot returns a frozen MCPCacheMetrics with correct counts."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    cache, client = _make_cache(_fresh_settings())
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")  # MISS
        await cache.call("dm20__get_class_info", class_name="wizard")  # HIT
        await cache.call("dm20__create_character", x=1)  # BYPASS
        snap = await cache.metrics_snapshot()
        assert isinstance(snap, MCPCacheMetrics)
        assert snap.hits_l1 == 1
        assert snap.misses_l1 == 1
        assert snap.bypass_count == 1
        assert snap.size_l1 == 1
        assert snap.size_l2 == -1  # L2 disabled sentinel
        assert snap.invalidations_total == 0
    finally:
        await cache.aclose()
        await client.aclose()


# ── KPI span emission ────────────────────────────────────────────────────────


@respx.mock
async def test_traced_span_emitted_per_call(
    env_base: None, isolated_span_buffer: None
) -> None:
    """One eldritch.mcp.cache span per call; layer attr reflects path."""
    from datetime import UTC, datetime, timedelta

    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    cache, client = _make_cache(_fresh_settings())
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")  # miss
        await cache.call("dm20__get_class_info", class_name="wizard")  # l1
        await cache.call("dm20__create_character", x=1)  # bypass
    finally:
        await cache.aclose()
        await client.aclose()

    buf = _span_buffer.init_buffer()
    buf.flush(timeout_s=1.0)
    now = datetime.now(UTC)
    rows = buf.query(
        since=now - timedelta(seconds=10),
        until=now + timedelta(seconds=1),
        span_name="eldritch.mcp.cache",
    )
    assert len(rows) == 3
    layers = sorted([r.driver_path for r in rows])
    # Mapping: driver_path holds the layer name.
    assert layers == ["bypass", "l1", "miss"]
    # Every row stamps the tool_name in the `model` column.
    tool_names = {r.model for r in rows}
    assert "dm20__get_class_info" in tool_names
    assert "dm20__create_character" in tool_names


@respx.mock
async def test_invalidation_span_emitted(
    env_base: None, isolated_span_buffer: None
) -> None:
    """invalidate() writes one eldritch.mcp.cache.invalidation row."""
    from datetime import UTC, datetime, timedelta

    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    cache, client = _make_cache(_fresh_settings())
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        await cache.invalidate()  # scope='all', removed=1
    finally:
        await cache.aclose()
        await client.aclose()

    buf = _span_buffer.init_buffer()
    buf.flush(timeout_s=1.0)
    now = datetime.now(UTC)
    rows = buf.query(
        since=now - timedelta(seconds=10),
        until=now + timedelta(seconds=1),
        span_name="eldritch.mcp.cache.invalidation",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.driver_path == "all"  # scope mapped onto driver_path
    assert row.combat_round == 1  # entries_removed mapped onto combat_round


