"""Tests for hivalidate.crossmatch -- cross-matching HI detections against an
external spectroscopic redshift catalogue (DESI, GAMA, ...) by position + velocity.
Uses the real run_sofia_mini fixture for the HI side (matching this repo's existing
catalogue-test convention, see test_catalogue.py) and small synthetic Tables built
in-test for the external-catalogue side, since there's no real external-catalogue
fixture shipped.
"""

from pathlib import Path

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table

from hivalidate import catalogue, conversions, crossmatch

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "run_sofia_mini"
REAL_SOURCE_NAME = "SoFiA J203213.07-563318.1"


def _real_hi_table() -> Table:
    paths = catalogue.find_run_catalogues(FIXTURE_DIR)
    combined = catalogue.combine_runs(paths)
    return catalogue.deduplicate_positional(combined).table


def _real_source_row(hi_table: Table) -> Table:
    row = hi_table[hi_table["name"] == REAL_SOURCE_NAME]
    assert len(row) == 1, "fixture assumption changed -- update this test's ground truth"
    return row


def _offset_position(center: SkyCoord, sep_arcsec: float) -> SkyCoord:
    """A real `sep_arcsec` away from `center`, computed via spherical trig (not a
    naive RA delta, which needs cos(dec) scaling to mean a real angular separation).
    """
    return center.spherical_offsets_by(sep_arcsec * u.arcsec, 0 * u.arcsec)


def _matching_z(row: Table) -> float:
    velocity_km_s = conversions.freq_to_velocity(float(row["freq"][0]))
    return velocity_km_s / conversions.SPEED_OF_LIGHT_KM_S


class TestReadExternalCatalogue:
    def _table(self) -> Table:
        return Table(
            {
                "z": [0.01, 0.02],
                "target_ra": [10.0, 20.0],
                "target_dec": [-5.0, 5.0],
                "other_column": ["a", "b"],
            }
        )

    def test_reads_votable_xml(self, tmp_path):
        path = tmp_path / "external.xml"
        self._table().write(path, format="votable")
        result = crossmatch.read_external_catalogue(path)
        assert list(result["z"]) == [0.01, 0.02]
        assert list(result["target_ra"]) == [10.0, 20.0]

    def test_reads_csv(self, tmp_path):
        path = tmp_path / "external.csv"
        self._table().write(path, format="ascii.csv")
        result = crossmatch.read_external_catalogue(path)
        assert list(result["z"]) == [0.01, 0.02]

    def test_reads_fits(self, tmp_path):
        path = tmp_path / "external.fits"
        self._table().write(path, format="fits")
        result = crossmatch.read_external_catalogue(path)
        assert list(result["z"]) == pytest.approx([0.01, 0.02])

    def test_custom_column_names_for_a_differently_named_catalogue(self, tmp_path):
        # e.g. GAMA-style RA/DEC/Z instead of DESI's target_ra/target_dec/z.
        path = tmp_path / "gama_style.csv"
        Table({"Z": [0.03], "RA": [15.0], "DEC": [-2.0]}).write(path, format="ascii.csv")
        result = crossmatch.read_external_catalogue(
            path, ra_column="RA", dec_column="DEC", z_column="Z"
        )
        assert list(result["Z"]) == [0.03]

    def test_missing_column_raises_a_clear_error(self, tmp_path):
        path = tmp_path / "bad.csv"
        Table({"z": [0.01], "ra": [1.0]}).write(path, format="ascii.csv")  # no target_dec
        with pytest.raises(ValueError, match="target_dec"):
            crossmatch.read_external_catalogue(path)


class TestCrossmatchRedshifts:
    def test_matches_a_real_source_within_tolerance(self):
        hi_table = _real_hi_table()
        row = _real_source_row(hi_table)
        center = SkyCoord(ra=float(row["ra"][0]), dec=float(row["dec"][0]), unit="deg")
        offset = _offset_position(center, sep_arcsec=1.0)
        matching_z = _matching_z(row)

        external = Table(
            {"z": [matching_z], "target_ra": [offset.ra.deg], "target_dec": [offset.dec.deg]}
        )
        result = crossmatch.crossmatch_redshifts(hi_table, external)
        assert result.n_matched == 1

        matched_row = result.table[result.table["name"] == REAL_SOURCE_NAME]
        assert matched_row["external_z"][0] == pytest.approx(matching_z)
        assert matched_row["external_sep_arcsec"][0] == pytest.approx(1.0, abs=1e-3)
        assert not np.isnan(matched_row["external_vel_diff_km_s"][0])

        other_rows = result.table[result.table["name"] != REAL_SOURCE_NAME]
        assert np.all(np.isnan(other_rows["external_z"]))

    def test_position_within_tolerance_but_velocity_too_different_does_not_match(self):
        hi_table = _real_hi_table()
        row = _real_source_row(hi_table)
        center = SkyCoord(ra=float(row["ra"][0]), dec=float(row["dec"][0]), unit="deg")
        # 10,000 km/s away -- no realistic vel_tol_wm50_factor/vel_tol_base_km_s covers this.
        far_velocity_km_s = conversions.freq_to_velocity(float(row["freq"][0])) + 10_000
        far_off_z = far_velocity_km_s / conversions.SPEED_OF_LIGHT_KM_S

        external = Table(
            {"z": [far_off_z], "target_ra": [center.ra.deg], "target_dec": [center.dec.deg]}
        )
        result = crossmatch.crossmatch_redshifts(hi_table, external)
        assert result.n_matched == 0

    def test_position_outside_sep_tolerance_does_not_match(self):
        hi_table = _real_hi_table()
        row = _real_source_row(hi_table)
        center = SkyCoord(ra=float(row["ra"][0]), dec=float(row["dec"][0]), unit="deg")
        offset = _offset_position(center, sep_arcsec=3600.0)  # 1 degree -- way outside 30"
        matching_z = _matching_z(row)

        external = Table(
            {"z": [matching_z], "target_ra": [offset.ra.deg], "target_dec": [offset.dec.deg]}
        )
        result = crossmatch.crossmatch_redshifts(hi_table, external, sep_arcsec=30.0)
        assert result.n_matched == 0

    def test_picks_the_closer_of_two_candidates_within_both_tolerances(self):
        hi_table = _real_hi_table()
        row = _real_source_row(hi_table)
        center = SkyCoord(ra=float(row["ra"][0]), dec=float(row["dec"][0]), unit="deg")
        far, near = _offset_position(center, 5.0), _offset_position(center, 1.0)
        matching_z = _matching_z(row)

        external = Table(
            {
                "z": [matching_z, matching_z],
                "target_ra": [far.ra.deg, near.ra.deg],
                "target_dec": [far.dec.deg, near.dec.deg],
            }
        )
        result = crossmatch.crossmatch_redshifts(hi_table, external)
        matched_row = result.table[result.table["name"] == REAL_SOURCE_NAME]
        assert matched_row["external_sep_arcsec"][0] == pytest.approx(1.0, abs=1e-3)

    def test_empty_hi_table_is_a_no_op(self):
        hi_table = _real_hi_table()[:0]
        external = Table({"z": [0.01], "target_ra": [1.0], "target_dec": [1.0]})
        result = crossmatch.crossmatch_redshifts(hi_table, external)
        assert len(result.table) == 0
        assert result.n_matched == 0

    def test_empty_external_table_leaves_every_row_unmatched(self):
        hi_table = _real_hi_table()
        external = Table({"z": [], "target_ra": [], "target_dec": []})
        result = crossmatch.crossmatch_redshifts(hi_table, external)
        assert result.n_matched == 0
        assert np.all(np.isnan(result.table["external_z"]))
