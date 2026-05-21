---
phase: 02-discord-scaffold-persistent-views
plan: 02
subsystem: bot
tags: [embeds, dynamic-items, persistent-buttons, warnings, discord-ui]
dependency_graph:
  requires:
    - "01-mcp-client-local-state (structlog, settings, persistence repos)"
  provides:
    - "lobby_embed / room_embed / combat_embed / character_confirm_embed"
    - "ReadyButton / DeclareActionButton / EndTurnButton / RiposteButton (DynamicItem subclasses)"
    - "WarningKind enum + send_warning helper"
    - "DYNAMIC_ITEM_CLASSES tuple for Plan 03 setup_hook"
  affects:
    - "Plan 03 (coalescer/rehydration): consumes DYNAMIC_ITEM_CLASSES via add_dynamic_items"
    - "Phase 3 (lobby cog): replaces ReadyButton stub callback"
    - "Phase 4 (combat cog): replaces DeclareActionButton + EndTurnButton stub callbacks"
    - "Phase 5 (riposte cog): replaces RiposteButton stub callback"
tech_stack:
  added: []
  patterns:
    - "discord.ui.DynamicItem[discord.ui.Button] with class-level template= regex"
    - "Pure-function embed renderers returning discord.Embed"
    - "Hand-rolled JSON fixture comparison via embed.to_dict() + _scrub_ts()"
    - "StrEnum for WarningKind with string.Formatter key introspection"
key_files:
  created:
    - src/eldritch_dm/bot/embeds.py
    - src/eldritch_dm/bot/dynamic_items.py
    - src/eldritch_dm/bot/warnings.py
    - tests/bot/test_embeds.py
    - tests/bot/test_dynamic_items.py
    - tests/bot/test_warnings.py
    - tests/bot/__init__.py
    - tests/bot/fixtures/embed_lobby.json
    - tests/bot/fixtures/embed_room.json
    - tests/bot/fixtures/embed_combat.json
    - tests/bot/fixtures/embed_character_confirm.json
  modified: []
decisions:
  - "Hand-rolled JSON fixture compare (embed.to_dict() + _scrub_ts) over syrupy — zero new deps"
  - "DynamicItem accessor is .item.custom_id, not .children[0].custom_id (discovered via runtime inspection)"
  - "bot.py stub created by this executor as Rule 3 auto-fix; Plan 01 executor overwrote with canonical impl"
  - "WarningKind uses StrEnum values for log-safe key strings"
  - "send_warning raises ValueError (not KeyError) with human-readable missing-key message"
metrics:
  duration_minutes: 28
  completed_at: "2026-05-21T22:04:22Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 11
  files_modified: 1
  tests_added: 67
  tests_total_after: 235
---

# Phase 02 Plan 02: Embed Renderers, DynamicItem Buttons, and Warning Helper Summary

**One-liner:** Pure-function embed renderers with JSON snapshot baselines, 4 regex-templated DynamicItem persistent buttons with defer-first stub callbacks, and a StrEnum-based ephemeral warning helper with key-introspecting validation.

## Tasks Completed

| # | Task | Commit | Tests Added |
|---|------|--------|-------------|
| 1 | Embed renderers with snapshot tests (RED) | 2fb38d1 | 13 |
| 1 | Embed renderers (GREEN + fixtures) | bd97bfe | — |
| 2 | DynamicItem subclasses (RED) | 657de92 | 36 |
| 2 | DynamicItem implementation (GREEN) | da38f4c | — |
| 3 | Warning helper (RED) | 99d3f34 | 18 |
| 3 | Warning helper (GREEN) | 2c66b2a | — |

**Total Plan 02 tests:** 67 (13 embed + 36 dynamic_items + 18 warnings)
**Full suite after:** 235 passing (168 Phase 1 + 13 embed + 36 dynamic_items + 18 warnings)

## Deliverables

