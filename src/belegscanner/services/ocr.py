"""OCR service for text extraction from scanned images."""

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from belegscanner.constants import OCR_LANGUAGE, OCR_THRESHOLDS


class OcrService:
    """Service for OCR operations and text extraction.

    Provides:
    - Multi-threshold OCR for optimal text recognition
    - Date extraction from OCR text
    - Vendor/description extraction from OCR text
    """

    def __init__(self, language: str = OCR_LANGUAGE, thresholds: list[int] | None = None):
        """Initialize OCR service.

        Args:
            language: Tesseract language code (default: "deu")
            thresholds: List of threshold percentages to try (default: [30,40,50,60,70,80])
        """
        self.language = language
        self.thresholds = thresholds or OCR_THRESHOLDS

    def extract_date(self, text: str | None) -> str | None:
        """Extract date from OCR text.

        Looks for common date patterns:
        - DD.MM.YYYY
        - DD.MM.YY (assumes 20xx)
        - DD/MM/YYYY

        Args:
            text: OCR text to search

        Returns:
            Date formatted as DD.MM.YYYY, or None if not found
        """
        if not text:
            return None

        patterns = [
            r"(\d{1,2})[./](\d{1,2})[./](20\d{2})",  # DD.MM.YYYY or DD/MM/YYYY
            r"(\d{1,2})[./](\d{1,2})[./](\d{2})\b",  # DD.MM.YY
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                day, month, year = match.groups()
                if len(year) == 2:
                    year = "20" + year
                try:
                    date = datetime(int(year), int(month), int(day))
                    return date.strftime("%d.%m.%Y")
                except ValueError:
                    continue

        return None

    # Known currency codes (only these are recognized, not arbitrary 3-letter codes)
    KNOWN_CURRENCIES = frozenset([
        "EUR", "USD", "CHF", "GBP", "JPY", "CAD", "AUD", "NZD",
        "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "BGN",
        "HRK", "RUB", "TRY", "BRL", "MXN", "INR", "CNY", "KRW",
    ])

    def extract_amount(self, text: str | None) -> tuple[str, str] | None:
        """Extract amount and currency from OCR text.

        Looks for amounts with currency symbols/codes, prioritizing
        lines with total keywords (Brutto, Gesamt, Summe, Total, etc.).

        Args:
            text: OCR text to search

        Returns:
            Tuple of (currency, amount) e.g. ("EUR", "27.07"),
            or None if not found
        """
        if not text:
            return None

        # Currency patterns: symbol → normalized code
        currency_map = {
            "€": "EUR",
            "$": "USD",
        }

        # Keywords that indicate total amount (priority lines)
        # Use word boundary \b to avoid matching "zwischensumme" for "summe"
        total_keywords = [
            r"\bbrutto\b",
            r"\bgesamt\b",
            r"\bsumme\b",
            r"\btotal\b",
            r"\bendbetrag\b",
            r"\bzu\s*zahlen\b",
        ]

        # Build currency code pattern from known currencies
        currency_codes = "|".join(self.KNOWN_CURRENCIES)

        # Pattern for amount with currency
        # Matches: €27,07 | 27,07€ | EUR 27,07 | 27,07 EUR | $99.50 | CHF 89.50
        # Handles: 1.234,56 (German) | 1,234.56 (English) | 100 (no decimal)
        amount_pattern = (
            r"(?:"
            # Currency before amount: € 27,07 or EUR 27,07 or $99.50
            rf"([€$]|{currency_codes})\s*"
            r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+)"
            r"|"
            # Currency after amount: 27,07 € or 27,07 EUR
            r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+)\s*"
            rf"([€$]|{currency_codes})"
            r")"
        )

        def parse_amount(match) -> tuple[str, str] | None:
            """Parse a regex match into (currency, normalized_amount)."""
            groups = match.groups()
            if groups[0]:  # Currency before amount
                currency_raw, amount_raw = groups[0], groups[1]
            else:  # Currency after amount
                amount_raw, currency_raw = groups[2], groups[3]

            # Normalize currency
            currency = currency_map.get(currency_raw, currency_raw.upper())

            # Normalize amount to XX.XX format
            amount = self._normalize_amount(amount_raw)
            if amount is None:
                return None

            return (currency, amount)

        def find_amount_in_line(line: str) -> tuple[str, str] | None:
            """Find amount in a single line."""
            match = re.search(amount_pattern, line, re.IGNORECASE)
            if match:
                return parse_amount(match)
            return None

        def find_amount_after_keyword(line: str, keyword: str) -> tuple[str, str] | None:
            """Find amount in line, searching AFTER the keyword position."""
            match = re.search(keyword, line, re.IGNORECASE)
            if match:
                # Search only in text after the keyword
                text_after = line[match.end():]
                amount_match = re.search(amount_pattern, text_after, re.IGNORECASE)
                if amount_match:
                    return parse_amount(amount_match)
            return None

        # First pass: look for total lines (priority)
        # Search for amount AFTER the keyword to avoid matching unrelated amounts
        for line in text.splitlines():
            line_lower = line.lower()
            for keyword in total_keywords:
                if re.search(keyword, line_lower):
                    result = find_amount_after_keyword(line, keyword)
                    if result:
                        return result

        # Second pass: find last amount with currency (fallback)
        last_match = None
        for line in text.splitlines():
            result = find_amount_in_line(line)
            if result:
                last_match = result

        return last_match

    def _normalize_amount(self, amount_raw: str) -> str | None:
        """Normalize amount string to XX.XX format with 2 decimal places.

        Handles:
        - German format: 1.234,56 → 1234.56
        - English format: 1,234.56 → 1234.56
        - No decimal: 100 → 100.00

        Args:
            amount_raw: Raw amount string

        Returns:
            Normalized amount string (e.g., "27.07"), or None if invalid
        """
        if not amount_raw:
            return None

        # Determine decimal separator by looking at last separator
        # German: 1.234,56 (comma is decimal)
        # English: 1,234.56 (dot is decimal)
        has_comma = "," in amount_raw
        has_dot = "." in amount_raw

        if has_comma and has_dot:
            # Both present: last one is decimal separator
            last_comma = amount_raw.rfind(",")
            last_dot = amount_raw.rfind(".")
            if last_comma > last_dot:
                # German format: 1.234,56
                amount = amount_raw.replace(".", "").replace(",", ".")
            else:
                # English format: 1,234.56
                amount = amount_raw.replace(",", "")
        elif has_comma:
            # Only comma: it's the decimal separator (German)
            amount = amount_raw.replace(",", ".")
        elif has_dot:
            # Only dot: could be decimal or thousands
            # If 3 digits after dot, it's thousands; otherwise decimal
            parts = amount_raw.split(".")
            if len(parts) == 2 and len(parts[1]) == 3:
                # Thousands separator (e.g., 1.234)
                amount = amount_raw.replace(".", "")
            else:
                # Decimal separator
                amount = amount_raw
        else:
            # No separator
            amount = amount_raw

        try:
            value = float(amount)
            return f"{value:.2f}"
        except ValueError:
            return None

    def extract_vendor(self, text: str | None) -> str | None:
        """Extract vendor/description from OCR text.

        Takes the first meaningful line (not numbers, not too short)
        and cleans it for use as filename.

        Args:
            text: OCR text to search

        Returns:
            Cleaned vendor name (lowercase, underscores, max 30 chars),
            or None if not found
        """
        if not text:
            return None

        for line in text.splitlines():
            line = line.strip()

            # Skip empty or very short lines
            if len(line) < 3:
                continue

            # Skip lines that are just numbers/dates/punctuation
            if re.match(r"^[\d\s./:,-]+$", line):
                continue

            # Clean up: keep letters (including umlauts) and spaces
            clean = re.sub(r"[^a-zA-ZäöüÄÖÜß\s]", "", line).strip().lower()
            clean = re.sub(r"\s+", "_", clean)

            if len(clean) >= 3:
                return clean[:30]

        return None

    def find_best_threshold(self, image_path: Path) -> str:
        """Try multiple thresholds and return OCR text from best one.

        Uses ImageMagick to create black/white variants at different
        threshold levels, runs Tesseract on each, and returns the result
        with the most characters.

        Args:
            image_path: Path to image file

        Returns:
            OCR text from the threshold that produced most output
        """
        best_text = ""
        image_str = str(image_path)

        for threshold in self.thresholds:
            # Create threshold variant
            temp_bw = image_str.replace(".png", f"_bw{threshold}.png")
            subprocess.run(
                ["convert", image_str, "-threshold", f"{threshold}%", temp_bw],
                check=True,
                capture_output=True,
            )

            # Run OCR
            result = subprocess.run(
                ["tesseract", temp_bw, "stdout", "-l", self.language],
                capture_output=True,
                text=True,
            )
            text = result.stdout

            # Clean up temp file
            os.remove(temp_bw)

            # Keep best result
            if len(text) > len(best_text):
                best_text = text

        return best_text
