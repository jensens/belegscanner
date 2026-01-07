"""Archive service for filing scanned receipts."""

import shutil
from datetime import datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta


class ArchiveService:
    """Service for archiving scanned receipts.

    Archives receipts into a structured folder hierarchy:
        base_path/YYYY/MM/category/YYYY-MM-DD_description.pdf

    Credit card receipts are filed in the following month.
    """

    def __init__(self, base_path: Path | str | None = None):
        """Initialize archive service.

        Args:
            base_path: Base directory for archive. Can be set later.
        """
        self._base_path = Path(base_path) if base_path else None

    @property
    def base_path(self) -> Path | None:
        """Get base archive path."""
        return self._base_path

    @base_path.setter
    def base_path(self, value: Path | str) -> None:
        """Set base archive path."""
        self._base_path = Path(value)

    def calc_target_month(self, date: datetime, is_credit_card: bool) -> tuple[int, int]:
        """Calculate target year and month for filing.

        Credit card receipts are filed in the following month.

        Args:
            date: Receipt date
            is_credit_card: Whether this is a credit card receipt

        Returns:
            Tuple of (year, month)
        """
        if is_credit_card:
            target = date + relativedelta(months=1)
        else:
            target = date
        return target.year, target.month

    def archive(
        self,
        source_path: Path,
        date: datetime,
        description: str,
        category: str,
        is_credit_card: bool,
        currency: str | None = None,
        amount: str | None = None,
    ) -> Path:
        """Move PDF to archive folder.

        Creates the target directory structure if needed.
        Handles duplicate filenames by appending a counter.

        Args:
            source_path: Path to source PDF file
            date: Receipt date
            description: Receipt description (for filename)
            category: Category folder name (e.g., "ER", "Kassa")
            is_credit_card: Whether this is a credit card receipt
            currency: Currency code (e.g., "EUR", "USD", "CHF")
            amount: Amount as string (e.g., "27.07")

        Returns:
            Path to the archived file

        Raises:
            ValueError: If base_path is not set
        """
        if self._base_path is None:
            raise ValueError("base_path must be set before archiving")

        year, month = self.calc_target_month(date, is_credit_card)

        # Create target directory
        target_dir = self._base_path / str(year) / f"{month:02d}" / category
        target_dir.mkdir(parents=True, exist_ok=True)

        # Create filename
        date_str = date.strftime("%Y-%m-%d")

        if currency and amount:
            # New format: YYYY-MM-DD_EUR27-07_description.pdf
            amount_formatted = amount.replace(".", "-")
            base_filename = f"{date_str}_{currency}{amount_formatted}_{description}"
        else:
            # Legacy format: YYYY-MM-DD_description.pdf
            base_filename = f"{date_str}_{description}"

        filename = f"{base_filename}.pdf"
        target_path = target_dir / filename

        # Handle duplicates
        counter = 1
        while target_path.exists():
            filename = f"{base_filename}_{counter:02d}.pdf"
            target_path = target_dir / filename
            counter += 1

        shutil.move(source_path, target_path)
        return target_path
