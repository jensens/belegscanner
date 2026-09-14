"""Text utility functions."""

import re
from html import unescape
from pathlib import Path

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def strip_html(html: str | None) -> str:
    """Strip HTML tags and return plain text.

    Simple regex-based HTML stripping for extraction purposes.

    Args:
        html: HTML string or None.

    Returns:
        Plain text with HTML tags removed and entities decoded.
    """
    if not html:
        return ""
    text = _SCRIPT_STYLE_RE.sub("", html)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def sanitize_filename(filename: str | None) -> str:
    """Reduce an untrusted (e.g. MIME) filename to a safe basename.

    Strips directory components (also Windows-style), control characters
    and NUL bytes; dot-only or empty names become "attachment".

    Args:
        filename: Untrusted filename or None.

    Returns:
        Safe basename, never empty.
    """
    if not filename:
        return "attachment"
    name = _CONTROL_RE.sub("", filename.replace("\\", "/"))
    name = Path(name).name
    if not name or set(name) == {"."}:
        return "attachment"
    return name
