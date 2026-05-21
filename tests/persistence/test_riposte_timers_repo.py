"""
Tests for RiposteTimerRepo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eldritch_dm.persistence.models import RiposteStatus, RiposteTimer


def make_timer(
    channel_id: str = "ch-1",
    character_id: str = "char-1",
    user_id: str = "user-1",
    deadline_offset_seconds: int = 10,
    status: RiposteStatus = RiposteStatus.PENDING,
    custom_id: str = "cid-1",
    message_id: str = "msg-1",
) -> RiposteTimer:
    return RiposteTimer(
        channel_id=channel_id,
        character_id=character_id,
        user_id=user_id,
        message_id=message_id,
        custom_id=custom_id,
        deadline_ts=datetime.now(UTC) + timedelta(seconds=deadline_offset_seconds),
        status=status,
        created_at=datetime.now(UTC),
    )


class TestRiposteTimerInsert:
    async def test_id_autopopulated_on_insert(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        timer = make_timer()
        inserted = await riposte_repo.insert(timer)

        assert inserted.id is not None
        assert isinstance(inserted.id, int)
        assert inserted.id > 0

    async def test_returns_pydantic_model(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        result = await riposte_repo.insert(make_timer())
        assert isinstance(result, RiposteTimer)

    async def test_roundtrip(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        timer = make_timer()
        inserted = await riposte_repo.insert(timer)
        got = await riposte_repo.get(inserted.id)

        assert got is not None
        assert got.id == inserted.id
        assert got.character_id == timer.character_id
        assert got.status == RiposteStatus.PENDING


class TestRiposteTimerMark:
    async def test_mark_consumed(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        inserted = await riposte_repo.insert(make_timer())
        await riposte_repo.mark_consumed(inserted.id)

        got = await riposte_repo.get(inserted.id)
        assert got is not None
        assert got.status == RiposteStatus.CONSUMED

    async def test_mark_expired(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        inserted = await riposte_repo.insert(make_timer())
        await riposte_repo.mark_expired(inserted.id)

        got = await riposte_repo.get(inserted.id)
        assert got is not None
        assert got.status == RiposteStatus.EXPIRED

    async def test_mark_consumed_idempotent(self, bootstrapped_db_with_repos):
        """Calling mark_consumed twice does not raise."""
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        inserted = await riposte_repo.insert(make_timer())
        await riposte_repo.mark_consumed(inserted.id)
        # Second call should not raise
        await riposte_repo.mark_consumed(inserted.id)

        got = await riposte_repo.get(inserted.id)
        assert got is not None
        assert got.status == RiposteStatus.CONSUMED


class TestRiposteTimerListPending:
    async def test_list_pending_ordered_by_deadline(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        # Insert timers with different deadlines
        await riposte_repo.insert(
            make_timer(custom_id="t1", message_id="m1", deadline_offset_seconds=30)
        )
        await riposte_repo.insert(
            make_timer(custom_id="t2", message_id="m2", deadline_offset_seconds=10)
        )
        await riposte_repo.insert(
            make_timer(custom_id="t3", message_id="m3", deadline_offset_seconds=20)
        )

        pending = await riposte_repo.list_pending()
        assert len(pending) == 3
        # Should be ordered by deadline_ts ASC (t2 < t3 < t1)
        deadlines = [t.deadline_ts for t in pending]
        assert deadlines == sorted(deadlines)

    async def test_list_pending_excludes_non_pending(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        pending_timer = await riposte_repo.insert(
            make_timer(custom_id="pending-t", message_id="mp")
        )
        consumed_timer = await riposte_repo.insert(
            make_timer(custom_id="consumed-t", message_id="mc")
        )
        await riposte_repo.mark_consumed(consumed_timer.id)

        pending = await riposte_repo.list_pending()
        ids = {t.id for t in pending}

        assert pending_timer.id in ids
        assert consumed_timer.id not in ids
