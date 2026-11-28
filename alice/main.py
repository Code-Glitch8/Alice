#!/usr/bin/env python3
"""ALICE Windows desktop application entry point.

Use `python -m alice.cli` for command-line diagnostics and interactive CLI chat.
"""
from __future__ import annotations

import logging
import sys


def main() -> int:
    from alice.core.config import Config
    from alice.dashboard.main import run_dashboard

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return run_dashboard(Config.load())


if __name__ == "__main__":
    raise SystemExit(main())
