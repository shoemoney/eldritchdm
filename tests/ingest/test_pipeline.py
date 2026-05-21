"""Unit tests for eldritch_dm.ingest.pipeline.

All external calls (OCR, PDF, oMLX, MCP) are mocked.
Tests verify routing logic, confidence scoring, and IngestResult fields.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from eldritch_dm.ingest.schema import IngestResult

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

VALID_ABILITIES = {
    "strength": 16,
    "dexterity": 14,
    "constitution": 15,
    "intelligence": 10,
    "wisdom": 12,
    "charisma": 8,
}

VALID_SHEET_DICT = {
    "name": "Aragorn",
    "character_class": "Ranger",
    "class_level": 5,
    "race": "Human",
    "abilities": VALID_ABILITIES,
}

PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
JPEG_MAGIC = b"\xff\xd8\xff" + b"\x00" * 100
PDF_MAGIC = b"%PDF-1.4\n" + b"\x00" * 100


def _make_openai_client(sheet_dict=None):
    """Return a mocked AsyncOpenAI client that returns sheet_dict as JSON content."""
    content = json.dumps(sheet_dict or VALID_SHEET_DICT)
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=resp)
    return client


def _make_mcp_client(class_found=True, race_found=True):
    """Return a mocked MCPClient for class/race verification."""
    client = MagicMock()
    class_result = {"found": class_found, "name": "Ranger"} if class_found else {"found": False}
    race_result = {"found": race_found, "name": "Human"} if race_found else {"found": False}
    client.call = AsyncMock(side_effect=lambda tool, **kwargs: (
        class_result if "class" in tool else race_result
    ))
    return client


# ---------------------------------------------------------------------------
# _sniff_kind
# ---------------------------------------------------------------------------


class TestSniffKind:
    def test_png_magic_bytes(self):
        from eldritch_dm.ingest.pipeline import _sniff_kind
        assert _sniff_kind(PNG_MAGIC, None) == "image"

    def test_jpeg_magic_bytes(self):
        from eldritch_dm.ingest.pipeline import _sniff_kind
        assert _sniff_kind(JPEG_MAGIC, None) == "image"

    def test_pdf_magic_bytes(self):
        from eldritch_dm.ingest.pipeline import _sniff_kind
        assert _sniff_kind(PDF_MAGIC, None) == "pdf"

    def test_pdf_magic_overrides_image_content_type(self):
        """PDF bytes must be treated as pdf even if content_type says image/png."""
        from eldritch_dm.ingest.pipeline import _sniff_kind
        assert _sniff_kind(PDF_MAGIC, "image/png") == "pdf"

    def test_image_content_type_used_when_no_magic(self):
        """Falls back to content_type hint when bytes don't match any magic."""
        from eldritch_dm.ingest.pipeline import _sniff_kind
        # A bytes blob that starts with PNG magic qualifies
        assert _sniff_kind(PNG_MAGIC, "image/jpeg") == "image"

    def test_unknown_bytes_raises(self):
        from eldritch_dm.ingest.pipeline import _sniff_kind
        with pytest.raises(ValueError, match="Unsupported"):
            _sniff_kind(b"\x00\x01\x02\x03", None)


# ---------------------------------------------------------------------------
# ingest() — image path
# ---------------------------------------------------------------------------


