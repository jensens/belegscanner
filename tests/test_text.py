"""Tests for text utility functions."""

import pytest

from belegscanner.services.text import sanitize_filename, strip_html


class TestStripHtml:
    def test_returns_empty_for_none(self):
        assert strip_html(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert strip_html("") == ""

    def test_strips_simple_tags(self):
        assert strip_html("<p>Hello</p>") == "Hello"

    def test_strips_script_elements(self):
        result = strip_html("<script>alert('xss')</script>Text")
        assert "alert" not in result
        assert "Text" in result

    def test_strips_style_elements(self):
        result = strip_html("<style>body{color:red}</style>Text")
        assert "color" not in result
        assert "Text" in result

    def test_decodes_html_entities(self):
        assert strip_html("&amp; &lt; &gt; &quot; &#39;") == "& < > \" '"

    def test_decodes_nbsp(self):
        assert "hello world" in strip_html("hello&nbsp;world")

    def test_collapses_whitespace(self):
        result = strip_html("<p>  lots   of    spaces  </p>")
        assert "  " not in result


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("invoice.pdf", "invoice.pdf"),
            ("../../etc/passwd", "passwd"),
            ("/etc/passwd", "passwd"),
            ("C:\\Users\\file.pdf", "file.pdf"),
            ("", "attachment"),
            (None, "attachment"),
            ("..", "attachment"),
            ("....", "attachment"),
            ("inv\x00oice.pdf", "invoice.pdf"),
            ("re\x1bport\t.pdf", "report.pdf"),
        ],
        ids=[
            "plain",
            "traversal",
            "absolute",
            "windows",
            "empty",
            "none",
            "dotdot",
            "dots",
            "nul",
            "control",
        ],
    )
    def test_sanitize(self, raw, expected):
        assert sanitize_filename(raw) == expected


class TestStripHtmlEntities:
    def test_decodes_euro_and_nbsp(self):
        assert strip_html("Gesamt: 47,99&nbsp;&euro;") == "Gesamt: 47,99 €"

    def test_decodes_umlaut_entities(self):
        assert strip_html("B&uuml;ro") == "Büro"

    def test_no_double_unescape(self):
        # "&amp;lt;" ist die Escapung des literalen Texts "&lt;"
        assert strip_html("&amp;lt;b&amp;gt;") == "&lt;b&gt;"
