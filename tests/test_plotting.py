"""Tests for plotting.py. `load_source_cubelets` is tested against real cubelet FITS
files from the fixture (no synthetic data needed there -- it's pure I/O). Figure
construction uses real cubelets plus synthetic optical/continuum cutouts (no network),
and is checked for structural correctness (axis count, no exception, graceful
degradation with missing cutouts) -- not pixel-perfect image comparison, which isn't
practical for a unit test. A real end-to-end visual check (actual dry-run output
inspected by eye) is documented in the Phase 3 commit message instead.
"""

from pathlib import Path

import numpy as np
import pytest
from astropy import units as u
from astropy.wcs import WCS
from matplotlib.figure import Figure

from hivalidate import catalogue
from hivalidate.cutouts.base import CutoutResult
from hivalidate.plotting import (
    DISPLAY_FOV_FACTOR,
    build_validation_figure,
    load_source_cubelets,
    reference_field_of_view_arcsec,
)

_FIXTURE_RUN_DIR = Path(__file__).parent / "fixtures" / "run_sofia_mini"
FIXTURE_CUBELETS = _FIXTURE_RUN_DIR / "SB82605_Removal_001_cubelets"
FIXTURE_CATALOGUE = _FIXTURE_RUN_DIR / "SB82605_Removal_001_cat.xml"


def _fake_cutout(size=40, ra=315.4611, dec=-55.8032, arcsec_per_pix=1.7) -> CutoutResult:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.crpix = [size / 2, size / 2]
    wcs.wcs.cdelt = [-arcsec_per_pix / 3600, arcsec_per_pix / 3600]
    data = np.random.default_rng(0).normal(0, 1, size=(size, size))
    return CutoutResult(data=data, wcs=wcs, provenance="fake:test")


def _axis_fov_arcsec(ax) -> tuple[float, float]:
    """Real angular width/height an axis is actually displaying, computed from its
    own WCS pixel scale and current xlim/ylim -- independent of `_set_fov`'s own
    implementation, so this genuinely checks the panel's visible extent rather than
    re-deriving the same formula the code under test uses.
    """
    wcs = ax.wcs.celestial
    scales = wcs.proj_plane_pixel_scales()
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    width = abs(xlim[1] - xlim[0]) * scales[0].to(u.arcsec).value
    height = abs(ylim[1] - ylim[0]) * scales[1].to(u.arcsec).value
    return width, height


def _real_row(name="SoFiA J210149.89-554804.6"):
    table = catalogue.read_votable(FIXTURE_CATALOGUE)
    matches = table[table["name"] == name]
    assert len(matches) == 1, f"expected exactly one row for {name}"
    return matches[0]


class TestLoadSourceCubelets:
    def test_loads_real_fixture_cubelets(self):
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        assert cubelets.mom0.ndim == 2
        assert cubelets.mom1.shape == cubelets.mom0.shape
        assert cubelets.mom2.shape == cubelets.mom0.shape
        assert cubelets.pv_data.ndim == 2
        assert len(cubelets.spec_freq_hz) == len(cubelets.spec_flux_jy)
        assert cubelets.beam_maj_arcsec > 0
        assert cubelets.beam_min_arcsec > 0
        assert cubelets.freq_width_hz != 0

    def test_missing_source_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_source_cubelets(FIXTURE_CUBELETS, "does_not_exist")


