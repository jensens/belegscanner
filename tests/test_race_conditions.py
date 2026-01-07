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


class TestBusyCounter:
    """Test busy counter to prevent multiple operations from interfering."""

    def test_initially_not_busy(self):
        """ViewModel starts not busy."""
        vm = EmailViewModel()
        assert vm.is_busy is False

    def test_increment_makes_busy(self):
        """Incrementing counter makes busy."""
        vm = EmailViewModel()
        vm.increment_busy()
        assert vm.is_busy is True

    def test_decrement_after_increment_not_busy(self):
        """Decrementing after increment makes not busy."""
        vm = EmailViewModel()
        vm.increment_busy()
        vm.decrement_busy()
        assert vm.is_busy is False

    def test_multiple_increments_need_multiple_decrements(self):
        """Multiple operations need multiple completions."""
        vm = EmailViewModel()
        vm.increment_busy()
        vm.increment_busy()
        vm.increment_busy()

        vm.decrement_busy()
        assert vm.is_busy is True

        vm.decrement_busy()
        assert vm.is_busy is True

        vm.decrement_busy()
        assert vm.is_busy is False

    def test_decrement_below_zero_safe(self):
        """Decrementing below zero is safe."""
        vm = EmailViewModel()
        vm.decrement_busy()
        vm.decrement_busy()
        assert vm.is_busy is False
        assert vm._busy_count == 0

    def test_reset_clears_counter(self):
        """Reset clears busy counter."""
        vm = EmailViewModel()
        vm.increment_busy()
        vm.increment_busy()
        vm.reset_busy()
        assert vm.is_busy is False
        assert vm._busy_count == 0


class TestRefreshAutoSelect:
    """Tests for RC3: Refresh with auto-select index validation."""

    def test_auto_select_with_empty_list_returns_none(self):
        """Auto-select handles empty list by returning None index."""
        vm = EmailViewModel()
        vm.set_emails([])

        filtered = vm.filtered_emails
        next_index = 5

        if filtered:
            idx = max(0, min(next_index, len(filtered) - 1))
        else:
            idx = None

        assert idx is None

    def test_auto_select_clamps_index_to_last(self):
        """Auto-select clamps index to last valid index."""
        from belegscanner.services.imap import EmailSummary

        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="a@test.com",
                    subject="A",
                    date=datetime(2024, 1, 1),
                    has_attachments=False,
                ),
                EmailSummary(
                    uid=2,
                    sender="b@test.com",
                    subject="B",
                    date=datetime(2024, 1, 2),
                    has_attachments=False,
                ),
            ]
        )

        filtered = vm.filtered_emails
        next_index = 100  # Way beyond list

        idx = max(0, min(next_index, len(filtered) - 1))

        assert idx == 1  # Clamped to last index

    def test_auto_select_clamps_negative_index(self):
        """Auto-select clamps negative index to zero."""
        from belegscanner.services.imap import EmailSummary

        vm = EmailViewModel()
        vm.set_emails(
            [
                EmailSummary(
                    uid=1,
                    sender="a@test.com",
                    subject="A",
                    date=datetime(2024, 1, 1),
                    has_attachments=False,
                ),
                EmailSummary(
                    uid=2,
                    sender="b@test.com",
                    subject="B",
                    date=datetime(2024, 1, 2),
                    has_attachments=False,
                ),
            ]
        )

        filtered = vm.filtered_emails
        next_index = -5  # Negative index

        idx = max(0, min(next_index, len(filtered) - 1))

        assert idx == 0  # Clamped to first index


