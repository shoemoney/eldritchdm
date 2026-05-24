"""
Tests for eldritch_dm.bot.party_mode_parser.

Covers:
  - Happy-path parsing: server_url + member list (URL + QR path)
  - QR generation-failed placeholder → qr_path=None
  - "Already running" response: already_running=True, members=[]
  - Malformed input: missing **Server:** line → ValueError
  - Input starting with "Error:" → ValueError
  - Whitespace tolerance in member blocks
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from eldritch_dm.bot.party_mode_parser import (
    ParsePartyResult,
    PartyMember,
    parse_party_mode_response,
)

# ── Sample markdown fixtures ────────────────────────────────────────────────────

SAMPLE_HAPPY_PATH = textwrap.dedent("""\
    # Party Mode Active

    **Server:** http://192.168.1.5:8080
    **Players:** 2 PCs + 1 Observer

    ## Player Connections

    ### Aragorn
    - **URL:** http://192.168.1.5:8080/play?token=abc123
    - **QR Code:** /tmp/campaigns/TestCamp/qr_codes/Aragorn.png

    ### Legolas
    - **URL:** http://192.168.1.5:8080/play?token=def456
    - **QR Code:** /tmp/campaigns/TestCamp/qr_codes/Legolas.png

    ---
    Scan the QR code or use the URL to join.
""")

SAMPLE_QR_FAILED = textwrap.dedent("""\
    # Party Mode Active

    **Server:** http://192.168.1.5:8080
    **Players:** 1 PC

    ## Player Connections

    ### Gimli
    - **URL:** http://192.168.1.5:8080/play?token=ggg999
    - **QR Code:** (generation failed, use URL instead)

    ---
""")

SAMPLE_ALREADY_RUNNING = textwrap.dedent("""\
    Party Mode is already running at http://192.168.1.5:8080

    **Server:** http://192.168.1.5:8080
""")

SAMPLE_MISSING_SERVER = textwrap.dedent("""\
    # Party Mode Active

    ### Aragorn
    - **URL:** http://192.168.1.5:8080/play?token=abc123
    - **QR Code:** /tmp/qr.png
""")


# ── Test 1: happy-path parsing ──────────────────────────────────────────────────


class TestHappyPath:
    def test_returns_parse_party_result(self):
        result = parse_party_mode_response(SAMPLE_HAPPY_PATH)
        assert isinstance(result, ParsePartyResult)

    def test_server_url_extracted(self):
        result = parse_party_mode_response(SAMPLE_HAPPY_PATH)
        assert result.server_url == "http://192.168.1.5:8080"

    def test_member_count(self):
        """Two ### blocks → two members."""
        with patch("eldritch_dm.bot.party_mode_parser.Path") as mock_path_cls:
            mock_path_instance = mock_path_cls.return_value
            mock_path_instance.exists.return_value = True
            result = parse_party_mode_response(SAMPLE_HAPPY_PATH)
        assert len(result.members) == 2

    def test_member_names(self):
        with patch("eldritch_dm.bot.party_mode_parser.Path") as mock_path_cls:
            mock_path_instance = mock_path_cls.return_value
            mock_path_instance.exists.return_value = True
            result = parse_party_mode_response(SAMPLE_HAPPY_PATH)
        names = [m.character_name for m in result.members]
        assert "Aragorn" in names
        assert "Legolas" in names

    def test_member_urls(self):
        with patch("eldritch_dm.bot.party_mode_parser.Path") as mock_path_cls:
            mock_path_instance = mock_path_cls.return_value
            mock_path_instance.exists.return_value = True
            result = parse_party_mode_response(SAMPLE_HAPPY_PATH)
        urls = [m.url for m in result.members]
        assert "http://192.168.1.5:8080/play?token=abc123" in urls
        assert "http://192.168.1.5:8080/play?token=def456" in urls

    def test_already_running_false_for_happy_path(self):
        with patch("eldritch_dm.bot.party_mode_parser.Path") as mock_path_cls:
            mock_path_instance = mock_path_cls.return_value
            mock_path_instance.exists.return_value = False
            result = parse_party_mode_response(SAMPLE_HAPPY_PATH)
        assert result.already_running is False

    def test_qr_path_none_when_file_missing(self):
        """QR path exists in markdown but file not on disk → qr_path=None."""
        with patch("eldritch_dm.bot.party_mode_parser.Path") as mock_path_cls:
            mock_path_instance = mock_path_cls.return_value
            mock_path_instance.exists.return_value = False
            result = parse_party_mode_response(SAMPLE_HAPPY_PATH)
        for member in result.members:
            assert member.qr_path is None

    def test_qr_path_set_when_file_exists(self):
        """QR path in markdown AND file exists on disk → qr_path is a Path."""
        with patch("eldritch_dm.bot.party_mode_parser.Path") as mock_path_cls:
            mock_path_instance = mock_path_cls.return_value
            mock_path_instance.exists.return_value = True
            result = parse_party_mode_response(SAMPLE_HAPPY_PATH)
        for member in result.members:
            assert member.qr_path is not None


