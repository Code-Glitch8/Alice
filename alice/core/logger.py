"""Logging setup. Rotating file logs; never logs audio or file contents."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_configured = False


def setup_logging(data_dir: Path | str, level: int = logging.INFO, console: bool = True) -> Path:
    global _configured
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / "alice.log"

    if _configured:
        return logfile

    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.handlers.RotatingFileHandler(
        logfile, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")
    )
    root.addHandler(handler)

    if console and sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(levelname)-7s [%(name)s] %(message)s"))
        root.addHandler(sh)

    # Keep noisy third-party libs quieter
    for noisy in ("httpx", "urllib3", "PIL", "asyncio", "wmi"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
    return logfile


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
