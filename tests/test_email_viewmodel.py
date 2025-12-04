"""Tests for EmailViewModel."""

from datetime import datetime

import pytest

from belegscanner.services.imap import EmailAttachment, EmailMessage, EmailSummary

# Import after mocking gi (if needed)
import gi

gi.require_version("Gtk", "4.0")

from belegscanner.email_viewmodel import EmailViewModel


class TestEmailViewModelInitialState:
    """Test initial state of EmailViewModel."""

    def test_initial_status_not_connected(self):
        """Initial status is 'Nicht verbunden'."""
        vm = EmailViewModel()
        assert vm.status == "Nicht verbunden"

    def test_initial_not_busy(self):
        """Initially not busy."""
        vm = EmailViewModel()
        assert vm.is_busy is False

    def test_initial_not_connected(self):
        """Initially not connected."""
        vm = EmailViewModel()
        assert vm.is_connected is False

    def test_initial_emails_empty(self):
        """Initial emails list is empty."""
        vm = EmailViewModel()
        assert vm.emails == []

    def test_initial_selected_email_none(self):
        """Initially no email selected."""
        vm = EmailViewModel()
        assert vm.selected_email is None

    def test_initial_suggestions_empty(self):
        """Initial suggestions are empty."""
        vm = EmailViewModel()
        assert vm.suggested_date == ""
        assert vm.suggested_description == ""


class TestEmailViewModelProperties:
    """Test GObject property notifications."""

    def test_status_change_emits_signal(self):
        """Changing status emits notify signal."""
        vm = EmailViewModel()
        signaled = []

        def on_notify(obj, pspec):
            signaled.append(pspec.name)

        vm.connect("notify::status", on_notify)
        vm.status = "Test Status"

        assert "status" in signaled

    def test_is_busy_change_emits_signal(self):
        """Changing is_busy emits notify signal."""
        vm = EmailViewModel()
        signaled = []

        def on_notify(obj, pspec):
            signaled.append(pspec.name)

        vm.connect("notify::is-busy", on_notify)
        vm.is_busy = True

        assert "is-busy" in signaled


class TestEmailViewModelEmails:
    """Test email list management."""

    def test_set_emails(self):
        """Setting emails updates the list."""
        vm = EmailViewModel()
        emails = [
            EmailSummary(
                uid=1,
                sender="test@example.com",
                subject="Test",
                date=datetime(2024, 11, 15),
                has_attachments=False,
            )
        ]

        vm.set_emails(emails)

        assert len(vm.emails) == 1
        assert vm.emails[0].uid == 1

    def test_clear_emails(self):
        """Clearing emails empties the list."""
        vm = EmailViewModel()
        emails = [
            EmailSummary(
                uid=1,
                sender="test@example.com",
                subject="Test",
                date=datetime(2024, 11, 15),
                has_attachments=False,
            )
        ]
        vm.set_emails(emails)

        vm.clear()

        assert vm.emails == []


class TestEmailViewModelSelection:
    """Test email selection."""

    def test_select_email_by_uid(self):
        """Selecting email by UID updates selected_email."""
        vm = EmailViewModel()
        emails = [
            EmailSummary(
                uid=101,
                sender="test@example.com",
                subject="Test 1",
                date=datetime(2024, 11, 15),
                has_attachments=False,
            ),
            EmailSummary(
                uid=102,
                sender="other@example.com",
                subject="Test 2",
                date=datetime(2024, 11, 16),
                has_attachments=True,
            ),
        ]
        vm.set_emails(emails)

        vm.select_email(102)

        assert vm.selected_email is not None
        assert vm.selected_email.uid == 102

    def test_select_invalid_uid_clears_selection(self):
        """Selecting invalid UID clears selection."""
        vm = EmailViewModel()
        emails = [
            EmailSummary(
                uid=101,
                sender="test@example.com",
                subject="Test",
                date=datetime(2024, 11, 15),
                has_attachments=False,
            )
        ]
        vm.set_emails(emails)
        vm.select_email(101)

        vm.select_email(999)

        assert vm.selected_email is None


class TestEmailViewModelCurrentEmail:
    """Test current email details."""

    def test_set_current_email_message(self):
        """Setting current email message stores details."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="rechnung@amazon.de",
            subject="Ihre Rechnung #12345",
            date=datetime(2024, 11, 15),
            message_id="<abc@amazon.de>",
            body_text="Text content",
            body_html=None,
            attachments=[
                EmailAttachment(
                    filename="Rechnung.pdf",
                    content_type="application/pdf",
                    size=1024,
                    data=b"%PDF",
                )
            ],
        )

        vm.set_current_email(email)

        assert vm.current_email is not None
        assert vm.current_email.uid == 101
        assert len(vm.current_email.attachments) == 1

    def test_set_current_email_updates_suggestions(self):
        """Setting current email extracts date and description."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="rechnung@amazon.de",
            subject="Ihre Rechnung",
            date=datetime(2024, 11, 15),
            message_id="<abc@amazon.de>",
            body_text="Content",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        assert vm.suggested_date == "15.11.2024"
        assert "amazon" in vm.suggested_description.lower()


class TestEmailViewModelAttachmentSelection:
    """Test attachment selection."""

    def test_select_attachment_index(self):
        """Can select attachment by index."""
        vm = EmailViewModel()
        vm.set_current_email(
            EmailMessage(
                uid=101,
                sender="test@example.com",
                subject="Test",
                date=datetime(2024, 11, 15),
                message_id="<test>",
                body_text="",
                body_html=None,
                attachments=[
                    EmailAttachment("a.pdf", "application/pdf", 100, b""),
                    EmailAttachment("b.pdf", "application/pdf", 200, b""),
                ],
            )
        )

        vm.selected_attachment_index = 1

        assert vm.selected_attachment_index == 1

    def test_email_as_pdf_selection(self):
        """Can select 'email as PDF' option (index -1)."""
        vm = EmailViewModel()

        vm.selected_attachment_index = -1

        assert vm.selected_attachment_index == -1


class TestEmailViewModelClear:
    """Test clearing state."""

    def test_clear_resets_all_state(self):
        """Clear resets all state to initial values."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="test@example.com",
                    subject="Test",
                    date=datetime(2024, 11, 15),
                    has_attachments=False,
                )
            ]
        )
        vm.status = "Working"
        vm.is_busy = True
        vm.suggested_date = "15.11.2024"
        vm.suggested_description = "test"

        vm.clear()

        assert vm.emails == []
        assert vm.selected_email is None
        assert vm.current_email is None
        assert vm.suggested_date == ""
        assert vm.suggested_description == ""
        # Note: status and is_busy might not be reset by clear
