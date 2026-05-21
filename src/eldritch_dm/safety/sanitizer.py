"""
Player-input sanitizer for EldritchDM.

Strips control tokens / ChatML sentinels from Discord modal input before
it flows into the MCP request and ultimately into the ShoeGPT prompt.

Order of operations (D-24):
  1. Truncate to max_chars FIRST — prevents past-cap sentinel smuggling
  2. Strip DEFAULT_BLACKLIST tokens (case-insensitive, bounded to 64 passes)
  3. Apply broad ChatML regex <|...|> (catch-all for non-ASCII lookalikes)
  4. Wrap in <player_action speaker="..." user_id="...">...</player_action>
     with XML-escaped values (D-27)

Audit hook (D-28):
  If stripped_tokens != [] or truncated is True AND audit_callback is provided,
  the callback is called synchronously with the completed SanitizerAuditRow.
  The callback is SYNC because sanitize_player_input is SYNC.
  Use make_async_audit_callback() to bridge to async SanitizerAuditRepo.insert.

Import note (Plan 03 decision):
  safety may import eldritch_dm.persistence.models (pure pydantic data shapes).
  safety must NOT import any other persistence submodule (connection, repos, etc.).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import escape

from eldritch_dm.persistence.models import SanitizerAuditRow

if TYPE_CHECKING:
    pass

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_BLACKLIST: tuple[str, ...] = (
    "<tool_call>",
    "</tool_call>",
    "<|im_start|>",
    "<|im_end|>",
    "<|system|>",
    "<|user|>",
    "<|assistant|>",
    "<player_action>",
    "</player_action>",
    "SYSTEM:",
    "ASSISTANT:",
    "USER:",
    "<|endoftext|>",
)

# Broad catch-all for ChatML-style <|anything|> patterns including lookalikes
# DOTALL so the content between pipes can span lines
_CHATML_RE = re.compile(r"<\|.*?\|>", re.DOTALL)

_MAX_STRIP_PASSES = 64


# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SanitizedInput:
    """Result of sanitize_player_input.

    Attributes:
        raw: Original unmodified input string.
        cleaned: Input after truncation + token stripping.
        wrapped: XML-wrapped sentinel form safe for injection into LLM context.
        truncated: True if input was longer than max_chars.
        stripped_tokens: List of token literals that were removed from the input.
    """

    raw: str
    cleaned: str
    wrapped: str
    truncated: bool
    stripped_tokens: list[str] = field(default_factory=list)


# ── Core sanitizer ────────────────────────────────────────────────────────────


def sanitize_player_input(
    raw: str,
    *,
    speaker: str,
    user_id: str,
    channel_id: str,
    max_chars: int = 500,
    blacklist: tuple[str, ...] = DEFAULT_BLACKLIST,
    audit_callback: Callable[[SanitizerAuditRow], None] | None = None,
) -> SanitizedInput:
    """Sanitize a player's free-text input for safe injection into the LLM prompt.

    Args:
        raw: The raw string from the Discord modal.
        speaker: The player character's name (XML-escaped in the wrapper).
        user_id: The Discord user snowflake (digits; XML-escaped defensively).
        channel_id: The Discord channel snowflake (for the audit row).
        max_chars: Maximum input length; longer inputs are truncated FIRST.
        blacklist: Tuple of token literals to strip (case-insensitive).
        audit_callback: Sync callback invoked with the audit row when
            stripped_tokens != [] or truncated is True. The caller is
            responsible for scheduling the async DB insert.
            Use make_async_audit_callback() for the canonical wiring.

    Returns:
        SanitizedInput with cleaned text, wrapped sentinel, and audit metadata.

    Security guarantees (D-24..D-27):
        - Truncation happens BEFORE stripping (past-cap smuggling impossible)
        - Strip loop is bounded (max 64 passes; early-exit on no-change pass)
        - Speaker and user_id are XML-escaped (attribute injection impossible)
        - Entire cleaned body is XML-escaped (< > & become entities)
    """
    assert isinstance(raw, str), f"raw must be str, got {type(raw).__name__!r}"

    # Step 1: Truncate
    if len(raw) > max_chars:
        cleaned = raw[:max_chars]
        truncated = True
    else:
        cleaned = raw
        truncated = False

    # Step 2 + 3: Strip tokens + ChatML regex (bounded passes)
    stripped_tokens: list[str] = []

    for _pass in range(_MAX_STRIP_PASSES):
        made_change = False

        # Step 2: blacklist tokens (case-insensitive)
        for token in blacklist:
            pattern = re.compile(re.escape(token), re.IGNORECASE)
            def _replacer(m: re.Match, _tokens: list = stripped_tokens) -> str:
                _tokens.append(m.group(0))
                return ""

            new_cleaned, count = pattern.subn(_replacer, cleaned)
            if count > 0:
                cleaned = new_cleaned
                made_change = True

        # Step 3: broad ChatML regex (records matches before removing)
        def _record_and_remove(m: re.Match) -> str:
            stripped_tokens.append(m.group(0))
            return ""

        new_cleaned = _CHATML_RE.sub(_record_and_remove, cleaned)
        if new_cleaned != cleaned:
            cleaned = new_cleaned
            made_change = True

        if not made_change:
            break

    # Step 4: Wrap with XML-escaped values
    wrapped = (
        f'<player_action speaker="{escape(speaker)}" user_id="{escape(user_id)}">'
        f"{escape(cleaned)}"
        f"</player_action>"
    )

    result = SanitizedInput(
        raw=raw,
        cleaned=cleaned,
        wrapped=wrapped,
        truncated=truncated,
        stripped_tokens=stripped_tokens,
    )

    # Audit callback: fire if there was any sanitization work
    if audit_callback is not None and (stripped_tokens or truncated):
        audit_row = SanitizerAuditRow(
            channel_id=channel_id,
            user_id=user_id,
            raw_input=raw,
            stripped_tokens=stripped_tokens,
            redacted_output=cleaned,
            truncated=truncated,
            ts=datetime.now(UTC),
        )
        audit_callback(audit_row)

    return result


# ── Async audit callback helper ───────────────────────────────────────────────


def make_async_audit_callback(
    repo: Any,  # SanitizerAuditRepo — typed as Any to avoid circular import at runtime
    loop: asyncio.AbstractEventLoop | None = None,
) -> Callable[[SanitizerAuditRow], None]:
    """Create a sync callback that fires the async repo.insert() on the event loop.

    Args:
        repo: A SanitizerAuditRepo instance.
        loop: The running event loop. Defaults to asyncio.get_event_loop() at call time.

    Returns:
        A sync callable accepting SanitizerAuditRow. Fire-and-forget; errors are logged.

    Usage (typical wiring in the bot)::

        loop = asyncio.get_running_loop()
        cb = make_async_audit_callback(audit_repo, loop=loop)
        sanitized = sanitize_player_input(raw, ..., audit_callback=cb)
    """
    from eldritch_dm.logging import get_logger

    _log = get_logger(__name__).bind(component="sanitizer_audit_callback")
    _loop = loop or asyncio.get_event_loop()

    def _cb(row: SanitizerAuditRow) -> None:
        async def _insert_safe() -> None:
            try:
                await repo.insert(row)
            except Exception as exc:  # noqa: BLE001
                _log.error(
                    "audit_insert_failed",
                    error=str(exc),
                    channel_id=row.channel_id,
                )

        asyncio.run_coroutine_threadsafe(_insert_safe(), _loop)

    return _cb
