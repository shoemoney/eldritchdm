"""
setup_hook.py — extracted persistent-view rehydration helpers.

Extracting into a separate module makes it testable in isolation without
spinning up a full EldritchBot instance.

Key decision (RESEARCH.md Pitfall 1):
  add_dynamic_items(Cls) is sufficient for DynamicItem-based buttons.
  add_view(view, message_id=...) calls are an optional audit layer here —
  they are NOT required for restart survival.

D-24 step 5 (rehydration flow):
  For each active channel session → for each persistent_view row →
  build a View and call bot.add_view(view, message_id=int(row.message_id)).
  This registers message-scoped view routing as an audit/cleanup aid.
  The primary dispatch mechanism remains add_dynamic_items (set in bot.py).

D-39 log line: "rehydrated N persistent views from M channel sessions"
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord

from eldritch_dm.logging import get_logger

if TYPE_CHECKING:
    from eldritch_dm.persistence.channel_sessions_repo import ChannelSessionRepo
    from eldritch_dm.persistence.persistent_views_repo import PersistentViewRepo
    from eldritch_dm.persistence.models import PersistentView

log = get_logger(__name__)


# ── Lazy import: avoid circular deps and allow standalone unit testing ─────────

def _get_dynamic_item_classes() -> dict[str, type]:
    """Return a mapping of view_class name → DynamicItem subclass.

    Imported lazily to avoid circular import at module load time.
    """
    from eldritch_dm.bot.dynamic_items import (
        DeclareActionButton,
        EndTurnButton,
        ReadyButton,
        RiposteButton,
    )

    return {
        "ReadyButton": ReadyButton,
        "DeclareActionButton": DeclareActionButton,
        "EndTurnButton": EndTurnButton,
        "RiposteButton": RiposteButton,
    }


def build_view_for_row(row: "PersistentView") -> discord.ui.View | None:
    """Construct a discord.ui.View with the DynamicItem for a persistent_views row.

    Args:
        row: A PersistentView model with custom_id and view_class fields.

    Returns:
        A View(timeout=None) containing a single DynamicItem instance, or None
        if the view_class name is unrecognized (logs WARNING, bot still boots).

    Note:
        The DynamicItem is instantiated by matching the custom_id against its
        template regex and parsing the named capture groups.
    """
    class_map = _get_dynamic_item_classes()
    cls = class_map.get(row.view_class)

    if cls is None:
        log.warning(
            "rehydration_unknown_class",
            view_class=row.view_class,
            custom_id=row.custom_id,
            message_id=row.message_id,
        )
        return None

    # Parse the custom_id using the class's template regex
    match = cls.template.fullmatch(row.custom_id)
    if match is None:
        log.warning(
            "rehydration_custom_id_mismatch",
            view_class=row.view_class,
            custom_id=row.custom_id,
            expected_pattern=cls.template.pattern,
        )
        return None

    # Build the DynamicItem from captured groups
    groups = match.groupdict()
    int_groups = {}
    for k, v in groups.items():
        try:
            int_groups[k] = int(v)
        except (ValueError, TypeError):
            int_groups[k] = v

    item = cls(**int_groups)

    view = discord.ui.View(timeout=None)
    view.add_item(item)
    return view


async def rehydrate_persistent_views(
    bot: discord.Client,
    repo: "PersistentViewRepo",
    channel_sessions_repo: "ChannelSessionRepo",
) -> int:
    """Rehydrate persistent views from the database after a restart.

    For each active channel session, fetches all persistent_view rows and
    registers a View containing the appropriate DynamicItem with discord.py.

    Args:
        bot: The discord.Client to call add_view() on.
        repo: PersistentViewRepo for reading view rows.
        channel_sessions_repo: ChannelSessionRepo for reading active sessions.

    Returns:
        Total number of views successfully rehydrated.

    Note (D-24, RESEARCH.md Pitfall 1):
        add_dynamic_items is the primary dispatch mechanism (registered in bot.py).
        These add_view() calls are an optional layer for message-scoped routing.
        Skipping a row (unknown class) does not abort rehydration.
    """
    sessions = await channel_sessions_repo.list_active()
    total = 0

    for session in sessions:
        rows = await repo.list_by_channel(session.channel_id)
        for row in rows:
            view = build_view_for_row(row)
            if view is None:
                continue
            try:
                bot.add_view(view, message_id=int(row.message_id))
                total += 1
            except Exception:  # noqa: BLE001
                log.warning(
                    "rehydration_add_view_failed",
                    custom_id=row.custom_id,
                    message_id=row.message_id,
                )

    log.info(
        "rehydrated_persistent_views",
        rehydrated_views=total,
        sessions=len(sessions),
    )
    return total
