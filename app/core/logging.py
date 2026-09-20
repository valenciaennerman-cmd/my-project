"""Logging setup.

Every failure in this app is expected to say what failed and why, so the format
carries the logger name and the noisy third-party loggers are turned down
rather than the app's own being turned up.
"""
from __future__ import annotations

import logging
import sys

FORMAT = "%(asctime)s %(levelname)-7s %(name)-28s | %(message)s"
DATEFMT = "%H:%M:%S"

QUIET = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "urllib3": logging.WARNING,
    "anthropic": logging.WARNING,
    "sqlalchemy.engine": logging.WARNING,
    "asyncio": logging.WARNING,
    "watchfiles": logging.WARNING,
}


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:  # uvicorn already configured one
        root.setLevel(level)
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(FORMAT, datefmt=DATEFMT))
        root.addHandler(handler)
        root.setLevel(level)

    for name, quiet_level in QUIET.items():
        logging.getLogger(name).setLevel(quiet_level)
