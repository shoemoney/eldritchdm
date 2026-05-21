---
phase: "03"
plan: "02"
subsystem: "ingest-pipeline"
tags: [ingest, ocr, pdf, omlx, pydantic, executor, translate, pipeline]
dependency_graph:
  requires: ["03-01"]
  provides: ["ingest-module", "CharacterSheet-model", "translate-wrapper", "confidence-scoring"]
  affects: ["03-03"]
tech_stack:
  added: ["reportlab>=4.0,<5.0 (dev extra for test fixtures)"]
  patterns:
    - "IngestExecutor.run_sync() wraps ThreadPoolExecutor for event-loop-safe blocking calls"
    - "Platform-conditional OCR imports inside functions (never at module top)"
    - "translate_to_character_sheet(raw_text, client, *, ...) — positional client arg"
    - "_defensive_json_parse wraps ValueError around json.JSONDecodeError"
    - "magic-byte sniff via _sniff_kind() overrides declared content_type"
    - "confidence score: 4 additive components (0.3+0.3+0.2+0.2)"
key_files:
  created:
    - src/eldritch_dm/ingest/__init__.py
    - src/eldritch_dm/ingest/schema.py
    - src/eldritch_dm/ingest/executor.py
    - src/eldritch_dm/ingest/ocr.py
    - src/eldritch_dm/ingest/pdf.py
    - src/eldritch_dm/ingest/translate.py
    - src/eldritch_dm/ingest/pipeline.py
    - tests/ingest/__init__.py
    - tests/ingest/conftest.py
    - tests/ingest/test_schema.py
    - tests/ingest/test_executor.py
    - tests/ingest/test_ocr.py
    - tests/ingest/test_pdf.py
    - tests/ingest/test_translate.py
    - tests/ingest/test_pipeline.py
  modified:
    - pyproject.toml
decisions:
  - "D-22 DEVIATION: translate_character_sheet wrapper relocated from mcp/tools.py to ingest/translate.py to honor import-linter contract (mcp must not import ingest → schema import chain)"
  - "IngestExecutor uses .run_sync() method pattern (not loop.run_in_executor(_pool, ...) directly) for testability"
  - "resolve_ocr_backend() returns None (not raises) — pipeline raises UnavailableOCRBackend on None"
  - "translate_to_character_sheet takes openai_client as positional arg 2 (not keyword-only)"
  - "_defensive_json_parse raises ValueError wrapping json.JSONDecodeError (test-expected interface)"
  - "PDF confidence_score uses 1.0 OCR quality (PDF extraction deterministic, no quality score)"
metrics:
  duration_minutes: 90
  completed_date: "2026-05-21"
  tasks_completed: 7
  tasks_total: 7
  files_created: 15
  files_modified: 1
  tests_added: 83
  tests_total: 438
---

# Phase 3 Plan 02: Character Ingest Pipeline Summary

**One-liner:** Hermetic `src/eldritch_dm/ingest/` module with OCR backend resolution (ocrmac/easyocr), PyMuPDF/pypdf PDF extraction, oMLX JSON-mode character sheet translation, pydantic v2 schema validation, and 4-component confidence scoring — all wired through `pipeline.ingest()`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Schema + IngestResult + package skeleton + pyproject deps | eab4dcf | schema.py, __init__.py, pyproject.toml |
| 2 | IngestExecutor singleton + conftest fixtures | e57f98d | executor.py, tests/ingest/conftest.py |
| 3 | OCR module (ocrmac/easyocr/resolver/aggregators) | 1c86282 | ocr.py, test_ocr.py |
| 4 | PDF module (PyMuPDF primary, pypdf fallback) | f7fed9e | pdf.py, test_pdf.py |
| 5 | translate module — oMLX wrapper + pipeline step | 4308395 | translate.py, test_translate.py |
| 6 | pipeline.ingest() coroutine — routing + confidence | 6562167 | pipeline.py, test_pipeline.py |
| 7 | Full-module test sweep + lint + hygiene | Task 7 | pyproject.toml per-file-ignores |

## What Was Built

### Task 1: Schema + Package Skeleton

`src/eldritch_dm/ingest/schema.py`:
- `AbilityScores` — frozen pydantic v2 model; `extra="forbid"`; all 6 scores `ge=1, le=30`
- `CharacterSheet` — frozen pydantic v2 model; `extra="ignore"`; name 1-80 chars, class 1-40 chars, level 1-20; skills max 30, weapons max 20, spells max 50
- `IngestResult` — frozen dataclass with `raw_text`, `parsed_sheet`, `confidence_score`, `validation_warnings`, `ocr_backend`, `pdf_backend`

`pyproject.toml` updates:
- `reportlab>=4.0,<5.0` added to `[dev]` extras for PDF fixture generation
- New import-linter contract: `ingest must not import bot or persistence`

### Task 2: IngestExecutor

