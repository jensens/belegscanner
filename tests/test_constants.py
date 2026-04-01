"""Tests for belegscanner constants."""

from belegscanner.constants import CURRENCIES


class TestCurrencies:
    """Test CURRENCIES constant."""

    def test_currencies_is_tuple(self):
        """CURRENCIES is a tuple."""
        assert isinstance(CURRENCIES, tuple)

    def test_currencies_contains_expected_values(self):
        """CURRENCIES contains EUR, USD, CHF, GBP."""
        assert CURRENCIES == ("EUR", "USD", "CHF", "GBP")

    def test_currencies_eur_is_first(self):
        """EUR is the first (default) currency."""
        assert CURRENCIES[0] == "EUR"

    def test_currencies_supports_index_lookup(self):
        """Each currency can be found by index."""
        assert CURRENCIES.index("EUR") == 0
        assert CURRENCIES.index("USD") == 1
        assert CURRENCIES.index("CHF") == 2
        assert CURRENCIES.index("GBP") == 3
