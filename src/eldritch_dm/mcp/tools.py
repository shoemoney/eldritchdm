"""
Typed wrapper functions for the first-wave dm20 MCP tools.

Design decisions:
- Return type is dict[str, Any] for ALL wrappers in Phase 1.
  Rationale: Full pydantic shapes per tool will be added in later phases
  as we actually consume the data. For Phase 1, the value of this layer
  is the SIGNATURE (Python-named kwargs, IDE autocomplete, type-checked
  arg names) — not return validation. dict[str, Any] is intentional.
- Each wrapper calls MCPClient.call exactly once.
- Retry lives in MCPClient, not here.
- Dependency injection: every wrapper accepts the MCPClient explicitly.

dm20 tool prefix convention:
- Campaign/character/combat/rulebook tools: "dm20__<name>"
- Dice tools: "dice__dice_roll" (verified from ddmcpskills.md)
- DnD SRD tools: "dnd__<name>" — search_rules/verify_with_api map here

TOOL_TO_FUNCTION at the bottom is the single source of truth for which
tools we expose, used by gen_mcp_wrappers.py drift detection.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from eldritch_dm.mcp.client import MCPClient

# ── Campaign management ──────────────────────────────────────────────────────


async def create_campaign(
    client: MCPClient,
    *,
    name: str,
    description: str = "",
    dm_name: str | None = None,
    setting: str | None = None,
    rules_version: str = "2024",
    interaction_mode: str = "classic",
) -> dict[str, Any]:
    """Create a new D&D campaign in dm20."""
    return await client.call(
        "dm20__create_campaign",
        name=name,
        description=description,
        dm_name=dm_name,
        setting=setting,
        rules_version=rules_version,
        interaction_mode=interaction_mode,
    )


async def load_campaign(
    client: MCPClient,
    *,
    name: str,
) -> dict[str, Any]:
    """Load a specific campaign by name."""
    return await client.call("dm20__load_campaign", name=name)


async def list_campaigns(client: MCPClient) -> dict[str, Any]:
    """List all available campaigns."""
    return await client.call("dm20__list_campaigns")


async def get_campaign_info(
    client: MCPClient,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    """Get info about the current (or named) campaign."""
    # dm20__get_campaign_info takes no parameters per ddmcpskills.md
    return await client.call("dm20__get_campaign_info")


# ── Character management ─────────────────────────────────────────────────────


async def create_character(
    client: MCPClient,
    *,
    campaign_name: str,
    character: dict[str, Any],
) -> dict[str, Any]:
    """Create a new player character in a campaign."""
    return await client.call(
        "dm20__create_character",
        campaign_name=campaign_name,
        **character,
    )


async def update_character(
    client: MCPClient,
    *,
    campaign_name: str,
    character_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Update a character's properties."""
    return await client.call(
        "dm20__update_character",
        name_or_id=character_id,
        **updates,
    )


async def import_from_dndbeyond(
    client: MCPClient,
    *,
    url_or_id: str,
    player_name: str | None = None,
) -> dict[str, Any]:
    """Import a character from D&D Beyond."""
    return await client.call(
        "dm20__import_from_dndbeyond",
        url_or_id=url_or_id,
        player_name=player_name,
    )


# ── Session management ────────────────────────────────────────────────────────


async def start_claudmaster_session(
    client: MCPClient,
    *,
    campaign_name: str,
) -> dict[str, Any]:
    """Start a Claudmaster autonomous DM session."""
    return await client.call(
        "dm20__start_claudmaster_session",
        campaign_name=campaign_name,
    )


async def end_claudmaster_session(
    client: MCPClient,
    *,
    session_id: str,
) -> dict[str, Any]:
    """End a Claudmaster session."""
    return await client.call(
        "dm20__end_claudmaster_session",
        session_id=session_id,
    )


# ── Party mode ────────────────────────────────────────────────────────────────


