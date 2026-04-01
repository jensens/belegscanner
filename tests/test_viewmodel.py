"""Tests for ScanViewModel."""

from pathlib import Path
from unittest.mock import MagicMock

import gi

gi.require_version("Gtk", "4.0")

from belegscanner.viewmodel import ScanViewModel


class TestViewModelInitialState:
    """Test initial state of ViewModel."""

    def test_initial_pages_empty(self):
        """Pages list is empty initially."""
        vm = ScanViewModel()
        assert vm.pages == []

    def test_initial_status_ready(self):
        """Status is 'Bereit' initially."""
        vm = ScanViewModel()
        assert vm.status == "Bereit"

    def test_initial_not_busy(self):
        """Not busy initially."""
        vm = ScanViewModel()
        assert vm.is_busy is False

    def test_initial_suggestions_empty(self):
        """No suggestions initially (empty strings in GObject)."""
        vm = ScanViewModel()
        # GObject string properties are never None, but empty string
        assert not vm.suggested_date  # Empty or None
        assert not vm.suggested_vendor


class TestViewModelSignals:
    """Test GObject signal emission."""

    def test_emits_status_changed_signal(self):
        """Emit signal when status changes."""
        vm = ScanViewModel()
        handler = MagicMock()
        vm.connect("notify::status", handler)

        vm.status = "Scanne..."

        assert handler.called

    def test_emits_busy_changed_signal(self):
        """Emit signal when busy state changes."""
        vm = ScanViewModel()
        handler = MagicMock()
        vm.connect("notify::is-busy", handler)

        vm.is_busy = True

        assert handler.called


class TestViewModelPages:
    """Test page management."""

    def test_add_page(self, tmp_path: Path):
        """Add a page to the list."""
        vm = ScanViewModel()
        page = tmp_path / "page1.png"
        page.touch()

        vm.add_page(page)

        assert len(vm.pages) == 1
        assert vm.pages[0] == page

    def test_add_multiple_pages(self, tmp_path: Path):
        """Add multiple pages."""
        vm = ScanViewModel()

        for i in range(3):
            page = tmp_path / f"page{i}.png"
            page.touch()
            vm.add_page(page)

        assert len(vm.pages) == 3

    def test_clear_pages(self, tmp_path: Path):
        """Clear all pages."""
        vm = ScanViewModel()
        page = tmp_path / "page.png"
        page.touch()
        vm.add_page(page)

        vm.clear()

        assert vm.pages == []
        assert not vm.suggested_date
        assert not vm.suggested_vendor

    def test_current_page_index(self, tmp_path: Path):
        """Track current page index."""
        vm = ScanViewModel()
        for i in range(3):
            page = tmp_path / f"page{i}.png"
            page.touch()
            vm.add_page(page)

        assert vm.current_page_index == 0

        vm.current_page_index = 2
        assert vm.current_page_index == 2

    def test_current_page_property(self, tmp_path: Path):
        """Get current page path."""
        vm = ScanViewModel()
        pages = []
        for i in range(3):
            page = tmp_path / f"page{i}.png"
            page.touch()
            pages.append(page)
            vm.add_page(page)

        vm.current_page_index = 1
        assert vm.current_page == pages[1]

    def test_current_page_none_when_empty(self):
        """Current page is None when no pages."""
        vm = ScanViewModel()
        assert vm.current_page is None


class TestViewModelSuggestions:
    """Test OCR suggestions."""

    def test_set_suggestions(self):
        """Set date and vendor suggestions."""
        vm = ScanViewModel()

        vm.suggested_date = "15.11.2024"
        vm.suggested_vendor = "rewe"

        assert vm.suggested_date == "15.11.2024"
        assert vm.suggested_vendor == "rewe"
