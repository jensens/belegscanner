"""Tests for ConfigManager service."""

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


class TestConfigManagerImap:
    """Test IMAP configuration fields."""

    def test_imap_server_returns_none_when_not_set(self, config_file: Path):
        """imap_server returns None when not configured."""
        config_file.write_text("ABLAGE_PFAD=/archive\n")
        manager = ConfigManager(config_file)

        assert manager.imap_server is None

    def test_imap_server_reads_from_config(self, config_file: Path):
        """imap_server reads value from config file."""
        config_file.write_text("ABLAGE_PFAD=/archive\nIMAP_SERVER=imap.example.com\n")
        manager = ConfigManager(config_file)

        assert manager.imap_server == "imap.example.com"

    def test_imap_server_setter_saves_to_file(self, config_file: Path):
        """Setting imap_server saves to file."""
        config_file.write_text("ABLAGE_PFAD=/archive\n")
        manager = ConfigManager(config_file)

        manager.imap_server = "mail.test.com"

        assert "IMAP_SERVER=mail.test.com" in config_file.read_text()

    def test_imap_user_returns_none_when_not_set(self, config_file: Path):
        """imap_user returns None when not configured."""
        config_file.write_text("ABLAGE_PFAD=/archive\n")
        manager = ConfigManager(config_file)

        assert manager.imap_user is None

    def test_imap_user_reads_from_config(self, config_file: Path):
        """imap_user reads value from config file."""
        config_file.write_text("ABLAGE_PFAD=/archive\nIMAP_USER=user@example.com\n")
        manager = ConfigManager(config_file)

        assert manager.imap_user == "user@example.com"

    def test_imap_user_setter_saves_to_file(self, config_file: Path):
        """Setting imap_user saves to file."""
        config_file.write_text("ABLAGE_PFAD=/archive\n")
        manager = ConfigManager(config_file)

        manager.imap_user = "test@mail.com"

        assert "IMAP_USER=test@mail.com" in config_file.read_text()

    def test_imap_inbox_returns_default_when_not_set(self, config_file: Path):
        """imap_inbox returns default value when not configured."""
        config_file.write_text("ABLAGE_PFAD=/archive\n")
        manager = ConfigManager(config_file)

        assert manager.imap_inbox == "Rechnungseingang"

    def test_imap_inbox_reads_from_config(self, config_file: Path):
        """imap_inbox reads value from config file."""
        config_file.write_text("ABLAGE_PFAD=/archive\nIMAP_INBOX=Invoices\n")
        manager = ConfigManager(config_file)

        assert manager.imap_inbox == "Invoices"

    def test_imap_inbox_setter_saves_to_file(self, config_file: Path):
        """Setting imap_inbox saves to file."""
        config_file.write_text("ABLAGE_PFAD=/archive\n")
        manager = ConfigManager(config_file)

        manager.imap_inbox = "Bills"

        assert "IMAP_INBOX=Bills" in config_file.read_text()

    def test_imap_archive_returns_default_when_not_set(self, config_file: Path):
        """imap_archive returns default value when not configured."""
        config_file.write_text("ABLAGE_PFAD=/archive\n")
        manager = ConfigManager(config_file)

        assert manager.imap_archive == "Rechnungseingang/archiviert"

    def test_imap_archive_reads_from_config(self, config_file: Path):
        """imap_archive reads value from config file."""
        config_file.write_text("ABLAGE_PFAD=/archive\nIMAP_ARCHIVE=Invoices/Done\n")
        manager = ConfigManager(config_file)

        assert manager.imap_archive == "Invoices/Done"

    def test_imap_archive_setter_saves_to_file(self, config_file: Path):
        """Setting imap_archive saves to file."""
        config_file.write_text("ABLAGE_PFAD=/archive\n")
        manager = ConfigManager(config_file)

        manager.imap_archive = "Bills/Processed"

        assert "IMAP_ARCHIVE=Bills/Processed" in config_file.read_text()

    def test_save_preserves_existing_values(self, config_file: Path):
        """Setting one IMAP field preserves other existing values."""
        config_file.write_text(
            "ABLAGE_PFAD=/archive\nIMAP_SERVER=old.server.com\nIMAP_USER=old@user.com\n"
        )
        manager = ConfigManager(config_file)

        manager.imap_server = "new.server.com"

        content = config_file.read_text()
        assert "IMAP_SERVER=new.server.com" in content
        assert "IMAP_USER=old@user.com" in content
        assert "ABLAGE_PFAD=/archive" in content


class TestConfigManagerIsEmailConfigured:
    """Test is_email_configured() method."""

    def test_returns_false_when_no_config_file(self, config_file: Path):
        """is_email_configured returns False when config file doesn't exist."""
        manager = ConfigManager(config_file)

        assert manager.is_email_configured() is False

    def test_returns_false_when_only_server_set(self, config_file: Path):
        """is_email_configured returns False when only server is set."""
        config_file.write_text("IMAP_SERVER=imap.example.com\n")
        manager = ConfigManager(config_file)

        assert manager.is_email_configured() is False

    def test_returns_false_when_only_user_set(self, config_file: Path):
        """is_email_configured returns False when only user is set."""
        config_file.write_text("IMAP_USER=user@example.com\n")
        manager = ConfigManager(config_file)

        assert manager.is_email_configured() is False

    def test_returns_true_when_server_and_user_set(self, config_file: Path):
        """is_email_configured returns True when server and user are set."""
        config_file.write_text("IMAP_SERVER=imap.example.com\nIMAP_USER=user@example.com\n")
        manager = ConfigManager(config_file)

        assert manager.is_email_configured() is True

    def test_returns_false_when_server_empty(self, config_file: Path):
        """is_email_configured returns False when server is empty string."""
        config_file.write_text("IMAP_SERVER=\nIMAP_USER=user@example.com\n")
        manager = ConfigManager(config_file)

        assert manager.is_email_configured() is False

    def test_returns_false_when_user_empty(self, config_file: Path):
        """is_email_configured returns False when user is empty string."""
        config_file.write_text("IMAP_SERVER=imap.example.com\nIMAP_USER=\n")
        manager = ConfigManager(config_file)

        assert manager.is_email_configured() is False
