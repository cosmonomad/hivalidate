"""Build post-validation artifacts (CSV, cubelets, mosaic) for true-flagged sources.

Run `hivalidate-qa` first (or at least far enough into a session that some sources
are flagged true -- this can be run against a partially-reviewed catalogue).
"""

from __future__ import annotations

import logging
import sys

from hivalidate import catalogue, postprocess
from hivalidate.cli._common import base_parser, configure_logging
from hivalidate.config import Config

logger = logging.getLogger(__name__)


def run(config: Config) -> None:
    validated_path = config.paths.qa_dir / "validated_cat.xml"
    if not validated_path.exists():
        raise SystemExit(f"{validated_path} does not exist -- run hivalidate-qa first")

    validated = catalogue.read_votable(validated_path)
    true_sources = postprocess.filter_by_qa(validated, {postprocess.QA_TRUE})
    logger.info("%d true-flagged sources out of %d reviewed", len(true_sources), len(validated))

    config.paths.postprocess_dir.mkdir(parents=True, exist_ok=True)

    csv_path = config.paths.postprocess_dir / "validated_true.csv"
    postprocess.write_validation_csv(true_sources, csv_path)
    logger.info("Wrote %s", csv_path)

    true_cubelets_dir = config.paths.postprocess_dir / "true_cubelets"
    names = [str(n) for n in true_sources["name"]]
    n_copied = postprocess.extract_cubelets(
        config.paths.renamed_cubelets_dir, true_cubelets_dir, names
    )
    logger.info(
        "Copied %d cubelet files for %d true sources to %s", n_copied, len(names), true_cubelets_dir
    )

    if config.paths.field_mosaic is None:
        logger.info("No paths.field_mosaic configured -- skipping mosaic step")
        return

    mom0_files = sorted(true_cubelets_dir.glob("*_mom0.fits"))
    mosaic_path = config.paths.postprocess_dir / "mosaic_true.fits"
    postprocess.build_mosaic(config.paths.field_mosaic, mom0_files, mosaic_path)
    logger.info("Wrote %s from %d moment-0 maps", mosaic_path, len(mom0_files))


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)
    run(config)


if __name__ == "__main__":
    sys.exit(main())
