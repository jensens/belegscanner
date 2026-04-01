"""Tests for text utility functions."""

from belegscanner.services.text import strip_html


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
        assert strip_html("&amp; &lt; &gt; &quot; &#39;") == '& < > " \''

    def test_decodes_nbsp(self):
        assert "hello world" in strip_html("hello&nbsp;world")

    def test_collapses_whitespace(self):
        result = strip_html("<p>  lots   of    spaces  </p>")
        assert "  " not in result
