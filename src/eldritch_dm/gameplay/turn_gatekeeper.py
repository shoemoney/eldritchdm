"""
Turn gatekeeper -- pure dict-shape helpers for combat turn enforcement.

No I/O, no async, no Discord imports. Depends only on the Python stdlib.
These helpers are called from combat button callbacks to gate Discord user
actions based on whether it is their character turn.

Shape contract: actor dict
{
    "id":          str,              -- dm20 character/monster unique id
    "name":        str,              -- display name
    "player_id":   str | int | None, -- Discord user snowflake string (None for monsters)
    "hp_current":  int,
    "hp_max":      int,
    "ac":          int,
    "conditions":  list[str],        -- e.g. ["stunned", "poisoned"]
}

game_state dict (our enriched form wrapping dm20 parsed data):
{
    "current_actor_id": str | None,  -- id of the actor whose turn it is
    "combatants":       list[dict],  -- list of actor dicts in initiative order
    "round_number":     int,
    "in_combat":        bool,
}

Note: dm20's get_game_state returns markdown text (not JSON). The
gameplay.game_state_parser module parses it into ParsedGameState.
The "game_state dict" shape above is what we build when enriching
ParsedGameState with per-combatant HP/AC/conditions pulled from
individual get_character calls in the CombatCog.
"""

from __future__ import annotations

from typing import Any


def is_actor(interaction_user_id: str, actor: dict[str, Any]) -> bool:
    """Return True if interaction_user_id matches actor player_id.

    Both sides are coerced to str before comparison so callers can pass
    either int or str Discord snowflakes without worrying about types.

    Returns False immediately when actor.player_id is None (monster turn) --
    no Discord user can act on behalf of a monster via the button UI.

    Args:
        interaction_user_id: The Discord user id from interaction.user.id
                             (str, but may be passed as int by callers).
        actor: Actor dict with at least a "player_id" key.

    Returns:
        True if the user_id matches the actor player_id; False otherwise.

    Example::

        current_actor = current_actor_from_game_state(game_state)
        if not is_actor(str(interaction.user.id), current_actor):
            await send_warning(interaction, WarningKind.NOT_YOUR_TURN, ...)
    """
    player_id = actor.get("player_id")
    if player_id is None:
        return False
    return str(interaction_user_id) == str(player_id)


def player_id_for_actor(actor: dict[str, Any]) -> str | None:
    """Return actor player_id as str, or None if absent/falsy.

    Args:
        actor: Actor dict with an optional "player_id" key.

    Returns:
        str(actor["player_id"]) if present and non-None, else None.

    Example::

        pid = player_id_for_actor(actor)
        if pid is not None:
            # This is a PC turn
    """
    pid = actor.get("player_id")
    if pid is None:
        return None
    return str(pid)


def current_actor_from_game_state(game_state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the combatant dict for the current turn, or None.

    Looks up game_state["current_actor_id"] in game_state["combatants"]
    by matching the "id" field. Returns None when:
      - game_state is empty
      - current_actor_id is None
      - no combatant matches the id

    Args:
        game_state: Enriched game state dict (see module-level shape comment).

    Returns:
        The matching combatant dict, or None.

    Example::

        current = current_actor_from_game_state(game_state)
        if current is None or not is_actor(user_id, current):
            await send_warning(interaction, WarningKind.NOT_YOUR_TURN, ...)
    """
    current_id = game_state.get("current_actor_id")
    if not current_id:
        return None

    combatants = game_state.get("combatants") or []
    for combatant in combatants:
        if combatant.get("id") == current_id:
            return combatant

    return None
