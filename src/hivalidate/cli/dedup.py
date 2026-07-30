"""Deduplicate a combined SoFiA catalogue by spatial + velocity cross-match.

Replaces ``legacy/remove_duplicate.py``'s exact-name-string matching (PLAN.md
issue #5). Run `hivalidate-combine` first.
"""

from __future__ import annotations

import logging
import sys

from hivalidate import catalogue
from hivalidate.cli._common import base_parser, configure_logging
from hivalidate.config import Config

logger = logging.getLogger(__name__)


def run(config: Config) -> None:
    if not config.paths.combined_catalogue.exists():
        raise SystemExit(
            f"{config.paths.combined_catalogue} does not exist -- run hivalidate-combine first"
        )

    combined = catalogue.read_votable(config.paths.combined_catalogue)
    logger.info(
        "Deduplicating %d sources (sep=%.1f arcsec)", len(combined), config.dedup.sep_arcsec
    )

    result = catalogue.deduplicate_positional(
        combined,
        sep_arcsec=config.dedup.sep_arcsec,
        vel_tol_base_km_s=config.dedup.vel_tol_base_km_s,
        vel_tol_wm50_factor=config.dedup.vel_tol_wm50_factor,
    )
    logger.info(
        "Removed %d duplicate detections, %d sources remain", result.n_removed, len(result.table)
    )
    for name in result.removed_names:
        logger.debug("Removed duplicate: %s", name)

    catalogue.write_votable(result.table, config.paths.deduped_catalogue)
    logger.info("Wrote %s", config.paths.deduped_catalogue)


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)
    run(config)


if __name__ == "__main__":
    sys.exit(main())
