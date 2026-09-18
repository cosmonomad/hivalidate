"""Build post-validation artifacts (CSV, cubelets, dry-run plots, and -- true and
uncertain only -- a moment-0 mosaic FITS; true only, additionally, a velocity-colored
PNG of that same mosaic, the field-wide optical background as its own FITS, and an
optical-background overview PNG) for every reviewed QA class (true/false/uncertain/
duplicate), each under its own `postprocess/<class_name>/` subdirectory.

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
from hivalidate.cutouts.optical import LegacySurveyBackend, SkyViewBackend  # noqa: E402

logger = logging.getLogger(__name__)

#: Generous enough for the slower of two real timings observed at
#: LegacySurveyBackend.MAX_CUTOUT_PIXELS (192s, the size a field-wide fetch always
#: lands on -- its own real FOV divided by the per-source default pixel scale is
#: always well above that cap) with real margin, not just barely over it --
#: LegacySurveyBackend's per-source default (30s) is far too tight for a
#: field-sized request and would abort a legitimately-still-working fetch as a
#: failure.
_FIELD_OVERVIEW_TIMEOUT_S = 300.0


def run(config: Config) -> None:
    validated_path = config.paths.qa_dir / "validated_cat.xml"
    if not validated_path.exists():
        raise SystemExit(f"{validated_path} does not exist -- run hivalidate-qa first")

    validated = catalogue.read_votable(validated_path)
    config.paths.postprocess_dir.mkdir(parents=True, exist_ok=True)

    true_cubelets_dir = None
    true_sources = None
    uncertain_cubelets_dir = None
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
            true_sources = sources
        elif class_name == "uncertain":
            uncertain_cubelets_dir = cubelets_dir

    if config.paths.field_mosaic is None:
        logger.info("No paths.field_mosaic configured -- skipping mosaic step")
        return

    mom0_files = sorted(true_cubelets_dir.glob("*_mom0.fits"))
    mosaic_path = config.paths.postprocess_dir / "true" / "mosaic_true.fits"
    mosaic_data = postprocess.build_mosaic(config.paths.field_mosaic, mom0_files, mosaic_path)
    logger.info("Wrote %s from %d moment-0 maps", mosaic_path, len(mom0_files))
    mosaic_wcs = WCS(fits.getheader(mosaic_path)).celestial

    # Direct user request: a moment-0 mosaic for "uncertain" too, so an ambiguous
    # call's spatial distribution across the field can be inspected the same way a
    # true detection's can -- flux only, no velocity-colored PNG or optical overview
    # (those stay true-only unless asked for uncertain as well).
    uncertain_mom0_files = sorted(uncertain_cubelets_dir.glob("*_mom0.fits"))
    uncertain_mosaic_path = config.paths.postprocess_dir / "uncertain" / "mosaic_uncertain.fits"
    postprocess.build_mosaic(config.paths.field_mosaic, uncertain_mom0_files, uncertain_mosaic_path)
    logger.info(
        "Wrote %s from %d moment-0 maps", uncertain_mosaic_path, len(uncertain_mom0_files)
    )

    # Each mom0_files entry is "<name>_mom0.fits" -- match it back to that source's
    # own velocity via the same name form the true-class CSV/cubelets already use.
    velocity_by_name = dict(
        zip(
            (str(n).replace(" ", "_") for n in true_sources["name"]),
            postprocess.add_derived_physical_columns(true_sources)["velocity_km_s"],
            strict=True,
        )
    )
    velocities = [velocity_by_name[f.name.removesuffix("_mom0.fits")] for f in mom0_files]
    velocity_mosaic = postprocess.build_velocity_mosaic(
        config.paths.field_mosaic, mom0_files, velocities
    )
    velocity_fig = plotting.build_true_detections_velocity_figure(
        mosaic_wcs, velocity_mosaic, config.field_name
    )
    velocity_png_path = config.paths.postprocess_dir / "true" / "mosaic_true.png"
    velocity_fig.savefig(velocity_png_path, bbox_inches="tight", dpi=100)
    plt.close(velocity_fig)
    logger.info("Wrote %s", velocity_png_path)

    center, fov_arcsec = postprocess.field_center_and_fov(config.paths.field_mosaic)
    cache = CutoutCache(config.cutouts.cache_dir) if config.cutouts.cache_dir else None
    try:
        # Not config.cutouts.optical_priority's per-source chain -- built fresh
        # here so this fetch gets its own timeout/retry budget (see
        # _FIELD_OVERVIEW_TIMEOUT_S) independent of per-source dry-run/qa fetches.
        # Legacy Survey first (matching the per-source preference for its real grz
        # composite imaging over SkyView's greyscale DSS2 Red); its own
        # LegacySurveyBackend.fetch already coarsens the pixel scale to stay within
        # MAX_CUTOUT_PIXELS for a FOV this wide, no field-specific pixscale needed
        # here. SkyView as fallback for coverage Legacy Survey doesn't have (e.g.
        # far-northern fields, past its DECam-based layers' declination ceiling).
        legacy_backend = LegacySurveyBackend(
            timeout_s=_FIELD_OVERVIEW_TIMEOUT_S,
            # Capped well below the default 5: at this timeout, several retries
            # could keep postprocess waiting on a single slow field for the better
            # part of half an hour in the worst case: still enough to ride out one
            # bad response without that.
            max_retries=2,
        )
        optical = fetch_with_fallback(
            center,
            fov_arcsec,
            config.field_name,
            [legacy_backend, SkyViewBackend()],
            cache=cache,
        )
    except CutoutUnavailable as exc:
        logger.warning("Could not fetch a field-wide optical background, skipping: %s", exc)
        optical = None

    if optical is not None:
        # The raw optical cutout as its own FITS, alongside mosaic_true.fits -- so it
        # can be loaded and inspected directly (e.g. in DS9, or overlaid with other
        # data) rather than only ever seen baked into the PNG.
        optical_fits_path = config.paths.postprocess_dir / "true" / "mosaic_true_optical.fits"
        optical_header = optical.wcs.to_header()
        optical_header["HIVPROV"] = optical.provenance
        fits.writeto(optical_fits_path, optical.data, optical_header, overwrite=True)
        logger.info("Wrote %s", optical_fits_path)

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
