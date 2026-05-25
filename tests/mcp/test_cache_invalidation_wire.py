"""Integration tests for the Phase 16 → Phase 17 invalidation wire (OPQOL-03).

When the dm20 schema_version bumps, the MCP cache schema poller wipes the
MCP cache AND invokes ``on_schema_change`` to wipe the character cache. If
either side fails, the other still runs and a ``eligible.cache.partial_wipe``
log is emitted (D-171/172). Partial-wipe is NOT a fatal error.

Uses respx to mock the dm20 endpoint and a tmp-path CharacterCacheRepo with
its own aiosqlite DB.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from eldritch_dm.config import Settings, get_settings
from eldritch_dm.mcp.cache import MCPCache
from eldritch_dm.mcp.client import MCPClient
from eldritch_dm.persistence.character_cache import CharacterCacheRepo

BASE_URL = "http://localhost:8765"
MCP_URL = f"{BASE_URL}/v1/mcp/execute"


@pytest.fixture
def env_base(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DISCORD_TOKEN", "t")
    monkeypatch.setenv("ELDRITCH_DB_PATH", str(tmp_path / "eldritch.sqlite3"))
    monkeypatch.setenv("CHARCACHE_PATH", str(tmp_path / "char_cache.sqlite"))
    monkeypatch.delenv("MCPCACHE_ENABLED", raising=False)
    monkeypatch.delenv("MCPCACHE_L2_ENABLED", raising=False)
    yield
    get_settings.cache_clear()


def _fresh_settings() -> Settings:
    get_settings.cache_clear()
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _make_cache_and_client(settings: Settings) -> tuple[MCPCache, MCPClient]:
    client = MCPClient(base_url=BASE_URL, http2=False)
    cache = MCPCache(client, settings=settings)
    return cache, client


async def _seed_character_cache(repo: CharacterCacheRepo) -> None:
    """Place ONE entry in the character cache via get_or_fetch."""

    async def fetcher(_cid: str) -> dict[str, Any]:
        return {
            "id": "char-1",
            "name": "Tester",
            "race": "Human",
            "character_class": "Fighter",
            "subclass": "Battle Master",
            "level": 1,
            "proficiency_bonus": 2,
            "max_hp": 12,
            "base_stats": {"STR": 16, "DEX": 14, "CON": 14, "INT": 10, "WIS": 12, "CHA": 8},
            "base_ac": 16,
            "base_speed": 30,
        }

    await repo.get_or_fetch("char-1", fetcher)


def _schema_responder_v1_then_v2() -> Any:
    state = {"calls": 0}

    def _responder(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        if "dm20__schema_version" in body:
            state["calls"] += 1
            version = "1" if state["calls"] == 1 else "2"
            return httpx.Response(200, json={"version": version})
        return httpx.Response(200, json={"v": 1})

    return _responder


# ── 1: schema change wipes BOTH caches ──────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_schema_change_wipes_both_caches(
    env_base: None, tmp_path: Path
) -> None:
    respx.post(MCP_URL).mock(side_effect=_schema_responder_v1_then_v2())
    settings = _fresh_settings()
    cache, client = _make_cache_and_client(settings)
    repo = CharacterCacheRepo(
        settings=settings, path=str(tmp_path / "char.sqlite")
    )
    try:
        # Seed MCP cache.
        await cache.call("dm20__get_class_info", class_name="wizard")
        assert cache.l1_size == 1
        # Seed character cache.
        await _seed_character_cache(repo)
        snap_before = await repo.metrics_snapshot()
        assert snap_before.size == 1

        # Start poller wired to repo.purge_all
        task = cache.start_schema_version_poller(
            client, interval_s=0.05, on_schema_change=repo.purge_all
        )
        # Wait long enough for the version change to be detected.
        for _ in range(40):
            if cache.l1_size == 0:
                snap_now = await repo.metrics_snapshot()
                if snap_now.size == 0:
                    break
            await asyncio.sleep(0.05)
        await cache.stop_schema_version_poller()
        assert task.done()

        assert cache.l1_size == 0
        snap_after = await repo.metrics_snapshot()
        assert snap_after.size == 0
    finally:
        await cache.aclose()
        await client.aclose()
        await repo.aclose()


# ── 2: character-cache wipe fails → MCP still cleared + partial_wipe log ────


@respx.mock
@pytest.mark.asyncio
async def test_partial_wipe_character_cache_fails_logs_continue(
    env_base: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(MCP_URL).mock(side_effect=_schema_responder_v1_then_v2())
    settings = _fresh_settings()
    cache, client = _make_cache_and_client(settings)

    async def boom_purge() -> int:
        raise RuntimeError("simulated disk full")

    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        assert cache.l1_size == 1

        task = cache.start_schema_version_poller(
            client, interval_s=0.05, on_schema_change=boom_purge
        )
        # Wait for at least one detected change.
        for _ in range(40):
            if cache.l1_size == 0:
                break
            await asyncio.sleep(0.05)
        await cache.stop_schema_version_poller()
        assert task.done()

        # MCP wipe happened (poller succeeded on its side)
        assert cache.l1_size == 0
        # Partial_wipe log captured with mcp_cleared=True via structlog stdout.
        captured = capsys.readouterr()
        assert "eldritch.cache.partial_wipe" in captured.out
        assert "mcp_cleared=True" in captured.out
        assert "secondary_error_type=RuntimeError" in captured.out
    finally:
        await cache.aclose()
        await client.aclose()


# ── 3: MCP wipe fails → character cache STILL wiped + partial_wipe log ──────


@respx.mock
@pytest.mark.asyncio
async def test_partial_wipe_mcp_fails_character_still_wiped(
    env_base: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(MCP_URL).mock(side_effect=_schema_responder_v1_then_v2())
    settings = _fresh_settings()
    cache, client = _make_cache_and_client(settings)
    repo = CharacterCacheRepo(
        settings=settings, path=str(tmp_path / "char.sqlite")
    )

    # Make the L1 clear raise. The OrderedDict is replaced with a subclass
    # whose `clear()` blows up — this is the simplest hook into the failure
    # path in _poll_schema_version's MCP-wipe try block.
    class ExplodingL1(type(cache._l1)):
        def clear(self) -> None:
            raise OSError("simulated mmap failure")

    cache._l1 = ExplodingL1(cache._l1)

    try:
        await _seed_character_cache(repo)
        assert (await repo.metrics_snapshot()).size == 1

        task = cache.start_schema_version_poller(
            client, interval_s=0.05, on_schema_change=repo.purge_all
        )
        # Wait for the version-change loop iteration to fire at least once.
        for _ in range(40):
            snap = await repo.metrics_snapshot()
            if snap.size == 0:
                break
            await asyncio.sleep(0.05)
        await cache.stop_schema_version_poller()
        assert task.done()

        # Character cache cleared even though MCP wipe raised.
        assert (await repo.metrics_snapshot()).size == 0
        # Partial wipe logged with mcp_cleared=False via structlog stdout.
        captured = capsys.readouterr()
        assert "eldritch.cache.partial_wipe" in captured.out
        assert "mcp_cleared=False" in captured.out
        assert "primary_error_type=OSError" in captured.out
    finally:
        await cache.aclose()
        await client.aclose()
        await repo.aclose()


# ── 4: no callback → existing behavior preserved ────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_no_callback_preserves_existing_behavior(env_base: None) -> None:
    """Default on_schema_change=None must NOT log partial_wipe."""
    respx.post(MCP_URL).mock(side_effect=_schema_responder_v1_then_v2())
    settings = _fresh_settings()
    cache, client = _make_cache_and_client(settings)
    try:
        await cache.call("dm20__get_class_info", class_name="wizard")
        assert cache.l1_size == 1

        task = cache.start_schema_version_poller(client, interval_s=0.05)
        for _ in range(40):
            if cache.l1_size == 0:
                break
            await asyncio.sleep(0.05)
        await cache.stop_schema_version_poller()
        assert task.done()
        assert cache.l1_size == 0
    finally:
        await cache.aclose()
        await client.aclose()
