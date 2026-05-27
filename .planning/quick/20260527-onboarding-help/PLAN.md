---
id: 260527-onboarding-help
slug: onboarding-help
date: 2026-05-27
status: in-progress
---

# Quick Task — Bot Onboarding UX

## Problem
Bot lands in a Discord server silently. Players have no idea what slash commands exist or where to start.

## Deliverable
1. `/help` slash command — ephemeral embed grouping all 8 commands by phase (Setup, Session, Diagnostics).
2. `on_guild_join` listener — when the bot is added to a server, post a public welcome embed to the system channel (or first writable text channel) pointing at `/help`, `/start_game`, and `/upload_character_file`.

## Implementation
- New cog: `src/eldritch_dm/bot/cogs/onboarding.py`
- Register in `bot.py` cog-load block (after diagnostics).
- Reuse `EmbedColor.LOBBY` for visual consistency.
- Welcome embed must defer-tolerate `Forbidden` (no Send Messages perm) silently.

## Out of scope
- Per-channel auto-welcome
- Persistent help button
- Localization (English only)
