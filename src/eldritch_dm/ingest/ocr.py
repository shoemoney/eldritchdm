"""OCR backend resolver and runners for the ingest pipeline.

Platform-conditional backends:
  - Darwin + ocrmac installed  → ocrmac (Vision framework via PyObjC)
  - Linux / ocrmac unavailable → easyocr (CPU fallback, heavier)
  - Neither available          → UnavailableOCRBackend raised at call time

Imports of backend libraries are DEFERRED (inside functions, not at module top)
to allow the module to import on machines where neither backend is installed.

Public API:
    UnavailableOCRBackend       — raised when no OCR backend is available
    resolve_ocr_backend()       — returns "ocrmac" | "easyocr" | None
    run_ocrmac(image_bytes)     → (text, avg_confidence)
    run_easyocr(image_bytes)    → (text, avg_confidence)
    aggregate_ocrmac_confidence(regions) → float
    aggregate_easyocr_confidence(results) → float
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import io
import sys
from typing import Any

from eldritch_dm.logging import get_logger

log = get_logger(__name__)

_OCRMAC_SPEC = "ocrmac"
_EASYOCR_SPEC = "easyocr"


class UnavailableOCRBackend(RuntimeError):
    """Raised when no OCR backend is available in the current environment."""


# ---------------------------------------------------------------------------
# Backend resolution
# ---------------------------------------------------------------------------


def resolve_ocr_backend() -> str | None:
    """Detect which OCR backend is available.

    Returns:
        "ocrmac"  — on macOS with ocrmac installed
        "easyocr" — on non-macOS or when ocrmac is absent but easyocr is present
        None      — no OCR backend found
    """
    if sys.platform == "darwin" and importlib.util.find_spec(_OCRMAC_SPEC) is not None:
        return "ocrmac"
    if importlib.util.find_spec(_EASYOCR_SPEC) is not None:
        return "easyocr"
    return None


# ---------------------------------------------------------------------------
# Confidence aggregators (pure functions — testable without a real image)
# ---------------------------------------------------------------------------


def aggregate_ocrmac_confidence(regions: list[Any]) -> float:
    """Compute average confidence from an ocrmac regions list.

    Args:
        regions: list of ocrmac Region objects with a `.confidence` attribute.

    Returns:
        Average confidence (0.0–1.0), or 0.0 if the list is empty.
    """
    if not regions:
        return 0.0
    total = sum(float(getattr(r, "confidence", 0.0)) for r in regions)
    return total / len(regions)


def aggregate_easyocr_confidence(results: list[tuple]) -> float:
    """Compute average confidence from an easyocr result list.

    Args:
        results: list of (bbox, text, confidence) tuples.

    Returns:
        Average confidence (0.0–1.0), or 0.0 if the list is empty.
    """
    if not results:
        return 0.0
    total = sum(float(entry[2]) for entry in results)
    return total / len(results)


# ---------------------------------------------------------------------------
# Backend runners
# ---------------------------------------------------------------------------


def run_ocrmac(image_bytes: bytes) -> tuple[str, float]:
    """Run ocrmac OCR on image bytes.

    This is a SYNCHRONOUS blocking call — must be executed via IngestExecutor.

    Args:
        image_bytes: Raw image bytes (PNG, JPEG, etc.)

    Returns:
        (extracted_text, avg_confidence)

    Raises:
        UnavailableOCRBackend: if ocrmac is not installed.
    """
    if importlib.util.find_spec(_OCRMAC_SPEC) is None:
        raise UnavailableOCRBackend("ocrmac is not installed")

    import ocrmac  # type: ignore[import-untyped]

    regions = ocrmac.OCR(image_bytes, recognition_level="accurate").recognize()
    lines = [getattr(r, "text", "") for r in regions]
    text = "\n".join(line for line in lines if line)
    confidence = aggregate_ocrmac_confidence(regions)
    log.debug("ocrmac_done", char_count=len(text), confidence=confidence)
    return text, confidence


def run_easyocr(image_bytes: bytes) -> tuple[str, float]:
    """Run easyocr OCR on image bytes.

    This is a SYNCHRONOUS blocking call — must be executed via IngestExecutor.

    Args:
        image_bytes: Raw image bytes (PNG, JPEG, etc.)

    Returns:
        (extracted_text, avg_confidence)

    Raises:
        UnavailableOCRBackend: if easyocr is not installed.
    """
    if importlib.util.find_spec(_EASYOCR_SPEC) is None:
        raise UnavailableOCRBackend("easyocr is not installed")

    import easyocr  # type: ignore[import-untyped]

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    buf = io.BytesIO(image_bytes)
    results = reader.readtext(buf.getvalue())
    lines = [entry[1] for entry in results]
    text = "\n".join(line for line in lines if line)
    confidence = aggregate_easyocr_confidence(results)
    log.debug("easyocr_done", char_count=len(text), confidence=confidence)
    return text, confidence
