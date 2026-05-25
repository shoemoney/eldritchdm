"""Tests for MonsterMemoryRepo (Phase 21 / MEM-03)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from eldritch_dm.persistence.monster_memory_repo import MonsterMemoryRepo


@pytest.fixture
async def repo(tmp_path: Path) -> Any:
    """Per-test isolated repo using a temp SQLite file."""
    r = MonsterMemoryRepo(path=tmp_path / "mm.sqlite")
    yield r
    await r.aclose()


# ── upsert / load round-trip ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_then_load_round_trip(repo: MonsterMemoryRepo) -> None:
    snap = {
        "damage_dealt_by": {"pc1": 12},
        "concentrating_on": {"pc1": "Hypnotic Pattern"},
        "marked_dangerous": ["pc1"],
    }
    await repo.upsert("c1", "s1", "m1", snap)
    loaded = await repo.load("c1", "s1", "m1")
    assert loaded == snap


@pytest.mark.asyncio
async def test_load_missing_returns_none(repo: MonsterMemoryRepo) -> None:
    assert await repo.load("c1", "s1", "missing") is None


@pytest.mark.asyncio
async def test_upsert_overwrites_existing(repo: MonsterMemoryRepo) -> None:
    await repo.upsert("c1", "s1", "m1", {"damage_dealt_by": {"pc1": 5}})
    await repo.upsert("c1", "s1", "m1", {"damage_dealt_by": {"pc1": 50}})
    loaded = await repo.load("c1", "s1", "m1")
    assert loaded == {"damage_dealt_by": {"pc1": 50}}


# ── load_all_for_session ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_all_for_session(repo: MonsterMemoryRepo) -> None:
    await repo.upsert("c", "s", "m1", {"damage_dealt_by": {"pc1": 1}})
    await repo.upsert("c", "s", "m2", {"damage_dealt_by": {"pc2": 2}})
    await repo.upsert("c", "other_sess", "m3", {"damage_dealt_by": {"pc3": 3}})

    out = await repo.load_all_for_session("c", "s")
    assert set(out.keys()) == {"m1", "m2"}
    assert out["m1"]["damage_dealt_by"] == {"pc1": 1}
    assert out["m2"]["damage_dealt_by"] == {"pc2": 2}


@pytest.mark.asyncio
async def test_load_all_for_session_empty(repo: MonsterMemoryRepo) -> None:
    out = await repo.load_all_for_session("c", "no-such-session")
    assert out == {}


# ── purge_session ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_purge_session_deletes_matching_only(repo: MonsterMemoryRepo) -> None:
    await repo.upsert("c", "s1", "m1", {"x": 1})
    await repo.upsert("c", "s1", "m2", {"x": 2})
    await repo.upsert("c", "s2", "m3", {"x": 3})  # different session
    await repo.upsert("other_c", "s1", "m4", {"x": 4})  # different channel

    deleted = await repo.purge_session("c", "s1")
    assert deleted == 2

    # Survivors:
    assert await repo.load("c", "s2", "m3") == {"x": 3}
    assert await repo.load("other_c", "s1", "m4") == {"x": 4}
    # Purged:
    assert await repo.load("c", "s1", "m1") is None
    assert await repo.load("c", "s1", "m2") is None


@pytest.mark.asyncio
async def test_purge_session_missing_returns_zero(repo: MonsterMemoryRepo) -> None:
    assert await repo.purge_session("c", "ghost") == 0


# ── Schema verification ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_uses_composite_pk_and_index(repo: MonsterMemoryRepo) -> None:
    """Verify D-161 schema shape."""
    conn = await repo._ensure_conn()
    cur = await conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='monster_memory_entries'"
    )
    row = await cur.fetchone()
    await cur.close()
    sql = row["sql"]
    assert "PRIMARY KEY (channel_id, session_id, monster_id)" in sql
    # Verify WAL pragma applied.
    cur2 = await conn.execute("PRAGMA journal_mode")
    mode = await cur2.fetchone()
    await cur2.close()
    assert mode[0].lower() == "wal"
    # Verify the session index exists.
    cur3 = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_monster_memory_session'"
    )
    idx = await cur3.fetchone()
    await cur3.close()
    assert idx is not None


# ── Fail-soft ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_repo_fail_soft_on_corrupt_payload(repo: MonsterMemoryRepo) -> None:
    """Manually inject malformed JSON; load returns None (per-row error swallowed)."""
    conn = await repo._ensure_conn()
    await conn.execute(
        "INSERT INTO monster_memory_entries VALUES (?, ?, ?, ?, ?)",
        ("c", "s", "bad", "{not-json", 0),
    )
    await conn.commit()
    # load should return None (decode error swallowed).
    assert await repo.load("c", "s", "bad") is None
    # load_all_for_session should skip the bad row but return others.
    await repo.upsert("c", "s", "good", {"x": 1})
    out = await repo.load_all_for_session("c", "s")
    assert "good" in out
    assert "bad" not in out


@pytest.mark.asyncio
async def test_upsert_after_close_does_not_raise(repo: MonsterMemoryRepo) -> None:
    """After aclose, ops must still not crash (they re-open lazily or swallow)."""
    await repo.upsert("c", "s", "m", {"x": 1})
    await repo.aclose()
    # Subsequent ops re-open the connection lazily and succeed.
    await repo.upsert("c", "s", "m2", {"x": 2})
    assert await repo.load("c", "s", "m2") == {"x": 2}


@pytest.mark.asyncio
async def test_aclose_is_idempotent(repo: MonsterMemoryRepo) -> None:
    await repo.aclose()
    await repo.aclose()  # second call must not raise


# ── Settings defaults (L-11) ──────────────────────────────────────────────────


def test_settings_defaults_monster_memory_persist_false() -> None:
    """Without env override, persistence is OFF by default per D-160."""
    from eldritch_dm.config import Settings

    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.monster_memory_persist is False
    assert s.monster_memory_path.endswith("monster_memory.sqlite")


def test_settings_alias_MONSTER_MEMORY_PERSIST_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting MONSTER_MEMORY_PERSIST=true flips persist on."""
    from eldritch_dm.config import Settings, get_settings

    monkeypatch.setenv("MONSTER_MEMORY_PERSIST", "true")
    monkeypatch.setenv("MONSTER_MEMORY_PATH", "/tmp/test_mm.sqlite")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    try:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.monster_memory_persist is True
        assert s.monster_memory_path == "/tmp/test_mm.sqlite"
    finally:
        get_settings.cache_clear()  # type: ignore[attr-defined]
