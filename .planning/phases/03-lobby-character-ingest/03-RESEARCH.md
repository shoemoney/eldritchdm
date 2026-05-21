# Phase 3: Lobby + Character Ingest — Research

**Researched:** 2026-05-21
**Domain:** Discord slash commands, persistent views, dm20 MCP integration, OCR + PDF ingest, oMLX JSON-mode translation
**Confidence:** HIGH on libraries and dm20 tool shapes (read source directly), MEDIUM on discord.py 2.7.x runtime edge cases (verified against master branch; 2.7.1 frozen behavior assumed stable)

## Summary

Phase 3 is the first user-visible gameplay surface for EldritchDM. The research surfaced several findings that materially change the implementation shape from what CONTEXT.md anticipated:

1. **`dm20__start_party_mode` returns a markdown string, not a structured object.** The bot must regex-parse `**URL:**` and `**QR Code:**` lines per character. There is no `session_id` field — the campaign name *is* the session key for party mode. QR code paths are local filesystem PNGs that the bot must read and re-attach via `discord.File`.
2. **`dm20__start_claudmaster_session` returns a dict with `session_id` at the top level.** This is the value we store in `channel_sessions.claudmaster_session_id`.
3. **`dm20__load_adventure` returns markdown, not structured data.** Idempotency: re-loading the same adventure into the same campaign is a soft idempotent operation — it re-binds the module (no error) and **re-runs Chapter 1 entity population if `populate_chapter_1=True`**, which means duplicate Locations/NPCs/Quests get created. Recommend `populate_chapter_1=False` on subsequent calls or check `dm20__list_locations` first.
4. **oMLX + ShoeGPT + `response_format=json_object` works correctly.** Live-tested with two prompts including a deliberately messy OCR-style input — both returned clean JSON with no markdown wrappers or commentary. JSON mode is the primary path; no fallback parser needed for the happy path.
5. **discord.py Modals are hard-capped at 5 components.** The 2-step flow (primary fields then optional fields) MUST be implemented as two sequential modals, not stacked. Each TextInput supports up to 4000 chars value, 45-char label, 100-char placeholder.
6. **`Attachment.read()` buffers entirely in memory.** Fine for character sheets <10 MB, but the OCR pipeline should defend against absurd uploads with an explicit size check before calling `.read()`.
7. **`segno` is the right QR library**, not `qrcode`. Pure Python, no Pillow dependency, 76 KB wheel, identical API ergonomics.
8. **`ocrmac` returns `list[tuple[str, float, list[float]]]`** — per-region confidence is the second tuple element. Confidence aggregation = mean across regions, weighted by text length.

**Primary recommendation:** Build `ingest/` as a synchronous-in-executor pipeline behind an async facade; treat `start_party_mode`'s markdown return as a parsing problem (a small regex utility), and store the URL list + a single QR PNG path in `channel_sessions.dm20_party_token` as JSON; route every interaction handler's first line through `defer(thinking=True)`.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01..D-03:** Two cogs (`lobby.py`, `ingest.py`), loaded via `EldritchBot.setup_hook._load_cogs`, constructor-injected dependencies (`mcp_client`, `persistence`, `settings`, `logger`).
- **D-04:** `/start_game name:str description:str=None` — defer first, then `create_campaign` → `start_claudmaster_session` → `start_party_mode`, with best-effort rollback on failure. Record trio in `channel_sessions` only after all three succeed.
- **D-05:** `/load_adventure adventure_id:str campaign_name:str=None` — fast path with curated autocomplete for CoS, LMoP, HotDQ, PotA, OotA, ToA, WDH, WDMM, BGDIA.
- **D-06:** `/upload_character_url url:str player_name:str=None` — calls `dm20__import_from_dndbeyond`.
- **D-07:** `/upload_character_file attachment:Attachment player_name:str=None` — routes PNG/JPG/PDF to OCR/PDF pipeline.
- **D-08:** `/upload_character_manual` — opens manual-entry modal directly.
- **D-09..D-13:** Lobby embed shape, QR generation via Python lib, `ReadyButton.callback` reads ready-state from `persistent_views.payload_json`, character `player_id = str(interaction.user.id)`.
- **D-14..D-15:** `/load_adventure` idempotency documented (see Question 3 below), adventure ID autocomplete from static dict.
- **D-16..D-21:** OCR pipeline shape (six stages), backend selection (ocrmac → easyocr → error), PDF detection (content-type/ext), `ThreadPoolExecutor(max_workers=2)` via `IngestExecutor` singleton, module layout under `src/eldritch_dm/ingest/`, import contract `bot → ingest → mcp/safety`.
- **D-22..D-23:** New `translate_character_sheet` wrapper in `mcp/tools.py` calling `/v1/chat/completions` with `response_format={"type":"json_object"}`, `temperature=0.05`, schema embedded in system prompt, OCR text wrapped via `sanitize_player_input`.
- **D-24..D-25:** `CharacterSheet` frozen pydantic model with `AbilityScores`, ability ranges 1-30, class/race verification via `dm20__get_class_info` / `dm20__get_race_info`.
- **D-26..D-28:** Confidence score 0.0-1.0 (4 components × 0.2-0.3), threshold 0.6 routes to manual-entry vs manual-review modal, 5-component limit acknowledged (optional fields in follow-up modal).
- **D-29..D-30:** Permission check via `manage_channels`, all confirmations ephemeral, non-ephemeral lobby embed updates on character commit.
- **D-31:** End-to-end ingest budget <8s.
- **D-32..D-37:** Testing strategy (Pillow/reportlab fixtures, `unittest.mock` for OCR, `respx` for oMLX, AsyncMock for modals), structlog binding contract.

### Claude's Discretion

- QR library choice (`qrcode` vs `segno` vs CDN URL) — **recommendation in Q11 below: `segno`.**
- Modal field ordering and labels.
- Discord application emoji for class icons (defer — Unicode is fine).
- Adventure ID autocomplete static vs dynamic (`dm20__discover_adventures`) — **static dict for v1.**

### Deferred Ideas (OUT OF SCOPE)

