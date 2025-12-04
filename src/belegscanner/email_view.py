"""Email view widget for processing IMAP invoices."""

import tempfile
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from belegscanner.constants import CATEGORIES
from belegscanner.email_viewmodel import EmailViewModel
from belegscanner.services import (
    ArchiveService,
    ConfigManager,
    CredentialService,
    EmailPdfService,
    ImapService,
    OcrService,
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

        # ViewModel
        self.vm = EmailViewModel()
        self.vm.connect("notify::status", self._on_status_changed)
        self.vm.connect("notify::is-busy", self._on_busy_changed)

        # Temp directory
        self._temp_dir = tempfile.TemporaryDirectory()

        # Build UI
        self._build_ui()

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

        # Main content: Paned
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        self.append(paned)

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
        list_box_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_box_container.set_margin_start(12)
        list_box_container.set_margin_end(6)
        list_box_container.set_margin_top(12)
        list_box_container.set_margin_bottom(12)

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

        # Spacer
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        details_box.append(spacer)

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
        """Handle connect button click."""
        if self.vm.is_connected:
            self._disconnect()
        else:
            self._show_connect_dialog()

    def _show_connect_dialog(self):
        """Show IMAP connection dialog."""
        dialog = Adw.MessageDialog(
            transient_for=self.parent_window,
            heading="IMAP-Verbindung",
            body="E-Mail-Konto verbinden",
        )

        # Form
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        server_entry = Adw.EntryRow(title="IMAP-Server")
        server_entry.set_text(self.config.imap_server or "")

        user_entry = Adw.EntryRow(title="E-Mail-Adresse")
        user_entry.set_text(self.config.imap_user or "")

        pass_entry = Adw.PasswordEntryRow(title="Passwort")
        # Try to load from keyring
        if self.config.imap_user:
            stored_pass = self.credential.get_password(self.config.imap_user)
            if stored_pass:
                pass_entry.set_text(stored_pass)

        save_pass = Gtk.CheckButton(label="Passwort speichern")
        save_pass.set_active(True)

        form_group = Adw.PreferencesGroup()
        form_group.add(server_entry)
        form_group.add(user_entry)
        form_group.add(pass_entry)
        form.append(form_group)
        form.append(save_pass)

        dialog.set_extra_child(form)

        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("connect", "Verbinden")
        dialog.set_response_appearance("connect", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dialog, response):
            if response == "connect":
                server = server_entry.get_text().strip()
                user = user_entry.get_text().strip()
                password = pass_entry.get_text()

                if server and user and password:
                    # Save config
                    self.config.imap_server = server
                    self.config.imap_user = user

                    if save_pass.get_active():
                        self.credential.store_password(user, password)

                    self._connect(server, user, password)

        dialog.connect("response", on_response)
        dialog.present()

    def _connect(self, server: str, user: str, password: str):
        """Connect to IMAP server."""
        self.vm.is_busy = True
        self.vm.status = "Verbinde..."

        def connect_thread():
            self.imap = ImapService(server)
            success, error_msg = self.imap.connect(user, password)

            if success:
                # Debug: Show available folders
                folders = self.imap.list_folders()
                print(f"[DEBUG] Verfügbare IMAP-Ordner: {folders}")
                print(f"[DEBUG] Konfigurierter Inbox-Ordner: {self.config.imap_inbox}")

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
        self.vm.is_busy = False
        self.vm.status = f"Verbunden - {len(emails)} E-Mail(s)"

        self.connect_btn.set_label("Trennen")
        self.refresh_btn.set_sensitive(True)

        self.vm.set_emails(emails)
        self._update_email_list()

    def _on_connect_failed(self, error_msg: str = ""):
        """Handle connection failure."""
        self.vm.is_connected = False
        self.vm.is_busy = False
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

        self.vm.is_busy = True
        self.vm.status = "Aktualisiere..."

        def refresh_thread():
            emails = self.imap.list_emails(self.config.imap_inbox)
            GLib.idle_add(self._on_refresh_complete, emails)

        thread = threading.Thread(target=refresh_thread, daemon=True)
        thread.start()

    def _on_refresh_complete(self, emails):
        """Handle refresh completion."""
        self.vm.is_busy = False
        self.vm.status = f"{len(emails)} E-Mail(s)"
        self.vm.set_emails(emails)
        self._update_email_list()

    def _update_email_list(self):
        """Update the email ListBox."""
        # Clear existing
        while True:
            row = self.email_list.get_row_at_index(0)
            if row is None:
                break
            self.email_list.remove(row)

        # Add emails
        for email in self.vm.emails:
            row = Adw.ActionRow()
            row.set_title(email.sender[:40])
            row.set_subtitle(email.subject[:50])

            date_label = Gtk.Label(label=email.date.strftime("%d.%m.%Y"))
            date_label.add_css_class("dim-label")
            row.add_suffix(date_label)

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

        # Fetch full email
        if self.imap and self.vm.is_connected:
            self.vm.is_busy = True
            self.vm.status = "Lade E-Mail..."

            def fetch_thread():
                email = self.imap.fetch_email(uid, self.config.imap_inbox)
                GLib.idle_add(self._on_email_fetched, email)

            thread = threading.Thread(target=fetch_thread, daemon=True)
            thread.start()

    def _on_email_fetched(self, email):
        """Handle email fetch completion."""
        self.vm.is_busy = False

        if email:
            self.vm.set_current_email(email)
            self._update_details()
            self.vm.status = "Bereit"
        else:
            self._clear_details()
            self.vm.status = "E-Mail konnte nicht geladen werden"

    def _update_details(self):
        """Update details panel with current email."""
        email = self.vm.current_email
        if not email:
            self._clear_details()
            return

        # Update info
        self.from_row.set_text(email.sender[:60] or "-")
        self.subject_row.set_text(email.subject[:80] or "-")
        self.email_date_row.set_text(email.date.strftime("%d.%m.%Y %H:%M"))

        # Update attachments
        self._update_attachment_options()

        # Update suggestions
        self.date_row.set_text(self.vm.suggested_date)
        self.desc_row.set_text(self.vm.suggested_description)

        self.process_btn.set_sensitive(True)
        self.archive_btn.set_sensitive(True)

    def _update_attachment_options(self):
        """Update attachment radio buttons."""
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

        # PDF attachments
        for i, att in enumerate(email.attachments):
            if att.content_type == "application/pdf":
                radio = Gtk.CheckButton(label=f"{att.filename} [{att.size // 1024}KB]")
                if first_radio:
                    radio.set_group(first_radio)
                else:
                    first_radio = radio
                    radio.set_active(True)
                radio.attachment_index = i
                radio.connect("toggled", self._on_attachment_toggled)
                self.attachment_group.append(radio)

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

    def _on_attachment_toggled(self, button):
        """Handle attachment selection change."""
        if button.get_active():
            self.vm.selected_attachment_index = button.attachment_index

    def _clear_details(self):
        """Clear details panel."""
        self.from_row.set_text("")
        self.subject_row.set_text("")
        self.email_date_row.set_text("")

        while True:
            child = self.attachment_group.get_first_child()
            if child is None:
                break
            self.attachment_group.remove(child)

        self.date_row.set_text("")
        self.desc_row.set_text("")
        self.process_btn.set_sensitive(False)
        self.archive_btn.set_sensitive(False)

    def _on_archive_clicked(self, button):
        """Archive email without processing (skip irrelevant emails)."""
        email = self.vm.current_email
        if not email:
            return

        self.vm.is_busy = True
        self.vm.status = "Archiviere..."

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
                        GLib.idle_add(self._on_archive_success)
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

    def _on_archive_success(self):
        """Handle successful archive-only operation."""
        self.vm.is_busy = False
        self.vm.status = "E-Mail archiviert"
        self._clear_details()
        self._on_refresh_clicked(None)

    def _on_process_clicked(self, button):
        """Process and archive the selected email/attachment."""
        email = self.vm.current_email
        if not email:
            return

        # Validate input
        date_str = self.date_row.get_text().strip()
        desc = self.desc_row.get_text().strip()
        cat_idx = self.category_row.get_selected()

        if not date_str:
            self._show_error("Fehler", "Bitte Datum eingeben.")
            return

        try:
            date = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            self._show_error("Fehler", "Ungültiges Datum. Format: TT.MM.JJJJ")
            return

        if not desc:
            self._show_error("Fehler", "Bitte Beschreibung eingeben.")
            return

        cat_key = str(cat_idx + 1)
        category, is_cc = CATEGORIES[cat_key]
        attachment_idx = self.vm.selected_attachment_index

        # Process in background
        self.vm.is_busy = True
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

                # Archive
                self.archive.base_path = self.config.archive_path
                final_path = self.archive.archive(pdf_path, date, desc, category, is_cc)

                # Move email to archive folder
                if self.imap:
                    self.imap.move_email(
                        email.uid,
                        self.config.imap_inbox,
                        self.config.imap_archive,
                    )

                GLib.idle_add(self._on_process_success, final_path, is_cc)

            except Exception as e:
                GLib.idle_add(self._on_process_failed, str(e))

        thread = threading.Thread(target=process_thread, daemon=True)
        thread.start()

    def _on_process_success(self, final_path: Path, is_cc: bool):
        """Handle successful processing."""
        self.vm.is_busy = False

        msg = f"Gespeichert: {final_path.name}"
        if is_cc:
            msg += " (Ablage im Folgemonat)"
        self.vm.status = msg

        # Refresh list
        self._on_refresh_clicked(None)

        # Clear selection
        self._clear_details()

    def _on_process_failed(self, error: str):
        """Handle processing failure."""
        self.vm.is_busy = False
        self.vm.status = "Verarbeitung fehlgeschlagen"
        self._show_error("Fehler", error)

    def _show_error(self, title: str, message: str):
        """Show error dialog."""
        dialog = Adw.MessageDialog(
            transient_for=self.parent_window,
            heading=title,
            body=message,
        )
        dialog.add_response("ok", "OK")
        dialog.present()
