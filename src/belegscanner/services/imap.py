"""IMAP email service for fetching invoices."""

import email
import threading
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime

from imapclient import IMAPClient

from belegscanner.log import get_logger
from belegscanner.services.text import sanitize_filename

logger = get_logger(__name__)

SOCKET_TIMEOUT = 15  # Sekunden; verhindert Minuten-Haenger bei toter Verbindung


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

    Instanzen sind nicht thread-safe; ab Phase 3 ist der EmailWorker der
    einzige Nutzer.

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
        self._connection: IMAPClient | None = None
        self._prefetch_connection: IMAPClient | None = None
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
            self._connection = IMAPClient(
                self.server, port=self.port, ssl=self.use_ssl, timeout=SOCKET_TIMEOUT
            )
            self._connection.login(username, password)
            return True, ""
        except Exception as e:
            logger.warning("IMAP-Verbindung fehlgeschlagen: %s", e)
            self._connection = None
            return False, str(e)

    def disconnect(self) -> None:
        """Disconnect from IMAP server (both main and prefetch connections)."""
        for attr in ("_connection", "_prefetch_connection"):
            conn = getattr(self, attr)
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    logger.debug("Fehler beim IMAP-Logout (ignoriert)")
                setattr(self, attr, None)

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
            self._prefetch_connection = IMAPClient(
                self.server, port=self.port, ssl=self.use_ssl, timeout=SOCKET_TIMEOUT
            )
            self._prefetch_connection.login(username, password)
            return True
        except Exception:
            logger.warning("Prefetch-Verbindung fehlgeschlagen")
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
                self._prefetch_connection.select_folder(folder)
                data = self._prefetch_connection.fetch([uid], [b"RFC822"]).get(uid)
                raw = data.get(b"RFC822") if data else None
                if not raw:
                    return None
                return self._parse_email(uid, raw)
            except Exception:
                logger.debug("Prefetch-Fetch fehlgeschlagen fuer UID %d", uid)
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
            sender = self._decode_mime_words(msg.get("From", ""))
            subject = self._decode_mime_words(msg.get("Subject", ""))
            message_id = msg.get("Message-ID", "")

            # Parse date
            date_str = msg.get("Date", "")
            try:
                date = parsedate_to_datetime(date_str)
            except Exception:
                logger.debug("Datum konnte nicht geparst werden: %s", date_str)
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
                        filename = sanitize_filename(self._decode_mime_words(filename))
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
            logger.debug("E-Mail-Parsing fehlgeschlagen fuer UID %d", uid)
            return None

    def list_folders(self) -> list[str]:
        """List all mailbox folders.

        Returns:
            List of folder names.
        """
        if not self._connection:
            return []
        try:
            return [
                name if isinstance(name, str) else name.decode("utf-8", errors="replace")
                for _flags, _delim, name in self._connection.list_folders()
            ]
        except Exception:
            logger.warning("Ordnerliste konnte nicht abgerufen werden", exc_info=True)
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
            self._connection.select_folder(folder)
            uids = self._connection.search("ALL")
            if not uids:
                return []
            summaries = []
            response = self._connection.fetch(uids, [b"ENVELOPE", b"BODYSTRUCTURE"])
            for uid, data in response.items():
                envelope = data.get(b"ENVELOPE")
                if envelope is None:
                    continue
                summaries.append(
                    EmailSummary(
                        uid=uid,
                        sender=self._format_address(envelope.from_),
                        subject=self._decode_mime_words(envelope.subject) or "(Kein Betreff)",
                        date=envelope.date or datetime.now(),
                        has_attachments=self._structure_has_attachments(data.get(b"BODYSTRUCTURE")),
                    )
                )
            return summaries
        except Exception:
            logger.warning("E-Mail-Liste konnte nicht abgerufen werden", exc_info=True)
            return []

    @staticmethod
    def _decode_mime_words(value: bytes | str | None) -> str:
        """RFC-2047-dekodierter Header-Wert (z. B. '=?utf-8?q?...?=')."""
        if not value:
            return ""
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        try:
            parts = decode_header(value)
        except Exception:
            logger.debug("Header-Dekodierung fehlgeschlagen: %s", value)
            return value
        return "".join(
            part.decode(charset or "utf-8", errors="replace") if isinstance(part, bytes) else part
            for part, charset in parts
        )

    def _format_address(self, addresses) -> str:
        """Erste Adresse als 'Name <mailbox@host>' formatieren."""
        if not addresses:
            return "(Unbekannt)"
        addr = addresses[0]
        mailbox = (addr.mailbox or b"").decode("utf-8", errors="replace")
        host = (addr.host or b"").decode("utf-8", errors="replace")
        name = self._decode_mime_words(addr.name)
        email_str = f"{mailbox}@{host}" if mailbox and host else ""
        if name and email_str:
            return f"{name} <{email_str}>"
        return email_str or name or "(Unbekannt)"

    _ATTACHMENT_EXTENSIONS = (b".pdf", b".zip", b".doc", b".docx", b".xls", b".xlsx")

    def _structure_has_attachments(self, structure) -> bool:
        """Heuristik auf der geparsten BODYSTRUCTURE (imapclient BodyData)."""
        if structure is None:
            return False
        try:
            return self._part_has_attachment(structure)
        except (IndexError, TypeError, AttributeError):
            logger.debug("BODYSTRUCTURE nicht auswertbar", exc_info=True)
            return False

    def _part_has_attachment(self, part) -> bool:
        if getattr(part, "is_multipart", False):
            return any(self._part_has_attachment(sub) for sub in part[0])
        for item in part:
            if not isinstance(item, tuple):
                continue
            flat = [x for x in item if isinstance(x, bytes)]
            if flat and flat[0].lower() == b"attachment":
                return True
            for i, token in enumerate(flat):
                if token.lower() in (b"name", b"filename") and i + 1 < len(flat):
                    if flat[i + 1].lower().endswith(self._ATTACHMENT_EXTENSIONS):
                        return True
        return False

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
            self._connection.select_folder(folder)
            data = self._connection.fetch([uid], [b"RFC822"]).get(uid)
            raw = data.get(b"RFC822") if data else None
            if not raw:
                return None
            return self._parse_email(uid, raw)
        except Exception:
            logger.warning("E-Mail-Fetch fehlgeschlagen fuer UID %d", uid, exc_info=True)
            return None

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
            self._connection.select_folder(source_folder)
            if self._connection.has_capability("MOVE"):
                self._connection.move([uid], target_folder)
            else:
                self._connection.copy([uid], target_folder)
                self._connection.delete_messages([uid])
                if self._connection.has_capability("UIDPLUS"):
                    self._connection.expunge([uid])  # UID EXPUNGE: nur diese Mail
                else:
                    self._connection.expunge()
            return True
        except Exception:
            logger.warning("E-Mail-Verschiebung fehlgeschlagen fuer UID %d", uid)
            return False
