"""Tests for VendorExtractor service."""

from belegscanner.services.vendor import VendorExtractor


class TestVendorExtractorFromSender:
    """Test extraction from sender/From header."""

    def test_extracts_display_name(self):
        """Display name is preferred over domain."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="Amazon <rechnung@amazon.de>")
        assert result == "amazon"

    def test_extracts_display_name_with_quotes(self):
        """Quoted display names are handled correctly."""
        extractor = VendorExtractor()
        result = extractor.extract(sender='"Amazon.de" <rechnung@amazon.de>')
        assert result == "amazon_de"

    def test_extracts_display_name_multiword(self):
        """Multi-word display names are cleaned."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="Amazon Deutschland <rechnung@email-amazon.de>")
        assert result == "amazon_deutschland"

    def test_falls_back_to_domain_when_no_display_name(self):
        """Domain is used when no display name present."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="rechnung@amazon.de")
        assert result == "amazon"

    def test_skips_blacklisted_display_name(self):
        """Blacklisted display names are skipped, domain used instead."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="Rechnung <rechnung@amazon.de>")
        assert result == "amazon"

    def test_skips_blacklisted_domain_uses_subject(self):
        """When domain is blacklisted, subject is used."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@invoice-service.com",
            subject="Rechnung von MediaMarkt #12345",
        )
        assert result == "mediamarkt"

    def test_extracts_domain_without_tld(self):
        """TLD is removed from domain."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="info@zalando.de")
        assert result == "zalando"

    def test_handles_complex_domain(self):
        """Subdomains are handled (first part used)."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="noreply@mail.amazon.de")
        # "mail" is blacklisted, should fall through
        # This tests that we handle subdomains
        result = extractor.extract(sender="info@shop.amazon.de")
        assert result == "shop"


class TestVendorExtractorFromSubject:
    """Test extraction from subject line."""

    def test_extracts_vendor_after_von(self):
        """'von' keyword extracts following word."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@billing.com",  # blacklisted
            subject="Rechnung von Amazon #12345",
        )
        assert result == "amazon"

    def test_extracts_vendor_after_bei(self):
        """'bei' keyword extracts following word."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@service.com",
            subject="Ihre Bestellung bei Zalando",
        )
        assert result == "zalando"

    def test_extracts_vendor_after_from(self):
        """'from' keyword extracts following word."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@billing.com",
            subject="Invoice from Spotify",
        )
        assert result == "spotify"

    def test_extracts_vendor_after_an(self):
        """'an' keyword extracts following word (German: 'to')."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@billing.com",
            subject="Sie haben eine Zahlung an Digitalcourage gesendet",
        )
        assert result == "digitalcourage"

    def test_extracts_vendor_after_by(self):
        """'by' keyword extracts following word."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@notification.com",
            subject="Payment processed by Adidas",
        )
        assert result == "adidas"

    def test_ignores_numbers_in_subject(self):
        """Numbers are not extracted as vendor names."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@service.com",
            subject="Rechnung #12345 vom 01.01.2024",
        )
        # Should not return "12345" or similar
        assert result is None or not result.isdigit()

    def test_ignores_short_words_in_subject(self):
        """Words shorter than 3 chars are ignored."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@service.com",
            subject="Rechnung von AB",
        )
        # "AB" is too short
        assert result != "ab"

    def test_finds_capitalized_words_as_fallback(self):
        """Capitalized words are considered as vendor names."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@billing.com",
            subject="Your MediaMarkt Order Confirmation",
        )
        assert result == "mediamarkt"


class TestVendorExtractorBlacklist:
    """Test blacklist functionality."""

    def test_blacklist_includes_generic_terms(self):
        """Generic terms like 'rechnung' are blacklisted."""
        extractor = VendorExtractor()
        # "Rechnung" as display name should be skipped
        result = extractor.extract(sender="Rechnung <info@amazon.de>")
        assert result == "amazon"

    def test_blacklist_is_case_insensitive(self):
        """Blacklist matching is case-insensitive."""
        extractor = VendorExtractor()
        # All case variations should be blocked
        for term in ["RECHNUNG", "Rechnung", "rechnung"]:
            result = extractor.extract(sender=f"{term} <info@amazon.de>")
            assert result == "amazon", f"'{term}' should be blacklisted"

    def test_blacklist_includes_own_company(self):
        """Own company name is blacklisted."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="weiterleitung@kleinundpartner.de",
            subject="Fwd: Rechnung von Telekom",
        )
        assert result == "telekom"
        assert "kleinundpartner" not in result.lower()

    def test_blacklist_includes_invoice(self):
        """'invoice' domain is blacklisted."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="info@invoice.example.com",
            subject="Rechnung von Lidl",
        )
        assert result == "lidl"

    def test_blacklist_includes_noreply(self):
        """'noreply' is blacklisted."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@noreply.de",
            subject="Bestellung bei Rewe",
        )
        assert result == "rewe"

    def test_blacklist_includes_paypal(self):
        """Payment processors like PayPal are blacklisted."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="service@paypal.at",
            subject="Sie haben eine Zahlung an Digitalcourage gesendet",
        )
        # PayPal should be blacklisted, "Digitalcourage" extracted from subject
        assert result == "digitalcourage"

    def test_blacklist_includes_stripe(self):
        """Payment processors like Stripe are blacklisted."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="receipts@stripe.com",
            subject="Your payment to Acme Corp",
        )
        # Stripe should be blacklisted, vendor extracted from subject
        assert "stripe" not in result.lower() if result else True