- D&D Beyond JSON file import (`dm20__import_character_file`).
- Curated adventure browser UI.
- Character sheet sync (`dm20__check_sheet_changes` / `approve_sheet_change`).
- Multi-character ingest from a single PDF.
- OCR for non-English sheets.
- Bulk character import.
- Auto-resolve homebrew classes (e.g., "Witcher" → "Fighter").

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LOBBY-01 | `/start_game` → `create_campaign` + `start_claudmaster_session` + `start_party_mode` | Q1 (party_mode return shape — markdown parsing), Q2 (session_id extraction) |
| LOBBY-02 | `/load_adventure` runs `dm20__load_adventure` | Q3 (idempotency: re-runs Chapter 1 population), Q6 (autocomplete API) |
| LOBBY-03 | Lobby embed with party-mode invite/QR + Discord-native Join button | Q1 (read QR PNG from filesystem), Q11 (segno for inline QR) |
| LOBBY-04 | Ready check + transition to EXPLORATION | Q12 (permission pattern), existing `persistent_views.payload_json` |
| INGEST-01 | `/upload_character_url` → `dm20__import_from_dndbeyond` | wrapper exists in `mcp/tools.py` |
| INGEST-02 | `/upload_character_file` for PNG/JPG/PDF | Q5 (Attachment.read), Q12 (permission) |
| INGEST-03 | ocrmac primary, easyocr fallback | Q7 (ocrmac API), Q8 (easyocr API) |
| INGEST-04 | PyMuPDF primary, pypdf fallback | Q9 (`get_text("dict")` for multi-column sheets) |
| INGEST-05 | `ThreadPoolExecutor` via `run_in_executor` | confirmed pattern from CONTEXT D-19 |
| INGEST-06 | oMLX JSON-mode translation | Q10 (live-verified — works) |
| INGEST-07 | Pydantic validation + class/race verification | wrappers exist in `mcp/tools.py` |
| INGEST-08 | Manual-review modal | Q4 (Modal limits — 5 components, 4000 char) |
| INGEST-09 | Confidence-gated manual-entry path | Q7 + Q8 (per-region confidence aggregation) |
| INGEST-10 | Ephemeral confirmations; permission gate | Q12 (`manage_channels` check) |
| INGEST-11 | <8s end-to-end | Q10 (oMLX returns ~2-4s for 400-token JSON output) |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Slash command dispatch + defer | Discord bot (`bot/cogs/lobby.py`, `bot/cogs/ingest.py`) | — | Discord interaction lifecycle; must defer within 3s |
| Lobby state & ready tracking | Local SQLite (`persistent_views.payload_json`) | Discord bot (view rehydration) | Survives bot restart per BOT-05 |
| Campaign + session creation | dm20 MCP (`create_campaign`, `start_claudmaster_session`, `start_party_mode`) | Local SQLite (`channel_sessions`) | dm20 owns game state; we own the Discord-side mapping |
| Character ingest | Local Python (`ingest/`) | OS (Apple Vision via ocrmac on macOS) | OCR + PDF extraction is local CPU work; runs in ThreadPoolExecutor |
| OCR → structured character | oMLX (`response_format=json_object`) | Local Pydantic validator | LLM does the translation, Python validates the math/ranges |
| Adventure module loading | dm20 MCP (`load_adventure`) | — | Pure dm20 responsibility |
| Player ↔ character mapping | dm20 MCP (`player_id` field on character) | Discord bot (passes `str(interaction.user.id)`) | dm20 owns character records |
| QR + invite URL surface | Discord bot (regex-parse markdown, re-attach as `discord.File`) | dm20 (markdown source of truth) | dm20 emits markdown; Discord must convert to embed-native form |

## Standard Stack

### Core (already pinned in `pyproject.toml`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `discord.py` | `>=2.7.1,<3.0` | Modals, slash commands, persistent views, Attachment | Mature Modal/Attachment APIs; matches existing pin [VERIFIED: pyproject.toml] |
| `PyMuPDF` (pymupdf) | `>=1.24,<2.0` | PDF text + render | `get_text("dict")` for multi-column sheets [CITED: pymupdf.readthedocs.io] |
| `pypdf` | `>=4.3,<6.0` | PDF fallback | MIT, pure Python, no native deps [VERIFIED: pyproject.toml] |
| `ocrmac` | `>=1.0,<2.0` (mac-ocr extra) | macOS Apple Vision OCR | Native NN inference, no model download [VERIFIED: pip index 1.0.1] |
| `easyocr` | `>=1.7,<2.0` (linux-ocr extra) | Linux/CUDA OCR fallback | Cross-platform when ocrmac unavailable [VERIFIED: pip index 1.7.2] |
| `openai` | `>=1.55,<2.0` | oMLX-compatible client | Already used by mcp.client [VERIFIED: pyproject.toml] |
| `pydantic` | `>=2.8,<3.0` | `CharacterSheet`, `AbilityScores` validators | Existing project standard |
| `aiosqlite` | `>=0.20,<0.22` | persistence layer | Already wired |

### Supporting (NEW for Phase 3)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `segno` | `>=1.6,<2.0` | QR code generation | Pure Python, zero deps (no Pillow needed), 76 KB wheel — strictly better than `qrcode` for this use case [VERIFIED: pip index 1.6.6] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `segno` | `qrcode>=7.4` | Same API ergonomics but requires Pillow (~3 MB) and `image_factory='pil'` flag; we use Pillow elsewhere via easyocr but on macOS we don't install easyocr, so adding Pillow just for QR is wasteful |
| `segno` | CDN-based QR URL (e.g., `https://api.qrserver.com/v1/?data=…`) | Adds network dependency for a feature that's part of the bot's first impression; embarrassing if the CDN goes down. Local generation is the right call |
| In-memory QR | Read dm20-generated QR PNG from filesystem | Both work; we'll read the dm20 PNGs because they're already correct, **and** generate a fresh embed-friendly QR with segno if the file is missing or unreadable (defense in depth) |
| Re-parsing markdown | Asking dm20 for structured return | dm20 is upstream; not our project. Recommend filing a downstream issue but not blocking on it |

**Installation:**

```bash
uv pip install -e ".[dev,mac-ocr]"   # macOS dev
uv pip install -e ".[dev,linux-ocr]" # Linux dev
uv pip install segno
```

Adding `segno` to `pyproject.toml` `dependencies` is the only change needed.

**Version verification (run 2026-05-21):**