class TestBuildValidationFigure:
    def test_produces_six_panel_figure_with_both_cutouts(self):
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(
            row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        assert isinstance(fig, Figure)
        assert len(fig.axes) >= 6  # 6 panels + 1 colorbar + 1 twinned spectrum axis
        assert row["name"] in fig._suptitle.get_text()

    def test_degrades_gracefully_with_no_optical_cutout(self):
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(row, cubelets, optical=None, continuum=_fake_cutout())
        assert isinstance(fig, Figure)
        titles = [ax.get_title() for ax in fig.axes]
        assert any("no cutout available" in t for t in titles)

    def test_degrades_gracefully_with_no_continuum_cutout(self):
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(row, cubelets, optical=_fake_cutout(), continuum=None)
        assert isinstance(fig, Figure)

    def test_degrades_gracefully_with_neither_cutout(self):
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(row, cubelets, optical=None, continuum=None)
        assert isinstance(fig, Figure)

    def test_never_calls_plt_show_or_touches_pyplot_state(self, monkeypatch):
        # This is the whole point of Figure-based construction (PLAN.md issue #3) --
        # if this function ever imports pyplot and calls show()/creates global state,
        # it stops being safe to call from inside a headless batch job. Guard it by
        # making pyplot.show unavailable/poisoned and confirming nothing breaks.
        import matplotlib.pyplot as plt

        def _poisoned_show(*a, **kw):
            raise AssertionError("build_validation_figure must never call plt.show()")

        monkeypatch.setattr(plt, "show", _poisoned_show)
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        build_validation_figure(row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout())

    def test_works_for_multiple_different_real_sources(self):
        # Different sources have different mom0/mom1/mom2/pv shapes and flux scales
        # -- loop a few real ones to catch a shape/broadcast assumption that happens
        # to hold for just one source.
        table = catalogue.read_votable(FIXTURE_CATALOGUE)
        for source_id, name in list(catalogue.id_to_name_mapping(table).items())[:5]:
            row = table[table["id"] == int(source_id)][0]
            cubelets = load_source_cubelets(FIXTURE_CUBELETS, f"SB82605_Removal_001_{source_id}")
            fig = build_validation_figure(
                row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
            )
            assert isinstance(fig, Figure), f"failed for {name}"


class TestAllSkyPanelsShareTheSameFieldOfView:
    """Regression tests for the bug reported live 2026-07-30: the continuum panel's
    displayed field of view was visibly wider than the optical/mom0/mom1 panels,
    because nothing pinned it (or the optical panel) to a common reference -- only
    mom0/mom1 borrowed the optical panel's raw pixel xlim, which only worked because
    they happened to share its exact WCS. optical and continuum are given
    deliberately different native pixel scales below (1.7 and 2.0 arcsec/pixel) --
    the real-world condition that exposed the bug (SkyView vs. the local continuum
    mosaic's own resolution never matched).
    """

    def _figure(self):
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        optical = _fake_cutout(size=100, arcsec_per_pix=1.7)
        continuum = _fake_cutout(size=60, arcsec_per_pix=2.0)
        fig = build_validation_figure(row, cubelets, optical=optical, continuum=continuum)
        return fig, cubelets

    def test_reference_fov_is_display_fov_factor_times_mom0s_own_footprint(self):
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fov = reference_field_of_view_arcsec(cubelets)

        wcs = cubelets.mom0_wcs.celestial
        scales = wcs.proj_plane_pixel_scales()
        ny, nx = cubelets.mom0.shape
        expected = (
            max(nx * scales[0].to(u.arcsec).value, ny * scales[1].to(u.arcsec).value)
            * DISPLAY_FOV_FACTOR
        )
        assert fov == pytest.approx(expected)

    def test_optical_and_continuum_panels_show_the_same_real_field_of_view(self):
        fig, cubelets = self._figure()
        ax_opt, ax_cont = fig.axes[0], fig.axes[1]

        opt_w, opt_h = _axis_fov_arcsec(ax_opt)
        cont_w, cont_h = _axis_fov_arcsec(ax_cont)

        # Loose tolerance: pixel-grid rounding on two different native resolutions
        # (1.7 vs 2.0 arcsec/pix here) means it can't be exact, but before the fix
        # the discrepancy was a large, visually-obvious ~30-70%, not a rounding error.
        assert opt_w == pytest.approx(cont_w, rel=0.05)
        assert opt_h == pytest.approx(cont_h, rel=0.05)

    def test_all_four_sky_panels_match_the_reference_fov(self):
        fig, cubelets = self._figure()
        expected_fov = reference_field_of_view_arcsec(cubelets)
        # fig.axes order (verified empirically, not assumed): 0=optical, 1=continuum,
        # 2=spectrum, 3=spectrum's twinned frequency axis (plain Axes, no WCS -- and
        # what pushes mom0/mom1 to indices 4/5 instead of 2/3), 4=mom0, 5=mom1,
        # 6=mom1's colorbar, 7=PV (a WCSAxes too, but angular-offset-vs-frequency,
        # not a sky panel, so deliberately excluded from this comparison).
        sky_panel_axes = {
            "optical": fig.axes[0],
            "continuum": fig.axes[1],
            "mom0": fig.axes[4],
            "mom1": fig.axes[5],
        }
        for label, ax in sky_panel_axes.items():
            width, height = _axis_fov_arcsec(ax)
            assert width == pytest.approx(expected_fov, rel=0.05), f"{label} width mismatch"
            assert height == pytest.approx(expected_fov, rel=0.05), f"{label} height mismatch"

    def test_matches_even_when_optical_cutout_is_missing(self):
        # display_wcs falls back to mom0_wcs when optical is None -- _set_fov must
        # still produce the same real FoV in that frame as everywhere else.
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        continuum = _fake_cutout(size=60, arcsec_per_pix=2.0)
        fig = build_validation_figure(row, cubelets, optical=None, continuum=continuum)
        expected_fov = reference_field_of_view_arcsec(cubelets)

        ax_cont = fig.axes[1]
        width, height = _axis_fov_arcsec(ax_cont)
        assert width == pytest.approx(expected_fov, rel=0.05)
        assert height == pytest.approx(expected_fov, rel=0.05)
