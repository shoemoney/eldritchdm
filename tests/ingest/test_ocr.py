"""Unit tests for eldritch_dm.ingest.ocr.

All OCR backend calls are mocked — no screen / GPU required.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from eldritch_dm.ingest.ocr import (
    UnavailableOCRBackend,
    aggregate_easyocr_confidence,
    aggregate_ocrmac_confidence,
    resolve_ocr_backend,
    run_easyocr,
    run_ocrmac,
)

# ---------------------------------------------------------------------------
# aggregate_ocrmac_confidence
# ---------------------------------------------------------------------------


class TestAggregateOcrmacConfidence:
    def test_empty_list_returns_zero(self):
        assert aggregate_ocrmac_confidence([]) == 0.0

    def test_single_region(self, mock_ocrmac_regions):
        single = [mock_ocrmac_regions[0]]
        # region1 has confidence=0.98
        result = aggregate_ocrmac_confidence(single)
        assert abs(result - 0.98) < 1e-9

    def test_average_of_multiple(self, mock_ocrmac_regions):
        # 0.98 + 0.92 = 1.90 / 2 = 0.95
        result = aggregate_ocrmac_confidence(mock_ocrmac_regions)
        assert abs(result - 0.95) < 1e-9

    def test_missing_confidence_attr_treated_as_zero(self):
        region = MagicMock(spec=[])  # no .confidence attribute
        result = aggregate_ocrmac_confidence([region])
        assert result == 0.0


# ---------------------------------------------------------------------------
# aggregate_easyocr_confidence
# ---------------------------------------------------------------------------


class TestAggregateEasyocrConfidence:
    def test_empty_list_returns_zero(self):
        assert aggregate_easyocr_confidence([]) == 0.0

    def test_single_result(self, mock_easyocr_regions):
        single = [mock_easyocr_regions[0]]
        assert abs(aggregate_easyocr_confidence(single) - 0.95) < 1e-9

    def test_average_of_multiple(self, mock_easyocr_regions):
        # 0.95 + 0.88 = 1.83 / 2 = 0.915
        result = aggregate_easyocr_confidence(mock_easyocr_regions)
        assert abs(result - 0.915) < 1e-9


# ---------------------------------------------------------------------------
# resolve_ocr_backend
# ---------------------------------------------------------------------------


class TestResolveOcrBackend:
    def test_darwin_with_ocrmac(self):
        with (
            patch.object(sys, "platform", "darwin"),
            patch("importlib.util.find_spec", side_effect=lambda n: MagicMock() if n == "ocrmac" else None),
        ):
            assert resolve_ocr_backend() == "ocrmac"

    def test_darwin_without_ocrmac_falls_back_to_easyocr(self):
        with (
            patch.object(sys, "platform", "darwin"),
            patch("importlib.util.find_spec", side_effect=lambda n: MagicMock() if n == "easyocr" else None),
        ):
            assert resolve_ocr_backend() == "easyocr"

    def test_linux_returns_easyocr_if_present(self):
        with (
            patch.object(sys, "platform", "linux"),
            patch("importlib.util.find_spec", side_effect=lambda n: MagicMock() if n == "easyocr" else None),
        ):
            assert resolve_ocr_backend() == "easyocr"

    def test_no_backend_returns_none(self):
        with patch("importlib.util.find_spec", return_value=None):
            assert resolve_ocr_backend() is None


# ---------------------------------------------------------------------------
# run_ocrmac
# ---------------------------------------------------------------------------


class TestRunOcrmac:
    def test_raises_when_not_installed(self):
        with patch("importlib.util.find_spec", return_value=None):
            with pytest.raises(UnavailableOCRBackend):
                run_ocrmac(b"fake_image_bytes")

    def test_returns_text_and_confidence(self, mock_ocrmac_regions):
        fake_ocrmac = MagicMock()
        fake_ocr_instance = MagicMock()
        fake_ocr_instance.recognize.return_value = mock_ocrmac_regions
        fake_ocrmac.OCR.return_value = fake_ocr_instance

        with (
            patch("importlib.util.find_spec", return_value=MagicMock()),
            patch.dict("sys.modules", {"ocrmac": fake_ocrmac}),
        ):
            text, conf = run_ocrmac(b"fake_image_bytes")

        assert "Character Sheet" in text
        assert "Thalindra Wizard 5" in text
        assert abs(conf - 0.95) < 1e-9

    def test_empty_regions_returns_empty_text(self):
        fake_ocrmac = MagicMock()
        fake_ocr_instance = MagicMock()
        fake_ocr_instance.recognize.return_value = []
        fake_ocrmac.OCR.return_value = fake_ocr_instance

        with (
            patch("importlib.util.find_spec", return_value=MagicMock()),
            patch.dict("sys.modules", {"ocrmac": fake_ocrmac}),
        ):
            text, conf = run_ocrmac(b"blank_image")

        assert text == ""
        assert conf == 0.0


# ---------------------------------------------------------------------------
# run_easyocr
# ---------------------------------------------------------------------------


class TestRunEasyocr:
    def test_raises_when_not_installed(self):
        with patch("importlib.util.find_spec", return_value=None):
            with pytest.raises(UnavailableOCRBackend):
                run_easyocr(b"fake_image_bytes")

    def test_returns_text_and_confidence(self, mock_easyocr_regions, png_bytes):
        fake_easyocr = MagicMock()
        fake_reader = MagicMock()
        fake_reader.readtext.return_value = mock_easyocr_regions
        fake_easyocr.Reader.return_value = fake_reader

        with (
            patch("importlib.util.find_spec", return_value=MagicMock()),
            patch.dict("sys.modules", {"easyocr": fake_easyocr}),
        ):
            text, conf = run_easyocr(png_bytes)

        assert "Character Sheet" in text
        assert abs(conf - 0.915) < 1e-9

    def test_empty_results_returns_empty_text(self, png_bytes):
        fake_easyocr = MagicMock()
        fake_reader = MagicMock()
        fake_reader.readtext.return_value = []
        fake_easyocr.Reader.return_value = fake_reader

        with (
            patch("importlib.util.find_spec", return_value=MagicMock()),
            patch.dict("sys.modules", {"easyocr": fake_easyocr}),
        ):
            text, conf = run_easyocr(png_bytes)

        assert text == ""
        assert conf == 0.0