```
ocrmac     1.0.1
easyocr    1.7.2
qrcode     8.2
segno      1.6.6
pymupdf    1.27.2.3
pypdf      6.12.0
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Disposition |
|---------|----------|-----|-----------|-------------|-------------|
| `segno` | PyPI | 6+ yrs | ~3 M/mo | https://github.com/heuer/segno | Approved — well-known, used by many projects |
| `ocrmac` | PyPI | 2+ yrs | ~50 K/mo | https://github.com/straussmaximilian/ocrmac | Approved — already in optional deps |
| `easyocr` | PyPI | 5+ yrs | ~1 M/mo | https://github.com/JaidedAI/EasyOCR | Approved — already in optional deps |
| `PyMuPDF` | PyPI | 8+ yrs | ~10 M/mo | https://github.com/pymupdf/PyMuPDF | Approved — already pinned |
| `pypdf` | PyPI | 10+ yrs | ~30 M/mo | https://github.com/py-pdf/pypdf | Approved — already pinned |

**Packages removed:** none
**Packages flagged:** none

*slopcheck not available in this environment; legitimacy assessed via direct registry inspection, GitHub source repo verification, and download counts. All packages have multi-year history and large user bases.*

## Architecture Patterns

### System Architecture Diagram

```
                    Discord (slash command / button click)
                                  │
                                  ▼
            ┌─────────────────────────────────────────────┐
            │           bot/cogs/lobby.py                 │
            │           bot/cogs/ingest.py                │
            │  (defer first; dispatch by command)         │
            └────────┬────────────────────────────┬───────┘
                     │                            │
        ┌────────────┼────────────┐    ┌──────────┼──────────────┐
        ▼            ▼            ▼    ▼          ▼              ▼
  /start_game   ReadyButton   /upload_*    /load_adv     /upload_manual
        │            │            │           │              │
        │            │            ▼           │              ▼
        │            │     ingest/ pipeline   │     character_modal
        │            │       (executor)       │       (5 fields)
        │            │            │           │              │
        │            │   ┌────────┴────────┐  │              │
        │            │   ▼                 ▼  │              │
        │            │  OCR             PDF   │              │
        │            │ (ocrmac /      (pymupdf│              │
        │            │  easyocr)     / pypdf) │              │
        │            │   │                 │  │              │
        │            │   └────────┬────────┘  │              │
        │            │            ▼           │              │
        │            │      raw_text          │              │
        │            │            │           │              │
        │            │            ▼           │              │
        │            │   safety/sanitizer     │              │
        │            │            │           │              │
        │            │            ▼           │              │
        │            │   mcp/tools.translate_ │              │
        │            │   character_sheet      │              │
        │            │   (oMLX JSON mode)     │              │
        │            │            │           │              │
        │            │            ▼           │              │
        │            │   Pydantic CharacterSheet              │
        │            │            │           │              │
        │            │            ▼           │              │
        │            │   confidence_score(...)│              │
        │            │            │           │              │
        │            │            └─────┬─────┴──────┐       │
        │            │                  ▼            ▼       ▼
        │            │           review_modal   entry_modal──┘
        │            │                  │            │
        │            │                  └──────┬─────┘
        │            │                         ▼
        │            │             mcp/tools.create_character
        │            │                         │
        ▼            ▼                         ▼
   ┌─────────────────────────────────────────────────────────┐
   │                       dm20 MCP                          │
   │  create_campaign / start_claudmaster_session /          │
   │  start_party_mode / load_adventure /                    │
   │  import_from_dndbeyond / create_character /             │
   │  get_class_info / get_race_info / list_characters /     │
   │  player_action                                          │
   └─────────────────────────────────────────────────────────┘
        │
        ▼
   ┌─────────────────────────────────────────────────────────┐
   │             persistence (local SQLite WAL)              │
   │  channel_sessions (state, dm20_party_token)             │
   │  persistent_views (payload_json — ready state)          │
   └─────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| File | Responsibility |
|------|----------------|
| `bot/cogs/lobby.py` | `/start_game`, `/load_adventure`, `ReadyButton.callback`, EXPLORATION transition |
| `bot/cogs/ingest.py` | `/upload_character_url`, `/upload_character_file`, `/upload_character_manual` |
| `ingest/pipeline.py` | `async def ingest(attachment, *, player_name, user_id, channel_id) -> IngestResult` |
| `ingest/ocr.py` | `run_ocrmac(image_bytes)` / `run_easyocr(image_bytes)` returning `(text: str, confidence: float)` |
| `ingest/pdf.py` | `extract_pdf_text(pdf_bytes) -> str` using PyMuPDF, fall back to pypdf on exception |
| `ingest/translate.py` | `translate_to_character_sheet(raw_text: str) -> CharacterSheet` via `mcp.tools.translate_character_sheet` |
| `ingest/schema.py` | `CharacterSheet`, `AbilityScores` frozen pydantic models |
| `ingest/executor.py` | `IngestExecutor` singleton wrapping `ThreadPoolExecutor(max_workers=2)` |
| `bot/dynamic_items.py` | `ReadyButton` callback updated to real logic (was stub in Phase 2) |
| `bot/embeds.py` | `lobby_embed` content fully populated; `character_confirm_embed` rendered post-commit |
| `mcp/tools.py` | NEW: `translate_character_sheet`, `list_characters`, `get_class_info`, `get_race_info`, `player_action`, `get_party_status` |

### Pattern 1: Defer-First Slash Handler

**What:** Every interaction's first awaited line is `defer(thinking=True)`. Discord enforces a 3-second response window; ANY downstream call (MCP, OCR, oMLX) can exceed this. Defer immediately to extend the window to 15 minutes for followup.

**When to use:** Every slash command and button callback in `lobby.py` / `ingest.py`.

**Example:**

```python
@app_commands.command(name="start_game", description="Start a new D&D campaign in this channel")
@app_commands.describe(name="Campaign name", description="Short tagline (optional)")
async def start_game(self, interaction: discord.Interaction, name: str, description: str | None = None) -> None:
    await interaction.response.defer(thinking=True)  # MUST be first await
    # ... downstream MCP calls can take seconds without timeout
    campaign = await mcp_tools.create_campaign(self.mcp, name=name, description=description or "")
    session = await mcp_tools.start_claudmaster_session(self.mcp, campaign_name=name)
    party = await mcp_tools.start_party_mode(self.mcp, campaign_name=name)  # returns markdown
    # ...
    await interaction.followup.send(embed=embed, file=qr_file)
```

### Pattern 2: Markdown Parser for `start_party_mode` Output

**What:** `dm20__start_party_mode` returns a markdown string. Parse it with a small regex utility to extract per-character URLs and QR file paths.

**When to use:** Inside `/start_game` after receiving the party mode response, before constructing the lobby embed.

**Example:**

