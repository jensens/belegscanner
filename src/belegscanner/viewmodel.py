"""ViewModel for the Belegscanner GUI.

Uses GObject properties and signals for reactive UI binding.
"""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GObject


class ScanViewModel(GObject.Object):
    """ViewModel managing scan workflow state.

    Properties:
        pages: List of scanned page paths
        current_page_index: Index of currently displayed page
        status: Status message for display
        is_busy: Whether an operation is in progress
        suggested_date: OCR-extracted date suggestion
        suggested_vendor: OCR-extracted vendor suggestion
        suggested_currency: OCR-extracted currency (default: EUR)
        suggested_amount: OCR-extracted amount suggestion

    Usage:
        vm = ScanViewModel()
        vm.connect("notify::status", on_status_changed)
        vm.status = "Scanne..."
    """

    __gtype_name__ = "ScanViewModel"

    # GObject properties
    status = GObject.Property(type=str, default="Bereit")
    is_busy = GObject.Property(type=bool, default=False, nick="is-busy")
    current_page_index = GObject.Property(type=int, default=0, nick="current-page-index")
    suggested_date = GObject.Property(type=str, default=None, nick="suggested-date")
    suggested_vendor = GObject.Property(type=str, default=None, nick="suggested-vendor")
    suggested_currency = GObject.Property(type=str, default="EUR", nick="suggested-currency")
    suggested_amount = GObject.Property(type=str, default=None, nick="suggested-amount")
    ki_extraction_running = GObject.Property(type=bool, default=False, nick="ki-extraction-running")

    def __init__(self):
        """Initialize ViewModel with empty state."""
        super().__init__()
        self._pages: list[Path] = []

    @property
    def pages(self) -> list[Path]:
        """Get list of scanned page paths."""
        return self._pages.copy()

    @property
    def current_page(self) -> Path | None:
        """Get current page path, or None if no pages."""
        if not self._pages:
            return None
        idx = self.current_page_index
        if 0 <= idx < len(self._pages):
            return self._pages[idx]
        return None

    def add_page(self, path: Path) -> None:
        """Add a scanned page.

        Args:
            path: Path to the page image
        """
        self._pages.append(path)

    def clear(self) -> None:
        """Clear all state for a new scan."""
        self._pages.clear()
        self.current_page_index = 0
        self.suggested_date = ""  # GObject strings can't be None
        self.suggested_vendor = ""
        self.suggested_currency = "EUR"
        self.suggested_amount = ""
        self.status = "Bereit"
        self.is_busy = False
        self.ki_extraction_running = False
