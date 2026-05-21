# Phase 3: Lobby + Character Ingest - Context

**Gathered:** 2026-05-21
**Status:** Ready for research + planning
**Mode:** Synthesized from REQUIREMENTS (LOBBY-01..04, INGEST-01..11) + Phase 1 & 2 deliverables + ddmcpskills.md

<domain>
## Phase Boundary

The first user-visible gameplay surface. After this phase:

1. **`/start_game`** in a Discord channel spins up a dm20 campaign + Claudmaster session + Party Mode server, records the trio in `channel_sessions`, posts a lobby embed with both a QR-code party-mode invite AND a Discord-native ready button
2. **`/load_adventure <id>`** loads a prebuilt 5etools adventure (CoS, LMoP, etc.) into the active campaign
3. **`/upload_character_url <ddb_url>`** imports a public D&D Beyond character in one MCP call
4. **`/upload_character_file`** ingests photo/PDF sheets through OCR (ocrmac on macOS, easyocr Linux fallback) + PyMuPDF (PDF), translates the extracted text to character schema via oMLX JSON mode, surfaces a manual-review modal, and persists via `dm20__create_character` / `update_character`
5. **Manual-entry modal** is a first-class fallback path when OCR confidence is low
6. **All-ready button** transitions the session from LOBBY to EXPLORATION and signals Claudmaster

ZERO combat logic. ZERO action declaration / narration loop. ZERO MCP tool registry expansion beyond what Phase 1's `tools.py` already exposes. The session enters EXPLORATION but no exploration UI exists yet — Phase 4 ships that.

</domain>

<decisions>
## Implementation Decisions

### Cog organization
- **D-01:** Two new cogs in `src/eldritch_dm/bot/cogs/`:
  - `lobby.py` — `/start_game`, `/load_adventure`, ready button callback, EXPLORATION transition
  - `ingest.py` — `/upload_character_url`, `/upload_character_file`, OCR/PDF pipeline, manual-review modal, manual-entry modal
- **D-02:** Cogs are loaded by `EldritchBot.setup_hook` after diagnostics — append to existing `_load_cogs` helper
- **D-03:** Each cog takes `mcp_client`, `persistence`, `settings`, `logger` via constructor — testable in isolation

### Slash command surface
- **D-04:** `/start_game name:str description:str=None` — required: campaign name; optional: short description/tagline. Defer-first, then call `dm20__create_campaign` → `start_claudmaster_session` → `start_party_mode` in sequence. On any failure, rollback (best-effort: end_claudmaster_session if it succeeded, stop_party_mode if it succeeded). Record the trio in `channel_sessions` only after all three MCP calls succeed.
- **D-05:** `/load_adventure adventure_id:str campaign_name:str=None` — fast path: `dm20__load_adventure(adventure_id, populate_chapter_1=True)`. If no active campaign in channel, error ephemeral. Provides a curated autocomplete list of common adventure IDs (CoS, LMoP, HotDQ, PotA, OotA, ToA, WDH, WDMM, BGDIA).
- **D-06:** `/upload_character_url url:str player_name:str=None` — `dm20__import_from_dndbeyond(url_or_id, player_name)`. Player_name defaults to interaction.user.display_name.
- **D-07:** `/upload_character_file attachment:Attachment player_name:str=None` — accepts PNG/JPG/PDF; routes to OCR or PDF pipeline based on content-type / extension.
- **D-08:** `/upload_character_manual` (NEW — not in original REQUIREMENTS but implied by INGEST-09) — opens the manual-entry modal directly without OCR. Useful when player knows OCR will fail (handwritten, glare, etc.).

### Lobby flow
- **D-09:** `lobby_embed` rendered with: campaign name, Claudmaster session id (short), party-mode invite URL + QR-code image, current player list with ready states, "Ready" button (DynamicItem `ReadyButton`, custom_id `ready:{channel_id}`), and a footer hinting at next steps
- **D-10:** QR code: generate from party-mode invite URL using `qrcode>=7.4,<9.0` (Python lib, no native deps) — output as PNG bytes, attached to the embed via `discord.File`
- **D-11:** `ReadyButton.callback` (now real, was stub in Phase 2):
  1. Defer ephemeral
  2. Get current `ChannelSessionRow` from repo
  3. Read the per-player ready state from `payload_json` on the persistent_view row OR a small in-memory dict keyed by channel (decision: use persistent_view payload_json for restart survival)
  4. Mark interaction.user as ready
  5. List all characters in the campaign via `dm20__list_characters` — if every character.player_id has clicked ready → transition
  6. Update `channel_sessions.state = 'EXPLORATION'`
  7. Update the lobby embed (mark "All ready! Entering EXPLORATION…")
  8. Signal Claudmaster via `dm20__player_action(session_id, action="party_ready", context="lobby_complete")` (placeholder; Phase 4 may use a different trigger if Claudmaster has a dedicated method)
