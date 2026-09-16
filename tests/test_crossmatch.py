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

    def test_id_column_is_optional_and_ignored_when_unset(self, tmp_path):
        path = tmp_path / "external.csv"
        self._table().write(path, format="ascii.csv")  # no id column at all
        result = crossmatch.read_external_catalogue(path)  # must not raise
        assert list(result["z"]) == [0.01, 0.02]

    def test_id_column_is_validated_when_given(self, tmp_path):
        path = tmp_path / "external.csv"
        self._table().write(path, format="ascii.csv")  # no target_id column
        with pytest.raises(ValueError, match="target_id"):
            crossmatch.read_external_catalogue(path, id_column="target_id")

    def test_reads_id_column_when_present(self, tmp_path):
        path = tmp_path / "external_with_id.csv"
        table = self._table()
        table["target_id"] = [111, 222]
        table.write(path, format="ascii.csv")
        result = crossmatch.read_external_catalogue(path, id_column="target_id")
        assert list(result["target_id"]) == [111, 222]


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
        result = crossmatch.crossmatch_redshifts(hi_table, external, catalogue_name="DESI")
        assert result.n_matched == 1

        matched_row = result.table[result.table["name"] == REAL_SOURCE_NAME][0]
        assert len(matched_row["external_z"]) == 1
        assert matched_row["external_z"][0] == pytest.approx(matching_z)
        assert matched_row["external_ra"][0] == pytest.approx(offset.ra.deg)
        assert matched_row["external_dec"][0] == pytest.approx(offset.dec.deg)
        assert matched_row["external_sep_arcsec"][0] == pytest.approx(1.0, abs=1e-3)
        assert len(matched_row["external_vel_diff_km_s"]) == 1
        assert matched_row["external_catalogue_name"] == "DESI"
        # id_column wasn't given -- external_id stays empty even on a matched row,
        # not length-mismatched garbage.
        assert len(matched_row["external_id"]) == 0

        other_rows = result.table[result.table["name"] != REAL_SOURCE_NAME]
        assert all(len(z) == 0 for z in other_rows["external_z"])
        assert all(len(ra) == 0 for ra in other_rows["external_ra"])
        assert np.all(other_rows["external_catalogue_name"] == "")

    def test_includes_matched_ids_when_id_column_given(self):
        hi_table = _real_hi_table()
        row = _real_source_row(hi_table)
        center = SkyCoord(ra=float(row["ra"][0]), dec=float(row["dec"][0]), unit="deg")
        offset = _offset_position(center, sep_arcsec=1.0)
        matching_z = _matching_z(row)

        external = Table(
            {
                "z": [matching_z],
                "target_ra": [offset.ra.deg],
                "target_dec": [offset.dec.deg],
                "target_id": [396330000123],
            }
        )
        result = crossmatch.crossmatch_redshifts(hi_table, external, id_column="target_id")
        matched_row = result.table[result.table["name"] == REAL_SOURCE_NAME][0]
        assert list(matched_row["external_id"]) == [396330000123]

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

    def test_keeps_every_candidate_within_both_tolerances_closest_first(self):
        # An HI detection can have more than one real optical counterpart (an
        # interacting pair, a gas-rich group) since HI is often more spatially
        # extended than any single galaxy it overlaps -- direct user feedback. Both
        # candidates here are equally good velocity matches, so both should survive,
        # ordered closest-in-position first.
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
        assert result.n_matched == 1  # one HI *source* has matches, even though 2 pairs exist
        matched_row = result.table[result.table["name"] == REAL_SOURCE_NAME][0]
        assert len(matched_row["external_sep_arcsec"]) == 2
        assert matched_row["external_sep_arcsec"][0] == pytest.approx(1.0, abs=1e-3)
        assert matched_row["external_sep_arcsec"][1] == pytest.approx(5.0, abs=1e-3)

    def test_a_closer_interloper_does_not_mask_a_farther_real_match(self):
        # Regression test for a real bug (dev session 2026-09-15): an earlier version
        # matched only the single nearest-position candidate and rejected the whole
        # source if that one failed velocity tolerance, even when a farther-but-
        # still-within-sep_arcsec candidate was a good velocity match. Confirmed
        # against real DESI data: a positionally closer but physically unrelated
        # interloper (~11,000 km/s away) masked a real counterpart sitting 15" away.
        hi_table = _real_hi_table()
        row = _real_source_row(hi_table)
        center = SkyCoord(ra=float(row["ra"][0]), dec=float(row["dec"][0]), unit="deg")
        interloper_pos = _offset_position(center, sep_arcsec=2.0)
        real_match_pos = _offset_position(center, sep_arcsec=15.0)
        matching_z = _matching_z(row)
        interloper_z = matching_z + 10_000 / conversions.SPEED_OF_LIGHT_KM_S  # ~10,000 km/s away

        external = Table(
            {
                "z": [interloper_z, matching_z],
                "target_ra": [interloper_pos.ra.deg, real_match_pos.ra.deg],
                "target_dec": [interloper_pos.dec.deg, real_match_pos.dec.deg],
            }
        )
        result = crossmatch.crossmatch_redshifts(hi_table, external, sep_arcsec=30.0)
        matched_row = result.table[result.table["name"] == REAL_SOURCE_NAME][0]
        # The interloper fails velocity tolerance outright, so it's never a
        # candidate at all -- only the real match should appear.
        assert len(matched_row["external_z"]) == 1
        assert matched_row["external_z"][0] == pytest.approx(matching_z)
        assert matched_row["external_sep_arcsec"][0] == pytest.approx(15.0, abs=1e-3)

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
        assert all(len(z) == 0 for z in result.table["external_z"])
