"""Tests for PdfService."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from belegscanner.services.pdf import PdfService


class TestCreatePdf:
    """Test PDF creation with OCR."""

    @patch("belegscanner.services.pdf.subprocess.run")
    def test_calls_convert_to_create_pdf(self, mock_run: MagicMock, tmp_path: Path):
        """Call ImageMagick convert to create PDF from images."""
        service = PdfService()
        pages = [tmp_path / "page1.png", tmp_path / "page2.png"]
        for p in pages:
            p.touch()
        output = tmp_path / "output.pdf"

        mock_run.return_value = MagicMock(returncode=0)

        service.create_pdf(pages, output)

        # First call should be convert
        first_call = mock_run.call_args_list[0]
        assert first_call[0][0][0] == "convert"

    @patch("belegscanner.services.pdf.subprocess.run")
    def test_calls_ocrmypdf_with_correct_args(self, mock_run: MagicMock, tmp_path: Path):
        """Call ocrmypdf with German language and cleanup options."""
        service = PdfService()
        page = tmp_path / "page.png"
        page.touch()
        output = tmp_path / "output.pdf"

        mock_run.return_value = MagicMock(returncode=0)

        service.create_pdf([page], output)

        # Second call should be ocrmypdf
        assert len(mock_run.call_args_list) >= 2
        ocrmypdf_call = mock_run.call_args_list[1]
        args = ocrmypdf_call[0][0]

        assert args[0] == "ocrmypdf"
        assert "--language" in args
        assert "deu" in args
        assert "--deskew" in args
        assert "--clean" in args

    @patch("belegscanner.services.pdf.subprocess.run")
    def test_returns_true_on_success(self, mock_run: MagicMock, tmp_path: Path):
        """Return True when PDF creation succeeds."""
        service = PdfService()
        page = tmp_path / "page.png"
        page.touch()
        output = tmp_path / "output.pdf"

        mock_run.return_value = MagicMock(returncode=0)

        result = service.create_pdf([page], output)

        assert result is True

    @patch("belegscanner.services.pdf.subprocess.run")
    def test_returns_false_on_convert_failure(self, mock_run: MagicMock, tmp_path: Path):
        """Return False when convert fails."""
        service = PdfService()
        page = tmp_path / "page.png"
        page.touch()
        output = tmp_path / "output.pdf"

        mock_run.side_effect = subprocess.CalledProcessError(1, "convert")

        result = service.create_pdf([page], output)

        assert result is False

    @patch("belegscanner.services.pdf.subprocess.run")
    def test_returns_false_on_ocrmypdf_failure(self, mock_run: MagicMock, tmp_path: Path):
        """Return False when ocrmypdf fails."""
        service = PdfService()
        page = tmp_path / "page.png"
        page.touch()
        output = tmp_path / "output.pdf"

        # First call (convert) succeeds, second (ocrmypdf) fails
        mock_run.side_effect = [
            MagicMock(returncode=0),
            subprocess.CalledProcessError(1, "ocrmypdf"),
        ]

        result = service.create_pdf([page], output)

        assert result is False

    @patch("belegscanner.services.pdf.os.path.exists")
    @patch("belegscanner.services.pdf.os.remove")
    @patch("belegscanner.services.pdf.subprocess.run")
    def test_cleans_up_temp_pdf(
        self, mock_run: MagicMock, mock_remove: MagicMock, mock_exists: MagicMock, tmp_path: Path
    ):
        """Remove temporary PDF after ocrmypdf processing."""
        service = PdfService()
        page = tmp_path / "page.png"
        page.touch()
        output = tmp_path / "output.pdf"

        mock_run.return_value = MagicMock(returncode=0)
        mock_exists.return_value = True

        service.create_pdf([page], output)

        # Should remove the temp PDF
        assert mock_remove.called
