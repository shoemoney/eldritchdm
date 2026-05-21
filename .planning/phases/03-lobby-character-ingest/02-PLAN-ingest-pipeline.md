---
phase: 03-lobby-character-ingest
plan: 02
type: execute
wave: 2
depends_on:
  - 03-01
files_modified:
  - pyproject.toml
  - src/eldritch_dm/ingest/__init__.py
  - src/eldritch_dm/ingest/schema.py
  - src/eldritch_dm/ingest/executor.py
  - src/eldritch_dm/ingest/ocr.py
  - src/eldritch_dm/ingest/pdf.py
  - src/eldritch_dm/ingest/translate.py
  - src/eldritch_dm/ingest/pipeline.py
  - src/eldritch_dm/mcp/tools.py
  - tests/ingest/__init__.py
  - tests/ingest/conftest.py
  - tests/ingest/test_schema.py
  - tests/ingest/test_executor.py
  - tests/ingest/test_ocr.py
  - tests/ingest/test_pdf.py
  - tests/ingest/test_translate.py
  - tests/ingest/test_pipeline.py
  - tests/mcp/test_tools.py
autonomous: true
requirements:
  - INGEST-03
  - INGEST-04
  - INGEST-05
  - INGEST-06
  - INGEST-07
  - INGEST-11
tags:
  - ingest
  - ocr
  - pdf
  - omlx
  - pydantic
  - executor

must_haves:
  truths:
    - "ingest/ is a fully isolated module: bot/ may import from it, but ingest/ never imports from bot/ or persistence/"
    - "CharacterSheet pydantic model validates ability scores in [1,30], levels in [1,20], and rejects malformed LLM JSON output before any dm20 call"
    - "OCR backend resolver picks ocrmac on macOS when available, easyocr when available, otherwise raises a typed UnavailableOCRBackend error — never silently degrades"
    - "OCR and PDF extraction always run in IngestExecutor.pool via loop.run_in_executor — never block the Discord event loop"
    - "translate_character_sheet calls oMLX with response_format=json_object, temperature=0.05, and the schema embedded in the system prompt; defensive markdown stripper handles ``` fences even though ShoeGPT verified-live doesn't emit them"
    - "pipeline.ingest(attachment_bytes, content_type, ...) returns an IngestResult with raw_text, parsed_sheet (or None), confidence_score, validation_warnings, ocr_backend"
    - "Confidence score is in [0.0, 1.0] composed of: +0.3 OCR quality, +0.3 pydantic clean, +0.2 class verified, +0.2 race verified — total tested at 1.0 for the happy path"
    - "End-to-end pipeline integration test (PNG → mocked OCR → respx-mocked oMLX → CharacterSheet → mock dm20 verify) runs in <100ms"
  artifacts:
    - path: "src/eldritch_dm/ingest/__init__.py"
      provides: "Public exports: ingest, IngestResult, CharacterSheet, AbilityScores"
      min_lines: 15
    - path: "src/eldritch_dm/ingest/schema.py"
      provides: "CharacterSheet + AbilityScores frozen pydantic models (D-24)"
      min_lines: 50
    - path: "src/eldritch_dm/ingest/executor.py"
      provides: "IngestExecutor singleton wrapping ThreadPoolExecutor(max_workers=2)"
      min_lines: 30
    - path: "src/eldritch_dm/ingest/ocr.py"
      provides: "OcrBackend resolver + run_ocrmac + run_easyocr + aggregate_*_confidence per RESEARCH §7+§8"
      min_lines: 90
    - path: "src/eldritch_dm/ingest/pdf.py"
      provides: "extract_pdf_text using PyMuPDF stream-mode get_text('blocks') with pypdf fallback per RESEARCH §9"
      min_lines: 50
    - path: "src/eldritch_dm/ingest/translate.py"
      provides: "async translate_to_character_sheet(raw_text) -> tuple[CharacterSheet | None, list[str]] (parsed_sheet, warnings)"
      min_lines: 60
    - path: "src/eldritch_dm/ingest/pipeline.py"
      provides: "async ingest(attachment_bytes, content_type, filename, *, player_name, user_id) -> IngestResult"
      min_lines: 80
    - path: "src/eldritch_dm/mcp/tools.py"
      provides: "translate_character_sheet wrapper (D-22)"
      contains: "async def translate_character_sheet"
  key_links:
    - from: "src/eldritch_dm/ingest/pipeline.py"
      to: "src/eldritch_dm/ingest/ocr.py"
      via: "ocr_resolve_backend → run_ocrmac OR run_easyocr inside IngestExecutor.pool"
      pattern: "loop\\.run_in_executor\\(IngestExecutor"
    - from: "src/eldritch_dm/ingest/pipeline.py"
      to: "src/eldritch_dm/ingest/translate.py"
      via: "translate_to_character_sheet after sanitize_player_input"
      pattern: "translate_to_character_sheet\\("
    - from: "src/eldritch_dm/ingest/translate.py"
      to: "src/eldritch_dm/mcp/tools.py"
      via: "translate_character_sheet wrapper (oMLX chat.completions.create with response_format=json_object)"
      pattern: "translate_character_sheet"
    - from: "src/eldritch_dm/ingest/translate.py"
      to: "src/eldritch_dm/safety/sanitizer.py"
      via: "sanitize_player_input wraps OCR text in <player_action> sentinels before oMLX call"
      pattern: "sanitize_player_input"
    - from: "pyproject.toml"
      to: "src/eldritch_dm/ingest"
      via: "new import-linter contract allowing bot → ingest, ingest → mcp + safety, but NOT ingest → bot or ingest → persistence"
      pattern: "ingest"
---

<objective>
Phase 3 Plan 02 — Character ingest pipeline module + oMLX JSON-mode translation wrapper.

