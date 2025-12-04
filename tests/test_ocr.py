"""Tests for OcrService."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from belegscanner.services.ocr import OcrService


class TestExtractDate:
    """Test date extraction from OCR text."""

    def test_extracts_date_dd_mm_yyyy(self):
        """Extract date in DD.MM.YYYY format."""
        service = OcrService()
        text = "Einkauf am 15.11.2024 bei REWE"

        result = service.extract_date(text)

        assert result == "15.11.2024"

    def test_extracts_date_short_year(self):
        """Extract date with 2-digit year (DD.MM.YY)."""
        service = OcrService()
        text = "Datum: 03.12.24"

        result = service.extract_date(text)

        assert result == "03.12.2024"

    def test_extracts_date_with_slashes(self):
        """Extract date with slash separators (DD/MM/YYYY)."""
        service = OcrService()
        text = "Date: 25/12/2024"

        result = service.extract_date(text)

        assert result == "25.12.2024"

    def test_extracts_first_valid_date(self):
        """When multiple dates present, extract first valid one."""
        service = OcrService()
        text = "MHD: 01.01.2099\nKaufdatum: 15.11.2024"

        result = service.extract_date(text)

        # Should find 01.01.2099 first as it's valid
        assert result == "01.01.2099"

    def test_returns_none_for_invalid_date(self):
        """Return None when date is invalid (e.g., 99.99.2024)."""
        service = OcrService()
        text = "Datum: 99.99.2024"

        result = service.extract_date(text)

        assert result is None

    def test_returns_none_when_no_date(self):
        """Return None when no date pattern found."""
        service = OcrService()
        text = "Keine Datum hier"

        result = service.extract_date(text)

        assert result is None

    def test_returns_none_for_none_input(self):
        """Return None when input is None."""
        service = OcrService()

        result = service.extract_date(None)

        assert result is None

    def test_returns_none_for_empty_string(self):
        """Return None when input is empty."""
        service = OcrService()

        result = service.extract_date("")

        assert result is None

    def test_handles_single_digit_day_month(self):
        """Handle single-digit day and month (D.M.YYYY)."""
        service = OcrService()
        text = "Datum: 5.3.2024"

        result = service.extract_date(text)

        assert result == "05.03.2024"


class TestExtractVendor:
    """Test vendor/description extraction from OCR text."""

    def test_extracts_first_meaningful_line(self):
        """Extract first line with meaningful text."""
        service = OcrService()
        text = "REWE\nMusterstraße 123\n15.11.2024"

        result = service.extract_vendor(text)

        assert result == "rewe"

    def test_skips_short_lines(self):
        """Skip lines with fewer than 3 characters."""
        service = OcrService()
        text = "AB\nREWE Center\nMore text"

        result = service.extract_vendor(text)

        assert result == "rewe_center"

    def test_skips_number_only_lines(self):
        """Skip lines that contain only numbers/punctuation."""
        service = OcrService()
        text = "12345\n15.11.2024\nBauhaus"

        result = service.extract_vendor(text)

        assert result == "bauhaus"

    def test_cleans_special_characters(self):
        """Remove special characters from vendor name."""
        service = OcrService()
        text = "REWE**Center!!#123"

        result = service.extract_vendor(text)

        assert result == "rewecenter"

    def test_converts_to_lowercase(self):
        """Convert vendor name to lowercase."""
        service = OcrService()
        text = "BAUHAUS"

        result = service.extract_vendor(text)

        assert result == "bauhaus"

    def test_replaces_spaces_with_underscores(self):
        """Replace spaces with underscores."""
        service = OcrService()
        text = "REWE City Center"

        result = service.extract_vendor(text)

        assert result == "rewe_city_center"

    def test_truncates_to_30_chars(self):
        """Truncate vendor name to 30 characters max."""
        service = OcrService()
        text = "A" * 50

        result = service.extract_vendor(text)

        assert len(result) == 30

    def test_handles_umlauts(self):
        """Handle German umlauts correctly."""
        service = OcrService()
        text = "Müller Drogerie"

        result = service.extract_vendor(text)

        assert result == "müller_drogerie"

    def test_returns_none_for_none_input(self):
        """Return None when input is None."""
        service = OcrService()

        result = service.extract_vendor(None)

        assert result is None

    def test_returns_none_for_no_valid_lines(self):
        """Return None when no valid vendor line found."""
        service = OcrService()
        text = "12345\n67890\n12.34"

        result = service.extract_vendor(text)

        assert result is None

    def test_skips_empty_lines(self):
        """Skip empty lines."""
        service = OcrService()
        text = "\n\n\nBauhaus\n\n"

        result = service.extract_vendor(text)

        assert result == "bauhaus"


class TestFindBestThreshold:
    """Test multi-threshold OCR functionality."""

    @patch("belegscanner.services.ocr.os.remove")
    @patch("belegscanner.services.ocr.subprocess.run")
    def test_calls_convert_with_thresholds(self, mock_run: MagicMock, mock_remove: MagicMock, tmp_path: Path):
        """Call ImageMagick convert with each threshold."""
        service = OcrService()
        image_path = tmp_path / "test.png"
        image_path.touch()

        # Mock successful subprocess calls
        mock_run.return_value = MagicMock(returncode=0, stdout="OCR Text")

        service.find_best_threshold(image_path)

        # Should call convert for each threshold (first arg is the command list)
        convert_calls = [c for c in mock_run.call_args_list if c[0][0][0] == "convert"]
        assert len(convert_calls) == 6  # 30, 40, 50, 60, 70, 80

    @patch("belegscanner.services.ocr.os.remove")
    @patch("belegscanner.services.ocr.subprocess.run")
    def test_calls_tesseract_for_each_threshold(self, mock_run: MagicMock, mock_remove: MagicMock, tmp_path: Path):
        """Call tesseract for each threshold variant."""
        service = OcrService()
        image_path = tmp_path / "test.png"
        image_path.touch()

        mock_run.return_value = MagicMock(returncode=0, stdout="OCR Text")

        service.find_best_threshold(image_path)

        # Should call tesseract for each threshold (first arg is the command list)
        tesseract_calls = [c for c in mock_run.call_args_list if c[0][0][0] == "tesseract"]
        assert len(tesseract_calls) == 6

    @patch("belegscanner.services.ocr.os.remove")
    @patch("belegscanner.services.ocr.subprocess.run")
    def test_returns_text_with_most_characters(self, mock_run: MagicMock, mock_remove: MagicMock, tmp_path: Path):
        """Return OCR result with most characters."""
        service = OcrService()
        image_path = tmp_path / "test.png"
        image_path.touch()

        # Simulate different OCR results for different thresholds
        results = ["Short", "Longer text here", "A", "Medium text", "X", "Even longer text result"]

        def mock_subprocess(*args, **kwargs):
            mock = MagicMock(returncode=0)
            if "tesseract" in args[0]:
                mock.stdout = results.pop(0) if results else ""
            else:
                mock.stdout = ""
            return mock

        mock_run.side_effect = mock_subprocess

        result = service.find_best_threshold(image_path)

        assert result == "Even longer text result"

    @patch("belegscanner.services.ocr.os.remove")
    @patch("belegscanner.services.ocr.subprocess.run")
    def test_cleans_up_temporary_files(self, mock_run: MagicMock, mock_remove: MagicMock, tmp_path: Path):
        """Remove temporary threshold images after processing."""
        service = OcrService()
        image_path = tmp_path / "test.png"
        image_path.touch()

        mock_run.return_value = MagicMock(returncode=0, stdout="Text")

        service.find_best_threshold(image_path)

        # Should remove 6 temporary files
        assert mock_remove.call_count == 6
