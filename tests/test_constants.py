"""Tests for shared constants."""

from belegscanner.constants import CURRENCIES, DEFAULT_CURRENCY, KNOWN_CURRENCIES


class TestCurrencyConstants:
    def test_ui_currencies(self):
        assert CURRENCIES == ("EUR", "USD", "CHF", "GBP")

    def test_default_is_a_ui_currency(self):
        assert DEFAULT_CURRENCY in CURRENCIES

    def test_known_currencies_superset_of_ui(self):
        assert frozenset(CURRENCIES) <= KNOWN_CURRENCIES
