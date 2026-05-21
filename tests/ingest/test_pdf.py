"""Unit tests for eldritch_dm.ingest.pdf."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from eldritch_dm.ingest.pdf import PdfExtractionError, extract_pdf_text


class TestExtractPdfText:
    def test_pymupdf_happy_path(self, pdf_bytes):
        """If PyMuPDF is available, should use it and return (text, 'pymupdf')."""
        text, backend = extract_pdf_text(pdf_bytes)
        assert "Thalindra" in text
        assert backend in ("pymupdf", "pypdf")  # either is acceptable here

    def test_pymupdf_backend_label(self, pdf_bytes):
        """When fitz is importable, backend label should be 'pymupdf'."""
        try:
            import fitz  # noqa: F401
            text, backend = extract_pdf_text(pdf_bytes)
            assert backend == "pymupdf"
        except ImportError:
            pytest.skip("PyMuPDF not installed in this environment")

    def test_falls_back_to_pypdf_when_fitz_missing(self, pdf_bytes):
        """When fitz import raises ImportError, should fall back to pypdf."""
        import sys

        original_fitz = sys.modules.get("fitz", None)
        try:
            # Force fitz to be absent
            sys.modules["fitz"] = None  # type: ignore[assignment]
            text, backend = extract_pdf_text(pdf_bytes)
            assert backend == "pypdf"
            assert len(text) > 0
        finally:
            if original_fitz is None:
                sys.modules.pop("fitz", None)
            else:
                sys.modules["fitz"] = original_fitz

    def test_raises_when_both_backends_fail(self):
        """Should raise PdfExtractionError if neither backend can process the bytes."""
        # Both backends raise on their key entry points
        fake_fitz = MagicMock()
        fake_fitz.open.side_effect = Exception("fitz internal error")

        fake_pypdf = MagicMock()
        fake_pypdf.PdfReader.side_effect = Exception("pypdf internal error")


        with patch.dict("sys.modules", {"fitz": fake_fitz, "pypdf": fake_pypdf}):
            with pytest.raises(PdfExtractionError):
                extract_pdf_text(b"%PDF-1.4 broken content")

    def test_raises_when_no_backends_installed(self):
        """Should raise PdfExtractionError when both fitz and pypdf are missing."""

        with patch.dict("sys.modules", {"fitz": None, "pypdf": None}):  # type: ignore[dict-item]
            with pytest.raises((PdfExtractionError, ImportError)):
                extract_pdf_text(b"%PDF-1.4")

    def test_extracted_text_not_empty_for_valid_pdf(self, pdf_bytes):
        """Valid PDF should produce non-empty text."""
        text, _ = extract_pdf_text(pdf_bytes)
        assert len(text.strip()) > 0

    def test_returns_tuple(self, pdf_bytes):
        """Return value should be a (str, str) tuple."""
        result = extract_pdf_text(pdf_bytes)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)
