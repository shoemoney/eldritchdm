"""Unit tests for eldritch_dm.ingest.translate.

The oMLX HTTP call is mocked via unittest.mock — no real network needed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from eldritch_dm.ingest.schema import CharacterSheet
from eldritch_dm.ingest.translate import (
    TRANSLATE_SYSTEM_PROMPT,
    _defensive_json_parse,
    translate_to_character_sheet,
)

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

VALID_SHEET_DICT = {
    "name": "Thalindra",
    "character_class": "Wizard",
    "class_level": 5,
    "race": "High Elf",
    "abilities": {
        "strength": 8,
        "dexterity": 16,
        "constitution": 14,
        "intelligence": 18,
        "wisdom": 12,
        "charisma": 10,
    },
    "hp": 35,
    "ac": 13,
    "skills": ["Arcana", "History"],
}

RAW_TEXT = "Character Name: Thalindra\nClass: Wizard Level: 5\nRace: High Elf"


def _make_openai_client(response_json: dict | None = None, raise_exc: Exception | None = None):
    """Build a mock AsyncOpenAI client that returns response_json or raises raise_exc."""
    client = MagicMock()

    if raise_exc:
        client.chat.completions.create = AsyncMock(side_effect=raise_exc)
    else:
        content = json.dumps(response_json or VALID_SHEET_DICT)
        message = MagicMock()
        message.content = content
        choice = MagicMock()
        choice.message = message
        completion = MagicMock()
        completion.choices = [choice]
        client.chat.completions.create = AsyncMock(return_value=completion)

    return client


# ---------------------------------------------------------------------------
# _defensive_json_parse
# ---------------------------------------------------------------------------


class TestDefensiveJsonParse:
    def test_plain_json(self):
        data = _defensive_json_parse('{"name": "Elf"}')
        assert data["name"] == "Elf"

    def test_strips_json_fence(self):
        raw = '```json\n{"name": "Elf"}\n```'
        data = _defensive_json_parse(raw)
        assert data["name"] == "Elf"

    def test_strips_bare_fence(self):
        raw = '```\n{"name": "Elf"}\n```'
        data = _defensive_json_parse(raw)
        assert data["name"] == "Elf"

    def test_invalid_json_raises(self):
        import json as _json
        with pytest.raises((_json.JSONDecodeError, ValueError)):
            _defensive_json_parse("this is not json")

    def test_empty_raises(self):
        import json as _json
        with pytest.raises((_json.JSONDecodeError, ValueError)):
            _defensive_json_parse("")


# ---------------------------------------------------------------------------
# TRANSLATE_SYSTEM_PROMPT
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_contains_schema_keys(self):
        """System prompt must reference all required JSON keys."""
        for key in ("name", "character_class", "class_level", "race", "abilities"):
            assert key in TRANSLATE_SYSTEM_PROMPT

    def test_no_markdown_fences_in_prompt(self):
        """The prompt itself should not accidentally contain ``` fences."""
        assert "```" not in TRANSLATE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# translate_to_character_sheet
# ---------------------------------------------------------------------------


class TestTranslateToCharacterSheet:
    async def test_happy_path_returns_sheet(self):
        """Valid oMLX response -> CharacterSheet returned with no warnings."""
        client = _make_openai_client(VALID_SHEET_DICT)
        sheet, warnings = await translate_to_character_sheet(RAW_TEXT, openai_client=client)
        assert isinstance(sheet, CharacterSheet)
        assert sheet.name == "Thalindra"
        assert sheet.class_level == 5
        assert len(warnings) == 0

    async def test_omlx_exception_returns_none(self):
        """oMLX connection error -> returns (None, [warning])."""
        client = _make_openai_client(raise_exc=Exception("connection refused"))
        sheet, warnings = await translate_to_character_sheet(RAW_TEXT, openai_client=client)
        assert sheet is None
        assert any("oMLX translation failed" in w for w in warnings)

    async def test_invalid_json_response_returns_none(self):
        """Non-JSON oMLX content -> returns (None, [warning with JSON error info])."""
        client = MagicMock()
        message = MagicMock()
        message.content = "I'm sorry, I cannot do that."
        choice = MagicMock()
        choice.message = message
        completion = MagicMock()
        completion.choices = [choice]
        client.chat.completions.create = AsyncMock(return_value=completion)

        sheet, warnings = await translate_to_character_sheet(RAW_TEXT, openai_client=client)
        assert sheet is None
        assert len(warnings) > 0  # some error warning was emitted

    async def test_validation_error_returns_none(self):
        """JSON that fails pydantic validation -> returns (None, [field error warnings])."""
        bad_data = {**VALID_SHEET_DICT, "class_level": 99}  # out of range
        client = _make_openai_client(bad_data)
        sheet, warnings = await translate_to_character_sheet(RAW_TEXT, openai_client=client)
        assert sheet is None
        assert len(warnings) > 0  # field errors surfaced as warnings

    async def test_fenced_json_still_parsed(self):
        """JSON inside ``` fences -> still produces a valid CharacterSheet."""
        raw_content = f"```json\n{json.dumps(VALID_SHEET_DICT)}\n```"
        client = MagicMock()
        message = MagicMock()
        message.content = raw_content
        choice = MagicMock()
        choice.message = message
        completion = MagicMock()
        completion.choices = [choice]
        client.chat.completions.create = AsyncMock(return_value=completion)

        sheet, warnings = await translate_to_character_sheet(RAW_TEXT, openai_client=client)
        assert sheet is not None
        assert sheet.name == "Thalindra"

    async def test_truncation_warning_emitted(self):
        """Very long OCR text should emit a truncation warning (rule: max_chars=4000)."""
        long_text = "x" * 5000
        client = _make_openai_client(VALID_SHEET_DICT)
        _sheet, warnings = await translate_to_character_sheet(long_text, openai_client=client)
        assert any("truncated" in w.lower() for w in warnings)

    async def test_openai_called_with_json_object_format(self):
        """Must call oMLX with response_format={'type': 'json_object'} and temperature=0.05."""
        client = _make_openai_client(VALID_SHEET_DICT)
        await translate_to_character_sheet(RAW_TEXT, openai_client=client)

        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("response_format") == {"type": "json_object"}
        assert call_kwargs.get("temperature") == 0.05

    async def test_system_prompt_included(self):
        """Must include the system prompt in the messages list."""
        client = _make_openai_client(VALID_SHEET_DICT)
        await translate_to_character_sheet(RAW_TEXT, openai_client=client)

        messages = client.chat.completions.create.call_args.kwargs["messages"]
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"] == TRANSLATE_SYSTEM_PROMPT
