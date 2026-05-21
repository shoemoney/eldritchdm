---
phase: "03"
plan: "01"
subsystem: "lobby-cog"
tags: [discord, lobby, mcp, ready-button, start-game, load-adventure, qr, segno]
dependency_graph:
  requires: ["02-03"]
  provides: ["lobby-cog", "ready-button-real", "mcp-phase3-wrappers", "party-mode-parser", "permissions-helper"]
  affects: ["03-02", "03-03"]
tech_stack:
  added: ["segno>=1.6,<2.0"]
  patterns:
    - "DynamicItem callback deps via interaction.client (not constructor injection)"
    - "TDD RED/GREEN per task with per-task commits"
    - "pv_repo alias on EldritchBot (avoids discord.Client.persistent_views property conflict)"
    - "TDD callback: cog.command.callback(cog, interaction, ...) to bypass app_commands decorator"
    - "AsyncMock(side_effect=coroutine_fn) for MCP call tracking in tests"
key_files:
  created:
    - src/eldritch_dm/bot/cogs/lobby.py
    - src/eldritch_dm/bot/party_mode_parser.py
    - src/eldritch_dm/bot/permissions.py
    - tests/bot/cogs/__init__.py
    - tests/bot/cogs/test_lobby.py
    - tests/bot/test_dynamic_items_real.py
    - uv.lock
  modified:
    - src/eldritch_dm/mcp/tools.py
    - src/eldritch_dm/bot/dynamic_items.py
    - src/eldritch_dm/bot/embeds.py
    - src/eldritch_dm/bot/bot.py
    - src/eldritch_dm/bot/cogs/__init__.py
    - src/eldritch_dm/persistence/persistent_views_repo.py
    - pyproject.toml
    - tests/bot/fixtures/embed_lobby.json
    - tests/bot/test_dynamic_items.py
decisions:
  - "bot.pv_repo instead of bot.persistent_views — discord.Client exposes persistent_views as a read-only property; overriding it raises AttributeError on EldritchBot"
  - "lobby.py calls bot.mcp.call() directly rather than via mcp_tools wrappers — avoids double-indirection in orchestration sequences; mcp_tools wrappers are for reusable single-shot calls"
  - "segno inline in lobby.py, Plan 03 extracts to bot/qr.py — avoids premature abstraction; function signature frozen in docstring"
  - "module_bound idempotency via JSON field in dm20_party_token — prevents duplicate Chapter 1 entities (Pitfall 7)"
  - "can_act_on_character(interaction, None) for /load_adventure — manage_channels-only gate per D-29; player_id=None means any player cannot bypass, only GMs"
metrics:
  duration_minutes: 120
  completed_date: "2026-05-21"
  tasks_completed: 4
  tasks_total: 4
  files_created: 7
  files_modified: 9
  tests_added: 32
  tests_total: 355
---

# Phase 3 Plan 01: Lobby Cog + ReadyButton Wiring + MCP Phase 3 Wrappers Summary

**One-liner:** LobbyCog with 3-MCP /start_game orchestration (rollback-ordered), /load_adventure with idempotency guard, ReadyButton real state machine with dedup and EXPLORATION transition, 6 new MCP wrappers, party_mode_parser and permissions helpers.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | MCP Phase 3 wrappers | a520ee9 | src/eldritch_dm/mcp/tools.py, tests/mcp/test_tools.py |
| 2 | party_mode_parser + permissions helpers | 650a41f | src/eldritch_dm/bot/party_mode_parser.py, src/eldritch_dm/bot/permissions.py, tests/ |
| 3 | Real ReadyButton callback + lobby_embed extended | a2ee2ba | src/eldritch_dm/bot/dynamic_items.py, embeds.py, bot.py, pv_repo, test_dynamic_items_real.py |
| 4 | LobbyCog + /start_game + /load_adventure + autocomplete | c970393 | src/eldritch_dm/bot/cogs/lobby.py, bot.py, pyproject.toml, tests/bot/cogs/ |

