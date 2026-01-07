"""ViewModel for Email processing workflow.

Uses GObject properties and signals for reactive UI binding.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GObject

from belegscanner.services.email_cache import EmailCache
from belegscanner.services.imap import EmailMessage, EmailSummary
from belegscanner.services.ocr import OcrService
from belegscanner.services.vendor import VendorExtractor


class EmailViewModel(GObject.Object):
    """ViewModel managing email processing workflow state.

    Properties:
        status: Status message for display
        is_busy: Whether an operation is in progress
        is_connected: Whether connected to IMAP server
        suggested_date: Extracted date suggestion
        suggested_description: Extracted description suggestion
        suggested_currency: Currency code (default: EUR)
        suggested_amount: Extracted amount suggestion
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
    suggested_currency = GObject.Property(type=str, default="EUR", nick="suggested-currency")
    suggested_amount = GObject.Property(type=str, default="", nick="suggested-amount")
    selected_attachment_index = GObject.Property(
        type=int, default=-1, nick="selected-attachment-index"
    )
    ki_extraction_running = GObject.Property(
        type=bool, default=False, nick="ki-extraction-running"
    )

    def __init__(self):
        """Initialize ViewModel with empty state."""
        super().__init__()
        self._emails: list[EmailSummary] = []
        self._selected_email: EmailSummary | None = None
        self._current_email: EmailMessage | None = None
        self._filter_query: str = ""
        self._current_folder: str = ""
        self._cache = EmailCache(max_size=20)
        self._ocr_service = OcrService()
        self._vendor_extractor = VendorExtractor()
        # Fetch request tracking to prevent race conditions
        self._fetch_request_id: int = 0
        self._current_fetch_request: int | None = None

    @property
    def emails(self) -> list[EmailSummary]:
        """Get list of email summaries."""
        return self._emails.copy()

    @property
    def filtered_emails(self) -> list[EmailSummary]:
        """Get filtered list of email summaries.

        If no filter is set, returns all emails.
        Filter matches sender or subject (case-insensitive).
        """
        if not self._filter_query:
            return self._emails.copy()

        query = self._filter_query.lower()
        return [
            email
            for email in self._emails
            if query in email.sender.lower() or query in email.subject.lower()
        ]

    def set_filter(self, query: str) -> None:
        """Set filter query for email list.

        Args:
            query: Search string to filter by (matches sender/subject).
        """
        self._filter_query = query.strip()

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

            # Extract vendor description from sender/subject
            self.suggested_description = (
                self._vendor_extractor.extract(
                    sender=email.sender,
                    subject=email.subject,
                )
                or ""
            )

            # Extract amount from email body text (or HTML if text is empty)
            text_for_extraction = email.body_text or self._strip_html(email.body_html)
            amount_result = self._ocr_service.extract_amount(text_for_extraction)
            if amount_result:
                self.suggested_currency, self.suggested_amount = amount_result
            else:
                self.suggested_currency = "EUR"
                self.suggested_amount = ""

            # Reset attachment selection
            self.selected_attachment_index = 0 if email.attachments else -1
        else:
            self.suggested_date = ""
            self.suggested_description = ""
            self.suggested_currency = "EUR"
            self.suggested_amount = ""
            self.selected_attachment_index = -1

    def clear(self) -> None:
        """Clear all state for fresh start."""
        self._emails = []
        self._selected_email = None
        self._current_email = None
        self._filter_query = ""
        self.suggested_date = ""
        self.suggested_description = ""
        self.suggested_currency = "EUR"
        self.suggested_amount = ""
        self.selected_attachment_index = -1
        self.ki_extraction_running = False
        self._cache.clear()
        # Reset fetch request tracking - invalidates any pending requests
        self._current_fetch_request = None

    def set_current_folder(self, folder: str) -> None:
        """Set current IMAP folder for cache operations.

        Args:
            folder: IMAP folder name (e.g., "INBOX").
        """
        self._current_folder = folder

    def get_cached_email(self, uid: int) -> EmailMessage | None:
        """Get email from cache if available.

        Args:
            uid: Email UID.

        Returns:
            EmailMessage if cached, None otherwise.
        """
        return self._cache.get(self._current_folder, uid)

    def cache_email(self, email: EmailMessage) -> None:
        """Store email in cache.

        Args:
            email: EmailMessage to cache.
        """
        self._cache.put(self._current_folder, email.uid, email)

    def invalidate_cached_email(self, uid: int) -> None:
        """Remove email from cache (e.g., after moving).

        Args:
            uid: Email UID to remove.
        """
        self._cache.remove(self._current_folder, uid)

    def start_fetch_request(self, uid: int) -> int:
        """Start a new fetch request and return its unique ID.

        Each call increments the request counter. Only the most recent
        request ID is considered valid, preventing race conditions when
        the user rapidly switches between emails.

        Args:
            uid: Email UID being fetched (for future tracking if needed).

        Returns:
            Unique request ID to pass to complete_fetch_request.
        """
        self._fetch_request_id += 1
        self._current_fetch_request = self._fetch_request_id
        return self._fetch_request_id

    def complete_fetch_request(self, request_id: int, email: EmailMessage) -> bool:
        """Complete a fetch request if it's still valid.

        A request is valid only if its ID matches the most recent request.
        If valid, sets the current email and caches it.

        Args:
            request_id: ID returned by start_fetch_request.
            email: The fetched EmailMessage.

        Returns:
            True if request was accepted, False if stale/rejected.
        """
        if request_id != self._current_fetch_request:
            return False
        self.cache_email(email)
        self.set_current_email(email)
        return True

    def cancel_fetch_request(self) -> None:
        """Cancel any pending fetch request.

        Makes the current request ID invalid so pending callbacks
        will be rejected.
        """
        self._current_fetch_request = None

    def get_next_email_uid(self, current_index: int) -> int | None:
        """Get UID of next email in filtered list for prefetching.

        Args:
            current_index: Current email index in filtered list.

        Returns:
            UID of next email, or None if at end of list.
        """
        filtered = self.filtered_emails
        next_index = current_index + 1
        if next_index < len(filtered):
            return filtered[next_index].uid
        return None

    def _strip_html(self, html: str | None) -> str:
        """Strip HTML tags and return plain text.

        Simple regex-based HTML stripping for extraction purposes.

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
