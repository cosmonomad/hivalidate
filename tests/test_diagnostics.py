"""Tests for the combine-stage frequency-vs-flux diagnostic plot, against the real
run_sofia_mini fixture catalogues and cubelets.

Regression coverage for a real bug found by inspecting the actual plot against real
SB82605 data: an earlier version used the catalogue's own `z` column directly as
"channel", which looked plausible (roughly monotonic with frequency) but was wrong --
`z` is a pixel coordinate local to each run's own input sub-cube, and different runs
in this field cover different frequency-axis sections, so the same `z` value means a
different real frequency depending which run a source came from. Fixed by computing
channel from frequency using the reference frequency/channel width read directly from
a cube FITS header (`CRVAL3`/`CDELT3`), confirmed identical across every run.
"""

from pathlib import Path

import numpy as np
from astropy.io import fits
from matplotlib.figure import Figure

from hivalidate import catalogue, diagnostics

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "run_sofia_mini"


def _combined_table():
    paths = catalogue.find_run_catalogues(FIXTURE_DIR)
    return catalogue.combine_runs(paths)


class TestFindSpectralReference:
    def test_reads_crval3_and_cdelt3_from_a_real_cube_header(self):
        result = diagnostics.find_spectral_reference(FIXTURE_DIR)
        assert result is not None
        freq_ref_hz, chan_width_hz = result

        # Verified directly against the fixture's own FITS headers, not derived from
        # the function under test.
        expected_header = fits.getheader(
            FIXTURE_DIR / "SB82605_Removal_001_cubelets" / "SB82605_Removal_001_1_cube.fits"
        )
        assert freq_ref_hz == expected_header["CRVAL3"]
        assert chan_width_hz == expected_header["CDELT3"]

    def test_reference_is_identical_across_runs_in_different_spectral_groups(self):
        # SB82605_Removal_001 and SB82605_Removal_011 belong to different spectral
        # groups in the real full dataset (different z-offset, same CRVAL3/CDELT3) --
        # confirm both runs' cube headers agree, independent of which one
        # find_spectral_reference happens to pick up first.
        header_001 = fits.getheader(
            FIXTURE_DIR / "SB82605_Removal_001_cubelets" / "SB82605_Removal_001_1_cube.fits"
        )
        header_011 = fits.getheader(
            FIXTURE_DIR / "SB82605_Removal_011_cubelets" / "SB82605_Removal_011_10_cube.fits"
        )
        assert (header_001["CRVAL3"], header_001["CDELT3"]) == (
            header_011["CRVAL3"],
            header_011["CDELT3"],
        )

    def test_returns_none_if_no_cube_files_exist(self, tmp_path):
        assert diagnostics.find_spectral_reference(tmp_path) is None


class TestBuildFrequencyFluxFigure:
    def test_without_a_spectral_reference_has_only_the_frequency_axis(self):
        fig = diagnostics.build_frequency_flux_figure(_combined_table())
        assert isinstance(fig, Figure)
        assert len(fig.axes) == 1
        assert fig.axes[0].get_xlabel() == "Frequency (MHz)"

    def test_with_a_spectral_reference_adds_a_channel_twiny_axis(self):
        table = _combined_table()
        freq_ref_hz, chan_width_hz = diagnostics.find_spectral_reference(FIXTURE_DIR)
        fig = diagnostics.build_frequency_flux_figure(table, freq_ref_hz, chan_width_hz)
        assert len(fig.axes) == 2

        ax, ax_chan = fig.axes
        assert ax.get_xlabel() == "Frequency (MHz)"
        assert ax_chan.get_xlabel() == "Channel"

    def test_channel_is_computed_from_frequency_not_from_the_z_column(self):
        table = _combined_table()
        freq_ref_hz, chan_width_hz = diagnostics.find_spectral_reference(FIXTURE_DIR)
        fig = diagnostics.build_frequency_flux_figure(table, freq_ref_hz, chan_width_hz)
        ax_chan = fig.axes[1]
        (collection,) = ax_chan.collections
        plotted_chan = np.sort(collection.get_offsets()[:, 0])

        freq_hz = np.asarray(table["freq"], dtype=float)
        expected_chan = np.sort((freq_hz - freq_ref_hz) / chan_width_hz)
        np.testing.assert_allclose(plotted_chan, expected_chan)

        # The bug this replaced: raw 'z' does NOT equal the correct channel for
        # every source, because it's local to each run's own spectral sub-cube.
        z = np.asarray(table["z"], dtype=float)
        assert not np.allclose(np.sort(z), expected_chan)

    def test_plots_exactly_one_point_per_source(self):
        table = _combined_table()
        fig = diagnostics.build_frequency_flux_figure(table)
        ax = fig.axes[0]
        (collection,) = ax.collections
        assert collection.get_offsets().shape[0] == len(table)

    def test_flux_axis_is_log10_of_f_sum(self):
        table = _combined_table()
        fig = diagnostics.build_frequency_flux_figure(table)
        ax = fig.axes[0]
        (collection,) = ax.collections
        plotted_y = np.sort(collection.get_offsets()[:, 1])
        expected_y = np.sort(np.log10(np.asarray(table["f_sum"], dtype=float)))
        np.testing.assert_allclose(plotted_y, expected_y)

    def test_frequency_axis_is_freq_column_in_mhz_not_hz(self):
        table = _combined_table()
        fig = diagnostics.build_frequency_flux_figure(table)
        ax = fig.axes[0]
        (collection,) = ax.collections
        plotted_x = np.sort(collection.get_offsets()[:, 0])
        expected_x = np.sort(np.asarray(table["freq"], dtype=float) * 1e-6)
        np.testing.assert_allclose(plotted_x, expected_x)
        # Sanity check this is really MHz (~1300ish for this fixture's HI band), not Hz.
        assert 1000 < plotted_x.min() < 2000
