"""Email view widget for processing IMAP invoices."""

import os
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path

# Disable WebKit sandbox to avoid "bwrap: Permission denied" errors
# on systems without user namespace support
os.environ["WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"] = "1"

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, GLib, Gtk, WebKit

from belegscanner.constants import CATEGORIES
from belegscanner.email_viewmodel import EmailViewModel
from belegscanner.services import (
    ArchiveService,
    ConfigManager,
    CredentialService,
    EmailPdfService,
    ImapService,
    OcrService,
    OllamaService,
)


class EmailView(Gtk.Box):
    """Widget for email-based invoice processing.

    Layout:
    +------------------------------------------+
    | [Verbinden] [Aktualisieren]              |
    +------------------------------------------+
    | Email List (left) | Details (right)       |
    |                   | - Von, Betreff, Datum |
    |   [Email 1]       | - Anhänge (Radio)     |
    |   [Email 2]       | - Datum/Beschr/Kat    |
    |   ...             | [Verarbeiten]         |
    +------------------------------------------+
    """

    def __init__(
        self,
        config: ConfigManager,
        archive: ArchiveService,
        parent_window: Gtk.Window,
    ):
        """Initialize email view.

        Args:
            config: Configuration manager.
            archive: Archive service for saving files.
            parent_window: Parent window for dialogs.
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.config = config
        self.archive = archive
        self.parent_window = parent_window

        # Services
        self.imap: ImapService | None = None
        self.credential = CredentialService()
        self.email_pdf = EmailPdfService()
        self.ocr = OcrService()
        self.ollama = OllamaService()

        # ViewModel
        self.vm = EmailViewModel()
        self.vm.connect("notify::status", self._on_status_changed)
        self.vm.connect("notify::is-busy", self._on_busy_changed)

        # Temp directory
        self._temp_dir = tempfile.TemporaryDirectory()

        # Index to select after refresh (for auto-advance)
        self._next_select_index: int | None = None

        # Prefetch state
        self._prefetch_thread: threading.Thread | None = None
        self._prefetch_pending_uid: int | None = None
        self._imap_credentials: tuple[str, str] | None = None  # (user, password)

        # Build UI
        self._build_ui()

        # Auto-connect when widget becomes visible
        self.connect("realize", self._on_realize)

    def _build_ui(self):
        """Build the user interface."""
        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(6)
        self.append(toolbar)

        self.connect_btn = Gtk.Button(label="Verbinden")
        self.connect_btn.add_css_class("suggested-action")
        self.connect_btn.connect("clicked", self._on_connect_clicked)
        toolbar.append(self.connect_btn)

        self.refresh_btn = Gtk.Button(label="Aktualisieren")
        self.refresh_btn.set_sensitive(False)
        self.refresh_btn.connect("clicked", self._on_refresh_clicked)
        toolbar.append(self.refresh_btn)

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        # Toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_vexpand(True)
        self.append(self.toast_overlay)

        # Main content: Paned
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        self.toast_overlay.set_child(paned)

        # Left: Email list
        self._build_email_list(paned)

        # Right: Details panel
        self._build_details_panel(paned)

        # Status bar
        self.status_bar = Gtk.Label(label=self.vm.status)
        self.status_bar.set_xalign(0)
        self.status_bar.set_margin_start(12)
        self.status_bar.set_margin_end(12)
        self.status_bar.set_margin_top(6)
        self.status_bar.set_margin_bottom(6)
        self.append(self.status_bar)

    def _build_email_list(self, paned: Gtk.Paned):
        """Build the email list panel."""
        list_box_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        list_box_container.set_margin_start(12)
        list_box_container.set_margin_end(6)
        list_box_container.set_margin_top(12)
        list_box_container.set_margin_bottom(12)

        # Search entry
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Suchen...")
        self.search_entry.connect("search-changed", self._on_search_changed)
        list_box_container.append(self.search_entry)

        # Scrolled window for list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_box_container.append(scrolled)

        # ListBox
        self.email_list = Gtk.ListBox()
        self.email_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.email_list.connect("row-selected", self._on_email_selected)
        self.email_list.add_css_class("boxed-list")
        scrolled.set_child(self.email_list)

        # Placeholder when empty
        self.placeholder = Gtk.Label(label="Keine E-Mails")
        self.placeholder.add_css_class("dim-label")
        self.email_list.set_placeholder(self.placeholder)

        paned.set_start_child(list_box_container)
        paned.set_resize_start_child(True)

    def _build_details_panel(self, paned: Gtk.Paned):
        """Build the details/input panel."""
        details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        details_box.set_margin_start(6)
        details_box.set_margin_end(12)
        details_box.set_margin_top(12)
        details_box.set_margin_bottom(12)
        details_box.set_size_request(350, -1)

        # Email info group
        info_group = Adw.PreferencesGroup(title="E-Mail")
        details_box.append(info_group)

        self.from_row = Adw.EntryRow(title="Von")
        self.from_row.set_editable(False)
        info_group.add(self.from_row)

        self.subject_row = Adw.EntryRow(title="Betreff")
        self.subject_row.set_editable(False)
        info_group.add(self.subject_row)

        self.email_date_row = Adw.EntryRow(title="Datum")
        self.email_date_row.set_editable(False)
        info_group.add(self.email_date_row)

        # Email body preview with WebKitWebView
        preview_group = Adw.PreferencesGroup(title="Inhalt")
        preview_group.set_vexpand(True)
        details_box.append(preview_group)

        preview_scrolled = Gtk.ScrolledWindow()
        preview_scrolled.set_min_content_height(150)
        preview_scrolled.set_vexpand(True)
        preview_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Create WebView (sandbox disabled via environment variable)
        self.webview = WebKit.WebView()
        self.webview.set_vexpand(True)
        self.webview.set_hexpand(True)
        # Disable navigation and JavaScript for security
        settings = self.webview.get_settings()
        settings.set_enable_javascript(False)
        settings.set_allow_modal_dialogs(False)
        preview_scrolled.set_child(self.webview)
        preview_group.add(preview_scrolled)

        # Attachments group
        attach_group = Adw.PreferencesGroup(title="Quelle")
        details_box.append(attach_group)

        self.attachment_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        attach_group.add(self.attachment_group)

        # Input group
        input_group = Adw.PreferencesGroup(title="Beleg-Daten")
        details_box.append(input_group)

        self.date_row = Adw.EntryRow(title="Datum (TT.MM.JJJJ)")
        input_group.add(self.date_row)

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
        input_group.add(amount_box)

        self.desc_row = Adw.EntryRow(title="Beschreibung")
        input_group.add(self.desc_row)

        # Category dropdown
        self.category_row = Adw.ComboRow(title="Kategorie")
        cat_model = Gtk.StringList()
        for key, (name, is_cc) in CATEGORIES.items():
            suffix = " (Kreditkarte)" if is_cc else ""
            cat_model.append(f"{name}{suffix}")
        self.category_row.set_model(cat_model)
        input_group.add(self.category_row)

        # KI-Extraktion button
        self.ki_btn = Gtk.Button(label="KI-Extraktion")
        self.ki_btn.set_tooltip_text("Verwendet lokales KI-Modell (Ollama) zur Extraktion")
        self.ki_btn.set_sensitive(False)
        self.ki_btn.connect("clicked", self._on_ki_extract_clicked)
        self.ki_btn.set_margin_top(6)
        details_box.append(self.ki_btn)

        # Button box
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        details_box.append(button_box)

        # Archive only button
        self.archive_btn = Gtk.Button(label="Nur Archivieren")
        self.archive_btn.set_sensitive(False)
        self.archive_btn.set_hexpand(True)
        self.archive_btn.connect("clicked", self._on_archive_clicked)
        button_box.append(self.archive_btn)

        # Process button
        self.process_btn = Gtk.Button(label="Verarbeiten & Ablegen")
        self.process_btn.add_css_class("suggested-action")
        self.process_btn.set_sensitive(False)
        self.process_btn.set_hexpand(True)
        self.process_btn.connect("clicked", self._on_process_clicked)
        button_box.append(self.process_btn)

        paned.set_end_child(details_box)
        paned.set_resize_end_child(False)

    def _on_realize(self, widget):
        """Handle widget realize - try auto-connect."""
        # Use idle_add to ensure UI is fully ready
        GLib.idle_add(self.try_auto_connect)

    def try_auto_connect(self) -> bool:
        """Try to auto-connect if configuration is complete.

        Checks if email configuration is complete and password is available,
        then initiates connection automatically.

        Returns:
            True if auto-connect was initiated, False otherwise.
        """
        # Don't auto-connect if already connected or connecting
        if self.vm.is_connected or self.vm.is_busy:
            return False

        # Check if configuration is complete
        if not self.config.is_email_configured():
            self.vm.status = "E-Mail nicht konfiguriert"
            return False

        # Check if password is available
        user = self.config.imap_user
        password = self.credential.get_password(user)
        if not password:
            self.vm.status = "Kein Passwort gespeichert"
            return False

        # All conditions met - initiate connection
        server = self.config.imap_server
        self._connect(server, user, password)
        return True

    def _on_status_changed(self, vm, pspec):
        """Update status bar."""
        self.status_bar.set_label(vm.status)

    def _on_busy_changed(self, vm, pspec):
        """Update UI when busy state changes."""
        is_busy = vm.is_busy
        self.connect_btn.set_sensitive(not is_busy)
        self.refresh_btn.set_sensitive(not is_busy and vm.is_connected)
        has_email = vm.current_email is not None
        self.process_btn.set_sensitive(not is_busy and has_email)
        self.archive_btn.set_sensitive(not is_busy and has_email)

    def _on_connect_clicked(self, button):
        """Handle connect button click - connect directly with stored credentials."""
        if self.vm.is_connected:
            self._disconnect()
        else:
            self._connect_with_stored_credentials()

    def _connect_with_stored_credentials(self):
        """Connect using credentials from settings.

        Shows error if credentials are missing.
        """
        server = self.config.imap_server
        user = self.config.imap_user

        if not server or not user:
            self._show_error(
                "Keine Zugangsdaten",
                "Bitte konfigurieren Sie die IMAP-Einstellungen "
                "unter Einstellungen (Zahnrad-Symbol).",
            )
            return

        password = self.credential.get_password(user)
        if not password:
            self._show_error(
                "Kein Passwort",
                "Bitte speichern Sie das Passwort in den Einstellungen (Zahnrad-Symbol).",
            )
            return

        self._connect(server, user, password)

    def _connect(self, server: str, user: str, password: str):
        """Connect to IMAP server."""
        self.vm.increment_busy()
        self.vm.status = "Verbinde..."

        # Store credentials for prefetch connection
        self._imap_credentials = (user, password)

        def connect_thread():
            self.imap = ImapService(server)
            success, error_msg = self.imap.connect(user, password)

            if success:
                # Debug: Show available folders
                folders = self.imap.list_folders()
                print(f"[DEBUG] Verfügbare IMAP-Ordner: {folders}")
                print(f"[DEBUG] Konfigurierter Inbox-Ordner: {self.config.imap_inbox}")

                # Establish prefetch connection for parallel fetching
                prefetch_ok = self.imap.connect_prefetch(user, password)
                if not prefetch_ok:
                    print("[DEBUG] Prefetch-Connection konnte nicht hergestellt werden")

                # Fetch emails
                emails = self.imap.list_emails(self.config.imap_inbox)
                GLib.idle_add(self._on_connect_success, emails)
            else:
                GLib.idle_add(self._on_connect_failed, error_msg)

        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()

    def _on_connect_success(self, emails):
        """Handle successful connection."""
        self.vm.is_connected = True
        self.vm.decrement_busy()
        self.vm.status = f"Verbunden - {len(emails)} E-Mail(s)"

        self.connect_btn.set_label("Trennen")
        self.refresh_btn.set_sensitive(True)

        # Set folder for cache operations
        self.vm.set_current_folder(self.config.imap_inbox)
        self.vm.set_emails(emails)
        self._update_email_list()

    def _on_connect_failed(self, error_msg: str = ""):
        """Handle connection failure."""
        self.vm.is_connected = False
        self.vm.decrement_busy()
        self.vm.status = "Verbindung fehlgeschlagen"

        # Provide helpful error message
        message = "IMAP-Verbindung konnte nicht hergestellt werden."
        if "AUTHENTICATIONFAILED" in error_msg or "Invalid credentials" in error_msg:
            message = (
                "Anmeldung fehlgeschlagen.\n\n"
                "Bei Gmail/Google:\n"
                "• Server: imap.gmail.com\n"
                "• App-Passwort erforderlich (nicht das normale Passwort)\n"
                "• Erstellen unter: myaccount.google.com/apppasswords"
            )
        elif error_msg:
            message = f"Fehler: {error_msg}"

        self._show_error("Verbindungsfehler", message)

    def _disconnect(self):
        """Disconnect from IMAP."""
        if self.imap:
            self.imap.disconnect()
            self.imap = None

        self.vm.is_connected = False
        self.vm.status = "Nicht verbunden"
        self.connect_btn.set_label("Verbinden")
        self.refresh_btn.set_sensitive(False)
        self.vm.clear()
        self._update_email_list()
        self._clear_details()

    def _on_refresh_clicked(self, button):
        """Refresh email list."""
        if not self.imap or not self.vm.is_connected:
            return

        self.vm.increment_busy()
        self.vm.status = "Aktualisiere..."

        def refresh_thread():
            import time
            print(f"[TIMING] refresh_thread START: {time.time()}")
            emails = self.imap.list_emails(self.config.imap_inbox)
            print(f"[TIMING] refresh_thread after list_emails: {time.time()}")
            GLib.idle_add(self._on_refresh_complete, emails)

        thread = threading.Thread(target=refresh_thread, daemon=True)
        thread.start()

    def _on_refresh_complete(self, emails):
        """Handle refresh completion."""
        import time
        print(f"[TIMING] _on_refresh_complete START: {time.time()}")
        self.vm.decrement_busy()
        self.vm.status = f"{len(emails)} E-Mail(s)"
        self.vm.set_emails(emails)
        print(f"[TIMING] after set_emails: {time.time()}")
        self._update_email_list()
        print(f"[TIMING] after _update_email_list: {time.time()}")

        # Auto-select next email if index was stored
        if self._next_select_index is not None:
            filtered = self.vm.filtered_emails
            if filtered:
                # Select same index, or last if list is shorter
                idx = min(self._next_select_index, len(filtered) - 1)
                # Select directly - list was just updated, rows are ready
                row = self.email_list.get_row_at_index(idx)
                if row:
                    print(f"[TIMING] before select_row: {time.time()}")
                    self.email_list.select_row(row)
                    print(f"[TIMING] after select_row: {time.time()}")
            self._next_select_index = None
        print(f"[TIMING] _on_refresh_complete END: {time.time()}")

    def _on_search_changed(self, entry):
        """Handle search entry changes."""
        query = entry.get_text()
        self.vm.set_filter(query)
        self._update_email_list()

    def _update_email_list(self):
        """Update the email ListBox."""
        # Clear existing
        while True:
            row = self.email_list.get_row_at_index(0)
            if row is None:
                break
            self.email_list.remove(row)

        # Add filtered emails
        for email in self.vm.filtered_emails:
            row = Adw.ActionRow()
            row.set_title(GLib.markup_escape_text(email.sender[:40]))
            row.set_subtitle(GLib.markup_escape_text(email.subject[:50]))

            date_label = Gtk.Label(label=email.date.strftime("%d.%m.%Y"))
            date_label.add_css_class("dim-label")
            row.add_suffix(date_label)

            # Attachment icon as separate column after date
            if email.has_attachments:
                icon = Gtk.Image.new_from_icon_name("mail-attachment-symbolic")
                row.add_suffix(icon)

            row.email_uid = email.uid
            self.email_list.append(row)

    def _on_email_selected(self, listbox, row):
        """Handle email selection."""
        if row is None:
            self.vm.select_email(-1)
            self._clear_details()
            return

        uid = row.email_uid
        self.vm.select_email(uid)

        # Check cache first
        cached_email = self.vm.get_cached_email(uid)
        if cached_email:
            import time
            print(f"[TIMING] Cache HIT for UID {uid}: {time.time()}")
            self.vm.set_current_email(cached_email)
            self._update_details()
            self.vm.status = "Bereit"
            return

        # Cache miss - fetch from server
        if self.imap and self.vm.is_connected:
            self.vm.increment_busy()
            self.vm.status = "Lade E-Mail..."
            # Start fetch request tracking to prevent race conditions
            request_id = self.vm.start_fetch_request(uid)

            def fetch_thread():
                import time
                print(f"[TIMING] fetch_thread START (cache miss): {time.time()}")
                email = self.imap.fetch_email(uid, self.config.imap_inbox)
                print(f"[TIMING] fetch_thread after fetch_email: {time.time()}")
                GLib.idle_add(self._on_email_fetched, email, request_id)

            thread = threading.Thread(target=fetch_thread, daemon=True)
            thread.start()

    def _on_email_fetched(self, email, request_id: int):
        """Handle email fetch completion.

        Args:
            email: The fetched EmailMessage or None on error.
            request_id: The request ID from start_fetch_request.
        """
        import time
        print(f"[TIMING] _on_email_fetched START: {time.time()}")
        self.vm.decrement_busy()

        if email:
            # Complete the fetch request - rejected if user selected another email
            if not self.vm.complete_fetch_request(request_id, email):
                print(f"[TIMING] Stale request {request_id} rejected")
                return  # Stale request, ignore
            self._update_details()
            self.vm.status = "Bereit"
        else:
            self._clear_details()
            self.vm.status = "E-Mail konnte nicht geladen werden"
        print(f"[TIMING] _on_email_fetched END: {time.time()}")

    def _update_details(self):
        """Update details panel with current email."""
        import time
        print(f"[TIMING] _update_details START: {time.time()}")
        email = self.vm.current_email
        if not email:
            self._clear_details()
            return

        # Update info
        self.from_row.set_text(email.sender[:60] or "-")
        self.subject_row.set_text(email.subject[:80] or "-")
        self.email_date_row.set_text(email.date.strftime("%d.%m.%Y %H:%M"))
        print(f"[TIMING] after info rows: {time.time()}")

        # Update email body preview
        self._update_body_preview()
        print(f"[TIMING] after _update_body_preview: {time.time()}")

        # Update attachments
        self._update_attachment_options()
        print(f"[TIMING] after _update_attachment_options: {time.time()}")

        # Update suggestions
        self.date_row.set_text(self.vm.suggested_date)
        self.desc_row.set_text(self.vm.suggested_description)

        # Update amount (if available)
        if self.vm.suggested_amount:
            display_amount = self.vm.suggested_amount.replace(".", ",")
            self.amount_row.set_text(display_amount)
            currencies = ["EUR", "USD", "CHF", "GBP"]
            if self.vm.suggested_currency in currencies:
                self.currency_dropdown.set_selected(
                    currencies.index(self.vm.suggested_currency)
                )
        else:
            self.amount_row.set_text("")
            self.currency_dropdown.set_selected(0)  # Default EUR

        self.process_btn.set_sensitive(True)
        self.archive_btn.set_sensitive(True)
        self.ki_btn.set_sensitive(bool(email.body_text or email.body_html))

        # Auto-fallback: Run KI extraction if extraction results are incomplete
        has_gaps = (
            not self.vm.suggested_description
            or not self.vm.suggested_amount
            or len(self.vm.suggested_description) < 3
        )
        has_body = email.body_text or email.body_html
        if has_gaps and has_body and self.ollama.is_available():
            self._do_ki_extraction()

    def _update_body_preview(self):
        """Update email body preview in WebView."""
        email = self.vm.current_email
        if not email:
            self.webview.load_html("<html><body></body></html>", None)
            return

        # Prefer HTML, fallback to plain text
        if email.body_html:
            # Wrap HTML in basic structure with charset
            html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body {{ font-family: sans-serif; font-size: 12px; margin: 8px; }}
</style></head>
<body>{email.body_html}</body>
</html>"""
            self.webview.load_html(html, None)
        elif email.body_text:
            # Convert plain text to HTML
            escaped_text = (
                email.body_text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
            )
            html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body {{ font-family: monospace; font-size: 12px; margin: 8px; white-space: pre-wrap; }}
