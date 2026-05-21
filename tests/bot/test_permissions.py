"""
Tests for eldritch_dm.bot.permissions.

Covers can_act_on_character(interaction, character_player_id) → bool:
  - Returns True when interaction.user.id matches character_player_id
  - Returns True when user has manage_channels permission (regardless of ownership)
  - Returns False when neither condition holds
  - Returns False when user has no guild_permissions (DM context)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from eldritch_dm.bot.permissions import can_act_on_character


def _make_interaction(user_id: int = 100, manage_channels: bool = False) -> discord.Interaction:
    """Build a minimal mock discord.Interaction for permission testing."""
    interaction = MagicMock(spec=discord.Interaction)
    user = MagicMock(spec=discord.Member)
    user.id = user_id

    perms = MagicMock(spec=discord.Permissions)
    perms.manage_channels = manage_channels
    user.guild_permissions = perms

    interaction.user = user
    return interaction


def _make_dm_interaction(user_id: int = 100) -> discord.Interaction:
    """Build a minimal mock discord.Interaction without guild_permissions (DM context)."""
    interaction = MagicMock(spec=discord.Interaction)
    user = MagicMock(spec=discord.User)  # discord.User has no guild_permissions
    user.id = user_id
    # Remove guild_permissions attribute so getattr fallback returns None
    del user.guild_permissions
    interaction.user = user
    return interaction


class TestCanActOnCharacter:
    def test_returns_true_when_user_id_matches_player_id(self):
        """Owner of the character can always act."""
        interaction = _make_interaction(user_id=123)
        assert can_act_on_character(interaction, character_player_id="123") is True

    def test_returns_true_when_user_has_manage_channels(self):
        """DM (manage_channels) can act regardless of ownership."""
        interaction = _make_interaction(user_id=999, manage_channels=True)
        # character belongs to someone else
        assert can_act_on_character(interaction, character_player_id="111") is True

    def test_returns_false_when_neither_owner_nor_dm(self):
        """Non-owner without manage_channels is denied."""
        interaction = _make_interaction(user_id=999, manage_channels=False)
        assert can_act_on_character(interaction, character_player_id="111") is False

    def test_returns_false_in_dm_context_no_guild_permissions(self):
        """User object without guild_permissions (DM channel) is denied."""
        interaction = _make_dm_interaction(user_id=123)
        # player_id doesn't match
        assert can_act_on_character(interaction, character_player_id="999") is False

    def test_returns_false_with_none_player_id_and_no_manage_channels(self):
        """None player_id falls through to manage_channels check; no perms = False."""
        interaction = _make_interaction(user_id=123, manage_channels=False)
        assert can_act_on_character(interaction, character_player_id=None) is False

    def test_returns_true_with_none_player_id_and_manage_channels(self):
        """None player_id + manage_channels = True (DM-only gate, per D-29)."""
        interaction = _make_interaction(user_id=123, manage_channels=True)
        assert can_act_on_character(interaction, character_player_id=None) is True

    def test_user_id_string_comparison_is_exact(self):
        """user.id is an int; player_id is a str — comparison must coerce int to str."""
        interaction = _make_interaction(user_id=456, manage_channels=False)
        assert can_act_on_character(interaction, character_player_id="456") is True
        assert can_act_on_character(interaction, character_player_id="4560") is False
