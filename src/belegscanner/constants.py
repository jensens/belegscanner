"""Belegscanner constants."""

from pathlib import Path

# Default config location
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "belegscanner.conf"

# Categories: key -> (folder_name, is_credit_card)
# Credit card receipts are filed in the following month
CATEGORIES = {
    "1": ("Kassa", False),
    "2": ("ER", False),
    "3": ("ER-KKJK", True),   # Kreditkarte JK -> +1 Monat
    "4": ("ER-KKCB", True),   # Kreditkarte CB -> +1 Monat
}

# Scanner settings
DEFAULT_RESOLUTION = 300
DEFAULT_SCAN_MODE = "True Gray"

# OCR settings
OCR_LANGUAGE = "deu"
OCR_THRESHOLDS = [30, 40, 50, 60, 70, 80]

# IMAP settings
DEFAULT_IMAP_PORT = 993
DEFAULT_IMAP_INBOX = "Rechnungseingang"
DEFAULT_IMAP_ARCHIVE = "Rechnungseingang/archiviert"
