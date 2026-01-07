"""Vendor/supplier extraction from email metadata."""

import re
from collections.abc import Callable

from belegscanner.constants import VENDOR_BLACKLIST, VENDOR_SUBJECT_KEYWORDS


class VendorExtractor:
    """Extract vendor/supplier name from email data.

    Priority:
    1. Display name from From header (e.g., "Amazon" from "Amazon <x@y.de>")
    2. Domain from From header (e.g., "amazon" from "x@amazon.de")
    3. Keywords from Subject (e.g., "mediamarkt" from "Rechnung von MediaMarkt")
    4. OCR text from PDF (optional callback, lazy evaluation)

    Each result is checked against blacklist. If blacklisted, next priority used.
    """

    def __init__(self, blacklist: set[str] | None = None):
        """Initialize extractor with optional custom blacklist.

        Args:
            blacklist: Set of terms to ignore. If None, uses VENDOR_BLACKLIST.
        """
        self.blacklist = blacklist if blacklist is not None else VENDOR_BLACKLIST

    def extract(
        self,
        sender: str,
        subject: str = "",
        ocr_callback: Callable[[], str | None] | None = None,
    ) -> str | None:
        """Extract vendor name from email metadata.

        Args:
            sender: From header (e.g., "Amazon <rechnung@amazon.de>")
            subject: Email subject line
            ocr_callback: Optional callback to get OCR text for fallback.
                          Only called if sender/subject extraction fails.

        Returns:
            Cleaned vendor name or None if not found.
        """
        # Try display name first
        vendor = self._extract_display_name(sender)
        if vendor and not self._is_blacklisted(vendor):
            return self._clean(vendor)

        # Try domain
        vendor = self._extract_domain(sender)
        if vendor and not self._is_blacklisted(vendor):
            return self._clean(vendor)

        # Try subject keywords
        vendor = self._extract_from_subject(subject)
        if vendor and not self._is_blacklisted(vendor):
            return self._clean(vendor)

        # Optional OCR fallback (lazy - only called if needed)
        if ocr_callback:
            ocr_text = ocr_callback()
            if ocr_text:
                vendor = self._extract_from_subject(ocr_text)
                if vendor and not self._is_blacklisted(vendor):
                    return self._clean(vendor)

        return None

    def _extract_display_name(self, sender: str) -> str | None:
        """Extract display name from sender.

        Examples:
            "Amazon <x@y.de>" -> "Amazon"
            '"Amazon.de" <x@y.de>' -> "Amazon.de"
            "x@y.de" -> None
        """
        if not sender:
            return None

        # Pattern: "Name" <email> or Name <email>
        match = re.match(r'^"?([^"<]+)"?\s*<', sender)
        if match:
            name = match.group(1).strip()
            if name and len(name) >= 3:
                return name
        return None

    def _extract_domain(self, sender: str) -> str | None:
        """Extract domain name from email address.

        Examples:
            "rechnung@amazon.de" -> "amazon"
            "Amazon <x@amazon.de>" -> "amazon"
            "info@shop.amazon.de" -> "shop"
        """
        if not sender:
            return None

        match = re.search(r"@([^>]+)", sender)
        if match:
            domain = match.group(1)
            # Get first part before TLD
            parts = domain.split(".")
            if parts:
                return parts[0]
        return None

    def _extract_from_subject(self, text: str) -> str | None:
        """Extract vendor from subject/text using keyword patterns.

        Examples:
            "Rechnung von Amazon #123" -> "Amazon"
            "Invoice from PayPal" -> "PayPal"
            "Your MediaMarkt Order" -> "MediaMarkt" (capitalized fallback)
        """
        if not text:
            return None

        # Try keyword patterns: "Rechnung von VENDOR", "Invoice from VENDOR"
        for keyword in VENDOR_SUBJECT_KEYWORDS:
            pattern = rf"\b{keyword}\s+(\w+)"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                vendor = match.group(1)
                if len(vendor) >= 3 and not vendor.isdigit():
                    return vendor

        # Fallback: Find first capitalized word that's not blacklisted
        words = re.findall(r"\b[A-Z][a-zA-Z]+\b", text)
        for word in words:
            if len(word) >= 3 and not self._is_blacklisted(word):
                return word

        return None

    def _is_blacklisted(self, term: str) -> bool:
        """Check if term is in blacklist (case-insensitive).

        Also checks parts of compound words (e.g., "invoice-service" contains "invoice").
        """
        term_lower = term.lower()
        # Direct match
        if term_lower in self.blacklist:
            return True
        # Check parts split by common separators (-, _)
        parts = re.split(r"[-_]", term_lower)
        return any(part in self.blacklist for part in parts if len(part) >= 3)

    def _clean(self, vendor: str) -> str | None:
        """Clean vendor name for filename use.

        - Lowercase
        - Replace non-alphanumeric (except umlauts) with underscore
        - Strip leading/trailing underscores
        - Truncate to 30 characters

        Returns:
            Cleaned vendor name, or None if result is too short.
        """
        # Lowercase
        result = vendor.lower()
        # Replace non-alphanumeric (keep umlauts äöüß) with underscore
        result = re.sub(r"[^a-z0-9äöüß]+", "_", result)
        # Strip and truncate
        result = result.strip("_")[:30]
        return result if len(result) >= 2 else None
