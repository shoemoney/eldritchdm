"""
Tests for ChannelSessionRepo.
"""

from __future__ import annotations

import pytest

from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
from eldritch_dm.persistence.models import ChannelSession, ChannelState


class TestChannelSessionRoundtrip:
    async def test_roundtrip(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = ChannelSessionRepo(db_path, wq)

        await repo.upsert(channel_id="ch-1", campaign_name="TestCamp")
        got = await repo.get("ch-1")

        assert got is not None
        assert got.channel_id == "ch-1"
        assert got.campaign_name == "TestCamp"
        assert got.state == ChannelState.LOBBY

    async def test_returns_pydantic_model(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = ChannelSessionRepo(db_path, wq)
        result = await repo.upsert(channel_id="ch-2", campaign_name="Camp2")
        assert isinstance(result, ChannelSession)

    async def test_upsert_updates_on_conflict(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = ChannelSessionRepo(db_path, wq)

        await repo.upsert(channel_id="ch-3", campaign_name="OriginalCamp")
        updated = await repo.upsert(channel_id="ch-3", campaign_name="UpdatedCamp")

        assert updated.campaign_name == "UpdatedCamp"
        got = await repo.get("ch-3")
        assert got is not None
        assert got.campaign_name == "UpdatedCamp"


class TestChannelSessionListActive:
    async def test_list_active_excludes_paused(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = ChannelSessionRepo(db_path, wq)

        await repo.upsert(channel_id="active-1", campaign_name="Active", state=ChannelState.LOBBY)
        await repo.upsert(channel_id="active-2", campaign_name="Combat", state=ChannelState.COMBAT)
        await repo.upsert(channel_id="paused-1", campaign_name="Paused", state=ChannelState.PAUSED)

        active = await repo.list_active()
        ids = {s.channel_id for s in active}

        assert "active-1" in ids
        assert "active-2" in ids
        assert "paused-1" not in ids


class TestChannelSessionSetState:
    async def test_set_state_updates(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = ChannelSessionRepo(db_path, wq)

        await repo.upsert(channel_id="state-ch", campaign_name="StateCamp")
        updated = await repo.set_state("state-ch", ChannelState.COMBAT)

        assert updated.state == ChannelState.COMBAT
        got = await repo.get("state-ch")
        assert got is not None
        assert got.state == ChannelState.COMBAT

    async def test_set_state_updates_timestamp(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = ChannelSessionRepo(db_path, wq)

        original = await repo.upsert(channel_id="ts-ch", campaign_name="TsCamp")
        updated = await repo.set_state("ts-ch", ChannelState.EXPLORATION)

        # updated_at should be >= created_at
        assert updated.updated_at >= original.created_at

    async def test_set_state_raises_for_missing(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = ChannelSessionRepo(db_path, wq)

        with pytest.raises(KeyError):
            await repo.set_state("nonexistent", ChannelState.COMBAT)


class TestChannelSessionDelete:
    async def test_delete_removes_row(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = ChannelSessionRepo(db_path, wq)

        await repo.upsert(channel_id="del-ch", campaign_name="DelCamp")
        await repo.delete("del-ch")

        got = await repo.get("del-ch")
        assert got is None


class TestChannelSessionWritesThroughQueue:
    async def test_writes_go_through_queue(self, bootstrapped_db):
        db_path, wq = bootstrapped_db
        repo = ChannelSessionRepo(db_path, wq)

        submit_calls: list[str] = []
        original_submit = wq.submit

        async def recording_submit(fn):
            submit_calls.append("submit")
            return await original_submit(fn)

        wq.submit = recording_submit

        # Mutating operations should use writer_queue.submit
        await repo.upsert(channel_id="wq-ch", campaign_name="WQCamp")
        assert len(submit_calls) >= 1

        # Read operations should NOT use submit
        before = len(submit_calls)
        await repo.get("wq-ch")
        assert len(submit_calls) == before  # no additional submit calls

    async def test_check_constraint_rejects_bogus_state(self, bootstrapped_db):
        """Ensure DB-level CHECK constraint rejects invalid states."""
        import aiosqlite

        db_path, wq = bootstrapped_db

        async def _bad_insert(conn: aiosqlite.Connection) -> None:
            await conn.execute(
                "INSERT INTO channel_sessions "
                "(channel_id, campaign_name, state, created_at, updated_at) "
                "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
                ("bogus-ch", "Bogus", "INVALID_STATE"),
            )

        with pytest.raises(aiosqlite.IntegrityError):
            await wq.submit(_bad_insert)