- **D-12:** Ready state survives restart because it lives in `persistent_views.payload_json`. On bot restart, `setup_hook` rebuilds the view; callback reads the same row.
- **D-13:** Player-to-character mapping: when a character is created (via /upload_character_url, /upload_character_file, or /upload_character_manual), we attach `player_id = str(interaction.user.id)` to the dm20 character. The ready button only counts users whose Discord ID matches a character.player_id in this campaign.

### Adventure loading
- **D-14:** `/load_adventure` is idempotent at the dm20 level (it binds a module to the current campaign; running twice with the same ID may be a no-op or may reset Chapter 1 — verify with dm20 docs, document outcome).
- **D-15:** Adventure ID autocomplete from a hard-coded `ADVENTURE_IDS: dict[str, str]` mapping ID → display name. NOT generated dynamically from `dm20__discover_adventures` (would cost an MCP call per keystroke) — but `/load_adventure --search <kw>` v2 could.

### Character ingest — the OCR pipeline
- **D-16:** Pipeline shape (all stages async):
  ```
  Attachment → bytes → OCR/PDF extract (in executor) → raw text
              → oMLX JSON mode translate → parsed character dict
              → validate (Pydantic + range checks) → confidence score
              → modal preview (manual-review or manual-entry depending on confidence)
              → user submits → dm20__create_character (or update_character if exists)
              → confirmation embed
  ```
- **D-17:** OCR backend selection:
  - macOS + `ocrmac` available → use it (preferred)
  - otherwise → `easyocr` if installed (linux-ocr extra)
  - otherwise → ephemeral error "OCR backend not installed; install ocrmac (macOS) or easyocr (Linux)"
- **D-18:** PDF detection: by content-type `application/pdf` OR extension `.pdf`. Pipeline: PyMuPDF first; on `Exception` fall back to pypdf.
- **D-19:** OCR/PDF work runs in `ThreadPoolExecutor(max_workers=2)` (already established in PROJECT.md). Pool is process-wide, owned by a new `IngestExecutor` singleton in `src/eldritch_dm/ingest/`.
- **D-20:** Module layout for ingest work:
  ```
  src/eldritch_dm/ingest/
    __init__.py
    pipeline.py          # high-level ingest() coroutine
    ocr.py               # ocrmac + easyocr backends
    pdf.py               # PyMuPDF + pypdf
    translate.py         # oMLX JSON-mode call → CharacterSheet pydantic model
    schema.py            # CharacterSheet, AbilityScores pydantic models with validators
    executor.py          # IngestExecutor (ThreadPoolExecutor singleton)
  tests/ingest/
    test_ocr.py
    test_pdf.py
    test_translate.py
    test_schema.py
    test_pipeline.py     # full pipeline with fixtures
    fixtures/
      sample_sheet.png   # tiny test image (or git-LFS / generated)
      sample_sheet.pdf
  ```
- **D-21:** `bot/` imports `ingest/`. `ingest/` imports `mcp/`, `safety/` (sanitize OCR text before sending to oMLX), `persistence/` (no — actually ingest produces a dm20 character, no local DB write). Update import-linter contract to allow `bot → ingest` and `ingest → mcp, safety`.

### oMLX JSON-mode translation
- **D-22:** New typed wrapper in `mcp/tools.py`: `async def translate_character_sheet(raw_text: str, model: str = "ShoeGPT") -> dict[str, Any]`. Calls `/v1/chat/completions` with:
  - `response_format={"type": "json_object"}`
  - `temperature=0.05`
  - System prompt: "You are a strict data formatter. Extract character sheet fields from the messy OCR text below. Return ONLY a JSON object matching this schema: {schema}. Do not include conversational filler or markdown."
  - User content: the raw extracted text wrapped in `<player_action>` sentinels via the sanitizer (defense-in-depth — even though it's "OCR text not player text," the file came from the player so it's untrusted input)
- **D-23:** Schema embedded in the prompt is the JSON-schema string of `CharacterSheet` pydantic model — generated at import time.

### Character schema
- **D-24:** `CharacterSheet` pydantic model — frozen, strict:
  ```python
  class AbilityScores(BaseModel):
      strength: int = Field(ge=1, le=30)
      dexterity: int = Field(ge=1, le=30)
      constitution: int = Field(ge=1, le=30)
      intelligence: int = Field(ge=1, le=30)
      wisdom: int = Field(ge=1, le=30)
      charisma: int = Field(ge=1, le=30)

  class CharacterSheet(BaseModel):
      name: str
      character_class: str
      class_level: int = Field(ge=1, le=20)
      race: str
      subclass: str | None = None
      subrace: str | None = None
      background: str | None = None
      alignment: str | None = None
      abilities: AbilityScores
      # Optional fields the LLM may or may not extract
      hp: int | None = Field(default=None, ge=1)
      ac: int | None = Field(default=None, ge=1)
      skills: list[str] = Field(default_factory=list)
      weapons: list[dict[str, Any]] = Field(default_factory=list)
      spells: list[str] = Field(default_factory=list)
  ```
