"""Unit tests for eldritch_dm.ingest.pipeline.

All external I/O is mocked:
  - OCR/PDF extraction via patched IngestExecutor.run_sync
  - oMLX translation (translate_to_character_sheet) via AsyncMock
  - MCP class/race verification (get_class_info / get_race_info) via AsyncMock
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from eldritch_dm.ingest.pipeline import _sniff_kind, ingest
from eldritch_dm.ingest.schema import AbilityScores, CharacterSheet, IngestResult

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_JPEG_MAGIC = b"\xff\xd8\xff" + b"\x00" * 100
_PDF_MAGIC = b"%PDF-1.4\n" + b"\x00" * 100

VALID_SHEET = CharacterSheet(
    name="Thalindra",
    character_class="Wizard",
    class_level=5,
    race="High Elf",
    abilities=AbilityScores(
        strength=8, dexterity=16, constitution=14,
        intelligence=18, wisdom=12, charisma=10,
    ),
    hp=35,
    ac=13,
)


def _make_patches(
    ocr_result: tuple = ("raw ocr text", 0.95),
    translate_result: tuple = (VALID_SHEET, []),
    class_found: bool = True,
    race_found: bool = True,
    ocr_backend: str = "ocrmac",
    pdf_result: tuple = ("pdf text", "pymupdf"),
):
    """Build an ExitStack with all the standard patches for ingest() tests."""
    sheet, warnings = translate_result

    stack = ExitStack()
    stack.enter_context(
        patch("eldritch_dm.ingest.pipeline.resolve_ocr_backend", return_value=ocr_backend)
    )

    # Patch IngestExecutor.run_sync to route to the right fake result
    async def _fake_run_sync(fn, *args):
        fn_name = getattr(fn, "__name__", repr(fn))
        if fn_name in ("run_ocrmac", "run_easyocr"):
            return ocr_result
        if fn_name == "extract_pdf_text":
            return pdf_result
        raise AssertionError(f"Unexpected fn in run_sync: {fn!r}")

    stack.enter_context(
        patch(
            "eldritch_dm.ingest.pipeline.get_executor",
            return_value=MagicMock(run_sync=AsyncMock(side_effect=_fake_run_sync)),
        )
    )
    stack.enter_context(
        patch(
            "eldritch_dm.ingest.pipeline.translate_to_character_sheet",
            new=AsyncMock(return_value=(sheet, list(warnings))),
        )
    )
    stack.enter_context(
        patch(
            "eldritch_dm.ingest.pipeline.get_class_info",
            new=AsyncMock(return_value={"found": class_found}),
        )
    )
    stack.enter_context(
        patch(
            "eldritch_dm.ingest.pipeline.get_race_info",
            new=AsyncMock(return_value={"found": race_found}),
        )
    )
    return stack


# ---------------------------------------------------------------------------
# _sniff_kind tests
# ---------------------------------------------------------------------------


class TestSniffKind:
    def test_png_magic_returns_image(self):
        assert _sniff_kind(_PNG_MAGIC, "image/png") == "image"

    def test_jpeg_magic_returns_image(self):
        assert _sniff_kind(_JPEG_MAGIC, "image/jpeg") == "image"

    def test_pdf_magic_returns_pdf(self):
        assert _sniff_kind(_PDF_MAGIC, "application/pdf") == "pdf"

    def test_pdf_magic_overrides_image_content_type(self):
        """Magic bytes take priority over the declared content-type."""
        assert _sniff_kind(_PDF_MAGIC, "image/png") == "pdf"

    def test_png_magic_overrides_pdf_content_type(self):
        """PNG magic bytes take priority even if Discord declares PDF."""
        assert _sniff_kind(_PNG_MAGIC, "application/pdf") == "image"

    def test_unknown_magic_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            _sniff_kind(b"\x00\x01\x02\x03" * 10, "application/octet-stream")


# ---------------------------------------------------------------------------
# ingest() — image path
# ---------------------------------------------------------------------------


class TestIngestImagePath:
    async def test_happy_path_image_ocrmac(self, png_bytes):
        """PNG bytes -> OCR path, IngestResult with ocr_backend='ocrmac'."""
        with _make_patches(
            ocr_result=("Thalindra Wizard 5", 0.95),
            translate_result=(VALID_SHEET, []),
            class_found=True,
            race_found=True,
        ):
            result = await ingest(
                png_bytes,
                content_type="image/png",
                filename="sheet.png",
                player_name="Jeremy",
                user_id="123",
                openai_client=MagicMock(),
                mcp_client=MagicMock(),
            )

        assert isinstance(result, IngestResult)
        assert result.parsed_sheet is not None
        assert result.ocr_backend == "ocrmac"
        assert result.pdf_backend is None
        # ocr=0.3 + pydantic=0.3 + class=0.2 + race=0.2 = 1.0
        assert result.confidence_score == pytest.approx(1.0)

    async def test_unsupported_bytes_returns_zero_confidence(self):
        """Unknown magic bytes -> IngestResult with confidence 0 and warning.

        Uses content_type=application/octet-stream so the _sniff_kind fallback
        to declared content-type also fails to identify a kind, exercising the
        ValueError-path. (Phase 14 / FLAKE-01: previously this test used
        content_type=image/png and relied on ocrmac being installed to raise
        UnavailableOCRBackend; now we exercise the documented error path.)
        """
        bad_bytes = b"\x00\x01\x02\x03" * 20
        result = await ingest(
            bad_bytes,
            content_type="application/octet-stream",
            filename="garbage.bin",
            player_name="Test",
            user_id="456",
            openai_client=MagicMock(),
            mcp_client=MagicMock(),
        )
        assert result.confidence_score == 0.0
        assert result.parsed_sheet is None
        assert len(result.validation_warnings) > 0


# ---------------------------------------------------------------------------
# ingest() — PDF path
# ---------------------------------------------------------------------------


class TestIngestPdfPath:
    async def test_happy_path_pdf(self):
        """PDF bytes -> PDF path, IngestResult with pdf_backend set."""
        with _make_patches(
            pdf_result=("pdf extracted text", "pymupdf"),
            translate_result=(VALID_SHEET, []),
            class_found=True,
            race_found=True,
        ):
            result = await ingest(
                _PDF_MAGIC,
                content_type="application/pdf",
                filename="sheet.pdf",
                player_name="DM",
                user_id="789",
                openai_client=MagicMock(),
                mcp_client=MagicMock(),
            )

        assert isinstance(result, IngestResult)
        assert result.pdf_backend == "pymupdf"
        assert result.ocr_backend is None
        # PDF ocr_confidence=1.0 -> ocr_quality=0.3 + pydantic=0.3 + class=0.2 + race=0.2 = 1.0
        assert result.confidence_score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Confidence score assembly
# ---------------------------------------------------------------------------


class TestConfidenceScoreAssembly:
    async def test_full_confidence_all_passes(self, png_bytes):
        """OCR>0.8 + clean validate + class found + race found -> 1.0."""
        with _make_patches(
            ocr_result=("text", 0.95),
            translate_result=(VALID_SHEET, []),
            class_found=True,
            race_found=True,
        ):
            result = await ingest(
                png_bytes, content_type="image/png", filename="s.png",
                player_name="Alice", user_id="1",
                openai_client=MagicMock(), mcp_client=MagicMock(),
            )
        assert result.confidence_score == pytest.approx(1.0)

    async def test_class_not_found_reduces_score_and_adds_warning(self, png_bytes):
        """Unknown class -> -0.2 and warning added."""
        with _make_patches(
            ocr_result=("text", 0.95),
            translate_result=(VALID_SHEET, []),
            class_found=False,
            race_found=True,
        ):
            result = await ingest(
                png_bytes, content_type="image/png", filename="s.png",
                player_name="Bob", user_id="2",
                openai_client=MagicMock(), mcp_client=MagicMock(),
            )
        # ocr=0.3 + pydantic=0.3 + class=0.0 + race=0.2 = 0.8
        assert result.confidence_score == pytest.approx(0.8)
        assert any("Class" in w for w in result.validation_warnings)

    async def test_pydantic_failure_gives_low_score(self, png_bytes):
        """Failed translation (None sheet) -> low confidence, no class/race check."""
        with _make_patches(
            ocr_result=("text", 0.95),
            translate_result=(None, ["class_level: must be <= 20"]),
        ):
            result = await ingest(
                png_bytes, content_type="image/png", filename="s.png",
                player_name="Charlie", user_id="3",
                openai_client=MagicMock(), mcp_client=MagicMock(),
            )
        # sheet is None -> pydantic=0.0, class=0.0, race=0.0; ocr=0.3
        assert result.confidence_score == pytest.approx(0.3)
        assert result.parsed_sheet is None
        assert len(result.validation_warnings) > 0

    async def test_low_ocr_confidence_zero_score(self, png_bytes):
        """OCR confidence < 0.5 -> ocr_quality = 0.0."""
        with _make_patches(
            ocr_result=("text", 0.3),  # < 0.5
            translate_result=(VALID_SHEET, []),
            class_found=True,
            race_found=True,
        ):
            result = await ingest(
                png_bytes, content_type="image/png", filename="s.png",
                player_name="Diana", user_id="4",
                openai_client=MagicMock(), mcp_client=MagicMock(),
            )
        # ocr=0.0 + pydantic=0.3 + class=0.2 + race=0.2 = 0.7
        assert result.confidence_score == pytest.approx(0.7)

    async def test_medium_ocr_confidence_partial_score(self, png_bytes):
        """OCR confidence 0.5 < x <= 0.8 -> ocr_quality = 0.15."""
        with _make_patches(
            ocr_result=("text", 0.65),  # 0.5 < 0.65 <= 0.8
            translate_result=(VALID_SHEET, []),
            class_found=True,
            race_found=True,
        ):
            result = await ingest(
                png_bytes, content_type="image/png", filename="s.png",
                player_name="Eve", user_id="5",
                openai_client=MagicMock(), mcp_client=MagicMock(),
            )
        # ocr=0.15 + pydantic=0.3 + class=0.2 + race=0.2 = 0.85
        assert result.confidence_score == pytest.approx(0.85)
