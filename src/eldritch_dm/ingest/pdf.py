"""PDF text extraction for the ingest pipeline.

Tries PyMuPDF first (fitz) — fastest, best quality.
Falls back to pypdf if PyMuPDF is not available.
Raises PdfExtractionError when neither backend can extract text.

Public API:
    PdfExtractionError          — raised when extraction fails
    extract_pdf_text(pdf_bytes) → (text, backend_name)
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io

from eldritch_dm.logging import get_logger

log = get_logger(__name__)


class PdfExtractionError(RuntimeError):
    """Raised when no PDF backend can extract text from the given bytes."""


def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, str]:
    """Extract plain text from a PDF.

    Tries PyMuPDF (fitz) first; falls back to pypdf.

    Args:
        pdf_bytes: Raw bytes of a PDF document.

    Returns:
        (text, backend_name) where backend_name is "pymupdf" or "pypdf".

    Raises:
        PdfExtractionError: If both backends fail or neither is installed.
    """
    # --- PyMuPDF (fitz) ---
    try:
        import fitz  # type: ignore[import-untyped]  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages: list[str] = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        text = "\n".join(pages)
        log.debug("pdf_extract_pymupdf", char_count=len(text))
        return text, "pymupdf"
    except ImportError:
        log.debug("pymupdf_not_available_trying_pypdf")
    except Exception as exc:
        log.warning("pymupdf_extraction_failed", error=str(exc))

    # --- pypdf fallback ---
    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]

        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
        log.debug("pdf_extract_pypdf", char_count=len(text))
        return text, "pypdf"
    except ImportError:
        log.warning("pypdf_not_available")
    except Exception as exc:
        log.warning("pypdf_extraction_failed", error=str(exc))

    raise PdfExtractionError(
        "PDF text extraction failed: neither PyMuPDF nor pypdf could read the document"
    )
