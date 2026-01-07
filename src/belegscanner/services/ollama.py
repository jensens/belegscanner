"""Ollama service for AI-based data extraction from OCR text."""

import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass

from belegscanner.constants import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT


@dataclass
class ExtractionResult:
    """Result of AI extraction from OCR text."""

    vendor: str | None
    amount: str | None
    currency: str | None
    date: str | None

    @property
    def has_data(self) -> bool:
        """Return True if any field has a value."""
        return any([self.vendor, self.amount, self.currency, self.date])


class OllamaService:
    """Service for AI-based data extraction using Ollama.

    Uses a local LLM (via Ollama) to extract structured data
    (vendor, amount, currency, date) from OCR text when
    regex-based extraction fails or produces poor results.
    """

    # Prompt template for extraction
    PROMPT_TEMPLATE = """Extrahiere aus diesem deutschen Beleg/Rechnung:

{ocr_text}

Antworte NUR mit JSON (keine Erklärung):
{{"vendor": "Firmenname oder null", "amount": "XX.XX oder null", \
"currency": "EUR/USD/CHF oder null", "date": "TT.MM.JJJJ oder null"}}"""

    def __init__(
        self,
        host: str = OLLAMA_HOST,
        model: str = OLLAMA_MODEL,
        timeout: int = OLLAMA_TIMEOUT,
    ):
        """Initialize Ollama service.

        Args:
            host: Ollama server URL (default: http://localhost:11434)
            model: Model name to use (default: phi3)
            timeout: Request timeout in seconds (default: 30)
        """
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def is_available(self) -> bool:
        """Check if Ollama server is running.

        Returns:
            True if Ollama responds, False otherwise
        """
        try:
            url = f"{self.host}/api/tags"
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status == 200
        except (urllib.error.URLError, socket.timeout, OSError):
            return False

    def extract(self, ocr_text: str | None) -> ExtractionResult:
        """Extract structured data from OCR text using LLM.

        Args:
            ocr_text: Raw OCR text from scanned document

        Returns:
            ExtractionResult with extracted fields (or None for each)
        """
        if not ocr_text:
            return ExtractionResult(vendor=None, amount=None, currency=None, date=None)

        try:
            response_text = self._call_ollama(ocr_text)
            return self._parse_response(response_text)
        except (urllib.error.URLError, socket.timeout, OSError, json.JSONDecodeError):
            return ExtractionResult(vendor=None, amount=None, currency=None, date=None)

    def _call_ollama(self, ocr_text: str) -> str:
        """Send prompt to Ollama and get response.

        Args:
            ocr_text: OCR text to include in prompt

        Returns:
            Raw response text from Ollama
        """
        url = f"{self.host}/api/generate"
        prompt = self.PROMPT_TEMPLATE.format(ocr_text=ocr_text)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("response", "")

    def _parse_response(self, response_text: str) -> ExtractionResult:
        """Parse JSON response from Ollama.

        Handles:
        - Raw JSON: {"vendor": "..."}
        - Markdown code blocks: ```json\n{...}\n```
        - Malformed/non-JSON responses

        Args:
            response_text: Raw response from Ollama

        Returns:
            ExtractionResult with parsed data
        """
        # Try to extract JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try direct JSON parse
            json_str = response_text.strip()

        try:
            data = json.loads(json_str)
            return ExtractionResult(
                vendor=self._clean_value(data.get("vendor")),
                amount=self._clean_value(data.get("amount")),
                currency=self._clean_value(data.get("currency")),
                date=self._clean_value(data.get("date")),
            )
        except json.JSONDecodeError:
            return ExtractionResult(vendor=None, amount=None, currency=None, date=None)

    def _clean_value(self, value: str | None) -> str | None:
        """Clean extracted value.

        Converts "null" string to None, strips whitespace.

        Args:
            value: Raw value from JSON

        Returns:
            Cleaned value or None
        """
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if value.lower() in ("null", "none", ""):
                return None
        return value