```python
import re
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class PartyMember:
    character_name: str
    url: str
    qr_path: Path | None  # None if QR generation failed in dm20

# Sample input from dm20__start_party_mode:
#   # Party Mode Active
#
#   **Server:** http://192.168.1.5:8080
#   **Players:** 4 PCs + 1 Observer
#
#   ## Player Connections
#
#   ### Aragorn
#   - **URL:** http://192.168.1.5:8080/play?token=abc123
#   - **QR Code:** /Users/.../campaigns/CampName/qr_codes/Aragorn.png
#
#   ### OBSERVER (read-only)
#   - **URL:** http://192.168.1.5:8080/play?token=xyz789
#   - **QR Code:** /Users/.../campaigns/CampName/qr_codes/OBSERVER.png
#
#   ---
#   ...

_HEADER_RE = re.compile(r"^### (?P<name>.+)$", re.MULTILINE)
_URL_RE = re.compile(r"^- \*\*URL:\*\* (?P<url>http[s]?://\S+)$", re.MULTILINE)
_QR_RE = re.compile(r"^- \*\*QR Code:\*\* (?P<path>\S+)$", re.MULTILINE)
_QR_FAIL = "(generation failed, use URL instead)"
_SERVER_RE = re.compile(r"^\*\*Server:\*\* (?P<url>http[s]?://\S+)$", re.MULTILINE)


def parse_party_mode_response(markdown: str) -> tuple[str, list[PartyMember]]:
    """Parse dm20__start_party_mode markdown output.

    Returns (server_url, members). Observer is included as a member with name='OBSERVER'.

    Raises ValueError if the response is malformed (e.g., starts with 'Error:').
    """
    if markdown.lstrip().startswith("Error:"):
        raise ValueError(markdown.strip())

    server_match = _SERVER_RE.search(markdown)
    if not server_match:
        raise ValueError("Party Mode response missing **Server:** line")
    server_url = server_match.group("url")

    # Iterate per-character blocks. We split on '### ' headers and walk pairs.
    sections = markdown.split("\n### ")
    members: list[PartyMember] = []
    for section in sections[1:]:  # skip preamble
        name_end = section.find("\n")
        name = section[:name_end].strip()
        body = section[name_end:]
        url_m = _URL_RE.search(body)
        qr_m = _QR_RE.search(body)
        if not url_m:
            continue  # malformed section, skip
        qr_path = None
        if qr_m and _QR_FAIL not in qr_m.group("path"):
            candidate = Path(qr_m.group("path"))
            if candidate.exists():
                qr_path = candidate
        members.append(PartyMember(character_name=name, url=url_m.group("url"), qr_path=qr_path))
    return server_url, members
```

**Storage:** Serialize the parsed result as JSON into `channel_sessions.dm20_party_token`:

```python
import json
party_token_json = json.dumps({
    "server_url": server_url,
    "members": [{"name": m.character_name, "url": m.url, "qr_path": str(m.qr_path) if m.qr_path else None} for m in members],
})
```

This is forward-compatible with the column's TEXT type and avoids inventing a new table just for party state.

### Pattern 3: Defensive Confidence Aggregation

**What:** Both OCR backends return per-region confidence floats. Aggregate to a single score using length-weighted mean.

**When to use:** Inside `ingest/ocr.py` after OCR returns.

**Example:**

```python
def aggregate_ocrmac_confidence(regions: list[tuple[str, float, list[float]]]) -> tuple[str, float]:
    """Combine ocrmac per-region tuples into (joined_text, confidence_score).

    Confidence is length-weighted mean — long text spans dominate.
    Empty input returns ("", 0.0).
    """
    if not regions:
        return "", 0.0
    total_len = sum(len(text) for text, _, _ in regions) or 1
    weighted_conf = sum(conf * len(text) for text, conf, _ in regions) / total_len
    joined = "\n".join(text for text, _, _ in regions)
    return joined, weighted_conf


def aggregate_easyocr_confidence(regions: list[tuple[list[list[int]], str, float]]) -> tuple[str, float]:
    """Same shape, different tuple ordering."""
    if not regions:
        return "", 0.0
    total_len = sum(len(text) for _, text, _ in regions) or 1
    weighted_conf = sum(conf * len(text) for _, text, conf in regions) / total_len
    joined = "\n".join(text for _, text, _ in regions)
    return joined, weighted_conf
```

### Anti-Patterns to Avoid

- **Synchronous OCR / PDF on the event loop.** `ocrmac` and `easyocr.Reader.readtext` block. Always wrap via `loop.run_in_executor(IngestExecutor.pool, ...)`.
- **`fitz.open(path)` with a temp file** for an in-memory bytes payload. Use `pymupdf.open(stream=BytesIO(b), filetype="pdf")` directly.
- **Trusting `Attachment.content_type` for routing.** Discord populates `content_type` from the client's upload metadata which can lie. Use **both** extension AND `content_type`, and ultimately rely on `python-magic` or PyMuPDF's own ability to reject non-PDF bytes.
- **Showing the raw `start_party_mode` markdown to users.** It contains absolute file paths that mean nothing to a Discord user. Always reformat into an embed.
- **Calling `attachment.read()` without a size check.** Discord allows attachments up to 25 MB on the standard tier; a 25 MB PNG in OCR + the LLM context window is a denial of service. Cap at e.g. 10 MB.
- **Storing the dm20 QR PNG path long-term.** The file lives in dm20's campaign directory and will move/disappear. Read the bytes immediately, attach to embed, discard the path. If you need to re-render the embed later (e.g., on bot restart), regenerate the QR with `segno` from the stored URL.
- **Two-step modals using `Modal.add_item` more than 5 times.** Discord rejects the 6th component. Use sequential modals or hand-off to a follow-up modal triggered from a button.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| QR code generation | Custom PNG encoder | `segno.make(url).save(buffer, kind='png')` | Battle-tested encoder, error correction modes, micro-QR support |
| Multi-column PDF text extraction | Coordinate-based reassembly | `PyMuPDF.page.get_text("dict")` | Block + line + span structure already computed |
| OCR confidence math | Custom statistics | Length-weighted mean of per-region floats | Standard practice — single regions can be noise |
| Markdown parsing of dm20 responses | Free-form string slicing | Small regex utility (see Pattern 2) | dm20's markdown is stable but not strict; regex tolerates whitespace |
| Modal field validation | Re-implementing pydantic | `CharacterSheet` model with `Field(ge=1, le=30)` | Pydantic v2 is already a dep |
| Permission checks | Custom role lookups | `interaction.user.guild_permissions.manage_channels` | discord.py resolves overwrites for you |
| QR PNG → discord.File | Writing to temp file | `discord.File(io.BytesIO(png_bytes), filename="qr.png")` | discord.py reads any file-like or path |

**Key insight:** Every problem in this phase has a battle-tested library. The custom work is the *plumbing* between Discord, dm20, OCR, and oMLX — not any of the individual transformations.

## Common Pitfalls

### Pitfall 1: Modal Component Cap (5 Hard Limit)

**What goes wrong:** Adding a 6th `TextInput` raises `ValueError('maximum number of children exceeded (5)')`.
**Why it happens:** Discord's API caps modals at 5 components total. discord.py enforces this client-side at `add_item()`.
**How to avoid:** Plan modal field sets at design time. Six ability scores can't fit alongside name/class/level/race — must split into two modals. CONTEXT D-28 already acknowledges this; the implementation must follow through.
**Warning signs:** A `Modal` subclass with 6+ class-level `TextInput` attributes — fails at modal instantiation, not at send time.

### Pitfall 2: Defer Forgotten on Long-Running Handlers

