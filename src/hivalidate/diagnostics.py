"""Catalogue-level diagnostic plots -- distinct from `plotting.py`'s per-source
validation figures, which need cubelets and cutouts for one source at a time. This
one just needs a catalogue table (plus, for the channel axis, one cube FITS header).

First (and so far only) one: integrated flux vs frequency and channel, from
`legacy/plot_detections.py`'s combine-stage QA plot. Useful for spotting whether
detections cluster at particular frequencies/channels rather than spreading roughly
evenly across the band -- a symptom of RFI or a bad channel range producing a burst
of spurious detections, which the combine stage's own row-count log line can't show.

Pure function (table in, `Figure` out -- no file I/O, no `plt.show()`), same
testability pattern as `plotting.build_validation_figure`: `hivalidate.cli.combine`
is the only thing that saves this to disk.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table
from matplotlib.figure import Figure


def find_spectral_reference(raw_sofia_dir: str | Path) -> tuple[float, float] | None:
    """Reads the spectral-axis reference frequency (`CRVAL3`, Hz) and channel width
    (`CDELT3`, Hz/channel) from the first cube FITS file found under
    `raw_sofia_dir`'s per-run `*_cubelets/` directories.

    Deliberately does *not* use the catalogue's own `z` column for this, even though
    `z` looks like a ready-made channel number -- found live against the real
    SB82605 data: `z` is a pixel coordinate local to each run's own input sub-cube,
    and different runs' sub-cubes cover different sections of the frequency axis (in
    this field's case, 5 groups of ~9 runs each, confirmed by fitting freq-vs-z per
    run: identical slope of 18518.5185 Hz/pixel everywhere, but a *different*
    intercept per group). Naively combining raw `z` across runs -- what an earlier
    version of this function did -- produces a channel axis where the same z value
    means a different real frequency depending which run a source came from, visibly
    wrong once plotted. `CRVAL3`/`CDELT3`, by contrast, are confirmed identical across
    every run's cubelets (they describe the one shared parent cube each run's
    sub-cube was cut from), so a channel computed from frequency using them is
    globally consistent no matter which run a source came from.

    Returns `None` (not an error) if no cube file with a recognisable frequency axis
    can be found, so the diagnostic plot degrades to frequency-only rather than
    blocking `hivalidate-combine` over a missing/differently-laid-out cubelets
    directory.
    """
    for cube_path in sorted(Path(raw_sofia_dir).glob("*_cubelets/*_cube.fits")):
        header = fits.getheader(cube_path)
        if str(header.get("CTYPE3", "")).upper().startswith("FREQ"):
            return float(header["CRVAL3"]), float(header["CDELT3"])
    return None


def build_frequency_flux_figure(
    table: Table, freq_ref_hz: float | None = None, chan_width_hz: float | None = None
) -> Figure:
    """Scatter of log10(integrated flux) against frequency (bottom x-axis, MHz) and,
    if `freq_ref_hz`/`chan_width_hz` are given (see `find_spectral_reference`),
    channel (top x-axis): `channel = (freq_hz - freq_ref_hz) / chan_width_hz`. Omit
    both to get a frequency-only plot when no spectral reference could be found.
    """
    freq_hz = np.asarray(table["freq"], dtype=float)
    freq_mhz = freq_hz * 1e-6
    log_flux = np.log10(np.asarray(table["f_sum"], dtype=float))

    fig = Figure(figsize=(10, 6))
    ax = fig.add_subplot(111)
    ax.scatter(freq_mhz, log_flux, s=4, linewidth=0)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel(r"log$_{10}$(Integrated flux / Jy Hz)")
    ax.set_title(f"{len(table)} combined detections: integrated flux vs frequency")
    ax.grid(True, alpha=0.3)

    if freq_ref_hz is not None and chan_width_hz is not None:
        channel = (freq_hz - freq_ref_hz) / chan_width_hz
        # Same data, plotted again against channel on an independently auto-scaled
        # twin x-axis -- since channel is an exact affine function of frequency here
        # (not approximated), the two scatters land at matching x-positions.
        ax_chan = ax.twiny()
        ax_chan.scatter(channel, log_flux, s=4, linewidth=0)
        ax_chan.set_xlabel("Channel")

    fig.tight_layout()
    return fig