</style></head>
<body>{escaped_text}</body>
</html>"""
            self.webview.load_html(html, None)
        else:
            self.webview.load_html(
                "<html><body><em>Kein Inhalt</em></body></html>", None
            )

    def _update_attachment_options(self):
        """Update attachment radio buttons with open buttons."""
        # Clear existing
        while True:
            child = self.attachment_group.get_first_child()
            if child is None:
                break
            self.attachment_group.remove(child)

        email = self.vm.current_email
        if not email:
            return

        first_radio = None

        # PDF attachments (including application/octet-stream with .pdf extension)
        for i, att in enumerate(email.attachments):
            is_pdf = att.content_type == "application/pdf" or (
                att.content_type == "application/octet-stream"
                and att.filename.lower().endswith(".pdf")
            )
            if is_pdf:
                # Row with radio button and open button
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

                radio = Gtk.CheckButton(label=f"{att.filename} [{att.size // 1024}KB]")
                radio.set_hexpand(True)
                if first_radio:
                    radio.set_group(first_radio)
                else:
                    first_radio = radio
                    radio.set_active(True)
                radio.attachment_index = i
                radio.connect("toggled", self._on_attachment_toggled)
                row.append(radio)

                # Open button
                open_btn = Gtk.Button(label="Öffnen")
                open_btn.add_css_class("flat")
                open_btn.attachment_index = i
                open_btn.connect("clicked", self._on_open_attachment_clicked)
                row.append(open_btn)

                self.attachment_group.append(row)

        # Email as PDF option
        email_radio = Gtk.CheckButton(label="E-Mail als PDF speichern")
        if first_radio:
            email_radio.set_group(first_radio)
        else:
            first_radio = email_radio
            email_radio.set_active(True)
        email_radio.attachment_index = -1
        email_radio.connect("toggled", self._on_attachment_toggled)
        self.attachment_group.append(email_radio)

    def _on_open_attachment_clicked(self, button):
        """Open PDF attachment in external viewer."""
        email = self.vm.current_email
        if not email:
            return

        idx = button.attachment_index
        if idx < 0 or idx >= len(email.attachments):
            return

        att = email.attachments[idx]

        # Save to temp file
        temp_path = Path(self._temp_dir.name) / att.filename
        temp_path.write_bytes(att.data)

        # Open with system default viewer
        try:
            subprocess.Popen(["xdg-open", str(temp_path)])
        except Exception as e:
            self._show_error("Fehler", f"PDF konnte nicht geöffnet werden: {e}")

    def _on_attachment_toggled(self, button):
        """Handle attachment selection change."""
        if button.get_active():
            self.vm.selected_attachment_index = button.attachment_index

    def _clear_details(self):
        """Clear details panel."""
        self.from_row.set_text("")
        self.subject_row.set_text("")
        self.email_date_row.set_text("")

        # Clear webview
        self.webview.load_html("<html><body></body></html>", None)

        while True:
            child = self.attachment_group.get_first_child()
            if child is None:
                break
            self.attachment_group.remove(child)

        self.date_row.set_text("")
        self.amount_row.set_text("")
        self.currency_dropdown.set_selected(0)  # Reset to EUR
        self.desc_row.set_text("")
        self.process_btn.set_sensitive(False)
        self.archive_btn.set_sensitive(False)
        self.ki_btn.set_sensitive(False)

    def _get_current_email_index(self) -> int:
        """Get index of currently selected email in filtered list.

        Returns:
            Index of selected email, or -1 if none selected.
        """
        if not self.vm.selected_email:
            return -1
        uid = self.vm.selected_email.uid
        for i, email in enumerate(self.vm.filtered_emails):
            if email.uid == uid:
                return i
        return -1

    def _on_archive_clicked(self, button):
        """Archive email without processing (skip irrelevant emails)."""
        email = self.vm.current_email
        if not email:
            return

        # Store current index for auto-advance after refresh
        self._next_select_index = self._get_current_email_index()

        # Start prefetching next email before archiving begins
        if self._next_select_index is not None:
            next_uid = self.vm.get_next_email_uid(self._next_select_index)
            if next_uid and not self.vm.get_cached_email(next_uid):
                self._start_prefetch(next_uid)

        self.vm.increment_busy()
        self.vm.status = "Archiviere..."

        archived_uid = email.uid  # Capture for closure

        def archive_thread():
            try:
                # Just move email to archive folder
                if self.imap:
                    success = self.imap.move_email(
                        email.uid,
                        self.config.imap_inbox,
                        self.config.imap_archive,
                    )
                    if success:
                        GLib.idle_add(self._on_archive_success, archived_uid)
                    else:
                        GLib.idle_add(
                            self._on_process_failed, "E-Mail konnte nicht verschoben werden."
                        )
                else:
                    GLib.idle_add(self._on_process_failed, "Nicht verbunden.")
            except Exception as e:
                GLib.idle_add(self._on_process_failed, str(e))

        thread = threading.Thread(target=archive_thread, daemon=True)
        thread.start()

    def _on_archive_success(self, archived_uid: int):
        """Handle successful archive-only operation."""
        import time
        print(f"[TIMING] _on_archive_success START: {time.time()}")

        # Remove archived email from cache
        self.vm.invalidate_cached_email(archived_uid)

        self._clear_details()
        print(f"[TIMING] after _clear_details: {time.time()}")
        # Start refresh first, then show toast (toast shouldn't block refresh)
        self._on_refresh_clicked(None)
        print(f"[TIMING] after _on_refresh_clicked: {time.time()}")
        self._show_toast("E-Mail archiviert ✓")
        print(f"[TIMING] after _show_toast: {time.time()}")

    def _on_process_clicked(self, button):
        """Process and archive the selected email/attachment."""
        email = self.vm.current_email
        if not email:
            return

        # Store current index for auto-advance after refresh
        self._next_select_index = self._get_current_email_index()

        # Validate input
        date_str = self.date_row.get_text().strip()
        amount_str = self.amount_row.get_text().strip()
        desc = self.desc_row.get_text().strip()
        cat_idx = self.category_row.get_selected()
        currency_idx = self.currency_dropdown.get_selected()

        if not date_str:
            self._show_error("Fehler", "Bitte Datum eingeben.")
            return

        try:
            date = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            self._show_error("Fehler", "Ungültiges Datum. Format: TT.MM.JJJJ")
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

        if not desc:
            self._show_error("Fehler", "Bitte Beschreibung eingeben.")
            return

        cat_key = str(cat_idx + 1)
        category, is_cc = CATEGORIES[cat_key]
        attachment_idx = self.vm.selected_attachment_index

        # Start prefetching next email before processing begins
        if self._next_select_index is not None:
            next_uid = self.vm.get_next_email_uid(self._next_select_index)
            if next_uid and not self.vm.get_cached_email(next_uid):
                self._start_prefetch(next_uid)

        # Process in background
        self.vm.increment_busy()
        self.vm.status = "Verarbeite..."

        def process_thread():
            try:
                # Get or create PDF
                if attachment_idx >= 0 and attachment_idx < len(email.attachments):
                    # Use attachment
                    att = email.attachments[attachment_idx]
                    pdf_path = Path(self._temp_dir.name) / "attachment.pdf"
                    pdf_path.write_bytes(att.data)
                else:
                    # Create PDF from email
                    pdf_path = Path(self._temp_dir.name) / "email.pdf"
                    success = self.email_pdf.create_pdf(
                        sender=email.sender,
                        subject=email.subject,
                        date=email.date,
                        message_id=email.message_id,
                        body_text=email.body_text,
                        body_html=email.body_html,
                        output_path=pdf_path,
                    )
                    if not success:
                        GLib.idle_add(
                            self._on_process_failed, "PDF konnte nicht erstellt werden."
                        )
                        return

                # Archive with amount
                self.archive.base_path = self.config.archive_path
                final_path = self.archive.archive(
                    pdf_path, date, desc, category, is_cc,
                    currency=currency, amount=amount
                )

                # Move email to archive folder
                processed_uid = email.uid  # Capture for callback
                if self.imap:
                    self.imap.move_email(
                        email.uid,
                        self.config.imap_inbox,
                        self.config.imap_archive,
                    )

                GLib.idle_add(self._on_process_success, final_path, is_cc, processed_uid)

            except Exception as e:
                GLib.idle_add(self._on_process_failed, str(e))

        thread = threading.Thread(target=process_thread, daemon=True)
        thread.start()

    def _on_process_success(self, final_path: Path, is_cc: bool, processed_uid: int):
        """Handle successful processing."""
        # Remove processed email from cache
        self.vm.invalidate_cached_email(processed_uid)

        self._clear_details()
        # Start refresh first, then show toast (toast shouldn't block refresh)
        self._on_refresh_clicked(None)

        # Show toast with filename
        msg = f"Gespeichert: {final_path.name} ✓"
        if is_cc:
            msg = f"Gespeichert (Folgemonat): {final_path.name} ✓"
        self._show_toast(msg, timeout=3)

    def _on_process_failed(self, error: str):
        """Handle processing failure."""
        self.vm.decrement_busy()
        self.vm.status = "Verarbeitung fehlgeschlagen"
        self._show_error("Fehler", error)

    def _show_toast(self, message: str, timeout: int = 2):
        """Show a brief toast notification.

        Args:
            message: Message to display.
            timeout: Duration in seconds (default 2).
        """
        toast = Adw.Toast(title=message, timeout=timeout)
        self.toast_overlay.add_toast(toast)

    def _show_error(self, title: str, message: str):
        """Show error dialog."""
        dialog = Adw.MessageDialog(
            transient_for=self.parent_window,
            heading=title,
            body=message,
        )
        dialog.add_response("ok", "OK")
        dialog.present()

    def _start_prefetch(self, uid: int):
        """Start prefetching an email in the background.

        Uses the dedicated prefetch connection to fetch the email
        while other operations continue on the main connection.

        Args:
            uid: UID of email to prefetch.
        """
        # Don't start if already prefetching
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            return

        if not self.imap:
            return

        self._prefetch_pending_uid = uid
        import time
        print(f"[TIMING] _start_prefetch for UID {uid}: {time.time()}")

        def prefetch_thread():
            email = self.imap.fetch_email_prefetch(uid, self.config.imap_inbox)
            if email:
                GLib.idle_add(self._on_prefetch_complete, email)
            else:
                # Prefetch failed - just clear pending state
                GLib.idle_add(self._on_prefetch_failed)

        self._prefetch_thread = threading.Thread(target=prefetch_thread, daemon=True)
        self._prefetch_thread.start()

    def _on_prefetch_complete(self, email):
        """Handle prefetch completion.

        Stores the prefetched email in cache for quick access.

        Args:
            email: Prefetched EmailMessage.
        """
        import time
        print(f"[TIMING] _on_prefetch_complete for UID {email.uid}: {time.time()}")
        self.vm.cache_email(email)
        self._prefetch_pending_uid = None

    def _on_prefetch_failed(self):
        """Handle prefetch failure - just clear state."""
        self._prefetch_pending_uid = None

    def _on_ki_extract_clicked(self, button):
        """Handle KI-Extraktion button click."""
        email = self.vm.current_email
        if not email or not (email.body_text or email.body_html):
            self._show_error("Fehler", "Kein E-Mail-Text vorhanden.")
            return

        if not self.ollama.is_available():
            self._show_error(
                "Ollama nicht verfügbar",
                "Bitte Ollama starten:\n\n"
                "ollama serve\n\n"
                "Modell installieren:\n\n"
                "ollama pull phi3",
            )
            return

        self._do_ki_extraction()

    def _do_ki_extraction(self):
        """Run KI extraction in background thread."""
        email = self.vm.current_email
        if not email:
            return

        self.vm.ki_extraction_running = True
        self.vm.status = "KI-Extraktion läuft..."
        self.ki_btn.set_sensitive(False)

        # Use body_text if available, otherwise strip HTML from body_html
        text_for_extraction = email.body_text or self._strip_html(email.body_html)

        def ki_thread():
            result = self.ollama.extract(text_for_extraction)
            GLib.idle_add(self._on_ki_extraction_complete, result)

        thread = threading.Thread(target=ki_thread, daemon=True)
        thread.start()

    def _on_ki_extraction_complete(self, result):
        """Handle KI extraction completion."""
        self.vm.ki_extraction_running = False
        self.vm.status = "KI-Extraktion abgeschlossen"
        self.ki_btn.set_sensitive(True)

        if result.amount and not self.amount_row.get_text():
            display_amount = result.amount.replace(".", ",")
            self.amount_row.set_text(display_amount)
            if result.currency:
                currencies = ["EUR", "USD", "CHF", "GBP"]
                if result.currency in currencies:
                    self.currency_dropdown.set_selected(currencies.index(result.currency))

        if result.vendor and not self.desc_row.get_text():
            self.desc_row.set_text(result.vendor)

    def _strip_html(self, html: str | None) -> str:
        """Strip HTML tags and return plain text.

        Args:
            html: HTML string or None.

        Returns:
            Plain text with HTML tags removed.
        """
        import re

        if not html:
            return ""
        # Remove script and style elements
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode common HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()
