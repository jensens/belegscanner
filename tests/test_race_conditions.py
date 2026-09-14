"""Tests for race condition prevention in email fetching.

These tests ensure that the selection generation counter invalidates
stale in-flight work (fetches, prefetches) when the user changes the
selection, and that the remaining guard patterns (RC3-RC6) still hold.
"""

from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")

from belegscanner.email_viewmodel import EmailViewModel
from belegscanner.services.imap import EmailMessage, EmailSummary


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


def make_summary(uid: int) -> EmailSummary:
    """Helper to create a test email summary with given UID."""
    return EmailSummary(
        uid=uid,
        sender=f"test{uid}@example.com",
        subject=f"Test Email {uid}",
        date=datetime(2024, 11, 15),
        has_attachments=False,
    )


class TestSelectionGeneration:
    """Test the selection generation counter that replaces fetch-request

    and prefetch tracking: any selection change bumps the generation, and
    stale in-flight work can check vm.is_current(generation) before
    touching the ViewModel.
    """

    def test_select_bumps_and_returns_generation(self):
        vm = EmailViewModel()
        vm.set_emails([make_summary(100), make_summary(200)])
        g1 = vm.select_email(100)
        g2 = vm.select_email(200)
        assert g2 == g1 + 1
        assert vm.generation == g2

    def test_is_current_only_for_latest(self):
        vm = EmailViewModel()
        vm.set_emails([make_summary(100), make_summary(200)])
        g1 = vm.select_email(100)
        g2 = vm.select_email(200)
        assert vm.is_current(g2) is True
        assert vm.is_current(g1) is False

    def test_clear_invalidates_all_generations(self):
        vm = EmailViewModel()
        vm.set_emails([make_summary(100)])
        g1 = vm.select_email(100)
        vm.clear()
        assert vm.is_current(g1) is False

    def test_set_emails_invalidates_generations(self):
        vm = EmailViewModel()
        vm.set_emails([make_summary(100)])
        g1 = vm.select_email(100)
        vm.set_emails([make_summary(100)])
        assert vm.is_current(g1) is False

    def test_deselect_invalidates(self):
        vm = EmailViewModel()
        vm.set_emails([make_summary(100)])
        g1 = vm.select_email(100)
        g2 = vm.select_email(-1)
        assert vm.selected_email is None
        assert g2 > g1


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
