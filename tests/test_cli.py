"""Tests for CLI interface."""

import logging
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


class TestCliVerbosity:
    @pytest.mark.parametrize(
        "extra_args, expected_level",
        [([], logging.WARNING), (["-v"], logging.INFO), (["-vv"], logging.DEBUG)],
        ids=["default", "verbose", "debug"],
    )
    def test_verbose_flags_configure_logging(self, extra_args, expected_level):
        with (
            patch("sys.argv", ["scan-beleg", "-k", "1", *extra_args]),
            patch("belegscanner.cli.setup_logging") as mock_setup,
            patch("belegscanner.cli.ConfigManager") as mock_config,
        ):
            mock_config.return_value.archive_path = None
            main()
            mock_setup.assert_called_once_with(expected_level)

    @pytest.mark.parametrize(
        "extra_args, expected_level",
        [([], logging.WARNING), (["-v"], logging.INFO), (["-vv"], logging.DEBUG)],
        ids=["default", "verbose", "debug"],
    )
    def test_gui_flag_passes_level_to_app_main(self, extra_args, expected_level):
        with (
            patch("sys.argv", ["scan-beleg", "-k", "1", "--gui", *extra_args]),
            patch("belegscanner.cli.setup_logging"),
            patch("belegscanner.app.main") as mock_gui_main,
        ):
            mock_gui_main.return_value = 0
            main()
            mock_gui_main.assert_called_once_with(level=expected_level)