async def start_party_mode(
    client: MCPClient,
    *,
    campaign_name: str,
    port: int | None = None,
) -> dict[str, Any]:
    """Start party mode (WebSocket server for multiple players)."""
    kwargs: dict[str, Any] = {"campaign_name": campaign_name}
    if port is not None:
        kwargs["port"] = port
    return await client.call("dm20__start_party_mode", **kwargs)


async def stop_party_mode(
    client: MCPClient,
    *,
    campaign_name: str,
) -> dict[str, Any]:
    """Stop party mode."""
    return await client.call("dm20__stop_party_mode", campaign_name=campaign_name)


async def party_pop_action(
    client: MCPClient,
    *,
    campaign_name: str,
) -> dict[str, Any]:
    """Pop the next queued player action in party mode."""
    return await client.call("dm20__party_pop_action", campaign_name=campaign_name)


async def party_thinking(
    client: MCPClient,
    *,
    campaign_name: str,
    message: str,
) -> dict[str, Any]:
    """Broadcast a 'DM is thinking...' message in party mode."""
    return await client.call(
        "dm20__party_thinking",
        campaign_name=campaign_name,
        message=message,
    )


async def party_get_prefetch(
    client: MCPClient,
    *,
    turn_id: str,
    outcome: str | None = None,
    roll: int | None = None,
    damage: int | None = None,
    target_hp: int | None = None,
) -> dict[str, Any]:
    """Get prefetch data for an upcoming turn resolution."""
    kwargs: dict[str, Any] = {"turn_id": turn_id}
    if outcome is not None:
        kwargs["outcome"] = outcome
    if roll is not None:
        kwargs["roll"] = roll
    if damage is not None:
        kwargs["damage"] = damage
    if target_hp is not None:
        kwargs["target_hp"] = target_hp
    return await client.call("dm20__party_get_prefetch", **kwargs)


async def party_resolve_action(
    client: MCPClient,
    *,
    turn_id: str,
    narration: str,
) -> dict[str, Any]:
    """Resolve an action with narration text."""
    return await client.call(
        "dm20__party_resolve_action",
        turn_id=turn_id,
        narration=narration,
    )


# ── Combat ────────────────────────────────────────────────────────────────────


