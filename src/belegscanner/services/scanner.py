"""Scanner service for scanning documents."""

import subprocess
from pathlib import Path

from belegscanner.constants import DEFAULT_RESOLUTION, DEFAULT_SCAN_MODE


class ScannerService:
    """Service for scanning documents using SANE (scanimage).

    Uses the scanimage command-line tool to interface with scanners.
    """

    def __init__(
        self,
        resolution: int = DEFAULT_RESOLUTION,
        mode: str = DEFAULT_SCAN_MODE,
    ):
        """Initialize scanner service.

        Args:
            resolution: Scan resolution in DPI (default: 300)
            mode: Scan mode, e.g., "True Gray", "Color" (default: "True Gray")
        """
        self.resolution = resolution
        self.mode = mode

    def scan_page(self, output_path: Path | str) -> bool:
        """Scan a single page to PNG.

        Args:
            output_path: Path where the scanned image will be saved

        Returns:
            True if scan succeeded, False otherwise
        """
        try:
            subprocess.run(
                [
                    "scanimage",
                    "--mode", self.mode,
                    "--resolution", str(self.resolution),
                    "--format", "png",
                    "-o", str(output_path),
                ],
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def is_available(self) -> bool:
        """Check if a scanner is available.

        Returns:
            True if a scanner is found, False otherwise
        """
        try:
            result = subprocess.run(
                ["scanimage", "-L"],
                capture_output=True,
                text=True,
                check=True,
            )
            # If output contains device info, scanner is available
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False
