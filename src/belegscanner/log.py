"""Logging setup for belegscanner."""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger for the given module name.

    Args:
        name: Module name (e.g., "belegscanner.services.imap").

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(name)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
    return logger
