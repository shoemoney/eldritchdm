"""
EldritchDM embed renderers.

All functions in this module are PURE: no I/O, no async, no Discord client
references. They accept data and return a `discord.Embed`. This keeps them
trivially testable and ensures the visual language is stable across phases.

Color palette (D-15):
    LOBBY            = 0x5865F2  (Discord blurple)
    EXPLORATION      = 0x57F287  (green)
    COMBAT           = 0xED4245  (red)
    CHARACTER_CONFIRM = 0xFEE75C (yellow)

Footer (D-16): every embed includes ``🎲 ShoeGPT · EldritchDM`` + timestamp.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum
from typing import Sequence

import discord

# ── Palette ────────────────────────────────────────────────────────────────────


class EmbedColor(IntEnum):
    """Discord embed color values for each game context (D-15)."""

    LOBBY = 0x5865F2
    EXPLORATION = 0x57F287
    COMBAT = 0xED4245
    CHARACTER_CONFIRM = 0xFEE75C


# ── Footer ─────────────────────────────────────────────────────────────────────

_FOOTER_TEXT = "🎲 ShoeGPT · EldritchDM"


# ── Shared dataclasses ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlayerStatus:
    """Snapshot of a player's lobby state for embed rendering."""

    display_name: str
    ready: bool
    character_name: str | None = None


# ── Internal helpers ───────────────────────────────────────────────────────────


def _apply_footer(embed: discord.Embed) -> None:
    """Add standard footer + current UTC timestamp to *embed* in-place."""
    embed.set_footer(text=_FOOTER_TEXT)
    embed.timestamp = datetime.now(tz=UTC)


# ── Embed renderers ────────────────────────────────────────────────────────────


def lobby_embed(
    *,
    campaign_name: str,
    players: Sequence[PlayerStatus],
    party_invite: str | None = None,
    server_url: str | None = None,
    transition_state: str | None = None,
) -> discord.Embed:
    """Render the lobby status embed.

    Args:
        campaign_name: Name of the campaign / session.
        players: Sequence of :class:`PlayerStatus` snapshots.
        party_invite: Optional invite URL; if provided a ``Join Party Mode``
            field is added; omitted when ``None``. (back-compat with Phase 2 callers)
        server_url: Optional Party Mode server base URL. When provided, adds a
            ``Party Mode Server`` field to the embed. Phase 3 addition (D-09).
        transition_state: Optional state hint for the description suffix.
            ``"transitioning"`` → "All ready — entering EXPLORATION…"
            ``"exploration"`` → "EXPLORATION active"
            ``None`` or ``"lobby"`` → "Waiting for players to ready up"

    Returns:
        A :class:`discord.Embed` with LOBBY color.
    """
    lines = [
        f"{'✅' if p.ready else '⌛'} **{p.display_name}** — {p.character_name or 'no character yet'}"
        for p in players
    ]
    player_block = "\n".join(lines) if lines else "*No players yet.*"

    # Append description suffix based on transition state
    if transition_state == "transitioning":
        suffix = "\n\n✅ All ready — entering EXPLORATION…"
    elif transition_state == "exploration":
        suffix = "\n\n🟢 EXPLORATION active"
    else:
        suffix = "\n\nWaiting for players to ready up."

    description = player_block + suffix

    embed = discord.Embed(
        title=f"⚔️ {campaign_name} — Lobby",
        description=description,
        color=int(EmbedColor.LOBBY),
    )

    if party_invite is not None:
        embed.add_field(name="Join Party Mode", value=party_invite, inline=False)

    if server_url is not None:
        embed.add_field(name="Party Mode Server", value=server_url, inline=False)

    _apply_footer(embed)
    return embed


def room_embed(
    *,
    room_title: str,
    narration: str,
    party_hp: Sequence[tuple[str, int, int]],
) -> discord.Embed:
    """Render the exploration room embed.

    Args:
        room_title: Short room/location name.
        narration: DM narration text (truncated to 4000 chars).
        party_hp: Sequence of ``(character_name, current_hp, max_hp)`` tuples.

    Returns:
        A :class:`discord.Embed` with EXPLORATION color.
    """
    embed = discord.Embed(
        title=f"🗺️ {room_title}",
        description=narration[:4000],
        color=int(EmbedColor.EXPLORATION),
    )

    if party_hp:
        hp_lines = [f"**{name}** — {cur}/{max_hp} HP" for name, cur, max_hp in party_hp]
        embed.add_field(name="Party", value="\n".join(hp_lines), inline=False)

    _apply_footer(embed)
    return embed


def combat_embed(
    *,
    round_n: int,
    current_actor: str,
    initiative: Sequence[tuple[str, int, int, int, list[str]]],
) -> discord.Embed:
    """Render the combat turn-order embed.

    Args:
        round_n: Current combat round number.
        current_actor: Display name of the actor whose turn it is.
        initiative: Sequence of
            ``(name, initiative_roll, hp_cur, hp_max, conditions)`` tuples
            sorted by initiative descending.

    Returns:
        A :class:`discord.Embed` with COMBAT color.
    """
    embed = discord.Embed(
        title=f"⚔️ Combat — Round {round_n}",
        description=f"Current turn: **{current_actor}**",
        color=int(EmbedColor.COMBAT),
    )

    for name, init, hp_cur, hp_max, conditions in initiative:
        marker = " ⏳" if name == current_actor else ""
        cond_str = ", ".join(conditions) if conditions else "—"
        embed.add_field(
            name=f"{name}{marker}",
            value=f"init {init} · HP {hp_cur}/{hp_max} · {cond_str}",
            inline=False,
        )

    _apply_footer(embed)
    return embed


def character_confirm_embed(
    *,
    player_name: str,
    character: dict,
) -> discord.Embed:
    """Render the character confirmation embed.

    Renders only the fields enumerated in D-13 (T-02-08 mitigated):
    name, race, class, level, ability_scores, hp, ac.

    Args:
        player_name: Discord display name of the player.
        character: Character data dict (DDB-shaped or equivalent).

    Returns:
        A :class:`discord.Embed` with CHARACTER_CONFIRM color.
    """
    # T-02-08: extract only the enumerated fields — never splat full JSON
    safe_fields = {
        k: character.get(k)
        for k in ("name", "race", "class", "level", "ability_scores", "hp", "ac")
    }
    pretty = json.dumps(safe_fields, indent=2, ensure_ascii=False)

    description = f"```json\n{pretty}\n```\n\n✅ Confirm or ❌ Cancel"

    embed = discord.Embed(
        title=f"📜 Confirm Character — {player_name}",
        description=description,
        color=int(EmbedColor.CHARACTER_CONFIRM),
    )

    _apply_footer(embed)
    return embed