### `src/eldritch_dm/bot/embeds.py`
- `EmbedColor(IntEnum)`: LOBBY=0x5865F2, EXPLORATION=0x57F287, COMBAT=0xED4245, CHARACTER_CONFIRM=0xFEE75C (D-15)
- `_FOOTER_TEXT = "🎲 ShoeGPT · EldritchDM"` (D-16) — footer + UTC timestamp on every embed
- `PlayerStatus(frozen dataclass)`: `display_name`, `ready`, `character_name`
- `lobby_embed(*, campaign_name, players, party_invite)` — LOBBY color, optional Join Party Mode field
- `room_embed(*, room_title, narration, party_hp)` — EXPLORATION color, narration truncated 4000 chars
- `combat_embed(*, round_n, current_actor, initiative)` — COMBAT color, per-actor initiative fields
- `character_confirm_embed(*, player_name, character)` — CHARACTER_CONFIRM color, T-02-08 safe field extraction (name/race/class/level/ability_scores/hp/ac only)

### `src/eldritch_dm/bot/dynamic_items.py`
- `ReadyButton`: `^ready:(?P<channel_id>\d+)$` — green button, Phase 3 handler
- `DeclareActionButton`: `^declare:(?P<channel_id>\d+)$` — blurple button, Phase 4 handler
- `EndTurnButton`: `^endturn:(?P<channel_id>\d+):(?P<actor_id>\d+)$` — gray button, Phase 4 handler
- `RiposteButton`: `^riposte:(?P<timer_id>\d+):(?P<user_id>\d+)$` — red button, Phase 5 handler
- All callbacks: defer first (D-09), structlog bind (D-38), ephemeral stub followup (D-23)
- All custom_ids fit in 100 chars for 19-digit snowflakes (verified by Test 6 boundary test)
- `DYNAMIC_ITEM_CLASSES` tuple for Plan 03 `add_dynamic_items(*DYNAMIC_ITEM_CLASSES)`

### `src/eldritch_dm/bot/warnings.py`
- `WarningKind(StrEnum)`: NOT_YOUR_TURN, RIPOSTE_EXPIRED, DM_OFFLINE, INVALID_ACTION, RATE_LIMITED
- `_COPY` dict: all 5 player-facing ephemeral message templates (D-33)
- `send_warning(interaction, kind, **ctx)`: formats via `string.Formatter`, raises `ValueError` naming missing keys, logs `warning_sent`, sends `ephemeral=True`

### Snapshot fixtures
- `tests/bot/fixtures/embed_lobby.json` — lobby_embed baseline (4 players, invite URL)
- `tests/bot/fixtures/embed_room.json` — room_embed baseline
- `tests/bot/fixtures/embed_combat.json` — combat_embed baseline (round 3, 5-actor initiative)
- `tests/bot/fixtures/embed_character_confirm.json` — character_confirm_embed baseline

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] bot.py stub created to unblock test imports**
- **Found during:** Task 1 (embed tests collection)
- **Issue:** `src/eldritch_dm/bot/__init__.py` (created by Plan 01 executor) imports `from eldritch_dm.bot.bot import EldritchBot`, which didn't exist yet. Tests couldn't collect.
- **Fix:** Created minimal `bot.py` stub with `class EldritchBot(commands.Bot)`. Plan 01 executor overwrote it with the canonical implementation during the same commit window.
- **Files modified:** `src/eldritch_dm/bot/bot.py` (stub; Plan 01 owns canonical)
- **Commits:** bd97bfe

**2. [Rule 1 - Bug] DynamicItem custom_id accessor corrected**
- **Found during:** Task 2 test run (GREEN phase)
- **Issue:** Tests used `.children[0].custom_id` (guessed from View pattern). DynamicItem exposes the wrapped button via `.item.custom_id`, not `.children`.
- **Fix:** Updated all `.children[0].custom_id` references to `.item.custom_id` in test file.
- **Files modified:** `tests/bot/test_dynamic_items.py`
- **Commits:** da38f4c

