"""Tests for EmailCache."""

from datetime import datetime

from belegscanner.services.email_cache import EmailCache
from belegscanner.services.imap import EmailMessage


def make_email(uid: int, subject: str = "Test") -> EmailMessage:
    """Create a test EmailMessage."""
    return EmailMessage(
        uid=uid,
        sender="test@example.com",
        subject=subject,
        date=datetime.now(),
        message_id=f"<{uid}@example.com>",
        body_text="Test body",
        body_html=None,
        attachments=[],
    )


class TestEmailCache:
    """Tests for EmailCache class."""

    def test_get_returns_none_for_missing(self):
        """Cache returns None for non-existent email."""
        cache = EmailCache()
        assert cache.get("INBOX", 123) is None

    def test_put_and_get(self):
        """Stored email can be retrieved."""
        cache = EmailCache()
        email = make_email(123, "Test Subject")

        cache.put("INBOX", 123, email)
        result = cache.get("INBOX", 123)

        assert result is not None
        assert result.uid == 123
        assert result.subject == "Test Subject"

    def test_get_different_folder_returns_none(self):
        """Same UID in different folder is not found."""
        cache = EmailCache()
        email = make_email(123)

        cache.put("INBOX", 123, email)

        assert cache.get("Archive", 123) is None

    def test_remove_deletes_entry(self):
        """Remove deletes email from cache."""
        cache = EmailCache()
        email = make_email(123)

        cache.put("INBOX", 123, email)
        cache.remove("INBOX", 123)

        assert cache.get("INBOX", 123) is None

    def test_remove_nonexistent_does_not_raise(self):
        """Remove on non-existent entry does not raise."""
        cache = EmailCache()
        cache.remove("INBOX", 999)  # Should not raise

    def test_clear_empties_cache(self):
        """Clear removes all entries."""
        cache = EmailCache()
        cache.put("INBOX", 1, make_email(1))
        cache.put("INBOX", 2, make_email(2))
        cache.put("Archive", 3, make_email(3))

        cache.clear()

        assert cache.get("INBOX", 1) is None
        assert cache.get("INBOX", 2) is None
        assert cache.get("Archive", 3) is None

    def test_contains_returns_true_for_cached(self):
        """Contains returns True for cached email."""
        cache = EmailCache()
        email = make_email(123)

        cache.put("INBOX", 123, email)

        assert cache.contains("INBOX", 123) is True
        assert cache.contains("INBOX", 999) is False
        assert cache.contains("Archive", 123) is False

    def test_max_size_evicts_oldest(self):
        """When max_size reached, oldest entries are evicted."""
        cache = EmailCache(max_size=3)

        cache.put("INBOX", 1, make_email(1))
        cache.put("INBOX", 2, make_email(2))
        cache.put("INBOX", 3, make_email(3))
        # Cache is full now

        cache.put("INBOX", 4, make_email(4))
        # Oldest (1) should be evicted

        assert cache.get("INBOX", 1) is None
        assert cache.get("INBOX", 2) is not None
        assert cache.get("INBOX", 3) is not None
        assert cache.get("INBOX", 4) is not None

    def test_lru_updates_on_access(self):
        """Accessing entry updates its recency (LRU behavior)."""
        cache = EmailCache(max_size=3)

        cache.put("INBOX", 1, make_email(1))
        cache.put("INBOX", 2, make_email(2))
        cache.put("INBOX", 3, make_email(3))

        # Access email 1 to make it recent
        cache.get("INBOX", 1)

        # Add new email - should evict 2 (oldest after access)
        cache.put("INBOX", 4, make_email(4))

        assert cache.get("INBOX", 1) is not None  # Recently accessed
        assert cache.get("INBOX", 2) is None  # Evicted
        assert cache.get("INBOX", 3) is not None
        assert cache.get("INBOX", 4) is not None

    def test_size_property(self):
        """Size property returns current cache size."""
        cache = EmailCache()

        assert cache.size == 0

        cache.put("INBOX", 1, make_email(1))
        assert cache.size == 1

        cache.put("INBOX", 2, make_email(2))
        assert cache.size == 2

        cache.remove("INBOX", 1)
        assert cache.size == 1

        cache.clear()
        assert cache.size == 0
