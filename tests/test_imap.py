"""Tests for ImapService."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from belegscanner.services.imap import (
    EmailAttachment,
    EmailMessage,
    EmailSummary,
    ImapService,
)


class TestImapServiceConnection:
    """Test IMAP connection handling."""

    def test_init_stores_server_info(self):
        """ImapService stores server configuration."""
        service = ImapService("imap.example.com", port=993, use_ssl=True)

        assert service.server == "imap.example.com"
        assert service.port == 993
        assert service.use_ssl is True

    def test_init_uses_default_port(self):
        """ImapService uses port 993 by default."""
        service = ImapService("imap.example.com")

        assert service.port == 993

    def test_is_connected_false_initially(self):
        """is_connected is False before connecting."""
        service = ImapService("imap.example.com")

        assert service.is_connected is False

    def test_connect_establishes_connection(self):
        """connect() establishes IMAP connection."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            success, error = service.connect("user@example.com", "password123")

            assert success is True
            assert error == ""
            assert service.is_connected is True
            mock_imap.assert_called_once_with("imap.example.com", 993)
            mock_conn.login.assert_called_once_with("user@example.com", "password123")

    def test_connect_returns_false_on_auth_failure(self):
        """connect() returns False with error message when authentication fails."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.side_effect = Exception("Authentication failed")
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            success, error = service.connect("user@example.com", "wrongpassword")

            assert success is False
            assert "Authentication failed" in error
            assert service.is_connected is False

    def test_connect_returns_false_on_connection_failure(self):
        """connect() returns False with error when server is unreachable."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_imap.side_effect = Exception("Connection refused")

            service = ImapService("imap.example.com")
            success, error = service.connect("user@example.com", "password123")

            assert success is False
            assert "Connection refused" in error
            assert service.is_connected is False

    def test_disconnect_closes_connection(self):
        """disconnect() closes IMAP connection."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            service.disconnect()

            assert service.is_connected is False
            mock_conn.logout.assert_called_once()

    def test_disconnect_handles_already_disconnected(self):
        """disconnect() handles case when not connected."""
        service = ImapService("imap.example.com")

        # Should not raise
        service.disconnect()

        assert service.is_connected is False


class TestImapServiceListFolders:
    """Test folder listing."""

    def test_list_folders_returns_folder_names(self):
        """list_folders() returns list of folder names."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.list.return_value = (
                "OK",
                [
                    b'(\\HasNoChildren) "/" "INBOX"',
                    b'(\\HasNoChildren) "/" "Rechnungseingang"',
                    b'(\\HasChildren) "/" "Rechnungseingang/archiviert"',
                ],
            )
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            folders = service.list_folders()

            assert "INBOX" in folders
            assert "Rechnungseingang" in folders
            assert "Rechnungseingang/archiviert" in folders

    def test_list_folders_returns_empty_when_not_connected(self):
        """list_folders() returns empty list when not connected."""
        service = ImapService("imap.example.com")

        folders = service.list_folders()

        assert folders == []


class TestImapServiceListEmails:
    """Test email listing."""

    def test_list_emails_returns_email_summaries(self):
        """list_emails() returns list of EmailSummary objects."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"5"])
            mock_conn.search.return_value = ("OK", [b"1 2"])
            # IMAP fetch returns list of tuples: [(b'header info', b'body'), b')']
            mock_conn.fetch.return_value = (
                "OK",
                [
                    (
                        b'1 (UID 101 ENVELOPE ("15-Nov-2024 10:30:00 +0100" '
                        b'"Ihre Rechnung #12345" '
                        b'((NIL NIL "rechnung" "amazon.de")) '
                        b'NIL NIL NIL NIL NIL NIL NIL) '
                        b'BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 100 10))',
                    ),
                    b")",
                    (
                        b'2 (UID 102 ENVELOPE ("01-Nov-2024 09:00:00 +0100" '
                        b'"Monatsrechnung November" '
                        b'((NIL NIL "service" "telekom.de")) '
                        b'NIL NIL NIL NIL NIL NIL NIL) '
                        b'BODYSTRUCTURE ("MULTIPART" "MIXED"))',
                    ),
                    b")",
                ],
            )
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            emails = service.list_emails("Rechnungseingang")

            assert len(emails) == 2
            assert isinstance(emails[0], EmailSummary)
            assert emails[0].uid == 101
            assert "amazon" in emails[0].sender.lower()

    def test_list_emails_returns_empty_when_folder_empty(self):
        """list_emails() returns empty list for empty folder."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"0"])
            mock_conn.search.return_value = ("OK", [b""])
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            emails = service.list_emails("Rechnungseingang")

            assert emails == []

    def test_list_emails_returns_empty_when_not_connected(self):
        """list_emails() returns empty list when not connected."""
        service = ImapService("imap.example.com")

        emails = service.list_emails("Rechnungseingang")

        assert emails == []