class TestVendorExtractorIntegration:
    """Test complete extraction pipeline."""

    def test_priority_display_name_over_domain(self):
        """Display name has higher priority than domain."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="Amazon Deutschland <service@email-amazon.de>",
            subject="Ihre Bestellung",
        )
        assert "amazon" in result.lower()
        # Should be "amazon_deutschland", not just domain

    def test_priority_domain_over_subject(self):
        """Domain has higher priority than subject."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="info@zalando.de",
            subject="Newsletter von MediaMarkt",
        )
        assert result == "zalando"

    def test_fallback_to_subject_when_domain_blacklisted(self):
        """Subject is used when domain is blacklisted."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="info@service.com",  # "service" is blacklisted
            subject="Rechnung von Zalando #12345",
        )
        assert result == "zalando"

    def test_returns_none_when_nothing_found(self):
        """Returns None when no vendor can be extracted."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@service.com",
            subject="Wichtige Mitteilung",
        )
        assert result is None

    def test_empty_sender_uses_subject(self):
        """Empty sender falls back to subject."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="",
            subject="Rechnung von Amazon",
        )
        assert result == "amazon"

    def test_empty_both_returns_none(self):
        """Empty sender and subject returns None."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="", subject="")
        assert result is None


class TestVendorExtractorCleaning:
    """Test vendor name cleaning."""

    def test_returns_lowercase(self):
        """Vendor names are lowercase."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="AMAZON <x@y.de>")
        assert result == "amazon"

    def test_replaces_special_chars_with_underscore(self):
        """Special characters become underscores."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="Media-Markt GmbH <x@y.de>")
        assert "_" in result
        assert "-" not in result

    def test_handles_umlauts(self):
        """German umlauts are preserved."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="Müller <x@y.de>")
        assert "ü" in result or "muller" in result  # Either preserved or normalized

    def test_truncates_long_names(self):
        """Names longer than 30 chars are truncated."""
        extractor = VendorExtractor()
        long_name = "A" * 50
        result = extractor.extract(sender=f"{long_name} <x@y.de>")
        assert len(result) <= 30

    def test_strips_trailing_underscores(self):
        """Trailing underscores are removed."""
        extractor = VendorExtractor()
        result = extractor.extract(sender="Amazon... <x@y.de>")
        assert not result.endswith("_")


class TestVendorExtractorOcrFallback:
    """Test OCR callback fallback."""

    def test_uses_ocr_callback_when_needed(self):
        """OCR callback is used when other methods fail."""
        extractor = VendorExtractor()

        def ocr_callback():
            return "Rechnung von Edeka GmbH"

        result = extractor.extract(
            sender="noreply@service.com",
            subject="Ihre Rechnung",
            ocr_callback=ocr_callback,
        )
        assert result == "edeka"

    def test_ocr_callback_not_called_when_not_needed(self):
        """OCR callback is not called if sender/subject succeed."""
        extractor = VendorExtractor()
        callback_called = False

        def ocr_callback():
            nonlocal callback_called
            callback_called = True
            return "Some text"

        result = extractor.extract(
            sender="Amazon <x@amazon.de>",
            subject="Ihre Bestellung",
            ocr_callback=ocr_callback,
        )
        assert result == "amazon"
        assert not callback_called

    def test_handles_none_ocr_callback(self):
        """None OCR callback is handled gracefully."""
        extractor = VendorExtractor()
        result = extractor.extract(
            sender="noreply@service.com",
            subject="Mitteilung",
            ocr_callback=None,
        )
        assert result is None

    def test_handles_ocr_callback_returning_none(self):
        """OCR callback returning None is handled."""
        extractor = VendorExtractor()

        def ocr_callback():
            return None

        result = extractor.extract(
            sender="noreply@service.com",
            subject="Mitteilung",
            ocr_callback=ocr_callback,
        )
        assert result is None


class TestVendorExtractorCustomBlacklist:
    """Test custom blacklist functionality."""

    def test_accepts_custom_blacklist(self):
        """Custom blacklist can be provided."""
        custom_blacklist = {"amazon", "zalando"}
        extractor = VendorExtractor(blacklist=custom_blacklist)

        result = extractor.extract(
            sender="info@amazon.de",
            subject="Rechnung von Lidl",
        )
        assert result == "lidl"

    def test_custom_blacklist_overrides_default(self):
        """Custom blacklist replaces default."""
        # "rechnung" is normally blacklisted, but not in custom
        custom_blacklist = {"amazon"}
        extractor = VendorExtractor(blacklist=custom_blacklist)

        result = extractor.extract(sender="Rechnung <x@amazon.de>")
        # "Rechnung" is NOT blacklisted with custom list
        assert result == "rechnung"
