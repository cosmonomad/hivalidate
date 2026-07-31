"""Combine every per-run SoFiA catalogue in a field into one VOTable.

Replaces the combine step of ``legacy/plot_detections.py``, including its
frequency-vs-flux QA plot (`hivalidate.diagnostics.build_frequency_flux_figure`) --
plotting itself lives in its own module, not inline here, since combining catalogues
and building a figure from one are different concerns and shouldn't share a function.
"""

from __future__ import annotations

import logging
import sys

from hivalidate import catalogue, diagnostics
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

    # A cluster of points at one frequency/channel rather than spread across the
    # band is usually RFI or a bad channel range, not real sources -- worth a look
    # before sinking time into dedup/rename/dry-run on a batch that might need
    # re-running with different SoFiA flagging.
    spectral_ref = diagnostics.find_spectral_reference(config.paths.raw_sofia_dir)
    if spectral_ref is None:
        logger.warning(
            "No cube FITS file with a recognisable frequency axis found under %s -- "
            "%s will show frequency only, not channel",
            config.paths.raw_sofia_dir,
            config.paths.frequency_flux_plot.name,
        )
        fig = diagnostics.build_frequency_flux_figure(combined)
    else:
        freq_ref_hz, chan_width_hz = spectral_ref
        fig = diagnostics.build_frequency_flux_figure(combined, freq_ref_hz, chan_width_hz)
    fig.savefig(config.paths.frequency_flux_plot, dpi=100, bbox_inches="tight")
    logger.info("Wrote %s", config.paths.frequency_flux_plot)


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)
    run(config)


if __name__ == "__main__":
    sys.exit(main())
