"""Shared argument-parsing helpers for hivalidate CLI stages."""

from __future__ import annotations

import argparse
import logging


def base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", required=True, help="Path to a field/SB YAML config")
    parser.add_argument(
        "--verbose", action="store_true", help="Enable DEBUG-level logging"
    )
    return parser


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