class TestIngestImagePath:
    async def test_png_routes_to_ocr(self):
        """PNG bytes → resolve_ocr_backend → run_ocrmac → translate → IngestResult."""
        from eldritch_dm.ingest.pipeline import ingest

        openai_client = _make_openai_client()
        mcp_client = _make_mcp_client()

        with (
            patch("eldritch_dm.ingest.pipeline.resolve_ocr_backend", return_value="ocrmac"),
            patch("eldritch_dm.ingest.pipeline.run_ocrmac", return_value=("Aragorn Ranger 5", 0.95)),
            patch("eldritch_dm.ingest.pipeline.get_executor") as mock_exec,
        ):
            mock_exec.return_value.run_sync = AsyncMock(return_value=("Aragorn Ranger 5", 0.95))

            result = await ingest(
                PNG_MAGIC,
                content_type="image/png",
                filename="sheet.png",
                player_name="Jeremy",
                user_id="123",
                openai_client=openai_client,
                mcp_client=mcp_client,
            )

        assert isinstance(result, IngestResult)
        assert result.ocr_backend == "ocrmac"
        assert result.pdf_backend is None
        assert result.parsed_sheet is not None
        assert result.parsed_sheet.name == "Aragorn"

    async def test_ocr_confidence_above_threshold_adds_score(self):
        """OCR confidence >0.8 should add 0.3 to the confidence score."""
        from eldritch_dm.ingest.pipeline import ingest

        openai_client = _make_openai_client()
        mcp_client = _make_mcp_client()

        with (
            patch("eldritch_dm.ingest.pipeline.resolve_ocr_backend", return_value="ocrmac"),
            patch("eldritch_dm.ingest.pipeline.get_executor") as mock_exec,
        ):
            mock_exec.return_value.run_sync = AsyncMock(return_value=("Aragorn text", 0.95))

            result = await ingest(
                PNG_MAGIC,
                content_type="image/png",
                filename="sheet.png",
                player_name="Jeremy",
                user_id="123",
                openai_client=openai_client,
                mcp_client=mcp_client,
            )

        # >0.8 confidence → +0.3 OCR component
        assert result.confidence_score >= 0.3

    async def test_ocr_confidence_below_threshold_partial_score(self):
        """OCR confidence 0.5-0.8 → +0.15 (partial), below 0.5 → +0.0."""
        from eldritch_dm.ingest.pipeline import ingest

        openai_client = _make_openai_client()
        mcp_client = _make_mcp_client()

        with (
            patch("eldritch_dm.ingest.pipeline.resolve_ocr_backend", return_value="easyocr"),
            patch("eldritch_dm.ingest.pipeline.get_executor") as mock_exec,
        ):
            # 0.6 confidence → partial credit (0.15)
            mock_exec.return_value.run_sync = AsyncMock(return_value=("Aragorn text", 0.6))

            result = await ingest(
                PNG_MAGIC,
                content_type="image/png",
                filename="sheet.png",
                player_name="Jeremy",
                user_id="123",
                openai_client=openai_client,
                mcp_client=mcp_client,
            )

        # 0.15 (ocr) + 0.3 (pydantic) + 0.2 (class) + 0.2 (race) = 0.85
        assert 0.1 <= result.confidence_score <= 1.0

    async def test_no_ocr_backend_raises(self):
        """resolve_ocr_backend returning None should raise UnavailableOCRBackend."""
        from eldritch_dm.ingest.ocr import UnavailableOCRBackend
        from eldritch_dm.ingest.pipeline import ingest

        openai_client = _make_openai_client()
        mcp_client = _make_mcp_client()

        with patch("eldritch_dm.ingest.pipeline.resolve_ocr_backend", return_value=None):
            with pytest.raises(UnavailableOCRBackend):
                await ingest(
                    PNG_MAGIC,
                    content_type="image/png",
                    filename="sheet.png",
                    player_name="Jeremy",
                    user_id="123",
                    openai_client=openai_client,
                    mcp_client=mcp_client,
                )


# ---------------------------------------------------------------------------
# ingest() — PDF path
# ---------------------------------------------------------------------------


class TestIngestPdfPath:
    async def test_pdf_routes_to_extract(self):
        """PDF bytes → extract_pdf_text → translate → IngestResult."""
        from eldritch_dm.ingest.pipeline import ingest

        openai_client = _make_openai_client()
        mcp_client = _make_mcp_client()

        with (
            patch("eldritch_dm.ingest.pipeline.get_executor") as mock_exec,
        ):
            mock_exec.return_value.run_sync = AsyncMock(
                return_value=("Aragorn Ranger Level 5 Human", "pymupdf")
            )

            result = await ingest(
                PDF_MAGIC,
                content_type="application/pdf",
                filename="sheet.pdf",
                player_name="Jeremy",
                user_id="123",
                openai_client=openai_client,
                mcp_client=mcp_client,
            )

        assert isinstance(result, IngestResult)
        assert result.pdf_backend == "pymupdf"
        assert result.ocr_backend is None
        assert result.parsed_sheet is not None

    async def test_pdf_magic_overrides_png_content_type(self):
        """PDF magic bytes must route to PDF pipeline regardless of content_type."""
        from eldritch_dm.ingest.pipeline import ingest

        openai_client = _make_openai_client()
        mcp_client = _make_mcp_client()

        with (
            patch("eldritch_dm.ingest.pipeline.get_executor") as mock_exec,
        ):
            mock_exec.return_value.run_sync = AsyncMock(
                return_value=("Aragorn text", "pymupdf")
            )

            result = await ingest(
                PDF_MAGIC,
                content_type="image/png",  # lying content_type
                filename="sheet.pdf",
                player_name="Jeremy",
                user_id="123",
                openai_client=openai_client,
                mcp_client=mcp_client,
            )

        assert result.pdf_backend is not None
        assert result.ocr_backend is None


# ---------------------------------------------------------------------------
# ingest() — confidence scoring (D-26)
# ---------------------------------------------------------------------------


