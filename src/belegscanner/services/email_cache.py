"""Email cache for storing fetched emails."""

import threading
from collections import OrderedDict

from belegscanner.services.imap import EmailMessage


class EmailCache:
    """LRU cache for EmailMessage objects.

    Thread-safe cache using OrderedDict for LRU eviction.
    Keys are (folder, uid) tuples.

    Usage:
        cache = EmailCache(max_size=20)
        cache.put("INBOX", 123, email)
        email = cache.get("INBOX", 123)
    """

    def __init__(self, max_size: int = 20):
        """Initialize cache.

        Args:
            max_size: Maximum number of emails to cache.
        """
        self._max_size = max_size
        self._cache: OrderedDict[tuple[str, int], EmailMessage] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        """Return current cache size."""
        with self._lock:
            return len(self._cache)

    def get(self, folder: str, uid: int) -> EmailMessage | None:
        """Get email from cache.

        Accessing an entry moves it to the end (most recently used).

        Args:
            folder: IMAP folder name.
            uid: Email UID.

        Returns:
            EmailMessage if found, None otherwise.
        """
        key = (folder, uid)
        with self._lock:
            if key not in self._cache:
                return None
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, folder: str, uid: int, email: EmailMessage) -> None:
        """Store email in cache.

        If cache is full, evicts least recently used entry.

        Args:
            folder: IMAP folder name.
            uid: Email UID.
            email: EmailMessage to cache.
        """
        key = (folder, uid)
        with self._lock:
            # If key exists, remove it first to update position
            if key in self._cache:
                del self._cache[key]
            # Add at end (most recently used)
            self._cache[key] = email
            # Evict oldest if over max_size
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def remove(self, folder: str, uid: int) -> None:
        """Remove email from cache.

        Args:
            folder: IMAP folder name.
            uid: Email UID.
        """
        key = (folder, uid)
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._cache.clear()

    def contains(self, folder: str, uid: int) -> bool:
        """Check if email is in cache.

        Args:
            folder: IMAP folder name.
            uid: Email UID.

        Returns:
            True if email is cached.
        """
        key = (folder, uid)
        with self._lock:
            return key in self._cache
