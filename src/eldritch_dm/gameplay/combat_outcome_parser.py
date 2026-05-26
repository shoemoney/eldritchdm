"""
Regex parser for dm20 combat_action text output.

dm20's `combat_action` returns formatted markdown text (NOT JSON). The header
line tells us hit/miss/critical/nat1 — see `dm20/src/dm20_protocol/main.py`
function `_format_combat_result` (around lines 1839-1873) for the source of
truth. Format strings are hand-coded in dm20, so the headers are stable:

  - **CRITICAL HIT!** {attacker} strikes {target}!
  - **Hit!** {attacker} hits {target}.
  - **Natural 1!** {attacker} misses {target}.
  - **Miss.** {attacker} misses {target}.

If dm20 ever drifts the format, the gated `RUN_INTEGRATION=1` smoke would
catch it — pin the parser to dm20's source version if drift becomes a real
risk (Phase 5 RESEARCH risk register T-05-02).

Phase 5 Plan 01.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from enum import StrEnum


class AttackOutcome(StrEnum):
    """Classification of a combat_action text outcome.

    Used by MonsterDriver to decide whether to surface a Riposte button:
        MISS / NATURAL_ONE → eligible PC may riposte (RAW Battle Master).
        HIT / CRITICAL    → no riposte trigger.
    """

    HIT = "hit"
    CRITICAL = "critical"
    MISS = "miss"
    NATURAL_ONE = "natural_one"


# Stable headers from dm20's _format_combat_result. Use re.MULTILINE so the
# header can appear on any line of the response, not just the first one.
_HEADER_RE = re.compile(
    r"^\*\*(?P<header>CRITICAL HIT!|Hit!|Natural 1!|Miss\.)\*\*",
    re.MULTILINE,
)


def parse_combat_outcome(raw: str) -> AttackOutcome | None:
    """Return the AttackOutcome implied by the first matching header in `raw`.

    Args:
        raw: The text body returned by dm20__combat_action.

    Returns:
        AttackOutcome enum value, or None if no recognized header is present.

    Example::

        outcome = parse_combat_outcome("**Miss.** Goblin Scout misses Thorin.")
        # outcome == AttackOutcome.MISS
    """
    if not raw:
        return None
    m = _HEADER_RE.search(raw)
    if m is None:
        return None
    header = m.group("header")
    if header == "CRITICAL HIT!":
        return AttackOutcome.CRITICAL
    if header == "Hit!":
        return AttackOutcome.HIT
    if header == "Natural 1!":
        return AttackOutcome.NATURAL_ONE
    if header == "Miss.":
        return AttackOutcome.MISS
    return None  # defensive — regex shouldn't allow other matches
