"""Tests for logging setup."""

import logging

from belegscanner.log import get_logger, setup_logging


class TestSetupLogging:
    def test_configures_package_logger_once(self):
        setup_logging()
        setup_logging()
        pkg = logging.getLogger("belegscanner")
        assert len(pkg.handlers) == 1
        assert pkg.propagate is False

    def test_default_level_is_warning(self):
        setup_logging()
        assert logging.getLogger("belegscanner").level == logging.WARNING

    def test_level_applies_to_child_loggers(self):
        setup_logging(logging.DEBUG)
        child = get_logger("belegscanner.services.imap")
        assert child.getEffectiveLevel() == logging.DEBUG
        assert child.handlers == []
        setup_logging()  # zuruecksetzen fuer andere Tests


class TestGetLogger:
    def test_returns_plain_logger_without_handlers(self):
        logger = get_logger("belegscanner.services.ocr")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "belegscanner.services.ocr"
        assert logger.handlers == []