class TestImapServiceFetchEmail:
    """Test full email fetching."""

    def test_fetch_email_returns_full_message(self):
        """fetch_email() returns EmailMessage with all details."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])

            # Create a proper email message
            email_bytes = (
                b"From: rechnung@amazon.de\r\n"
                b"To: user@example.com\r\n"
                b"Subject: Ihre Rechnung #12345\r\n"
                b"Date: Fri, 15 Nov 2024 10:30:00 +0100\r\n"
                b"Message-ID: <abc123@amazon.de>\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"\r\n"
                b"Sehr geehrter Kunde,\r\n"
                b"anbei Ihre Rechnung.\r\n"
            )
            mock_conn.uid.return_value = ("OK", [(b"1 (RFC822 ", email_bytes, b")")])
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            email = service.fetch_email(101, "Rechnungseingang")

            assert email is not None
            assert isinstance(email, EmailMessage)
            assert email.uid == 101
            assert "amazon" in email.sender.lower()
            assert "12345" in email.subject
            assert "<abc123@amazon.de>" in email.message_id
            assert "Sehr geehrter Kunde" in email.body_text

    def test_fetch_email_extracts_pdf_attachments(self):
        """fetch_email() extracts PDF attachments."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])

            # Create multipart email with PDF attachment
            email_bytes = (
                b"From: rechnung@amazon.de\r\n"
                b"To: user@example.com\r\n"
                b"Subject: Ihre Rechnung\r\n"
                b"Date: Fri, 15 Nov 2024 10:30:00 +0100\r\n"
                b"Message-ID: <abc123@amazon.de>\r\n"
                b"MIME-Version: 1.0\r\n"
                b'Content-Type: multipart/mixed; boundary="boundary123"\r\n'
                b"\r\n"
                b"--boundary123\r\n"
                b"Content-Type: text/plain\r\n"
                b"\r\n"
                b"Siehe Anhang.\r\n"
                b"--boundary123\r\n"
                b"Content-Type: application/pdf\r\n"
                b'Content-Disposition: attachment; filename="Rechnung.pdf"\r\n'
                b"Content-Transfer-Encoding: base64\r\n"
                b"\r\n"
                b"JVBERi0xLjQK\r\n"
                b"--boundary123--\r\n"
            )
            mock_conn.uid.return_value = ("OK", [(b"1 (RFC822 ", email_bytes, b")")])
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            email = service.fetch_email(101, "Rechnungseingang")

            assert email is not None
            assert len(email.attachments) == 1
            assert email.attachments[0].filename == "Rechnung.pdf"
            assert email.attachments[0].content_type == "application/pdf"
            assert len(email.attachments[0].data) > 0

    def test_fetch_email_extracts_octet_stream_attachment(self):
        """fetch_email() extracts application/octet-stream with PDF filename."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])
            # Email with application/octet-stream attachment (like domaindiscount24)
            email_bytes = (
                b"From: support@domaindiscount24.com\r\n"
                b"Subject: Ihre Rechnung\r\n"
                b"Date: 23 Nov 2025 13:38:00 +0100\r\n"
                b"Message-ID: <test@example.com>\r\n"
                b"Content-Type: multipart/mixed; boundary=\"boundary123\"\r\n"
                b"\r\n"
                b"--boundary123\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                b"\r\n"
                b"<html><body>Invoice</body></html>\r\n"
                b"--boundary123\r\n"
                b"Content-Type: application/octet-stream\r\n"
                b'Content-Disposition: attachment; filename="2025172897.pdf"\r\n'
                b"\r\n"
                b"JVBERi0xLjQK\r\n"
                b"--boundary123--\r\n"
            )
            mock_conn.uid.return_value = ("OK", [(b"1 (RFC822 ", email_bytes, b")")])
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            email = service.fetch_email(101, "INBOX")

            assert email is not None
            assert len(email.attachments) == 1
            assert email.attachments[0].filename == "2025172897.pdf"
            assert email.attachments[0].content_type == "application/octet-stream"

    def test_fetch_email_returns_none_when_not_found(self):
        """fetch_email() returns None when email not found."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])
            mock_conn.uid.return_value = ("OK", [None])
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            email = service.fetch_email(999, "Rechnungseingang")

            assert email is None

    def test_fetch_email_returns_none_when_not_connected(self):
        """fetch_email() returns None when not connected."""
        service = ImapService("imap.example.com")

        email = service.fetch_email(101, "Rechnungseingang")

        assert email is None