- **D-25:** Class / race verification: after pydantic validation, call `dm20__get_class_info(class_name=sheet.character_class)` and `dm20__get_race_info(race=sheet.race)` — if either returns "not found", mark the sheet as `validation_warnings` so the modal can surface "Class 'Witcher' not in 5e rules — proceed anyway?"

### Confidence scoring & modal routing
- **D-26:** Confidence score is a float [0.0, 1.0]:
  - +0.3 if OCR backend reports no warnings (ocrmac average confidence > 0.8; easyocr no fallback flags)
  - +0.3 if Pydantic validation passes with no warnings
  - +0.2 if class verification succeeds
  - +0.2 if race verification succeeds
- **D-27:** Threshold: `< 0.6` → automatically open manual-entry modal (player retypes ability scores from scratch, prefilled with whatever was extracted). `≥ 0.6` → open manual-review modal (player confirms or edits).
- **D-28:** Both modals are `discord.ui.Modal` with text inputs for name, class, level, race, and ability scores (6 fields). 25-component limit on a modal is fine for these fields. Optional fields (subclass, background, skills, spells) shown in a follow-up modal after primary fields confirmed — OR rendered as text in the confirmation embed and edited via a "Refine" button later.

### Permissions
- **D-29:** Uploads restricted to invoking player or the DM (channel admin). The "DM" is determined by Discord permission `manage_channels` on the invoking channel — same as Phase 5 will use for `/upload_character_file` mod gates. Other players see ephemeral "Only the uploading player or DM can do this".
- **D-30:** All confirmations are ephemeral. The non-ephemeral lobby embed updates to show "✅ Aragorn (ranger, lvl 5) joined" once a character is committed.

### Performance
- **D-31:** Ingest path budget: <8s end-to-end for standard sheets (INGEST-11). OCR ~1-2s, oMLX translation ~2-4s, dm20 character creation ~1s. Modal interaction time is excluded.

### Testing
- **D-32:** Tiny fixture images and PDFs for OCR/PDF tests (`tests/ingest/fixtures/`). Generated via `Pillow` (text-on-image) and `reportlab` (text-on-PDF) at test setup time — keeps fixtures < 10 KB each and reproducible.
- **D-33:** OCR tests use `unittest.mock` for `ocrmac.recognize` / `easyocr.Reader.readtext` — predictable string returns; we're not testing the OCR libs, we're testing our pipeline.
- **D-34:** oMLX translate tests use `respx` to mock the chat completions endpoint with canned JSON responses.
- **D-35:** Integration test: full pipeline (PNG → OCR mock → oMLX mock → CharacterSheet model → dm20 create mock → confirmation). Wired into the existing integration smoke from Phase 1.
- **D-36:** Modal tests use AsyncMock for `discord.Interaction.response.send_modal`.

### Logging
- **D-37:** Every ingest stage logs at INFO with bound context: `attachment_filename`, `bytes_size`, `ocr_backend`, `ocr_confidence`, `translation_model`, `pydantic_errors`, `dm20_character_id`. Failures log at WARNING + structured exception.

### Claude's Discretion
- Whether `qrcode` library or a CDN-based QR URL is used (qrcode is fine but adds a dep)
- Modal field ordering and labels (just be consistent with D&D character sheet conventions)
- Whether to use Discord application emoji for class icons (defer; Unicode is fine)
- Adventure ID autocomplete — static dict is fine for v1; dynamic fetch from `dm20__discover_adventures` is v2

</decisions>

<canonical_refs>
## Canonical References

### Phase scope
- `.planning/REQUIREMENTS.md` § Lobby (LOBBY-01..04), § Character Ingest (INGEST-01..11)
- `.planning/ROADMAP.md` § Phase 3 — goal + 6 success criteria

### Phase 1 & 2 deliverables (this phase consumes)
- `src/eldritch_dm/mcp/tools.py` — typed wrappers for `create_campaign`, `start_claudmaster_session`, `start_party_mode`, `load_adventure`, `import_from_dndbeyond`, `create_character`, `update_character`, `list_characters`, `get_class_info`, `get_race_info` (most exist; verify; add if missing)
- `src/eldritch_dm/persistence/channel_sessions_repo.py` — insert + update_state
- `src/eldritch_dm/persistence/persistent_views_repo.py` — upsert
- `src/eldritch_dm/safety/sanitizer.py` — sanitize OCR text before LLM
- `src/eldritch_dm/bot/embeds.py` — `lobby_embed`, `character_confirm_embed` (already shipped Phase 2; populate dynamic content)
- `src/eldritch_dm/bot/dynamic_items.py` — `ReadyButton` (callback was stub Phase 2; this phase makes it real)
- `src/eldritch_dm/bot/warnings.py` — `send_warning` helper
- `src/eldritch_dm/bot/bot.py` — `EldritchBot.setup_hook` cog loader (extend)

