"""Belegscanner constants."""

from pathlib import Path

# Default config location
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "belegscanner.conf"

# Categories: key -> (folder_name, is_credit_card)
# Credit card receipts are filed in the following month
CATEGORIES = {
    "1": ("Kassa", False),
    "2": ("ER", False),
    "3": ("ER-KKJK", True),  # Kreditkarte JK -> +1 Monat
    "4": ("ER-KKCB", True),  # Kreditkarte CB -> +1 Monat
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

# Vendor extraction settings
# Terms that don't identify a vendor (blacklisted)
VENDOR_BLACKLIST = {
    # Deutsche Begriffe (Rechnungs-bezogen)
    "rechnung",
    "bestellung",
    "beleg",
    "quittung",
    "lieferung",
    "zahlung",
    "mahnung",
    "erinnerung",
    "benachrichtigung",
    # Deutsche Begriffe (allgemein)
    "ihre",
    "ihr",
    "ihre",
    "wichtige",
    "wichtig",
    "mitteilung",
    "neue",
    "aktualisierung",
    "bestätigung",
    # Englische Begriffe (Rechnungs-bezogen)
    "invoice",
    "receipt",
    "billing",
    "order",
    "payment",
    "notification",
    "confirmation",
    "reminder",
    "statement",
    # Englische Begriffe (allgemein)
    "your",
    "the",
    "new",
    "update",
    "important",
    "dear",
    # Generische E-Mail-Begriffe
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "newsletter",
    "info",
    "service",
    "support",
    "kontakt",
    "contact",
    "mail",
    "email",
    "team",
    "admin",
    "system",
    "auto",
    # Generische Domains
    "gmail",
    "outlook",
    "yahoo",
    "hotmail",
    "gmx",
    "web",
    "posteo",
    # Zahlungsdienstleister (nicht der eigentliche Lieferant)
    "paypal",
    "stripe",
    "klarna",
    "giropay",
    "sofort",
    # Eigene Firma
    "kleinundpartner",
}

# Keywords that precede vendor names in email subjects
# German: "Rechnung von X", "Bestellung bei X", "Zahlung an X"
# English: "Invoice from X", "Payment to X"
VENDOR_SUBJECT_KEYWORDS = ["von", "bei", "für", "durch", "an", "from", "by", "for", "to"]

# Ollama settings (for AI-based extraction fallback)
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "phi3"
OLLAMA_TIMEOUT = 30  # seconds
