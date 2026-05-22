"""
Tests for PCClassesRepo (Phase 5 Plan 01 Task 1).

Verifies:
  - upsert inserts a new row
  - upsert updates an existing (channel_id, character_id) row (no duplicate)
  - get returns PCClassInfo (pydantic frozen model) or None
  - class_name + subclass are normalized (lowercased + whitespace-collapsed)
  - get on non-existent row returns None
"""

from __future__ import annotations

import pytest

from eldritch_dm.persistence.bootstrap import bootstrap
from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
from eldritch_dm.persistence.connection import WriterQueue
from eldritch_dm.persistence.pc_classes_repo import PCClassesRepo, PCClassInfo


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def pc_classes_setup(tmp_path):
    """Bootstrap a fresh DB, return (repo, channel_repo, db_path)."""
    db_path = str(tmp_path / "pc_classes_test.sqlite3")
    await bootstrap(db_path)
    wq = WriterQueue(db_path)
    await wq.start()
    try:
        channel_repo = ChannelSessionRepo(db_path, wq)
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")
        repo = PCClassesRepo(db_path)
        yield repo, channel_repo, db_path
    finally:
        await wq.stop()


# ── Test 6: upsert inserts new row ────────────────────────────────────────────


class TestPCClassesUpsertInsert:
    async def test_upsert_inserts_new_row(self, pc_classes_setup) -> None:
        repo, _, _ = pc_classes_setup
        await repo.upsert(
            channel_id="ch-1",
            character_id="hero-001",
            class_name="Fighter",
            subclass="Battle Master",
        )
        got = await repo.get("ch-1", "hero-001")
        assert got is not None
        assert got.class_name == "fighter"
        assert got.subclass == "battle master"


# ── Test 7: second upsert is an UPDATE (no duplicates) ───────────────────────


class TestPCClassesUpsertUpdate:
    async def test_second_upsert_updates_existing_row(self, pc_classes_setup) -> None:
        repo, _, db_path = pc_classes_setup
        await repo.upsert(
            channel_id="ch-1",
            character_id="hero-001",
            class_name="Fighter",
            subclass="Battle Master",
        )
        # Second call with new subclass
        await repo.upsert(
            channel_id="ch-1",
            character_id="hero-001",
            class_name="Fighter",
            subclass="Champion",
        )
        # Only one row exists
        import aiosqlite
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM pc_classes WHERE character_id = ?",
                ("hero-001",),
            )
            row = await cursor.fetchone()
        assert row[0] == 1, f"Expected 1 row after second upsert, got {row[0]}"

        got = await repo.get("ch-1", "hero-001")
        assert got is not None
        assert got.subclass == "champion"


# ── Test 8: get returns PCClassInfo or None ──────────────────────────────────


class TestPCClassesGet:
    async def test_get_returns_pcclassinfo_model(self, pc_classes_setup) -> None:
        repo, _, _ = pc_classes_setup
        await repo.upsert(
            channel_id="ch-1",
            character_id="hero-001",
            class_name="wizard",
            subclass="evocation",
        )
        got = await repo.get("ch-1", "hero-001")
        assert isinstance(got, PCClassInfo)
        # PCClassInfo is a pydantic v2 frozen model
        with pytest.raises(Exception):  # noqa: B017,PT011
            got.class_name = "rogue"  # type: ignore[misc]


# ── Test 9: class_name + subclass normalized ─────────────────────────────────


class TestPCClassesNormalization:
    async def test_class_and_subclass_lowercased_and_whitespace_collapsed(
        self, pc_classes_setup
    ) -> None:
        repo, _, _ = pc_classes_setup
        await repo.upsert(
            channel_id="ch-1",
            character_id="hero-001",
            class_name="  FiGhTeR  ",
            subclass="Battle  Master",  # double space → single space
        )
        got = await repo.get("ch-1", "hero-001")
        assert got is not None
        assert got.class_name == "fighter"
        assert got.subclass == "battle master"

    async def test_pcclassinfo_validator_normalizes_on_construct(self) -> None:
        info = PCClassInfo(class_name="ROGUE", subclass="  Swashbuckler ")
        assert info.class_name == "rogue"
        assert info.subclass == "swashbuckler"


# ── Test 10: get on non-existent row returns None ─────────────────────────────


class TestPCClassesGetMissing:
    async def test_get_missing_row_returns_none(self, pc_classes_setup) -> None:
        repo, _, _ = pc_classes_setup
        got = await repo.get("ch-1", "no-such-char")
        assert got is None