# ── Test 2: QR generation failed placeholder ────────────────────────────────────


class TestQrFailed:
    def test_qr_failed_sentinel_yields_qr_path_none(self):
        """(generation failed, use URL instead) → qr_path=None without file check."""
        result = parse_party_mode_response(SAMPLE_QR_FAILED)
        assert len(result.members) == 1
        assert result.members[0].qr_path is None

    def test_url_still_extracted_when_qr_failed(self):
        result = parse_party_mode_response(SAMPLE_QR_FAILED)
        assert result.members[0].url == "http://192.168.1.5:8080/play?token=ggg999"


# ── Test 3: already running ─────────────────────────────────────────────────────


class TestAlreadyRunning:
    def test_already_running_flag_set(self):
        result = parse_party_mode_response(SAMPLE_ALREADY_RUNNING)
        assert result.already_running is True

    def test_already_running_server_url_extracted(self):
        result = parse_party_mode_response(SAMPLE_ALREADY_RUNNING)
        assert result.server_url == "http://192.168.1.5:8080"

    def test_already_running_members_empty(self):
        result = parse_party_mode_response(SAMPLE_ALREADY_RUNNING)
        assert result.members == []


# ── Test 4: error cases ─────────────────────────────────────────────────────────


class TestErrorCases:
    def test_error_prefix_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_party_mode_response("Error: Party mode failed to start")

    def test_error_prefix_with_leading_whitespace(self):
        with pytest.raises(ValueError):
            parse_party_mode_response("  Error: Something went wrong\n\nmore text")

    def test_missing_server_line_raises_value_error(self):
        with pytest.raises(ValueError, match=r"missing \*\*Server:\*\* line"):
            parse_party_mode_response(SAMPLE_MISSING_SERVER)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_party_mode_response("")


# ── Test 5: PartyMember dataclass ───────────────────────────────────────────────


class TestPartyMember:
    def test_party_member_is_frozen(self):
        member = PartyMember(
            character_name="Bilbo",
            url="http://example.com/play?token=t1",
            qr_path=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            member.character_name = "Frodo"  # type: ignore[misc]

    def test_party_member_fields(self):
        p = Path("/tmp/qr.png")
        member = PartyMember(character_name="Frodo", url="http://example.com", qr_path=p)
        assert member.character_name == "Frodo"
        assert member.url == "http://example.com"
        assert member.qr_path == p


# ── Test 6: whitespace tolerance ────────────────────────────────────────────────


class TestWhitespaceTolerance:
    def test_extra_blank_lines_in_member_block(self):
        """Parser tolerates extra blank lines between fields."""
        markdown = textwrap.dedent("""\
            # Party Mode Active

            **Server:** http://192.168.1.5:8080

            ## Player Connections


            ### Thorin


            - **URL:** http://192.168.1.5:8080/play?token=ttt999
            - **QR Code:** (generation failed, use URL instead)

        """)
        result = parse_party_mode_response(markdown)
        assert len(result.members) == 1
        assert result.members[0].character_name == "Thorin"
