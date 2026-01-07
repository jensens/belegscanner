"""IMAP email service for fetching invoices."""

import email
import imaplib
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime


@dataclass
class EmailSummary:
    """Summary of an email for list display."""

    uid: int
    sender: str
    subject: str
    date: datetime
    has_attachments: bool


@dataclass
class EmailAttachment:
    """Email attachment data."""

    filename: str
    content_type: str
    size: int
    data: bytes


@dataclass
class EmailMessage:
    """Full email message with content and attachments."""

    uid: int
    sender: str
    subject: str
    date: datetime
    message_id: str
    body_text: str
    body_html: str | None
    attachments: list[EmailAttachment]


class ImapService:
    """IMAP service for fetching emails from a mailbox.

    Usage:
        service = ImapService("imap.example.com")
        if service.connect("user@example.com", "password"):
            emails = service.list_emails("INBOX")
            for summary in emails:
                full_email = service.fetch_email(summary.uid, "INBOX")
            service.disconnect()
    """

    def __init__(self, server: str, port: int = 993, use_ssl: bool = True):
        """Initialize IMAP service.

        Args:
            server: IMAP server hostname.
            port: IMAP port (default 993 for SSL).
            use_ssl: Whether to use SSL (default True).
        """
        self.server = server
        self.port = port
        self.use_ssl = use_ssl
        self._connection: imaplib.IMAP4_SSL | imaplib.IMAP4 | None = None
        self._prefetch_connection: imaplib.IMAP4_SSL | imaplib.IMAP4 | None = None
        self._prefetch_lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if connected to IMAP server."""
        return self._connection is not None

    def connect(self, username: str, password: str) -> tuple[bool, str]:
        """Connect and authenticate to IMAP server.

        Args:
            username: IMAP username/email.
            password: IMAP password.

        Returns:
            Tuple of (success, error_message). Error message is empty on success.
        """
        try:
            if self.use_ssl:
                self._connection = imaplib.IMAP4_SSL(self.server, self.port)
            else:
                self._connection = imaplib.IMAP4(self.server, self.port)

            self._connection.login(username, password)
            return True, ""
        except imaplib.IMAP4.error as e:
            self._connection = None
            return False, str(e)
        except Exception as e:
            self._connection = None
            return False, str(e)

    def disconnect(self) -> None:
        """Disconnect from IMAP server (both main and prefetch connections)."""
        if self._connection:
            try:
                self._connection.logout()
            except Exception:
                pass
            self._connection = None

        if self._prefetch_connection:
            try:
                self._prefetch_connection.logout()
            except Exception:
                pass
            self._prefetch_connection = None

    def connect_prefetch(self, username: str, password: str) -> bool:
        """Establish a separate connection for prefetching.

        This connection is used for parallel email fetching while the
        main connection handles other operations.

        Args:
            username: IMAP username/email.
            password: IMAP password.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            if self.use_ssl:
                self._prefetch_connection = imaplib.IMAP4_SSL(self.server, self.port)
            else:
                self._prefetch_connection = imaplib.IMAP4(self.server, self.port)

            self._prefetch_connection.login(username, password)
            return True
        except Exception:
            self._prefetch_connection = None
            return False

    def fetch_email_prefetch(self, uid: int, folder: str) -> EmailMessage | None:
        """Fetch email using the prefetch connection.

        Thread-safe method for fetching emails in parallel with main operations.

        Args:
            uid: Email UID.
            folder: Folder containing the email.

        Returns:
            EmailMessage or None if not found or prefetch not connected.
        """
        if not self._prefetch_connection:
            return None

        with self._prefetch_lock:
            try:
                status, data = self._prefetch_connection.select(folder)
                if status != "OK":
                    return None

                status, data = self._prefetch_connection.uid("FETCH", str(uid), "(RFC822)")
                if status != "OK" or not data or not data[0]:
                    return None

                # Parse email (reuse existing parsing logic)
                if isinstance(data[0], tuple):
                    raw_email = data[0][1]
                else:
                    return None

                return self._parse_email(uid, raw_email)
            except Exception:
                return None

    def _parse_email(self, uid: int, raw_email: bytes) -> EmailMessage | None:
        """Parse raw email bytes into EmailMessage.

        Args:
            uid: Email UID.
            raw_email: Raw RFC822 email bytes.

        Returns:
            EmailMessage or None if parsing fails.
        """
        try:
            msg = email.message_from_bytes(raw_email)

            # Extract headers
            sender = self._decode_header(msg.get("From", ""))
            subject = self._decode_header(msg.get("Subject", ""))
            message_id = msg.get("Message-ID", "")

            # Parse date
            date_str = msg.get("Date", "")
            try:
                date = parsedate_to_datetime(date_str)
            except Exception:
                date = datetime.now()

            # Extract body and attachments
            body_text = ""
            body_html = None
            attachments = []

            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", "")).lower()
                    filename = part.get_filename()

                    is_attachment = "attachment" in content_disposition

                    if not is_attachment and filename:
                        filename_lower = filename.lower()
                        attachment_extensions = (".pdf", ".zip", ".doc", ".docx", ".xls", ".xlsx")
                        is_attachment = content_type in (
                            "application/pdf",
                            "application/octet-stream",
                        ) or filename_lower.endswith(attachment_extensions)

                    if is_attachment and filename:
                        filename = self._decode_header(filename)
                        payload = part.get_payload(decode=True)
                        if payload:
                            attachments.append(
                                EmailAttachment(
                                    filename=filename,
                                    content_type=content_type,
                                    size=len(payload),
                                    data=payload,
                                )
                            )
                    elif content_type == "text/plain" and not body_text:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body_text = payload.decode(charset, errors="replace")
                    elif content_type == "text/html" and not body_html:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body_html = payload.decode(charset, errors="replace")
            else:
                content_type = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    if content_type == "text/html":
                        body_html = payload.decode(charset, errors="replace")
                    else:
                        body_text = payload.decode(charset, errors="replace")

            return EmailMessage(
                uid=uid,
                sender=sender,
                subject=subject,
                date=date,
                message_id=message_id,
                body_text=body_text,
                body_html=body_html,
                attachments=attachments,
            )
        except Exception:
            return None

    def list_folders(self) -> list[str]:
        """List all mailbox folders.

        Returns:
            List of folder names.
        """
        if not self._connection:
            return []

        try:
            status, data = self._connection.list()
            if status != "OK":
                return []

            folders = []
            for item in data:
                if item:
                    # Parse folder name from response like: (\\HasNoChildren) "/" "FolderName"
                    match = re.search(rb'"([^"]+)"$', item)
                    if match:
                        folder_name = match.group(1).decode("utf-8")
                        folders.append(folder_name)
            return folders
        except Exception:
            return []

    def list_emails(self, folder: str) -> list[EmailSummary]:
        """List emails in a folder.

        Args:
            folder: Folder name to list emails from.

        Returns:
            List of EmailSummary objects.
        """
        if not self._connection:
            return []

        try:
            status, data = self._connection.select(folder)
            if status != "OK":
                return []

            # Search for all emails
            status, data = self._connection.search(None, "ALL")
            if status != "OK" or not data[0]:
                return []

            email_ids = data[0].split()
            if not email_ids:
                return []

            # Fetch envelope and bodystructure for each email
            summaries = []
            ids_str = b",".join(email_ids).decode()

            status, data = self._connection.fetch(ids_str, "(UID ENVELOPE BODYSTRUCTURE)")
            if status != "OK":
                return []

            for item in data:
                # Handle both tuple format (some servers) and bytes format (Gmail)
                if isinstance(item, tuple):
                    raw_data = item[0]
                elif isinstance(item, bytes) and b"ENVELOPE" in item:
                    raw_data = item
                else:
                    continue

                summary = self._parse_envelope(raw_data)
                if summary:
                    summaries.append(summary)

            return summaries
        except Exception:
            return []

    def _parse_envelope(self, data: bytes) -> EmailSummary | None:
        """Parse ENVELOPE response into EmailSummary.

        Args:
            data: Raw ENVELOPE response bytes.

        Returns:
            EmailSummary or None if parsing fails.
        """
        try:
            data_str = data.decode("utf-8", errors="replace")

            # Extract UID
            uid_match = re.search(r"UID (\d+)", data_str)
            uid = int(uid_match.group(1)) if uid_match else 0

            # Extract date string
            date_match = re.search(r'ENVELOPE \("([^"]*)"', data_str)
            date_str = date_match.group(1) if date_match else ""

            # Parse date
            try:
                date = parsedate_to_datetime(date_str)
            except Exception:
                date = datetime.now()

            # Extract subject (second quoted string after date)
            subject_match = re.search(r'ENVELOPE \("[^"]*" "([^"]*)"', data_str)
            subject = subject_match.group(1) if subject_match else "(Kein Betreff)"

            # Extract sender (from the FROM field)
            # Format: ((name route mailbox host))
            from_match = re.search(
                r'\(\((?:NIL|"[^"]*") (?:NIL|"[^"]*") "([^"]*)" "([^"]*)"\)\)',
                data_str,
            )
            if from_match:
                sender = f"{from_match.group(1)}@{from_match.group(2)}"
            else:
                sender = "(Unbekannt)"

            # Check for attachments in BODYSTRUCTURE
            # Look for multiple patterns since servers format disposition differently:
            # - ("ATTACHMENT" ...) - quoted uppercase
            # - (attachment ...) - unquoted lowercase
            # - ("FILENAME" ...) or ("NAME" "xxx.pdf") with common attachment extensions
            data_upper = data_str.upper()
            has_attachments = (
                '"ATTACHMENT"' in data_upper
                or "(ATTACHMENT " in data_upper
                or re.search(r'\("(?:FILE)?NAME"\s+"[^"]+\.(?:PDF|ZIP|DOC|XLS)', data_upper)
                is not None
            )

            return EmailSummary(
                uid=uid,
                sender=sender,
                subject=subject,
                date=date,
                has_attachments=has_attachments,
            )
        except Exception:
            return None

    def fetch_email(self, uid: int, folder: str) -> EmailMessage | None:
        """Fetch full email by UID.

        Args:
            uid: Email UID.
            folder: Folder containing the email.

        Returns:
            EmailMessage or None if not found.
        """
        if not self._connection:
            return None

        try:
            status, data = self._connection.select(folder)
            if status != "OK":
                return None

            status, data = self._connection.uid("FETCH", str(uid), "(RFC822)")
            if status != "OK" or not data or not data[0]:
                return None

            # Parse email
            if isinstance(data[0], tuple):
                raw_email = data[0][1]
            else:
                return None

            return self._parse_email(uid, raw_email)
        except Exception:
            return None

    def _decode_header(self, value: str) -> str:
        """Decode email header value.

        Args:
            value: Raw header value.

        Returns:
            Decoded string.
        """
        if not value:
            return ""

        try:
            decoded_parts = decode_header(value)
            result = []
            for data, charset in decoded_parts:
                if isinstance(data, bytes):
                    result.append(data.decode(charset or "utf-8", errors="replace"))
                else:
                    result.append(data)
            return "".join(result)
        except Exception:
            return value

    def move_email(self, uid: int, source_folder: str, target_folder: str) -> bool:
        """Move email to another folder.

        Args:
            uid: Email UID.
            source_folder: Source folder name.
            target_folder: Target folder name.

        Returns:
            True if move successful, False otherwise.
        """
        if not self._connection:
            return False

        try:
            # Select source folder
            status, _ = self._connection.select(source_folder)
            if status != "OK":
                return False

            # Copy to target folder
            status, _ = self._connection.uid("COPY", str(uid), target_folder)
            if status != "OK":
                return False

            # Mark as deleted in source
            status, _ = self._connection.uid("STORE", str(uid), "+FLAGS", "\\Deleted")
            if status != "OK":
                return False

            # Expunge to actually delete
            self._connection.expunge()

            return True
        except Exception:
            return False
