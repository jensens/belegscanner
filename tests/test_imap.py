"""Tests for ImapService."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from imapclient.response_types import Address, Envelope

from belegscanner.services.imap import (
    SOCKET_TIMEOUT,
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

    @patch("belegscanner.services.imap.IMAPClient")
    def test_connect_establishes_connection(self, mock_client_cls):
        """connect() establishes IMAP connection."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        success, error = service.connect("user@example.com", "secret")
        assert success is True
        assert error == ""
        mock_client_cls.assert_called_once_with(
            "imap.example.com", port=993, ssl=True, timeout=SOCKET_TIMEOUT
        )
        mock_client.login.assert_called_once_with("user@example.com", "secret")
        assert service.is_connected

    @patch("belegscanner.services.imap.IMAPClient")
    def test_connect_returns_false_on_auth_failure(self, mock_client_cls):
        """connect() returns False with error message when authentication fails."""
        mock_client = MagicMock()
        mock_client.login.side_effect = Exception("AUTHENTICATIONFAILED")
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        success, error = service.connect("user@example.com", "wrong")
        assert success is False
        assert "AUTHENTICATIONFAILED" in error
        assert not service.is_connected

    @patch("belegscanner.services.imap.IMAPClient")
    def test_connect_returns_false_on_connection_failure(self, mock_client_cls):
        """connect() returns False with error when server is unreachable."""
        mock_client_cls.side_effect = Exception("Connection refused")

        service = ImapService("imap.example.com")
        success, error = service.connect("user@example.com", "password123")

        assert success is False
        assert "Connection refused" in error
        assert service.is_connected is False

    @patch("belegscanner.services.imap.IMAPClient")
    def test_disconnect_closes_connection(self, mock_client_cls):
        """disconnect() closes IMAP connection."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        service = ImapService("imap.example.com")
        service.connect("user@example.com", "password123")
        service.disconnect()

        assert service.is_connected is False
        mock_client.logout.assert_called_once()

    def test_disconnect_handles_already_disconnected(self):
        """disconnect() handles case when not connected."""
        service = ImapService("imap.example.com")

        # Should not raise
        service.disconnect()

        assert service.is_connected is False

    @patch("belegscanner.services.imap.IMAPClient")
    def test_disconnect_swallows_logout_errors(self, mock_client_cls):
        """disconnect() ignores exceptions raised during logout."""
        mock_client = MagicMock()
        mock_client.logout.side_effect = Exception("connection reset")
        mock_client_cls.return_value = mock_client

        service = ImapService("imap.example.com")
        service.connect("user@example.com", "password123")

        # Should not raise
        service.disconnect()

        assert service.is_connected is False


class TestImapServiceListFolders:
    """Test folder listing."""

    @patch("belegscanner.services.imap.IMAPClient")
    def test_list_folders_returns_folder_names(self, mock_client_cls):
        """list_folders() returns list of folder names."""
        mock_client = MagicMock()
        mock_client.list_folders.return_value = [
            ((b"\\HasNoChildren",), b"/", "INBOX"),
            ((b"\\HasNoChildren",), b"/", "Rechnungseingang"),
        ]
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.list_folders() == ["INBOX", "Rechnungseingang"]

    def test_list_folders_returns_empty_when_not_connected(self):
        """list_folders() returns empty list when not connected."""
        service = ImapService("imap.example.com")

        folders = service.list_folders()

        assert folders == []


def make_envelope(subject=b"Rechnung", name=b"Amazon", mailbox=b"billing", host=b"amazon.de"):
    """Build an imapclient Envelope for tests."""
    return Envelope(
        date=datetime(2024, 11, 15, 10, 0),
        subject=subject,
        from_=(Address(name, None, mailbox, host),),
        sender=None,
        reply_to=None,
        to=None,
        cc=None,
        bcc=None,
        in_reply_to=None,
        message_id=b"<x@y>",
    )


class TestImapServiceListEmails:
    """Test email listing."""

    @patch("belegscanner.services.imap.IMAPClient")
    def test_list_emails_returns_email_summaries(self, mock_client_cls):
        """list_emails() returns list of EmailSummary objects."""
        mock_client = MagicMock()
        mock_client.search.return_value = [7]
        mock_client.fetch.return_value = {7: {b"ENVELOPE": make_envelope(), b"BODYSTRUCTURE": None}}
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        result = service.list_emails("INBOX")
        assert len(result) == 1
        assert result[0].uid == 7
        assert result[0].subject == "Rechnung"
        assert "billing@amazon.de" in result[0].sender
        mock_client.select_folder.assert_called_with("INBOX")

    @patch("belegscanner.services.imap.IMAPClient")
    def test_subject_is_rfc2047_decoded(self, mock_client_cls):
        """list_emails() decodes RFC-2047 encoded subjects."""
        mock_client = MagicMock()
        mock_client.search.return_value = [1]
        mock_client.fetch.return_value = {
            1: {
                b"ENVELOPE": make_envelope(subject=b"=?utf-8?q?Rechnung_M=C3=A4rz?="),
                b"BODYSTRUCTURE": None,
            }
        }
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.list_emails("INBOX")[0].subject == "Rechnung März"

    @patch("belegscanner.services.imap.IMAPClient")
    def test_list_emails_empty_folder(self, mock_client_cls):
        """list_emails() returns empty list for empty folder."""
        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.list_emails("INBOX") == []

    def test_list_emails_returns_empty_when_not_connected(self):
        """list_emails() returns empty list when not connected."""
        assert ImapService("imap.example.com").list_emails("INBOX") == []


class TestImapServiceFetchEmail:
    """Test full email fetching."""

    @patch("belegscanner.services.imap.IMAPClient")
    def test_fetch_email_returns_full_message(self, mock_client_cls):
        """fetch_email() returns EmailMessage with all details."""
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
        mock_client = MagicMock()
        mock_client.fetch.return_value = {101: {b"RFC822": email_bytes}}
        mock_client_cls.return_value = mock_client

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
        mock_client.select_folder.assert_called_with("Rechnungseingang")

    @patch("belegscanner.services.imap.IMAPClient")
    def test_fetch_email_extracts_pdf_attachments(self, mock_client_cls):
        """fetch_email() extracts PDF attachments."""
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
        mock_client = MagicMock()
        mock_client.fetch.return_value = {101: {b"RFC822": email_bytes}}
        mock_client_cls.return_value = mock_client

        service = ImapService("imap.example.com")
        service.connect("user@example.com", "password123")
        email = service.fetch_email(101, "Rechnungseingang")

        assert email is not None
        assert len(email.attachments) == 1
        assert email.attachments[0].filename == "Rechnung.pdf"
        assert email.attachments[0].content_type == "application/pdf"
        assert len(email.attachments[0].data) > 0

    @patch("belegscanner.services.imap.IMAPClient")
    def test_fetch_email_extracts_octet_stream_attachment(self, mock_client_cls):
        """fetch_email() extracts application/octet-stream with PDF filename."""
        # Email with application/octet-stream attachment (like domaindiscount24)
        email_bytes = (
            b"From: support@domaindiscount24.com\r\n"
            b"Subject: Ihre Rechnung\r\n"
            b"Date: 23 Nov 2025 13:38:00 +0100\r\n"
            b"Message-ID: <test@example.com>\r\n"
            b'Content-Type: multipart/mixed; boundary="boundary123"\r\n'
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
        mock_client = MagicMock()
        mock_client.fetch.return_value = {101: {b"RFC822": email_bytes}}
        mock_client_cls.return_value = mock_client

        service = ImapService("imap.example.com")
        service.connect("user@example.com", "password123")
        email = service.fetch_email(101, "INBOX")

        assert email is not None
        assert len(email.attachments) == 1
        assert email.attachments[0].filename == "2025172897.pdf"
        assert email.attachments[0].content_type == "application/octet-stream"

    @patch("belegscanner.services.imap.IMAPClient")
    def test_fetch_email_returns_none_when_not_found(self, mock_client_cls):
        """fetch_email() returns None when email not found."""
        mock_client = MagicMock()
        mock_client.fetch.return_value = {}
        mock_client_cls.return_value = mock_client

        service = ImapService("imap.example.com")
        service.connect("user@example.com", "password123")
        email = service.fetch_email(999, "Rechnungseingang")

        assert email is None

    def test_fetch_email_returns_none_when_not_connected(self):
        """fetch_email() returns None when not connected."""
        service = ImapService("imap.example.com")

        email = service.fetch_email(101, "Rechnungseingang")

        assert email is None

    @patch("belegscanner.services.imap.IMAPClient")
    def test_attachment_filename_is_sanitized_on_parse(self, mock_client_cls):
        raw = (
            b"From: a@b.de\r\nSubject: x\r\nDate: Mon, 4 Nov 2024 10:00:00 +0100\r\n"
            b"Message-ID: <1@b>\r\nMIME-Version: 1.0\r\n"
            b'Content-Type: multipart/mixed; boundary="B"\r\n\r\n'
            b"--B\r\nContent-Type: text/plain\r\n\r\nText\r\n"
            b"--B\r\nContent-Type: application/pdf\r\n"
            b'Content-Disposition: attachment; filename="../../etc/passwd.pdf"\r\n'
            b"Content-Transfer-Encoding: base64\r\n\r\nJVBERg==\r\n--B--\r\n"
        )
        mock_client = MagicMock()
        mock_client.fetch.return_value = {42: {b"RFC822": raw}}
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        message = service.fetch_email(42, "INBOX")
        assert message.attachments[0].filename == "passwd.pdf"


class TestImapServiceMoveEmail:
    @patch("belegscanner.services.imap.IMAPClient")
    def test_move_uses_move_capability(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.has_capability.side_effect = lambda cap: cap == "MOVE"
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.move_email(5, "INBOX", "Archiv") is True
        mock_client.move.assert_called_once_with([5], "Archiv")
        mock_client.copy.assert_not_called()

    @patch("belegscanner.services.imap.IMAPClient")
    def test_move_falls_back_to_copy_delete_expunge(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.has_capability.side_effect = lambda cap: cap == "UIDPLUS"
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.move_email(5, "INBOX", "Archiv") is True
        mock_client.copy.assert_called_once_with([5], "Archiv")
        mock_client.delete_messages.assert_called_once_with([5])
        mock_client.expunge.assert_called_once_with([5])

    @patch("belegscanner.services.imap.IMAPClient")
    def test_move_returns_false_on_failure(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.has_capability.return_value = True
        mock_client.move.side_effect = Exception("kaputt")
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.move_email(5, "INBOX", "Archiv") is False

    def test_move_returns_false_when_not_connected(self):
        assert ImapService("x").move_email(5, "a", "b") is False


class FakePart(tuple):
    """Fake single-part BODYSTRUCTURE entry for attachment-detection tests."""

    is_multipart = False


class FakeMultipart(tuple):
    """Fake multipart BODYSTRUCTURE entry for attachment-detection tests."""

    is_multipart = True


class TestHasAttachmentsDetection:
    """Test attachment detection in BODYSTRUCTURE parsing."""

    def _service(self):
        return ImapService("imap.example.com")

    def test_none_structure(self):
        assert self._service()._structure_has_attachments(None) is False

    def test_plain_text_part(self):
        part = FakePart((b"text", b"plain", (b"charset", b"utf-8"), None, None, b"7bit", 42))
        assert self._service()._structure_has_attachments(part) is False

    def test_attachment_disposition(self):
        part = FakePart(
            (
                b"application",
                b"pdf",
                None,
                None,
                None,
                b"base64",
                1000,
                None,
                (b"attachment", (b"filename", b"invoice.pdf")),
            )
        )
        assert self._service()._structure_has_attachments(part) is True

    def test_pdf_by_param_name(self):
        part = FakePart(
            (
                b"application",
                b"octet-stream",
                (b"name", b"rechnung.PDF"),
                None,
                None,
                b"base64",
                1000,
            )
        )
        assert self._service()._structure_has_attachments(part) is True

    def test_multipart_with_nested_attachment(self):
        text = FakePart((b"text", b"plain", None, None, None, b"7bit", 10))
        pdf = FakePart(
            (
                b"application",
                b"pdf",
                None,
                None,
                None,
                b"base64",
                99,
                None,
                (b"attachment", (b"filename", b"a.pdf")),
            )
        )
        multi = FakeMultipart(([text, pdf], b"mixed"))
        assert self._service()._structure_has_attachments(multi) is True

    def test_broken_structure_returns_false(self):
        assert self._service()._structure_has_attachments(FakePart(())) is False


class TestImapServicePrefetch:
    """Test prefetch connection for parallel email fetching."""

    @patch("belegscanner.services.imap.IMAPClient")
    def test_connect_prefetch_establishes_second_connection(self, mock_client_cls):
        """connect_prefetch() creates a separate IMAP connection."""
        main_mock = MagicMock()
        prefetch_mock = MagicMock()
        mock_client_cls.side_effect = [main_mock, prefetch_mock]

        service = ImapService("imap.example.com")
        service.connect("user@example.com", "password123")
        result = service.connect_prefetch("user@example.com", "password123")

        assert result is True
        assert mock_client_cls.call_count == 2

    @patch("belegscanner.services.imap.IMAPClient")
    def test_connect_prefetch_returns_false_on_failure(self, mock_client_cls):
        """connect_prefetch() returns False when connection fails."""
        main_mock = MagicMock()
        mock_client_cls.side_effect = [main_mock, Exception("Connection refused")]

        service = ImapService("imap.example.com")
        service.connect("user@example.com", "password123")
        result = service.connect_prefetch("user@example.com", "password123")

        assert result is False

    @patch("belegscanner.services.imap.IMAPClient")
    def test_fetch_email_prefetch_uses_separate_connection(self, mock_client_cls):
        """fetch_email_prefetch() uses the prefetch connection."""
        main_mock = MagicMock()
        prefetch_mock = MagicMock()

        email_bytes = (
            b"From: test@example.com\r\n"
            b"Subject: Test\r\n"
            b"Date: Fri, 15 Nov 2024 10:30:00 +0100\r\n"
            b"Message-ID: <test@example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Test body\r\n"
        )
        prefetch_mock.fetch.return_value = {101: {b"RFC822": email_bytes}}
        mock_client_cls.side_effect = [main_mock, prefetch_mock]

        service = ImapService("imap.example.com")
        service.connect("user@example.com", "password123")
        service.connect_prefetch("user@example.com", "password123")
        email = service.fetch_email_prefetch(101, "INBOX")

        assert email is not None
        # Verify prefetch connection was used, not main connection
        prefetch_mock.select_folder.assert_called_with("INBOX")
        main_mock.select_folder.assert_not_called()

    @patch("belegscanner.services.imap.IMAPClient")
    def test_fetch_email_prefetch_returns_none_without_prefetch_connection(self, mock_client_cls):
        """fetch_email_prefetch() returns None if prefetch not connected."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        service = ImapService("imap.example.com")
        service.connect("user@example.com", "password123")
        # Don't call connect_prefetch
        email = service.fetch_email_prefetch(101, "INBOX")

        assert email is None

    @patch("belegscanner.services.imap.IMAPClient")
    def test_disconnect_closes_both_connections(self, mock_client_cls):
        """disconnect() closes main and prefetch connections."""
        main_mock = MagicMock()
        prefetch_mock = MagicMock()
        mock_client_cls.side_effect = [main_mock, prefetch_mock]

        service = ImapService("imap.example.com")
        service.connect("user@example.com", "password123")
        service.connect_prefetch("user@example.com", "password123")
        service.disconnect()

        main_mock.logout.assert_called_once()
        prefetch_mock.logout.assert_called_once()
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
