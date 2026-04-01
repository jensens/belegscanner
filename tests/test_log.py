"""Tests for logging setup."""

import logging

from belegscanner.log import get_logger


class TestGetLogger:
    def test_returns_logger_with_module_name(self):
        logger = get_logger("belegscanner.services.imap")
        assert logger.name == "belegscanner.services.imap"
        assert isinstance(logger, logging.Logger)

    def test_default_level_is_warning(self):
        logger = get_logger("belegscanner.test")
        assert logger.getEffectiveLevel() == logging.WARNING
