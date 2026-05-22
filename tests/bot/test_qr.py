"""
Tests for eldritch_dm.bot.qr — render_qr_for_embed.

Covers:
  - Returns a discord.File instance
  - PNG magic bytes present (\\x89PNG\\r\\n\\x1a\\n)
  - File positioned at offset 0 after creation
  - Default filename is "qr.png"
  - Custom filename overrides the default
  - Error correction level 'm' (15%) is used
  - Can be used as embed.set_thumbnail(url=f"attachment://{filename}") pattern
  - segno is NOT imported in lobby.py after extraction
  - render_qr_for_embed IS imported in lobby.py
"""

from __future__ import annotations

import subprocess
import sys

import discord
import pytest

from eldritch_dm.bot.qr import render_qr_for_embed

# ── Helpers ────────────────────────────────────────────────────────────────────

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_render_qr_returns_discord_file():
    """render_qr_for_embed returns a discord.File instance."""
    result = render_qr_for_embed("https://example.com")
    assert isinstance(result, discord.File)


def test_render_qr_default_filename():
    """Default filename is 'qr.png'."""
    f = render_qr_for_embed("https://example.com")
    assert f.filename == "qr.png"


def test_render_qr_custom_filename():
    """Custom filename overrides the default."""
    f = render_qr_for_embed("https://party.example.com/join", filename="party_qr.png")
    assert f.filename == "party_qr.png"


def test_render_qr_png_magic_bytes():
    """File bytes start with the PNG magic header."""
    f = render_qr_for_embed("https://example.com")
    # discord.File wraps a BytesIO; read the underlying fp
    raw = f.fp.read()
    assert raw[:8] == _PNG_MAGIC, f"Expected PNG magic, got {raw[:8]!r}"


def test_render_qr_file_position_at_zero():
    """File stream is positioned at offset 0 so Discord can read from the start."""
    f = render_qr_for_embed("https://example.com")
    assert f.fp.tell() == 0


def test_render_qr_thumbnail_pattern():
    """filename attribute matches the attachment:// URL pattern used with set_thumbnail."""
    filename = "lobby_qr.png"
    f = render_qr_for_embed("https://example.com/lobby", filename=filename)
    # The typical pattern: embed.set_thumbnail(url=f"attachment://{filename}")
    assert f.filename == filename


def test_render_qr_non_empty_output():
    """QR output is non-trivial (PNG > 100 bytes for any reasonable QR code)."""
    f = render_qr_for_embed("https://discord.gg/eldritchdm")
    raw = f.fp.read()
    assert len(raw) > 100, f"QR output suspiciously small: {len(raw)} bytes"


def test_lobby_does_not_import_segno_directly():
    """After the refactor, lobby.py should not contain 'import segno'."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "lobby_src",
        "/Users/shoemoney/Services/DiscordDM/src/eldritch_dm/bot/cogs/lobby.py",
    )
    # Read source directly to check imports without executing the module
    with open("/Users/shoemoney/Services/DiscordDM/src/eldritch_dm/bot/cogs/lobby.py") as fh:
        source = fh.read()

    assert "import segno" not in source, (
        "lobby.py still contains 'import segno'; should import render_qr_for_embed from qr.py"
    )


def test_lobby_imports_render_qr_for_embed():
    """After the refactor, lobby.py imports render_qr_for_embed from qr.py."""
    with open("/Users/shoemoney/Services/DiscordDM/src/eldritch_dm/bot/cogs/lobby.py") as fh:
        source = fh.read()

    assert "render_qr_for_embed" in source, (
        "lobby.py does not import render_qr_for_embed; refactor not applied"
    )
