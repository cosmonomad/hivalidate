"""Build post-validation artifacts (CSV, cubelets, dry-run plots, and -- true only --
a mosaic FITS plus an optical-background overview PNG) for every reviewed QA class
(true/false/uncertain/duplicate), each under its own `postprocess/<class_name>/`
subdirectory.

Run `hivalidate-qa` first (or at least far enough into a session that some sources
have been reviewed -- this can be run against a partially-reviewed catalogue; classes
with zero matching sources still get their (empty) CSV/cubelets/plots directories).
"""

from __future__ import annotations

import logging
import sys

import matplotlib

matplotlib.use("Agg")  # must happen before pyplot/plotting is touched anywhere

import matplotlib.pyplot as plt  # noqa: E402 -- only used to close figures, never to show them
from astropy.io import fits  # noqa: E402
from astropy.wcs import WCS  # noqa: E402

from hivalidate import catalogue, plotting, postprocess  # noqa: E402
from hivalidate.cli._common import base_parser, configure_logging  # noqa: E402
from hivalidate.config import Config  # noqa: E402
from hivalidate.cutouts.base import (  # noqa: E402
    CutoutCache,
    CutoutUnavailable,
    fetch_with_fallback,
)
from hivalidate.cutouts.optical import SkyViewBackend  # noqa: E402

logger = logging.getLogger(__name__)


def run(config: Config) -> None:
    validated_path = config.paths.qa_dir / "validated_cat.xml"
    if not validated_path.exists():
        raise SystemExit(f"{validated_path} does not exist -- run hivalidate-qa first")

    validated = catalogue.read_votable(validated_path)
    config.paths.postprocess_dir.mkdir(parents=True, exist_ok=True)

    true_cubelets_dir = None
    for class_name, qa_value in postprocess.QA_CLASSES.items():
        sources = postprocess.filter_by_qa(validated, {qa_value})
        logger.info(
            "%d %s-flagged sources out of %d reviewed", len(sources), class_name, len(validated)
        )

        class_dir = config.paths.postprocess_dir / class_name
        class_dir.mkdir(parents=True, exist_ok=True)
        names = [str(n) for n in sources["name"]]

        csv_path = class_dir / f"validated_{class_name}.csv"
        postprocess.write_validation_csv(sources, csv_path)
        logger.info("Wrote %s", csv_path)

        cubelets_dir = class_dir / "cubelets"
        n_cubelets = postprocess.extract_cubelets(
            config.paths.renamed_cubelets_dir, cubelets_dir, names
        )
        logger.info(
            "Copied %d cubelet files for %d %s sources to %s",
            n_cubelets,
            len(names),
            class_name,
            cubelets_dir,
        )

        plots_dir = class_dir / "plots"
        n_plots = postprocess.extract_plots(config.paths.dry_run_dir, plots_dir, names)
        logger.info(
            "Copied %d validation plots for %d %s sources to %s",
            n_plots,
            len(names),
            class_name,
            plots_dir,
        )

        if class_name == "true":
            true_cubelets_dir = cubelets_dir

    if config.paths.field_mosaic is None:
        logger.info("No paths.field_mosaic configured -- skipping mosaic step")
        return

    mom0_files = sorted(true_cubelets_dir.glob("*_mom0.fits"))
    mosaic_path = config.paths.postprocess_dir / "true" / "mosaic_true.fits"
    mosaic_data = postprocess.build_mosaic(config.paths.field_mosaic, mom0_files, mosaic_path)
    logger.info("Wrote %s from %d moment-0 maps", mosaic_path, len(mom0_files))

    center, fov_arcsec = postprocess.field_center_and_fov(config.paths.field_mosaic)
    cache = CutoutCache(config.cutouts.cache_dir) if config.cutouts.cache_dir else None
    try:
        # SkyViewBackend specifically, not config.cutouts.optical_priority's
        # per-source chain -- see build_true_detections_overview_figure's docstring
        # for why the per-source-oriented LegacySurveyBackend isn't a fit here.
        optical = fetch_with_fallback(
            center, fov_arcsec, config.field_name, [SkyViewBackend()], cache=cache
        )
    except CutoutUnavailable as exc:
        logger.warning("Could not fetch a field-wide optical background, skipping: %s", exc)
        optical = None

    if optical is not None:
        mosaic_wcs = WCS(fits.getheader(mosaic_path)).celestial
        fig = plotting.build_true_detections_overview_figure(
            optical, mosaic_data, mosaic_wcs, config.field_name
        )
        overview_path = config.paths.postprocess_dir / "true" / "mosaic_true_optical.png"
        fig.savefig(overview_path, bbox_inches="tight", dpi=100)
        plt.close(fig)
        logger.info("Wrote %s", overview_path)


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)
    run(config)


if __name__ == "__main__":
    sys.exit(main())
