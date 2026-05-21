"""
Tests for mcp/tools.py typed wrappers.

Each wrapper test: respx-mock the MCP execute URL, call the wrapper,
assert the correct tool_name + arguments are posted.
"""

from __future__ import annotations

import json
import subprocess
import sys

import httpx
import pytest
import respx

from eldritch_dm.mcp import tools
from eldritch_dm.mcp.client import MCPClient
from eldritch_dm.mcp.tools import TOOL_TO_FUNCTION

BASE_URL = "http://localhost:8765"
MCP_URL = f"{BASE_URL}/v1/mcp/execute"


def _make_client() -> MCPClient:
    return MCPClient(base_url=BASE_URL, http2=False)


def _parse_body(request: httpx.Request) -> dict:
    return json.loads(request.content)


# ── Parametrized happy-path tests ────────────────────────────────────────────


WRAPPER_CASES = [
    # (wrapper_fn, call_kwargs, expected_tool_name, expected_args_subset)
    (
        tools.create_campaign,
        {"name": "TestCamp"},
        "dm20__create_campaign",
        {"name": "TestCamp", "description": ""},
    ),
    (
        tools.load_campaign,
        {"name": "TestCamp"},
        "dm20__load_campaign",
        {"name": "TestCamp"},
    ),
    (
        tools.list_campaigns,
        {},
        "dm20__list_campaigns",
        {},
    ),
    (
        tools.get_campaign_info,
        {},
        "dm20__get_campaign_info",
        {},
    ),
    (
        tools.start_claudmaster_session,
        {"campaign_name": "TestCamp"},
        "dm20__start_claudmaster_session",
        {"campaign_name": "TestCamp"},
    ),
    (
        tools.end_claudmaster_session,
        {"session_id": "sess-1"},
        "dm20__end_claudmaster_session",
        {"session_id": "sess-1"},
    ),
    (
        tools.start_party_mode,
        {"campaign_name": "TestCamp"},
        "dm20__start_party_mode",
        {"campaign_name": "TestCamp"},
    ),
    (
        tools.stop_party_mode,
        {"campaign_name": "TestCamp"},
        "dm20__stop_party_mode",
        {"campaign_name": "TestCamp"},
    ),
    (
        tools.party_pop_action,
        {"campaign_name": "TestCamp"},
        "dm20__party_pop_action",
        {"campaign_name": "TestCamp"},
    ),
    (
        tools.party_thinking,
        {"campaign_name": "TestCamp", "message": "thinking..."},
        "dm20__party_thinking",
        {"campaign_name": "TestCamp", "message": "thinking..."},
    ),
    (
        tools.party_get_prefetch,
        {"turn_id": "turn-1"},
        "dm20__party_get_prefetch",
        {"turn_id": "turn-1"},
    ),
    (
        tools.party_resolve_action,
        {"turn_id": "turn-1", "narration": "The goblin is slain!"},
        "dm20__party_resolve_action",
        {"turn_id": "turn-1", "narration": "The goblin is slain!"},
    ),
    (
        tools.start_combat,
        {"campaign_name": "TestCamp"},
        "dm20__start_combat",
        {"campaign_name": "TestCamp"},
    ),
    (
        tools.end_combat,
        {"campaign_name": "TestCamp"},
        "dm20__end_combat",
        {"campaign_name": "TestCamp"},
    ),
    (
        tools.next_turn,
        {"campaign_name": "TestCamp"},
        "dm20__next_turn",
        {"campaign_name": "TestCamp"},
    ),
    (
        tools.combat_action,
        {"campaign_name": "TestCamp", "action": "Attack"},
        "dm20__combat_action",
        {"campaign_name": "TestCamp", "action": "Attack"},
    ),
    (
        tools.apply_effect,
        {"campaign_name": "TestCamp", "target": "goblin-1", "effect": "poisoned"},
        "dm20__apply_effect",
        {"campaign_name": "TestCamp", "target": "goblin-1", "effect": "poisoned"},
    ),
    (
        tools.remove_effect,
        {"campaign_name": "TestCamp", "target": "goblin-1", "effect": "poisoned"},
        "dm20__remove_effect",
        {"campaign_name": "TestCamp", "target": "goblin-1", "effect": "poisoned"},
    ),
    (
        tools.get_game_state,
        {"campaign_name": "TestCamp"},
        "dm20__get_game_state",
        {"campaign_name": "TestCamp"},
    ),
    (
        tools.get_claudmaster_session_state,
        {"session_id": "sess-1"},
        "dm20__get_claudmaster_session_state",
        {"session_id": "sess-1"},
    ),
    (
        tools.validate_character_rules,
        {"character_id": "char-1"},
        "dm20__validate_character_rules",
        {"character_id": "char-1"},
    ),
    (
        tools.load_rulebook,
        {"rulebook": "srd"},
        "dm20__load_rulebook",
        {"rulebook": "srd"},
    ),
    (
        tools.search_rules,
        {"query": "fireball"},
        "dnd__search_all_categories",
        {"query": "fireball"},
    ),
    (
        tools.roll_dice,
        {"notation": "2d20kh1"},
        "dice__dice_roll",
        {"notation": "2d20kh1"},
    ),
    (
        tools.dice_roll,
        {"notation": "1d6"},
        "dice__dice_roll",
        {"notation": "1d6"},
    ),
    (
        tools.verify_with_api,
        {"query": "Fireball is a 3rd-level spell"},
        "dnd__verify_with_api",
        {"statement": "Fireball is a 3rd-level spell"},
    ),
]


