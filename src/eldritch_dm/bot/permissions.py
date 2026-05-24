"""
Permission helpers for EldritchDM bot.

This module is PURE: it accepts Discord interaction objects but only reads
attributes — no async, no Discord API calls, no I/O.

Importable in tests without a running bot or a Discord gateway connection.

Design decisions:
  - D-29 (CONTEXT.md): Permission gate combines ownership AND DM rights.
    The "DM" is identified by the Discord ``manage_channels`` permission on
    the invoking channel — a reliable DM proxy that requires no custom roles.
  - RESEARCH §12 (manage_channels): ``interaction.user.guild_permissions``
    is resolved by discord.py including channel-level permission overwrites.
    In DM (direct message) contexts, ``guild_permissions`` is absent and
    ``getattr`` falls through to ``None``, returning False — correct behavior.
  - T-03-03 (PLAN threat model): /load_adventure and other DM-only commands
    gate on ``can_act_on_character(interaction, character_player_id=None)``,
    which skips the ownership check and falls directly to manage_channels.
  - INGEST-10: shared with the ingest cog in Plan 02 — do NOT alter the
    signature without updating both consumers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord


def can_act_on_character(
    interaction: discord.Interaction,
    character_player_id: str | None,
) -> bool:
    """Return True if the invoking user may act on the given character.

    Implements the two-path gate from CONTEXT D-29 and RESEARCH §12:

    1. **Owner path**: ``str(interaction.user.id) == character_player_id``.
       Any player can manage their own character.
    2. **DM path**: ``interaction.user.guild_permissions.manage_channels``.
       Any user with manage_channels on the channel is treated as the DM and
       may act on any character.

    When ``character_player_id`` is None (DM-only gates like /load_adventure
    or /start_game), the owner path is skipped and only the DM path applies.

    Args:
        interaction: Discord interaction from the invoking user.
        character_player_id: String Discord user ID of the character's owner,
            or None for commands that have no per-character ownership concept.

    Returns:
        True if the invoking user is the character owner OR has manage_channels.

    CONTEXT ref: D-29
    RESEARCH ref: §12 (manage_channels permission gate)
    Threat ref: T-03-03 (elevation of privilege via /load_adventure)
    """
    if character_player_id and str(interaction.user.id) == character_player_id:
        return True
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.manage_channels)
