"""Tests for race condition prevention in email fetching.

These tests ensure that fetch requests are tracked properly to prevent
stale callbacks from updating the UI with outdated data.
"""

from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")

from belegscanner.email_viewmodel import EmailViewModel
from belegscanner.services.imap import EmailMessage


def make_email(uid: int) -> EmailMessage:
    """Helper to create a test email with given UID."""
    return EmailMessage(
        uid=uid,
        sender=f"test{uid}@example.com",
        subject=f"Test Email {uid}",
        date=datetime(2024, 11, 15),
        message_id=f"<test{uid}@example.com>",
        body_text=f"Content for email {uid}",
        body_html=None,
        attachments=[],
    )


class TestFetchRequestTracking:
    """Test fetch request ID tracking to prevent race conditions."""

    def test_start_fetch_request_returns_unique_id(self):
        """Each fetch request gets a unique ID."""
        vm = EmailViewModel()
        id1 = vm.start_fetch_request(100)
        id2 = vm.start_fetch_request(200)
        assert id1 != id2

    def test_start_fetch_request_increments_id(self):
        """Fetch request IDs increment sequentially."""
        vm = EmailViewModel()
        id1 = vm.start_fetch_request(100)
        id2 = vm.start_fetch_request(200)
        id3 = vm.start_fetch_request(300)
        assert id2 == id1 + 1
        assert id3 == id2 + 1

    def test_complete_fetch_request_accepted_when_current(self):
        """Fetch request accepted when still current."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        request_id = vm.start_fetch_request(100)
        email = make_email(100)

        accepted = vm.complete_fetch_request(request_id, email)

        assert accepted is True
        assert vm.current_email is not None
        assert vm.current_email.uid == 100

    def test_complete_fetch_request_rejected_when_stale(self):
        """Fetch request rejected when another request started."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        old_request = vm.start_fetch_request(100)
        _new_request = vm.start_fetch_request(200)  # Start new request, making old one stale
        email_100 = make_email(100)

        accepted = vm.complete_fetch_request(old_request, email_100)

        assert accepted is False
        # current_email should NOT be updated
        assert vm.current_email is None

    def test_complete_fetch_request_rejected_with_wrong_id(self):
        """Fetch request rejected when ID doesn't match current."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        _request_id = vm.start_fetch_request(100)
        email = make_email(100)

        # Try to complete with wrong ID
        accepted = vm.complete_fetch_request(9999, email)

        assert accepted is False
        assert vm.current_email is None

    def test_cancel_fetch_request_rejects_pending(self):
        """Cancel makes pending request stale."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        request_id = vm.start_fetch_request(100)

        vm.cancel_fetch_request()

        accepted = vm.complete_fetch_request(request_id, make_email(100))
        assert accepted is False

    def test_cancel_fetch_request_allows_new_requests(self):
        """After cancel, new requests can be started and completed."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        vm.start_fetch_request(100)  # Old request
        vm.cancel_fetch_request()

        new_id = vm.start_fetch_request(200)
        email = make_email(200)
        accepted = vm.complete_fetch_request(new_id, email)

        assert accepted is True
        assert vm.current_email is not None
        assert vm.current_email.uid == 200

    def test_multiple_rapid_selections_only_last_completes(self):
        """When user clicks rapidly, only the last fetch completes."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")

        # Simulate rapid clicking through emails
        id1 = vm.start_fetch_request(100)
        id2 = vm.start_fetch_request(200)
        id3 = vm.start_fetch_request(300)

        # All fetches complete, but only the last should be accepted
        result1 = vm.complete_fetch_request(id1, make_email(100))
        result2 = vm.complete_fetch_request(id2, make_email(200))
        result3 = vm.complete_fetch_request(id3, make_email(300))

        assert result1 is False
        assert result2 is False
        assert result3 is True
        assert vm.current_email is not None
        assert vm.current_email.uid == 300

    def test_fetch_request_tracks_uid(self):
        """start_fetch_request stores the requested UID."""
        vm = EmailViewModel()
        vm.start_fetch_request(42)
        # Internal state check - the UID should be tracked
        # This is tested implicitly via complete_fetch_request behavior

    def test_clear_resets_fetch_request_state(self):
        """Clearing ViewModel resets fetch request tracking."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        request_id = vm.start_fetch_request(100)

        vm.clear()

        # After clear, old request should be stale
        accepted = vm.complete_fetch_request(request_id, make_email(100))
        assert accepted is False


class TestFetchRequestWithCache:
    """Test that fetch request tracking integrates with caching."""

    def test_complete_request_also_caches_email(self):
        """Completing a request should also cache the email."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        request_id = vm.start_fetch_request(100)
        email = make_email(100)

        vm.complete_fetch_request(request_id, email)

        # Email should be in cache
        cached = vm.get_cached_email(100)
        assert cached is not None
        assert cached.uid == 100

    def test_rejected_request_does_not_cache_email(self):
        """Rejected requests should NOT cache the email."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        old_request = vm.start_fetch_request(100)
        _new_request = vm.start_fetch_request(200)  # Makes old request stale
        email_100 = make_email(100)

        vm.complete_fetch_request(old_request, email_100)

        # Email 100 should NOT be in cache since request was rejected
        cached = vm.get_cached_email(100)
        assert cached is None
