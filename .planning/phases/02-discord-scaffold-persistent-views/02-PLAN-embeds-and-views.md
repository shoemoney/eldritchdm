---
phase: 02-discord-scaffold-persistent-views
plan: 02
type: execute
wave: 2
depends_on: ["01"]
files_modified:
  - src/eldritch_dm/bot/embeds.py
  - src/eldritch_dm/bot/dynamic_items.py
  - src/eldritch_dm/bot/warnings.py
  - tests/bot/test_embeds.py
  - tests/bot/test_dynamic_items.py
  - tests/bot/test_warnings.py
  - tests/bot/__snapshots__/test_embeds.ambr
autonomous: true
requirements: [BOT-03, BOT-04, BOT-07]

must_haves:
  truths:
    - "Four pure-function embed renderers (`lobby_embed`, `room_embed`, `combat_embed`, `character_confirm_embed`) exist, return `discord.Embed`, and have snapshot tests."
    - "Four `DynamicItem[Button]` subclasses (`ReadyButton`, `DeclareActionButton`, `EndTurnButton`, `RiposteButton`) define regex `custom_id` templates per D-20."
    - "Each DynamicItem's `from_custom_id` round-trips: building an instance from a custom_id string, then reading its template-captured fields, recovers the original encoded values."
    - "All `custom_id`s fit in 100 characters (D-22) for plausible Discord snowflake inputs."
    - "`WarningKind` enum + `send_warning(interaction, kind, **ctx)` helper produces the standardized ephemeral payloads from D-31/D-33."
    - "Callbacks on each DynamicItem are STUBS that log + ephemeral-reply 'Phase 2 stub — wired up in Phase N' (D-23); they still defer first."
  artifacts:
    - path: "src/eldritch_dm/bot/embeds.py"
      provides: "EmbedColor IntEnum + 4 renderer functions + helper PlayerStatus dataclass"
    - path: "src/eldritch_dm/bot/dynamic_items.py"
      provides: "4 DynamicItem subclasses + base class with shared helpers"
    - path: "src/eldritch_dm/bot/warnings.py"
      provides: "WarningKind enum + send_warning helper"
  key_links:
    - from: "src/eldritch_dm/bot/dynamic_items.py"
      to: "discord.ui.DynamicItem"
      via: "subclass with `template = re.compile(r'...')` class attr"
    - from: "src/eldritch_dm/bot/warnings.py"
      to: "discord.Interaction.followup.send"
      via: "ephemeral=True payload"
---

<objective>
Build the visual + interactive primitives every later phase will compose: pure embed renderers, persistent-button `DynamicItem` subclasses with regex `custom_id` templates, and a centralized ephemeral warning helper. Callbacks are stubs (D-23) — real handlers land in Phases 3-5. No bot wiring yet: that's Plan 03's job.

Purpose: Stabilize the embed/View shape NOW so Phases 3-5 don't churn the visual language. Snapshot tests pin the look and feel.

Output: Three modules (`embeds.py`, `dynamic_items.py`, `warnings.py`), three test files with snapshot + parsing coverage.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/02-discord-scaffold-persistent-views/02-CONTEXT.md
@.planning/phases/02-discord-scaffold-persistent-views/02-RESEARCH.md
@.planning/phases/02-discord-scaffold-persistent-views/02-01-SUMMARY.md
@src/eldritch_dm/bot/__init__.py
@src/eldritch_dm/bot/bot.py

<interfaces>
discord.py 2.7.1 DynamicItem pattern (per official `persistent.py` example + RESEARCH Q1):

```
class MyButton(discord.ui.DynamicItem[discord.ui.Button], template=r'^myb:(?P<id>\d+)$'):
    def __init__(self, captured_id: int) -> None:
        super().__init__(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Click",
            custom_id=f"myb:{captured_id}",
        ))
        self.captured_id = captured_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str], /) -> MyButton:
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        ...
```

