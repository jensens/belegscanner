"""Tests for ArchiveService."""

from datetime import datetime
from pathlib import Path

from belegscanner.services.archive import ArchiveService


class TestCalcTargetMonth:
    """Test target month calculation."""

    def test_regular_category_uses_receipt_date(self):
        """Regular receipts use the receipt's month."""
        service = ArchiveService()
        date = datetime(2024, 11, 15)

        year, month = service.calc_target_month(date, is_credit_card=False)

        assert year == 2024
        assert month == 11

    def test_credit_card_uses_next_month(self):
        """Credit card receipts are filed in next month."""
        service = ArchiveService()
        date = datetime(2024, 11, 15)

        year, month = service.calc_target_month(date, is_credit_card=True)

        assert year == 2024
        assert month == 12

    def test_credit_card_december_rolls_to_next_year(self):
        """Credit card in December rolls to January next year."""
        service = ArchiveService()
        date = datetime(2024, 12, 20)

        year, month = service.calc_target_month(date, is_credit_card=True)

        assert year == 2025
        assert month == 1


class TestArchive:
    """Test file archiving functionality."""

    def test_creates_target_directory(self, archive_dir: Path):
        """Create target directory structure if it doesn't exist."""
        service = ArchiveService(archive_dir)

        # Create a temp file to archive
        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        date = datetime(2024, 11, 15)
        service.archive(source, date, "rewe", "ER", is_credit_card=False)

        target_dir = archive_dir / "2024" / "11" / "ER"
        assert target_dir.exists()

    def test_moves_file_to_correct_location(self, archive_dir: Path):
        """Move PDF to year/month/category folder."""
        service = ArchiveService(archive_dir)

        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        date = datetime(2024, 11, 15)
        result = service.archive(source, date, "rewe", "ER", is_credit_card=False)

        expected = archive_dir / "2024" / "11" / "ER" / "2024-11-15_rewe.pdf"
        assert result == expected
        assert expected.exists()
        assert not source.exists()  # Original should be moved

    def test_filename_format(self, archive_dir: Path):
        """Filename is YYYY-MM-DD_description.pdf."""
        service = ArchiveService(archive_dir)

        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        date = datetime(2024, 3, 5)
        result = service.archive(source, date, "bauhaus", "Kassa", is_credit_card=False)

        assert result.name == "2024-03-05_bauhaus.pdf"

    def test_handles_duplicate_filenames(self, archive_dir: Path):
        """Append counter when filename already exists."""
        service = ArchiveService(archive_dir)

        # Create first file
        source1 = archive_dir / "temp1.pdf"
        source1.write_text("first")
        date = datetime(2024, 11, 15)
        service.archive(source1, date, "rewe", "ER", is_credit_card=False)

        # Create second file with same date/description
        source2 = archive_dir / "temp2.pdf"
        source2.write_text("second")
        result = service.archive(source2, date, "rewe", "ER", is_credit_card=False)

        assert result.name == "2024-11-15_rewe_01.pdf"

    def test_increments_counter_for_multiple_duplicates(self, archive_dir: Path):
        """Counter increments for each duplicate."""
        service = ArchiveService(archive_dir)
        date = datetime(2024, 11, 15)

        for i in range(3):
            source = archive_dir / f"temp{i}.pdf"
            source.write_text(f"content{i}")
            result = service.archive(source, date, "rewe", "ER", is_credit_card=False)

        # Third file should have _02 suffix
        assert result.name == "2024-11-15_rewe_02.pdf"

    def test_credit_card_filed_in_next_month(self, archive_dir: Path):
        """Credit card receipts go to next month's folder."""
        service = ArchiveService(archive_dir)

        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        date = datetime(2024, 11, 15)
        result = service.archive(source, date, "amazon", "ER-KKJK", is_credit_card=True)

        # Should be in December folder even though date is November
        expected_dir = archive_dir / "2024" / "12" / "ER-KKJK"
        assert result.parent == expected_dir

    def test_returns_path_object(self, archive_dir: Path):
        """Return value is a Path object."""
        service = ArchiveService(archive_dir)

        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        result = service.archive(source, datetime(2024, 11, 15), "test", "ER", is_credit_card=False)

        assert isinstance(result, Path)


class TestArchiveWithAmount:
    """Test archiving with amount in filename."""

    def test_filename_includes_amount_eur(self, archive_dir: Path):
        """Filename includes EUR amount."""
        service = ArchiveService(archive_dir)

        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        date = datetime(2024, 11, 15)
        result = service.archive(
            source, date, "rewe", "ER", is_credit_card=False, currency="EUR", amount="27.07"
        )

        assert result.name == "2024-11-15_EUR27-07_rewe.pdf"

    def test_filename_includes_amount_usd(self, archive_dir: Path):
        """Filename includes USD amount."""
        service = ArchiveService(archive_dir)

        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        date = datetime(2024, 11, 15)
        result = service.archive(
            source, date, "hotel", "ER", is_credit_card=False, currency="USD", amount="150.00"
        )

        assert result.name == "2024-11-15_USD150-00_hotel.pdf"

    def test_filename_includes_amount_chf(self, archive_dir: Path):
        """Filename includes CHF amount."""
        service = ArchiveService(archive_dir)

        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        date = datetime(2024, 3, 5)
        result = service.archive(
            source, date, "migros", "Kassa", is_credit_card=False, currency="CHF", amount="89.50"
        )

        assert result.name == "2024-03-05_CHF89-50_migros.pdf"

    def test_amount_replaces_dot_with_dash(self, archive_dir: Path):
        """Amount decimal point is replaced with dash."""
        service = ArchiveService(archive_dir)

        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        date = datetime(2024, 11, 15)
        result = service.archive(
            source, date, "test", "ER", is_credit_card=False, currency="EUR", amount="1234.56"
        )

        assert result.name == "2024-11-15_EUR1234-56_test.pdf"

    def test_amount_whole_number(self, archive_dir: Path):
        """Amount with .00 is formatted correctly."""
        service = ArchiveService(archive_dir)

        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        date = datetime(2024, 11, 15)
        result = service.archive(
            source, date, "test", "ER", is_credit_card=False, currency="EUR", amount="100.00"
        )

        assert result.name == "2024-11-15_EUR100-00_test.pdf"

    def test_handles_duplicate_with_amount(self, archive_dir: Path):
        """Duplicate handling works with amount in filename."""
        service = ArchiveService(archive_dir)
        date = datetime(2024, 11, 15)

        # Create first file
        source1 = archive_dir / "temp1.pdf"
        source1.write_text("first")
        service.archive(
            source1, date, "rewe", "ER", is_credit_card=False, currency="EUR", amount="27.07"
        )

        # Create second file with same details
        source2 = archive_dir / "temp2.pdf"
        source2.write_text("second")
        result = service.archive(
            source2, date, "rewe", "ER", is_credit_card=False, currency="EUR", amount="27.07"
        )

        assert result.name == "2024-11-15_EUR27-07_rewe_01.pdf"

    def test_credit_card_with_amount(self, archive_dir: Path):
        """Credit card receipts with amount go to next month."""
        service = ArchiveService(archive_dir)

        source = archive_dir / "temp.pdf"
        source.write_text("test content")

        date = datetime(2024, 11, 15)
        result = service.archive(
            source, date, "amazon", "ER-KKJK", is_credit_card=True, currency="EUR", amount="99.99"
        )

        # Should be in December folder
        expected_dir = archive_dir / "2024" / "12" / "ER-KKJK"
        assert result.parent == expected_dir
        assert result.name == "2024-11-15_EUR99-99_amazon.pdf"
