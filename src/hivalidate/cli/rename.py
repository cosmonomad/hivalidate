"""Rename and copy per-run cubelets into one combined directory, keyed by source name.

Replaces ``legacy/rename_cubelets.py`` + ``legacy/run_all_renames.sh``. Fixes PLAN.md
issue #1 (the shell wrapper's glob pattern didn't match the actual raw SoFiA output
naming) by using `hivalidate.catalogue.find_run_catalogues` against the real
`raw_sofia_dir`, and issue #6 by mapping IDs to names per-run (never on a combined
catalogue -- SoFiA's `id` column is not run-unique).

Only copies cubelets for sources that survived `hivalidate-dedup` -- run
`hivalidate-combine` and `hivalidate-dedup` first, so duplicate detections don't get
cubelet files sitting in the final directory that dry-run/QA will work through.
"""

from __future__ import annotations

import logging
import sys

from hivalidate import catalogue
from hivalidate.cli._common import base_parser, configure_logging
from hivalidate.config import Config

logger = logging.getLogger(__name__)


def run(config: Config) -> None:
    if not config.paths.deduped_catalogue.exists():
        raise SystemExit(
            f"{config.paths.deduped_catalogue} does not exist -- run hivalidate-dedup first"
        )

    deduped = catalogue.read_votable(config.paths.deduped_catalogue)
    if "source_run" not in deduped.colnames:
        raise SystemExit(
            f"{config.paths.deduped_catalogue} has no 'source_run' column -- it must be "
            "produced by hivalidate-combine (which adds provenance) followed by "
            "hivalidate-dedup, not hand-assembled"
        )
    keep_keys = {
        (str(run), str(source_id)) for run, source_id in zip(deduped["source_run"], deduped["id"])
    }
    logger.info("%d sources survived dedup and will get renamed cubelets", len(keep_keys))

    run_catalogues = catalogue.find_run_catalogues(config.paths.raw_sofia_dir)
    total_copied = 0
    for cat_path in run_catalogues:
        base_prefix = cat_path.name.removesuffix("_cat.xml")
        cubelets_dir = config.paths.raw_sofia_dir / f"{base_prefix}_cubelets"
        if not cubelets_dir.is_dir():
            logger.warning(
                "No cubelets directory for %s (expected %s) -- skipping",
                cat_path.name,
                cubelets_dir,
            )
            continue
        count = catalogue.rename_and_copy_cubelets(
            cat_path, cubelets_dir, config.paths.renamed_cubelets_dir, keep_keys=keep_keys
        )
        logger.info("%s: copied %d files", base_prefix, count)
        total_copied += count

    logger.info("Copied %d files total into %s", total_copied, config.paths.renamed_cubelets_dir)


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)
    run(config)


if __name__ == "__main__":
    sys.exit(main())
