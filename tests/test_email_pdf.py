"""Tests for EmailPdfService."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from belegscanner.services.email_pdf import EmailPdfService, _restricted_url_fetcher


class TestEmailPdfServiceCreatePdf:
    """Test PDF creation from email."""

    def test_create_pdf_creates_file(self, tmp_path: Path):
        """create_pdf() creates a PDF file."""
        service = EmailPdfService()
        output_path = tmp_path / "test.pdf"

        result = service.create_pdf(
            sender="test@example.com",
            subject="Test Subject",
            date=datetime(2024, 11, 15, 10, 30),
            message_id="<test123@example.com>",
            body_text="Hello World",
            body_html=None,
            output_path=output_path,
        )

        assert result is True
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_create_pdf_with_html_body(self, tmp_path: Path):
        """create_pdf() uses HTML body when available."""
        service = EmailPdfService()
        output_path = tmp_path / "test_html.pdf"

        result = service.create_pdf(
            sender="test@example.com",
            subject="HTML Email",
            date=datetime(2024, 11, 15),
            message_id="<html@example.com>",
            body_text="Fallback text",
            body_html="<h1>Hello</h1><p>This is <strong>HTML</strong> content.</p>",
            output_path=output_path,
        )

        assert result is True
        assert output_path.exists()

    def test_pdf_starts_with_pdf_header(self, tmp_path: Path):
        """Created file is a valid PDF (starts with %PDF)."""
        service = EmailPdfService()
        output_path = tmp_path / "valid.pdf"

        service.create_pdf(
            sender="test@example.com",
            subject="Test",
            date=datetime(2024, 11, 15),
            message_id="<test@example.com>",
            body_text="Content",
            body_html=None,
            output_path=output_path,
        )

        content = output_path.read_bytes()
        assert content.startswith(b"%PDF")

    def test_create_pdf_handles_unicode(self, tmp_path: Path):
        """create_pdf() handles Unicode characters correctly."""
        service = EmailPdfService()
        output_path = tmp_path / "unicode.pdf"

        result = service.create_pdf(
            sender="täst@example.com",
            subject="Tëst Sübjéct with Ümlauts",
            date=datetime(2024, 11, 15),
            message_id="<unicode@example.com>",
            body_text="Héllo Wörld! 日本語 中文 한국어",
            body_html=None,
            output_path=output_path,
        )

        assert result is True
        assert output_path.exists()

    def test_create_pdf_handles_empty_body(self, tmp_path: Path):
        """create_pdf() handles empty body text."""
        service = EmailPdfService()
        output_path = tmp_path / "empty_body.pdf"

        result = service.create_pdf(
            sender="test@example.com",
            subject="Empty Body",
            date=datetime(2024, 11, 15),
            message_id="<empty@example.com>",
            body_text="",
            body_html=None,
            output_path=output_path,
        )

        assert result is True
        assert output_path.exists()

    def test_create_pdf_creates_parent_directories(self, tmp_path: Path):
        """create_pdf() creates parent directories if needed."""
        service = EmailPdfService()
        output_path = tmp_path / "deep" / "nested" / "dir" / "test.pdf"

        result = service.create_pdf(
            sender="test@example.com",
            subject="Test",
            date=datetime(2024, 11, 15),
            message_id="<test@example.com>",
            body_text="Content",
            body_html=None,
            output_path=output_path,
        )

        assert result is True
        assert output_path.exists()

    def test_create_pdf_handles_long_subject(self, tmp_path: Path):
        """create_pdf() handles very long subject lines."""
        service = EmailPdfService()
        output_path = tmp_path / "long_subject.pdf"
        long_subject = "A" * 500  # Very long subject

        result = service.create_pdf(
            sender="test@example.com",
            subject=long_subject,
            date=datetime(2024, 11, 15),
            message_id="<long@example.com>",
            body_text="Content",
            body_html=None,
            output_path=output_path,
        )

        assert result is True
        assert output_path.exists()

    def test_create_pdf_returns_false_on_invalid_path(self):
        """create_pdf() returns False for invalid output path."""
        service = EmailPdfService()
        # /dev/null/file is not writable
        output_path = Path("/dev/null/impossible/path.pdf")

        result = service.create_pdf(
            sender="test@example.com",
            subject="Test",
            date=datetime(2024, 11, 15),
            message_id="<test@example.com>",
            body_text="Content",
            body_html=None,
            output_path=output_path,
        )

        assert result is False


class TestEmailPdfServiceHtmlGeneration:
    """Test HTML generation for PDF."""

    def test_generates_html_with_header_info(self, tmp_path: Path):
        """Generated HTML includes email header information."""
        service = EmailPdfService()

        html = service._generate_html(
            sender="rechnung@amazon.de",
            subject="Ihre Rechnung #12345",
            date=datetime(2024, 11, 15, 10, 30),
            message_id="<abc123@amazon.de>",
            body_text="Test body",
            body_html=None,
        )

        assert "rechnung@amazon.de" in html
        assert "Ihre Rechnung #12345" in html
        assert "15.11.2024" in html
        assert "&lt;abc123@amazon.de&gt;" in html or "<abc123@amazon.de>" in html

    def test_prefers_html_body_over_text(self, tmp_path: Path):
        """HTML body is used when available."""
        service = EmailPdfService()

        html = service._generate_html(
            sender="test@example.com",
            subject="Test",
            date=datetime(2024, 11, 15),
            message_id="<test@example.com>",
            body_text="Plain text fallback",
            body_html="<p>HTML content</p>",
        )

        assert "HTML content" in html
        # Plain text might still be present as fallback, but HTML is primary

    def test_wraps_plain_text_in_pre(self, tmp_path: Path):
        """Plain text body is wrapped in <pre> tags."""
        service = EmailPdfService()

        html = service._generate_html(
            sender="test@example.com",
            subject="Test",
            date=datetime(2024, 11, 15),
            message_id="<test@example.com>",
            body_text="Line 1\nLine 2\n  Indented",
            body_html=None,
        )

        assert "<pre" in html
        # Text should be escaped and preserved
        assert "Line 1" in html


class TestRestrictedUrlFetcher:
    def test_blocks_file_scheme(self):
        with pytest.raises(ValueError, match="Blockiertes URL-Schema"):
            _restricted_url_fetcher("file:///etc/passwd")

    def test_blocks_unknown_scheme(self):
        with pytest.raises(ValueError):
            _restricted_url_fetcher("ftp://example.com/x")

    def test_allows_http_with_timeout(self):
        with patch("belegscanner.services.email_pdf.default_url_fetcher") as mock_fetch:
            _restricted_url_fetcher("https://example.com/logo.png")
            mock_fetch.assert_called_once_with("https://example.com/logo.png", timeout=5)

    def test_allows_inline_data_image(self):
        with patch("belegscanner.services.email_pdf.default_url_fetcher") as mock_fetch:
            _restricted_url_fetcher("data:image/png;base64,AAAA")
            mock_fetch.assert_called_once()


class TestCreatePdfBlocksLocalFiles:
    def test_pdf_with_file_url_image_still_succeeds(self, tmp_path):
        service = EmailPdfService()
        output = tmp_path / "mail.pdf"
        ok = service.create_pdf(
            sender="a@b.de",
            subject="Test",
            date=datetime(2024, 11, 15, 10, 0),
            message_id="<x@y>",
            body_text="",
            body_html='<p>Hallo</p><img src="file:///etc/hostname">',
            output_path=output,
        )
        assert ok is True  # kaputtes/blockiertes Bild bricht das PDF nicht
        assert output.exists()
