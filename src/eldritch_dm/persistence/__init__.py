"""
EldritchDM persistence subpackage — public API surface.

Exports the connection helpers, lock registry, pydantic models, and repositories.
Repositories were created early (Wave 1) to support Wave 2 tests.

DO NOT import from eldritch_dm.mcp or eldritch_dm.safety -- boundary discipline.
"""

from __future__ import annotations

from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
from eldritch_dm.persistence.character_cache import (
    ALLOWED_SNAPSHOT_FIELDS,
    FORBIDDEN_SNAPSHOT_FIELDS,
    CharacterCacheMetrics,
    CharacterCacheRepo,
    CharacterSnapshot,
    etag_of,
)
from eldritch_dm.persistence.connection import (
    WriterQueue,
    apply_pragmas,
    open_connection,
)
from eldritch_dm.persistence.locks import SessionLocks
from eldritch_dm.persistence.models import (
    ChannelSession,
    ChannelState,
    PersistentView,
    RiposteStatus,
    RiposteTimer,
    SanitizerAuditRow,
)
from eldritch_dm.persistence.pc_classes_repo import PCClassesRepo, PCClassInfo
from eldritch_dm.persistence.persistent_views_repo import PersistentViewRepo
from eldritch_dm.persistence.riposte_timers_repo import RiposteTimerRepo
from eldritch_dm.persistence.sanitizer_audit_repo import SanitizerAuditRepo

__all__ = [
    # Connection helpers
    "open_connection",
    "WriterQueue",
    "apply_pragmas",
    # Lock registry
    "SessionLocks",
    # Models
    "ChannelSession",
    "PersistentView",
    "RiposteTimer",
    "SanitizerAuditRow",
    "PCClassInfo",
    # Enums
    "ChannelState",
    "RiposteStatus",
    # Repositories
    "ChannelSessionRepo",
    "PersistentViewRepo",
    "RiposteTimerRepo",
    "SanitizerAuditRepo",
    "PCClassesRepo",
    # Phase 17 — character cache
    "CharacterCacheRepo",
    "CharacterSnapshot",
    "CharacterCacheMetrics",
    "ALLOWED_SNAPSHOT_FIELDS",
    "FORBIDDEN_SNAPSHOT_FIELDS",
    "etag_of",
]
