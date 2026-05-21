"""
Tests for PersistentViewRepo.
"""

from __future__ import annotations

from datetime import datetime, UTC

import pytest

from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
from eldritch_dm.persistence.models import PersistentView
from eldritch_dm.persistence.persistent_views_repo import PersistentViewRepo


def make_view(custom_id="view-1", channel_id="ch-1", message_id="msg-1", payload=None) -> PersistentView:
    return PersistentView(
        custom_id=custom_id,
        view_class="LobbyView",
        message_id=message_id,
        channel_id=channel_id,
        payload=payload or {},
        created_at=datetime.now(UTC),
    )


class TestPersistentViewRoundtrip:
    async def test_roundtrip(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, view_repo, _, _, _ = bootstrapped_db_with_repos

        # Need parent channel_sessions row for FK
        await channel_repo.upsert(channel_id="ch-1", campaign_name="Camp1")

        view = make_view()
        inserted = await view_repo.insert(view)
        got = await view_repo.get("view-1")

        assert got is not None
        assert got.custom_id == "view-1"
        assert got.channel_id == "ch-1"
        assert isinstance(inserted, PersistentView)

    async def test_returns_pydantic_model(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, view_repo, _, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-model", campaign_name="CampModel")
        result = await view_repo.insert(make_view(custom_id="view-model", channel_id="ch-model"))
        assert isinstance(result, PersistentView)

    async def test_payload_json_roundtrip(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, view_repo, _, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-payload", campaign_name="PayloadCamp")

        complex_payload = {"items": [1, "two", {"three": 3}], "nested": {"a": True}}
        view = make_view(custom_id="view-payload", channel_id="ch-payload", payload=complex_payload)
        inserted = await view_repo.insert(view)

        got = await view_repo.get("view-payload")
        assert got is not None
        assert got.payload == complex_payload


class TestPersistentViewListByChannel:
    async def test_list_by_channel_ordering(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, view_repo, _, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-list", campaign_name="ListCamp")

        # Insert three views
        for i in range(3):
            await view_repo.insert(make_view(
                custom_id=f"view-list-{i}",
                channel_id="ch-list",
                message_id=f"msg-{i}",
            ))

        views = await view_repo.list_by_channel("ch-list")
        assert len(views) == 3
        # Should be ordered by created_at ASC
        for i in range(len(views) - 1):
            assert views[i].created_at <= views[i + 1].created_at

    async def test_list_by_channel_filters_correctly(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, view_repo, _, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-a", campaign_name="CampA")
        await channel_repo.upsert(channel_id="ch-b", campaign_name="CampB")

        await view_repo.insert(make_view(custom_id="v-a", channel_id="ch-a"))
        await view_repo.insert(make_view(custom_id="v-b", channel_id="ch-b"))

        views_a = await view_repo.list_by_channel("ch-a")
        assert len(views_a) == 1
        assert views_a[0].custom_id == "v-a"


class TestPersistentViewDeleteForMessage:
    async def test_delete_for_message(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, view_repo, _, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-del", campaign_name="DelCamp")

        await view_repo.insert(make_view(custom_id="v-del-1", channel_id="ch-del", message_id="msg-del"))
        await view_repo.insert(make_view(custom_id="v-del-2", channel_id="ch-del", message_id="msg-del"))
        await view_repo.insert(make_view(custom_id="v-keep", channel_id="ch-del", message_id="msg-keep"))

        deleted = await view_repo.delete_for_message("msg-del")
        assert deleted == 2

        still_there = await view_repo.list_by_channel("ch-del")
        assert len(still_there) == 1
        assert still_there[0].custom_id == "v-keep"

    async def test_delete_returns_zero_for_unknown_message(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, view_repo, _, _, _ = bootstrapped_db_with_repos
        deleted = await view_repo.delete_for_message("nonexistent-msg")
        assert deleted == 0


class TestPersistentViewFKCascade:
    async def test_fk_cascade_on_channel_delete(self, bootstrapped_db_with_repos):
        db_path, wq, channel_repo, view_repo, _, _, _ = bootstrapped_db_with_repos
        await channel_repo.upsert(channel_id="ch-cascade", campaign_name="CascadeCamp")
        await view_repo.insert(make_view(custom_id="v-cascade", channel_id="ch-cascade"))

        # Verify view exists
        assert await view_repo.get("v-cascade") is not None

        # Delete the parent channel
        await channel_repo.delete("ch-cascade")

        # Child view should cascade-delete
        got = await view_repo.get("v-cascade")
        assert got is None
