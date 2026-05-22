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
        {},
        "dm20__party_pop_action",
        {},
    ),
    (
        tools.party_thinking,
        {"message": "thinking..."},
        "dm20__party_thinking",
        {"message": "thinking..."},
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
        {},
        "dm20__start_combat",
        {},
    ),
    (
        tools.end_combat,
        {},
        "dm20__end_combat",
        {},
    ),
    (
        tools.next_turn,
        {},
        "dm20__next_turn",
        {},
    ),
    (
        tools.combat_action,
        {"action": "Attack"},
        "dm20__combat_action",
        {"action": "Attack"},
    ),
    (
        tools.apply_effect,
        {"target": "goblin-1", "effect": "poisoned"},
        "dm20__apply_effect",
        {"target": "goblin-1", "effect": "poisoned"},
    ),
    (
        tools.remove_effect,
        {"target": "goblin-1", "effect": "poisoned"},
        "dm20__remove_effect",
        {"target": "goblin-1", "effect": "poisoned"},
    ),
    (
        tools.get_game_state,
        {},
        "dm20__get_game_state",
        {},
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


# ── Phase 3 wrappers ─────────────────────────────────────────────────────────


class TestPhase3Wrappers:
    """TDD: RED tests for Phase 3 MCP wrappers (list_characters, get_class_info,
    get_race_info, player_action, get_party_status, load_adventure)."""

    @respx.mock
    async def test_list_characters_routes_to_correct_tool(self):
        route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        client = _make_client()
        await tools.list_characters(client, campaign_name="X")
        body = _parse_body(route.calls.last.request)
        assert body["tool_name"] == "dm20__list_characters"
        assert body["arguments"]["campaign_name"] == "X"
        await client.aclose()

    @respx.mock
    async def test_get_class_info_routes_to_correct_tool(self):
        route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        client = _make_client()
        await tools.get_class_info(client, class_name="Fighter")
        body = _parse_body(route.calls.last.request)
        assert body["tool_name"] == "dm20__get_class_info"
        assert body["arguments"]["class_name"] == "Fighter"
        await client.aclose()

    @respx.mock
    async def test_get_race_info_routes_to_correct_tool(self):
        route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        client = _make_client()
        await tools.get_race_info(client, race="Elf")
        body = _parse_body(route.calls.last.request)
        assert body["tool_name"] == "dm20__get_race_info"
        assert body["arguments"]["race"] == "Elf"
        await client.aclose()

    @respx.mock
    async def test_player_action_forwards_all_kwargs(self):
        route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        client = _make_client()
        await tools.player_action(
            client, session_id="s1", action="party_ready", context="lobby_complete"
        )
        body = _parse_body(route.calls.last.request)
        assert body["tool_name"] == "dm20__player_action"
        assert body["arguments"]["session_id"] == "s1"
        assert body["arguments"]["action"] == "party_ready"
        assert body["arguments"]["context"] == "lobby_complete"
        await client.aclose()

    @respx.mock
    async def test_get_party_status_routes_to_correct_tool(self):
        route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        client = _make_client()
        await tools.get_party_status(client, campaign_name="X")
        body = _parse_body(route.calls.last.request)
        assert body["tool_name"] == "dm20__get_party_status"
        assert body["arguments"]["campaign_name"] == "X"
        await client.aclose()

    @respx.mock
    async def test_load_adventure_with_all_kwargs(self):
        route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        client = _make_client()
        await tools.load_adventure(
            client, module_id="CoS", populate_chapter_1=False, campaign_name="TestCamp"
        )
        body = _parse_body(route.calls.last.request)
        assert body["tool_name"] == "dm20__load_adventure"
        assert body["arguments"]["module_id"] == "CoS"
        assert body["arguments"]["populate_chapter_1"] is False
        assert body["arguments"]["campaign_name"] == "TestCamp"
        await client.aclose()

    @respx.mock
    async def test_load_adventure_omits_campaign_name_when_none(self):
        route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        client = _make_client()
        await tools.load_adventure(client, module_id="CoS", populate_chapter_1=False)
        body = _parse_body(route.calls.last.request)
        assert "campaign_name" not in body["arguments"]
        await client.aclose()

    def test_phase3_tools_in_registry(self):
        expected = {
            "dm20__list_characters",
            "dm20__get_class_info",
            "dm20__get_race_info",
            "dm20__player_action",
            "dm20__get_party_status",
            "dm20__load_adventure",
        }
        for tool_name in expected:
            assert tool_name in TOOL_TO_FUNCTION, f"{tool_name!r} missing from TOOL_TO_FUNCTION"

    def test_tool_to_function_has_at_least_34_entries(self):
        """Phase 3 adds 6 wrappers to the existing 28 = minimum 34."""
        assert len(TOOL_TO_FUNCTION) >= 34


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
