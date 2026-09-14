"""Logging setup for belegscanner."""

import logging
import sys

_PACKAGE = "belegscanner"


def setup_logging(level: int = logging.WARNING) -> None:
    """Configure the package logger (idempotent; call once per entry point).

    Args:
        level: Log level for the whole belegscanner package.
    """
    pkg_logger = logging.getLogger(_PACKAGE)
    if not pkg_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(name)s [%(levelname)s] %(message)s"))
        pkg_logger.addHandler(handler)
        pkg_logger.propagate = False
    pkg_logger.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return the logger for a module; configuration happens via setup_logging()."""
    return logging.getLogger(name)