## What Was Built

### Task 1: MCP Phase 3 Wrappers

Six new async wrapper functions added to `src/eldritch_dm/mcp/tools.py`:

- `list_characters(client, *, campaign_name)` — roster for a campaign
- `get_class_info(client, *, class_name)` — D&D 5e class data from dm20
- `get_race_info(client, *, race_name)` — D&D 5e race data from dm20
- `player_action(client, *, session_id, action, context)` — signals party_ready and other player events
- `get_party_status(client, *, session_id)` — health/status of the party
- `load_adventure(client, *, module_id, populate_chapter_1, campaign_name)` — load adventure module

TOOL_TO_FUNCTION registry extended from 28 to 34 entries. 9 new tests; count assertion updated to 34.

### Task 2: Pure Helper Modules

**party_mode_parser.py:** Parses `dm20__start_party_mode` markdown response into structured `ParsePartyResult`. Handles error prefix, already-running detection, missing Server line, and QR sentinel `(generation failed, use URL instead)`. Pure module — no discord.ext imports.

**permissions.py:** `can_act_on_character(interaction, character_player_id) -> bool` per D-29. Returns True if user ID matches player_id, or if user has `manage_channels` guild permission (DM override). TYPE_CHECKING-only discord import.

### Task 3: Real ReadyButton Callback

Replaced Phase 2 stub in `dynamic_items.py` with full state machine:

1. Defer ephemeral (EDM001 — always first await)
2. Fetch channel_sessions via `bot.channel_sessions.get(str(channel_id))`
3. If no session: ephemeral "No active session"
4. Fetch party roster via `bot.mcp.call("dm20__list_characters", ...)`
5. Check user in roster (player_id match): reject non-roster users
6. Fetch persistent_views via `bot.pv_repo.get(custom_id)` → extract `ready_user_ids`
7. Add user ID (deduped), save updated view via `bot.pv_repo.insert(...)`
8. If all roster players ready: `channel_sessions.set_state(EXPLORATION)` + signal `dm20__player_action(party_ready)` + edit embed
9. Otherwise: ephemeral "Marked ready (N/M)"

`lobby_embed` extended with `server_url: str | None` and `transition_state: str | None` parameters (backward-compatible). Three stub buttons (TradeButton, LootButton, CombatButton) remain intentionally stubbed for later phases.

### Task 4: LobbyCog

Full Discord cog in `src/eldritch_dm/bot/cogs/lobby.py` (~350 lines):

- **ADVENTURE_IDS**: curated 9-entry catalog (CoS, LMoP, HotDQ, PotA, OotA, ToA, WDH, WDMM, BGDIA)
- **_render_qr(url)**: inline segno renderer — `error='m'`, scale=8, returns `discord.File`
- **/start_game**: defer-first; create_campaign → start_claudmaster_session → start_party_mode; rollback on step 3 failure calls end_claudmaster_session (best-effort); sends lobby embed with QR thumbnail + ReadyButton
- **/load_adventure**: permission-gated (manage_channels); idempotency via `module_bound` JSON field in `dm20_party_token`; `populate_chapter_1` flag avoids duplicate Chapter 1 entities on re-runs
- **adventure_id_autocomplete**: substring match case-insensitive, max 25 results
- **`async def setup(bot)`**: discord.py extension entry point

`bot.py` updated: `self.channel_sessions` and `self.pv_repo` aliases, `load_extension("eldritch_dm.bot.cogs.lobby")` in setup_hook.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] discord.Client.persistent_views property conflict**
- Found during: Task 3
- Issue: Setting `self.persistent_views` on EldritchBot raised `AttributeError: property 'persistent_views' of 'EldritchBot' object has no setter` — discord.Client exposes this as a read-only property
- Fix: Renamed bot attribute to `self.pv_repo` throughout (bot.py, ReadyButton callback, LobbyCog, all tests)
- Files modified: bot.py, dynamic_items.py, cogs/lobby.py, test_dynamic_items_real.py