**What goes wrong:** Interaction expires after 3s; user sees "This interaction failed" toast.
**Why it happens:** MCP calls (`create_campaign` + `start_claudmaster_session` + `start_party_mode`) routinely take >3s in aggregate.
**How to avoid:** Project already plans a custom pre-commit lint to enforce `defer` as the first line (BOT-02). Phase 3 cogs MUST honor this.
**Warning signs:** Any `await` before the `defer(thinking=True)` call.

### Pitfall 3: dm20 QR Path Race After Bot Restart

**What goes wrong:** On restart, bot rehydrates `channel_sessions` and tries to re-render the lobby embed, but the dm20 QR PNG was generated under a previous campaign directory that no longer matches.
**Why it happens:** Party mode QR paths are written to `<dm20_data>/campaigns/<name>/qr_codes/<character>.png`. If dm20 was restarted, the *file* may still exist but the *token* embedded in the QR is stale.
**How to avoid:** On rehydration, regenerate the QR from the stored URL (`segno.make(url)`). The URL contains the token; the PNG is just visual. Treat the on-disk PNG as a one-shot artifact.
**Warning signs:** Players scan QR after a restart and get "invalid token" from the party mode server.

### Pitfall 4: oMLX Returns Markdown-Wrapped JSON Despite `response_format`

**What goes wrong:** Some local models ignore `response_format=json_object` and wrap output in `` ```json ... ``` ``.
**Why it happens:** `response_format` is a hint; not all backends enforce. Verified that ShoeGPT on oMLX as deployed honors it correctly (live-tested 2026-05-21), but a future model swap could regress.
**How to avoid:** Defensive parser strips a leading `` ```json `` / trailing `` ``` `` even when not expected. Pydantic validation catches any residual issues.
**Warning signs:** `json.JSONDecodeError` on what looks like a valid response — print the raw content first.

```python
def parse_json_response(content: str) -> dict:
    """Defensive JSON parse — strips ``` fences if present."""
    s = content.strip()
    if s.startswith("```"):
        # strip leading fence
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        # strip trailing fence
        if s.endswith("```"):
            s = s[:-3]
    return json.loads(s.strip())
```

### Pitfall 5: `Attachment.content_type` is Client-Reported (Untrusted)

**What goes wrong:** Player renames `payload.exe` to `sheet.png`, uploads; `content_type` might be reported as `image/png`.
**Why it happens:** Discord trusts the upload client's MIME claim. We are the bot — we receive what Discord forwards.
**How to avoid:** After `attachment.read()`, sniff the first few bytes:
- PNG: `\x89PNG\r\n\x1a\n`
- JPEG: `\xff\xd8\xff`
- PDF: `%PDF-`
Reject anything else before passing to OCR/PDF.
**Warning signs:** PyMuPDF or PIL raising "cannot identify image format" — sanitize earlier in the pipeline.

### Pitfall 6: ocrmac Imports PyObjC at Module Load

**What goes wrong:** Tests run on a Linux CI machine, `import ocrmac` raises ImportError at test collection time.
**Why it happens:** `ocrmac` is macOS-only. Phase 3 should never `import ocrmac` at module level outside the macOS detection branch.
**How to avoid:** Detect platform inside the function:

```python
import sys

def _ocrmac_available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import ocrmac  # noqa: F401
        return True
    except ImportError:
        return False
```

Or use `importlib.util.find_spec`. Tests must use `unittest.mock` to provide `ocrmac` (D-33).

### Pitfall 7: `load_adventure` Non-Idempotency (Duplicate Locations/NPCs)

**What goes wrong:** Player runs `/load_adventure CoS` twice; the second call re-creates the same 3 locations, 5 NPCs, and 1 quest.
**Why it happens:** `populate_chapter_1=True` (the default) unconditionally calls `storage.add_location/add_npc/add_quest`. Reading the source code, there is no dedup check.
**How to avoid:** Before calling `load_adventure`, query `dm20__list_locations` (or similar). If any exist, prompt the user with "This campaign already has locations — load anyway?" or default to `populate_chapter_1=False` on re-runs.
**Warning signs:** Players seeing duplicate NPCs in the campaign after a re-load.

### Pitfall 8: Party Mode Already Running

**What goes wrong:** Bot crashes mid-`/start_game` after `start_party_mode` succeeded. On restart, user re-runs `/start_game` and dm20 returns `"Party Mode is already running at http://..."` — which doesn't include the QR paths we need.
**Why it happens:** dm20 enforces single-instance party mode.
**How to avoid:** Before retrying, call `dm20__get_party_status` to detect the running server and reuse it; or call `dm20__stop_party_mode` first if the campaign has changed.
**Warning signs:** Markdown response starts with "Party Mode is already running" — parser must detect this and either short-circuit (reuse) or recover (stop+start).

## Code Examples

### Slash Command with Autocomplete (`/load_adventure`)

```python
# bot/cogs/lobby.py
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from eldritch_dm.mcp.client import MCPClient

ADVENTURE_IDS: dict[str, str] = {
    "CoS": "Curse of Strahd",
    "LMoP": "Lost Mine of Phandelver",
    "HotDQ": "Hoard of the Dragon Queen",
    "PotA": "Princes of the Apocalypse",
    "OotA": "Out of the Abyss",
    "ToA": "Tomb of Annihilation",
    "WDH": "Waterdeep: Dragon Heist",
    "WDMM": "Waterdeep: Dungeon of the Mad Mage",
    "BGDIA": "Baldur's Gate: Descent into Avernus",
}


class LobbyCog(commands.Cog):
    def __init__(self, bot: commands.Bot, mcp: "MCPClient") -> None:
        self.bot = bot
        self.mcp = mcp

    @app_commands.command(name="load_adventure", description="Load an official 5e adventure")
    @app_commands.describe(adventure_id="Adventure module ID (CoS, LMoP, etc.)")
    async def load_adventure(
        self,
        interaction: discord.Interaction,
        adventure_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        # ... call dm20__load_adventure, parse markdown, post embed ...

    @load_adventure.autocomplete("adventure_id")
    async def adventure_id_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Returns up to 25 matching adventure IDs.

        Discord sends this on each keystroke (debounced client-side ~200ms).
        Stay <3s per call. Static dict makes this O(N) and instant.
        """
        cur = current.lower()
        return [
            app_commands.Choice(name=f"{aid} — {title}", value=aid)
            for aid, title in ADVENTURE_IDS.items()
            if cur in aid.lower() or cur in title.lower()
        ][:25]
```

[CITED: discord.py master commands.py — autocomplete callback must be coroutine returning up to 25 Choices]

### Modal with Permission Check + Confidence Routing

```python
# bot/cogs/ingest.py
import discord
from discord import app_commands
from discord.ext import commands


