"""Main window for Belegscanner."""

import tempfile
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from belegscanner.constants import CATEGORIES
from belegscanner.email_view import EmailView
from belegscanner.services import (
    ArchiveService,
    ConfigManager,
    OcrService,
    PdfService,
    ScannerService,
)
from belegscanner.viewmodel import ScanViewModel


class BelegscannerWindow(Adw.ApplicationWindow):
    """Main application window with Scanner and Email views.

    Layout:
    +-----------------------------------------------------+
    | Header: [ViewSwitcher: Scanner | E-Mail] [Settings] |
    +-----------------------------------------------------+
    | ViewStack                                           |
    | - Scanner View (existing)                           |
    | - Email View (new)                                  |
    +-----------------------------------------------------+
    | Status Bar                                          |
    +-----------------------------------------------------+
    """

    def __init__(self, **kwargs):
        """Initialize window."""
        super().__init__(**kwargs)

        self.set_title("Belegscanner")
        self.set_default_size(900, 600)

        # Services
        self.config = ConfigManager()
        self.scanner = ScannerService()
        self.ocr = OcrService()
        self.pdf = PdfService()
        self.archive = ArchiveService()

        # ViewModel
        self.vm = ScanViewModel()
        self.vm.connect("notify::status", self._on_status_changed)
        self.vm.connect("notify::is-busy", self._on_busy_changed)

        # Temp directory for scans
        self._temp_dir = tempfile.TemporaryDirectory()

        # Build UI
        self._build_ui()

        # Check config
        if not self.config.archive_path:
            GLib.idle_add(self._show_config_dialog)

    def _build_ui(self):
        """Build the user interface."""
        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header bar with ViewSwitcher
        header = Adw.HeaderBar()
        main_box.append(header)

        # ViewStack for switching between Scanner and Email
        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)

        # ViewSwitcher in header (centered)
        view_switcher = Adw.ViewSwitcher()
        view_switcher.set_stack(self.view_stack)
        view_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(view_switcher)

        # Scanner controls (only visible on scanner page)
        self.scanner_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.scan_btn = Gtk.Button(label="Scannen")
        self.scan_btn.add_css_class("suggested-action")
        self.scan_btn.connect("clicked", self._on_scan_clicked)
        self.scanner_controls.append(self.scan_btn)

        self.rescan_btn = Gtk.Button(label="Nochmal")
        self.rescan_btn.set_sensitive(False)
        self.rescan_btn.connect("clicked", self._on_rescan_clicked)
        self.scanner_controls.append(self.rescan_btn)

        header.pack_start(self.scanner_controls)

        # Settings button
        settings_btn = Gtk.Button(icon_name="preferences-system-symbolic")
        settings_btn.connect("clicked", self._on_settings_clicked)
        header.pack_end(settings_btn)

        # Scanner page content
        scanner_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Content: Paned with preview and input
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        scanner_page.append(paned)

        # Left: Preview
        self._build_preview_panel(paned)

        # Right: Input panel
        self._build_input_panel(paned)

        # Scanner status bar
        self.status_bar = Gtk.Label(label="Bereit")
        self.status_bar.set_xalign(0)
        self.status_bar.set_margin_start(12)
        self.status_bar.set_margin_end(12)
        self.status_bar.set_margin_top(6)
        self.status_bar.set_margin_bottom(6)
        scanner_page.append(self.status_bar)

        # Add scanner page to ViewStack
        self.view_stack.add_titled_with_icon(
            scanner_page, "scanner", "Scanner", "scanner-symbolic"
        )

        # Email view
        self.email_view = EmailView(self.config, self.archive, self)
        self.view_stack.add_titled_with_icon(
            self.email_view, "email", "E-Mail", "mail-unread-symbolic"
        )

        # Add ViewStack to main layout
        main_box.append(self.view_stack)

        # Show/hide scanner controls based on active page
        self.view_stack.connect("notify::visible-child-name", self._on_page_changed)

    def _build_preview_panel(self, paned: Gtk.Paned):
        """Build the preview panel on the left."""
        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        preview_box.set_margin_start(12)
        preview_box.set_margin_end(6)
        preview_box.set_margin_top(12)
        preview_box.set_margin_bottom(12)

        # Scrolled window for image
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        preview_box.append(scrolled)

        # Image
        self.preview_image = Gtk.Picture()
        self.preview_image.set_content_fit(Gtk.ContentFit.CONTAIN)
        scrolled.set_child(self.preview_image)

        # Page navigation
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        nav_box.set_halign(Gtk.Align.CENTER)
        nav_box.set_margin_top(6)
        preview_box.append(nav_box)

        self.prev_btn = Gtk.Button(icon_name="go-previous-symbolic")
        self.prev_btn.connect("clicked", self._on_prev_page)
        self.prev_btn.set_sensitive(False)
        nav_box.append(self.prev_btn)

        self.page_label = Gtk.Label(label="Keine Seite")
        nav_box.append(self.page_label)

        self.next_btn = Gtk.Button(icon_name="go-next-symbolic")
        self.next_btn.connect("clicked", self._on_next_page)
        self.next_btn.set_sensitive(False)
        nav_box.append(self.next_btn)

        paned.set_start_child(preview_box)
        paned.set_resize_start_child(True)

    def _build_input_panel(self, paned: Gtk.Paned):
        """Build the input panel on the right."""
        input_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        input_box.set_margin_start(6)
        input_box.set_margin_end(12)
        input_box.set_margin_top(12)
        input_box.set_margin_bottom(12)
        input_box.set_size_request(300, -1)

        # Date entry
        date_group = Adw.PreferencesGroup(title="Belegdaten")
        input_box.append(date_group)

        self.date_row = Adw.EntryRow(title="Datum (TT.MM.JJJJ)")
        date_group.add(self.date_row)

        self.date_hint = Gtk.Label()
        self.date_hint.set_xalign(0)
        self.date_hint.add_css_class("dim-label")
        self.date_hint.set_margin_start(12)
        input_box.append(self.date_hint)

        # Description entry
        self.desc_row = Adw.EntryRow(title="Beschreibung")
        date_group.add(self.desc_row)

        self.desc_hint = Gtk.Label()
        self.desc_hint.set_xalign(0)
        self.desc_hint.add_css_class("dim-label")
        self.desc_hint.set_margin_start(12)
        input_box.append(self.desc_hint)

        # Category dropdown
        cat_group = Adw.PreferencesGroup(title="Kategorie")
        input_box.append(cat_group)

        self.category_row = Adw.ComboRow(title="Ablageordner")
        cat_model = Gtk.StringList()
        for key, (name, is_cc) in CATEGORIES.items():
            suffix = " (Kreditkarte)" if is_cc else ""
            cat_model.append(f"{name}{suffix}")
        self.category_row.set_model(cat_model)
        cat_group.add(self.category_row)

        # Add page button
        self.add_page_btn = Gtk.Button(label="+ Weitere Seite")
        self.add_page_btn.set_sensitive(False)
        self.add_page_btn.connect("clicked", self._on_add_page_clicked)
        input_box.append(self.add_page_btn)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        input_box.append(spacer)

        # Save button
        self.save_btn = Gtk.Button(label="Speichern")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.set_sensitive(False)
        self.save_btn.connect("clicked", self._on_save_clicked)
        input_box.append(self.save_btn)

        paned.set_end_child(input_box)
        paned.set_resize_end_child(False)

    def _on_status_changed(self, vm, pspec):
        """Update status bar when ViewModel status changes."""
        self.status_bar.set_label(vm.status)

    def _on_busy_changed(self, vm, pspec):
        """Update UI when busy state changes."""
        is_busy = vm.is_busy
        self.scan_btn.set_sensitive(not is_busy)
        self.rescan_btn.set_sensitive(not is_busy and len(self.vm.pages) > 0)
        self.save_btn.set_sensitive(not is_busy and len(self.vm.pages) > 0)
        self.add_page_btn.set_sensitive(not is_busy and len(self.vm.pages) > 0)

    def _on_scan_clicked(self, button):
        """Start scanning."""
        self.vm.clear()
        self._do_scan()

    def _on_rescan_clicked(self, button):
        """Rescan (clear and scan again)."""
        self.vm.clear()
        self._update_preview()
        self._do_scan()

    def _on_add_page_clicked(self, button):
        """Add another page to the document."""
        self._do_scan()

    def _do_scan(self):
        """Perform scan in background thread."""
        self.vm.is_busy = True
        self.vm.status = "Scanne..."

        def scan_thread():
            page_num = len(self.vm.pages) + 1
            output_path = Path(self._temp_dir.name) / f"page_{page_num:03d}.png"

            success = self.scanner.scan_page(output_path)

            if success:
                GLib.idle_add(self._on_scan_complete, output_path)
            else:
                GLib.idle_add(self._on_scan_failed)

        thread = threading.Thread(target=scan_thread, daemon=True)
        thread.start()

    def _on_scan_complete(self, page_path: Path):
        """Handle successful scan."""
        self.vm.add_page(page_path)
        self.vm.current_page_index = len(self.vm.pages) - 1
        self._update_preview()

        # Run OCR in background
        self.vm.status = "OCR läuft..."

        def ocr_thread():
            text = self.ocr.find_best_threshold(page_path)
            date = self.ocr.extract_date(text)
            vendor = self.ocr.extract_vendor(text)
            GLib.idle_add(self._on_ocr_complete, date, vendor)

        thread = threading.Thread(target=ocr_thread, daemon=True)
        thread.start()

    def _on_ocr_complete(self, date: str | None, vendor: str | None):
        """Handle OCR completion."""
        self.vm.is_busy = False
        self.vm.status = "Bereit"

        if date:
            self.vm.suggested_date = date
            self.date_row.set_text(date)
            self.date_hint.set_label(f"Erkannt: {date}")

        if vendor:
            self.vm.suggested_vendor = vendor
            self.desc_row.set_text(vendor)
            self.desc_hint.set_label(f"Erkannt: {vendor}")

        self._update_buttons()

    def _on_scan_failed(self):
        """Handle scan failure."""
        self.vm.is_busy = False
        self.vm.status = "Scan fehlgeschlagen"
        self._show_error("Scanfehler", "Der Scan konnte nicht durchgeführt werden.")

    def _update_preview(self):
        """Update preview image and navigation."""
        pages = self.vm.pages
        idx = self.vm.current_page_index

        if pages and 0 <= idx < len(pages):
            self.preview_image.set_filename(str(pages[idx]))
            self.page_label.set_label(f"Seite {idx + 1} / {len(pages)}")
            self.prev_btn.set_sensitive(idx > 0)
            self.next_btn.set_sensitive(idx < len(pages) - 1)
        else:
            self.preview_image.set_filename(None)
            self.page_label.set_label("Keine Seite")
            self.prev_btn.set_sensitive(False)
            self.next_btn.set_sensitive(False)

    def _update_buttons(self):
        """Update button states."""
        has_pages = len(self.vm.pages) > 0
        self.rescan_btn.set_sensitive(has_pages)
        self.save_btn.set_sensitive(has_pages)
        self.add_page_btn.set_sensitive(has_pages)

    def _on_prev_page(self, button):
        """Go to previous page."""
        if self.vm.current_page_index > 0:
            self.vm.current_page_index -= 1
            self._update_preview()

    def _on_next_page(self, button):
        """Go to next page."""
        if self.vm.current_page_index < len(self.vm.pages) - 1:
            self.vm.current_page_index += 1
            self._update_preview()

    def _on_save_clicked(self, button):
        """Save the scanned document."""
        if not self.vm.pages:
            return

        # Get input values
        date_str = self.date_row.get_text().strip()
        desc = self.desc_row.get_text().strip()
        cat_idx = self.category_row.get_selected()

        # Validate
        if not date_str:
            self._show_error("Fehler", "Bitte Datum eingeben.")
            return

        try:
            date = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            self._show_error("Fehler", "Ungültiges Datumsformat. Bitte TT.MM.JJJJ verwenden.")
            return

        if not desc:
            self._show_error("Fehler", "Bitte Beschreibung eingeben.")
            return

        # Get category
        cat_key = str(cat_idx + 1)
        category, is_cc = CATEGORIES[cat_key]

        # Save in background
        self.vm.is_busy = True
        self.vm.status = "Speichere..."

        def save_thread():
            try:
                # Create PDF
                pdf_path = Path(self._temp_dir.name) / "output.pdf"
                success = self.pdf.create_pdf(self.vm.pages, pdf_path)

                if not success:
                    GLib.idle_add(self._on_save_failed, "PDF konnte nicht erstellt werden.")
                    return

                # Archive
                self.archive.base_path = self.config.archive_path
                final_path = self.archive.archive(pdf_path, date, desc, category, is_cc)

                GLib.idle_add(self._on_save_complete, final_path, is_cc)

            except Exception as e:
                GLib.idle_add(self._on_save_failed, str(e))

        thread = threading.Thread(target=save_thread, daemon=True)
        thread.start()

    def _on_save_complete(self, final_path: Path, is_credit_card: bool):
        """Handle successful save."""
        self.vm.is_busy = False

        msg = f"Gespeichert: {final_path.name}"
        if is_credit_card:
            msg += " (Ablage im Folgemonat)"

        self.vm.status = msg

        # Reset for next scan
        self.vm.clear()
        self.date_row.set_text("")
        self.desc_row.set_text("")
        self.date_hint.set_label("")
        self.desc_hint.set_label("")
        self._update_preview()
        self._update_buttons()

    def _on_save_failed(self, error: str):
        """Handle save failure."""
        self.vm.is_busy = False
        self.vm.status = "Speichern fehlgeschlagen"
        self._show_error("Fehler", error)

    def _on_settings_clicked(self, button):
        """Show settings dialog."""
        self._show_config_dialog()

    def _show_config_dialog(self):
        """Show configuration dialog."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Einstellungen",
            body="Ablage-Pfad konfigurieren:",
        )

        entry = Gtk.Entry()
        entry.set_text(self.config.archive_path or "")
        entry.set_placeholder_text("/pfad/zu/nextcloud/finanzen")
        dialog.set_extra_child(entry)

        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("save", "Speichern")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dialog, response):
            if response == "save":
                path = entry.get_text().strip()
                if path:
                    self.config.archive_path = path
                    self.vm.status = f"Ablage: {path}"

        dialog.connect("response", on_response)
        dialog.present()

    def _show_error(self, title: str, message: str):
        """Show error dialog."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=title,
            body=message,
        )
        dialog.add_response("ok", "OK")
        dialog.present()

    def _on_page_changed(self, stack, pspec):
        """Handle page switch between Scanner and Email views."""
        is_scanner = stack.get_visible_child_name() == "scanner"
        self.scanner_controls.set_visible(is_scanner)
