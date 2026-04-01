"""Tests for email attachment filename sanitization."""

from pathlib import Path


def _sanitize_filename(filename: str) -> str:
    """Sanitize attachment filename to prevent path traversal."""
    # Handle Windows-style backslash paths on any OS
    name = filename.replace("\\", "/")
    name = Path(name).name
    # Reject dot-only names like "." or ".."
    if not name or set(name) == {"."}:
        return "attachment"
    return name


class TestSanitizeAttachmentFilename:
    def test_normal_filename_unchanged(self):
        assert _sanitize_filename("invoice.pdf") == "invoice.pdf"

    def test_strips_directory_traversal(self):
        assert _sanitize_filename("../../etc/passwd") == "passwd"

    def test_strips_absolute_path(self):
        assert _sanitize_filename("/etc/passwd") == "passwd"

    def test_strips_windows_path(self):
        assert _sanitize_filename("C:\\Users\\file.pdf") == "file.pdf"

    def test_empty_filename_gets_default(self):
        assert _sanitize_filename("") == "attachment"

    def test_dot_only_gets_default(self):
        assert _sanitize_filename("..") == "attachment"
