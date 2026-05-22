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


class TestRiposteTimerPhase5Extensions:
    """Phase 5 Plan 01: list_for_character, mark_cancelled, update_message_ref,
    mark_consumed_with_round, consumed_in_round model field."""

    async def test_list_for_character_returns_all_statuses_id_asc(
        self, bootstrapped_db_with_repos
    ) -> None:
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        # Three timers for the same character
        t1 = await riposte_repo.insert(
            make_timer(custom_id="t1", message_id="m1", character_id="hero-001")
        )
        t2 = await riposte_repo.insert(
            make_timer(custom_id="t2", message_id="m2", character_id="hero-001")
        )
        t3 = await riposte_repo.insert(
            make_timer(custom_id="t3", message_id="m3", character_id="hero-001")
        )
        # Mix statuses
        await riposte_repo.mark_consumed(t1.id)
        await riposte_repo.mark_expired(t2.id)
        # t3 stays pending

        # Another character — should NOT be included
        other = await riposte_repo.insert(
            make_timer(custom_id="other", message_id="m-other", character_id="hero-002")
        )

        rows = await riposte_repo.list_for_character("ch-1", "hero-001")
        ids = [r.id for r in rows]
        assert ids == sorted(ids), f"Expected id ASC ordering, got {ids}"
        assert {r.id for r in rows} == {t1.id, t2.id, t3.id}
        assert other.id not in {r.id for r in rows}

    async def test_mark_cancelled_sets_status(self, bootstrapped_db_with_repos) -> None:
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")
        timer = await riposte_repo.insert(make_timer())

        await riposte_repo.mark_cancelled(timer.id)

        got = await riposte_repo.get(timer.id)
        assert got is not None
        assert got.status == RiposteStatus.CANCELLED

    async def test_mark_cancelled_idempotent(self, bootstrapped_db_with_repos) -> None:
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")
        timer = await riposte_repo.insert(make_timer())

        await riposte_repo.mark_cancelled(timer.id)
        # Second call must not raise
        await riposte_repo.mark_cancelled(timer.id)

        got = await riposte_repo.get(timer.id)
        assert got.status == RiposteStatus.CANCELLED

    async def test_mark_cancelled_does_not_overwrite_consumed(
        self, bootstrapped_db_with_repos
    ) -> None:
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")
        timer = await riposte_repo.insert(make_timer())

        await riposte_repo.mark_consumed(timer.id)
        await riposte_repo.mark_cancelled(timer.id)  # should be no-op

        got = await riposte_repo.get(timer.id)
        assert got.status == RiposteStatus.CONSUMED, (
            "mark_cancelled must NOT overwrite a consumed row"
        )

    async def test_update_message_ref_writes_all_three_atomically(
        self, bootstrapped_db_with_repos
    ) -> None:
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")
        timer = await riposte_repo.insert(make_timer(message_id="placeholder"))

        new_deadline = datetime.now(UTC) + timedelta(seconds=20)
        await riposte_repo.update_message_ref(
            timer.id,
            message_id="real-msg-123",
            custom_id=f"riposte:{timer.id}:99",
            deadline_ts=new_deadline,
        )

        got = await riposte_repo.get(timer.id)
        assert got is not None
        assert got.message_id == "real-msg-123"
        assert got.custom_id == f"riposte:{timer.id}:99"
        # deadline written back (comparison tolerant of microseconds since stored as ISO string)
        assert got.deadline_ts.isoformat() == new_deadline.isoformat()

    async def test_mark_consumed_with_round_sets_both_fields(
        self, bootstrapped_db_with_repos
    ) -> None:
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")
        timer = await riposte_repo.insert(make_timer())

        await riposte_repo.mark_consumed_with_round(timer.id, 4)

        got = await riposte_repo.get(timer.id)
        assert got is not None
        assert got.status == RiposteStatus.CONSUMED
        assert got.consumed_in_round == 4

    async def test_insert_then_mark_with_round_3(
        self, bootstrapped_db_with_repos
    ) -> None:
        """Inserted with consumed_in_round=None; after mark_consumed_with_round(3) it's 3."""
        db_path, wq, channel_repo, _, riposte_repo, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        timer = await riposte_repo.insert(make_timer())
        assert timer.consumed_in_round is None

        await riposte_repo.mark_consumed_with_round(timer.id, 3)
        got = await riposte_repo.get(timer.id)
        assert got is not None
        assert got.consumed_in_round == 3

    async def test_riposte_timer_model_accepts_consumed_in_round(self) -> None:
        """Pydantic model accepts optional consumed_in_round: int | None = None."""
        t = RiposteTimer(
            channel_id="ch-1",
            character_id="hero-1",
            user_id="user-1",
            message_id="m",
            custom_id="cid",
            deadline_ts=datetime.now(UTC) + timedelta(seconds=10),
            status=RiposteStatus.PENDING,
            created_at=datetime.now(UTC),
            consumed_in_round=2,
        )
        assert t.consumed_in_round == 2

        t_none = RiposteTimer(
            channel_id="ch-1",
            character_id="hero-1",
            user_id="user-1",
            message_id="m",
            custom_id="cid",
            deadline_ts=datetime.now(UTC) + timedelta(seconds=10),
            status=RiposteStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        assert t_none.consumed_in_round is None


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