class TestImapServiceMoveEmail:
    """Test email moving."""

    def test_move_email_copies_and_deletes(self):
        """move_email() copies to target and deletes from source."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])
            mock_conn.uid.return_value = ("OK", [])
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            result = service.move_email(
                101, "Rechnungseingang", "Rechnungseingang/archiviert"
            )

            assert result is True
            # Verify COPY was called
            copy_calls = [
                c for c in mock_conn.uid.call_args_list if c[0][0] == "COPY"
            ]
            assert len(copy_calls) == 1
            # Verify STORE (delete flag) was called
            store_calls = [
                c for c in mock_conn.uid.call_args_list if c[0][0] == "STORE"
            ]
            assert len(store_calls) == 1

    def test_move_email_returns_false_on_failure(self):
        """move_email() returns False when operation fails."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])
            mock_conn.uid.side_effect = Exception("COPY failed")
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            result = service.move_email(
                101, "Rechnungseingang", "Rechnungseingang/archiviert"
            )

            assert result is False

    def test_move_email_returns_false_when_not_connected(self):
        """move_email() returns False when not connected."""
        service = ImapService("imap.example.com")

        result = service.move_email(
            101, "Rechnungseingang", "Rechnungseingang/archiviert"
        )

        assert result is False


class TestHasAttachmentsDetection:
    """Test attachment detection in BODYSTRUCTURE parsing."""

    def test_has_attachments_true_with_pdf_attachment(self):
        """has_attachments is True when BODYSTRUCTURE contains attachment disposition."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])
            mock_conn.search.return_value = ("OK", [b"1"])
            # BODYSTRUCTURE with attachment disposition
            mock_conn.fetch.return_value = (
                "OK",
                [
                    (
                        b'1 (UID 101 ENVELOPE ("15-Nov-2024 10:30:00 +0100" '
                        b'"Ihre Rechnung" '
                        b'((NIL NIL "rechnung" "amazon.de")) '
                        b'NIL NIL NIL NIL NIL NIL NIL) '
                        b'BODYSTRUCTURE (("TEXT" "PLAIN" NIL NIL NIL "7BIT" 100 10 NIL NIL NIL NIL)'
                        b'("APPLICATION" "PDF" ("NAME" "Rechnung.pdf") NIL NIL "BASE64" 5000 NIL '
                        b'("ATTACHMENT" ("FILENAME" "Rechnung.pdf")) NIL NIL) "MIXED"))',
                    ),
                    b")",
                ],
            )
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            emails = service.list_emails("INBOX")

            assert len(emails) == 1
            assert emails[0].has_attachments is True

    def test_has_attachments_false_for_multipart_alternative(self):
        """has_attachments is False for multipart/alternative (HTML+Text) without attachment."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])
            mock_conn.search.return_value = ("OK", [b"1"])
            # BODYSTRUCTURE with multipart/alternative but NO attachment
            mock_conn.fetch.return_value = (
                "OK",
                [
                    (
                        b'1 (UID 101 ENVELOPE ("15-Nov-2024 10:30:00 +0100" '
                        b'"Newsletter" '
                        b'((NIL NIL "news" "example.com")) '
                        b'NIL NIL NIL NIL NIL NIL NIL) '
                        b'BODYSTRUCTURE (("TEXT" "PLAIN" NIL NIL NIL "7BIT" 100 10 NIL NIL NIL NIL)'
                        b'("TEXT" "HTML" NIL NIL NIL "QUOTED-PRINTABLE" 500 20 NIL NIL NIL NIL) "ALTERNATIVE"))',
                    ),
                    b")",
                ],
            )
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            emails = service.list_emails("INBOX")

            assert len(emails) == 1
            assert emails[0].has_attachments is False

    def test_has_attachments_false_for_plain_text(self):
        """has_attachments is False for simple text email."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])
            mock_conn.search.return_value = ("OK", [b"1"])
            # Simple text email
            mock_conn.fetch.return_value = (
                "OK",
                [
                    (
                        b'1 (UID 101 ENVELOPE ("15-Nov-2024 10:30:00 +0100" '
                        b'"Kurze Nachricht" '
                        b'((NIL NIL "sender" "example.com")) '
                        b'NIL NIL NIL NIL NIL NIL NIL) '
                        b'BODYSTRUCTURE ("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 50 5 NIL NIL NIL NIL))',
                    ),
                    b")",
                ],
            )
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            emails = service.list_emails("INBOX")

            assert len(emails) == 1
            assert emails[0].has_attachments is False

    def test_has_attachments_true_with_inline_disposition_ignored(self):
        """has_attachments ignores inline images (only counts attachment disposition)."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])
            mock_conn.search.return_value = ("OK", [b"1"])
            # BODYSTRUCTURE with inline image but no attachment
            mock_conn.fetch.return_value = (
                "OK",
                [
                    (
                        b'1 (UID 101 ENVELOPE ("15-Nov-2024 10:30:00 +0100" '
                        b'"Email mit Bild" '
                        b'((NIL NIL "sender" "example.com")) '
                        b'NIL NIL NIL NIL NIL NIL NIL) '
                        b'BODYSTRUCTURE (("TEXT" "HTML" NIL NIL NIL "7BIT" 100 10 NIL NIL NIL NIL)'
                        b'("IMAGE" "PNG" ("NAME" "logo.png") NIL NIL "BASE64" 5000 NIL '
                        b'("INLINE" ("FILENAME" "logo.png")) NIL NIL) "RELATED"))',
                    ),
                    b")",
                ],
            )
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            emails = service.list_emails("INBOX")

            assert len(emails) == 1
            assert emails[0].has_attachments is False

    def test_has_attachments_true_without_quotes(self):
        """has_attachments detects attachment without quotes in BODYSTRUCTURE."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])
            mock_conn.search.return_value = ("OK", [b"1"])
            # BODYSTRUCTURE with attachment but no quotes around disposition
            mock_conn.fetch.return_value = (
                "OK",
                [
                    (
                        b'1 (UID 101 ENVELOPE ("23-Nov-2025 13:38:00 +0100" '
                        b'"Ihre Rechnung" '
                        b'((NIL NIL "support" "domaindiscount24.com")) '
                        b'NIL NIL NIL NIL NIL NIL NIL) '
                        b'BODYSTRUCTURE (("TEXT" "HTML" ("CHARSET" "utf-8") NIL NIL "7BIT" 100 10 NIL NIL NIL NIL)'
                        b'("APPLICATION" "OCTET-STREAM" NIL NIL NIL "BASE64" 5000 NIL '
                        b'(attachment ("FILENAME" "2025172897.pdf")) NIL NIL) "MIXED"))',
                    ),
                    b")",
                ],
            )
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            emails = service.list_emails("INBOX")

            assert len(emails) == 1
            assert emails[0].has_attachments is True

    def test_has_attachments_true_with_filename_in_bodystructure(self):
        """has_attachments detects attachment via filename pattern in BODYSTRUCTURE."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_conn.select.return_value = ("OK", [b"1"])
            mock_conn.search.return_value = ("OK", [b"1"])
            # BODYSTRUCTURE with filename but different disposition format
            mock_conn.fetch.return_value = (
                "OK",
                [
                    (
                        b'1 (UID 101 ENVELOPE ("23-Nov-2025 13:38:00 +0100" '
                        b'"Ihre Rechnung" '
                        b'((NIL NIL "support" "example.com")) '
                        b'NIL NIL NIL NIL NIL NIL NIL) '
                        b'BODYSTRUCTURE (("TEXT" "PLAIN" NIL NIL NIL "7BIT" 100 10 NIL NIL NIL NIL)'
                        b'("APPLICATION" "PDF" ("NAME" "invoice.pdf") NIL NIL "BASE64" 5000 NIL '
                        b'NIL NIL NIL) "MIXED"))',
                    ),
                    b")",
                ],
            )
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            emails = service.list_emails("INBOX")

            assert len(emails) == 1
            assert emails[0].has_attachments is True


