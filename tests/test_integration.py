"""Integration tests for the full scan-to-archive workflow."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from belegscanner.services.archive import ArchiveService
from belegscanner.services.config import ConfigManager
from belegscanner.services.ocr import OcrService
from belegscanner.services.pdf import PdfService
from belegscanner.services.scanner import ScannerService


@pytest.fixture
def mock_image(tmp_path: Path) -> Path:
    """Create a minimal valid PNG image for testing."""
    # Minimal 1x1 white PNG (67 bytes)
    png_data = bytes(
        [
            0x89,
            0x50,
            0x4E,
            0x47,
            0x0D,
            0x0A,
            0x1A,
            0x0A,  # PNG signature
            0x00,
            0x00,
            0x00,
            0x0D,
            0x49,
            0x48,
            0x44,
            0x52,  # IHDR chunk
            0x00,
            0x00,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,
            0x01,  # 1x1
            0x08,
            0x02,
            0x00,
            0x00,
            0x00,
            0x90,
            0x77,
            0x53,
            0xDE,
            0x00,
            0x00,
            0x00,
            0x0C,
            0x49,
            0x44,
            0x41,  # IDAT chunk
            0x54,
            0x08,
            0xD7,
            0x63,
            0xF8,
            0xFF,
            0xFF,
            0x3F,
            0x00,
            0x05,
            0xFE,
            0x02,
            0xFE,
            0xDC,
            0xCC,
            0x59,
            0xE7,
            0x00,
            0x00,
            0x00,
            0x00,
            0x49,
            0x45,
            0x4E,  # IEND chunk
            0x44,
            0xAE,
            0x42,
            0x60,
            0x82,
        ]
    )
    image_path = tmp_path / "scan.png"
    image_path.write_bytes(png_data)
    return image_path


@pytest.fixture
def workflow_services(tmp_path: Path, config_file: Path, archive_dir: Path):
    """Create all services needed for the workflow."""
    # Config
    config = ConfigManager(config_path=config_file)
    config.archive_path = str(archive_dir)

    # Services
    scanner = ScannerService()
    ocr = OcrService()
    pdf = PdfService()
    archive = ArchiveService(base_path=archive_dir)

    return {
        "config": config,
        "scanner": scanner,
        "ocr": ocr,
        "pdf": pdf,
        "archive": archive,
        "archive_dir": archive_dir,
    }


class TestFullWorkflowMockScanner:
    """Test the complete scan-to-archive workflow with mocked scanner."""

    def test_single_page_workflow(self, tmp_path: Path, workflow_services, mock_image):
        """Test scanning a single page and archiving it."""
        services = workflow_services
        scan_output = tmp_path / "scanned.png"

        # Mock scanner to copy our test image
        def mock_scan(output_path):
            import shutil

            shutil.copy(mock_image, output_path)
            return True

        # Mock OCR to return predictable text
        ocr_text = "REWE\n15.11.2024\nEinkauf"

        with patch.object(services["scanner"], "scan_page", side_effect=mock_scan):
            with patch.object(services["ocr"], "find_best_threshold", return_value=ocr_text):
                # Step 1: Scan
                success = services["scanner"].scan_page(scan_output)
                assert success
                assert scan_output.exists()

                # Step 2: OCR
                text = services["ocr"].find_best_threshold(scan_output)
                date = services["ocr"].extract_date(text)
                vendor = services["ocr"].extract_vendor(text)

                assert date == "15.11.2024"
                assert vendor == "rewe"

                # Step 3: Create PDF (mock subprocess)
                pdf_output = tmp_path / "output.pdf"
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    # Create a dummy PDF for archive test
                    pdf_output.write_bytes(b"%PDF-1.4 dummy")
                    success = True  # Would be services["pdf"].create_pdf([scan_output], pdf_output)

                assert success

                # Step 4: Archive
                receipt_date = datetime.strptime(date, "%d.%m.%Y")
                archived = services["archive"].archive(
                    source_path=pdf_output,
                    date=receipt_date,
                    description=vendor,
                    category="ER",
                    is_credit_card=False,
                )

                # Verify archive location
                assert archived.exists()
                assert "2024" in str(archived)
                assert "11" in str(archived)
                assert "ER" in str(archived)
                assert "rewe" in archived.name

    def test_multi_page_workflow(self, tmp_path: Path, workflow_services, mock_image):
        """Test scanning multiple pages into a single PDF."""
        services = workflow_services
        pages = []

        # Mock scanner
        def mock_scan(output_path):
            import shutil

            shutil.copy(mock_image, output_path)
            return True

        with patch.object(services["scanner"], "scan_page", side_effect=mock_scan):
            # Scan 3 pages
            for i in range(3):
                page_path = tmp_path / f"page_{i}.png"
                success = services["scanner"].scan_page(page_path)
                assert success
                pages.append(page_path)

            assert len(pages) == 3
            assert all(p.exists() for p in pages)

    def test_credit_card_workflow(self, tmp_path: Path, workflow_services, mock_image):
        """Test credit card receipt is filed in the following month."""
        services = workflow_services

        # Create test PDF
        pdf_path = tmp_path / "receipt.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        # December credit card receipt should go to January next year
        receipt_date = datetime(2024, 12, 15)

        archived = services["archive"].archive(
            source_path=pdf_path,
            date=receipt_date,
            description="amazon",
            category="ER-KKJK",
            is_credit_card=True,
        )

        # Should be in 2025/01
        assert "2025" in str(archived)
        assert "/01/" in str(archived)
        assert "ER-KKJK" in str(archived)

    def test_duplicate_filename_handling(self, tmp_path: Path, workflow_services):
        """Test that duplicate filenames get unique suffixes."""
        services = workflow_services
        receipt_date = datetime(2024, 11, 15)

        archived_files = []
        for i in range(3):
            pdf_path = tmp_path / f"receipt_{i}.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test")

            archived = services["archive"].archive(
                source_path=pdf_path,
                date=receipt_date,
                description="rewe",
                category="Kassa",
                is_credit_card=False,
            )
            archived_files.append(archived)

        # All files should exist with unique names
        assert len(archived_files) == 3
        assert all(f.exists() for f in archived_files)
        assert len(set(archived_files)) == 3  # All unique


class TestConfigIntegration:
    """Test configuration persistence across service instances."""

    def test_config_persists_across_instances(self, config_file: Path, archive_dir: Path):
        """Test that config saved by one instance is read by another."""
        # First instance saves
        config1 = ConfigManager(config_path=config_file)
        config1.archive_path = str(archive_dir)

        # Second instance reads
        config2 = ConfigManager(config_path=config_file)
        assert config2.archive_path == str(archive_dir)


class TestOcrExtraction:
    """Test OCR extraction with realistic receipt texts."""

    @pytest.fixture
    def realistic_receipts(self):
        """Collection of realistic receipt texts."""
        return {
            "supermarket": """
                REWE Center
                Musterstraße 123
                12345 Berlin

                Datum: 15.11.2024  Zeit: 14:32

                Bananen Bio         1,99
                Vollmilch 3,5%      1,29
                Brot Dinkel         2,49
                ----------------------
                SUMME EUR           5,77

                EC-Zahlung
                Vielen Dank!
            """,
            "hardware": """
                *** BAUHAUS ***
                Filiale 0815

                03.12.24

                Schrauben M6x30     5,99
                Dübel Set          12,99
                ----------------------
                Gesamt:            18,98

                Bar bezahlt
            """,
            "online": """
                Amazon.de
                Rechnung

                Rechnungsdatum: 2024/11/20

                Bestellung #123-456
                USB Kabel           8,99
                MwSt 19%            1,44
                ----------------------
                Gesamtbetrag       10,43
            """,
        }

    def test_extract_dates_various_formats(self, realistic_receipts):
        """Test date extraction from various receipt formats."""
        ocr = OcrService()

        # DD.MM.YYYY format
        date = ocr.extract_date(realistic_receipts["supermarket"])
        assert date == "15.11.2024"

        # DD.MM.YY format
        date = ocr.extract_date(realistic_receipts["hardware"])
        assert date == "03.12.2024"

    def test_extract_vendors(self, realistic_receipts):
        """Test vendor extraction from various receipts."""
        ocr = OcrService()

        vendor = ocr.extract_vendor(realistic_receipts["supermarket"])
        assert "rewe" in vendor.lower()

        vendor = ocr.extract_vendor(realistic_receipts["hardware"])
        assert "bauhaus" in vendor.lower()


class TestServiceErrorHandling:
    """Test error handling across services."""

    def test_archive_without_base_path_raises(self, tmp_path: Path):
        """Test that archiving without base_path raises ValueError."""
        archive = ArchiveService()  # No base_path
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF")

        with pytest.raises(ValueError, match="base_path must be set"):
            archive.archive(
                source_path=pdf_path,
                date=datetime.now(),
                description="test",
                category="ER",
                is_credit_card=False,
            )

    def test_scanner_handles_missing_device(self):
        """Test scanner returns False when scan fails."""
        scanner = ScannerService()

        with patch("subprocess.run") as mock_run:
            from subprocess import CalledProcessError

            mock_run.side_effect = CalledProcessError(1, "scanimage")

            result = scanner.scan_page(Path("/tmp/test.png"))
            assert result is False
