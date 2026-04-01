"""Configuration management for Belegscanner."""

from pathlib import Path

from belegscanner.constants import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_IMAP_ARCHIVE,
    DEFAULT_IMAP_INBOX,
)


class ConfigManager:
    """Manages belegscanner configuration file.

    The config file is a simple key=value format:
        # Belegscanner Konfiguration
        ABLAGE_PFAD=/path/to/archive
        IMAP_SERVER=imap.example.com
        IMAP_USER=user@example.com
        IMAP_INBOX=Rechnungseingang
        IMAP_ARCHIVE=Rechnungseingang/archiviert

    Usage:
        manager = ConfigManager()
        path = manager.archive_path  # Loads and caches
        manager.archive_path = "/new/path"  # Saves and updates cache
    """

    def __init__(self, config_path: Path | None = None):
        """Initialize with optional custom config path.

        Args:
            config_path: Path to config file. Defaults to ~/.config/belegscanner.conf
        """
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        self._cache: dict[str, str | None] = {}
        self._loaded = False

    def _load_all(self) -> dict[str, str]:
        """Load all config values from file.

        Returns:
            Dictionary of key-value pairs from config file.
        """
        if not self._config_path.exists():
            return {}

        values = {}
        for line in self._config_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return values

    def _ensure_loaded(self) -> None:
        """Ensure config is loaded into cache."""
        if not self._loaded:
            values = self._load_all()
            self._cache = {
                "ABLAGE_PFAD": values.get("ABLAGE_PFAD"),
                "IMAP_SERVER": values.get("IMAP_SERVER"),
                "IMAP_USER": values.get("IMAP_USER"),
                "IMAP_INBOX": values.get("IMAP_INBOX"),
                "IMAP_ARCHIVE": values.get("IMAP_ARCHIVE"),
            }
            self._loaded = True

    def _save_all(self) -> None:
        """Save all cached config values to file."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["# Belegscanner Konfiguration"]
        for key, value in self._cache.items():
            if value is not None:
                lines.append(f"{key}={value}")

        self._config_path.write_text("\n".join(lines) + "\n")

    def _get_value(self, key: str, default: str | None = None) -> str | None:
        """Get a config value.

        Args:
            key: Config key to retrieve.
            default: Default value if not set.

        Returns:
            Config value or default.
        """
        self._ensure_loaded()
        value = self._cache.get(key)
        return value if value is not None else default

    def _set_value(self, key: str, value: str) -> None:
        """Set a config value and save to file.

        Args:
            key: Config key to set.
            value: Value to store.
        """
        self._ensure_loaded()
        self._cache[key] = value
        self._save_all()

    def load(self) -> str | None:
        """Load archive path from config file.

        Returns:
            Archive path if config exists and contains ABLAGE_PFAD, None otherwise.
        """
        return self._get_value("ABLAGE_PFAD")

    def save(self, archive_path: str) -> None:
        """Save archive path to config file.

        Creates parent directories if needed.

        Args:
            archive_path: Path to archive directory.
        """
        self._set_value("ABLAGE_PFAD", archive_path)

    @property
    def archive_path(self) -> str | None:
        """Get archive path, loading from file on first access."""
        return self._get_value("ABLAGE_PFAD")

    @archive_path.setter
    def archive_path(self, value: str) -> None:
        """Set archive path, saving to file and updating cache."""
        self._set_value("ABLAGE_PFAD", value)

    @property
    def imap_server(self) -> str | None:
        """Get IMAP server address."""
        return self._get_value("IMAP_SERVER")

    @imap_server.setter
    def imap_server(self, value: str) -> None:
        """Set IMAP server address."""
        self._set_value("IMAP_SERVER", value)

    @property
    def imap_user(self) -> str | None:
        """Get IMAP username/email."""
        return self._get_value("IMAP_USER")

    @imap_user.setter
    def imap_user(self, value: str) -> None:
        """Set IMAP username/email."""
        self._set_value("IMAP_USER", value)

    @property
    def imap_inbox(self) -> str:
        """Get IMAP inbox folder name (default: Rechnungseingang)."""
        return self._get_value("IMAP_INBOX", DEFAULT_IMAP_INBOX) or DEFAULT_IMAP_INBOX

    @imap_inbox.setter
    def imap_inbox(self, value: str) -> None:
        """Set IMAP inbox folder name."""
        self._set_value("IMAP_INBOX", value)

    @property
    def imap_archive(self) -> str:
        """Get IMAP archive folder name (default: Rechnungseingang/archiviert)."""
        return self._get_value("IMAP_ARCHIVE", DEFAULT_IMAP_ARCHIVE) or DEFAULT_IMAP_ARCHIVE

    @imap_archive.setter
    def imap_archive(self, value: str) -> None:
        """Set IMAP archive folder name."""
        self._set_value("IMAP_ARCHIVE", value)

    def is_email_configured(self) -> bool:
        """Check if email configuration is complete.

        Returns:
            True if both IMAP server and user are set and non-empty.
        """
        server = self.imap_server
        user = self.imap_user
        return bool(server and user)