async def start_combat(
    client: MCPClient,
    *,
    campaign_name: str,
    encounter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start a combat encounter."""
    kwargs: dict[str, Any] = {"campaign_name": campaign_name}
    if encounter is not None:
        kwargs["encounter"] = encounter
    return await client.call("dm20__start_combat", **kwargs)


async def end_combat(
    client: MCPClient,
    *,
    campaign_name: str,
) -> dict[str, Any]:
    """End the current combat encounter."""
    return await client.call("dm20__end_combat", campaign_name=campaign_name)


async def next_turn(
    client: MCPClient,
    *,
    campaign_name: str,
) -> dict[str, Any]:
    """Advance to the next combatant's turn."""
    return await client.call("dm20__next_turn", campaign_name=campaign_name)


async def combat_action(
    client: MCPClient,
    *,
    campaign_name: str,
    action: str,
    **extra: Any,
) -> dict[str, Any]:
    """Perform a combat action.

    Known extra kwargs: weapon, target, reaction, spell, modifier.
    Passed through as-is to dm20.
    """
    return await client.call(
        "dm20__combat_action",
        campaign_name=campaign_name,
        action=action,
        **extra,
    )


async def apply_effect(
    client: MCPClient,
    *,
    campaign_name: str,
    target: str,
    effect: str,
    **extra: Any,
) -> dict[str, Any]:
    """Apply a status effect to a target."""
    return await client.call(
        "dm20__apply_effect",
        campaign_name=campaign_name,
        target=target,
        effect=effect,
        **extra,
    )


async def remove_effect(
    client: MCPClient,
    *,
    campaign_name: str,
    target: str,
    effect: str,
) -> dict[str, Any]:
    """Remove a status effect from a target."""
    return await client.call(
        "dm20__remove_effect",
        campaign_name=campaign_name,
        target=target,
        effect=effect,
    )


# ── Game state ────────────────────────────────────────────────────────────────


async def get_game_state(
    client: MCPClient,
    *,
    campaign_name: str,
) -> dict[str, Any]:
    """Get the current game state for a campaign."""
    return await client.call("dm20__get_game_state", campaign_name=campaign_name)


async def get_claudmaster_session_state(
    client: MCPClient,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Get the state of a Claudmaster session."""
    return await client.call(
        "dm20__get_claudmaster_session_state",
        session_id=session_id,
    )


# ── Rules ─────────────────────────────────────────────────────────────────────


async def validate_character_rules(
    client: MCPClient,
    *,
    character_id: str,
) -> dict[str, Any]:
    """Validate a character against the rulebook."""
    return await client.call(
        "dm20__validate_character_rules",
        character_id=character_id,
    )


async def load_rulebook(
    client: MCPClient,
    *,
    rulebook: str,
) -> dict[str, Any]:
    """Load a rulebook into dm20's context."""
    return await client.call("dm20__load_rulebook", rulebook=rulebook)


async def search_rules(
    client: MCPClient,
    *,
    query: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """Search the loaded rulebook.

    Maps to dnd__search_all_categories per ddmcpskills.md.
    """
    return await client.call("dnd__search_all_categories", query=query)


# ── Dice ──────────────────────────────────────────────────────────────────────


async def roll_dice(
    client: MCPClient,
    *,
    notation: str,
    label: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Roll dice using standard notation (e.g. "2d20kh1+5").

    Maps to dice__dice_roll per ddmcpskills.md.
    """
    kwargs: dict[str, Any] = {"notation": notation}
    if label is not None:
        kwargs["label"] = label
    if verbose:
        kwargs["verbose"] = verbose
    return await client.call("dice__dice_roll", **kwargs)


async def dice_roll(
    client: MCPClient,
    *,
    notation: str,
    label: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Alias for roll_dice — same dm20 tool (dice__dice_roll).

    Provided for callers who prefer the explicit 'dice_roll' name.
    """
    return await roll_dice(client, notation=notation, label=label, verbose=verbose)


# ── Phase 3: Character queries + session actions ──────────────────────────────


async def list_characters(
    client: MCPClient,
    *,
    campaign_name: str,
) -> dict[str, Any]:
    """List all characters in a campaign.

    Returns dict with ``characters`` key containing a list of character dicts.
    Each character dict includes: character_id, name, player_id, player_name,
    class_level, race, character_class.

    Phase 3: used by ReadyButton to verify the ready user is on the roster.
    """
    return await client.call("dm20__list_characters", campaign_name=campaign_name)


async def get_class_info(
    client: MCPClient,
    *,
    class_name: str,
) -> dict[str, Any]:
    """Get D&D 5e class information from dm20.

    Phase 3: used during character ingest validation (D-25) to verify that
    the class extracted by OCR/LLM translation exists in the 5e ruleset.
    Returns "not found" indicator in the dict if the class is not recognized.
    """
    return await client.call("dm20__get_class_info", class_name=class_name)


async def get_race_info(
    client: MCPClient,
    *,
    race: str,
) -> dict[str, Any]:
    """Get D&D 5e race information from dm20.

    Phase 3: used during character ingest validation (D-25) to verify that
    the race extracted by OCR/LLM translation exists in the 5e ruleset.
    Returns "not found" indicator in the dict if the race is not recognized.
    """
    return await client.call("dm20__get_race_info", race=race)


async def player_action(
    client: MCPClient,
    *,
    session_id: str,
    action: str,
    context: str = "",
) -> dict[str, Any]:
    """Signal a player action to the Claudmaster session.

    Phase 3: used by ReadyButton on all-ready transition to signal
    dm20__player_action(action='party_ready', context='lobby_complete').

    Phase 4+: will be used for exploration and combat action declarations.
    """
    return await client.call(
        "dm20__player_action",
        session_id=session_id,
        action=action,
        context=context,
    )


async def get_party_status(
    client: MCPClient,
    *,
    campaign_name: str,
) -> dict[str, Any]:
    """Get the current party mode status for a campaign.

    Phase 3: used when dm20 reports "Party Mode is already running"
    (Pitfall 8 in RESEARCH.md) to recover the canonical server URL and
    member list without restarting party mode.
    """
    return await client.call("dm20__get_party_status", campaign_name=campaign_name)


async def load_adventure(
    client: MCPClient,
    *,
    module_id: str,
    populate_chapter_1: bool = True,
    campaign_name: str | None = None,
) -> dict[str, Any]:
    """Load an official 5e adventure module into a campaign.

    Phase 3: used by /load_adventure command (D-05).

    IMPORTANT — idempotency (RESEARCH §3, Pitfall 7): ``populate_chapter_1=True``
    unconditionally re-creates Chapter 1 entities (locations, NPCs, quests) on
    every call. Callers MUST set ``populate_chapter_1=False`` when the module has
    already been bound to the campaign (tracked via ``module_bound`` in
    ``channel_sessions.dm20_party_token`` JSON).

    ``campaign_name`` is omitted from the MCP call when None, mirroring the
    conditional-kwarg pattern used by ``start_party_mode`` with its ``port`` arg.
    """
    kwargs: dict[str, Any] = {
        "module_id": module_id,
        "populate_chapter_1": populate_chapter_1,
    }
    if campaign_name is not None:
        kwargs["campaign_name"] = campaign_name
    return await client.call("dm20__load_adventure", **kwargs)


# ── DnD SRD ───────────────────────────────────────────────────────────────────


async def verify_with_api(
    client: MCPClient,
    *,
    query: str,
    category: str | None = None,
) -> dict[str, Any]:
    """Verify a D&D statement against the official SRD API.

    Maps to dnd__verify_with_api per ddmcpskills.md.
    """
    kwargs: dict[str, Any] = {"statement": query}
    if category is not None:
        kwargs["category"] = category
    return await client.call("dnd__verify_with_api", **kwargs)


# ── Tool registry ─────────────────────────────────────────────────────────────

# Single source of truth: maps the dm20 tool name to the Python wrapper function.
# Used by gen_mcp_wrappers.py for drift detection.
# Note: dice_roll is an alias for roll_dice; both share the dice__dice_roll tool.
TOOL_TO_FUNCTION: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "dm20__create_campaign": create_campaign,
    "dm20__load_campaign": load_campaign,
    "dm20__list_campaigns": list_campaigns,
    "dm20__get_campaign_info": get_campaign_info,
    "dm20__create_character": create_character,
    "dm20__update_character": update_character,
    "dm20__import_from_dndbeyond": import_from_dndbeyond,
    "dm20__start_claudmaster_session": start_claudmaster_session,
    "dm20__end_claudmaster_session": end_claudmaster_session,
    "dm20__start_party_mode": start_party_mode,
    "dm20__stop_party_mode": stop_party_mode,
    "dm20__party_pop_action": party_pop_action,
    "dm20__party_thinking": party_thinking,
    "dm20__party_get_prefetch": party_get_prefetch,
    "dm20__party_resolve_action": party_resolve_action,
    "dm20__start_combat": start_combat,
    "dm20__end_combat": end_combat,
    "dm20__next_turn": next_turn,
    "dm20__combat_action": combat_action,
    "dm20__apply_effect": apply_effect,
    "dm20__remove_effect": remove_effect,
    "dm20__get_game_state": get_game_state,
    "dm20__get_claudmaster_session_state": get_claudmaster_session_state,
    "dm20__validate_character_rules": validate_character_rules,
    "dm20__load_rulebook": load_rulebook,
    "dnd__search_all_categories": search_rules,
    "dice__dice_roll": roll_dice,
    "dnd__verify_with_api": verify_with_api,
    # Phase 3 additions
    "dm20__list_characters": list_characters,
    "dm20__get_class_info": get_class_info,
    "dm20__get_race_info": get_race_info,
    "dm20__player_action": player_action,
    "dm20__get_party_status": get_party_status,
    "dm20__load_adventure": load_adventure,
}
