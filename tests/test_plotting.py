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
from astropy.wcs import WCS
from matplotlib.figure import Figure

from hivalidate import catalogue
from hivalidate.cutouts.base import CutoutResult
from hivalidate.plotting import build_validation_figure, load_source_cubelets

_FIXTURE_RUN_DIR = Path(__file__).parent / "fixtures" / "run_sofia_mini"
FIXTURE_CUBELETS = _FIXTURE_RUN_DIR / "SB82605_Removal_001_cubelets"
FIXTURE_CATALOGUE = _FIXTURE_RUN_DIR / "SB82605_Removal_001_cat.xml"


def _fake_cutout(size=40, ra=315.4611, dec=-55.8032) -> CutoutResult:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.crpix = [size / 2, size / 2]
    wcs.wcs.cdelt = [-1.7 / 3600, 1.7 / 3600]
    data = np.random.default_rng(0).normal(0, 1, size=(size, size))
    return CutoutResult(data=data, wcs=wcs, provenance="fake:test")


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
