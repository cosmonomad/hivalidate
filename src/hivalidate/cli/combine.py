"""Combine every per-run SoFiA catalogue in a field into one VOTable.

Replaces the combine step of ``legacy/plot_detections.py``. Does not plot anything --
the legacy script's frequency-vs-flux QA plot may return as a small standalone
diagnostic later, but combining catalogues and eyeballing a plot are different
concerns and shouldn't share a script.
"""

from __future__ import annotations

import logging
import sys

from hivalidate import catalogue
from hivalidate.cli._common import base_parser, configure_logging
from hivalidate.config import Config

logger = logging.getLogger(__name__)


def run(config: Config) -> None:
    run_catalogues = catalogue.find_run_catalogues(config.paths.raw_sofia_dir)
    if not run_catalogues:
        raise SystemExit(f"No *_cat.xml files found under {config.paths.raw_sofia_dir}")
    logger.info(
        "Combining %d run catalogues from %s", len(run_catalogues), config.paths.raw_sofia_dir
    )

    combined = catalogue.combine_runs(run_catalogues)
    logger.info("Combined catalogue has %d sources", len(combined))

    config.paths.work_dir.mkdir(parents=True, exist_ok=True)
    catalogue.write_votable(combined, config.paths.combined_catalogue)
    logger.info("Wrote %s", config.paths.combined_catalogue)


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)
    run(config)


if __name__ == "__main__":
    sys.exit(main())