class UploadCharacterModal(discord.ui.Modal):
    """Manual-review modal — prefilled with OCR best guesses (D-27, D-28)."""

    def __init__(self, prefill: dict, *, on_submit_cb):
        super().__init__(title="Confirm Character", custom_id="char_review")
        self._on_submit_cb = on_submit_cb

        # 5-component cap forces strict prioritization
        self.name_in = discord.ui.TextInput(
            label="Character Name",
            default=prefill.get("name", ""),
            max_length=80,
            required=True,
        )
        self.class_in = discord.ui.TextInput(
            label="Class",
            default=prefill.get("character_class", ""),
            max_length=40,
            required=True,
        )
        self.level_in = discord.ui.TextInput(
            label="Level (1-20)",
            default=str(prefill.get("class_level", 1)),
            max_length=2,
            required=True,
        )
        self.race_in = discord.ui.TextInput(
            label="Race",
            default=prefill.get("race", ""),
            max_length=40,
            required=True,
        )
        abilities = prefill.get("abilities", {})
        # Pack all 6 ability scores into a single multi-line input
        self.abilities_in = discord.ui.TextInput(
            label="Ability Scores (STR DEX CON INT WIS CHA)",
            style=discord.TextStyle.short,
            default=" ".join(str(abilities.get(k, 10)) for k in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]),
            max_length=23,  # "30 30 30 30 30 30" with spaces
            required=True,
        )
        for item in [self.name_in, self.class_in, self.level_in, self.race_in, self.abilities_in]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._on_submit_cb(interaction, {
            "name": str(self.name_in).strip(),
            "character_class": str(self.class_in).strip(),
            "class_level": int(str(self.level_in)),
            "race": str(self.race_in).strip(),
            "abilities_str": str(self.abilities_in).strip(),
        })


def can_act_on_character(interaction: discord.Interaction, character_player_id: str | None) -> bool:
    """D-29: invoking player OR DM (manage_channels) can act."""
    if character_player_id and str(interaction.user.id) == character_player_id:
        return True
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.manage_channels)
```

[CITED: discord.py master ui/modal.py — `len(self._children) >= 5` raises `ValueError`]
[CITED: discord.py master ui/text_input.py — label ≤45, placeholder ≤100, max_length 1-4000]

### QR Code Generation (segno → discord.File)

```python
# bot/qr.py
import io
import segno
import discord


def render_qr_for_embed(url: str, *, filename: str = "qr.png") -> discord.File:
    """Generate a QR code as an in-memory PNG suitable for an embed thumbnail.

    Choose error correction 'M' (15%) — robust to camera glare without bloat.
    scale=8 yields ~250x250 px which is the sweet spot for Discord embeds.
    """
    qr = segno.make(url, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=8, border=2, dark="black", light="white")
    buf.seek(0)
    return discord.File(buf, filename=filename)
```

Then in the embed:

```python
qr_file = render_qr_for_embed(member.url, filename=f"qr_{member.character_name}.png")
embed.set_thumbnail(url=f"attachment://qr_{member.character_name}.png")
await interaction.followup.send(embed=embed, file=qr_file)
```

### Attachment Read + Sniff + Route

```python
# bot/cogs/ingest.py (excerpt)
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB hard cap

async def _read_and_route(attachment: discord.Attachment) -> tuple[str, bytes]:
    """Returns (kind, data) where kind is 'image' or 'pdf'.

    Raises ValueError on oversize or unsupported type.
    """
    if attachment.size > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"Attachment exceeds {MAX_ATTACHMENT_BYTES // 1024 // 1024} MB limit")

    data = await attachment.read()  # buffers in memory (verified: discord.py message.py)

    # Magic-byte sniff (do NOT trust attachment.content_type)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image", data
    if data[:3] == b"\xff\xd8\xff":
        return "image", data
    if data[:5] == b"%PDF-":
        return "pdf", data
    raise ValueError("Unsupported file format (PNG, JPEG, PDF only)")
```

### oMLX JSON-Mode Translation Wrapper

```python
# mcp/tools.py (NEW addition)
from openai import AsyncOpenAI
from eldritch_dm.ingest.schema import CharacterSheet
import json

CHARACTER_SHEET_SCHEMA_JSON = json.dumps(CharacterSheet.model_json_schema())

TRANSLATE_SYSTEM_PROMPT = (
    "You are a strict data formatter. Extract D&D 5e character sheet fields "
    "from the messy OCR text inside <player_action> sentinels. "
    "Return ONLY a JSON object matching this schema. "
    "Do not include markdown, code fences, or commentary.\n\n"
    f"Schema: {CHARACTER_SHEET_SCHEMA_JSON}"
)


async def translate_character_sheet(
    openai_client: AsyncOpenAI,
    raw_text_wrapped: str,  # already wrapped via sanitize_player_input
    *,
    model: str = "ShoeGPT",
) -> dict:
    """Call oMLX with response_format=json_object.

    Verified live 2026-05-21 against ShoeGPT on omlx serve :8765 —
    JSON mode returns clean JSON with no markdown wrappers.
    """
    completion = await openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": TRANSLATE_SYSTEM_PROMPT},
            {"role": "user", "content": raw_text_wrapped},
        ],
        response_format={"type": "json_object"},
        temperature=0.05,
        max_tokens=600,
    )
    content = completion.choices[0].message.content or ""
    return _defensive_json_parse(content)


