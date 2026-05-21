"""
EldritchDM safety subpackage — public API surface.

Exports the player-input sanitizer and related helpers.
"""

from __future__ import annotations

from eldritch_dm.safety.sanitizer import (
    DEFAULT_BLACKLIST,
    SanitizedInput,
    make_async_audit_callback,
    sanitize_player_input,
)

__all__ = [
    "sanitize_player_input",
    "SanitizedInput",
    "DEFAULT_BLACKLIST",
    "make_async_audit_callback",
]
