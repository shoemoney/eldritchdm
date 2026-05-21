"""
eldritch_dm.bot — Discord bot integration layer for EldritchDM.

This subpackage is the integration layer: it imports from mcp/, persistence/,
safety/, config, and logging. NOTHING outside bot/ may import from bot/ —
enforced by import-linter (see pyproject.toml).
"""

from __future__ import annotations

from eldritch_dm.bot.bot import EldritchBot

__all__ = ["EldritchBot"]
