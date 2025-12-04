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
