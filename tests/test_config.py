"""Tests for ConfigManager service."""

import pytest
from pathlib import Path

from belegscanner.services.config import ConfigManager


class TestConfigManager:
    """Test ConfigManager functionality."""

    def test_load_returns_none_when_no_config(self, config_file: Path):
        """Load returns None when config file doesn't exist."""
        manager = ConfigManager(config_file)
        assert manager.load() is None

    def test_load_reads_existing_config(self, config_file: Path):
        """Load reads archive path from existing config."""
        config_file.write_text("# Config\nABLAGE_PFAD=/home/test/archive\n")
        manager = ConfigManager(config_file)

        result = manager.load()

        assert result == "/home/test/archive"

    def test_load_ignores_comments_and_empty_lines(self, config_file: Path):
        """Load ignores comments and empty lines."""
        config_file.write_text("# Comment\n\nABLAGE_PFAD=/path/to/archive\n# Another\n")
        manager = ConfigManager(config_file)

        result = manager.load()

        assert result == "/path/to/archive"

    def test_load_handles_spaces_around_value(self, config_file: Path):
        """Load trims whitespace from path value."""
        config_file.write_text("ABLAGE_PFAD=  /path/with/spaces  \n")
        manager = ConfigManager(config_file)

        result = manager.load()

        assert result == "/path/with/spaces"

    def test_save_creates_config_file(self, config_file: Path):
        """Save creates config file with archive path."""
        manager = ConfigManager(config_file)

        manager.save("/home/user/nextcloud/finanzen")

        assert config_file.exists()
        content = config_file.read_text()
        assert "ABLAGE_PFAD=/home/user/nextcloud/finanzen" in content

    def test_save_creates_parent_directories(self, tmp_path: Path):
        """Save creates parent directories if they don't exist."""
        nested_config = tmp_path / "deep" / "nested" / "belegscanner.conf"
        manager = ConfigManager(nested_config)

        manager.save("/some/path")

        assert nested_config.exists()

    def test_save_adds_header_comment(self, config_file: Path):
        """Save adds a descriptive header comment."""
        manager = ConfigManager(config_file)

        manager.save("/some/path")

        content = config_file.read_text()
        assert content.startswith("# Belegscanner")

    def test_archive_path_property_loads_on_first_access(self, config_file: Path):
        """archive_path property loads config on first access."""
        config_file.write_text("ABLAGE_PFAD=/cached/path\n")
        manager = ConfigManager(config_file)

        # First access loads
        path = manager.archive_path

        assert path == "/cached/path"

    def test_archive_path_property_caches_value(self, config_file: Path):
        """archive_path property caches the loaded value."""
        config_file.write_text("ABLAGE_PFAD=/original/path\n")
        manager = ConfigManager(config_file)

        # Load once
        _ = manager.archive_path

        # Modify file
        config_file.write_text("ABLAGE_PFAD=/modified/path\n")

        # Should still return cached value
        assert manager.archive_path == "/original/path"

    def test_archive_path_setter_saves_and_caches(self, config_file: Path):
        """Setting archive_path saves to file and updates cache."""
        manager = ConfigManager(config_file)

        manager.archive_path = "/new/path"

        assert manager.archive_path == "/new/path"
        assert "ABLAGE_PFAD=/new/path" in config_file.read_text()
