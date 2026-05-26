"""
Parser for dm20's get_game_state markdown response.

dm20 returns formatted markdown text from get_game_state, not JSON.
This module provides regex-based parsing to extract structured game state.

Source: dm20-protocol/src/dm20_protocol/main.py:1627-1668 (04-RESEARCH.md Pattern 4)

Example dm20 output::

    ## Game State

    **Campaign:** My Campaign
    **In Combat:** No
    **Current Turn:** None
    **Round:** 0

    ### Initiative Order
    (no active combat)

    **Location:** Tavern

Regex patterns are stable because the format is hand-written in dm20's source.
TODO: if dm20 ever ships get_game_state_json, swap the parser here.

Phase 4 Plan 01.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Compiled patterns ──────────────────────────────────────────────────────────

_IN_COMBAT_RE = re.compile(r"\*\*In Combat:\*\*\s+(Yes|No)", re.IGNORECASE)
_CURRENT_TURN_RE = re.compile(r"\*\*Current Turn:\*\*\s+(.+?)$", re.MULTILINE)
_ROUND_RE = re.compile(r"\*\*Round:\*\*\s+(\d+)", re.MULTILINE)
_CAMPAIGN_RE = re.compile(r"\*\*Campaign:\*\*\s+(.+?)$", re.MULTILINE)

# Initiative rows: "  1. Thorin (Initiative: 18)"
_INIT_ROW_RE = re.compile(
    r"^\s+\d+\.\s+(.+?)\s+\(Initiative:\s+(-?\d+)\)$", re.MULTILINE
)


# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedGameState:
    """Structured game state parsed from dm20's markdown response.

    Attributes:
        in_combat: True if dm20 reports "In Combat: Yes".
        current_turn: Name of the current actor (None if not in combat or not present).
        initiative_order: List of (name, initiative_score) tuples, in order.
        round_number: Current combat round (0 if not in combat).
        campaign_name: Campaign name from the state (empty string if not found).
        raw: The original markdown string (for debugging).
    """

    in_combat: bool
    current_turn: str | None
    initiative_order: list[tuple[str, int]]
    round_number: int
    campaign_name: str
    raw: str = field(compare=False, repr=False)


# ── Parser ─────────────────────────────────────────────────────────────────────


def parse_game_state(raw: str) -> ParsedGameState:
    """Parse dm20's get_game_state markdown response into structured data.

    Args:
        raw: The raw markdown string returned by dm20__get_game_state.

    Returns:
        ParsedGameState with in_combat, current_turn, initiative_order,
        round_number, campaign_name, and the original raw text.

    Example::

        state = parse_game_state(await tools.get_game_state(client))
        if state.in_combat:
            # Switch to combat embed
            ...
    """
    # in_combat
    in_combat_m = _IN_COMBAT_RE.search(raw)
    in_combat = bool(in_combat_m and in_combat_m.group(1).lower() == "yes")

    # current_turn (the current actor name)
    current_turn_m = _CURRENT_TURN_RE.search(raw)
    current_turn: str | None = None
    if current_turn_m:
        ct = current_turn_m.group(1).strip()
        if ct.lower() not in ("none", "n/a", ""):
            current_turn = ct

    # initiative order
    initiative_order = [
        (m.group(1).strip(), int(m.group(2)))
        for m in _INIT_ROW_RE.finditer(raw)
    ]

    # round number
    round_m = _ROUND_RE.search(raw)
    round_number = int(round_m.group(1)) if round_m else 0

    # campaign name
    campaign_m = _CAMPAIGN_RE.search(raw)
    campaign_name = campaign_m.group(1).strip() if campaign_m else ""

    return ParsedGameState(
        in_combat=in_combat,
        current_turn=current_turn,
        initiative_order=initiative_order,
        round_number=round_number,
        campaign_name=campaign_name,
        raw=raw,
    )
