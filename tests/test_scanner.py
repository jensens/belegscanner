"""Tests for ScannerService."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

from belegscanner.services.scanner import ScannerService


class TestScanPage:
    """Test single page scanning."""

    @patch("belegscanner.services.scanner.subprocess.run")
    def test_calls_scanimage_with_correct_args(self, mock_run: MagicMock, tmp_path: Path):
        """Call scanimage with correct parameters."""
        service = ScannerService()
        output_path = tmp_path / "scan.png"

        mock_run.return_value = MagicMock(returncode=0)

        service.scan_page(output_path)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "scanimage"
        assert "--mode" in call_args
        assert "True Gray" in call_args
        assert "--resolution" in call_args
        assert "300" in call_args
        assert "--format" in call_args
        assert "png" in call_args
        assert "-o" in call_args
        assert str(output_path) in call_args

    @patch("belegscanner.services.scanner.subprocess.run")
    def test_returns_true_on_success(self, mock_run: MagicMock, tmp_path: Path):
        """Return True when scan succeeds."""
        service = ScannerService()
        output_path = tmp_path / "scan.png"

        mock_run.return_value = MagicMock(returncode=0)

        result = service.scan_page(output_path)

        assert result is True

    @patch("belegscanner.services.scanner.subprocess.run")
    def test_returns_false_on_failure(self, mock_run: MagicMock, tmp_path: Path):
        """Return False when scan fails."""
        service = ScannerService()
        output_path = tmp_path / "scan.png"

        mock_run.side_effect = subprocess.CalledProcessError(1, "scanimage")

        result = service.scan_page(output_path)

        assert result is False

    @patch("belegscanner.services.scanner.subprocess.run")
    def test_uses_custom_resolution(self, mock_run: MagicMock, tmp_path: Path):
        """Use custom resolution when specified."""
        service = ScannerService(resolution=600)
        output_path = tmp_path / "scan.png"

        mock_run.return_value = MagicMock(returncode=0)

        service.scan_page(output_path)

        call_args = mock_run.call_args[0][0]
        assert "600" in call_args

    @patch("belegscanner.services.scanner.subprocess.run")
    def test_uses_custom_mode(self, mock_run: MagicMock, tmp_path: Path):
        """Use custom mode when specified."""
        service = ScannerService(mode="Color")
        output_path = tmp_path / "scan.png"

        mock_run.return_value = MagicMock(returncode=0)

        service.scan_page(output_path)

        call_args = mock_run.call_args[0][0]
        assert "Color" in call_args


class TestScannerAvailable:
    """Test scanner availability check."""

    @patch("belegscanner.services.scanner.subprocess.run")
    def test_returns_true_when_scanner_found(self, mock_run: MagicMock):
        """Return True when scanner is available."""
        service = ScannerService()

        mock_run.return_value = MagicMock(returncode=0, stdout="device `brother' found")

        result = service.is_available()

        assert result is True

    @patch("belegscanner.services.scanner.subprocess.run")
    def test_returns_false_when_no_scanner(self, mock_run: MagicMock):
        """Return False when no scanner found."""
        service = ScannerService()

        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = service.is_available()

        assert result is False

    @patch("belegscanner.services.scanner.subprocess.run")
    def test_returns_false_on_error(self, mock_run: MagicMock):
        """Return False when scanimage command fails."""
        service = ScannerService()

        mock_run.side_effect = subprocess.CalledProcessError(1, "scanimage")

        result = service.is_available()

        assert result is False
