"""PDF service for creating searchable PDFs with OCR."""

import os
import subprocess
from pathlib import Path

from belegscanner.constants import OCR_LANGUAGE


class PdfService:
    """Service for creating searchable PDFs from scanned images.

    Uses ImageMagick (convert) to combine images into PDF,
    and ocrmypdf to add searchable text layer.
    """

    def __init__(self, language: str = OCR_LANGUAGE):
        """Initialize PDF service.

        Args:
            language: OCR language code (default: "deu")
        """
        self.language = language

    def create_pdf(self, pages: list[Path], output_path: Path | str) -> bool:
        """Create PDF from page images and run OCR.

        Args:
            pages: List of paths to page images (PNG)
            output_path: Path for the output PDF

        Returns:
            True if PDF creation succeeded, False otherwise
        """
        output_path = Path(output_path)
        temp_pdf = output_path.with_suffix(".temp.pdf")

        try:
            # Create PDF from images using ImageMagick
            subprocess.run(
                ["convert"] + [str(p) for p in pages] + [str(temp_pdf)],
                check=True,
                capture_output=True,
            )

            # Run OCR to create searchable PDF
            subprocess.run(
                [
                    "ocrmypdf",
                    "--language",
                    self.language,
                    "--skip-text",
                    "--deskew",
                    "--clean",
                    str(temp_pdf),
                    str(output_path),
                ],
                check=True,
                capture_output=True,
            )

            # Clean up temp file
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

            return True

        except subprocess.CalledProcessError:
            # Clean up temp file on error
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)
            return False
