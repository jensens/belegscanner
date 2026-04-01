"""Tests for EmailViewModel."""

from datetime import datetime

# Import after mocking gi (if needed)
import gi

from belegscanner.services.imap import EmailAttachment, EmailMessage, EmailSummary

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


class TestEmailViewModelFilter:
    """Test email filtering."""

    def test_filter_by_sender(self):
        """Filter matches sender address."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="rechnung@amazon.de",
                    subject="Bestellung",
                    date=datetime(2024, 11, 15),
                    has_attachments=True,
                ),
                EmailSummary(
                    uid=2,
                    sender="newsletter@example.com",
                    subject="News",
                    date=datetime(2024, 11, 16),
                    has_attachments=False,
                ),
            ]
        )

        vm.set_filter("amazon")

        assert len(vm.filtered_emails) == 1
        assert vm.filtered_emails[0].uid == 1

    def test_filter_by_subject(self):
        """Filter matches subject."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="test@example.com",
                    subject="Ihre Rechnung #12345",
                    date=datetime(2024, 11, 15),
                    has_attachments=True,
                ),
                EmailSummary(
                    uid=2,
                    sender="other@example.com",
                    subject="Newsletter",
                    date=datetime(2024, 11, 16),
                    has_attachments=False,
                ),
            ]
        )

        vm.set_filter("rechnung")

        assert len(vm.filtered_emails) == 1
        assert vm.filtered_emails[0].uid == 1

    def test_filter_empty_query_returns_all(self):
        """Empty filter query returns all emails."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="test@example.com",
                    subject="Test 1",
                    date=datetime(2024, 11, 15),
                    has_attachments=False,
                ),
                EmailSummary(
                    uid=2,
                    sender="other@example.com",
                    subject="Test 2",
                    date=datetime(2024, 11, 16),
                    has_attachments=False,
                ),
            ]
        )

        vm.set_filter("")

        assert len(vm.filtered_emails) == 2

    def test_filter_case_insensitive(self):
        """Filter is case insensitive."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="Rechnung@Amazon.DE",
                    subject="IHRE BESTELLUNG",
                    date=datetime(2024, 11, 15),
                    has_attachments=True,
                ),
            ]
        )

        vm.set_filter("amazon")

        assert len(vm.filtered_emails) == 1

    def test_filter_no_match_returns_empty(self):
        """Filter with no matches returns empty list."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="test@example.com",
                    subject="Test",
                    date=datetime(2024, 11, 15),
                    has_attachments=False,
                ),
            ]
        )

        vm.set_filter("xyz123notfound")

        assert len(vm.filtered_emails) == 0

    def test_filtered_emails_without_filter_returns_all(self):
        """filtered_emails property returns all when no filter set."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="test@example.com",
                    subject="Test",
                    date=datetime(2024, 11, 15),
                    has_attachments=False,
                ),
            ]
        )

        # No set_filter called
        assert len(vm.filtered_emails) == 1


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


class TestEmailViewModelCache:
    """Test email caching functionality."""

    def test_get_cached_email_returns_none_initially(self):
        """Cache is empty initially."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        assert vm.get_cached_email(123) is None

    def test_cache_email_stores_for_retrieval(self):
        """Cached email can be retrieved."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        email = EmailMessage(
            uid=123,
            sender="test@example.com",
            subject="Test",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="Content",
            body_html=None,
            attachments=[],
        )

        vm.cache_email(email)
        result = vm.get_cached_email(123)

        assert result is not None
        assert result.uid == 123

    def test_invalidate_removes_from_cache(self):
        """Invalidate removes email from cache."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        email = EmailMessage(
            uid=123,
            sender="test@example.com",
            subject="Test",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="Content",
            body_html=None,
            attachments=[],
        )
        vm.cache_email(email)

        vm.invalidate_cached_email(123)

        assert vm.get_cached_email(123) is None

    def test_clear_also_clears_cache(self):
        """Clear method also clears the cache."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        email = EmailMessage(
            uid=123,
            sender="test@example.com",
            subject="Test",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="Content",
            body_html=None,
            attachments=[],
        )
        vm.cache_email(email)

        vm.clear()

        assert vm.get_cached_email(123) is None