**2. [Rule 1 - Bug] PersistentView model validation — message_id required**
- Found during: Task 3
- Issue: `PersistentView(message_id=None, ...)` failed Pydantic validation (message_id: str required)
- Fix: Provide `message_id=""` and `created_at=datetime.now(tz=UTC)` for newly-created views
- Files modified: dynamic_items.py

**3. [Rule 1 - Bug] app_commands.command wraps function — not directly callable**
- Found during: Task 4 (tests)
- Issue: `cog.start_game(interaction, ...)` fails because `@app_commands.command` wraps the method
- Fix: Use `cog.start_game.callback(cog, interaction, ...)` pattern (matches diagnostics cog pattern)
- Files modified: tests/bot/cogs/test_lobby.py

**4. [Rule 1 - Bug] AsyncMock vs coroutine for mcp.call tracking**
- Found during: Task 4 (tests)
- Issue: Using a plain coroutine for `bot.mcp.call` doesn't expose `call_args_list`
- Fix: `AsyncMock(side_effect=coroutine_fn)` provides both tracking and async dispatch
- Files modified: tests/bot/cogs/test_lobby.py

**5. [Rule 1 - Bug] Lobby embed snapshot regression**
- Found during: Task 3
- Issue: Phase 2 fixture `embed_lobby.json` lacked the description suffix added in Phase 3
- Fix: Updated fixture to include `"\n\nWaiting for players to ready up."`
- Files modified: tests/bot/fixtures/embed_lobby.json

**6. [Rule 1 - Bug] TestStubCallback included ReadyButton after real impl landed**
- Found during: Task 3 (tests)
- Issue: Stub test was parametrized over all 4 DynamicItem buttons; ReadyButton now has a real callback requiring bot subsystem attributes
- Fix: Removed ReadyButton from `_STUB_CLASSES` in test_dynamic_items.py; moved tests to test_dynamic_items_real.py
- Files modified: tests/bot/test_dynamic_items.py

## Known Stubs

| Stub | File | Line | Reason |
|------|------|------|--------|
| Phase 2 stub callback | src/eldritch_dm/bot/dynamic_items.py | 311, 373, 434 | TradeButton, LootButton, CombatButton — out of scope for Plan 01; wired in Phase 4 |

## Notes for Plan 03 Author

The QR rendering function `_render_qr(url, filename)` is currently inline in `src/eldritch_dm/bot/cogs/lobby.py`. Plan 03 should extract this to `src/eldritch_dm/bot/qr.py` as `render_qr_for_embed()`. The function signature, error correction level ('m'), scale (8), and border (2) are frozen — do not change without testing Discord embed thumbnail dimensions.

## Threat Flags

No new security-relevant surface introduced beyond what was modeled in the plan's threat model. `/start_game` and `/load_adventure` both defer-first (no auth exposure window). Campaign names are passed verbatim to dm20 and never echoed to LLM narration in this cog.

## Self-Check

Files exist:
- [x] src/eldritch_dm/bot/cogs/lobby.py
- [x] src/eldritch_dm/bot/party_mode_parser.py
- [x] src/eldritch_dm/bot/permissions.py
- [x] tests/bot/cogs/__init__.py
- [x] tests/bot/cogs/test_lobby.py
- [x] tests/bot/test_dynamic_items_real.py

Commits exist:
- [x] a520ee9 — Task 1 MCP wrappers
- [x] 650a41f — Task 2 helpers
- [x] a2ee2ba — Task 3 ReadyButton
- [x] c970393 — Task 4 LobbyCog

Test results: 355 passed, 4 skipped
Import-linter: 5 contracts kept, 0 broken
Ruff (plan files): 0 errors

## Self-Check: PASSED
