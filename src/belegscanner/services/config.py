"""Configuration management for Belegscanner."""

from pathlib import Path

from belegscanner.constants import DEFAULT_CONFIG_PATH


class ConfigManager:
    """Manages belegscanner configuration file.

    The config file is a simple key=value format:
        # Belegscanner Konfiguration
        ABLAGE_PFAD=/path/to/archive

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
        self._archive_path: str | None = None
        self._loaded = False

    def load(self) -> str | None:
        """Load archive path from config file.

        Returns:
            Archive path if config exists and contains ABLAGE_PFAD, None otherwise.
        """
        if not self._config_path.exists():
            return None

        for line in self._config_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("ABLAGE_PFAD="):
                return line.split("=", 1)[1].strip()

        return None

    def save(self, archive_path: str) -> None:
        """Save archive path to config file.

        Creates parent directories if needed.

        Args:
            archive_path: Path to archive directory.
        """
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"# Belegscanner Konfiguration\nABLAGE_PFAD={archive_path}\n"
        self._config_path.write_text(content)

    @property
    def archive_path(self) -> str | None:
        """Get archive path, loading from file on first access.

        Returns:
            Cached archive path, or None if not configured.
        """
        if not self._loaded:
            self._archive_path = self.load()
            self._loaded = True
        return self._archive_path

    @archive_path.setter
    def archive_path(self, value: str) -> None:
        """Set archive path, saving to file and updating cache.

        Args:
            value: New archive path.
        """
        self.save(value)
        self._archive_path = value
        self._loaded = True
