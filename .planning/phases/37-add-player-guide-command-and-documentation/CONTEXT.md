# Phase 37: Add Player Guide command and documentation

## Goal
Create a comprehensive, emoji-rich player guide document with graphs, and add a `/guide` slash command to help new players get oriented.

## Context
The user requested continuous improvements, emphasizing professional tone, liberal use of emojis, and graphs in the documentation. 
Since we just improved the UX of modals and embeds, the natural next step is to provide a dedicated guide for players so they understand the bot's workflow (Lobby -> Ingest -> Play -> Combat).

## Requirements
- Create `docs/PLAYER_GUIDE.md` containing mermaid diagrams and emojis explaining the D&D flow.
- Add `/guide` or `/help` command in `src/eldritch_dm/bot/cogs/lobby.py` (or similar) that gives players a quick-start embed.
- Update `README.md` to link to the new player guide.
