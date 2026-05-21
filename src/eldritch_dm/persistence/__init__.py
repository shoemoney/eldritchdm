"""
EldritchDM persistence subpackage — public API surface.

Exports the connection helpers, lock registry, and pydantic models.
Repositories (ChannelSessionRepo, PersistentViewRepo, RiposteTimerRepo,
SanitizerAuditRepo) will be added by Plan 02 and extend __all__.

DO NOT import from eldritch_dm.mcp or eldritch_dm.safety — boundary discipline.
"""

from __future__ import annotations

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
    # Enums
    "ChannelState",
    "RiposteStatus",
]