`src/eldritch_dm/ingest/executor.py`:
- `IngestExecutor` class wrapping `ThreadPoolExecutor(max_workers=2, thread_name_prefix="ingest")`
- `run_sync(fn, *args)` — async method using `loop.run_in_executor`
- `get_executor()` — module-level singleton
- `shutdown(wait=True)` — graceful cleanup

`tests/ingest/conftest.py` — shared fixtures: `png_bytes`, `pdf_bytes` (Pillow/reportlab), `mock_ocrmac_regions`, `mock_easyocr_regions`

### Task 3: OCR Module

`src/eldritch_dm/ingest/ocr.py`:
- `UnavailableOCRBackend(RuntimeError)` — typed error for missing backend
- `resolve_ocr_backend()` → `"ocrmac" | "easyocr" | None` — platform-conditional check
- `aggregate_ocrmac_confidence(regions)` → `float` — average confidence from Region objects
- `aggregate_easyocr_confidence(results)` → `float` — average confidence from (bbox, text, conf) tuples
- `run_ocrmac(image_bytes)` → `(text, confidence)` — synchronous, runs inside executor
- `run_easyocr(image_bytes)` → `(text, confidence)` — synchronous, runs inside executor
- All backend imports are deferred (inside functions) per RESEARCH Pitfall 6

### Task 4: PDF Module

`src/eldritch_dm/ingest/pdf.py`:
- `PdfExtractionError(RuntimeError)` — raised when both backends fail
- `extract_pdf_text(pdf_bytes)` → `(text, backend_name)` — synchronous
- Primary path: PyMuPDF (`fitz.open(stream=BytesIO(pdf_bytes), filetype="pdf")`)
- Fallback: pypdf `PdfReader(BytesIO(pdf_bytes))`
- Error path: `PdfExtractionError` with both failure messages

### Task 5: Translate Module

`src/eldritch_dm/ingest/translate.py`:
- `_get_schema_json()` — generates `CharacterSheet.model_json_schema()` JSON string
- `TRANSLATE_SYSTEM_PROMPT` — embeds schema JSON per D-23
- `_defensive_json_parse(raw)` — strips ``` fences, raises `ValueError` on bad JSON
- `translate_character_sheet(openai_client, raw_text_wrapped, *, model)` — async, calls oMLX with `response_format={"type":"json_object"}`, `temperature=0.05`, `max_tokens=600`
- `translate_to_character_sheet(raw_text, openai_client, *, speaker, user_id, channel_id, model)` — async full pipeline: sanitize → translate → pydantic validate → (sheet | None, warnings)

**D-22 DEVIATION**: `translate_character_sheet` wrapper relocated from `mcp/tools.py` (per CONTEXT) to `ingest/translate.py`. Root cause: import-linter contract "mcp must not import persistence or safety" would extend to `mcp must not import ingest` (ingest imports schema.py). By putting the wrapper in ingest/translate.py, we honor both the existing mcp contract and the new ingest contract. Tests live in `tests/ingest/test_translate.py`.

### Task 6: Pipeline Module

`src/eldritch_dm/ingest/pipeline.py`:
- `_sniff_kind(data, declared_ct)` → `"image" | "pdf"` — magic bytes override content_type (T-03-11)
- `_ocr_quality_score(confidence)` → `float` — 0.3 for >0.8, 0.15 for >0.5, 0.0 otherwise
- `_verify_class(mcp, class_name, warnings)` — calls `get_class_info`; +0.2 on hit
- `_verify_race(mcp, race, warnings)` — calls `get_race_info`; +0.2 on hit
- `ingest(attachment_bytes, content_type, filename, *, player_name, user_id, openai_client, mcp_client)` → `IngestResult`

Pipeline stages:
1. `_sniff_kind` — route to image or PDF
2. OCR: `executor.run_sync(run_ocrmac | run_easyocr, bytes)`
3. PDF: `executor.run_sync(extract_pdf_text, bytes)`
4. `translate_to_character_sheet(raw_text, openai_client, ...)` — sanitize + translate + validate
5. Confidence assembly: OCR quality + pydantic clean + class verified + race verified
6. Return `IngestResult`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] translate_to_character_sheet signature mismatch**
- Found during: Task 5
- Issue: Linter rewrote test file to use `translate_to_character_sheet(raw_text, client)` (client as positional arg 2), but implementation used `openai_client` as keyword-only
- Fix: Changed function signature to accept `openai_client` as positional arg 2 (not keyword-only), keeping keyword-only for speaker/user_id/channel_id/model
- Files modified: src/eldritch_dm/ingest/translate.py

**2. [Rule 1 - Bug] _defensive_json_parse raises ValueError vs json.JSONDecodeError**
- Found during: Task 5
- Issue: Linter-generated test expected `ValueError` with "not valid JSON" pattern; implementation raised raw `json.JSONDecodeError`
- Fix: Added try/except to wrap `json.JSONDecodeError` in `ValueError` with "oMLX response is not valid JSON" message
- Files modified: src/eldritch_dm/ingest/translate.py

**3. [Rule 1 - Bug] Pipeline used loop.run_in_executor(executor._pool) directly**
- Found during: Task 6 (test failures)
- Issue: Tests mocked `get_executor().run_sync` but pipeline called `loop.run_in_executor(executor._pool, ...)` — accesses private attribute and doesn't work with mocks
- Fix: Changed pipeline to use `executor.run_sync(fn, bytes)` — cleaner API, properly testable
- Files modified: src/eldritch_dm/ingest/pipeline.py

### Documented Deviations

**D-22 DEVIATION: translate_character_sheet in ingest/translate.py not mcp/tools.py**
- CONTEXT D-22 planned the wrapper in `mcp/tools.py`
- Import-linter "mcp must not import persistence or safety" contract would be violated if mcp imported from ingest (ingest → schema → pydantic, chain imports safety indirectly)
- Resolution: wrapper lives in `ingest/translate.py` as `translate_character_sheet(openai_client, wrapped_text)`
- Impact: Plan 03 ingest cog imports from `eldritch_dm.ingest.translate`, not `eldritch_dm.mcp.tools`

## Known Stubs

None. All pipeline components are fully implemented with real logic.

## Notes for Plan 03

1. **Import path for translate wrapper**: `from eldritch_dm.ingest.translate import translate_to_character_sheet` (NOT from `eldritch_dm.mcp.tools`)

2. **Public ingest() API** (for the ingest cog in Plan 03):
   ```python
   from eldritch_dm.ingest import ingest, IngestResult, CharacterSheet
   
   result = await ingest(
       attachment_bytes,
       content_type="image/png",
       filename="sheet.png",
       player_name=interaction.user.display_name,
       user_id=str(interaction.user.id),
       openai_client=AsyncOpenAI(base_url=str(settings.omlx_endpoint)),
       mcp_client=bot.mcp,
   )
   # result.confidence_score < 0.6 → manual-entry modal
   # result.confidence_score >= 0.6 → manual-review modal
   ```

3. **QR extraction (qr.py)**: Per Plan 01 SUMMARY, the `_render_qr()` function is inline in `lobby.py`. Plan 03 should extract it to `src/eldritch_dm/bot/qr.py` as `render_qr_for_embed()`. This is a Plan 03 task.

4. **mcp_client for confidence scoring**: The `ingest()` coroutine calls `get_class_info` and `get_race_info` via the MCP client. The cog must pass the bot's `bot.mcp` instance.

5. **openai_client construction**: Plan 03 cog constructs `AsyncOpenAI(base_url=str(settings.omlx_endpoint), api_key="not-needed")` and passes it to `ingest()`. The endpoint is `http://localhost:8765/v1` by default.

