---
phase: 03-lobby-character-ingest
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eldritch_dm/mcp/tools.py
  - src/eldritch_dm/bot/cogs/__init__.py
  - src/eldritch_dm/bot/cogs/lobby.py
  - src/eldritch_dm/bot/dynamic_items.py
  - src/eldritch_dm/bot/embeds.py
  - src/eldritch_dm/bot/bot.py
  - src/eldritch_dm/bot/permissions.py
  - src/eldritch_dm/bot/party_mode_parser.py
  - tests/mcp/test_tools.py
  - tests/bot/cogs/__init__.py
  - tests/bot/cogs/test_lobby.py
  - tests/bot/test_party_mode_parser.py
  - tests/bot/test_permissions.py
  - tests/bot/test_dynamic_items.py
  - tests/bot/test_embeds.py
autonomous: true
requirements:
  - LOBBY-01
  - LOBBY-02
  - LOBBY-03
  - LOBBY-04
tags:
  - discord
  - dm20
  - lobby
  - mcp
  - persistent-views

must_haves:
  truths:
    - "Running /start_game in a Discord channel creates a dm20 campaign, Claudmaster session, and Party Mode server, records the trio in channel_sessions, and posts a lobby embed with a QR-coded invite and a Discord-native Ready button"
    - "Running /load_adventure CoS (or other curated ID) binds an official 5e adventure to the active campaign and never duplicates Chapter 1 entities on re-runs"
    - "Adventure ID autocomplete returns up to 25 curated matches client-side without hitting dm20 (instant; no MCP cost per keystroke)"
    - "On Ready button click, only players whose Discord user_id matches a character.player_id in this campaign are counted; clicks by non-roster users are rejected with an ephemeral warning"
    - "Ready state survives a bot restart because it lives in persistent_views.payload_json; rehydration re-attaches the same button and reads the same row"
    - "When the last roster member readies up, channel_sessions.state transitions LOBBY → EXPLORATION, the lobby embed updates, and Claudmaster is signalled via dm20__player_action(action='party_ready', context='lobby_complete')"
    - "If start_party_mode fails after start_claudmaster_session succeeded, end_claudmaster_session is invoked and no channel_sessions row is left behind (rollback ordering preserved)"
    - "Permission helper allows the invoking player OR a user with manage_channels permission on the channel; everyone else gets an ephemeral denial"
  artifacts:
    - path: "src/eldritch_dm/bot/cogs/lobby.py"
      provides: "LobbyCog with /start_game, /load_adventure (+ autocomplete), ready_callback helper"
      min_lines: 250
    - path: "src/eldritch_dm/bot/party_mode_parser.py"
      provides: "parse_party_mode_response(markdown) -> (server_url, list[PartyMember]) per RESEARCH §1"
      min_lines: 60
    - path: "src/eldritch_dm/bot/permissions.py"
      provides: "can_act_on_character(interaction, character_player_id) -> bool per CONTEXT D-29"
      min_lines: 20
    - path: "src/eldritch_dm/bot/dynamic_items.py"
      provides: "ReadyButton.callback (real, replaces Phase 2 stub) and read/write ready state from persistent_views.payload_json"
    - path: "src/eldritch_dm/mcp/tools.py"
      provides: "list_characters, get_class_info, get_race_info, player_action, get_party_status wrappers"
      contains: "TOOL_TO_FUNCTION mapping for dm20__list_characters, dm20__get_class_info, dm20__get_race_info, dm20__player_action, dm20__get_party_status"
  key_links:
    - from: "src/eldritch_dm/bot/cogs/lobby.py"
      to: "src/eldritch_dm/mcp/tools.py"
      via: "imports and awaits create_campaign / start_claudmaster_session / start_party_mode / load_adventure / list_characters / player_action"
      pattern: "from eldritch_dm.mcp import tools|mcp_tools\\."
    - from: "src/eldritch_dm/bot/cogs/lobby.py"
      to: "src/eldritch_dm/bot/party_mode_parser.py"
      via: "parse_party_mode_response on start_party_mode markdown return"
      pattern: "parse_party_mode_response\\("
    - from: "src/eldritch_dm/bot/dynamic_items.py:ReadyButton.callback"
      to: "src/eldritch_dm/persistence/persistent_views_repo.py"
      via: "read/write per-player ready dict via upsert/insert + get on custom_id=f'ready:{channel_id}'"
      pattern: "PersistentViewRepo|persistent_views_repo"
    - from: "src/eldritch_dm/bot/dynamic_items.py:ReadyButton.callback"
      to: "src/eldritch_dm/persistence/channel_sessions_repo.py"
      via: "set_state(channel_id, ChannelState.EXPLORATION) on all-ready transition"
      pattern: "set_state\\(.*EXPLORATION"
    - from: "src/eldritch_dm/bot/bot.py:setup_hook"
      to: "src/eldritch_dm/bot/cogs/lobby.py:LobbyCog"
      via: "_load_cogs appends LobbyCog after diagnostics cog"
      pattern: "LobbyCog|cogs\\.lobby"
---

<objective>
Phase 3 Plan 01 — Lobby cog, EXPLORATION transition, ReadyButton wiring, missing MCP wrappers.