**3. [Discretion] Hand-rolled JSON fixture comparison over syrupy**
- **Rationale:** Per 02-RESEARCH.md Claude's Discretion section and note that syrupy is not installed. Hand-rolled `_scrub_ts(embed.to_dict())` + JSON fixture files achieve the same snapshot pinning with zero new deps.
- **Files modified:** `tests/bot/test_embeds.py`

**4. [Discretion] tests/bot/__init__.py created as empty shim**
- **Rationale:** The other executor (Plan 01) owns this file per the executor brief, but it was missing and needed for test collection. Created as empty file; last-writer wins if Plan 01 also creates it.

## Plan 03 Notes (for handoff)

- **`DYNAMIC_ITEM_CLASSES` stub callbacks:** `ReadyButton`, `DeclareActionButton`, `EndTurnButton`, `RiposteButton` all return ephemeral "Phase 2 stub — {ClassName} will be wired up in a later phase." Replace in Phases 3-5.
- **Registration:** Plan 03 `setup_hook` calls `bot.add_dynamic_items(*DYNAMIC_ITEM_CLASSES)`. Do NOT also call `bot.add_view(view, message_id=...)` — `add_dynamic_items` alone is sufficient (see dynamic_items.py module docstring and 02-RESEARCH.md Pitfall 1).
- **Embed snapshot updates:** Changing any renderer output requires `pytest --snapshot-update` to regenerate fixtures in `tests/bot/fixtures/`.
- **EDM001 lint scope:** The stub callbacks in `dynamic_items.py` already follow D-09 (defer first). The EDM001 AST hook (Plan 03) will validate this at CI time.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `ReadyButton.callback` | `src/eldritch_dm/bot/dynamic_items.py` | Phase 3 handler (lobby ready-up) |
| `DeclareActionButton.callback` | `src/eldritch_dm/bot/dynamic_items.py` | Phase 4 handler (exploration intent) |
| `EndTurnButton.callback` | `src/eldritch_dm/bot/dynamic_items.py` | Phase 4 handler (turn yield + actor gate) |
| `RiposteButton.callback` | `src/eldritch_dm/bot/dynamic_items.py` | Phase 5 handler (timed riposte) |

These stubs are intentional per D-23. Each replies "Phase 2 stub — {ClassName} will be wired up in a later phase." They do defer first and log dispatch, so they are fully observable. The future phases replace the callback body only.

## Threat Surface Scan

No new threat surface introduced beyond what is documented in the plan's threat model:
- T-02-07 (custom_id regex anchoring): fullmatch anchors `^...$` present; `int()` cast rejects non-digits
- T-02-08 (character_confirm field extraction): only 7 enumerated fields extracted, never full dict
- T-02-10 (custom_id length): 19-digit snowflake boundary test pins this
- T-02-11 (warning ephemeral): all `send_warning` calls use `ephemeral=True`

## Self-Check: PASSED

Files exist:
- src/eldritch_dm/bot/embeds.py: FOUND
- src/eldritch_dm/bot/dynamic_items.py: FOUND
- src/eldritch_dm/bot/warnings.py: FOUND
- tests/bot/test_embeds.py: FOUND
- tests/bot/test_dynamic_items.py: FOUND
- tests/bot/test_warnings.py: FOUND
- tests/bot/fixtures/embed_lobby.json: FOUND
- tests/bot/fixtures/embed_room.json: FOUND
- tests/bot/fixtures/embed_combat.json: FOUND
- tests/bot/fixtures/embed_character_confirm.json: FOUND

Commits verified:
- 2fb38d1 (test RED embeds): FOUND
- bd97bfe (feat GREEN embeds): FOUND
- 657de92 (test RED dynamic_items): FOUND
- da38f4c (feat GREEN dynamic_items): FOUND
- 99d3f34 (test RED warnings): FOUND
- 2c66b2a (feat GREEN warnings): FOUND
