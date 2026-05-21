"""Shared fixtures for ingest tests.

Fixtures:
    png_bytes           — a minimal valid PNG image (from Pillow)
    pdf_bytes           — a minimal single-page PDF with text (from reportlab)
    mock_ocrmac_regions — monkeypatched ocrmac regions list
    mock_easyocr_regions— monkeypatched easyocr result list
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# PNG fixture (Pillow — always available in dev)
# ---------------------------------------------------------------------------


@pytest.fixture
def png_bytes() -> bytes:
    """Return bytes of a minimal 100x100 white PNG.

    Pillow is not in the direct deps but is pulled in by easyocr/ocrmac on
    developer machines. For environments without Pillow we fall back to a
    hand-crafted minimal PNG (1x1 white pixel).
    """
    try:
        from PIL import Image

        img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # Minimal 1×1 white PNG (hardcoded bytes — valid per PNG spec)
        import zlib

        def _pack_chunk(chunk_type: bytes, data: bytes) -> bytes:
            import struct

            crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

        import struct

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = _pack_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        raw = b"\x00\xff\xff\xff"  # filter=none, R=255, G=255, B=255
        idat = _pack_chunk(b"IDAT", zlib.compress(raw))
        iend = _pack_chunk(b"IEND", b"")
        return sig + ihdr + idat + iend


# ---------------------------------------------------------------------------
# PDF fixture (reportlab)
# ---------------------------------------------------------------------------


@pytest.fixture
def pdf_bytes() -> bytes:
    """Return bytes of a minimal one-page PDF with a known sentence."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(72, 700, "Character Sheet: Thalindra, Wizard 5, High Elf")
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Mock OCR region fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ocrmac_regions() -> list[dict]:
    """Return a list mimicking ocrmac's Region objects (dict-like with .text / .confidence)."""
    region1 = MagicMock()
    region1.text = "Character Sheet"
    region1.confidence = 0.98

    region2 = MagicMock()
    region2.text = "Thalindra Wizard 5"
    region2.confidence = 0.92

    return [region1, region2]


@pytest.fixture
def mock_easyocr_regions() -> list[tuple]:
    """Return a list mimicking easyocr's result tuples: (bbox, text, confidence)."""
    return [
        ([[0, 0], [100, 0], [100, 20], [0, 20]], "Character Sheet", 0.95),
        ([[0, 25], [100, 25], [100, 45], [0, 45]], "Thalindra Wizard 5", 0.88),
    ]