Purpose: Build the hermetic `src/eldritch_dm/ingest/` subsystem that turns a Discord attachment (PNG/JPG/PDF) into a validated `CharacterSheet` pydantic model plus a confidence score. No Discord runtime deps, no persistence writes, no bot imports — the cog in Plan 03 will be the integration layer. This plan owns OCR backend selection, PDF parsing, oMLX JSON-mode translation, schema validation, and the public `ingest()` coroutine. It also adds the `translate_character_sheet` MCP wrapper required by D-22.

Output: 7 new files under `src/eldritch_dm/ingest/`, one new MCP wrapper, 5 test files in `tests/ingest/` (≥20-25 new tests), `segno` reference acknowledgment (segno was added in Plan 01), and an updated import-linter contract allowing `bot → ingest, ingest → mcp/safety`.
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

@src/eldritch_dm/mcp/tools.py
@src/eldritch_dm/mcp/client.py
@src/eldritch_dm/safety/sanitizer.py
@src/eldritch_dm/config.py
@pyproject.toml

<interfaces>
<!-- Contracts established in Plan 01 + Phase 1; Plan 02 builds on them. -->

From src/eldritch_dm/safety/sanitizer.py (Phase 1):
```python
def sanitize_player_input(raw: str, *, speaker: str | None = None, user_id: str | None = None) -> SanitizedInput
# Returns SanitizedInput with `.wrapped` property — a string already wrapped in <player_action> sentinels.
```

From src/eldritch_dm/mcp/client.py (Phase 1):
```python
class MCPClient:
    async def call(self, tool_name: str, **kwargs) -> dict[str, Any]
    # MCPClient holds an internal AsyncOpenAI client for non-MCP oMLX calls — verify by reading client.py
    # If MCPClient does NOT expose an oMLX client, create one inside translate.py from settings.OMLX_ENDPOINT
```
**ACTION**: Read `mcp/client.py` once at the top of Task 4. The `translate_character_sheet` wrapper in `mcp/tools.py` needs an `AsyncOpenAI` client. If Phase 1 didn't expose one, the wrapper accepts an `AsyncOpenAI` instance as its first positional arg (like other wrappers accept `MCPClient`). The cog in Plan 03 will construct one from settings — for Plan 02, the test mocks the client directly via respx.

From Plan 01 (just landed):
- `mcp/tools.py` has `list_characters`, `get_class_info`, `get_race_info` wrappers — Plan 02 uses get_class_info + get_race_info for the verification step in confidence scoring.

CharacterSheet contract (D-24 — implement exactly):
```python
# src/eldritch_dm/ingest/schema.py
from pydantic import BaseModel, ConfigDict, Field
from typing import Any

class AbilityScores(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    strength: int = Field(ge=1, le=30)
    dexterity: int = Field(ge=1, le=30)
    constitution: int = Field(ge=1, le=30)
    intelligence: int = Field(ge=1, le=30)
    wisdom: int = Field(ge=1, le=30)
    charisma: int = Field(ge=1, le=30)

class CharacterSheet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    name: str = Field(min_length=1, max_length=80)
    character_class: str = Field(min_length=1, max_length=40)
    class_level: int = Field(ge=1, le=20)
    race: str = Field(min_length=1, max_length=40)
    subclass: str | None = None
    subrace: str | None = None
    background: str | None = None
    alignment: str | None = None
    abilities: AbilityScores
    hp: int | None = Field(default=None, ge=1)
    ac: int | None = Field(default=None, ge=1)
    skills: list[str] = Field(default_factory=list, max_length=30)
    weapons: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    spells: list[str] = Field(default_factory=list, max_length=50)
```

IngestResult contract (Plan 03 consumes via cog):
```python
@dataclass(frozen=True)
class IngestResult:
    raw_text: str
    parsed_sheet: CharacterSheet | None    # None if pydantic validation failed
    confidence_score: float                 # [0.0, 1.0]
    validation_warnings: list[str]          # surfaced in review modal
    ocr_backend: str | None                 # "ocrmac" | "easyocr" | None (for PDFs)
    pdf_backend: str | None                 # "pymupdf" | "pypdf" | None (for images)
```

OCR backend return shapes (RESEARCH §7+§8 — VERIFIED):
- `ocrmac.OCR(image_path).recognize()` → `list[tuple[str, float, list[float]]]` where `(text, confidence, bbox)`.
- `easyocr.Reader(['en']).readtext(image_bytes)` → `list[tuple[list[list[int]], str, float]]` where `(bbox, text, confidence)`.

Confidence aggregation: length-weighted mean (D-26 components; see RESEARCH Pattern 3).
</interfaces>