### MCP tool reference
- `ddmcpskills.md` § dm20 — `create_campaign`, `start_claudmaster_session`, `start_party_mode`, `load_adventure`, `import_from_dndbeyond`, `create_character`, `update_character`, `list_characters`, `get_class_info`, `get_race_info`, `validate_character_rules`, `player_action`

### External
- [discord.py 2.7.1 Modals + AppCommands](https://discordpy.readthedocs.io/en/v2.7.1/) — slash commands with autocomplete, Modal class, Attachment type, file handling
- [qrcode (Python)](https://pypi.org/project/qrcode/) — pure-Python QR generation
- [PyMuPDF docs](https://pymupdf.readthedocs.io/) — PDF text extraction
- [ocrmac](https://github.com/straussmaximilian/ocrmac) — Apple Vision wrapper
- [easyocr](https://github.com/JaidedAI/EasyOCR) — Linux fallback

</canonical_refs>

<code_context>
## Existing Code Insights

### Phase 1 + 2 delivered (interfaces this phase imports)
- 28 MCP tool wrappers in `mcp/tools.py` — most needed for Phase 3 already exist. Verify and add only if missing: `list_characters`, `get_class_info`, `get_race_info`, `validate_character_rules`, `player_action`.
- `EldritchBot` with cog loading pattern established in Phase 2
- `lobby_embed`, `character_confirm_embed` renderers — Phase 3 fills in dynamic content
- `ReadyButton` DynamicItem — Phase 2 had a stub callback; Phase 3 replaces with real logic
- `sanitize_player_input` for OCR-text pass-through (defense-in-depth)
- `ChannelSessionRepo`, `PersistentViewRepo` writes through WriterQueue
- Adventure IDs from `dm20__discover_adventures` documentation in `ddmcpskills.md` (CoS, LMoP, HotDQ, PotA, OotA, ToA, WDH, WDMM, BGDIA)

### Reusable Assets
- `Settings` env loader (no new env vars needed in Phase 3 unless OCR backend selection becomes env-driven)
- `structlog` setup with bound context — Phase 3 binds `attachment_filename`, `dm20_character_id` etc.
- `tests/conftest.py` settings_factory fixture
- `tests/integration/test_phase1_smoke.py` — extend in Phase 3

### Integration Points
- Phase 4 (Exploration) reads `channel_sessions.state == 'EXPLORATION'` and assumes characters exist → Phase 3 sets both up
- Phase 4 uses the same Party Mode session_id we stored in `channel_sessions` (from `start_party_mode` response — note: the response shape per ddmcpskills.md is invite URLs + QR file paths, not a session id directly. Verify what dm20 actually returns and what we need to store.)
- Phase 5 (Riposte) uses character_id from dm20 — we ensure player_id is set when creating characters so combat can map back to Discord users

</code_context>

<specifics>
## Specific Ideas

- The lobby experience is the first thing a new user sees — make it feel polished. The QR code + persistent ready button + clear "what to do next" copy in the embed footer matter for retention.
- OCR for handwritten / glare-affected sheets WILL be unreliable. Don't make players hate the bot when OCR fails — manual-entry modal should be 30 seconds and feel like a thoughtful fallback, not a punishment.
- `dm20__load_adventure` is huge value-add — Phase 3 unlocks ALL the official prebuilt adventures. Lean into this in copy.
- Confirm what `dm20__start_party_mode` actually returns (invite URLs, QR file paths, session_id?). The PRD assumed a session id; ddmcpskills.md returns URLs + QR file paths. Plan accordingly.
- Manual-review modal vs manual-entry modal: the difference matters. Review = "trust OCR, fix outliers." Entry = "OCR failed, type it yourself, prefilled with best guesses." Don't conflate them.

</specifics>

<deferred>
## Deferred Ideas

- D&D Beyond JSON file import (`dm20__import_character_file`) — defer to v2; URL import covers 90% case
- Curated adventure browser UI (search/filter dropdown) — v2
- Character sheet sync (`dm20__check_sheet_changes` / `approve_sheet_change`) — v2
- Multi-character ingest (one upload with multiple sheets in one PDF) — v2; "one upload = one character" in v1
- OCR for non-English sheets — English only in v1
- Bulk character import from a player roster — v2
- Class verification UX beyond a warning (auto-resolve "Witcher" → "Fighter (Witcher-flavored)"?) — v2

</deferred>

---

*Phase: 03-lobby-character-ingest*
*Context gathered: 2026-05-21*