def _defensive_json_parse(s: str) -> dict:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return json.loads(s.strip())
```

## Runtime State Inventory

> Phase 3 is greenfield (new cogs, new module). Below is included only because the phase touches existing tables.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `channel_sessions.dm20_party_token` — currently TEXT, will store JSON-serialized party state. No migration needed; column exists. `persistent_views.payload_json` already used; will add per-channel ready-state under a documented key. | code edit only |
| Live service config | None. dm20 owns its own state. | none |
| OS-registered state | None new. | none |
| Secrets/env vars | None new. `OMLX_ENDPOINT`, `OMLX_MODEL`, `MCP_EXECUTE_URL` already documented. | none |
| Build artifacts | None. Adding `segno` to `pyproject.toml` is a normal dep change. | run `uv pip install -e ".[dev,mac-ocr]"` after merge |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| oMLX server on :8765 | INGEST-06 (JSON-mode translation) | ✓ | model `ShoeGPT` | none — required for ingest |
| dm20 MCP server (`POST :8765/v1/mcp/execute`) | LOBBY-01..04, INGEST-01,07 | ✓ | reachable | none — required |
| ocrmac (Python pkg) | INGEST-03 (macOS primary) | install on demand via `[mac-ocr]` extra | 1.0.1 | easyocr extra |
| easyocr (Python pkg) | INGEST-03 (Linux fallback) | install on demand via `[linux-ocr]` extra | 1.7.2 | ephemeral error to user |
| PyMuPDF | INGEST-04 | ✓ (pinned) | 1.27.x | pypdf |
| pypdf | INGEST-04 (fallback) | ✓ (pinned) | 6.x | none (very low likelihood both fail) |
| segno | LOBBY-03 (QR generation) | NEW pin | 1.6.6 | regenerate using dm20 PNG path |
| macOS Apple Vision framework | ocrmac runtime | ✓ on macOS 10.15+ | platform | linux-ocr extra |

**Missing dependencies with no fallback:** None for primary platform (macOS with all extras).
**Missing dependencies with fallback:** `ocrmac` on Linux → `easyocr` automatically selected by `OcrBackend` resolver.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23 + respx 0.21 |
| Config file | `pyproject.toml` [tool.pytest] section (existing) |
| Quick run command | `pytest -x tests/ingest/ tests/bot/cogs/test_lobby.py tests/bot/cogs/test_ingest.py` |
| Full suite command | `pytest` |
| Phase gate | `pytest --cov=eldritch_dm` green; integration smoke (Phase 1) extended |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File |
|--------|----------|-----------|-------------------|------|
| LOBBY-01 | `/start_game` orchestrates 3 MCP calls + records session | integration | `pytest tests/bot/cogs/test_lobby.py::test_start_game_happy_path -x` | ❌ Wave 0 |
| LOBBY-01 | Rollback on `start_party_mode` failure | integration | `pytest tests/bot/cogs/test_lobby.py::test_start_game_rollback -x` | ❌ Wave 0 |
| LOBBY-02 | `/load_adventure` + autocomplete returns ≤25 matches | unit | `pytest tests/bot/cogs/test_lobby.py::test_load_adventure_autocomplete -x` | ❌ Wave 0 |
| LOBBY-03 | Lobby embed renders QR + URL + ready button | unit | `pytest tests/bot/test_embeds.py::test_lobby_embed_with_qr -x` | ❌ Wave 0 (extend) |
| LOBBY-04 | Ready button transitions LOBBY → EXPLORATION when all players ready | integration | `pytest tests/bot/cogs/test_lobby.py::test_ready_transition -x` | ❌ Wave 0 |
| INGEST-01 | `/upload_character_url` calls `import_from_dndbeyond` | unit | `pytest tests/bot/cogs/test_ingest.py::test_upload_url -x` | ❌ Wave 0 |
| INGEST-02 | `/upload_character_file` routes by sniff | unit | `pytest tests/bot/cogs/test_ingest.py::test_file_sniff_routing -x` | ❌ Wave 0 |
| INGEST-03 | ocrmac and easyocr backends produce text + confidence | unit (mocked) | `pytest tests/ingest/test_ocr.py -x` | ❌ Wave 0 |
| INGEST-04 | PyMuPDF primary, pypdf fallback | unit | `pytest tests/ingest/test_pdf.py -x` | ❌ Wave 0 |
| INGEST-05 | ThreadPoolExecutor used for OCR/PDF | unit | `pytest tests/ingest/test_executor.py -x` | ❌ Wave 0 |
| INGEST-06 | oMLX JSON-mode translation parses dirty input | unit (respx mock) | `pytest tests/ingest/test_translate.py -x` | ❌ Wave 0 |
| INGEST-07 | Pydantic + range checks + class/race verify | unit | `pytest tests/ingest/test_schema.py -x` | ❌ Wave 0 |
| INGEST-08 | Manual-review modal opens with prefilled fields | unit (AsyncMock) | `pytest tests/bot/cogs/test_ingest.py::test_review_modal -x` | ❌ Wave 0 |
| INGEST-09 | Low confidence → manual-entry modal | unit | `pytest tests/bot/cogs/test_ingest.py::test_low_confidence_routes_to_entry -x` | ❌ Wave 0 |
| INGEST-10 | Permission gate blocks non-owner non-DM | unit | `pytest tests/bot/cogs/test_ingest.py::test_permission_denied -x` | ❌ Wave 0 |
| INGEST-11 | End-to-end <8s for standard sheet | integration (mocked oMLX) | `pytest tests/integration/test_ingest_smoke.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest -x tests/ingest/ tests/bot/cogs/test_lobby.py tests/bot/cogs/test_ingest.py`
- **Per wave merge:** `pytest`
- **Phase gate:** Full suite green; integration smoke extended (per CONTEXT D-35)

### Wave 0 Gaps

- [ ] `tests/ingest/conftest.py` — fixtures: minimal PNG/PDF generators using Pillow/reportlab, `mock_ocrmac`, `mock_easyocr`, `mock_omlx_translate`
- [ ] `tests/ingest/test_ocr.py`
- [ ] `tests/ingest/test_pdf.py`
- [ ] `tests/ingest/test_translate.py`
- [ ] `tests/ingest/test_schema.py`
- [ ] `tests/ingest/test_pipeline.py`
- [ ] `tests/ingest/test_executor.py`
- [ ] `tests/bot/cogs/test_lobby.py` (new file)
- [ ] `tests/bot/cogs/test_ingest.py` (new file)
- [ ] `tests/integration/test_phase3_smoke.py` (extend existing Phase 1 smoke)
- [ ] dev dep: `reportlab` for PDF fixture generation (lightweight; add to `[dev]`)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partial | Discord OAuth handles user identity; `user_id` is the trust anchor |
| V3 Session Management | partial | Bot sessions are per-channel; party mode tokens are dm20's responsibility |
| V4 Access Control | yes | `manage_channels` permission gates DM actions (D-29); per-player character ownership |
| V5 Input Validation | yes | `sanitize_player_input` + pydantic `CharacterSheet` model |
| V6 Cryptography | no | No new crypto in this phase; party mode tokens come from dm20 |
| V12 Files & Resources | yes | Attachment size cap, magic-byte sniff, no path traversal (we never echo filenames into paths) |

### Known Threat Patterns for Phase 3

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via OCR text | Tampering / Spoofing | `sanitize_player_input` wraps in `<player_action>` sentinels; `response_format=json_object` discards prose |
| Malicious file upload (zip bomb, polyglot) | DoS / Tampering | 10 MB cap, magic-byte sniff before parsing |
| Discord-side spoofing of `content_type` | Spoofing | Sniff bytes after `.read()` (do NOT trust `attachment.content_type`) |
| QR-code phishing (player tricks others into scanning a forged URL) | Spoofing | QR is generated from dm20's response, not user input |
| Modal injection (player submits `<|im_start|>` in name field) | Tampering | Modal submission text passes through `sanitize_player_input` before any LLM call |
| Privilege escalation (non-DM uploading character for another player) | Elevation of Privilege | `can_act_on_character` gate combining ownership + `manage_channels` |
| dm20 party token leakage in logs | Information Disclosure | structlog redaction list — never log `dm20_party_token` raw value |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pyzbar` + ImageMagick for QR | `segno` pure Python | 2024+ | No native deps, no image magick install pain |
| Tesseract + pytesseract for OCR | Apple Vision (ocrmac) on macOS, easyocr on Linux | 2023+ | Higher accuracy on printed text, no model download for ocrmac |
| `pyPDF2` (deprecated) | `pypdf` | 2022 | Same lineage, current name |
| `requests` + sync OCR on the event loop | `httpx` + `run_in_executor` | 2022+ | Doesn't block Discord heartbeat |
| Embedding JSON schemas in prompt + regex parse | `response_format=json_object` | OpenAI API 2024 | Backend enforces JSON; cleaner pipeline |

