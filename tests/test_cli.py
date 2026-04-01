"""Tests for CLI interface."""

from unittest.mock import patch

import pytest

from belegscanner.cli import main


class TestCliArgumentParsing:
    def test_requires_kategorie_argument(self):
        """CLI should fail without --kategorie."""
        with patch("sys.argv", ["scan-beleg"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse error

    def test_rejects_invalid_kategorie(self):
        """CLI should reject kategorie outside 1-4."""
        with patch("sys.argv", ["scan-beleg", "-k", "5"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2

    def test_accepts_valid_kategorie(self):
        """CLI should accept kategorie 1-4 (will fail at scanner check)."""
        with (
            patch("sys.argv", ["scan-beleg", "-k", "1"]),
            patch("belegscanner.cli.ConfigManager") as mock_config,
            patch("belegscanner.cli.ScannerService") as mock_scanner,
        ):
            mock_config.return_value.archive_path = "/tmp/test"
            mock_scanner.return_value.is_available.return_value = False
            result = main()
            assert result == 1  # fails at scanner check, not argument parsing


class TestCliNoScanner:
    def test_returns_error_when_no_scanner(self):
        with (
            patch("sys.argv", ["scan-beleg", "-k", "1"]),
            patch("belegscanner.cli.ConfigManager") as mock_config,
            patch("belegscanner.cli.ScannerService") as mock_scanner,
        ):
            mock_config.return_value.archive_path = "/tmp/test"
            mock_scanner.return_value.is_available.return_value = False
            assert main() == 1


class TestCliNoArchivePath:
    def test_returns_error_when_no_archive_path(self):
        with (
            patch("sys.argv", ["scan-beleg", "-k", "1"]),
            patch("belegscanner.cli.ConfigManager") as mock_config,
        ):
            mock_config.return_value.archive_path = None
            assert main() == 1