<conventions>
- **Module hermetic boundary**: `src/eldritch_dm/ingest/` must NOT import from `eldritch_dm.bot` or `eldritch_dm.persistence`. It MAY import from `eldritch_dm.mcp`, `eldritch_dm.safety`, `eldritch_dm.config`, `eldritch_dm.logging`. Add a new import-linter contract.
- **Platform-conditional import for ocrmac (RESEARCH Pitfall 6)**: NEVER `import ocrmac` at module top. Always inside a function guarded by `sys.platform == "darwin"` plus `importlib.util.find_spec("ocrmac")`. Same for easyocr (so Linux dev machines without it don't crash test collection).
- **All OCR/PDF work via run_in_executor**: synchronous library calls (ocrmac.recognize, easyocr.readtext, fitz.open/get_text, pypdf.PdfReader) MUST be wrapped in `loop.run_in_executor(IngestExecutor.pool, ...)`. Direct calls on the event loop are a lint failure (we have no specific rule for this — enforce via code review + a test that asserts the executor is consulted).
- **No fenced code blocks inside `<action>`**: directive prose only. Implementation patterns are in this `<interfaces>` block and the referenced RESEARCH.md.
- **Atomic commit format**: `feat(03-lobby-character-ingest): <component>` per task; tests in matching `test(...)` commits, or interleaved within feat commits if they ship together (TDD allowed).
</conventions>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Schema (CharacterSheet, AbilityScores) + IngestResult + ingest package skeleton + pyproject deps + import-linter contract</name>
  <files>src/eldritch_dm/ingest/__init__.py, src/eldritch_dm/ingest/schema.py, pyproject.toml, tests/ingest/__init__.py, tests/ingest/test_schema.py</files>
  <behavior>
    Schema tests:
    - CharacterSheet validates a minimal valid dict (name, character_class, class_level, race, abilities with all 6 scores) → frozen instance.
    - AbilityScores rejects 0, 31, negative values per field.
    - class_level rejects 0 and 21.
    - Missing required field (e.g., abilities) raises pydantic ValidationError.
    - `frozen=True` enforced — attribute assignment raises.
    - `extra="ignore"` on CharacterSheet → unknown LLM fields don't crash (e.g., LLM includes "feats": [...]); `extra="forbid"` on AbilityScores → unknown ability keys (e.g., "luck") DO crash.
    - JSON schema generation via `CharacterSheet.model_json_schema()` returns a dict containing all required keys (used by D-23 schema embed).

    Package skeleton tests (in test_schema.py):
    - `from eldritch_dm.ingest import CharacterSheet, AbilityScores, IngestResult, ingest` works (the public API is curated in __init__.py).
    - `IngestResult` is a frozen dataclass; raises on attribute set.
  </behavior>
  <action>
    Create `src/eldritch_dm/ingest/__init__.py` exporting the public API: `CharacterSheet, AbilityScores, IngestResult, ingest`. Implementation files will be added by later tasks; for Task 1, only schema.py exists, so __init__.py re-exports from schema + a placeholder for `IngestResult` (define it in schema.py for now — refactor allowed in Task 7 to move to pipeline.py if it grows).

    Implement `src/eldritch_dm/ingest/schema.py` per the &lt;interfaces&gt; contract block — exact field constraints, frozen, model_config. Add an `IngestResult` dataclass with the fields documented in the &lt;interfaces&gt; block.

    Update `pyproject.toml`:
    1. Confirm `segno>=1.6,<2.0` was added by Plan 01 (grep — if missing, add it; otherwise leave alone).
    2. Confirm `PyMuPDF>=1.24,<2.0` and `pypdf>=4.3,<6.0` are already pinned (they were Phase 1 deps — confirm via grep).
    3. Confirm `mac-ocr` extra has `ocrmac>=1.0,<2.0` and `linux-ocr` extra has `easyocr>=1.7,<2.0` (already there per pyproject).
    4. Add `reportlab>=4.0,<5.0` to the `[dev]` extras for PDF fixture generation in tests/ingest/conftest.py (NEW dep).
    5. Add a new import-linter contract:
       - Name: "ingest must not import bot or persistence"
       - Type: forbidden
       - source_modules: `["eldritch_dm.ingest"]`
       - forbidden_modules: `["eldritch_dm.bot", "eldritch_dm.persistence"]`
    6. (Optional, defensive — adds to but doesn't replace existing contracts.) Document the allowed direction in a comment: `bot → ingest → mcp, safety`.

    Run `uv pip install -e ".[dev,mac-ocr]"` to pick up reportlab.

    Tests in `tests/ingest/test_schema.py`: ≥8 tests covering the behavior block. Use `pytest.raises(pydantic.ValidationError)` patterns matching Phase 1's persistence/test_models.py.

    Implements INGEST-07 (schema portion).
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/ingest/test_schema.py -x -q 2&gt;&amp;1 | tail -15 &amp;&amp; lint-imports 2&gt;&amp;1 | tail -10</automated>
  </verify>
  <done>schema.py + __init__.py exist; pyproject.toml has reportlab in [dev]; new import-linter contract present and green; ≥8 schema tests pass; the public API import works from any module.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: IngestExecutor singleton + tests/ingest/conftest.py fixtures (PNG + PDF generators, mock OCR backends, respx oMLX)</name>
  <files>src/eldritch_dm/ingest/executor.py, tests/ingest/conftest.py, tests/ingest/test_executor.py</files>
  <behavior>
    Executor tests:
    - `IngestExecutor.pool` returns the same `ThreadPoolExecutor` instance on repeated access (singleton).
    - `IngestExecutor.pool._max_workers == 2`.
    - Calling `await loop.run_in_executor(IngestExecutor.pool, _sync_fn, arg)` works in an asyncio test — proves the singleton is asyncio-friendly.
    - A `shutdown()` classmethod is callable in tests (not necessarily during prod; gracefully closes the pool).

    conftest fixtures (no direct tests; tested indirectly by Tasks 3-6):
    - `sample_png_bytes` fixture: a 200×200 PNG generated with Pillow, drawing "Aragorn / Ranger / Level 5" text. Returned as bytes.
    - `sample_pdf_bytes` fixture: a 1-page reportlab-generated PDF with similar text content. Returned as bytes.
    - `mock_ocrmac_regions` fixture: returns canned `[(text, confidence, bbox), ...]` list mimicking ocrmac output.
    - `mock_easyocr_regions` fixture: returns canned `[(bbox, text, confidence), ...]` list.
    - `respx_omlx` fixture: respx mock targeting `http://localhost:8765/v1/chat/completions` with a JSON-mode response payload (verified shape from RESEARCH §10).
  </behavior>
  <action>
    Implement `src/eldritch_dm/ingest/executor.py`:
    - Class `IngestExecutor` with class-level `_pool: ThreadPoolExecutor | None = None` and a classmethod `pool` (or `get_pool`) that lazy-creates `ThreadPoolExecutor(max_workers=2, thread_name_prefix="ingest")` on first access.
    - Classmethod `shutdown(wait: bool = True)` for graceful test cleanup.
    - Module-level singleton via class methods — no module-level instance to avoid import-time side effects.

    Implement `tests/ingest/conftest.py`:
    - `@pytest.fixture` `sample_png_bytes` using `Pillow.Image.new(mode="RGB", size=(200, 200), color="white")`, draw text via `ImageDraw.Draw(img).text((10, 10), "Aragorn\nRanger\nLevel 5\nSTR 15 DEX 18 CON 14", fill="black")`, save to BytesIO with `img.save(buf, format="PNG")`, return `buf.getvalue()`.
    - `@pytest.fixture` `sample_pdf_bytes` using `reportlab.pdfgen.canvas.Canvas(io.BytesIO()).drawString(x, y, "...").save()` pattern.
    - `@pytest.fixture` `mock_ocrmac_regions`: hardcoded list with 4 regions, mix of confidences (0.95, 0.92, 0.88, 0.6).
    - `@pytest.fixture` `mock_easyocr_regions`: hardcoded list with same content, easyocr tuple ordering.
    - `@pytest.fixture` `respx_omlx_mock`: uses respx to register a POST to `/v1/chat/completions` returning a JSON-mode response containing a clean CharacterSheet JSON in `choices[0].message.content`.

    Tests in `tests/ingest/test_executor.py`: 4 tests as listed in the behavior block.

    Implements INGEST-05 (executor) + test infrastructure for INGEST-03/04/06.
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/ingest/test_executor.py -x -q 2&gt;&amp;1 | tail -15</automated>
  </verify>
  <done>executor.py exists with the singleton pattern; conftest.py has all 5 fixtures usable from other test files; ≥4 executor tests pass; reportlab is importable.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: OCR module (ocrmac primary, easyocr fallback, length-weighted confidence aggregation, OcrBackend resolver)</name>
  <files>src/eldritch_dm/ingest/ocr.py, tests/ingest/test_ocr.py</files>
  <behavior>
    OCR tests (ALL mock the OCR libs per D-33 — never call real ocrmac/easyocr):
    - `aggregate_ocrmac_confidence([])` returns `("", 0.0)`.
    - `aggregate_ocrmac_confidence(mock_ocrmac_regions)` returns joined text + length-weighted mean confidence; assert numerically (e.g., expect `0.85` ± 0.01).
    - `aggregate_easyocr_confidence(mock_easyocr_regions)` similarly.
    - `resolve_ocr_backend()` on macOS with ocrmac importable returns `"ocrmac"`.
    - `resolve_ocr_backend()` on Linux with easyocr importable returns `"easyocr"`.
    - `resolve_ocr_backend()` on Linux without easyocr raises `UnavailableOCRBackend("OCR backend not installed; install ocrmac (macOS) or easyocr (Linux)")`.
    - `run_ocrmac(image_bytes)` (mocked) returns `(joined_text, confidence)` — assert it calls `ocrmac.OCR(...).recognize()` once and aggregates via `aggregate_ocrmac_confidence`.
    - `run_easyocr(image_bytes)` (mocked) returns `(joined_text, confidence)` — assert it calls `easyocr.Reader(['en'], gpu=False).readtext(image_bytes)`.
    - run_ocrmac uses a temp file via `tempfile.NamedTemporaryFile(suffix=".png")` because `ocrmac.OCR` expects a path, not bytes (verify by reading ocrmac docs/source if needed — RESEARCH §7 confirms this); temp file is deleted after.
    - Both run_* functions are SYNCHRONOUS (they're meant to be called inside `run_in_executor`).
  </behavior>
  <action>
    Implement `src/eldritch_dm/ingest/ocr.py` per RESEARCH §7+§8 and Pattern 3:

    - `class UnavailableOCRBackend(Exception): ...` — typed error for the resolver.
    - `def aggregate_ocrmac_confidence(regions: list[tuple[str, float, list[float]]]) -> tuple[str, float]` — length-weighted mean per RESEARCH Pattern 3.
    - `def aggregate_easyocr_confidence(regions: list[tuple[list[list[int]], str, float]]) -> tuple[str, float]` — same pattern, different tuple ordering.
    - `def _ocrmac_available() -> bool` — `sys.platform == "darwin"` + `importlib.util.find_spec("ocrmac") is not None`.
    - `def _easyocr_available() -> bool` — `importlib.util.find_spec("easyocr") is not None`.
    - `def resolve_ocr_backend() -> str` — returns "ocrmac" | "easyocr" or raises `UnavailableOCRBackend`.
    - `def run_ocrmac(image_bytes: bytes) -> tuple[str, float]` — writes bytes to NamedTemporaryFile, calls `ocrmac.OCR(temp.name).recognize()`, aggregates, deletes temp. Import ocrmac INSIDE the function (Pitfall 6).
    - `def run_easyocr(image_bytes: bytes) -> tuple[str, float]` — calls `easyocr.Reader(['en'], gpu=False).readtext(image_bytes)`, aggregates. The Reader is expensive to construct; cache as a module-level lazy `_get_easyocr_reader()` function with `functools.lru_cache(maxsize=1)`. Import easyocr INSIDE the function.

    Tests in `tests/ingest/test_ocr.py`: use `unittest.mock.patch` to inject fake `ocrmac.OCR` and `easyocr.Reader` (per D-33). Use the `mock_ocrmac_regions` and `mock_easyocr_regions` fixtures from conftest.py. ≥8 tests covering the behavior block.

    Implements INGEST-03 + INGEST-09 (confidence component).
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/ingest/test_ocr.py -x -q 2&gt;&amp;1 | tail -15</automated>
  </verify>
  <done>ocr.py implements resolver + both backends + aggregation; ≥8 ocr tests pass on macOS AND on a Linux CI by virtue of the platform-conditional imports never touching ocrmac at collection time; lint-imports stays green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: PDF module (PyMuPDF primary using stream-mode get_text("blocks") for multi-column, pypdf fallback)</name>
  <files>src/eldritch_dm/ingest/pdf.py, tests/ingest/test_pdf.py</files>
  <behavior>
    PDF tests:
    - `extract_pdf_text(sample_pdf_bytes)` returns joined non-empty text containing the expected fixture strings.
    - Stream-mode call uses `pymupdf.open(stream=BytesIO(b), filetype="pdf")` (NOT writing a temp file — RESEARCH "Anti-Patterns to Avoid").
    - Multi-column extraction uses `page.get_text("blocks")` then sorts blocks top-to-bottom, left-to-right, joining each block's text — per RESEARCH §9 (multi-column sheets need block-level extraction, not flat get_text()).
    - On `pymupdf.FileDataError` (corrupt PDF), falls back to `pypdf.PdfReader(BytesIO(b))` and extracts text via `page.extract_text()` per page.
    - On TOTAL failure (both backends raise), raises a typed `PdfExtractionError("PDF unparseable: pymupdf=..., pypdf=...")`.
    - Returns a tuple `(text: str, backend: Literal["pymupdf", "pypdf"])` so the pipeline can record which path was used.
    - Function is SYNCHRONOUS (intended for run_in_executor).
  </behavior>
  <action>
    Implement `src/eldritch_dm/ingest/pdf.py`:

    - `class PdfExtractionError(Exception): ...`.
    - `def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, str]` returning `(text, backend_name)`.
    - Primary path: `import pymupdf; doc = pymupdf.open(stream=BytesIO(pdf_bytes), filetype="pdf"); pages_text = []; for page in doc: blocks = page.get_text("blocks"); blocks.sort(key=lambda b: (b[1], b[0])); pages_text.append("\n".join(b[4].strip() for b in blocks if b[4].strip())); text = "\n\n".join(pages_text); doc.close(); return text, "pymupdf"`.
    - Fallback path on `Exception`: `import pypdf; reader = pypdf.PdfReader(BytesIO(pdf_bytes)); text = "\n\n".join(p.extract_text() or "" for p in reader.pages); return text, "pypdf"`.
    - If pypdf ALSO raises, raise `PdfExtractionError` with both inner exception strings.
    - Synchronous function (intended for `run_in_executor`).

    Tests in `tests/ingest/test_pdf.py`: use the `sample_pdf_bytes` fixture from conftest.py. Mock `pymupdf.open` to raise on the fallback test (use `unittest.mock.patch`). ≥6 tests covering the behavior block.

    Implements INGEST-04.
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/ingest/test_pdf.py -x -q 2&gt;&amp;1 | tail -15</automated>
  </verify>
  <done>pdf.py extracts text from reportlab-generated fixture via PyMuPDF primary path; fallback path tested via mocked pymupdf failure; ≥6 PDF tests pass; no temp files written (assert via patching `tempfile.NamedTemporaryFile` and confirming it's not called in pdf module).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: translate_character_sheet MCP wrapper + ingest/translate.py with defensive markdown stripper</name>
  <files>src/eldritch_dm/mcp/tools.py, src/eldritch_dm/ingest/translate.py, tests/mcp/test_tools.py, tests/ingest/test_translate.py</files>
  <behavior>
    translate_character_sheet wrapper tests (in test_tools.py):
    - Calls `openai_client.chat.completions.create(...)` with `model="ShoeGPT"`, `response_format={"type": "json_object"}`, `temperature=0.05`, `max_tokens=600`.
    - System prompt contains the substring "JSON object matching this schema" and the literal `CharacterSheet.model_json_schema()` JSON.
    - User message is the raw sanitized text (already wrapped in `<player_action>` sentinels by the caller).
    - On clean JSON response: returns parsed dict.
    - On JSON wrapped in ``` fences (Pitfall 4): defensive parser strips fences and returns dict.
    - On malformed JSON: raises `json.JSONDecodeError`.

    ingest/translate.py tests:
    - `translate_to_character_sheet(raw_text)`:
      1. Calls `sanitize_player_input(raw_text)` to get wrapped text.
      2. Calls `mcp.tools.translate_character_sheet(openai_client, wrapped_text)` — openai client constructed from settings.
      3. Validates result via `CharacterSheet.model_validate(result_dict)`.
      4. Returns `tuple[CharacterSheet | None, list[str]]` — (sheet, warnings); on validation error returns `(None, [str(error)])`.
    - Live mock via respx: a happy-path test feeds canned oMLX response with a valid CharacterSheet dict, asserts the returned sheet has the expected fields.
    - Validation failure test: oMLX returns a dict with `strength=99` (out of range), function returns `(None, ["strength must be ≤ 30"])` (or similar — exact wording matches pydantic's error format).
    - Markdown-wrapped response test: oMLX returns ```json...``` fenced output, defensive parser strips, validation passes.
  </behavior>
  <action>
    1. In `src/eldritch_dm/mcp/tools.py` (additive — don't break existing wrappers):
       - Add `CHARACTER_SHEET_SCHEMA_JSON = json.dumps(CharacterSheet.model_json_schema())` at module level (lazy via a function would be safer to avoid import cycle — use `_get_character_sheet_schema()` cached helper). **Import note**: importing from `eldritch_dm.ingest.schema` into `eldritch_dm.mcp.tools` is FORBIDDEN by import-linter (mcp must not import bot OR ingest by the new contract Task 1 added). Resolve by: option (a) define `translate_character_sheet` in `eldritch_dm/ingest/translate.py` instead of `mcp/tools.py` — moves the wrapper into the ingest module, which is allowed to import from mcp. **Choose option (a)**. Plan 02 builds the wrapper in `ingest/translate.py` and exports it; `mcp/tools.py` is unchanged for this MCP wrapper. Update CONTEXT D-22 narrative in the SUMMARY to note the relocation.
       - **CORRECTION** to D-22: CONTEXT placed the wrapper in `mcp/tools.py`. The import-linter contract from Task 1 forbids this. The wrapper lives in `ingest/translate.py` as a public function `translate_character_sheet(openai_client, wrapped_text)`. This is a documented deviation — call it out in the SUMMARY.

    2. In `src/eldritch_dm/ingest/translate.py`:
       - `TRANSLATE_SYSTEM_PROMPT` constant (multi-line) referencing the JSON schema string. Schema is generated via `_get_schema_json()` lazy helper returning `json.dumps(CharacterSheet.model_json_schema(), sort_keys=True)`.
       - `def _defensive_json_parse(s: str) -> dict` per RESEARCH Pitfall 4 (strip leading/trailing ``` fences, then `json.loads`).
       - `async def translate_character_sheet(openai_client: AsyncOpenAI, raw_text_wrapped: str, *, model: str = "ShoeGPT") -> dict` per RESEARCH "oMLX JSON-Mode Translation Wrapper" — exact body shown there.
       - `async def translate_to_character_sheet(raw_text: str, *, openai_client: AsyncOpenAI) -> tuple[CharacterSheet | None, list[str]]`:
         1. Wrap via `sanitize_player_input(raw_text)` (use `.wrapped` accessor — verify exact attribute in sanitizer.py).
         2. Call `translate_character_sheet(openai_client, wrapped)`.
         3. Try `CharacterSheet.model_validate(...)`. On ValidationError, format `[str(e) for e in error.errors()]` and return `(None, warnings)`.
         4. On JSONDecodeError from the LLM, return `(None, ["LLM returned unparseable JSON: ..."])`.

    3. Tests in `tests/ingest/test_translate.py` (≥6 tests): use respx fixture from conftest. Cover happy path, fenced-JSON path, validation failure (out-of-range ability), JSONDecodeError path, prompt structure assertion (system prompt contains schema), sanitizer integration (assert `<player_action>` sentinels appear in the request body).

    4. Tests in `tests/mcp/test_tools.py`: NO new wrapper to add (moved to translate.py per the correction above). Document this in the SUMMARY.

    Implements INGEST-06 + INGEST-07 (validation portion).
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/ingest/test_translate.py -x -q 2&gt;&amp;1 | tail -15 &amp;&amp; lint-imports 2&gt;&amp;1 | tail -10</automated>
  </verify>
  <done>ingest/translate.py implements both wrappers; ≥6 translate tests pass; lint-imports green (mcp does NOT import from ingest); SUMMARY captures the D-22 deviation rationale.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 6: pipeline.ingest() coroutine — end-to-end OCR/PDF → translate → validate → confidence score</name>
  <files>src/eldritch_dm/ingest/pipeline.py, tests/ingest/test_pipeline.py, src/eldritch_dm/ingest/__init__.py</files>
  <behavior>
    pipeline tests:
    - `await ingest(image_bytes, content_type="image/png", filename="aragorn.png", player_name="Jeremy", user_id="123", openai_client=mock, mcp_client=mock)`:
      1. Routes to OCR path (content_type starts with "image/").
      2. Resolves OCR backend → "ocrmac" (mocked).
      3. Calls run_ocrmac via `loop.run_in_executor(IngestExecutor.pool, run_ocrmac, image_bytes)` — assert via spy on run_in_executor.
      4. Returns `IngestResult(raw_text=..., parsed_sheet=CharacterSheet(...), confidence_score=1.0, validation_warnings=[], ocr_backend="ocrmac", pdf_backend=None)`.
    - PDF routing: content_type "application/pdf" → calls `extract_pdf_text` via run_in_executor; result has `pdf_backend="pymupdf"` and `ocr_backend=None`.
    - Magic-byte sniff (RESEARCH §5): if content_type lies (e.g., "image/png" but bytes start with "%PDF-"), the pipeline trusts the bytes and routes to PDF anyway. Add a `_sniff_kind(data: bytes, declared_ct: str) -> Literal["image", "pdf"]` helper.
    - Confidence assembly (D-26):
      * +0.3 if OCR confidence > 0.8 (mocked).
      * +0.3 if pydantic validation passes with no warnings.
      * +0.2 if `get_class_info(mcp, class_name=sheet.character_class)` returns non-error.
      * +0.2 if `get_race_info(mcp, race=sheet.race)` returns non-error.
    - On class/race "not found" responses (mocked), the corresponding 0.2 component is NOT added and a warning is appended to `validation_warnings` (e.g., "Class 'Witcher' not in 5e rules").
    - On validation failure: returns `IngestResult(parsed_sheet=None, confidence_score≈0.3, validation_warnings=[...])` — still useful for the manual-entry modal in Plan 03.
    - End-to-end test runtime <100ms per case (asyncio mocks; no real network/disk).
  </behavior>
  <action>
    Implement `src/eldritch_dm/ingest/pipeline.py`:

    - Public coroutine: `async def ingest(attachment_bytes: bytes, content_type: str | None, filename: str, *, player_name: str | None, user_id: str, openai_client: AsyncOpenAI, mcp_client: MCPClient) -> IngestResult`.
    - Magic-byte sniff via `_sniff_kind(data, declared_ct)` returning "image" or "pdf"; raise `ValueError("Unsupported file format")` on unknown bytes (PNG `\x89PNG\r\n\x1a\n`, JPEG `\xff\xd8\xff`, PDF `%PDF-`).
    - Image path: `backend = resolve_ocr_backend(); fn = run_ocrmac if backend == "ocrmac" else run_easyocr; raw_text, ocr_confidence = await loop.run_in_executor(IngestExecutor.pool, fn, attachment_bytes)`.
    - PDF path: `raw_text, pdf_backend = await loop.run_in_executor(IngestExecutor.pool, extract_pdf_text, attachment_bytes)`.
    - Translate: `sheet, warnings = await translate_to_character_sheet(raw_text, openai_client=openai_client)`.
    - Confidence components:
      * `ocr_quality = 0.3 if ocr_confidence > 0.8 else (0.15 if ocr_confidence > 0.5 else 0.0)` (graceful degradation).
      * `pydantic_clean = 0.3 if sheet is not None and not warnings else 0.0`.
      * If sheet is not None: `class_verified = 0.2 if (await mcp.tools.get_class_info(mcp_client, class_name=sheet.character_class)).get("found", True) else 0.0` — `.get("found", True)` defensive: dm20 may return error dict; the test stubs supply explicit shapes.
      * Same for race.
      * On class/race "not found", append warning string to `warnings`.
    - Return `IngestResult(...)` with all fields populated.

    Update `src/eldritch_dm/ingest/__init__.py` to re-export `ingest` from `pipeline.py`.

    Tests in `tests/ingest/test_pipeline.py` (≥6 tests): happy-path image, happy-path PDF, magic-byte override, class-not-found warning, pydantic-failure path, OCR-low-confidence partial score. Use AsyncMock + respx + executor spy.

    Implements INGEST-02 (routing), INGEST-09 (confidence + warnings), INGEST-11 (<100ms test runtime stands in for the 8s real budget; live measurement deferred to Plan 03's integration smoke).
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; pytest tests/ingest/test_pipeline.py -x -q 2&gt;&amp;1 | tail -20</automated>
  </verify>
  <done>pipeline.py implements ingest() with both image and PDF paths; ≥6 pipeline tests pass; all tests run in <2s aggregate; sniff helper handles polyglot/lying content_type; IngestResult populates all fields correctly.</done>
</task>

<task type="auto">
  <name>Task 7: Full-module test sweep + lint + commit hygiene</name>
  <files>tests/integration/test_phase1_smoke.py</files>
  <action>
    Verify the six prior-task commits are conventional-commit formatted (`feat(03-lobby-character-ingest): <component>`). If squashed, split.

    Run the full chain end-to-end:
    1. `ruff check src tests` — must be clean (treat any line-length or unused import as a fail).
    2. `lint-imports` — all contracts green, INCLUDING the new "ingest must not import bot or persistence" contract.
    3. `pytest -x -q` — full suite green; expect ≥270 tests passing (247 baseline from Plan 01 + ≥23 new from Plan 02).
    4. Smoke-grep: `grep -rn "from eldritch_dm.bot" src/eldritch_dm/ingest/` MUST return zero matches (hermetic boundary).
    5. Smoke-grep: `grep -rn "from eldritch_dm.persistence" src/eldritch_dm/ingest/` MUST return zero matches.

    Skim `tests/integration/test_phase1_smoke.py` — verify nothing in Plan 02 broke the Phase 1 smoke (the smoke doesn't touch ingest; should be untouched).

    No new code in this task.
  </action>
  <verify>
    <automated>cd /Users/shoemoney/Services/DiscordDM &amp;&amp; source .venv/bin/activate &amp;&amp; ruff check src tests &amp;&amp; lint-imports &amp;&amp; pytest -x -q 2&gt;&amp;1 | tail -6 &amp;&amp; ! grep -rn 'from eldritch_dm.bot\|from eldritch_dm.persistence' src/eldritch_dm/ingest/</automated>
  </verify>
  <done>Full pytest run reports ≥270 passing, ruff clean, lint-imports green, ingest is hermetic (grep returns 0 bot/persistence imports), six atomic commits visible in `git log --oneline | head -8`.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Discord attachment bytes → ingest | Untrusted file payload — could be malicious image, oversized PDF, polyglot, or zip bomb |
| OCR raw_text → oMLX translation | Untrusted player-supplied content — prompt-injection vector |
| oMLX JSON response → CharacterSheet | dm20's local model output is structurally trusted but values could be out of range or wrong types |
| dm20 get_class_info / get_race_info response | Trusted local source, but absence-of-class shouldn't break the pipeline |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-08 | Denial of Service | Player uploads a 100 MB PDF or 50 MP image | mitigate | 10 MB cap enforced in Plan 03 BEFORE attachment.read(); Plan 02's pipeline accepts bytes already-bounded — no defensive re-check needed but document the assumption in pipeline.py docstring |
| T-03-09 | Tampering | Prompt injection in OCR text (e.g., player draws "ignore previous instructions" on their character sheet) | mitigate | sanitize_player_input wraps in `<player_action>` sentinels; response_format=json_object discards prose; pydantic rejects out-of-schema fields |
| T-03-10 | Tampering | OCR fails entirely; raw_text is "" → LLM hallucinates a character | mitigate | confidence component for "OCR quality" is 0.0 when no regions; pydantic validation likely fails because LLM has nothing to extract; result is `(None, [...])` and Plan 03's cog routes to manual-entry modal |
| T-03-11 | Spoofing | Polyglot file (e.g., PDF with PNG magic bytes) | mitigate | `_sniff_kind` uses content magic bytes, not Discord-supplied content_type (Pitfall 5) |
| T-03-12 | Tampering | oMLX returns valid-shaped JSON but wrong values (`strength=999`) | mitigate | pydantic Field(ge=1, le=30) rejects; warnings surface to manual-review modal |
| T-03-13 | Information Disclosure | Confidence < 1.0 with "class not found" warning leaks dm20 internals | accept | Warning text is shown to the player anyway as part of the review UX — surfacing "Class 'Witcher' not in 5e rules" is intentional |
| T-03-SC | Tampering | npm/pip install of new deps (reportlab) | mitigate | reportlab is [VERIFIED] — 15+ yrs on PyPI, mature, MIT-equivalent. Direct add to pyproject.toml. |
</threat_model>

<verification>
- `pytest tests/ingest/ -x` passes (≥23 new tests)
- `pytest -x` (full suite) passes (≥270 tests)
- `ruff check src tests` clean
- `lint-imports` green (new "ingest must not import bot or persistence" contract enforced)
- `grep -rn 'from eldritch_dm.bot' src/eldritch_dm/ingest/` returns 0 matches
- `grep -rn 'from eldritch_dm.persistence' src/eldritch_dm/ingest/` returns 0 matches

## Source artifact coverage
- D-16: 6-stage pipeline shape ✓ (Task 6 — sniff → OCR/PDF → sanitize → translate → validate → confidence)
- D-17: ocrmac → easyocr → typed error ✓ (Task 3)
- D-18: content-type + magic-byte sniff for PDF detection ✓ (Task 6)
- D-19: ThreadPoolExecutor(max_workers=2) via IngestExecutor singleton ✓ (Task 2)
- D-20: Module layout under src/eldritch_dm/ingest/ ✓ (all tasks)
- D-21: Import-linter contract bot→ingest, ingest→mcp/safety ✓ (Task 1)
- D-22: oMLX wrapper — **DEVIATION**: relocated from mcp/tools.py to ingest/translate.py to honor "mcp must not import ingest" contract (documented in SUMMARY) ✓ (Task 5)
- D-23: Schema embedded in system prompt via model_json_schema() ✓ (Task 5)
- D-24: CharacterSheet + AbilityScores models with field ranges ✓ (Task 1)
- D-25: Class/race verification via get_class_info/get_race_info ✓ (Task 6)
- D-26..D-28: Confidence components + threshold (modal routing happens in Plan 03) ✓ (Task 6)
- D-32: Pillow/reportlab fixture generators ✓ (Task 2)
- D-33: unittest.mock for OCR libs ✓ (Task 3)
- D-34: respx for oMLX ✓ (Task 5)
- D-37: structlog binding contract (logging stubs in each module; structured logs verified via test that asserts log key names) ✓ (each task)
</verification>

<success_criteria>
1. `src/eldritch_dm/ingest/` is a fully hermetic module — no bot/ or persistence/ imports; verified by grep + lint-imports.
2. `CharacterSheet` and `AbilityScores` pydantic models enforce all D-24 field constraints.
3. OCR backend resolver picks ocrmac on macOS, easyocr on Linux, raises typed error otherwise.
4. PDF extraction uses PyMuPDF stream-mode with multi-column block sort, pypdf fallback.
5. `translate_to_character_sheet` calls oMLX with `response_format=json_object`, defensive fence-stripper, pydantic validation, returns warnings on failure.
6. `pipeline.ingest()` orchestrates the 6-stage pipeline end-to-end with confidence scoring per D-26.
7. ≥23 new tests pass; full suite stays green (≥270 total).
8. ruff clean, lint-imports green, no hermetic-boundary violations.
</success_criteria>

<risks>
- **D-22 deviation (mcp/tools.py vs ingest/translate.py).** import-linter rules forbid mcp importing from ingest. Resolved by relocating the wrapper to ingest/translate.py. Acceptance: SUMMARY documents this; tests for the wrapper live in tests/ingest/test_translate.py rather than tests/mcp/test_tools.py.
- **ocrmac OCR.recognize() needs a path, not bytes.** Mitigated by writing a NamedTemporaryFile inside `run_ocrmac` and cleaning up via try/finally. Acceptance: ocr test asserts the temp file is deleted on the happy path.
- **easyocr Reader construction is slow.** Cached at module level via `lru_cache`. Acceptance: a test asserts the Reader is constructed once across two calls.
- **load_adventure non-idempotency (RESEARCH §3) — TOP risk from CONTEXT — is handled in Plan 01, not here.** This plan inherits the assumption that Plan 01's `module_bound` tracker is correct.
- **Pillow/reportlab fixtures might be platform-flaky.** Both are pure-Python in their text-rendering paths; no native deps. If a CI run sees fixture drift, regenerate via the fixture function — the fixture isn't a golden file, it's a code generator.
</risks>

<dependencies>
- **Plan 01 (03-01)** — must land first. Provides: list_characters/get_class_info/get_race_info MCP wrappers (Task 6 confidence verification consumes them), bot attribute exposure (Plan 03 needs it, but Plan 02 itself doesn't touch bot/).
- External NEW: `reportlab>=4.0,<5.0` (added to `[dev]` extras in Task 1).
- External existing: `pymupdf`, `pypdf`, `pydantic`, `openai`, `tenacity`, `structlog`, `ocrmac` (mac-ocr extra), `easyocr` (linux-ocr extra) — all already pinned.
</dependencies>

<output>
Create `.planning/phases/03-lobby-character-ingest/03-02-SUMMARY.md` documenting:
- 7 new files under src/eldritch_dm/ingest/ + 5 new test files
- reportlab added to [dev] extras
- New import-linter contract: ingest must not import bot or persistence
- D-22 DEVIATION: translate_character_sheet wrapper relocated from mcp/tools.py to ingest/translate.py
- Test count delta (≥23 new); baseline maintained
- Plan 03 consumes: `ingest(attachment_bytes, content_type, filename, *, player_name, user_id, openai_client, mcp_client) -> IngestResult`
</output>
