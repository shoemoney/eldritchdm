"""
Tests for eldritch_dm.persistence.models — pydantic v2 frozen models.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from eldritch_dm.persistence.models import (
    ChannelSession,
    ChannelState,
    PersistentView,
    RiposteStatus,
    RiposteTimer,
    SanitizerAuditRow,
)

NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


class TestChannelSessionFrozen:
    """ChannelSession is frozen — mutation raises."""

    def test_channel_session_constructs(self) -> None:
        obj = ChannelSession(
            channel_id="ch-1",
            campaign_name="Lost Mines",
            state=ChannelState.LOBBY,
            created_at=NOW,
            updated_at=NOW,
        )
        assert obj.channel_id == "ch-1"
        assert obj.state == ChannelState.LOBBY

    def test_channel_session_frozen(self) -> None:
        obj = ChannelSession(
            channel_id="ch-1",
            campaign_name="Lost Mines",
            created_at=NOW,
            updated_at=NOW,
        )
        with pytest.raises((ValidationError, TypeError)):
            obj.state = ChannelState.PAUSED  # type: ignore[misc]


class TestExtraForbid:
    """extra='forbid' rejects unknown fields on all models."""

    def test_channel_session_extra_forbid(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            ChannelSession(
                channel_id="ch-1",
                campaign_name="c",
                created_at=NOW,
                updated_at=NOW,
                extra_field=True,  # type: ignore[call-arg]
            )

    def test_persistent_view_extra_forbid(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            PersistentView(
                custom_id="v-1",
                view_class="CombatView",
                message_id="msg-1",
                channel_id="ch-1",
                created_at=NOW,
                surprise_field="oops",  # type: ignore[call-arg]
            )


class TestPersistentViewPayloadRoundtrip:
    """PersistentView.payload round-trips through model_dump(mode='json') / model_validate."""

    def test_payload_roundtrip(self) -> None:
        payload = {"foo": [1, "two"], "nested": {"key": True}}
        obj = PersistentView(
            custom_id="v-2",
            view_class="ExploreView",
            message_id="msg-2",
            channel_id="ch-2",
            payload=payload,
            created_at=NOW,
        )

        dumped = obj.model_dump(mode="json")
        reloaded = PersistentView.model_validate(dumped)

        assert reloaded.payload == payload
        assert reloaded == obj

    def test_payload_defaults_to_empty_dict(self) -> None:
        obj = PersistentView(
            custom_id="v-3",
            view_class="LobbyView",
            message_id="msg-3",
            channel_id="ch-3",
            created_at=NOW,
        )
        assert obj.payload == {}


class TestSanitizerAuditRowDefaults:
    """SanitizerAuditRow has correct defaults."""

    def test_stripped_tokens_defaults_to_empty_list(self) -> None:
        row = SanitizerAuditRow(
            channel_id="ch-1",
            user_id="user-1",
            raw_input="hello",
            redacted_output="hello",
            truncated=False,
            ts=NOW,
        )
        assert row.stripped_tokens == []

    def test_id_defaults_to_none(self) -> None:
        row = SanitizerAuditRow(
            channel_id="ch-1",
            user_id="user-1",
            raw_input="hello",
            redacted_output="hello",
            truncated=False,
            ts=NOW,
        )
        assert row.id is None

    def test_truncated_field(self) -> None:
        row = SanitizerAuditRow(
            channel_id="ch-1",
            user_id="user-1",
            raw_input="a" * 600,
            redacted_output="a" * 500,
            truncated=True,
            ts=NOW,
        )
        assert row.truncated is True


class TestStateCheckConstraintsDocumented:
    """ChannelState enum values match the SQL CHECK constraint in schema.sql."""

    def test_state_values_match_schema_check(self) -> None:
        import pathlib

        schema_path = (
            pathlib.Path(__file__).parents[2] / "database" / "schema.sql"
        )
        schema_sql = schema_path.read_text()

        # Extract the CHECK constraint for the `state` column
        # Pattern: CHECK(state IN ('LOBBY','EXPLORATION',...))
        match = re.search(
            r"CHECK\(state IN \(([^)]+)\)\)",
            schema_sql,
        )
        assert match is not None, "Could not find CHECK(state IN (...)) in schema.sql"

        sql_values = {
            v.strip().strip("'\"") for v in match.group(1).split(",")
        }
        enum_values = {member.value for member in ChannelState}

        assert sql_values == enum_values, (
            f"ChannelState enum values {enum_values!r} do not match "
            f"schema.sql CHECK constraint values {sql_values!r}"
        )

    def test_riposte_status_values_match_schema_check(self) -> None:
        import pathlib

        schema_path = (
            pathlib.Path(__file__).parents[2] / "database" / "schema.sql"
        )
        schema_sql = schema_path.read_text()

        # Extract the CHECK constraint for the `status` column in riposte_timers
        match = re.search(
            r"CHECK\(status IN \(([^)]+)\)\)",
            schema_sql,
        )
        assert match is not None, "Could not find CHECK(status IN (...)) in schema.sql"

        sql_values = {
            v.strip().strip("'\"") for v in match.group(1).split(",")
        }
        enum_values = {member.value for member in RiposteStatus}

        assert sql_values == enum_values, (
            f"RiposteStatus enum values {enum_values!r} do not match "
            f"schema.sql CHECK constraint values {sql_values!r}"
        )
