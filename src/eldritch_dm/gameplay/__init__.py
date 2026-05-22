"""
eldritch_dm.gameplay — game state orchestration layer.

This layer sits between the Discord bot layer (eldritch_dm.bot) and the MCP
tools layer (eldritch_dm.mcp). It owns:

  - PartyModeOrchestrator (party_mode.py) — per-channel asyncio.Task that
    drives the dm20 pop/thinking/resolve loop for EXPLORATION and COMBAT states.
  - ExplorationBatch + BatchCoordinator (exploration_batch.py) — 30s action
    batching for multi-player exploration (EXPLORE-06).
  - GameStateParser (game_state_parser.py) — regex parser for dm20's markdown
    get_game_state response (since dm20 returns formatted text, not JSON).

Import policy (enforced by import-linter):
  - gameplay MAY import: eldritch_dm.mcp, eldritch_dm.persistence,
                         eldritch_dm.safety, eldritch_dm.config,
                         eldritch_dm.logging
  - gameplay MUST NOT import: eldritch_dm.bot, eldritch_dm.ingest

Phase 4, Plan 01.
"""