Purpose: Ship the user-visible lobby flow. `/start_game` orchestrates the dm20 campaign + Claudmaster session + Party Mode trio with proper rollback. `/load_adventure` exposes the 9 official adventures via curated autocomplete. The Ready button — stubbed in Phase 2 — becomes the real all-ready gate that transitions the session to EXPLORATION. This plan delivers requirements LOBBY-01..04 with no character-ingest concerns (Plans 02 and 03 handle that).

Output: New `LobbyCog`, two pure-helper modules (`party_mode_parser`, `permissions`), real `ReadyButton.callback`, five new typed MCP wrappers (`list_characters`, `get_class_info`, `get_race_info`, `player_action`, `get_party_status`), and ~13-15 new tests proving the state machine works including rollback on partial MCP failure.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md
@.planning/phases/03-lobby-character-ingest/03-CONTEXT.md
@.planning/phases/03-lobby-character-ingest/03-RESEARCH.md
@.planning/phases/02-discord-scaffold-persistent-views/02-01-SUMMARY.md
@.planning/phases/02-discord-scaffold-persistent-views/02-02-SUMMARY.md

@src/eldritch_dm/mcp/tools.py
@src/eldritch_dm/mcp/client.py
@src/eldritch_dm/bot/bot.py
@src/eldritch_dm/bot/embeds.py
@src/eldritch_dm/bot/dynamic_items.py
@src/eldritch_dm/bot/warnings.py
@src/eldritch_dm/bot/cogs/diagnostics.py
@src/eldritch_dm/persistence/channel_sessions_repo.py
@src/eldritch_dm/persistence/persistent_views_repo.py
@src/eldritch_dm/persistence/models.py
@src/eldritch_dm/safety/sanitizer.py
@ddmcpskills.md

<interfaces>
<!-- Contracts already in the tree this cog consumes. Executor: do not re-explore. -->

From src/eldritch_dm/mcp/tools.py (Phase 1 — confirmed wrappers exist):

```python
async def create_campaign(client, *, name, description="", dm_name=None, setting=None,
                         rules_version="2024", interaction_mode="classic") -> dict[str, Any]
async def start_claudmaster_session(client, *, campaign_name) -> dict[str, Any]
async def end_claudmaster_session(client, *, session_id) -> dict[str, Any]
async def start_party_mode(client, *, campaign_name, port=None) -> dict[str, Any]
async def stop_party_mode(client, *, campaign_name) -> dict[str, Any]
async def import_from_dndbeyond(client, *, url_or_id, player_name=None) -> dict[str, Any]
TOOL_TO_FUNCTION: dict[str, Callable[..., Awaitable[dict[str, Any]]]]   # registry
```

Wrappers we MUST add in this plan (do not exist yet — grep -n confirms):
- `list_characters(client, *, campaign_name) -> dict[str, Any]` → `dm20__list_characters`
- `get_class_info(client, *, class_name) -> dict[str, Any]` → `dm20__get_class_info`
- `get_race_info(client, *, race) -> dict[str, Any]` → `dm20__get_race_info`
- `player_action(client, *, session_id, action, context="") -> dict[str, Any]` → `dm20__player_action`
- `get_party_status(client, *, campaign_name) -> dict[str, Any]` → `dm20__get_party_status`

Also add a wrapper for `dm20__load_adventure` if missing (per ddmcpskills.md it takes `module_id`, `populate_chapter_1: bool = True`, `campaign_name: str | None = None`):
- `load_adventure(client, *, module_id, populate_chapter_1=True, campaign_name=None) -> dict[str, Any]`

From src/eldritch_dm/persistence/models.py:
```python
class ChannelState(StrEnum):
    LOBBY = "LOBBY"
    EXPLORATION = "EXPLORATION"
    # ...
class ChannelSession(BaseModel):
    channel_id: str
    campaign_name: str
    claudmaster_session_id: str | None
    dm20_party_token: str | None   # TEXT — we'll store JSON in here
    state: ChannelState
class PersistentView(BaseModel):
    custom_id: str
    view_class: str
    message_id: str | None
    channel_id: str
    payload: dict       # serialized as payload_json TEXT in the DB
```

From src/eldritch_dm/persistence/persistent_views_repo.py:
```python
class PersistentViewRepo:
    async def insert(self, view: PersistentView) -> PersistentView
    async def get(self, custom_id: str) -> PersistentView | None
    # (upsert via insert with replace=True OR delete+insert; verify exact method name in file at read time)
```
**ACTION**: read `persistent_views_repo.py` once at the top of Task 2. If no `upsert` method exists, add one (insert ON CONFLICT DO UPDATE SET payload_json=excluded.payload_json). The cog needs an upsert.

From src/eldritch_dm/persistence/channel_sessions_repo.py:
```python
class ChannelSessionRepo:
    async def upsert(self, *, channel_id, campaign_name, claudmaster_session_id=None,
                     dm20_party_token=None, state=ChannelState.LOBBY) -> ChannelSession
    async def set_state(self, channel_id: str, state: ChannelState) -> ChannelSession
    async def get(self, channel_id: str) -> ChannelSession | None
    async def delete(self, channel_id: str) -> None
```