class TestImapServicePrefetch:
    """Test prefetch connection for parallel email fetching."""

    def test_connect_prefetch_establishes_second_connection(self):
        """connect_prefetch() creates a separate IMAP connection."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn1 = MagicMock()
            mock_conn1.login.return_value = ("OK", [])
            mock_conn2 = MagicMock()
            mock_conn2.login.return_value = ("OK", [])
            mock_imap.side_effect = [mock_conn1, mock_conn2]

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            result = service.connect_prefetch("user@example.com", "password123")

            assert result is True
            assert mock_imap.call_count == 2

    def test_connect_prefetch_returns_false_on_failure(self):
        """connect_prefetch() returns False when connection fails."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn1 = MagicMock()
            mock_conn1.login.return_value = ("OK", [])
            mock_imap.side_effect = [mock_conn1, Exception("Connection refused")]

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            result = service.connect_prefetch("user@example.com", "password123")

            assert result is False

    def test_fetch_email_prefetch_uses_separate_connection(self):
        """fetch_email_prefetch() uses the prefetch connection."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn1 = MagicMock()
            mock_conn1.login.return_value = ("OK", [])
            mock_conn2 = MagicMock()
            mock_conn2.login.return_value = ("OK", [])
            mock_conn2.select.return_value = ("OK", [b"1"])

            email_bytes = (
                b"From: test@example.com\r\n"
                b"Subject: Test\r\n"
                b"Date: Fri, 15 Nov 2024 10:30:00 +0100\r\n"
                b"Message-ID: <test@example.com>\r\n"
                b"Content-Type: text/plain\r\n"
                b"\r\n"
                b"Test body\r\n"
            )
            mock_conn2.uid.return_value = ("OK", [(b"1 (RFC822 ", email_bytes, b")")])
            mock_imap.side_effect = [mock_conn1, mock_conn2]

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            service.connect_prefetch("user@example.com", "password123")
            email = service.fetch_email_prefetch(101, "INBOX")

            assert email is not None
            # Verify prefetch connection was used, not main connection
            mock_conn2.select.assert_called()
            mock_conn1.select.assert_not_called()

    def test_fetch_email_prefetch_returns_none_without_prefetch_connection(self):
        """fetch_email_prefetch() returns None if prefetch not connected."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.return_value = ("OK", [])
            mock_imap.return_value = mock_conn

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            # Don't call connect_prefetch
            email = service.fetch_email_prefetch(101, "INBOX")

            assert email is None

    def test_disconnect_closes_both_connections(self):
        """disconnect() closes main and prefetch connections."""
        with patch("imaplib.IMAP4_SSL") as mock_imap:
            mock_conn1 = MagicMock()
            mock_conn1.login.return_value = ("OK", [])
            mock_conn2 = MagicMock()
            mock_conn2.login.return_value = ("OK", [])
            mock_imap.side_effect = [mock_conn1, mock_conn2]

            service = ImapService("imap.example.com")
            service.connect("user@example.com", "password123")
            service.connect_prefetch("user@example.com", "password123")
            service.disconnect()

            mock_conn1.logout.assert_called_once()
            mock_conn2.logout.assert_called_once()
            assert service.is_connected is False