**Deprecated/outdated:**

- `pyPDF2` → use `pypdf`
- `qrcode` library on its own → prefer `segno` for new projects
- Sync OCR libraries in async contexts → always wrap via executor

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | discord.py 2.7.1 frozen behaviors match `master` branch source we read | Code Examples | Modal/TextInput limits could differ — but Discord API enforces 5/4000 server-side regardless |
| A2 | oMLX `response_format=json_object` honored by ShoeGPT across all future model swaps | Pitfall 4 | Defensive parser mitigates; pydantic validation catches edge cases |
| A3 | dm20's markdown format for `start_party_mode` is stable | Pattern 2 | Brittle if dm20 changes wording; regex tolerates whitespace but not radically different structure. Mitigation: add a smoke test against the live dm20 in CI |
| A4 | `manage_channels` is the right DM identifier | D-29 | If users prefer Discord roles, can switch to `has_role` check later; backwards-compat |
| A5 | Ingest budget of 8s holds with ShoeGPT on M3 Ultra | INGEST-11 | Live test showed ~2-3s for translate alone; OCR <2s typical; should hold |
| A6 | `dm20__list_locations` exists for the dedup check in Pitfall 7 | Pitfall 7 | If not exposed, fall back to "set populate_chapter_1=False on retry" UX |

## Open Questions

1. **dm20 idempotency strategy for `load_adventure`**
   - What we know: re-running with `populate_chapter_1=True` creates duplicate entities.
   - What's unclear: whether dm20 exposes a "module already bound" signal we can check first.
   - Recommendation: Use a heuristic — if `module_bound==True` was already set on a prior call (track in `channel_sessions` if needed), prompt the user before re-running.

2. **Player name binding on `create_character`**
   - What we know: CONTEXT D-13 says set `player_id=str(interaction.user.id)`.
   - What's unclear: dm20's `create_character` schema doesn't explicitly document a `player_id` field shape, though the import tools accept `player_name`. Need to inspect or test.
   - Recommendation: pass `player_id` and `player_name` both, let dm20 dedupe; verify in the Phase 3 integration smoke test.

3. **`start_party_mode` port collision**
   - What we know: dm20 returns "already running" if port 8080 is in use.
   - What's unclear: whether dm20 supports auto-port-selection or whether we must pass `port=8081, 8082, ...` and retry.
   - Recommendation: First call no `port` arg; on "already running", call `get_party_status` to reuse; on real port collision, surface to user.

## Sources

### Primary (HIGH confidence — source code inspected)

- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/main.py:4749` — `start_party_mode` returns markdown string with `**URL:**` and `**QR Code:**` lines per character
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/claudmaster/tools/session_tools.py:873` — `start_claudmaster_session` returns dict with `session_id`
- `/Users/shoemoney/Services/mcp-servers/dm20-protocol/src/dm20_protocol/adventures/tools.py:20` — `load_adventure_flow` populates Chapter 1 entities unconditionally when `populate_chapter_1=True`
- Live oMLX test (`POST :8765/v1/chat/completions` with `response_format=json_object`) — verified ShoeGPT returns clean JSON on character-sheet input (test executed 2026-05-21)
- `https://raw.githubusercontent.com/Rapptz/discord.py/master/discord/ui/modal.py` — `len(self._children) >= 5` raises `ValueError('maximum number of children exceeded (5)')`
- `https://raw.githubusercontent.com/Rapptz/discord.py/master/discord/ui/text_input.py` — label ≤45, placeholder ≤100, max_length 1-4000, default/value ≤4000
- `https://raw.githubusercontent.com/Rapptz/discord.py/master/discord/message.py` — `Attachment.read()` is async, buffers entire payload via `_http.get_from_cdn`, no streaming
- `https://raw.githubusercontent.com/Rapptz/discord.py/master/discord/app_commands/commands.py` — `autocomplete` decorator signature; coroutine returning ≤25 Choices

### Secondary (MEDIUM confidence — official docs cross-referenced)

- [ocrmac README on GitHub](https://github.com/straussmaximilian/ocrmac) — return shape `list[tuple[text, confidence, bbox]]`
- [EasyOCR README on GitHub](https://github.com/JaidedAI/EasyOCR) — `readtext(bytes_or_path)` returns `list[tuple[bbox, text, confidence]]`
- [PyMuPDF text extraction recipes](https://pymupdf.readthedocs.io/en/latest/recipes-text.html) — `get_text("dict")` for multi-column
- [segno PyPI page](https://pypi.org/project/segno/) — pure Python, ~76 KB wheel
- [qrcode PyPI page](https://pypi.org/project/qrcode/) — fallback option, requires Pillow
- [discord.py master Permissions](https://github.com/Rapptz/discord.py/blob/master/discord/permissions.py) — `manage_channels` attribute on `guild_permissions`
- PyPI version index (pip index versions) for ocrmac 1.0.1, easyocr 1.7.2, qrcode 8.2, segno 1.6.6, pymupdf 1.27.2.3, pypdf 6.12.0 — all VERIFIED 2026-05-21

### Tertiary (cross-confirmation)

- Discord API community discussion on Modal limits (5-component cap, 4000-char text input)
- ddmcpskills.md generated live from `oMLX :8765/v1/mcp/tools` — verified tool surface

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against pip index; existing project deps respected
- Architecture / dm20 return shapes: HIGH — read directly from dm20-protocol source
- discord.py API limits: HIGH — read from master branch source (2.7.1 is expected to be a frozen subset)
- oMLX JSON-mode behavior with ShoeGPT: HIGH — live test executed 2026-05-21 with both clean and dirty input; both returned valid JSON
- Idempotency of `load_adventure`: HIGH — read source code; confirmed re-runs duplicate entities
- OCR confidence aggregation strategy: MEDIUM — standard length-weighted mean; works in practice but no formal benchmark in this repo yet
- Phase 3 performance budget (<8s): MEDIUM — based on observed oMLX latency; OCR latency varies with image size

**Research date:** 2026-05-21
**Valid until:** 2026-06-20 (30 days for stable Python ecosystem; re-verify dm20 markdown format if dm20-protocol bumps minor version)
