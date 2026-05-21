---
phase: 03-lobby-character-ingest
plan: 03
type: execute
wave: 3
depends_on:
  - 03-01
  - 03-02
files_modified:
  - src/eldritch_dm/bot/qr.py
  - src/eldritch_dm/bot/modals.py
  - src/eldritch_dm/bot/cogs/ingest.py
  - src/eldritch_dm/bot/cogs/lobby.py
  - src/eldritch_dm/bot/bot.py
  - src/eldritch_dm/bot/embeds.py
  - tests/bot/test_qr.py
  - tests/bot/test_modals.py
  - tests/bot/cogs/test_ingest.py
  - tests/integration/test_phase3_smoke.py
  - .planning/phases/03-lobby-character-ingest/03-SUMMARY.md
  - .planning/REQUIREMENTS.md
  - .planning/ROADMAP.md
  - .planning/STATE.md
autonomous: true
requirements:
  - INGEST-01
  - INGEST-02
  - INGEST-08
  - INGEST-09
  - INGEST-10
  - INGEST-11
  - LOBBY-03
tags:
  - discord
  - modals
  - ingest
  - qr
  - integration

must_haves:
  truths:
    - "/upload_character_url <ddb_url> calls dm20__import_from_dndbeyond and posts an ephemeral confirmation in <8s for the happy path"
    - "/upload_character_file routes PNG/JPG to OCR path, PDF to PDF path via magic-byte sniff — Discord-reported content_type is never trusted alone"
    - "/upload_character_file rejects attachments larger than 10 MB BEFORE calling attachment.read()"
    - "Confidence score < 0.6 → manual-entry modal opens, prefilled with best-guess values (D-27)"
    - "Confidence score ≥ 0.6 → manual-review modal opens with the parsed CharacterSheet for confirmation (D-28)"
    - "Both modals fit Discord's hard 5-component cap: name + class + level + race + 'STR DEX CON INT WIS CHA' single-field per RESEARCH §5"
    - "Submit triggers dm20__create_character with player_id=str(interaction.user.id) so combat can map back to Discord users (D-13)"
    - "Lobby embed updates non-ephemerally to show '✅ {char_name} ({class}, lvl {N}) joined' after a successful commit (D-30)"
    - "/upload_character_manual opens the manual-entry modal directly without OCR — useful when player knows OCR will fail (D-08)"
    - "Permission gate accepts invoking player OR manage_channels DM — non-owners and non-DMs receive ephemeral 'Only the uploading player or DM can do this' (D-29)"
    - "QR rendering moved from inline helper in Plan 01 lobby.py into bot/qr.py — shared between lobby and any future feature; Plan 01's inline helper is deleted"
    - "Phase 3 integration smoke test exercises lobby + ingest end-to-end with respx/AsyncMock — completes in <2s and proves the LOBBY-01..04 + INGEST-01..11 wiring"
  artifacts:
    - path: "src/eldritch_dm/bot/qr.py"
      provides: "render_qr_for_embed(url, *, filename) -> discord.File using segno per RESEARCH §11"
      min_lines: 30
    - path: "src/eldritch_dm/bot/modals.py"
      provides: "CharacterReviewModal + CharacterEntryModal + secondary OptionalFieldsModal — all 5-component-compliant"
      min_lines: 150
    - path: "src/eldritch_dm/bot/cogs/ingest.py"
      provides: "IngestCog with /upload_character_url, /upload_character_file, /upload_character_manual; routes by confidence; permission-gated"
      min_lines: 250
    - path: "tests/integration/test_phase3_smoke.py"
      provides: "End-to-end smoke covering /start_game → /upload_character_file → ReadyButton → EXPLORATION transition with all external deps mocked"
      min_lines: 100
    - path: ".planning/phases/03-lobby-character-ingest/03-SUMMARY.md"
      provides: "Phase 3 retrospective summary with deliverables, test counts, deferred items, and Phase 4 handoff notes"
  key_links:
    - from: "src/eldritch_dm/bot/cogs/ingest.py"
      to: "src/eldritch_dm/ingest/pipeline.py"
      via: "await ingest(attachment_bytes, content_type, filename, ...)"
      pattern: "from eldritch_dm.ingest import ingest|ingest\\("
    - from: "src/eldritch_dm/bot/cogs/ingest.py"
      to: "src/eldritch_dm/bot/permissions.py"
      via: "can_act_on_character gating"
      pattern: "can_act_on_character\\("
    - from: "src/eldritch_dm/bot/cogs/ingest.py"
      to: "src/eldritch_dm/mcp/tools.py"
      via: "import_from_dndbeyond / create_character / update_character / list_characters"
      pattern: "import_from_dndbeyond|create_character"
    - from: "src/eldritch_dm/bot/cogs/ingest.py"
      to: "src/eldritch_dm/bot/modals.py"
      via: "interaction.response.send_modal(CharacterReviewModal(...) | CharacterEntryModal(...))"
      pattern: "send_modal\\("
    - from: "src/eldritch_dm/bot/cogs/lobby.py"
      to: "src/eldritch_dm/bot/qr.py"
      via: "render_qr_for_embed (refactor: replaces inline _render_qr from Plan 01)"
      pattern: "render_qr_for_embed"
---

<objective>
Phase 3 Plan 03 — Ingest cog (URL/file/manual upload commands), confidence-routed modals, QR helper extraction, and Phase 3 phase-closure (SUMMARY + REQUIREMENTS check-offs + ROADMAP/STATE updates).

