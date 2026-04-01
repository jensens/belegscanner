"""Text utility functions."""

import re


def strip_html(html: str | None) -> str:
    """Strip HTML tags and return plain text.

    Simple regex-based HTML stripping for extraction purposes.

    Args:
        html: HTML string or None.

    Returns:
        Plain text with HTML tags removed.
    """
    if not html:
        return ""
    # Remove script and style elements
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()
