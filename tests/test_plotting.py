"""Tests for plotting.py. `load_source_cubelets` is tested against real cubelet FITS
files from the fixture (no synthetic data needed there -- it's pure I/O). Figure
construction uses real cubelets plus synthetic optical/continuum cutouts (no network),
and is checked for structural correctness (axis count, no exception, graceful
degradation with missing cutouts) -- not pixel-perfect image comparison, which isn't
practical for a unit test. A real end-to-end visual check (actual dry-run output
inspected by eye) is documented in the Phase 3 commit message instead.
"""

import dataclasses
from pathlib import Path

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.wcs import WCS
from matplotlib.figure import Figure
from matplotlib.patches import Ellipse

from hivalidate import catalogue, conversions
from hivalidate.cutouts.base import CutoutResult
from hivalidate.plotting import (
    _EXTERNAL_MATCH_COLORS,
    DISPLAY_FOV_FACTOR,
    build_true_detections_overview_figure,
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

    def test_all_nan_pv_data_shows_a_clear_placeholder_not_a_blank_panel(self):
        # Regression test: found live 2026-07-30 that SoFiA occasionally writes an
        # all-NaN PV cubelet for a real source (confirmed against the actual data --
        # 1/448 sources in the first full run_sofia batch; that source's own FITS
        # header even has PVD_PA = -NAN, SoFiA's own record that it couldn't
        # determine a kinematic position angle). Not a bug in this pipeline, but an
        # unlabelled blank panel looks exactly like one -- must say so explicitly.
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        nan_pv_cubelets = dataclasses.replace(
            cubelets, pv_data=np.full_like(cubelets.pv_data, np.nan)
        )
        fig = build_validation_figure(
            row, nan_pv_cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        ax_pv = fig.axes[-1]
        texts = [t.get_text() for t in ax_pv.texts]
        assert any("No PV data available" in t for t in texts)
        # No image should have been drawn either.
        assert len(ax_pv.images) == 0

    def test_normal_pv_data_is_unaffected_by_the_nan_check(self):
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        assert np.isfinite(cubelets.pv_data).any(), "fixture assumption changed"
        fig = build_validation_figure(
            row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        ax_pv = fig.axes[-1]
        assert len(ax_pv.images) == 1
        texts = [t.get_text() for t in ax_pv.texts]
        assert not any("No PV data available" in t for t in texts)

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


class TestBeamEllipsePlacement:
    """Regression tests for the bug reported live 2026-09-15: the beam ellipse was
    placed via a fixed 20-pixel offset in the cutout's own array, which only gives a
    fixed real angular offset if every source's cutout shares the same pixel scale
    and pixel count -- false in general (SkyView returns a fixed 300x300 pixel image
    regardless of the requested angular size). For a source with a smaller real
    field of view, that offset put the ellipse's own extent past the displayed zoom
    window on one or both axes -- clipped by the panel edge, per direct user report.
    """

    def _beam_pixel_offset_and_radius(self, fig, cubelets, center):
        ax_opt = fig.axes[0]
        ellipses = [p for p in ax_opt.patches if isinstance(p, Ellipse)]
        assert len(ellipses) == 1, "expected exactly one beam ellipse patch"
        wcs = ax_opt.wcs.celestial
        px, py = wcs.world_to_pixel_values(*ellipses[0].center)
        cx, cy = wcs.world_to_pixel_values(center.ra.deg, center.dec.deg)
        scales = wcs.proj_plane_pixel_scales()
        dx_arcsec = abs(px - cx) * scales[0].to(u.arcsec).value
        dy_arcsec = abs(py - cy) * scales[1].to(u.arcsec).value
        return dx_arcsec, dy_arcsec, cubelets.beam_maj_arcsec / 2

    def test_beam_ellipse_stays_fully_within_the_displayed_field_of_view(self):
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fov_arcsec = reference_field_of_view_arcsec(cubelets)
        fig = build_validation_figure(
            row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        center = SkyCoord(ra=row["ra"], dec=row["dec"], unit="deg")
        dx, dy, beam_half = self._beam_pixel_offset_and_radius(fig, cubelets, center)
        assert dx + beam_half <= fov_arcsec / 2
        assert dy + beam_half <= fov_arcsec / 2

    def test_stays_within_bounds_against_a_skyview_shaped_cutout(self):
        # Reproduces the real failure mode: a fixed 300x300 pixel cutout (SkyView's
        # actual behaviour) whose own pixel scale is derived from this specific
        # source's real field of view, not a hand-picked one -- confirmed to clip
        # under the old fixed-20-pixel-offset logic before this fix.
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fov_arcsec = reference_field_of_view_arcsec(cubelets)
        center = SkyCoord(ra=row["ra"], dec=row["dec"], unit="deg")
        skyview_shaped_optical = _fake_cutout(
            size=300, ra=center.ra.deg, dec=center.dec.deg, arcsec_per_pix=fov_arcsec / 300
        )
        fig = build_validation_figure(
            row, cubelets, optical=skyview_shaped_optical, continuum=_fake_cutout()
        )
        dx, dy, beam_half = self._beam_pixel_offset_and_radius(fig, cubelets, center)
        assert dx + beam_half <= fov_arcsec / 2
        assert dy + beam_half <= fov_arcsec / 2


class TestExternalRedshiftMatchOverlay:
    """Regression tests for the bug reported live 2026-09-15: hivalidate.crossmatch's
    match columns were added to the catalogue but never actually shown on the
    figure -- the legacy script overlaid a matched GAMA source as a marker on the
    optical panel and a dashed line at its velocity on the spectrum panel, and that
    behaviour was dropped during the port.
    """

    def _row_with_matches(
        self,
        matches: list[tuple[float, float]] | None = None,
        catalogue_name: str | None = "DESI",
        ids: list[int] | None = None,
    ) -> Table:
        """`matches`: list of (sep_arcsec, z) pairs -- defaults to a single match
        5" away at z=0.05. `ids`, if given, must be the same length as `matches`.
        """
        if matches is None:
            matches = [(5.0, 0.05)]
        row = _real_row()
        center = SkyCoord(ra=float(row["ra"]), dec=float(row["dec"]), unit="deg")
        positions = [
            center.spherical_offsets_by(sep * u.arcsec, 0 * u.arcsec) for sep, _ in matches
        ]
        data = {name: [row[name]] for name in row.colnames}
        data["external_z"] = [np.array([z for _, z in matches], dtype=float)]
        data["external_ra"] = [np.array([p.ra.deg for p in positions], dtype=float)]
        data["external_dec"] = [np.array([p.dec.deg for p in positions], dtype=float)]
        if catalogue_name is not None:
            data["external_catalogue_name"] = [catalogue_name]
        if ids is not None:
            assert len(ids) == len(matches)
            data["external_id"] = [np.array(ids, dtype=object)]
        return Table(data)[0]

    def test_overlays_marker_and_spectrum_line_labelled_with_the_catalogue_name(self):
        row = self._row_with_matches(matches=[(5.0, 0.05)], catalogue_name="DESI")
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(
            row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        ax_opt = fig.axes[0]
        assert len(ax_opt.collections) >= 1  # the scatter marker
        opt_legend = ax_opt.get_legend()
        assert opt_legend is not None
        assert any(t.get_text() == "DESI" for t in opt_legend.get_texts())

        ax_spec = fig.axes[2]
        spec_legend = ax_spec.get_legend()
        assert spec_legend is not None
        assert any(t.get_text() == "DESI" for t in spec_legend.get_texts())
        expected_vel = conversions.redshift_to_velocity(0.05)
        match_lines = [
            ln
            for ln in ax_spec.lines
            if ln.get_linestyle() == "--" and ln.get_color() in _EXTERNAL_MATCH_COLORS
        ]
        assert [ln.get_xdata()[0] for ln in match_lines] == pytest.approx([expected_vel])
        assert match_lines[0].get_color() == _EXTERNAL_MATCH_COLORS[0]

    def test_label_includes_the_catalogue_id_when_available(self):
        # Direct user request: the DESI catalogue was updated to include target_id,
        # and cross-matched sources should show it on the plot.
        row = self._row_with_matches(
            matches=[(5.0, 0.05)], catalogue_name="DESI", ids=[396330000123]
        )
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(
            row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        opt_legend = fig.axes[0].get_legend()
        assert any(t.get_text() == "DESI 396330000123" for t in opt_legend.get_texts())
        spec_legend = fig.axes[2].get_legend()
        assert any(t.get_text() == "DESI 396330000123" for t in spec_legend.get_texts())

    def test_label_omits_id_when_external_id_is_shorter_than_external_z(self):
        # This is the normal case when external_redshift_catalogue_id_column was
        # left unset: crossmatch_redshifts leaves every row's external_id an empty
        # array regardless of how many real matches external_z has. Must fall back
        # cleanly, not misalign via zip() truncating to the shorter array.
        base_row = self._row_with_matches(matches=[(5.0, 0.05), (12.0, 0.052)])
        data = {name: [base_row[name]] for name in base_row.colnames}
        data["external_id"] = [np.array([], dtype=object)]  # deliberately mismatched length
        row = Table(data)[0]
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(
            row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        opt_legend = fig.axes[0].get_legend()
        # Both matches show the identical "DESI" label -- no ID to distinguish them
        # by, and the redshift was deliberately dropped from the label (it's still
        # readable off the spectrum panel's own axes). Two separate legend entries
        # regardless, one per marker.
        assert [t.get_text() for t in opt_legend.get_texts()] == ["DESI", "DESI"]

    def test_overlays_a_marker_and_line_per_match_for_multiple_counterparts(self):
        # An HI detection can have more than one real optical counterpart (an
        # interacting pair, a gas-rich group) since HI is often more spatially
        # extended than any single galaxy it overlaps -- direct user feedback.
        row = self._row_with_matches(matches=[(5.0, 0.05), (12.0, 0.052)], catalogue_name="DESI")
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(
            row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        ax_opt = fig.axes[0]
        assert len(ax_opt.collections) >= 2  # one scatter marker per match
        opt_legend = ax_opt.get_legend()
        assert opt_legend is not None
        assert [t.get_text() for t in opt_legend.get_texts()] == ["DESI", "DESI"]

        ax_spec = fig.axes[2]
        match_lines = [
            ln
            for ln in ax_spec.lines
            if ln.get_linestyle() == "--" and ln.get_color() in _EXTERNAL_MATCH_COLORS
        ]
        assert len(match_lines) == 2
        vline_x = sorted(ln.get_xdata()[0] for ln in match_lines)
        expected = sorted(
            [conversions.redshift_to_velocity(0.05), conversions.redshift_to_velocity(0.052)]
        )
        assert vline_x == pytest.approx(expected)
        # Each match gets its own color, not just its own position -- distinguishable
        # even if two matches happened to sit at the same velocity.
        assert {ln.get_color() for ln in match_lines} == {
            _EXTERNAL_MATCH_COLORS[0],
            _EXTERNAL_MATCH_COLORS[1],
        }

    def test_falls_back_to_a_generic_label_when_catalogue_name_column_is_missing(self):
        # A match produced before external_catalogue_name existed -- must still show
        # something, not crash.
        row = self._row_with_matches(matches=[(5.0, 0.05)], catalogue_name=None)
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(
            row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        opt_legend = fig.axes[0].get_legend()
        assert opt_legend is not None
        assert any(t.get_text() == "External" for t in opt_legend.get_texts())

    def test_no_overlay_when_row_has_no_external_match_columns(self):
        row = _real_row()
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(
            row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        assert fig.axes[0].get_legend() is None
        assert fig.axes[2].get_legend() is None

    def test_no_overlay_when_external_z_is_empty(self):
        row = self._row_with_matches(matches=[])
        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82605_Removal_001_1")
        fig = build_validation_figure(
            row, cubelets, optical=_fake_cutout(), continuum=_fake_cutout()
        )
        assert fig.axes[0].get_legend() is None
        assert fig.axes[2].get_legend() is None


class TestBuildTrueDetectionsOverviewFigure:
    """Direct user request: a whole-field overview showing true detections'
    coadded moment-0 mosaic (postprocess.build_mosaic) as contours over an optical
    background of the whole field, to see the overall spatial distribution at a
    glance.
    """

    def _mosaic(self, data, size=50):
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
        wcs.wcs.crval = [315.4611, -55.8032]
        wcs.wcs.crpix = [size / 2, size / 2]
        wcs.wcs.cdelt = [-6.0 / 3600, 6.0 / 3600]
        return data, wcs

    def test_produces_a_single_panel_figure_with_the_field_name_in_the_title(self):
        optical = _fake_cutout(size=100, arcsec_per_pix=6.0)
        mosaic_data, mosaic_wcs = self._mosaic(np.zeros((50, 50)))
        fig = build_true_detections_overview_figure(optical, mosaic_data, mosaic_wcs, "SB82605")
        assert isinstance(fig, Figure)
        assert len(fig.axes) == 1
        assert "SB82605" in fig.axes[0].get_title()

    def test_all_zero_mosaic_does_not_raise(self):
        # build_mosaic fills every pixel with no reprojected true-detection cubelet
        # with exactly 0 -- a field with (so far) zero true detections is a
        # legitimate state, not an error, and must not crash while trying to
        # contour something that isn't there.
        optical = _fake_cutout(size=100, arcsec_per_pix=6.0)
        mosaic_data, mosaic_wcs = self._mosaic(np.zeros((50, 50)))
        fig = build_true_detections_overview_figure(optical, mosaic_data, mosaic_wcs, "SB82605")
        assert isinstance(fig, Figure)

    def test_mosaic_with_real_signal_draws_contours(self):
        optical = _fake_cutout(size=100, arcsec_per_pix=6.0)
        rng = np.random.default_rng(0)
        data = rng.normal(0, 1, size=(50, 50))
        data[20:25, 20:25] += 50  # a clear detection well above the noise
        mosaic_data, mosaic_wcs = self._mosaic(data)
        fig = build_true_detections_overview_figure(optical, mosaic_data, mosaic_wcs, "SB82605")
        assert len(fig.axes[0].collections) >= 1  # the contour

    def test_view_stays_pinned_to_the_optical_cutout_not_the_contours_full_extent(self):
        # Found live against real data: WCSAxes autoscales to include everything it's
        # been shown, including a contour plotted via a *different* WCS transform
        # (mosaic_wcs, a whole field spanning several degrees) -- without explicitly
        # pinning the view back to the optical image's own pixel extent, the axes
        # zoomed out to a huge, mostly-empty patch of sky with the actual cutout
        # shrunk into one corner.
        optical = _fake_cutout(size=100, arcsec_per_pix=6.0)
        rng = np.random.default_rng(0)
        data = rng.normal(0, 1, size=(50, 50))
        data[20:25, 20:25] += 50
        mosaic_data, mosaic_wcs = self._mosaic(data)
        fig = build_true_detections_overview_figure(optical, mosaic_data, mosaic_wcs, "SB82605")
        ax = fig.axes[0]
        xlim, ylim = ax.get_xlim(), ax.get_ylim()
        assert xlim == pytest.approx((-0.5, 99.5))
        assert ylim == pytest.approx((-0.5, 99.5))