Purpose: Close Phase 3. Wire `src/eldritch_dm/ingest/` (built in Plan 02) into Discord via three slash commands and two confidence-routed modals. Refactor Plan 01's inline QR helper into a shared `bot/qr.py`. Persist the resulting character through `dm20__create_character` with `player_id` binding so Phase 4's combat turn gatekeeping can map button clicks back to Discord users. Land the Phase 3 integration smoke test and finalize all planning artifacts (SUMMARY, REQUIREMENTS check-offs, ROADMAP marks, STATE update).

Output: 3 new bot files (`qr.py`, `modals.py`, `cogs/ingest.py`), 1 new integration smoke test, ≥15 new unit tests (modal flow, confidence routing, permission denial, oversize rejection), and the closing planning artifacts that mark Phase 3 [x].
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
@.planning/phases/03-lobby-character-ingest/03-01-SUMMARY.md
@.planning/phases/03-lobby-character-ingest/03-02-SUMMARY.md

@src/eldritch_dm/bot/cogs/lobby.py
@src/eldritch_dm/bot/dynamic_items.py
@src/eldritch_dm/bot/embeds.py
@src/eldritch_dm/bot/permissions.py
@src/eldritch_dm/bot/party_mode_parser.py
@src/eldritch_dm/ingest/__init__.py
@src/eldritch_dm/ingest/pipeline.py
@src/eldritch_dm/ingest/schema.py
@src/eldritch_dm/mcp/tools.py

<interfaces>
<!-- Contracts from Plans 01 and 02. Executor: do not re-derive. -->

From Plan 02 ingest module:
```python
from eldritch_dm.ingest import ingest, IngestResult, CharacterSheet, AbilityScores

@dataclass(frozen=True)
class IngestResult:
    raw_text: str
    parsed_sheet: CharacterSheet | None
    confidence_score: float
    validation_warnings: list[str]
    ocr_backend: str | None
    pdf_backend: str | None

async def ingest(
    attachment_bytes: bytes,
    content_type: str | None,
    filename: str,
    *,
    player_name: str | None,
    user_id: str,
    openai_client: AsyncOpenAI,
    mcp_client: MCPClient,
) -> IngestResult
```

From Plan 01:
```python
# src/eldritch_dm/bot/permissions.py
def can_act_on_character(interaction: discord.Interaction, character_player_id: str | None) -> bool
# True if user.id == character_player_id OR user.guild_permissions.manage_channels

# src/eldritch_dm/bot/cogs/lobby.py contains _render_qr(url) inline — TO BE REMOVED in Task 1 here
# Re-import path becomes: from eldritch_dm.bot.qr import render_qr_for_embed
```

From Plan 01 MCP wrappers:
```python
# src/eldritch_dm/mcp/tools.py
async def import_from_dndbeyond(client, *, url_or_id, player_name=None) -> dict
async def create_character(client, *, campaign_name, character: dict) -> dict
async def update_character(client, *, campaign_name, character_id, updates: dict) -> dict
async def list_characters(client, *, campaign_name) -> dict
```

Modal contracts (RESEARCH §5 + D-28 — 5-component HARD limit):

CharacterReviewModal (used when confidence ≥ 0.6):
- TextInput #1: "Character Name" (default = sheet.name, max 80)
- TextInput #2: "Class" (default = sheet.character_class, max 40)
- TextInput #3: "Level (1-20)" (default = str(sheet.class_level), max 2)
- TextInput #4: "Race" (default = sheet.race, max 40)
- TextInput #5: "Ability Scores (STR DEX CON INT WIS CHA)" — single field, space-separated, default = "15 18 14 12 10 8", max_length 23

CharacterEntryModal (used when confidence < 0.6):
- Same 5 fields, but defaults are best-guesses or empty strings; intended for player to type from scratch.

OptionalFieldsModal (secondary; opened from a "Refine" button in the confirmation embed, NOT auto-launched — D-28):
- Subclass, Background, Skills (comma-separated), Spells (comma-separated), Alignment — also 5 fields max.

The "Ability Scores" single-field parsing helper:
```python
def parse_abilities_field(s: str) -> AbilityScores:
    """Parse 'STR DEX CON INT WIS CHA' space-separated string into AbilityScores.
    Raises ValueError on wrong count or non-int values."""
    parts = s.split()
    if len(parts) != 6:
        raise ValueError("Expected 6 ability scores separated by spaces")
    try:
        ints = [int(p) for p in parts]
    except ValueError as e:
        raise ValueError(f"Ability scores must be integers: {e}")
    return AbilityScores(
        strength=ints[0], dexterity=ints[1], constitution=ints[2],
        intelligence=ints[3], wisdom=ints[4], charisma=ints[5]
    )
```
Lives in `src/eldritch_dm/bot/modals.py` as a module-level function.

From Plan 01 lobby cog (to be patched in Task 1):
- `_render_qr` inline helper in lobby.py — DELETE in Task 1. Replace its sole call site with `from eldritch_dm.bot.qr import render_qr_for_embed`.

From RESEARCH §6 (Attachment.read() before size check):
```python
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB

async def _read_and_route(attachment: discord.Attachment) -> tuple[Literal["image", "pdf"], bytes]:
    if attachment.size > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"Attachment exceeds {MAX_ATTACHMENT_BYTES // 1024 // 1024} MB limit")
    data = await attachment.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff":
        return "image", data
    if data[:5] == b"%PDF-":
        return "pdf", data
    raise ValueError("Unsupported file format (PNG, JPEG, PDF only)")
```
This helper is duplicated logic with Plan 02's pipeline `_sniff_kind` — keep both: Plan 02's lives in pipeline.py as a defense-in-depth check; Plan 03's lives in the cog to surface a user-facing error BEFORE the bytes hit the executor.
</interfaces>