From src/eldritch_dm/bot/embeds.py:
```python
@dataclass(frozen=True)
class PlayerStatus:
    display_name: str
    ready: bool
    character_name: str | None = None

def lobby_embed(*, campaign_name, players, party_invite=None) -> discord.Embed
```
**Note**: `lobby_embed` currently takes a single `party_invite` string. This plan extends it to also accept an optional `server_url: str | None = None` parameter so the embed can show both the server base AND a description of the per-character QR situation. Keep backward compat with the existing signature.

From src/eldritch_dm/bot/dynamic_items.py:
```python
class ReadyButton(discord.ui.DynamicItem[discord.ui.Button], template=r"^ready:(?P<channel_id>\d+)$"):
    template = re.compile(r"^ready:(?P<channel_id>\d+)$")
    def __init__(self, channel_id: int) -> None: ...
    @classmethod
    async def from_custom_id(cls, interaction, item, match, /) -> "ReadyButton": ...
    async def callback(self, interaction): ...   # ⏳ Phase 2 STUB — replace in Task 3
```

From src/eldritch_dm/bot/bot.py:
- `EldritchBot.setup_hook` calls a `_load_cogs` helper after diagnostics; Task 4 appends `await self.add_cog(LobbyCog(self, mcp=…, persistence=…, settings=…, logger=…))` here.
- The bot holds references to: `self.mcp` (MCPClient), `self.channel_sessions` (ChannelSessionRepo), `self.persistent_views` (PersistentViewRepo), `self.settings` (Settings).
- **ACTION**: read `bot.py` once at the top of Task 4 to confirm attribute names; if the bot does NOT yet expose `channel_sessions` / `persistent_views` as attributes, wire them through (and update Phase 2 SUMMARY accordingly — but DO NOT regress Phase 2 tests).

From ddmcpskills.md — verified dm20 tool shapes (HIGH-confidence per RESEARCH):
- `dm20__start_party_mode(campaign_name, port?)` returns markdown string. Parser in `party_mode_parser.py` extracts `**Server:**` line + per-`### Name` block with `**URL:**` + `**QR Code:**`. The "already running" case starts with the string `"Party Mode is already running"` and contains a `**Server:**` line but NO per-character QR file paths.
- `dm20__start_claudmaster_session(campaign_name)` returns a dict containing `session_id` at the top level (NOT inside `result` — per dm20-protocol source 873).
- `dm20__load_adventure(module_id, populate_chapter_1=True, campaign_name=None)` returns markdown.
- `dm20__list_characters(campaign_name)` returns dict with `characters: list[{character_id, name, player_id, player_name, class_level: int, race, character_class}]` (verify on first call; defensive `.get()` access in the cog).

Permission contract (D-29 + RESEARCH §12):
```python
def can_act_on_character(interaction: discord.Interaction, character_player_id: str | None) -> bool:
    if character_player_id and str(interaction.user.id) == character_player_id:
        return True
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.manage_channels)
```
This signature is shared by Plan 03 — keep it stable.
</interfaces>