class TestDataClasses:
    """Test data classes."""

    def test_email_summary_fields(self):
        """EmailSummary has all required fields."""
        summary = EmailSummary(
            uid=123,
            sender="test@example.com",
            subject="Test Subject",
            date=datetime(2024, 11, 15),
            has_attachments=True,
        )

        assert summary.uid == 123
        assert summary.sender == "test@example.com"
        assert summary.subject == "Test Subject"
        assert summary.date == datetime(2024, 11, 15)
        assert summary.has_attachments is True

    def test_email_attachment_fields(self):
        """EmailAttachment has all required fields."""
        attachment = EmailAttachment(
            filename="test.pdf",
            content_type="application/pdf",
            size=1024,
            data=b"%PDF-1.4",
        )

        assert attachment.filename == "test.pdf"
        assert attachment.content_type == "application/pdf"
        assert attachment.size == 1024
        assert attachment.data == b"%PDF-1.4"

    def test_email_message_fields(self):
        """EmailMessage has all required fields."""
        message = EmailMessage(
            uid=123,
            sender="test@example.com",
            subject="Test Subject",
            date=datetime(2024, 11, 15),
            message_id="<test@example.com>",
            body_text="Hello World",
            body_html="<p>Hello World</p>",
            attachments=[],
        )

        assert message.uid == 123
        assert message.sender == "test@example.com"
        assert message.subject == "Test Subject"
        assert message.message_id == "<test@example.com>"
        assert message.body_text == "Hello World"
        assert message.body_html == "<p>Hello World</p>"
        assert message.attachments == []
