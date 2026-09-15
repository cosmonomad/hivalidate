"""Deduplicate a combined SoFiA catalogue by spatial + velocity cross-match, then
(if configured) cross-match the survivors against an external spectroscopic
redshift catalogue.

Replaces ``legacy/remove_duplicate.py``'s exact-name-string matching (PLAN.md
issue #5). Run `hivalidate-combine` first.
"""

from __future__ import annotations

import logging
import sys

from hivalidate import catalogue, crossmatch
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

    deduped = result.table
    if config.paths.external_redshift_catalogue is not None:
        logger.info(
            "Cross-matching against %s", config.paths.external_redshift_catalogue
        )
        external = crossmatch.read_external_catalogue(config.paths.external_redshift_catalogue)
        cx_result = crossmatch.crossmatch_redshifts(
            deduped,
            external,
            sep_arcsec=config.dedup.sep_arcsec,
            vel_tol_base_km_s=config.dedup.vel_tol_base_km_s,
            vel_tol_wm50_factor=config.dedup.vel_tol_wm50_factor,
            catalogue_name=config.paths.external_redshift_catalogue_name,
        )
        logger.info(
            "Matched %d/%d sources to a %s redshift",
            cx_result.n_matched,
            len(deduped),
            config.paths.external_redshift_catalogue_name,
        )
        deduped = cx_result.table

    catalogue.write_votable(deduped, config.paths.deduped_catalogue)
    logger.info("Wrote %s", config.paths.deduped_catalogue)


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)
    run(config)


if __name__ == "__main__":
    sys.exit(main())
