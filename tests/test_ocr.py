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


class TestExtractAmount:
    """Test amount/currency extraction from OCR text."""

    def test_extracts_eur_with_euro_symbol_before(self):
        """Extract EUR amount with € symbol before amount."""
        service = OcrService()
        text = "Gesamt: € 27,07"

        result = service.extract_amount(text)

        assert result == ("EUR", "27.07")

    def test_extracts_eur_with_euro_symbol_after(self):
        """Extract EUR amount with € symbol after amount."""
        service = OcrService()
        text = "Summe: 27,07 €"

        result = service.extract_amount(text)

        assert result == ("EUR", "27.07")

    def test_extracts_eur_with_eur_text(self):
        """Extract EUR amount with EUR text."""
        service = OcrService()
        text = "Total: EUR 150,00"

        result = service.extract_amount(text)

        assert result == ("EUR", "150.00")

    def test_extracts_usd_with_dollar_symbol(self):
        """Extract USD amount with $ symbol."""
        service = OcrService()
        text = "Total: $99.50"

        result = service.extract_amount(text)

        assert result == ("USD", "99.50")

    def test_extracts_usd_with_usd_text(self):
        """Extract USD amount with USD text."""
        service = OcrService()
        text = "Total: USD 150.00"

        result = service.extract_amount(text)

        assert result == ("USD", "150.00")

    def test_extracts_chf(self):
        """Extract CHF amount."""
        service = OcrService()
        text = "Betrag: CHF 89.50"

        result = service.extract_amount(text)

        assert result == ("CHF", "89.50")

    def test_prefers_brutto_over_other_amounts(self):
        """Prefer amount from Brutto line over others."""
        service = OcrService()
        text = """Netto: € 22,75
        MwSt: € 4,32
        Brutto: € 27,07"""

        result = service.extract_amount(text)

        assert result == ("EUR", "27.07")

    def test_prefers_gesamt_line(self):
        """Prefer amount from Gesamt line."""
        service = OcrService()
        text = """Artikel 1: € 10,00
        Artikel 2: € 17,07
        Gesamt: € 27,07"""

        result = service.extract_amount(text)

        assert result == ("EUR", "27.07")

    def test_prefers_summe_line(self):
        """Prefer amount from Summe line."""
        service = OcrService()
        text = """Position 1: 10,00 €
        Position 2: 17,07 €
        Summe: 27,07 €"""

        result = service.extract_amount(text)

        assert result == ("EUR", "27.07")

    def test_prefers_total_line(self):
        """Prefer amount from Total line."""
        service = OcrService()
        text = """Item: $50.00
        Tax: $5.00
        Total: $55.00"""

        result = service.extract_amount(text)

        assert result == ("USD", "55.00")

    def test_prefers_endbetrag_line(self):
        """Prefer amount from Endbetrag line."""
        service = OcrService()
        text = """Zwischensumme: € 25,00
        Rabatt: € -2,00
        Endbetrag: € 23,00"""

        result = service.extract_amount(text)

        assert result == ("EUR", "23.00")

    def test_prefers_zu_zahlen_line(self):
        """Prefer amount from 'zu zahlen' line."""
        service = OcrService()
        text = """Summe: € 25,00
        Zu zahlen: € 25,00"""

        result = service.extract_amount(text)

        assert result == ("EUR", "25.00")

    def test_handles_comma_decimal_separator(self):
        """Handle German comma decimal separator."""
        service = OcrService()
        text = "Betrag: 1.234,56 €"

        result = service.extract_amount(text)

        assert result == ("EUR", "1234.56")

    def test_handles_dot_decimal_separator(self):
        """Handle English dot decimal separator."""
        service = OcrService()
        text = "Amount: $1,234.56"

        result = service.extract_amount(text)

        assert result == ("USD", "1234.56")

    def test_handles_no_decimal(self):
        """Handle amounts without decimal places."""
        service = OcrService()
        text = "Gesamt: € 100"

        result = service.extract_amount(text)

        assert result == ("EUR", "100.00")

    def test_returns_none_for_none_input(self):
        """Return None when input is None."""
        service = OcrService()

        result = service.extract_amount(None)

        assert result is None

    def test_returns_none_for_empty_string(self):
        """Return None when input is empty."""
        service = OcrService()

        result = service.extract_amount("")

        assert result is None

    def test_returns_none_when_no_amount(self):
        """Return None when no amount pattern found."""
        service = OcrService()
        text = "Kein Betrag hier"

        result = service.extract_amount(text)

        assert result is None

    def test_fallback_to_last_amount_with_currency(self):
        """When no total line found, use last amount with currency."""
        service = OcrService()
        text = """Artikel: € 10,00
        Noch ein Artikel: € 17,07"""

        result = service.extract_amount(text)

        assert result == ("EUR", "17.07")

    def test_extracts_amount_case_insensitive(self):
        """Extract amount with case-insensitive keywords."""
        service = OcrService()
        text = "GESAMT: € 27,07"

        result = service.extract_amount(text)

        assert result == ("EUR", "27.07")

    def test_handles_other_currency_codes(self):
        """Handle other 3-letter currency codes."""
        service = OcrService()
        text = "Total: GBP 50.00"

        result = service.extract_amount(text)

        assert result == ("GBP", "50.00")

    def test_ignores_unknown_currency_codes(self):
        """Ignore random 3-letter words that look like currency codes.

        Regression test: 'PRE' from 'Prepaid' was matched as currency.
        """
        service = OcrService()
        # PRE is not a valid currency
        text = "Amount: PRE 2667.00"

        result = service.extract_amount(text)

        assert result is None

    def test_anthropic_receipt_email(self):
        """Extract correct amount from Anthropic receipt email.

        Regression test: Was extracting 2667.00 PRE instead of 5.00 EUR.
        The issue was: '2667 Prepaid' matched as '2667 PRE' currency.
        """
        service = OcrService()
        text = """Receipt #2422-7882-2667 Prepaid extra usage, Individual plan Qty 1 €5.00 Total €5.00 Amount paid €5.00"""

        result = service.extract_amount(text)

        assert result == ("EUR", "5.00")

    def test_finds_amount_after_total_keyword(self):
        """When total keyword found, search for amount AFTER the keyword."""
        service = OcrService()
        # Amount appears before AND after "Total"
        text = "Item: €99.00 other stuff Total: €5.00"

        result = service.extract_amount(text)

        assert result == ("EUR", "5.00")


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