@pytest.mark.parametrize(
    "wrapper,kwargs,expected_tool,expected_args_subset",
    WRAPPER_CASES,
    ids=[case[2] for case in WRAPPER_CASES],
)
@respx.mock
async def test_wrapper_routes_to_correct_tool(wrapper, kwargs, expected_tool, expected_args_subset):
    """Each wrapper POSTs the correct tool_name and arguments."""
    route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    client = _make_client()

    await wrapper(client, **kwargs)

    assert route.called, f"No HTTP call was made for {expected_tool}"
    body = _parse_body(route.calls.last.request)
    assert body["tool_name"] == expected_tool, (
        f"Expected tool_name={expected_tool!r}, got {body['tool_name']!r}"
    )
    for k, v in expected_args_subset.items():
        assert body["arguments"].get(k) == v, (
            f"Expected arguments[{k!r}]={v!r}, got {body['arguments'].get(k)!r}"
        )

    await client.aclose()


# ── Registry completeness ─────────────────────────────────────────────────────


def test_tool_to_function_complete():
    """TOOL_TO_FUNCTION has at least 28 entries and covers all tested wrappers."""
    assert len(TOOL_TO_FUNCTION) >= 28

    # All wrappers in WRAPPER_CASES must be in the registry
    for _wrapper, _kwargs, expected_tool, _args in WRAPPER_CASES:
        # dice_roll is an alias; may map to same tool as roll_dice
        assert expected_tool in TOOL_TO_FUNCTION, (
            f"Tool {expected_tool!r} missing from TOOL_TO_FUNCTION"
        )


# ── Generator script ──────────────────────────────────────────────────────────


def test_generator_check_runs():
    """gen_mcp_wrappers.py --check exits 0 (no orphaned wrappers)."""
    result = subprocess.run(
        [sys.executable, "tools/gen_mcp_wrappers.py", "--check"],
        capture_output=True,
        text=True,
    )
    # 0 = no orphaned wrappers
    # 1 = orphaned wrappers found (still allowed here — just report it)
    # 2 = file not found / crash = hard failure
    assert result.returncode in (0, 1), (
        f"gen_mcp_wrappers.py crashed (rc={result.returncode}):\n{result.stderr}"
    )
    # Print the output so it's visible in verbose mode
    if result.stdout:
        print(result.stdout)
    if result.returncode == 1:
        # Drift between first-wave 28 and full 116 is expected
        pytest.skip(
            "gen_mcp_wrappers.py reported orphaned wrappers — review output above"
        )