Note: in 2.7.1 the `template=` kwarg in the class declaration is the canonical pattern; `from_custom_id` is a classmethod (not async-required but conventionally async); `callback` is async and is invoked by the View registry on a regex match. See 02-RESEARCH.md Q1 for the authoritative pattern + edge cases.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Embed renderers with snapshot tests</name>
  <files>
    src/eldritch_dm/bot/embeds.py,
    tests/bot/test_embeds.py
  </files>
  <behavior>
    Module exports (`embeds.py`):

    - `class EmbedColor(IntEnum)` per D-15:
      - `LOBBY = 0x5865F2`
      - `EXPLORATION = 0x57F287`
      - `COMBAT = 0xED4245`
      - `CHARACTER_CONFIRM = 0xFEE75C`

    - `_FOOTER_TEXT = "🎲 ShoeGPT · EldritchDM"` (D-16).

    - `@dataclass(frozen=True) class PlayerStatus`: `display_name: str`, `ready: bool`, `character_name: str | None = None`.

    - `def lobby_embed(*, campaign_name: str, players: Sequence[PlayerStatus], party_invite: str | None = None) -> discord.Embed`:
      title `f"⚔️ {campaign_name} — Lobby"`; color LOBBY; description lists players as `f"{'✅' if p.ready else '⌛'} **{p.display_name}** — {p.character_name or 'no character yet'}"` (newline-joined). Includes a `Join Party Mode` field with the `party_invite` value if not None. Footer with timestamp.

    - `def room_embed(*, room_title: str, narration: str, party_hp: Sequence[tuple[str, int, int]]) -> discord.Embed`:
      title `f"🗺️ {room_title}"`; color EXPLORATION; description = narration (truncate to 4000 chars). Field "Party" with `name | current_hp/max_hp` lines from `party_hp`.

    - `def combat_embed(*, round_n: int, current_actor: str, initiative: Sequence[tuple[str, int, int, int, list[str]]]) -> discord.Embed`:
      `(name, initiative_roll, hp_cur, hp_max, conditions)`. Title `f"⚔️ Combat — Round {round_n}"`; color COMBAT; description "Current turn: **{current_actor}**"; one field per actor: name (with ⏳ marker if current), `f"init {init} · HP {cur}/{max} · {','.join(conditions) or '—'}"`.

    - `def character_confirm_embed(*, player_name: str, character: dict) -> discord.Embed`:
      title `f"📜 Confirm Character — {player_name}"`; color CHARACTER_CONFIRM; description = JSON-pretty extraction of `name, race, class, level, ability_scores, hp, ac` from the character dict. Asks "✅ Confirm or ❌ Cancel" in description footer line.

    Footer + timestamp behavior: each renderer sets `embed.timestamp = datetime.now(tz=UTC)` and `embed.set_footer(text=_FOOTER_TEXT)`. NOTE: timestamp varies — snapshot tests must scrub it (see below).

    No I/O. No async. No discord client references. Pure functions on data.

    Tests (`test_embeds.py`):
    - Use `syrupy` SnapshotAssertion fixture. Each test calls a renderer with fixed inputs and asserts `embed.to_dict() == snapshot(matcher=...)` where the matcher scrubs the volatile `timestamp` field (replace with `"<TIMESTAMP>"`).
    - Test 1: `lobby_embed` with 4 players (2 ready, 2 not), `party_invite="https://dm20.local/party/abc"`.
    - Test 2: `room_embed` with a sample narration and a 4-PC party_hp tuple list.
    - Test 3: `combat_embed` round 3, current_actor "Thorin", 5-actor initiative list (mixed conditions).
    - Test 4: `character_confirm_embed` for a sample DDB-shaped character dict.
    - Test 5: parametric — assert each renderer's `embed.color.value == EmbedColor.{X}` and `embed.footer.text == _FOOTER_TEXT`.
    - Test 6: `lobby_embed` with `party_invite=None` produces no "Join Party Mode" field.
  </behavior>
  <action>
    Implement `embeds.py` per `<behavior>`. Use `discord.Embed` directly; do NOT subclass.

    Snapshot scrubbing — write a small helper in the test file:

    `def _scrub_ts(data: dict) -> dict:` that pops `"timestamp"` and replaces with `"<TIMESTAMP>"` recursively. Or use `syrupy`'s built-in `PathMatcher` to ignore the `timestamp` path. Pick whichever proves simpler — both are acceptable.

    First test run will write the `.ambr` snapshot file; commit it. Subsequent runs compare. If a renderer needs to change later, snapshots must be updated via `pytest --snapshot-update` (intentional churn — that's the point of pinning).

    Commit 1 (RED): `test(02-discord-scaffold-persistent-views): add failing embed renderer tests`
    Commit 2 (GREEN): `feat(02-discord-scaffold-persistent-views): embed renderers (lobby/room/combat/character_confirm)`
    Commit 3 (CHORE): `test(02-discord-scaffold-persistent-views): commit embed snapshot baselines`
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM && pytest tests/bot/test_embeds.py -x -q</automated>
  </verify>
  <done>All 6 embed tests pass; `.ambr` snapshot baseline committed.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: DynamicItem subclasses with regex custom_id templates</name>
  <files>
    src/eldritch_dm/bot/dynamic_items.py,
    tests/bot/test_dynamic_items.py
  </files>
  <behavior>
    Module exports (`dynamic_items.py`):

    Four subclasses of `discord.ui.DynamicItem[discord.ui.Button]`, each with the regex template from D-20:

    | Class | Template | Encoded fields |
    |---|---|---|
    | `ReadyButton` | `^ready:(?P<channel_id>\d+)$` | channel_id |
    | `DeclareActionButton` | `^declare:(?P<channel_id>\d+)$` | channel_id |
    | `EndTurnButton` | `^endturn:(?P<channel_id>\d+):(?P<actor_id>\d+)$` | channel_id, actor_id |
    | `RiposteButton` | `^riposte:(?P<timer_id>\d+):(?P<user_id>\d+)$` | timer_id, user_id |

    Each class:
    - Declares `template=` (compiled or raw — match the discord.py 2.7.1 idiom from 02-RESEARCH.md Q1).
    - `__init__` accepts the captured fields as ints; constructs a `discord.ui.Button` with style/label/emoji appropriate to the kind:
      - `ReadyButton`: green button labeled "✅ Ready" with `custom_id=f"ready:{channel_id}"`.
      - `DeclareActionButton`: blurple "💬 Declare Action" with `custom_id=f"declare:{channel_id}"`.
      - `EndTurnButton`: gray "⏭️ End Turn" with `custom_id=f"endturn:{channel_id}:{actor_id}"`.
      - `RiposteButton`: red "⚔️ Riposte!" with `custom_id=f"riposte:{timer_id}:{user_id}"`.
    - Stores captured fields as instance attributes.
    - `@classmethod async def from_custom_id(cls, interaction, item, match, /)` parses the regex match and returns `cls(...)`.
    - `async def callback(self, interaction)` is a STUB (D-23):
      - First line: `await interaction.response.defer(thinking=True, ephemeral=True)`.
      - Bind structlog context (D-38): `channel_id` / `actor_id` / `timer_id` / `user_id` as applicable; `custom_id=self._custom_id_str()`; `view_class=type(self).__name__`.
      - Log "phase2_stub_callback_invoked".
      - `await interaction.followup.send(content=f"⏳ Phase 2 stub — {type(self).__name__} will be wired up in a later phase.", ephemeral=True)`.

    Also export a module-level constant:
    `DYNAMIC_ITEM_CLASSES: tuple[type[discord.ui.DynamicItem], ...] = (ReadyButton, DeclareActionButton, EndTurnButton, RiposteButton)`
    (used by Plan 03's `setup_hook` to register them all).

    Tests (`test_dynamic_items.py`):
    - Test 1 (parametric over the 4 classes): construct an instance with sample ints, assert `instance.children[0].custom_id` (or whatever the Button accessor is in 2.7.1) equals the expected string, AND assert it's ≤ 100 chars (D-22).
    - Test 2 (parametric): for each class, run its `template.fullmatch(custom_id)`; call `from_custom_id(...)`; assert returned instance has the same captured fields as the source ints.
    - Test 3: bad custom_id (e.g. `"ready:notanumber"`) does NOT match the template (regex `fullmatch` returns None).
    - Test 4 (parametric): each class's stub callback, given a mocked interaction, calls `defer` first then `followup.send` with the expected stub message including `type(self).__name__`.
    - Test 5: `DYNAMIC_ITEM_CLASSES` tuple has length 4 and contains the four expected classes.
    - Test 6 (boundary): plausible snowflake inputs (19-digit channel_id + 19-digit actor_id) → `endturn:` and `riposte:` custom_ids fit in 100 chars (string length assertion).
  </behavior>
  <action>
    Implement per `<behavior>`. Follow the EXACT discord.py 2.7.1 DynamicItem declaration style documented in 02-RESEARCH.md Q1 — if research confirms `template=` is provided via class kwarg, use that; if it's an annotated class attr, use that. Do not invent a third form.

    Helper: `_custom_id_str(self) -> str` on each class returns the formatted custom_id; reused by callback logging.

    Plan 03 will: (a) call `bot.add_dynamic_items(*DYNAMIC_ITEM_CLASSES)` in setup_hook, (b) at end of Phase 2 replace the stub callback bodies with the real handlers when the corresponding cog lands in Phase 3/4/5 — for now, do NOT add any "real handler" hooks; keep stubs total.

    Commit 1 (RED): `test(02-discord-scaffold-persistent-views): add failing DynamicItem tests`
    Commit 2 (GREEN): `feat(02-discord-scaffold-persistent-views): 4 DynamicItem subclasses (Ready/Declare/EndTurn/Riposte) with regex custom_ids`
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM && pytest tests/bot/test_dynamic_items.py -x -q</automated>
  </verify>
  <done>All 6 tests pass; `DYNAMIC_ITEM_CLASSES` importable; all custom_ids ≤ 100 chars for 19-digit inputs.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: WarningKind enum + send_warning helper</name>
  <files>
    src/eldritch_dm/bot/warnings.py,
    tests/bot/test_warnings.py
  </files>
  <behavior>
    Module exports (`warnings.py`):

    - `class WarningKind(StrEnum)`: `NOT_YOUR_TURN`, `RIPOSTE_EXPIRED`, `DM_OFFLINE`, `INVALID_ACTION`, `RATE_LIMITED`.

    - `_COPY: dict[WarningKind, str]` table per D-33 (full set):
      - `NOT_YOUR_TURN`: `"❌ It is not your turn, **{actor_name}**. Sit tight!"`
      - `RIPOSTE_EXPIRED`: `"⌛ The riposte window has closed."`
      - `DM_OFFLINE`: `"🔌 ShoeGPT is offline. Health check failed {failure_count} times in a row. Try again in a moment."`
      - `INVALID_ACTION`: `"❌ Invalid action: {reason}"`
      - `RATE_LIMITED`: `"🐌 Slow down — try again in {retry_after}s."`

    - `async def send_warning(interaction: discord.Interaction, kind: WarningKind, **ctx) -> None`:
      - Assumes `interaction.response.is_done()` is True (caller deferred per D-09) — uses `interaction.followup.send`.
      - Formats `_COPY[kind].format(**ctx)`; if `KeyError` on missing format key, raises a clear error: `ValueError(f"Missing context for warning {kind}: needs {missing_keys}")`.
      - Sends `await interaction.followup.send(content=formatted, ephemeral=True)`.
      - Logs `warning_sent` with kind + ctx (D-38).

    Tests (`test_warnings.py`):
    - Test 1: `send_warning(interaction, NOT_YOUR_TURN, actor_name="Thorin")` → followup.send called with content containing "Thorin" and "not your turn", `ephemeral=True`.
    - Test 2 (parametric over all 5 kinds): build interaction, call helper with the correct ctx kwargs, assert followup.send called exactly once with `ephemeral=True`.
    - Test 3: `send_warning(interaction, NOT_YOUR_TURN)` WITHOUT `actor_name` → raises `ValueError` mentioning `actor_name`.
    - Test 4: WarningKind enum has exactly 5 members; the `_COPY` dict has an entry for each.
  </behavior>
  <action>
    Implement per `<behavior>`. Use `MagicMock(spec=discord.Interaction)` with `AsyncMock` for `.followup.send` in tests. The helper itself does not need to check `response.is_done()` defensively — D-09's contract is enforced by the EDM001 lint rule landing in Plan 03; this helper trusts the contract.

    Commit 1 (RED): `test(02-discord-scaffold-persistent-views): add failing warning helper tests`
    Commit 2 (GREEN): `feat(02-discord-scaffold-persistent-views): ephemeral warning helper (WarningKind, send_warning)`
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM && pytest tests/bot/test_warnings.py -x -q && pytest tests/bot -x -q</automated>
  </verify>
  <done>All warning tests pass; full `tests/bot` suite green; module exports correct.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Discord interaction → DynamicItem.callback | Untrusted: channel_id / actor_id / user_id parsed from `custom_id` |
| Renderer inputs → embed | Trusted (callers are bot-internal); but text fields could one day include narration containing user-controlled chars — sanitizer (Phase 1) already covers that for player text |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-07 | Tampering | `custom_id` regex | mitigate | Templates use `^...$` anchors + `\d+` for ids (D-20) — non-numeric or extra-suffix payloads cannot match. Test 3 of dynamic_items pins this. |
| T-02-08 | Information disclosure | `character_confirm_embed` payload | mitigate | Render only fields enumerated in D-13 (name, race, class, level, ability_scores, hp, ac) — do NOT splat full DDB JSON. Caller chooses dict shape. |
| T-02-09 | Elevation of privilege | `EndTurnButton` callback | mitigate | Encoded `actor_id` allows the real (Phase 4) handler to gate by Discord user_id; for now the stub merely logs — gating belongs to the future real handler. Plan 03's restart drill verifies dispatch; Phase 4's `cogs/combat.py` enforces the gate. |
| T-02-10 | Denial of service | `custom_id` length | mitigate | D-22 explicit 100-char limit. Test 6 of dynamic_items pins this for 19-digit snowflakes (the realistic worst case). |
| T-02-11 | Information disclosure | `send_warning` payloads | mitigate | All warnings are ephemeral (D-32); never broadcast to channel. |
</threat_model>

<verification>
- `pytest tests/bot -x -q` green (existing Plan 01 tests + new embed/dynamic_items/warnings tests).
- `lint-imports` green (no new contracts needed, but the existing `bot/` contract must still hold — `embeds.py`/`dynamic_items.py`/`warnings.py` may import from `discord`, `eldritch_dm.logging`, stdlib only; NO MCP/persistence reach-through).
- Manual: `python -c "from eldritch_dm.bot.embeds import lobby_embed, EmbedColor; from eldritch_dm.bot.dynamic_items import DYNAMIC_ITEM_CLASSES; from eldritch_dm.bot.warnings import WarningKind, send_warning; print(EmbedColor.LOBBY, len(DYNAMIC_ITEM_CLASSES), list(WarningKind))"` prints expected values.
</verification>

<success_criteria>
- Four embed renderers exist, are pure, and have snapshot baselines.
- Four DynamicItem subclasses exist; their custom_id regexes round-trip; stubs defer-then-followup correctly.
- WarningKind + send_warning helper exist; all 5 standardized warnings render correctly.
- All 17+ Plan 02 tests pass (6 embed + 6 dynamic_items + 4 warnings + 1 export-shape sanity).
- Nothing in this plan wires anything into the bot yet — Plan 03 does the registration + setup_hook integration.
</success_criteria>

<output>
Create `.planning/phases/02-discord-scaffold-persistent-views/02-02-SUMMARY.md` when done.
</output>
