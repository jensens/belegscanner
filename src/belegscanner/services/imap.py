"""IMAP email service for fetching invoices."""

import email
import imaplib
import re
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
        """Disconnect from IMAP server."""
        if self._connection:
            try:
                self._connection.logout()
            except Exception:
                pass
            self._connection = None

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
            print(f"[DEBUG] Selecting folder: {folder}")
            status, data = self._connection.select(folder)
            print(f"[DEBUG] Select status: {status}, data: {data}")
            if status != "OK":
                return []

            # Search for all emails
            status, data = self._connection.search(None, "ALL")
            print(f"[DEBUG] Search status: {status}, data: {data}")
            if status != "OK" or not data[0]:
                return []

            email_ids = data[0].split()
            print(f"[DEBUG] Found {len(email_ids)} email IDs: {email_ids[:5]}...")
            if not email_ids:
                return []

            # Fetch envelope and bodystructure for each email
            summaries = []
            ids_str = b",".join(email_ids).decode()

            status, data = self._connection.fetch(
                ids_str, "(UID ENVELOPE BODYSTRUCTURE)"
            )
            print(f"[DEBUG] Fetch status: {status}, items: {len(data) if data else 0}")
            if data:
                print(f"[DEBUG] First 3 items types: {[type(x).__name__ for x in data[:3]]}")
                print(f"[DEBUG] First item: {data[0][:300] if isinstance(data[0], bytes) else data[0]}")
            if status != "OK":
                return []

            for i, item in enumerate(data):
                # Handle both tuple format (some servers) and bytes format (Gmail)
                if isinstance(item, tuple):
                    raw_data = item[0]
                elif isinstance(item, bytes) and b"ENVELOPE" in item:
                    raw_data = item
                else:
                    continue

                if i == 0:  # Show first item for debugging
                    print(f"[DEBUG] Parsing item: {raw_data[:200]}...")

                summary = self._parse_envelope(raw_data)
                if summary:
                    summaries.append(summary)
                elif i == 0:
                    print(f"[DEBUG] Failed to parse first item")

            print(f"[DEBUG] Parsed {len(summaries)} summaries")
            return summaries
        except Exception as e:
            print(f"[DEBUG] Exception in list_emails: {e}")
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
            subject_match = re.search(
                r'ENVELOPE \("[^"]*" "([^"]*)"', data_str
            )
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

            # Check for attachments (MULTIPART in bodystructure indicates possible attachments)
            has_attachments = "MULTIPART" in data_str.upper()

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
            print(f"[DEBUG] fetch_email status: {status}, data type: {type(data[0]) if data else 'None'}")
            if status != "OK" or not data or not data[0]:
                return None

            # Parse email
            if isinstance(data[0], tuple):
                raw_email = data[0][1]
            else:
                print(f"[DEBUG] fetch_email: data[0] is not tuple, it's {type(data[0])}")
                return None

            msg = email.message_from_bytes(raw_email)

            # Extract headers
            sender = self._decode_header(msg.get("From", ""))
            subject = self._decode_header(msg.get("Subject", ""))
            print(f"[DEBUG] fetch_email: sender={sender}, subject={subject[:50]}")
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
                    content_disposition = str(part.get("Content-Disposition", ""))

                    if "attachment" in content_disposition:
                        # This is an attachment
                        filename = part.get_filename()
                        if filename:
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
                # Single part message
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