class TestEmailViewModelNextEmail:
    """Test next email UID lookup for prefetching."""

    def test_get_next_email_uid_returns_next(self):
        """get_next_email_uid returns UID of next email in list."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="a@test.com",
                    subject="A",
                    date=datetime(2024, 11, 17),
                    has_attachments=False,
                ),
                EmailSummary(
                    uid=2,
                    sender="b@test.com",
                    subject="B",
                    date=datetime(2024, 11, 16),
                    has_attachments=False,
                ),
                EmailSummary(
                    uid=3,
                    sender="c@test.com",
                    subject="C",
                    date=datetime(2024, 11, 15),
                    has_attachments=False,
                ),
            ]
        )

        next_uid = vm.get_next_email_uid(0)

        assert next_uid == 2

    def test_get_next_email_uid_returns_none_at_end(self):
        """get_next_email_uid returns None at end of list."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="a@test.com",
                    subject="A",
                    date=datetime(2024, 11, 15),
                    has_attachments=False,
                ),
            ]
        )

        next_uid = vm.get_next_email_uid(0)

        assert next_uid is None

    def test_get_next_email_uid_returns_none_for_invalid_index(self):
        """get_next_email_uid returns None for invalid index."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="a@test.com",
                    subject="A",
                    date=datetime(2024, 11, 15),
                    has_attachments=False,
                ),
            ]
        )

        next_uid = vm.get_next_email_uid(99)

        assert next_uid is None

    def test_get_next_email_uid_respects_filter(self):
        """get_next_email_uid works with filtered list."""
        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="amazon@test.com",
                    subject="Order",
                    date=datetime(2024, 11, 17),
                    has_attachments=False,
                ),
                EmailSummary(
                    uid=2,
                    sender="other@test.com",
                    subject="News",
                    date=datetime(2024, 11, 16),
                    has_attachments=False,
                ),
                EmailSummary(
                    uid=3,
                    sender="amazon@test.com",
                    subject="Shipping",
                    date=datetime(2024, 11, 15),
                    has_attachments=False,
                ),
            ]
        )
        vm.set_filter("amazon")

        # Filtered list: [1, 3] (by date: 1 first, then 3)
        next_uid = vm.get_next_email_uid(0)

        assert next_uid == 3


class TestEmailViewModelAmountExtraction:
    """Test amount extraction from email body."""

    def test_extracts_amount_from_body_text(self):
        """Extracts amount and currency from email body text."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="rechnung@amazon.de",
            subject="Ihre Rechnung",
            date=datetime(2024, 11, 15),
            message_id="<abc@amazon.de>",
            body_text="Vielen Dank für Ihre Bestellung.\n\nGesamtbetrag: 47,99 EUR\n\nMit freundlichen Grüßen",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        assert vm.suggested_currency == "EUR"
        assert vm.suggested_amount == "47.99"

    def test_extracts_euro_symbol(self):
        """Extracts amount with € symbol."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="rechnung@shop.de",
            subject="Rechnung",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="Ihre Rechnung\nBrutto: € 29,95",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        assert vm.suggested_currency == "EUR"
        assert vm.suggested_amount == "29.95"

    def test_extracts_usd_from_body(self):
        """Extracts USD amount from email body."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="receipt@hotel.com",
            subject="Your Receipt",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="Thank you for staying with us.\n\nTotal: $150.00 USD",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        assert vm.suggested_currency == "USD"
        assert vm.suggested_amount == "150.00"

    def test_no_amount_in_body_defaults_to_empty(self):
        """When no amount in body, suggested_amount is empty."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="news@example.com",
            subject="Newsletter",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="Welcome to our newsletter. No prices here.",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        assert vm.suggested_currency == "EUR"  # Default
        assert vm.suggested_amount == ""

    def test_clear_resets_amount(self):
        """Clear resets amount and currency."""
        vm = EmailViewModel()
        vm.suggested_currency = "USD"
        vm.suggested_amount = "99.99"

        vm.clear()

        assert vm.suggested_currency == "EUR"
        assert vm.suggested_amount == ""

    def test_set_none_email_resets_amount(self):
        """Setting email to None resets amount."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="shop@example.com",
            subject="Receipt",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="Summe: 50,00 EUR",
            body_html=None,
            attachments=[],
        )
        vm.set_current_email(email)

        vm.set_current_email(None)

        assert vm.suggested_currency == "EUR"
        assert vm.suggested_amount == ""


class TestEmailViewModelVendorExtraction:
    """Test vendor extraction from email sender/subject."""

    def test_extracts_vendor_from_display_name(self):
        """Uses display name when available."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="Amazon Deutschland <rechnung@email-amazon.de>",
            subject="Ihre Bestellung",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        assert "amazon" in vm.suggested_description.lower()

    def test_extracts_vendor_from_domain(self):
        """Falls back to domain when no display name."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="rechnung@zalando.de",
            subject="Ihre Rechnung",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        assert vm.suggested_description == "zalando"

    def test_uses_subject_when_domain_blacklisted(self):
        """Falls back to subject for generic domains."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="noreply@invoice-service.com",
            subject="Rechnung von MediaMarkt #12345",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        assert "mediamarkt" in vm.suggested_description.lower()

    def test_skips_own_company_domain(self):
        """Doesn't use own company as vendor."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="weiterleitung@kleinundpartner.de",
            subject="Fwd: Rechnung von Telekom",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        assert "kleinundpartner" not in vm.suggested_description.lower()
        assert "telekom" in vm.suggested_description.lower()

    def test_empty_sender_uses_subject(self):
        """Empty sender falls back to subject."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="",
            subject="Rechnung von Amazon",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        assert vm.suggested_description == "amazon"

    def test_returns_empty_when_nothing_found(self):
        """Returns empty string when no vendor can be extracted."""
        vm = EmailViewModel()
        email = EmailMessage(
            uid=101,
            sender="noreply@service.com",
            subject="Wichtige Mitteilung",
            date=datetime(2024, 11, 15),
            message_id="<test>",
            body_text="",
            body_html=None,
            attachments=[],
        )

        vm.set_current_email(email)

        # Should be empty since all terms are blacklisted
        assert vm.suggested_description == ""