<conventions>
- **D-09 defer-first rule** (BOT-02 lint): every interaction handler's first `await` is `interaction.response.defer(thinking=True)` (or `ephemeral=True` for ephemeral flows). The Phase 2 ruff plugin EDM001 will fail CI otherwise.
- **Cog construction** (D-03): `LobbyCog(bot, *, mcp: MCPClient, channel_sessions: ChannelSessionRepo, persistent_views: PersistentViewRepo, settings: Settings, logger: structlog.BoundLogger)`. Mirror the diagnostics cog's signature style.
- **Structlog binding** (D-37): bind `channel_id`, `campaign_name`, `tool_name` on every MCP call within the cog; bind `user_id` on button callbacks.
- **Atomic commits**: one commit per task. Format: `feat(03-lobby-character-ingest): <what>` for code, `test(03-lobby-character-ingest): <what>` for tests, `refactor(03-lobby-character-ingest): <what>` for the embed/ReadyButton refactor.
- **No fenced code blocks inside `<action>`**: directive prose only. Implementation details are in this `<interfaces>` block and in the referenced source files.
</conventions>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add missing MCP tool wrappers (list_characters, get_class_info, get_race_info, player_action, get_party_status, load_adventure)</name>
  <files>src/eldritch_dm/mcp/tools.py, tests/mcp/test_tools.py</files>
  <behavior>
    - Test: each new wrapper is awaitable, accepts keyword-only args matching the dm20 schema in ddmcpskills.md, and forwards the correct dm20 tool name to MCPClient.call.
    - Test: TOOL_TO_FUNCTION dict includes all five new tool names AND `dm20__load_adventure`.
    - Test: `list_characters(client, campaign_name="X")` calls `client.call("dm20__list_characters", campaign_name="X")`.
    - Test: `player_action(client, session_id="s1", action="party_ready", context="lobby_complete")` forwards all three kwargs verbatim.
    - Test: `load_adventure(client, module_id="CoS", populate_chapter_1=False, campaign_name=None)` omits the `campaign_name` kwarg when None (mirrors `start_party_mode` pattern with port).
    - Test: `get_party_status(client, campaign_name="X")` calls `client.call("dm20__get_party_status", campaign_name="X")`.
  </behavior>
  <action>
    Implement the six wrappers per the contract in the &lt;interfaces&gt; block (list_characters, get_class_info, get_race_info, player_action, get_party_status, load_adventure). Follow the existing style in tools.py — async, keyword-only args, return `dict[str, Any]`, dispatch via `client.call("dm20__<name>", ...)`. For `load_adventure`, conditional-kwarg pattern matching `start_party_mode`'s port: only include `campaign_name` if not None. Append each wrapper to `TOOL_TO_FUNCTION` at the bottom of the file.

    For tests in `tests/mcp/test_tools.py`: append a class `TestPhase3Wrappers` with one `async def test_<name>` per wrapper using the existing pattern (`AsyncMock` MCPClient, assert called_with). Update the existing `test_tool_to_function_registry_drift` (if present) by extending its expected count, or rely on the existing drift check to accept the additions.

    Implements LOBBY-01, LOBBY-02, LOBBY-04 (the typed-wrapper foundation those commands consume).
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/mcp/test_tools.py -x -q 2&gt;&amp;1 | tail -20</automated>
  </verify>
  <done>Six new wrappers exist in tools.py, six new entries in TOOL_TO_FUNCTION, ≥6 new tests in tests/mcp/test_tools.py all pass, existing 235+ Phase 1+2 tests still green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Pure helpers — party_mode_parser + permissions (no Discord runtime deps)</name>
  <files>src/eldritch_dm/bot/party_mode_parser.py, src/eldritch_dm/bot/permissions.py, tests/bot/test_party_mode_parser.py, tests/bot/test_permissions.py</files>
  <behavior>
    party_mode_parser tests:
    - Parses a canonical dm20 start_party_mode markdown (per RESEARCH §1 sample): extracts server_url and one PartyMember per `### Name` block with URL + QR path.
    - Handles `(generation failed, use URL instead)` QR placeholders — sets `qr_path=None`.
    - Handles missing QR-file-on-disk gracefully — qr_path stays None.
    - Handles "Party Mode is already running at http://..." response: server_url extracted, members list empty, dedicated `already_running` flag returned (or surface via raised AlreadyRunning subclass — pick one and document).
    - Raises `ValueError("Party Mode response missing **Server:** line")` on malformed input.
    - Raises ValueError if response begins with "Error:".

    permissions tests:
    - `can_act_on_character(interaction, character_player_id="123")` returns True when `interaction.user.id == 123`.
    - Returns True when `interaction.user.guild_permissions.manage_channels` is True regardless of ownership.
    - Returns False when neither match.
    - Returns False when `interaction.user` has no `guild_permissions` attribute (DM context).
  </behavior>
  <action>
    Create `src/eldritch_dm/bot/party_mode_parser.py` implementing `PartyMember` frozen dataclass and `parse_party_mode_response(markdown: str) -> ParsePartyResult` where `ParsePartyResult` is a small NamedTuple/dataclass with `server_url: str`, `members: list[PartyMember]`, `already_running: bool`. Use the exact regex patterns from RESEARCH §1 (`_HEADER_RE`, `_URL_RE`, `_QR_RE`, `_SERVER_RE`, `_QR_FAIL` sentinel). Detect "already running" by string match on the first non-empty line — when detected, parse only `**Server:**` and set `already_running=True`, leaving `members=[]`.

    Create `src/eldritch_dm/bot/permissions.py` with `can_act_on_character(interaction, character_player_id)` per the &lt;interfaces&gt; block — exactly the body shown there, plus a docstring referencing CONTEXT D-29 and RESEARCH §12.

    Both modules are PURE (no async, no Discord runtime calls — `permissions.py` accepts a Discord interaction object but only reads attributes). Both must be importable in tests without a running bot.

    Implements LOBBY-01 (parser), LOBBY-04 + INGEST-10 (permission helper shared with Plan 03).
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/bot/test_party_mode_parser.py tests/bot/test_permissions.py -x -q 2&gt;&amp;1 | tail -20</automated>
  </verify>
  <done>Both helpers exist with full docstrings citing CONTEXT/RESEARCH; ≥10 parser tests + ≥4 permission tests pass; both modules grep-clean of any `import discord.ext` (parser is pure-Python; permissions imports `discord` only for type hints).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Replace Phase 2 ReadyButton stub with real callback (state machine + persistent_views.payload_json + EXPLORATION transition)</name>
  <files>src/eldritch_dm/bot/dynamic_items.py, src/eldritch_dm/bot/embeds.py, tests/bot/test_dynamic_items.py, tests/bot/test_embeds.py</files>
  <behavior>
    ReadyButton.callback tests (use AsyncMock for Interaction, MCPClient, PersistentViewRepo, ChannelSessionRepo):
    - First await is `interaction.response.defer(thinking=True, ephemeral=True)` (defer-first rule).
    - Looks up ChannelSession via `channel_sessions_repo.get(str(channel_id))`; if missing, replies ephemeral "No active session" and returns without writing state.
    - Calls `mcp_tools.list_characters(mcp, campaign_name=session.campaign_name)` to fetch the roster.
    - If `interaction.user.id` is not in the roster `player_id` set, replies ephemeral "Only seated players can ready up" (citation: D-13 — player_id mapping is the gate) and returns.
    - Loads the per-channel ready dict via `persistent_views_repo.get(custom_id=f"ready:{channel_id}")`. If missing, treats it as `payload={"ready_user_ids": []}`.
    - Adds `str(interaction.user.id)` to the ready_user_ids set (deduped) and upserts the row (D-12 — survives restart).
    - If `set(ready_user_ids) >= set(player_ids)`: transition. Otherwise: ephemeral "✅ Marked ready ({n}/{total})" and return.
    - On transition: `channel_sessions_repo.set_state(str(channel_id), ChannelState.EXPLORATION)`, then `mcp_tools.player_action(mcp, session_id=session.claudmaster_session_id, action="party_ready", context="lobby_complete")`, then edit the original lobby message embed via `interaction.message.edit(embed=...)` to mark "✅ All ready — entering EXPLORATION…" (use `lobby_embed` with updated `PlayerStatus` rows).
    - All side effects survive a restart because `persistent_views.payload_json` is the source of truth.

    embeds tests:
    - Extend `lobby_embed` to accept an optional `server_url: str | None = None` parameter rendered as a "Party Mode server" field; ensure existing callers (lobby_embed signature back-compat) still work — keyword-only new param.
    - Add a `description` formatter helper that, given a `transition_state: "lobby" | "transitioning" | "exploration"`, renders the description suffix ("Waiting for ready", "✅ All ready — entering EXPLORATION…", "🟢 EXPLORATION").
  </behavior>
  <action>
    Replace `ReadyButton.callback` body with the real logic. Add constructor-injected dependencies via a module-level dependency-resolution hook: `ReadyButton.callback` cannot accept extra kwargs (Discord routes the call), so the cog stores references on the bot object (`bot.mcp`, `bot.channel_sessions`, `bot.persistent_views`) and `callback` reads `interaction.client` (the bot) to resolve them. Verify by reading `bot.py` once — if those attributes are not yet present, add them in Task 4 (file is owned by Task 4); for Task 3, the callback uses `interaction.client.mcp` / `.channel_sessions` / `.persistent_views` and tests inject a mock client with those attributes.

    Implement the state machine per the behavior block above. Bind structlog logger with `channel_id, custom_id, view_class=type(self).__name__, user_id` (already done in Phase 2 stub — preserve and extend with `campaign_name` after session lookup).

    For embeds: add the optional `server_url` kwarg and the description-suffix helper to `lobby_embed`. Update `tests/bot/test_embeds.py` with two new tests covering the new field and the transitioning-state copy. Do NOT regress existing Phase 2 snapshot tests — add a new snapshot rather than mutating in place.

    For dynamic_items tests: add a `TestReadyButtonReal` class with mocks for the bot client object. Cover: defer-first, no-session, non-roster user, partial ready (3/5), all-ready transition with player_action call, persistent_views payload upsert call args.

    Implements LOBBY-03 (embed), LOBBY-04 (ready/transition).
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/bot/test_dynamic_items.py tests/bot/test_embeds.py -x -q 2&gt;&amp;1 | tail -25</automated>
  </verify>
  <done>ReadyButton.callback is no longer a stub (grep -c 'phase2_stub' src/eldritch_dm/bot/dynamic_items.py returns 3, not 4 — the ReadyButton stub log line is removed; the other three DynamicItems still log it); lobby_embed accepts server_url; ≥6 new ReadyButton tests + ≥2 new embed tests pass; Phase 2 snapshot tests stay green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: LobbyCog with /start_game + /load_adventure + autocomplete + rollback ordering</name>
  <files>src/eldritch_dm/bot/cogs/lobby.py, src/eldritch_dm/bot/cogs/__init__.py, src/eldritch_dm/bot/bot.py, tests/bot/cogs/__init__.py, tests/bot/cogs/test_lobby.py</files>
  <behavior>
    /start_game tests:
    - Defer is the first await (BOT-02 lint).
    - Happy path: calls create_campaign → start_claudmaster_session → start_party_mode in order, parses the markdown via party_mode_parser, upserts channel_sessions with `dm20_party_token=json.dumps({"server_url": ..., "members": [...]})`, posts a lobby embed with a segno-rendered QR for the server URL attached as discord.File, and adds a ReadyButton view.
    - Rollback on start_party_mode failure: end_claudmaster_session IS called with the session_id from step 2; channel_sessions IS NOT inserted.
    - Rollback on start_claudmaster_session failure: no end_claudmaster_session attempted (it never started), channel_sessions IS NOT inserted, the dm20 campaign is left in place (we never delete campaigns — they're cheap; document this in the cog docstring).
    - Already-running party mode (parser sets `already_running=True`): the cog reuses the existing server, calls get_party_status to recover member data, and proceeds as happy path.
    - Permission check: `/start_game` is open to anyone with `manage_channels` OR the first user in the channel (de-facto DM). Implemented via `can_act_on_character` called with `character_player_id=None` (falls through to manage_channels-only path).

    /load_adventure tests:
    - Defer is the first await.
    - Calls `dm20__load_adventure(module_id=adventure_id, populate_chapter_1=True, campaign_name=session.campaign_name)`.
    - **load_adventure non-idempotency mitigation (RESEARCH §3, Pitfall 7)**: before calling load_adventure, the cog reads `channel_sessions.dm20_party_token` JSON; if it has a `module_bound` key set to a non-empty string, the cog sets `populate_chapter_1=False` (re-binds module without duplicating Chapter 1 entities). After a successful call, the cog upserts channel_sessions with `dm20_party_token` patched to include `module_bound: adventure_id`.
    - No active campaign in channel → ephemeral "No active campaign — run /start_game first" + early return.
    - Permission check: only `manage_channels` users can load adventures (a player can't change the module mid-campaign).

    autocomplete tests:
    - Static ADVENTURE_IDS dict has exactly 9 entries (CoS, LMoP, HotDQ, PotA, OotA, ToA, WDH, WDMM, BGDIA).
    - Autocomplete returns ≤25 Choices, matching on substring of either ID or title (case-insensitive).
    - Empty `current` returns all 9.
    - Returns a list of `app_commands.Choice[str]` (assert via type check on first element).

    LobbyCog construction tests:
    - Constructor takes `(bot, *, mcp, channel_sessions, persistent_views, settings, logger)`.
    - Logger is bound with `cog="lobby"`.

    bot.py integration test:
    - `EldritchBot.setup_hook._load_cogs` includes a `LobbyCog` registration AFTER the diagnostics cog.
    - Bot exposes `self.mcp`, `self.channel_sessions`, `self.persistent_views` as attributes for the ReadyButton callback to reach via `interaction.client`.
  </behavior>
  <action>
    Implement `LobbyCog` in `src/eldritch_dm/bot/cogs/lobby.py` per the &lt;interfaces&gt; conventions:

    - Define the curated `ADVENTURE_IDS: Final[dict[str, str]] = {...}` at module level per RESEARCH "Code Examples" (CoS, LMoP, HotDQ, PotA, OotA, ToA, WDH, WDMM, BGDIA).
    - `@app_commands.command(name="start_game", ...)` with `name: str, description: str | None = None` parameters. First line: `await interaction.response.defer(thinking=True)`. Then sequence: create_campaign → start_claudmaster_session → (try/except — see below) start_party_mode. The session_id from claudmaster MUST be captured in a local variable BEFORE the party_mode call so rollback can use it.
    - Rollback ordering: wrap start_party_mode in try/except. On exception, await `mcp_tools.end_claudmaster_session(self.mcp, session_id=cm_session_id)` (best-effort; suppress its own exceptions and log via structlog at WARNING). Then re-raise as a structured exception for the cog to surface to the user via ephemeral followup.
    - Markdown parsing: use `parse_party_mode_response` from Task 2. Build `dm20_party_token` as `json.dumps({"server_url": result.server_url, "members": [{"name": m.character_name, "url": m.url, "qr_path": str(m.qr_path) if m.qr_path else None} for m in result.members], "module_bound": null})`.
    - Already-running path: if `result.already_running` is True, call `get_party_status(self.mcp, campaign_name=name)` (returns dict with the same shape; verify on first call, defensive `.get()`) and use that response in place of the original.
    - QR rendering: defer to Plan 03's `bot/qr.py::render_qr_for_embed` — **but Plan 03 hasn't shipped yet**, so for Plan 01 inline a minimal `_render_qr(url: str) -> discord.File` helper in `lobby.py` that uses `segno.make(url, error="m").save(BytesIO, kind='png', scale=8)`. Plan 03 will refactor this into the shared `bot/qr.py` and update the import. **Add `segno>=1.6,<2.0` to `pyproject.toml` dependencies** as part of THIS task (Plan 01) — note the addition in the SUMMARY so Plan 02 doesn't add it twice.
    - Lobby embed: post via `interaction.followup.send(embed=lobby_embed(campaign_name=name, players=[], server_url=server_url, party_invite=server_url), file=qr_file, view=view)` where `view` is a `discord.ui.View()` with a `ReadyButton(int(channel_id))` added. Persist the message_id back to `persistent_views` so restart-rehydration can find it.

    - `@app_commands.command(name="load_adventure", ...)` with `adventure_id: str, campaign_name: str | None = None`. First line: defer. Read existing session via channel_sessions_repo. Mitigate non-idempotency per the test plan above. Call `load_adventure(self.mcp, module_id=adventure_id, populate_chapter_1=should_populate, campaign_name=session.campaign_name)`. On success, patch dm20_party_token JSON with `module_bound`. Post a confirmation embed (use a simple discord.Embed; not a new template — keep it inline).

    - `@load_adventure.autocomplete("adventure_id")` per RESEARCH "Code Examples" — exact pattern (substring match on ID or title, ≤25 results, instant).

    - Wire into `bot/bot.py`: add `LobbyCog` import and `await self.add_cog(LobbyCog(self, mcp=self.mcp, channel_sessions=self.channel_sessions, persistent_views=self.persistent_views, settings=self.settings, logger=self._logger))` inside `_load_cogs` AFTER the diagnostics cog. If `self.channel_sessions` / `self.persistent_views` are not yet attached to the bot, add them in `EldritchBot.__init__` (constructor signature already accepts the dependencies — verify by reading bot.py once at task start).

    - Tests: in `tests/bot/cogs/test_lobby.py`, use respx + AsyncMock pattern from Phase 1/2 to construct mock interactions. Cover: happy path (assert call order on MCPClient.call), start_party_mode failure → end_claudmaster_session called → no DB write, no-active-campaign for /load_adventure, idempotency mitigation (module_bound already set → populate_chapter_1=False), autocomplete returns 9 entries on empty input, autocomplete filters case-insensitively. Aim for 12-15 new tests covering both commands + state machine + rollback + idempotency. Use `tests/bot/cogs/__init__.py` empty package marker.

    Atomic commit message: `feat(03-lobby-character-ingest): lobby cog with /start_game, /load_adventure, autocomplete, rollback ordering, idempotency mitigation`.

    Implements LOBBY-01, LOBBY-02, LOBBY-03 (embed wiring).
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/bot/cogs/test_lobby.py tests/bot/test_bot_lifecycle.py -x -q 2&gt;&amp;1 | tail -25 &amp;&amp; lint-imports 2&gt;&amp;1 | tail -10</automated>
  </verify>
  <done>LobbyCog file ≥250 lines, /start_game + /load_adventure both decorated with @app_commands.command, ADVENTURE_IDS dict has 9 entries, /load_adventure has the autocomplete decorator, bot.py registers the cog, segno added to pyproject.toml, ≥12 lobby tests pass, lint-imports stays green (bot→mcp allowed; new files import nothing from persistence internals other than the repos which is fine because they're constructor-injected).</done>
</task>

<task type="auto">
  <name>Task 5: Atomic commits + lint + final 235+ baseline check</name>
  <files>tests/integration/test_phase1_smoke.py</files>
  <action>
    Verify the four atomic commits from Tasks 1-4 landed with the conventional-commit format (`feat(03-lobby-character-ingest): ...`, `test(...)`, `refactor(...)`). If multiple were squashed, split with `git reset HEAD~N` and re-commit per task. Then run the FULL test suite and lint chain end-to-end:

    1. `ruff check src tests` — must be clean
    2. `lint-imports` — must report all contracts kept
    3. `pytest -x` — must report ≥247 tests passing (235 prior + ≥12 new in this plan)

    Skim `tests/integration/test_phase1_smoke.py` and ensure it still passes unchanged — no Phase 3 wiring leaks into the Phase 1 smoke. If it depends on the bot lifecycle and now needs LobbyCog to be loadable, add a single `assert "lobby" in bot.cogs` check there (low-cost insurance for Phase 3 integration smoke landing in Plan 03).

    No new feature code in this task — purely housekeeping + final verification.
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; ruff check src tests &amp;&amp; lint-imports &amp;&amp; pytest -x -q 2&gt;&amp;1 | tail -6</automated>
  </verify>
  <done>Full pytest run reports ≥247 passing (was 235 before this plan), ruff clean, lint-imports green, four atomic commits visible in `git log --oneline | head -6` with the conventional-commit format.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Discord client → bot (slash invocation) | Untrusted text in `name`, `description`, `adventure_id`; could contain prompt-injection sentinels |
| Discord client → bot (button click) | Untrusted `interaction.user.id`; could be a non-roster user spamming ready |
| bot → dm20 (MCP execute) | Trusted local service, but errors could leak campaign names in stack traces |
| dm20 → bot (start_party_mode markdown) | Trusted local source, but file paths in the response point at the dm20 user's home dir (info disclosure if logged unredacted) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-01 | Tampering | `/start_game` campaign name input | mitigate | Pass `name` through dm20 unchanged but never echo it into LLM prompts (no LLM call in this plan); structlog logs the name but DB stores verbatim — acceptable, dm20 is the system of record |
| T-03-02 | Elevation of Privilege | ReadyButton clicked by non-roster user | mitigate | Roster check via `list_characters` → set of player_ids; reject non-members with ephemeral warning (D-13) |
| T-03-03 | Elevation of Privilege | `/load_adventure` run by non-DM | mitigate | `can_act_on_character(interaction, character_player_id=None)` → falls through to `manage_channels` check |
| T-03-04 | Denial of Service | Repeated `/load_adventure` re-runs duplicating Chapter 1 entities | mitigate | `module_bound` tracker in `dm20_party_token` JSON; second call defaults to `populate_chapter_1=False` (Pitfall 7) |
| T-03-05 | Information Disclosure | dm20 party-mode markdown contains absolute home-dir paths in QR file paths | mitigate | Parser extracts paths into `qr_path: Path` but cog reads bytes immediately and discards path; never log raw path strings (structlog redaction list adds `qr_path`) |
| T-03-06 | Spoofing | dm20 returns "Party Mode is already running" — different campaign reusing port | mitigate | Detect via parser `already_running` flag; call `get_party_status` to recover canonical state before trusting it (Pitfall 8) |
| T-03-07 | Tampering | partial-failure between start_claudmaster_session and start_party_mode leaves dangling Claudmaster session | mitigate | Best-effort `end_claudmaster_session` in `except` block; idempotent so safe to retry on next /start_game |
| T-03-SC | Tampering | npm/pip install of `segno` | mitigate | `segno` is `[VERIFIED]` per RESEARCH §Package Legitimacy Audit (6+ yrs, ~3M downloads/mo, MIT, GitHub source confirmed). No blocking human checkpoint required — disposition is direct add to pyproject.toml. |
</threat_model>

<verification>
## Phase-relative gates
- `pytest tests/mcp/test_tools.py tests/bot/cogs/test_lobby.py tests/bot/test_party_mode_parser.py tests/bot/test_permissions.py tests/bot/test_dynamic_items.py tests/bot/test_embeds.py -x` passes
- `pytest -x` (full suite) passes with ≥247 tests
- `ruff check src tests` clean
- `lint-imports` reports all contracts kept
- `grep -n "phase2_stub" src/eldritch_dm/bot/dynamic_items.py | wc -l` returns 3 (not 4) — ReadyButton stub is replaced; the other three DynamicItems still stub

## Source artifact coverage
- D-01: `lobby.py` cog file exists ✓
- D-02: Cog registered in `_load_cogs` ✓ (Task 4)
- D-03: Constructor-injected deps ✓ (Task 4)
- D-04: `/start_game` defer-first + 3-MCP-call orchestration + rollback ✓ (Task 4)
- D-05: `/load_adventure` with curated autocomplete ✓ (Task 4)
- D-09: lobby_embed extended with server_url ✓ (Task 3)
- D-10: Static dict autocomplete ✓ (Task 4 — RESEARCH §11 says segno not qrcode; QR inline-rendered, file moved to bot/qr.py in Plan 03)
- D-11: ReadyButton.callback real implementation ✓ (Task 3)
- D-12: Restart-survival via persistent_views.payload_json ✓ (Task 3)
- D-13: player_id roster gate ✓ (Task 3)
- D-14: Idempotency mitigation via module_bound ✓ (Task 4)
- D-15: Static ADVENTURE_IDS ✓ (Task 4)
- D-29: can_act_on_character helper ✓ (Task 2)
- D-37: structlog binding ✓ (Tasks 3+4)
</verification>

<success_criteria>
1. `/start_game` orchestrates create_campaign → start_claudmaster_session → start_party_mode in order, persists the trio in `channel_sessions`, posts a lobby embed with a segno QR + Ready button.
2. start_party_mode failure rolls back the Claudmaster session and leaves no DB row.
3. `/load_adventure` autocomplete returns curated entries client-side (no MCP cost per keystroke).
4. Re-running `/load_adventure` does NOT duplicate Chapter 1 entities (`module_bound` tracker + `populate_chapter_1=False` on retry).
5. ReadyButton click marks the user ready, transitions to EXPLORATION when all roster players have readied, calls `dm20__player_action(action='party_ready', context='lobby_complete')`, and the state survives a bot restart.
6. Permission gate accepts the invoking player OR a user with `manage_channels`; rejects everyone else with an ephemeral warning.
7. ≥247 tests pass (235 baseline + 12-15 new).
8. `ruff check` and `lint-imports` both clean.
</success_criteria>

<risks>
- **TOP RISK: load_adventure non-idempotency (RESEARCH §3, Pitfall 7).** Mitigation: module_bound tracker in dm20_party_token JSON + populate_chapter_1=False on subsequent calls. Acceptance: a test in Task 4 explicitly verifies the second /load_adventure call uses populate_chapter_1=False.
- **start_party_mode markdown shape drift.** dm20's markdown format is stable today but unversioned. Parser uses tolerant regex (not strict line offsets) per RESEARCH §1. Acceptance: parser unit tests include a "whitespace tolerance" case.
- **Bot attribute exposure (`self.mcp`, `self.channel_sessions`, `self.persistent_views`).** If Phase 2's `EldritchBot` doesn't yet expose these, Task 4 must add them in `__init__`. Acceptance: a bot lifecycle test asserts the attributes exist after construction.
- **ReadyButton callback can't accept extra kwargs.** discord.py routes via class-level dispatch; cog can't inject deps. Mitigated by reading from `interaction.client` (the bot). Acceptance: ReadyButton tests inject a mock client with `mcp`, `channel_sessions`, `persistent_views` attributes.
- **segno transitive deps.** Pure-Python, zero deps, 76 KB wheel per RESEARCH §11. No risk; adding to pyproject.toml is safe.
</risks>

<dependencies>
- No cross-plan blocking deps; this plan is the foundation for Plans 02 and 03 (it adds the bot attributes + `permissions.py` helper they both consume).
- External: segno (NEW pin in pyproject.toml — Task 4).
- Internal: Phase 1 (MCPClient + repos), Phase 2 (EldritchBot + DynamicItem registry + lobby_embed shell + ReadyButton stub).
</dependencies>

<output>
Create `.planning/phases/03-lobby-character-ingest/03-01-SUMMARY.md` documenting:
- New cog (lobby.py), new helpers (party_mode_parser.py, permissions.py)
- 6 new MCP wrappers; segno added to pyproject.toml
- ReadyButton real callback + state machine
- Test count delta (≥12 new); baseline maintained
- Open follow-ups for Plan 02 + Plan 03 (notably: bot/qr.py extraction in Plan 03)
</output>
