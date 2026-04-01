"""Main window for Belegscanner."""

import tempfile
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from belegscanner.constants import CATEGORIES
from belegscanner.email_view import EmailView
from belegscanner.services import (
    ArchiveService,
    ConfigManager,
    CredentialService,
    OcrService,
    OllamaService,
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
        self.credential = CredentialService()
        self.scanner = ScannerService()
        self.ocr = OcrService()
        self.ollama = OllamaService()
        self.pdf = PdfService()
        self.archive = ArchiveService()

        # Store OCR text for KI fallback
        self._current_ocr_text: str | None = None

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
        self.view_stack.add_titled_with_icon(scanner_page, "scanner", "Scanner", "scanner-symbolic")

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

        # Amount row with currency dropdown and entry
        amount_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.currency_dropdown = Gtk.DropDown()
        currency_model = Gtk.StringList()
        for currency in ["EUR", "USD", "CHF", "GBP"]:
            currency_model.append(currency)
        self.currency_dropdown.set_model(currency_model)
        self.currency_dropdown.set_size_request(80, -1)
        amount_box.append(self.currency_dropdown)

        self.amount_row = Adw.EntryRow(title="Betrag (z.B. 27,07)")
        self.amount_row.set_hexpand(True)
        amount_box.append(self.amount_row)

        date_group.add(amount_box)

        self.amount_hint = Gtk.Label()
        self.amount_hint.set_xalign(0)
        self.amount_hint.add_css_class("dim-label")
        self.amount_hint.set_margin_start(12)
        input_box.append(self.amount_hint)

        # Description entry
        self.desc_row = Adw.EntryRow(title="Beschreibung")
        date_group.add(self.desc_row)

        self.desc_hint = Gtk.Label()
        self.desc_hint.set_xalign(0)
        self.desc_hint.add_css_class("dim-label")
        self.desc_hint.set_margin_start(12)
        input_box.append(self.desc_hint)

        # KI-Extraktion button
        self.ki_btn = Gtk.Button(label="KI-Extraktion")
        self.ki_btn.set_tooltip_text("Verwendet lokales KI-Modell (Ollama) zur Extraktion")
        self.ki_btn.set_sensitive(False)
        self.ki_btn.connect("clicked", self._on_ki_extract_clicked)
        self.ki_btn.set_margin_top(6)
        input_box.append(self.ki_btn)

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
            amount = self.ocr.extract_amount(text)
            GLib.idle_add(self._on_ocr_complete, text, date, vendor, amount)

        thread = threading.Thread(target=ocr_thread, daemon=True)
        thread.start()

    def _on_ocr_complete(
        self,
        ocr_text: str | None,
        date: str | None,
        vendor: str | None,
        amount: tuple[str, str] | None,
    ):
        """Handle OCR completion."""
        # Store OCR text for KI fallback
        self._current_ocr_text = ocr_text

        if date:
            self.vm.suggested_date = date
            self.date_row.set_text(date)
            self.date_hint.set_label(f"Erkannt: {date}")

        if amount:
            currency, amount_value = amount
            self.vm.suggested_currency = currency
            self.vm.suggested_amount = amount_value
            # Set currency dropdown
            currencies = ["EUR", "USD", "CHF", "GBP"]
            if currency in currencies:
                self.currency_dropdown.set_selected(currencies.index(currency))
            # Set amount (convert to German format for display)
            display_amount = amount_value.replace(".", ",")
            self.amount_row.set_text(display_amount)
            self.amount_hint.set_label(f"Erkannt: {currency} {display_amount}")

        if vendor:
            self.vm.suggested_vendor = vendor
            self.desc_row.set_text(vendor)
            self.desc_hint.set_label(f"Erkannt: {vendor}")

        self._update_buttons()

        # Auto-fallback: Run KI extraction if OCR results are incomplete
        has_gaps = not date or not vendor or not amount or (vendor and len(vendor) < 3)
        if has_gaps and ocr_text and self.ollama.is_available():
            self._do_ki_extraction()
        else:
            self.vm.is_busy = False
            self.vm.status = "Bereit"

    def _on_ki_extract_clicked(self, button):
        """Handle KI-Extraktion button click."""
        if not self._current_ocr_text:
            self._show_error("Fehler", "Kein OCR-Text vorhanden. Bitte zuerst scannen.")
            return

        if not self.ollama.is_available():
            self._show_error(
                "Ollama nicht verfügbar",
                "Bitte Ollama starten:\n\nollama serve\n\nModell installieren:\n\nollama pull phi3",
            )
            return

        self._do_ki_extraction()

    def _do_ki_extraction(self):
        """Run KI extraction in background thread."""
        self.vm.ki_extraction_running = True
        self.vm.status = "KI-Extraktion läuft..."
        self.ki_btn.set_sensitive(False)

        def ki_thread():
            result = self.ollama.extract(self._current_ocr_text)
            GLib.idle_add(self._on_ki_extraction_complete, result)

        thread = threading.Thread(target=ki_thread, daemon=True)
        thread.start()

    def _on_ki_extraction_complete(self, result):
        """Handle KI extraction completion."""
        self.vm.ki_extraction_running = False
        self.vm.is_busy = False
        self.vm.status = "KI-Extraktion abgeschlossen"
        self.ki_btn.set_sensitive(True)

        if result.date and not self.date_row.get_text():
            self.date_row.set_text(result.date)
            self.date_hint.set_label(f"KI: {result.date}")

        if result.amount and not self.amount_row.get_text():
            display_amount = result.amount.replace(".", ",")
            self.amount_row.set_text(display_amount)
            if result.currency:
                currencies = ["EUR", "USD", "CHF", "GBP"]
                if result.currency in currencies:
                    self.currency_dropdown.set_selected(currencies.index(result.currency))
            self.amount_hint.set_label(f"KI: {result.currency or 'EUR'} {display_amount}")

        if result.vendor and not self.desc_row.get_text():
            self.desc_row.set_text(result.vendor)
            self.desc_hint.set_label(f"KI: {result.vendor}")

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
        self.ki_btn.set_sensitive(has_pages and bool(self._current_ocr_text))

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
        amount_str = self.amount_row.get_text().strip()
        desc = self.desc_row.get_text().strip()
        cat_idx = self.category_row.get_selected()
        currency_idx = self.currency_dropdown.get_selected()

        # Validate date
        if not date_str:
            self._show_error("Fehler", "Bitte Datum eingeben.")
            return

        try:
            date = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            self._show_error("Fehler", "Ungültiges Datumsformat. Bitte TT.MM.JJJJ verwenden.")
            return

        # Validate amount (required)
        if not amount_str:
            self._show_error("Fehler", "Bitte Betrag eingeben.")
            return

        # Parse amount: accept both , and . as decimal separator
        amount_str = amount_str.replace(",", ".")
        try:
            amount_value = float(amount_str)
            amount = f"{amount_value:.2f}"
        except ValueError:
            self._show_error("Fehler", "Ungültiger Betrag. Bitte Zahl eingeben (z.B. 27,07).")
            return

        # Get currency
        currencies = ["EUR", "USD", "CHF", "GBP"]
        currency = currencies[currency_idx] if currency_idx < len(currencies) else "EUR"

        # Validate description
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

                # Archive with amount
                self.archive.base_path = self.config.archive_path
                final_path = self.archive.archive(
                    pdf_path, date, desc, category, is_cc, currency=currency, amount=amount
                )

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
        self.amount_row.set_text("")
        self.currency_dropdown.set_selected(0)  # Reset to EUR
        self.desc_row.set_text("")
        self.date_hint.set_label("")
        self.amount_hint.set_label("")
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
        """Show configuration dialog with archive path and IMAP settings."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Einstellungen",
        )

        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        # Archive path group
        archive_group = Adw.PreferencesGroup(title="Ablage")
        main_box.append(archive_group)

        archive_entry = Adw.EntryRow(title="Ablage-Pfad")
        archive_entry.set_text(self.config.archive_path or "")
        archive_group.add(archive_entry)

        # IMAP settings group
        imap_group = Adw.PreferencesGroup(title="E-Mail (IMAP)")
        main_box.append(imap_group)

        server_entry = Adw.EntryRow(title="IMAP-Server")
        server_entry.set_text(self.config.imap_server or "")
        imap_group.add(server_entry)

        user_entry = Adw.EntryRow(title="E-Mail-Adresse")
        user_entry.set_text(self.config.imap_user or "")
        imap_group.add(user_entry)

        pass_entry = Adw.PasswordEntryRow(title="Passwort")
        # Load existing password from keyring
        if self.config.imap_user:
            stored_pass = self.credential.get_password(self.config.imap_user)
            if stored_pass:
                pass_entry.set_text(stored_pass)
        imap_group.add(pass_entry)

        inbox_entry = Adw.EntryRow(title="Posteingang-Ordner")
        inbox_entry.set_text(self.config.imap_inbox or "")
        imap_group.add(inbox_entry)

        archive_folder_entry = Adw.EntryRow(title="Archiv-Ordner")
        archive_folder_entry.set_text(self.config.imap_archive or "")
        imap_group.add(archive_folder_entry)

        dialog.set_extra_child(main_box)

        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("save", "Speichern")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dialog, response):
            if response == "save":
                # Save archive path
                path = archive_entry.get_text().strip()
                if path:
                    self.config.archive_path = path

                # Save IMAP settings
                server = server_entry.get_text().strip()
                user = user_entry.get_text().strip()
                password = pass_entry.get_text()
                inbox = inbox_entry.get_text().strip()
                archive_folder = archive_folder_entry.get_text().strip()

                if server:
                    self.config.imap_server = server
                if user:
                    self.config.imap_user = user
                if password and user:
                    self.credential.store_password(user, password)
                if inbox:
                    self.config.imap_inbox = inbox
                if archive_folder:
                    self.config.imap_archive = archive_folder

                self.vm.status = "Einstellungen gespeichert"

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