class TestConfidenceScoring:
    async def test_happy_path_full_score(self):
        """All 4 components → confidence_score == 1.0."""
        from eldritch_dm.ingest.pipeline import ingest

        openai_client = _make_openai_client()
        mcp_client = _make_mcp_client(class_found=True, race_found=True)

        with (
            patch("eldritch_dm.ingest.pipeline.resolve_ocr_backend", return_value="ocrmac"),
            patch("eldritch_dm.ingest.pipeline.get_executor") as mock_exec,
        ):
            mock_exec.return_value.run_sync = AsyncMock(return_value=("Aragorn text", 0.95))

            result = await ingest(
                PNG_MAGIC,
                content_type="image/png",
                filename="sheet.png",
                player_name="Jeremy",
                user_id="123",
                openai_client=openai_client,
                mcp_client=mcp_client,
            )

        assert result.confidence_score == pytest.approx(1.0)
        assert result.validation_warnings == []

    async def test_class_not_found_adds_warning_and_reduces_score(self):
        """Class 'Witcher' not in 5e → -0.2 component + warning string."""
        from eldritch_dm.ingest.pipeline import ingest

        openai_client = _make_openai_client()
        mcp_client = _make_mcp_client(class_found=False, race_found=True)

        with (
            patch("eldritch_dm.ingest.pipeline.resolve_ocr_backend", return_value="ocrmac"),
            patch("eldritch_dm.ingest.pipeline.get_executor") as mock_exec,
        ):
            mock_exec.return_value.run_sync = AsyncMock(return_value=("text", 0.95))

            result = await ingest(
                PNG_MAGIC,
                content_type="image/png",
                filename="sheet.png",
                player_name="Jeremy",
                user_id="123",
                openai_client=openai_client,
                mcp_client=mcp_client,
            )

        # Without class component: 0.3 + 0.3 + 0.0 + 0.2 = 0.8
        assert result.confidence_score == pytest.approx(0.8)
        assert any("class" in w.lower() or "ranger" in w.lower() for w in result.validation_warnings)

    async def test_pydantic_failure_returns_none_sheet(self):
        """If pydantic validation fails, parsed_sheet is None and score is lower."""
        from eldritch_dm.ingest.pipeline import ingest

        # Provide dict with invalid abilities
        bad_dict = {**VALID_SHEET_DICT, "abilities": {
            "strength": 99, "dexterity": 10, "constitution": 10,
            "intelligence": 10, "wisdom": 10, "charisma": 10,
        }}
        openai_client = _make_openai_client(bad_dict)
        mcp_client = _make_mcp_client()

        with (
            patch("eldritch_dm.ingest.pipeline.resolve_ocr_backend", return_value="ocrmac"),
            patch("eldritch_dm.ingest.pipeline.get_executor") as mock_exec,
        ):
            mock_exec.return_value.run_sync = AsyncMock(return_value=("text", 0.95))

            result = await ingest(
                PNG_MAGIC,
                content_type="image/png",
                filename="sheet.png",
                player_name="Jeremy",
                user_id="123",
                openai_client=openai_client,
                mcp_client=mcp_client,
            )

        assert result.parsed_sheet is None
        # Without pydantic component (0.3 absent) + no class/race (can't verify)
        assert result.confidence_score < 0.5
        assert len(result.validation_warnings) > 0


# ---------------------------------------------------------------------------
# ingest() — IngestResult structure
# ---------------------------------------------------------------------------


class TestIngestResultStructure:
    async def test_result_fields_populated(self):
        """All IngestResult fields should be set after a successful ingest."""
        from eldritch_dm.ingest.pipeline import ingest

        openai_client = _make_openai_client()
        mcp_client = _make_mcp_client()

        with (
            patch("eldritch_dm.ingest.pipeline.resolve_ocr_backend", return_value="ocrmac"),
            patch("eldritch_dm.ingest.pipeline.get_executor") as mock_exec,
        ):
            mock_exec.return_value.run_sync = AsyncMock(return_value=("Aragorn text", 0.92))

            result = await ingest(
                PNG_MAGIC,
                content_type="image/png",
                filename="sheet.png",
                player_name="Jeremy",
                user_id="123",
                openai_client=openai_client,
                mcp_client=mcp_client,
            )

        assert isinstance(result.raw_text, str)
        assert len(result.raw_text) > 0
        assert isinstance(result.confidence_score, float)
        assert 0.0 <= result.confidence_score <= 1.0
        assert isinstance(result.validation_warnings, list)
        assert result.ocr_backend == "ocrmac"
        assert result.pdf_backend is None
