"""
EldritchDM pydantic v2 models for the four local SQLite tables.

All models are:
  - frozen=True: immutable after construction (thread-safe, hashable)
  - extra="forbid": rejects unknown fields (catches schema drift early)

JSON columns:
  - PersistentView.payload maps to `payload_json` TEXT in the DB (D-20)
  - SanitizerAuditRow.stripped_tokens maps to `stripped_tokens` TEXT in the DB

Repositories handle the JSON serialization/deserialization; callers see Python types.

DO NOT import from eldritch_dm.mcp or eldritch_dm.safety -- boundary discipline.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── Enums ─────────────────────────────────────────────────────────────────────


class ChannelState(StrEnum):
    """Valid states for a channel_sessions row.

    Must match the CHECK constraint in database/schema.sql exactly.
    """

    LOBBY = "LOBBY"
    EXPLORATION = "EXPLORATION"
    COMBAT_INIT = "COMBAT_INIT"
    COMBAT = "COMBAT"
    NPC_DLG = "NPC_DLG"
    PAUSED = "PAUSED"


class RiposteStatus(StrEnum):
    """Valid statuses for a riposte_timers row.

    Must match the CHECK constraint in database/schema.sql exactly.
    """

    PENDING = "pending"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# ── Models ────────────────────────────────────────────────────────────────────


class ChannelSession(BaseModel):
    """Represents a row in channel_sessions.

    Maps a Discord channel_id to its active dm20 campaign and session context.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel_id: str
    campaign_name: str
    claudmaster_session_id: str | None = None
    dm20_party_token: str | None = None
    state: ChannelState = ChannelState.LOBBY
    created_at: datetime
    updated_at: datetime


class PersistentView(BaseModel):
    """Represents a row in persistent_views.

    Tracks Discord UI components (buttons, selects) that need to be
    re-registered after a bot restart.

    Note: `payload` (Python dict) <-> `payload_json` (TEXT) in the DB.
    The repository is responsible for JSON serialization/deserialization.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    custom_id: str
    view_class: str
    message_id: str
    channel_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RiposteTimer(BaseModel):
    """Represents a row in riposte_timers.

    Tracks the timed riposte button for a Discord user. The background sweeper
    marks PENDING timers as EXPIRED when deadline_ts passes.

    Phase 5 Plan 01 adds the `consumed_in_round` shim column (RESEARCH Q1): when
    a Riposte click succeeds, the bot records the combat round so the
    eligibility check can enforce one reaction per PC per round (dm20 has no
    native reaction-budget tracking).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int | None = None  # None before INSERT; DB assigns AUTOINCREMENT
    channel_id: str
    character_id: str  # dm20 character id
    user_id: str  # Discord user id (gatekeeping)
    monster_uuid: str | None = None  # dm20 monster uuid that missed
    weapon_used: str | None = None
    message_id: str  # the ephemeral message hosting the button
    custom_id: str
    deadline_ts: datetime
    status: RiposteStatus = RiposteStatus.PENDING
    created_at: datetime
    # Phase 5 Plan 01 reaction-budget shim: round in which the riposte was
    # consumed. None for pending/expired/cancelled rows. Eligibility check
    # rejects new riposte surfaces when ANY row with consumed_in_round ==
    # current_round exists for the PC.
    consumed_in_round: int | None = None


class SanitizerAuditRow(BaseModel):
    """Represents a row in sanitizer_audit.

    Append-only audit log for every sanitized player input that had
    tokens stripped or was truncated.

    Note: `stripped_tokens` (Python list) <-> `stripped_tokens` (TEXT/JSON) in the DB.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int | None = None  # None before INSERT; DB assigns AUTOINCREMENT
    channel_id: str
    user_id: str
    raw_input: str
    stripped_tokens: list[str] = Field(default_factory=list)
    redacted_output: str
    truncated: bool
    ts: datetime