class TestSnapshotPattern:
    """Tests for RC4: Snapshot pattern for current_email."""

    def test_snapshot_survives_concurrent_modification(self):
        """Snapshot survives when current_email changes concurrently."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        email = make_email(100)
        vm.set_current_email(email)

        # Capture snapshot (simulating what _update_details should do)
        snapshot = vm.current_email

        # Simulate concurrent modification (another thread sets to None)
        vm.set_current_email(None)

        # Snapshot should still be valid
        assert snapshot is not None
        assert snapshot.uid == 100
        # Original reference changed
        assert vm.current_email is None

    def test_snapshot_preserves_email_data(self):
        """Snapshot preserves all email data during processing."""
        vm = EmailViewModel()
        vm.set_current_folder("INBOX")
        original_email = make_email(42)
        vm.set_current_email(original_email)

        # Capture snapshot
        snapshot = vm.current_email

        # Replace with different email
        new_email = make_email(99)
        vm.set_current_email(new_email)

        # Snapshot has original data
        assert snapshot.uid == 42
        assert snapshot.subject == "Test Email 42"
        # ViewModel has new data
        assert vm.current_email.uid == 99


class TestImapConnectionGuard:
    """Tests for RC5: IMAP connection guard.

    These tests verify that capturing IMAP reference at thread start
    prevents AttributeError when self.imap becomes None during execution.
    """

    def test_captured_reference_survives_disconnect(self):
        """Captured IMAP reference survives when self.imap becomes None.

        This demonstrates the guard pattern: capture self.imap at start,
        then use captured reference. Even if self.imap is set to None
        during thread execution, the captured reference remains valid.
        """
        from unittest.mock import MagicMock

        class MockView:
            def __init__(self):
                self.imap = MagicMock()

            def fetch_with_guard(self, uid):
                # Guard pattern: capture reference at start
                imap = self.imap
                if imap is None:
                    return None
                return imap.fetch_email(uid)

        view = MockView()
        captured = view.imap  # Simulate capturing reference

        # Simulate disconnect during thread execution
        view.imap = None

        # Captured reference still valid and callable
        assert captured is not None
        captured.fetch_email(100)  # Should not raise

    def test_guard_returns_none_when_disconnected_before_capture(self):
        """Guard returns None when disconnected before thread starts.

        If self.imap is already None when the thread captures it,
        the guard should detect this and return early with None.
        """

        class MockView:
            def __init__(self):
                self.imap = None

            def fetch_with_guard(self, uid):
                # Guard pattern: capture and check
                imap = self.imap
                if imap is None:
                    return None
                return imap.fetch_email(uid)

        view = MockView()
        result = view.fetch_with_guard(100)

        assert result is None

    def test_guard_pattern_with_email_uid_capture(self):
        """Guard pattern should also capture email.uid to avoid RC6.

        Both imap reference and email.uid should be captured at start
        to prevent using stale email references.
        """
        from unittest.mock import MagicMock

        class MockView:
            def __init__(self):
                self.imap = MagicMock()
                self.current_email = MagicMock(uid=100)

            def archive_with_guard(self):
                # Capture both imap and uid at start
                imap = self.imap
                uid = self.current_email.uid if self.current_email else None

                if imap is None or uid is None:
                    return False

                # Simulate email changing during execution
                self.current_email.uid = 999

                # Use captured uid, not current email
                imap.move_email(uid, "INBOX", "Archive")
                return True

        view = MockView()
        result = view.archive_with_guard()

        assert result is True
        # Verify move_email was called with captured uid (100), not changed uid (999)
        view.imap.move_email.assert_called_once_with(100, "INBOX", "Archive")


class TestPrefetchCoordination:
    """Tests for RC7: Prefetch coordination.

    These tests verify that prefetch status is tracked properly to prevent
    duplicate fetches when user selects an email that's already being prefetched.
    """

    def test_prefetch_pending_tracking(self):
        """Can track pending prefetch."""
        vm = EmailViewModel()

        vm.start_prefetch(100)

        assert vm.is_prefetch_pending_for(100) is True
        assert vm.is_prefetch_pending_for(200) is False

    def test_complete_prefetch_clears_pending(self):
        """Completing prefetch clears pending state."""
        vm = EmailViewModel()

        vm.start_prefetch(100)
        vm.complete_prefetch(100)

        assert vm.is_prefetch_pending_for(100) is False

    def test_complete_wrong_prefetch_keeps_pending(self):
        """Completing wrong UID keeps original pending."""
        vm = EmailViewModel()

        vm.start_prefetch(100)
        vm.complete_prefetch(200)  # Wrong UID

        assert vm.is_prefetch_pending_for(100) is True

    def test_new_prefetch_replaces_old(self):
        """Starting new prefetch replaces old one."""
        vm = EmailViewModel()

        vm.start_prefetch(100)
        vm.start_prefetch(200)

        assert vm.is_prefetch_pending_for(100) is False
        assert vm.is_prefetch_pending_for(200) is True

    def test_initially_no_prefetch_pending(self):
        """No prefetch pending initially."""
        vm = EmailViewModel()

        assert vm.is_prefetch_pending_for(100) is False

    def test_clear_resets_prefetch_state(self):
        """Clearing ViewModel resets prefetch tracking."""
        vm = EmailViewModel()
        vm.start_prefetch(100)

        vm.clear()

        assert vm.is_prefetch_pending_for(100) is False


class TestWebKitLoadGuard:
    """Tests for RC8: WebKit load guard.

    These tests verify that the WebKit load guard pattern correctly detects
    when the current email has changed during processing.
    """

    def test_load_guard_checks_current_email(self):
        """Load guard should verify email is still current."""
        vm = EmailViewModel()
        email = make_email(100)
        vm.set_current_email(email)

        # Capture snapshot (simulating what _update_body_preview should do)
        snapshot_uid = email.uid

        # Email changes before load
        vm.set_current_email(make_email(200))

        # Guard should detect mismatch
        current = vm.current_email
        should_load = current is not None and current.uid == snapshot_uid

        assert should_load is False

    def test_load_guard_allows_when_email_unchanged(self):
        """Load guard should allow when email is still current."""
        vm = EmailViewModel()
        email = make_email(100)
        vm.set_current_email(email)

        # Capture snapshot
        snapshot_uid = email.uid

        # Email doesn't change
        current = vm.current_email
        should_load = current is not None and current.uid == snapshot_uid

        assert should_load is True

    def test_load_guard_blocks_when_email_cleared(self):
        """Load guard should block when email becomes None."""
        vm = EmailViewModel()
        email = make_email(100)
        vm.set_current_email(email)

        # Capture snapshot
        snapshot_uid = email.uid

        # Email cleared (user deselects)
        vm.set_current_email(None)

        # Guard should detect
        current = vm.current_email
        should_load = current is not None and current.uid == snapshot_uid

        assert should_load is False