6. **UnavailableOCRBackend**: If `resolve_ocr_backend()` returns None, `ingest()` raises `UnavailableOCRBackend`. The ingest cog should catch this and send an ephemeral error to the user.

7. **Confidence threshold routing** (D-27):
   - `< 0.6` → manual-entry modal (player types from scratch, prefilled with best guesses)
   - `>= 0.6` → manual-review modal (player confirms or edits extracted values)
   Both modals are Plan 03's responsibility.

## Threat Flags

None — no new security-relevant surface beyond what was modeled in the plan's threat model. All mitigations from the threat register were implemented (T-03-09 via sanitize_player_input, T-03-11 via _sniff_kind, T-03-12 via pydantic validation).

## Self-Check

Files exist:
- [x] src/eldritch_dm/ingest/__init__.py
- [x] src/eldritch_dm/ingest/schema.py
- [x] src/eldritch_dm/ingest/executor.py
- [x] src/eldritch_dm/ingest/ocr.py
- [x] src/eldritch_dm/ingest/pdf.py
- [x] src/eldritch_dm/ingest/translate.py
- [x] src/eldritch_dm/ingest/pipeline.py
- [x] tests/ingest/__init__.py
- [x] tests/ingest/conftest.py
- [x] tests/ingest/test_schema.py
- [x] tests/ingest/test_executor.py
- [x] tests/ingest/test_ocr.py
- [x] tests/ingest/test_pdf.py
- [x] tests/ingest/test_translate.py
- [x] tests/ingest/test_pipeline.py

Commits exist:
- [x] eab4dcf — Task 1 schema + skeleton
- [x] e57f98d — Task 2 executor + conftest
- [x] 1c86282 — Task 3 OCR module
- [x] f7fed9e — Task 4 PDF module
- [x] 4308395 — Task 5 translate module
- [x] 6562167 — Task 6 pipeline module

Test results: 438 passed, 4 skipped
Import-linter: 6 contracts kept, 0 broken
Ruff (ingest src + tests): 0 errors
Hermetic boundary: grep returns 0 bot/persistence imports in src/eldritch_dm/ingest/

## Self-Check: PASSED