<conventions>
- **D-09 defer-first** every interaction handler awaits `defer(thinking=True, ephemeral=True)` first (ephemeral=True for ingest because confirmations are ephemeral per D-30).
- **D-30 ephemeral confirmations**: every cog reply uses `followup.send(..., ephemeral=True)`. The only non-ephemeral surface is the lobby embed UPDATE on commit ("✅ Aragorn joined") — done via `lobby_message.edit(embed=updated_lobby_embed(...))` not via followup.
- **D-37 structlog binding**: cog binds `attachment_filename`, `bytes_size`, `ocr_backend`, `ocr_confidence`, `translation_model`, `pydantic_errors`, `dm20_character_id` per the CONTEXT contract.
- **Modal callbacks**: `Modal.on_submit` is invoked by Discord; the modal stores a callback function `_on_submit_cb` that the cog provides at construction. This keeps the modal class testable in isolation (no cog reference inside the modal).
- **Atomic commits**: one commit per task, conventional-commit format. The final task includes the SUMMARY + REQUIREMENTS + ROADMAP + STATE check-off commit.
</conventions>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extract bot/qr.py from Plan 01's inline helper; refactor lobby.py to import it</name>
  <files>src/eldritch_dm/bot/qr.py, src/eldritch_dm/bot/cogs/lobby.py, tests/bot/test_qr.py</files>
  <behavior>
    QR module tests:
    - `render_qr_for_embed("https://example.com")` returns a `discord.File` instance.
    - The PNG bytes start with `\x89PNG\r\n\x1a\n` (magic bytes).
    - The file is positioned at offset 0 (so Discord can read from the start).
    - Default filename is "qr.png"; custom filename works.
    - Error correction level is "m" per RESEARCH §11 sample (15%); scale=8, border=2.
    - File can be passed to `discord.Embed.set_thumbnail(url=f"attachment://{filename}")` pattern (test asserts the filename attribute matches).

    Lobby refactor tests:
    - `grep -c "import segno" src/eldritch_dm/bot/cogs/lobby.py` returns 0 (segno moved to qr.py).
    - `grep -c "render_qr_for_embed" src/eldritch_dm/bot/cogs/lobby.py` returns ≥1 (import + at least one call site).
    - Existing Plan 01 lobby tests still pass — refactor is internal-only.
  </behavior>
  <action>
    Create `src/eldritch_dm/bot/qr.py` per RESEARCH §11 "QR Code Generation" sample:
    - `def render_qr_for_embed(url: str, *, filename: str = "qr.png") -> discord.File`.
    - Uses `segno.make(url, error="m").save(buf, kind="png", scale=8, border=2, dark="black", light="white")`.
    - Returns `discord.File(buf, filename=filename)` after `buf.seek(0)`.
    - Add a docstring referencing RESEARCH §11 and the EmbedColor pattern from embeds.py.

    Refactor `src/eldritch_dm/bot/cogs/lobby.py`:
    - Delete the `_render_qr` inline helper added in Plan 01.
    - Replace its call site with `qr_file = render_qr_for_embed(server_url, filename="lobby_qr.png")`.
    - Update imports (`from eldritch_dm.bot.qr import render_qr_for_embed`).
    - Drop the local `import segno` and `import io` if no longer needed.

    Tests in `tests/bot/test_qr.py`: ≥5 tests covering the behavior block. Use BytesIO sniffing for the PNG magic-byte check.

    Implements LOBBY-03 (cleanup) — the QR component finalized.
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/bot/test_qr.py tests/bot/cogs/test_lobby.py -x -q 2&gt;&amp;1 | tail -15 &amp;&amp; lint-imports 2&gt;&amp;1 | tail -10</automated>
  </verify>
  <done>qr.py exists; lobby.py imports from qr.py; grep confirms segno removed from lobby.py; ≥5 qr tests pass; Plan 01's lobby tests still pass unchanged; lint-imports green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Modals — CharacterReviewModal + CharacterEntryModal + parse_abilities_field + ability-string round-trip helpers</name>
  <files>src/eldritch_dm/bot/modals.py, tests/bot/test_modals.py</files>
  <behavior>
    parse_abilities_field tests:
    - "15 18 14 12 10 8" → AbilityScores(15, 18, 14, 12, 10, 8).
    - "15 18 14" → ValueError("Expected 6 ability scores...").
    - "15 18 14 12 10 foo" → ValueError("must be integers...").
    - "15  18  14  12  10  8" (multi-space) → still parses (use .split() not .split(" ")).
    - "  15 18 14 12 10 8  " (leading/trailing whitespace) → parses.
    - Ability score 0 or 31 → raises pydantic ValidationError (from AbilityScores constructor).

    serialize_abilities (the inverse helper) tests:
    - serialize_abilities(AbilityScores(15, 18, 14, 12, 10, 8)) == "15 18 14 12 10 8".

    CharacterReviewModal tests (use AsyncMock for Interaction per D-36):
    - Constructor takes `(prefill: dict, *, on_submit_cb: Callable[[discord.Interaction, dict], Awaitable[None]])`.
    - `len(modal.children) == 5` (hard cap respected).
    - Each TextInput has `default` populated from prefill dict.
    - Ability scores field default is space-separated string from prefill["abilities"].
    - `on_submit` defers ephemeral first, then invokes `on_submit_cb(interaction, parsed_dict)` with parsed values.
    - Submitting an invalid ability string (only 5 scores) causes the callback to receive an error path: `on_submit_cb` is called with `{"_validation_error": "Expected 6 ability scores"}` (so the cog can re-open the modal or surface an ephemeral warning). **Decision**: validation happens in the cog after submit, not inside the modal — keeps modal pure. So the modal passes the raw string through and the cog handles parse failures.

    CharacterEntryModal tests:
    - Same 5-component layout, but with empty/placeholder defaults intended for "type from scratch".
    - Inherits or shares the parse helper.
  </behavior>
  <action>
    Implement `src/eldritch_dm/bot/modals.py`:

    - Constants: `MODAL_TITLE_REVIEW = "Confirm Character"`, `MODAL_TITLE_ENTRY = "Enter Character"`.
    - `def parse_abilities_field(s: str) -> AbilityScores` — exact body from the &lt;interfaces&gt; block; raises ValueError with descriptive messages.
    - `def serialize_abilities(a: AbilityScores) -> str` — `f"{a.strength} {a.dexterity} {a.constitution} {a.intelligence} {a.wisdom} {a.charisma}"`.
    - `class CharacterReviewModal(discord.ui.Modal)` per RESEARCH "Modal with Permission Check + Confidence Routing":
      - `__init__(self, prefill: dict[str, Any], *, on_submit_cb: Callable)` — assigns the 5 TextInputs as instance attributes and `self.add_item(...)` each in order: name, character_class, class_level, race, abilities_str.
      - Use `discord.TextStyle.short` for all fields (no multiline; saves the 4000-char budget).
      - `async def on_submit(self, interaction)`: defers ephemeral+thinking; collects raw values into a dict (do NOT pre-validate ability string — pass through); calls `await self._on_submit_cb(interaction, raw_dict)`.
    - `class CharacterEntryModal(discord.ui.Modal)`: same structure, different title + empty/placeholder defaults.
    - `class OptionalFieldsModal(discord.ui.Modal)`: 5 fields — subclass, background, skills (comma-list), spells (comma-list), alignment. Same callback pattern. **DEFER**: only exposed if the cog wires a "Refine" button — DOCUMENTED in Task 3 SUMMARY but no required wiring in Phase 3 (Phase 4 / v2 enhancement).
    - **5-component hard cap assertion**: each modal class has `__init_subclass__` or constructor-time `assert len(self.children) <= 5, "Modal exceeds Discord 5-component cap"` to fail fast if someone adds a 6th TextInput by accident (RESEARCH §5 pitfall).

    Tests in `tests/bot/test_modals.py`: ≥10 tests covering the behavior block. Use `discord.Interaction = AsyncMock(spec=discord.Interaction)`. Validate `modal.children` length, default values, and that `on_submit` calls the callback with the expected raw_dict.

    Implements INGEST-08 (review modal), INGEST-09 (entry modal — opened on low confidence by Task 3).
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/bot/test_modals.py -x -q 2&gt;&amp;1 | tail -20</automated>
  </verify>
  <done>modals.py contains both modal classes + parse/serialize helpers; ≥10 modal tests pass; 5-component assertion fires in a deliberate "add 6th item" test; modal classes have NO imports from cogs/ingest.py (testable in isolation).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: IngestCog with /upload_character_url, /upload_character_file, /upload_character_manual — confidence routing + permission + lobby update</name>
  <files>src/eldritch_dm/bot/cogs/ingest.py, src/eldritch_dm/bot/bot.py, src/eldritch_dm/bot/embeds.py, tests/bot/cogs/test_ingest.py</files>
  <behavior>
    /upload_character_url tests:
    - Defer is the first await (ephemeral=True).
    - Calls `dm20__import_from_dndbeyond(url_or_id=url, player_name=player_name or interaction.user.display_name)`.
    - Passes `player_id=str(interaction.user.id)` to dm20 alongside the import (D-13). **Verify**: ddmcpskills.md says import_from_dndbeyond accepts url_or_id + player_name. If player_id is NOT a parameter, we follow up with `update_character` to set player_id. Add a defensive follow-up call: after import, the cog calls `update_character(self.mcp, campaign_name=..., character_id=imported.character_id, updates={"player_id": str(interaction.user.id)})`.
    - On dm20 error (e.g., 404 DDB URL), replies ephemeral "❌ Could not import from D&D Beyond: {reason}".
    - On success, edits the lobby embed (looked up via channel_sessions → message_id from persistent_views) to add "✅ {char_name} ({class}, lvl {N}) joined". Use a new `lobby_embed_with_joined_member` helper in embeds.py — see embed updates below.
    - Permission: only the invoking user or DM (manage_channels) can run — but URL upload defaults to "the invoking user is uploading their own character", so the gate is effectively pass-through.

    /upload_character_file tests:
    - Defer is the first await.
    - Permission check: `can_act_on_character(interaction, character_player_id=str(interaction.user.id))` — passes for own upload. For uploads on behalf of another player, the DM (manage_channels) is required.
    - Oversize: attachment.size > 10 MB → ephemeral "❌ File exceeds 10 MB limit" + NO call to attachment.read().
    - Wrong format (txt/exe etc.): magic-byte sniff fails → ephemeral "❌ Unsupported file format (PNG, JPEG, PDF only)".
    - Happy path with confidence ≥ 0.6: routes to `ingest()`, then `interaction.followup.send` with the `CharacterReviewModal` (NOT `send_modal` — modal opens via a *button* in an ephemeral message because send_modal can only be called once on the original interaction, and we've already deferred). **Architectural pivot**: since we deferred at the start, we cannot send a modal as the followup. The pattern is: defer → run ingest → followup with an ephemeral message containing a "Review & Confirm" button → button click opens the modal. This is the discord.py-correct flow. Tests assert this 2-step flow.
    - Confidence < 0.6: same 2-step flow but the button label is "Enter Character Manually" and opens CharacterEntryModal.
    - Modal submit callback: parses abilities, validates via `parse_abilities_field`, on success calls `dm20__create_character` with player_id, on failure re-opens an ephemeral with "❌ {validation error} — please re-enter".
    - End-to-end timing assertion (mocked): the cog completes the ingest call within 8s (INGEST-11). Use `time.monotonic()` bracket in the test with mocked ingest returning immediately.

    /upload_character_manual tests:
    - Defer ephemeral first.
    - Posts an ephemeral with a "Enter Character" button that opens `CharacterEntryModal` (same pattern as low-confidence file flow).
    - No OCR/PDF/translate calls happen — purely manual.

    embeds.py extension test:
    - `lobby_embed_with_joined_member(...)` — same signature as `lobby_embed` but accepts an extra `recently_joined: list[str]` rendered as a separate "Recently joined" field. Backward compat: existing `lobby_embed` callers unchanged.
  </behavior>
  <action>
    Implement `src/eldritch_dm/bot/cogs/ingest.py`:

    - Class `IngestCog(commands.Cog)` with constructor `(bot, *, mcp, channel_sessions, persistent_views, settings, logger, openai_client)`.
    - Module-level constant `MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024`.

    - `@app_commands.command(name="upload_character_url", description="Import from D&D Beyond URL")` with `url: str, player_name: str | None = None`:
      1. `await interaction.response.defer(thinking=True, ephemeral=True)`.
      2. Bind logger with `url=url[:60], user_id=interaction.user.id`.
      3. Look up channel_sessions row; ephemeral "❌ No active campaign — run /start_game first" if missing.
      4. Call `import_from_dndbeyond(self.mcp, url_or_id=url, player_name=player_name or interaction.user.display_name)`.
      5. On success, extract `character_id` from response (defensive `.get("character_id") or .get("name")`); call `update_character` with `updates={"player_id": str(interaction.user.id)}`.
      6. Update lobby embed via `lobby_message.edit(embed=lobby_embed_with_joined_member(...))` — look up the lobby message via persistent_views_repo for the LobbyView or by message_id stored in channel_sessions (verify what Plan 01 stored — if no lobby_message_id is stored, add one as a small migration: append a `lobby_message_id` key to the `dm20_party_token` JSON in channel_sessions; document in SUMMARY).
      7. Ephemeral followup "✅ Imported {char_name}".

    - `@app_commands.command(name="upload_character_file", description="Upload a character sheet (PNG/JPG/PDF)")` with `attachment: discord.Attachment, player_name: str | None = None`:
      1. Defer ephemeral.
      2. Permission check: `can_act_on_character(interaction, character_player_id=str(interaction.user.id))` — pass for own upload; for `player_name` override, require manage_channels.
      3. Size check on `attachment.size` against MAX_ATTACHMENT_BYTES — early ephemeral return.
      4. `data = await attachment.read()`.
      5. Magic-byte sniff: PNG/JPEG → "image", PDF → "pdf", else ephemeral "❌ Unsupported file format".
      6. `result = await ingest(data, content_type=attachment.content_type, filename=attachment.filename, player_name=player_name or interaction.user.display_name, user_id=str(interaction.user.id), openai_client=self.openai, mcp_client=self.mcp)`.
      7. Build ephemeral with a button (`discord.ui.Button` with custom_id `f"review_char:{channel_id}:{user_id}"` or similar non-persistent label; we don't need DynamicItem registration because the button is short-lived).
         - If `result.confidence_score >= 0.6`: label "Review & Confirm" → opens CharacterReviewModal.
         - Else: label "Enter Character Manually" → opens CharacterEntryModal.
      8. Modal callback `_on_character_submit(interaction, raw_dict)`:
         - Parse abilities via `parse_abilities_field(raw_dict["abilities_str"])`; on ValueError, ephemeral "❌ {err} — please re-enter" + early return.
         - Construct `CharacterSheet` via pydantic validate; on error, ephemeral "❌ Validation failed: {warnings}".
         - Call `create_character(self.mcp, campaign_name=session.campaign_name, character={**sheet.model_dump(), "player_id": str(interaction.user.id), "player_name": player_name or interaction.user.display_name})`.
         - On success, edit lobby embed with `lobby_embed_with_joined_member` patch, ephemeral "✅ {char_name} joined".

    - `@app_commands.command(name="upload_character_manual", description="Enter a character sheet manually")` — defers, posts ephemeral with "Enter Character" button → opens CharacterEntryModal with empty defaults. Reuses the same `_on_character_submit` callback.

    - Wire `IngestCog` into `bot/bot.py` `_load_cogs` AFTER `LobbyCog` (LobbyCog establishes channel_sessions; ingest cog consumes it).

    - Add `openai_client: AsyncOpenAI` to the bot constructor if not present from Plan 02 — construct it lazily from `settings.OMLX_ENDPOINT` (default `http://localhost:8765/v1`) and pass to both Plan 02 (ingest) and Plan 03 (cog).

    - Extend `embeds.py` with `lobby_embed_with_joined_member(*, campaign_name, players, server_url=None, party_invite=None, recently_joined: list[str] | None = None) -> discord.Embed`. If `recently_joined` is non-empty, add a "Recently joined" embed field listing them. Existing `lobby_embed` callers unchanged.

    Tests in `tests/bot/cogs/test_ingest.py` (≥15 tests):
    - /upload_character_url happy path (assert dm20 call order: import_from_dndbeyond → update_character).
    - /upload_character_url no-active-campaign.
    - /upload_character_url dm20 error path.
    - /upload_character_file oversize rejection (size > 10 MB, NO .read() called — assert via spy).
    - /upload_character_file wrong format (sniff fails).
    - /upload_character_file confidence ≥ 0.6 → CharacterReviewModal flow (assert button is sent, click opens modal, submit triggers create_character).
    - /upload_character_file confidence < 0.6 → CharacterEntryModal flow.
    - /upload_character_file modal-submit with invalid ability string → ephemeral error path.
    - /upload_character_file modal-submit with valid input → dm20__create_character called with player_id.
    - /upload_character_file permission denied (other player's upload, not DM).
    - /upload_character_manual happy path (no OCR, direct entry modal).
    - lobby embed update test: edit() called with `lobby_embed_with_joined_member` that includes the new character.
    - End-to-end <8s timing assertion (mocked).
    - INGEST-10 ephemeral assertion: every cog reply uses `ephemeral=True`.
    - INGEST-11 8s budget assertion: ingest() is called once and the cog awaits it without additional MCP calls in the hot path.

    Implements INGEST-01, INGEST-02, INGEST-08, INGEST-09, INGEST-10, INGEST-11.
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/bot/cogs/test_ingest.py tests/bot/test_embeds.py -x -q 2&gt;&amp;1 | tail -30 &amp;&amp; lint-imports 2&gt;&amp;1 | tail -10</automated>
  </verify>
  <done>cogs/ingest.py ≥250 lines, three slash commands all defer-first, MAX_ATTACHMENT_BYTES enforced, magic-byte sniff before .read() routing, confidence routing to correct modal, dm20__create_character called with player_id, ≥15 ingest tests pass, lint-imports green, lobby_embed_with_joined_member added with backward-compat signature.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Phase 3 integration smoke test — /start_game → /upload_character_file → ReadyButton → EXPLORATION</name>
  <files>tests/integration/test_phase3_smoke.py</files>
  <behavior>
    Phase 3 smoke test:
    - Builds an `EldritchBot` instance with all deps as AsyncMock/respx mocks (MCPClient → respx, openai client → respx, channel_sessions + persistent_views → real in-memory SQLite).
    - Exercises the full happy path:
      1. Invoke `/start_game name="Pilot"` — assert channel_sessions row created in LOBBY state.
      2. Invoke `/upload_character_file` with a fake PNG fixture — assert ingest() called, modal flow simulated by directly calling the modal's `on_submit` with a valid raw_dict, assert `dm20__create_character` invoked with player_id.
      3. Invoke ReadyButton.callback for the same user — assert persistent_views row updated with `ready_user_ids=[user_id]`.
      4. Since the user is the only roster member (list_characters returns 1), assert channel_sessions transitions to EXPLORATION + `dm20__player_action(action='party_ready', context='lobby_complete')` was called.
    - Total test runtime <2s (use AsyncMock/respx, no real I/O).
    - Logs INFO-level lifecycle events ("phase3_smoke_start_game_ok", "phase3_smoke_upload_ok", "phase3_smoke_ready_transition_ok") for ops visibility.
    - This is the end-to-end gate for Phase 3 — if it passes, Phase 3 is functionally complete.
  </behavior>
  <action>
    Create `tests/integration/test_phase3_smoke.py` modeled on `tests/integration/test_phase1_smoke.py`:

    - Use the existing `settings_factory` fixture from `tests/conftest.py` for a fresh in-memory SQLite per test.
    - Construct `MCPClient` with a respx-mocked HTTP transport; register canned responses for: `dm20__create_campaign`, `dm20__start_claudmaster_session` (returns dict with `session_id`), `dm20__start_party_mode` (returns the canonical RESEARCH §1 markdown), `dm20__list_characters` (returns list with one character whose `player_id` matches the test user), `dm20__create_character`, `dm20__update_character`, `dm20__get_class_info`, `dm20__get_race_info`, `dm20__player_action`.
    - Mock the openai client with respx for `POST /v1/chat/completions` returning a valid CharacterSheet JSON.
    - Mock `ingest.ocr.run_ocrmac` to return `("Aragorn / Ranger / Level 5 / STR 15 DEX 18 CON 14 INT 12 WIS 10 CHA 8", 0.92)`.
    - Drive the cogs by invoking their command callbacks directly with AsyncMock interactions (this matches the Phase 1+2 test pattern; we are NOT running a live Discord connection — the bot's command tree dispatch is bypassed).
    - Assert the four-step happy path completes in <2s, with all expected MCP calls in the correct order.

    Implements the phase-level success criteria #1-#6 from ROADMAP.md.
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/integration/test_phase3_smoke.py -x -v 2&gt;&amp;1 | tail -20</automated>
  </verify>
  <done>Phase 3 smoke test passes in <2s; covers all four happy-path steps; ROADMAP Phase 3 success criteria 1-6 are demonstrated end-to-end with mocked externals.</done>
</task>

<task type="auto">
  <name>Task 5: Final test sweep + ruff + lint-imports + Phase 3 closure (SUMMARY + REQUIREMENTS check-offs + ROADMAP + STATE)</name>
  <files>.planning/phases/03-lobby-character-ingest/03-SUMMARY.md, .planning/REQUIREMENTS.md, .planning/ROADMAP.md, .planning/STATE.md</files>
  <action>
    1. Run the full chain:
       - `ruff check src tests` — must be clean.
       - `lint-imports` — all contracts green, including the "ingest must not import bot or persistence" contract.
       - `pytest -x -q` — full suite green; expect ≥285 tests passing (270 from Plans 01+02 + ≥15 from Plan 03).
       - `grep -c "phase2_stub" src/eldritch_dm/bot/dynamic_items.py` returns 3 (ReadyButton stub gone, three remaining stubs are Phase 4/5 work).

    2. Write `.planning/phases/03-lobby-character-ingest/03-SUMMARY.md` following the template at `$HOME/.claude/get-shit-done/templates/summary.md`. Include:
       - **Deliverables**: 3 new modules (qr.py, modals.py, cogs/ingest.py), 3 new MCP wrappers (Plan 01: list_characters, get_class_info, get_race_info, player_action, get_party_status, load_adventure), 1 wrapper relocation (translate_character_sheet — see Plan 02 deviation), 7 ingest module files, segno + reportlab dep additions, ReadyButton.callback real implementation, EXPLORATION transition wired, 3 slash commands, 3 modal classes.
       - **Test counts**: baseline 235 → final ≥285 (+50 across Plans 01, 02, 03).
       - **Deferred items** (carried from CONTEXT): D&D Beyond JSON file import, OptionalFieldsModal wiring (modal exists but no entry point until Phase 4/v2), character sheet sync, multi-character ingest from single PDF, non-English OCR, bulk import, auto-resolve homebrew classes.
       - **Plan 02 deviation**: `translate_character_sheet` lives in `ingest/translate.py` not `mcp/tools.py` (import-linter contract).
       - **load_adventure non-idempotency mitigation** (RESEARCH §3 TOP risk): `module_bound` tracker in `dm20_party_token` JSON; populate_chapter_1=False on retry.
       - **Phase 4 handoff notes**:
         * channel_sessions.state is now LOBBY → EXPLORATION machine; Phase 4 reads EXPLORATION and renders room_embed.
         * persistent_views.payload_json `ready_user_ids` schema documented for restart-survival; Phase 4 can build similar payload schemas for its declare/endturn buttons.
         * `dm20_party_token` JSON shape stabilized: `{"server_url", "members", "module_bound", "lobby_message_id"}`.
         * Player ↔ character mapping is in place via dm20's `player_id` field — Phase 4 turn gatekeeping uses `interaction.user.id == character.player_id`.

    3. Update `.planning/REQUIREMENTS.md`:
       - LOBBY-01 [x] (Plan 01)
       - LOBBY-02 [x] (Plan 01)
       - LOBBY-03 [x] (Plans 01 + 03)
       - LOBBY-04 [x] (Plan 01)
       - INGEST-01 [x] (Plan 03)
       - INGEST-02 [x] (Plan 03)
       - INGEST-03 [x] (Plan 02)
       - INGEST-04 [x] (Plan 02)
       - INGEST-05 [x] (Plan 02)
       - INGEST-06 [x] (Plan 02)
       - INGEST-07 [x] (Plan 02)
       - INGEST-08 [x] (Plan 03)
       - INGEST-09 [x] (Plan 03)
       - INGEST-10 [x] (Plan 03)
       - INGEST-11 [x] (Plan 03)
       - Update the Traceability table footer counts.

    4. Update `.planning/ROADMAP.md`:
       - Phase 3 header: `- [x] **Phase 3: Lobby + Character Ingest** — ...`
       - Plans list:
         * `- [x] 01-PLAN-lobby-and-cogs.md — Lobby cog + ReadyButton wiring`
         * `- [x] 02-PLAN-ingest-pipeline.md — Character ingest module`
         * `- [x] 03-PLAN-ingest-cogs-and-modals.md — Ingest cog + modals + Phase 3 closure`

    5. Update `.planning/STATE.md`:
       - `completed_phases: [1, 2, 3]` (or however STATE.md tracks it — read first).
       - `current_phase: "04-gameplay-exploration-combat"`.
       - Append a "Phase 3 complete" entry to the timeline / decisions log.

    Atomic commit message: `docs(03-lobby-character-ingest): phase 3 complete — summary, requirements check-offs, roadmap closure, state update`.

    Closes Phase 3 fully.
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; ruff check src tests &amp;&amp; lint-imports &amp;&amp; pytest -x -q 2&gt;&amp;1 | tail -6 &amp;&amp; grep -c '^- \[x\] \*\*Phase 3' .planning/ROADMAP.md</automated>
  </verify>
  <done>Full pytest suite reports ≥285 passing; ruff clean; lint-imports green; 03-SUMMARY.md written with deliverables/test counts/deferred/handoff sections; REQUIREMENTS.md has LOBBY-01..04 + INGEST-01..11 all marked [x]; ROADMAP.md Phase 3 marked [x] with all three plans checked; STATE.md advanced to phase 4.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Discord attachment → bot.cogs.ingest | Untrusted file payload; size, format, content all hostile |
| Discord modal submission → cog.on_submit | Untrusted player-typed text (ability scores, name, class) |
| URL string in /upload_character_url → dm20 | dm20 fetches the URL; SSRF risk delegated to dm20 (we don't fetch ourselves) |
| dm20 import response → bot | Trusted local source but malformed responses possible |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-14 | Denial of Service | Player uploads 25 MB attachment | mitigate | MAX_ATTACHMENT_BYTES = 10 MB enforced BEFORE attachment.read() (RESEARCH §6) |
| T-03-15 | Spoofing | Attacker sets `content_type=image/png` on actual PDF or .exe | mitigate | Magic-byte sniff after .read() (RESEARCH §5 Pitfall 5); reject unknown bytes |
| T-03-16 | Elevation of Privilege | Player runs /upload_character_file with player_name="OtherPlayer" to inject a fake character | mitigate | can_act_on_character — only manage_channels users can override player_name (D-29) |
| T-03-17 | Tampering | Modal injection — player types `<player_action>...</player_action>` inside the Name field | mitigate | All modal fields pass through sanitize_player_input before any LLM call (SAN-01) |
| T-03-18 | Tampering | Ability score 30 (valid pydantic) but rules-illegal (e.g., level 1 PC) | accept | Pydantic accepts ge=1, le=30 per D-24; dm20's rules engine is the final arbiter, not us |
| T-03-19 | Information Disclosure | Validation warnings echoed back to player leak schema internals (field names) | accept | Pydantic field names are part of the documented API; not sensitive |
| T-03-20 | DoS | Modal callback creates_character blocks for 10s on slow dm20 | accept | dm20 is local; if it's slow, the whole bot is slow. Discord's 15-min followup window covers this. |
| T-03-SC | Tampering | npm/pip install of any new dep | N/A | No new deps in Plan 03 — segno (Plan 01) and reportlab (Plan 02) already audited and added. |
</threat_model>

<verification>
- `pytest tests/bot/test_qr.py tests/bot/test_modals.py tests/bot/cogs/test_ingest.py tests/integration/test_phase3_smoke.py -x` passes (≥30 new tests)
- `pytest -x` (full suite) passes (≥285 tests)
- `ruff check src tests` clean
- `lint-imports` green
- `grep -c "phase2_stub" src/eldritch_dm/bot/dynamic_items.py` returns 3 (ReadyButton no longer stub; 3 remaining are Phase 4/5)
- `.planning/REQUIREMENTS.md` has LOBBY-01..04 + INGEST-01..11 all `[x]`
- `.planning/ROADMAP.md` Phase 3 header `- [x]` + all 3 plans `- [x]`
- `.planning/STATE.md` current_phase advanced to `04-gameplay-exploration-combat`

## Source artifact coverage
- D-06: /upload_character_url with player_name default ✓ (Task 3)
- D-07: /upload_character_file with content-type+magic-byte routing ✓ (Task 3)
- D-08: /upload_character_manual direct entry modal ✓ (Task 3)
- D-26..D-28: Confidence routing to review vs entry modal ✓ (Task 3)
- D-29: Permission gate ✓ (Task 3, uses Plan 01's permissions.py)
- D-30: Ephemeral confirmations + non-ephemeral lobby update ✓ (Task 3, embeds.py)
- D-31: <8s ingest budget ✓ (Task 3 timing test; full smoke <2s mocked)
- D-32..D-36: Test strategy honored (Pillow/reportlab fixtures, mocked OCR, respx oMLX, AsyncMock modals) ✓ (Plan 02 + Plan 03)
- D-37: Structlog binding contract on cog ✓ (Task 3)
- RESEARCH §5 (5-component cap): hard assertion in modal constructors ✓ (Task 2)
- RESEARCH §6 (10 MB cap): MAX_ATTACHMENT_BYTES enforced pre-read ✓ (Task 3)
- RESEARCH §11 (segno): bot/qr.py extracted ✓ (Task 1)
</verification>

<success_criteria>
1. Three slash commands (`/upload_character_url`, `/upload_character_file`, `/upload_character_manual`) defer first, gate by permission, route by confidence.
2. Modals respect Discord's 5-component hard cap; ability scores packed into single space-separated field per RESEARCH §5.
3. Attachment size cap (10 MB) enforced BEFORE `attachment.read()`; magic-byte sniff routes by content, not by Discord-supplied content_type.
4. `dm20__create_character` called with `player_id=str(interaction.user.id)` so Phase 4 combat can map back to Discord users.
5. Lobby embed updates non-ephemerally on successful character commit ("✅ Aragorn (ranger, lvl 5) joined").
6. `bot/qr.py` extracted from Plan 01's inline helper; lobby.py refactored to use it.
7. Phase 3 integration smoke test passes in <2s — exercises start_game → upload → ready → EXPLORATION.
8. ≥30 new tests pass; full suite ≥285 tests green.
9. Phase 3 fully closed: SUMMARY written, all requirements `[x]`, ROADMAP Phase 3 `[x]`, STATE advanced to phase 4.
</success_criteria>

<risks>
- **Defer + send_modal conflict.** Discord's modal API requires `interaction.response.send_modal(...)` as the FIRST response, not a followup. The cog defers first (BOT-02 lint), so a modal cannot open on the deferred interaction. Mitigation: 2-step flow — defer → followup with an ephemeral button → button click is a fresh interaction → button click opens the modal. Acceptance: Task 3 tests this explicitly with two interaction objects.
- **Lobby message lookup for embed updates.** Plan 01 stores the lobby message_id in persistent_views; the ingest cog needs to find it. Mitigation: Task 3 adds `lobby_message_id` to `dm20_party_token` JSON for direct lookup. Acceptance: cog test mocks the JSON and verifies edit() is called on the right message.
- **dm20__create_character schema unknowns.** ddmcpskills.md documents the call but the exact `player_id` field name is unverified. Mitigation: cog passes both `player_id` and `player_name`; if dm20 ignores one, the other persists. Acceptance: integration smoke asserts the call includes both keys.
- **OptionalFieldsModal not wired in Phase 3.** Modal class exists but no UI surface opens it. Documented as v2 / Phase 4 follow-up. Acceptance: SUMMARY's Deferred Items section calls this out explicitly.
- **Modal validation re-prompt UX.** If the player submits an invalid ability string, the cog can only send an ephemeral error — Discord doesn't allow re-opening the same modal. Mitigation: error message includes a "Try /upload_character_manual again" hint. Acceptance: a test verifies the ephemeral message is sent with the hint.
</risks>

<dependencies>
- **Plan 01 (03-01)** — provides MCP wrappers (`import_from_dndbeyond`, `create_character`, `update_character`, `list_characters`), permission helper (`can_act_on_character`), embed extension hooks, bot attribute exposure.
- **Plan 02 (03-02)** — provides `ingest()` pipeline, `CharacterSheet` model, `IngestResult` dataclass, openai client wiring path.
- External: no new packages (segno + reportlab already added by prior plans).
</dependencies>

<output>
Create `.planning/phases/03-lobby-character-ingest/03-SUMMARY.md` (Task 5 produces this) — the canonical Phase 3 retrospective consumed by Phase 4's planning.
Also commit updates to `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md` per Task 5.
</output>
