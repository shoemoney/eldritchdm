"""Public ingest() coroutine — end-to-end OCR/PDF → translate → validate → confidence.

Accepts a Discord attachment as raw bytes, routes to OCR or PDF extraction,
translates the text to a CharacterSheet via the configured ingest backend
(oMLX, Ollama, or OpenRouter — selected by ``INGEST_BACKEND`` via
``Settings.resolve_ingest_config``; D-27), validates with pydantic, and
assembles a confidence score from four components (D-26).

Confidence components:
  +0.3  OCR quality   > 0.8 (0.15 if > 0.5)
  +0.3  Pydantic validation clean (sheet not None and no warnings)
  +0.2  Class verified via dm20 get_class_info
  +0.2  Race verified via dm20 get_race_info
  Max:  1.0

Public API:
    ingest(attachment_bytes, content_type, filename, *, player_name, user_id,
           openai_client, mcp_client) -> IngestResult
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from eldritch_dm.ingest.executor import get_executor
from eldritch_dm.ingest.ocr import (
    UnavailableOCRBackend,
    resolve_ocr_backend,
    run_easyocr,
    run_ocrmac,
)
from eldritch_dm.ingest.pdf import PdfExtractionError, extract_pdf_text
from eldritch_dm.ingest.schema import IngestResult
from eldritch_dm.ingest.translate import translate_to_character_sheet
from eldritch_dm.logging import get_logger
from eldritch_dm.mcp.tools import get_class_info, get_race_info

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from eldritch_dm.mcp.client import MCPClient

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Magic-byte sniffing
# ---------------------------------------------------------------------------

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PDF_MAGIC = b"%PDF-"


def _sniff_kind(data: bytes, declared_ct: str | None) -> Literal["image", "pdf"]:
    """Determine whether attachment bytes are an image or PDF.

    Magic bytes take priority over the declared content-type — Discord and
    browser content-type headers cannot be trusted (RESEARCH §5).

    Args:
        data:        Raw attachment bytes (only first 8 bytes are examined).
        declared_ct: MIME content-type string from the Discord attachment
                     (may be None or incorrect).

    Returns:
        "image" for PNG/JPEG, "pdf" for PDF.

    Raises:
        ValueError: If the bytes match no supported format.
    """
    head = data[:8]

    if head.startswith(_PDF_MAGIC):
        return "pdf"
    if head.startswith(_PNG_MAGIC) or head.startswith(_JPEG_MAGIC):
        return "image"

    # Fall through to content-type hint as secondary signal
    ct = (declared_ct or "").lower()
    if "pdf" in ct:
        return "pdf"
    if ct.startswith("image/"):
        return "image"

    raise ValueError(
        f"Unsupported file format: magic bytes {head[:4]!r}, content_type={declared_ct!r}"
    )


# ---------------------------------------------------------------------------
# Confidence assembly
# ---------------------------------------------------------------------------


def _ocr_quality_score(ocr_confidence: float) -> float:
    """Map raw OCR confidence to a pipeline component score."""
    if ocr_confidence > 0.8:
        return 0.3
    if ocr_confidence > 0.5:
        return 0.15
    return 0.0


async def _verify_class(
    mcp_client: MCPClient,
    class_name: str,
    warnings: list[str],
) -> float:
    """Check class with dm20 and return 0.2 on success, 0.0 on miss/error."""
    try:
        result = await get_class_info(mcp_client, class_name=class_name)
        if result.get("found", True):
            return 0.2
        warnings.append(f"Class '{class_name}' not recognised by dm20 5e rules")
        return 0.0
    except Exception as exc:
        log.debug("class_verify_error", class_name=class_name, error=str(exc))
        return 0.0


async def _verify_race(
    mcp_client: MCPClient,
    race: str,
    warnings: list[str],
) -> float:
    """Check race with dm20 and return 0.2 on success, 0.0 on miss/error."""
    try:
        result = await get_race_info(mcp_client, race=race)
        if result.get("found", True):
            return 0.2
        warnings.append(f"Race '{race}' not recognised by dm20 5e rules")
        return 0.0
    except Exception as exc:
        log.debug("race_verify_error", race=race, error=str(exc))
        return 0.0


# ---------------------------------------------------------------------------
# Public coroutine
# ---------------------------------------------------------------------------


async def ingest(
    attachment_bytes: bytes,
    content_type: str | None,
    filename: str,
    *,
    player_name: str | None,
    user_id: str,
    openai_client: AsyncOpenAI,
    mcp_client: MCPClient,
    model: str = "ShoeGPT",
) -> IngestResult:
    """End-to-end ingest pipeline: bytes → CharacterSheet + confidence score.

    Args:
        attachment_bytes: Raw bytes from the Discord attachment.
        content_type:     MIME type (may be None or wrong — magic bytes override).
        filename:         Original filename (for logging).
        player_name:      Player display name (for sanitizer audit context).
        user_id:          Discord user snowflake (for sanitizer audit context).
        openai_client:    Backend-agnostic AsyncOpenAI client. Pointed at oMLX,
                          Ollama, or OpenRouter — selected by ``INGEST_BACKEND``
                          via ``Settings.resolve_ingest_config()`` (D-27).
        mcp_client:       MCPClient for dm20 class/race verification (always
                          oMLX — dm20 MCP is not relocatable by INGEST_BACKEND).
        model:            Model id sent to the ingest backend. Resolved by
                          ``Settings.resolve_ingest_config().model``; defaults
                          to "ShoeGPT" for legacy test call sites (D-27).

    Returns:
        IngestResult with all fields populated.
    """
    executor = get_executor()

    log.info("ingest_start", filename=filename, content_type=content_type, user_id=user_id)

    # --- Step 1: Route to OCR or PDF extraction ---
    try:
        kind = _sniff_kind(attachment_bytes, content_type)
    except ValueError as exc:
        log.warning("ingest_unsupported_format", filename=filename, error=str(exc))
        return IngestResult(
            raw_text="",
            parsed_sheet=None,
            confidence_score=0.0,
            validation_warnings=[str(exc)],
            ocr_backend=None,
            pdf_backend=None,
        )

    raw_text = ""
    ocr_backend: str | None = None
    pdf_backend: str | None = None
    ocr_confidence = 0.0

    if kind == "image":
        backend_name = resolve_ocr_backend()
        if backend_name is None:
            raise UnavailableOCRBackend(
                "No OCR backend available. Install ocrmac (macOS) or easyocr (Linux)."
            )
        ocr_fn = run_ocrmac if backend_name == "ocrmac" else run_easyocr
        try:
            raw_text, ocr_confidence = await executor.run_sync(ocr_fn, attachment_bytes)
            ocr_backend = backend_name
        except Exception as exc:
            log.warning("ingest_ocr_error", backend=backend_name, error=str(exc))
            return IngestResult(
                raw_text="",
                parsed_sheet=None,
                confidence_score=0.0,
                validation_warnings=[f"OCR extraction failed: {exc}"],
                ocr_backend=backend_name,
                pdf_backend=None,
            )

    else:  # PDF
        try:
            raw_text, pdf_backend = await executor.run_sync(extract_pdf_text, attachment_bytes)
            ocr_confidence = 1.0  # PDF text extraction is deterministic; no quality score needed
        except PdfExtractionError as exc:
            log.warning("ingest_pdf_error", filename=filename, error=str(exc))
            return IngestResult(
                raw_text="",
                parsed_sheet=None,
                confidence_score=0.0,
                validation_warnings=[f"PDF extraction failed: {exc}"],
                ocr_backend=None,
                pdf_backend=None,
            )

    # --- Step 2: Translate to CharacterSheet via the ingest backend ---
    # The backend is selected by INGEST_BACKEND (omlx / ollama / openrouter).
    # The openai_client and model are resolved by the cog from Settings.
    sheet, translate_warnings = await translate_to_character_sheet(
        raw_text,
        openai_client,
        user_id=user_id,
        channel_id="ingest",
        speaker=player_name or "unknown_player",
        model=model,
    )

    # --- Step 3: Confidence assembly (D-26) ---
    all_warnings = list(translate_warnings)

    ocr_quality = _ocr_quality_score(ocr_confidence)
    pydantic_clean = 0.3 if (sheet is not None and not translate_warnings) else 0.0

    class_score = 0.0
    race_score = 0.0
    if sheet is not None:
        class_score = await _verify_class(mcp_client, sheet.character_class, all_warnings)
        race_score = await _verify_race(mcp_client, sheet.race, all_warnings)

    confidence = min(1.0, ocr_quality + pydantic_clean + class_score + race_score)

    log.info(
        "ingest_done",
        filename=filename,
        confidence=confidence,
        ocr_backend=ocr_backend,
        pdf_backend=pdf_backend,
        parsed=sheet is not None,
    )

    return IngestResult(
        raw_text=raw_text,
        parsed_sheet=sheet,
        confidence_score=confidence,
        validation_warnings=all_warnings,
        ocr_backend=ocr_backend,
        pdf_backend=pdf_backend,
    )
