"""ViewModel for Email processing workflow.

Uses GObject properties and signals for reactive UI binding.
"""

import re

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GObject

from belegscanner.services.imap import EmailMessage, EmailSummary


class EmailViewModel(GObject.Object):
    """ViewModel managing email processing workflow state.

    Properties:
        status: Status message for display
        is_busy: Whether an operation is in progress
        is_connected: Whether connected to IMAP server
        suggested_date: Extracted date suggestion
        suggested_description: Extracted description suggestion
        selected_attachment_index: Selected attachment (-1 = email as PDF)

    Usage:
        vm = EmailViewModel()
        vm.connect("notify::status", on_status_changed)
        vm.set_emails(email_list)
        vm.select_email(uid)
    """

    __gtype_name__ = "EmailViewModel"

    # GObject properties
    status = GObject.Property(type=str, default="Nicht verbunden")
    is_busy = GObject.Property(type=bool, default=False, nick="is-busy")
    is_connected = GObject.Property(type=bool, default=False, nick="is-connected")
    suggested_date = GObject.Property(type=str, default="", nick="suggested-date")
    suggested_description = GObject.Property(
        type=str, default="", nick="suggested-description"
    )
    selected_attachment_index = GObject.Property(
        type=int, default=-1, nick="selected-attachment-index"
    )

    def __init__(self):
        """Initialize ViewModel with empty state."""
        super().__init__()
        self._emails: list[EmailSummary] = []
        self._selected_email: EmailSummary | None = None
        self._current_email: EmailMessage | None = None

    @property
    def emails(self) -> list[EmailSummary]:
        """Get list of email summaries."""
        return self._emails.copy()

    @property
    def selected_email(self) -> EmailSummary | None:
        """Get currently selected email summary."""
        return self._selected_email

    @property
    def current_email(self) -> EmailMessage | None:
        """Get full current email message (after fetch)."""
        return self._current_email

    def set_emails(self, emails: list[EmailSummary]) -> None:
        """Set the list of emails, sorted by date (newest first).

        Args:
            emails: List of EmailSummary objects.
        """
        # Sort by date, handling mixed timezone-aware and naive datetimes
        def sort_key(e):
            dt = e.date
            # Convert to naive datetime for comparison
            if dt.tzinfo is not None:
                return dt.replace(tzinfo=None)
            return dt

        self._emails = sorted(emails, key=sort_key, reverse=True)
        self._selected_email = None
        self._current_email = None

    def select_email(self, uid: int) -> None:
        """Select an email by UID.

        Args:
            uid: Email UID to select.
        """
        for email in self._emails:
            if email.uid == uid:
                self._selected_email = email
                return
        self._selected_email = None

    def set_current_email(self, email: EmailMessage | None) -> None:
        """Set the current full email message.

        Also extracts suggested date and description.

        Args:
            email: Full EmailMessage or None.
        """
        self._current_email = email

        if email:
            # Extract date suggestion from email date
            self.suggested_date = email.date.strftime("%d.%m.%Y")

            # Extract description from sender
            self.suggested_description = self._extract_description(email.sender)

            # Reset attachment selection
            self.selected_attachment_index = 0 if email.attachments else -1
        else:
            self.suggested_date = ""
            self.suggested_description = ""
            self.selected_attachment_index = -1

    def _extract_description(self, sender: str) -> str:
        """Extract description from sender address.

        Uses domain name (e.g., amazon.de -> amazon) as it's usually
        more meaningful than the local part (e.g., rechnung).

        Args:
            sender: Email sender address.

        Returns:
            Cleaned description suitable for filename.
        """
        if not sender:
            return ""

        # Extract domain from email address
        match = re.search(r"@([^>]+)", sender)
        if match:
            domain = match.group(1)
            # Remove TLD (.de, .com, etc.)
            domain = domain.split(".")[0]
        else:
            # Fallback to full sender
            domain = sender

        # Clean up
        desc = domain.lower()
        desc = re.sub(r"[^a-z0-9äöüß]+", "_", desc)
        desc = desc.strip("_")[:30]

        return desc

    def clear(self) -> None:
        """Clear all state for fresh start."""
        self._emails = []
        self._selected_email = None
        self._current_email = None
        self.suggested_date = ""
        self.suggested_description = ""
        self.selected_attachment_index = -1
