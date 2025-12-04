"""Pytest fixtures for belegscanner tests."""

import pytest
from pathlib import Path


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Temporary config directory."""
    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def config_file(config_dir: Path) -> Path:
    """Path to config file (may not exist yet)."""
    return config_dir / "belegscanner.conf"


@pytest.fixture
def archive_dir(tmp_path: Path) -> Path:
    """Temporary archive directory."""
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    return archive_dir


@pytest.fixture
def sample_ocr_text() -> str:
    """Sample OCR text with date and vendor."""
    return """REWE
Musterstraße 123
12345 Berlin

15.11.2024  12:34

Äpfel           1,99
Brot            2,49
-----------------
SUMME           4,48
"""


@pytest.fixture
def sample_ocr_text_short_year() -> str:
    """Sample OCR text with short year format."""
    return """Bauhaus
03.12.24
Schrauben 5,99
"""
