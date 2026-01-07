"""Tests for OllamaService."""

import pytest
from unittest.mock import patch, MagicMock
import json

from belegscanner.services.ollama import OllamaService, ExtractionResult


class TestIsAvailable:
    """Test Ollama availability check."""

    @patch("belegscanner.services.ollama.urllib.request.urlopen")
    def test_returns_true_when_ollama_running(self, mock_urlopen: MagicMock):
        """Return True when Ollama server responds."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        service = OllamaService()

        assert service.is_available() is True

    @patch("belegscanner.services.ollama.urllib.request.urlopen")
    def test_returns_false_when_connection_refused(self, mock_urlopen: MagicMock):
        """Return False when Ollama server not running."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        service = OllamaService()

        assert service.is_available() is False

    @patch("belegscanner.services.ollama.urllib.request.urlopen")
    def test_returns_false_on_timeout(self, mock_urlopen: MagicMock):
        """Return False when request times out."""
        import socket
        mock_urlopen.side_effect = socket.timeout("timed out")

        service = OllamaService()

        assert service.is_available() is False


class TestExtract:
    """Test structured data extraction from OCR text."""

    @patch("belegscanner.services.ollama.urllib.request.urlopen")
    def test_extracts_vendor_amount_currency(self, mock_urlopen: MagicMock):
        """Extract vendor, amount, and currency from OCR text."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "response": '{"vendor": "REWE", "amount": "27.07", "currency": "EUR", "date": "15.11.2024"}'
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        service = OllamaService()
        result = service.extract("REWE\nGesamt: € 27,07\n15.11.2024")

        assert result.vendor == "REWE"
        assert result.amount == "27.07"
        assert result.currency == "EUR"
        assert result.date == "15.11.2024"

    @patch("belegscanner.services.ollama.urllib.request.urlopen")
    def test_handles_partial_extraction(self, mock_urlopen: MagicMock):
        """Handle when only some fields are extracted."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "response": '{"vendor": "Amazon", "amount": null, "currency": null, "date": null}'
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        service = OllamaService()
        result = service.extract("Amazon Order Confirmation")

        assert result.vendor == "Amazon"
        assert result.amount is None
        assert result.currency is None

    @patch("belegscanner.services.ollama.urllib.request.urlopen")
    def test_handles_ollama_not_running(self, mock_urlopen: MagicMock):
        """Return empty result when Ollama not available."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        service = OllamaService()
        result = service.extract("Some OCR text")

        assert result.vendor is None
        assert result.amount is None
        assert result.currency is None
        assert result.date is None

    @patch("belegscanner.services.ollama.urllib.request.urlopen")
    def test_handles_malformed_json_response(self, mock_urlopen: MagicMock):
        """Handle non-JSON response from Ollama."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "response": "I cannot parse this text properly."
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        service = OllamaService()
        result = service.extract("Garbled OCR text")

        assert result.vendor is None
        assert result.amount is None

    @patch("belegscanner.services.ollama.urllib.request.urlopen")
    def test_handles_json_in_markdown_code_block(self, mock_urlopen: MagicMock):
        """Handle JSON wrapped in markdown code block."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "response": '```json\n{"vendor": "Bauhaus", "amount": "50.00", "currency": "EUR", "date": null}\n```'
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        service = OllamaService()
        result = service.extract("Bauhaus receipt")

        assert result.vendor == "Bauhaus"
        assert result.amount == "50.00"
        assert result.currency == "EUR"

    @patch("belegscanner.services.ollama.urllib.request.urlopen")
    def test_sends_correct_prompt(self, mock_urlopen: MagicMock):
        """Send OCR text with extraction prompt to Ollama."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "response": '{"vendor": null, "amount": null, "currency": null, "date": null}'
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        service = OllamaService()
        service.extract("Test OCR Text")

        # Check the request payload
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        payload = json.loads(request.data.decode())

        assert "Test OCR Text" in payload["prompt"]
        assert payload["model"] == "phi3"
        assert payload["stream"] is False

    @patch("belegscanner.services.ollama.urllib.request.urlopen")
    def test_uses_configured_model(self, mock_urlopen: MagicMock):
        """Use configured model name in request."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "response": '{"vendor": null, "amount": null, "currency": null, "date": null}'
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        service = OllamaService(model="qwen2.5:3b")
        service.extract("Test")

        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        payload = json.loads(request.data.decode())

        assert payload["model"] == "qwen2.5:3b"

    def test_returns_empty_result_for_empty_input(self):
        """Return empty result for empty OCR text."""
        service = OllamaService()
        result = service.extract("")

        assert result.vendor is None
        assert result.amount is None

    def test_returns_empty_result_for_none_input(self):
        """Return empty result for None OCR text."""
        service = OllamaService()
        result = service.extract(None)

        assert result.vendor is None
        assert result.amount is None


class TestExtractionResult:
    """Test ExtractionResult dataclass."""

    def test_creates_with_all_fields(self):
        """Create result with all fields."""
        result = ExtractionResult(
            vendor="REWE",
            amount="27.07",
            currency="EUR",
            date="15.11.2024"
        )

        assert result.vendor == "REWE"
        assert result.amount == "27.07"
        assert result.currency == "EUR"
        assert result.date == "15.11.2024"

    def test_creates_with_none_fields(self):
        """Create result with None fields."""
        result = ExtractionResult(
            vendor=None,
            amount=None,
            currency=None,
            date=None
        )

        assert result.vendor is None
        assert result.amount is None

    def test_has_data_returns_true_when_any_field_set(self):
        """has_data returns True when any field has value."""
        result = ExtractionResult(vendor="Test", amount=None, currency=None, date=None)

        assert result.has_data is True

    def test_has_data_returns_false_when_all_none(self):
        """has_data returns False when all fields are None."""
        result = ExtractionResult(vendor=None, amount=None, currency=None, date=None)

        assert result.has_data is False
