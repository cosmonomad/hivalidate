"""Tests for postprocess.py. filter_by_qa/write_validation_csv/extract_cubelets use
real fixture data (via combine -> dedup -> rename, same pattern as other CLI tests).
build_mosaic uses small synthetic FITS (fast, no dependency on the real ~50MB
data/run_sofia/mom0.fits) -- that real file was checked separately, see the Phase 5
commit message.
"""

import csv
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

from hivalidate import catalogue, conversions, postprocess
from hivalidate.cli import combine, dedup, rename
from hivalidate.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def prepared_config(tmp_path):
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    config.paths.work_dir = tmp_path / "work"
    combine.run(config)
    dedup.run(config)
    rename.run(config)
    return config


def _fake_validated_table():
    return Table(
        {
            "name": [
                "SoFiA J000000.00-300000.0",
                "SoFiA J000001.00-300000.0",
                "SoFiA J000002.00-300000.0",
            ],
            "ra": [0.0, 0.001, 0.002],
            "qa": [1.0, 0.0, float("nan")],
            # add_derived_physical_columns' inputs -- SoFiA's native frequency-domain
            # units, matching real catalogue column names.
            "freq": [1.40e9, 1.35e9, 1.30e9],
            "w20": [2.0e5, 1.8e5, 1.6e5],
            "w50": [1.5e5, 1.3e5, 1.1e5],
            "wm50": [1.4e5, 1.2e5, 1.0e5],
            "f_sum": [10.0, 5.0, 2.0],
            "err_f_sum": [0.5, 0.3, 0.1],
            # write_validation_csv's _CSV_DROPPED_COLUMNS -- present here so those
            # tests exercise the real drop, not just the absence of an error.
            "source_run": ["run1", "run1", "run2"],
            "external_ra": [0.0, 0.001, 0.002],
            "external_dec": [-30.0, -30.0, -30.0],
            "external_z": [0.01, 0.02, 0.03],
        }
    )


class TestFilterByQa:
    def test_selects_only_matching_qa_values(self):
        table = _fake_validated_table()
        result = postprocess.filter_by_qa(table, {1.0})
        assert list(result["name"]) == ["SoFiA J000000.00-300000.0"]

    def test_excludes_unreviewed_nan_rows(self):
        table = _fake_validated_table()
        result = postprocess.filter_by_qa(table, {0.0, 1.0, 2.0, 3.0})
        assert len(result) == 2  # the NaN row is never selected by any real qa value

    def test_can_select_multiple_qa_values_at_once(self):
        table = _fake_validated_table()
        result = postprocess.filter_by_qa(table, {0.0, 1.0})
        assert len(result) == 2


class TestWriteValidationCsv:
    def test_writes_a_readable_csv_with_matching_row_count(self, tmp_path):
        table = _fake_validated_table()[:2]
        out = tmp_path / "out.csv"
        postprocess.write_validation_csv(table, out)
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 2
        assert rows[0]["name"] == "SoFiA J000000.00-300000.0"

    def test_creates_parent_directory_if_missing(self, tmp_path):
        table = _fake_validated_table()[:1]
        out = tmp_path / "nested" / "dir" / "out.csv"
        postprocess.write_validation_csv(table, out)
        assert out.exists()

    def test_adds_derived_physical_columns(self, tmp_path):
        table = _fake_validated_table()[:1]
        out = tmp_path / "out.csv"
        postprocess.write_validation_csv(table, out)
        with open(out) as fh:
            row = next(csv.DictReader(fh))
        for column in (
            "redshift",
            "velocity_km_s",
            "w20_km_s",
            "w50_km_s",
            "wm50_km_s",
            "log_hi_mass_msun",
            "log_hi_mass_msun_err",
        ):
            assert column in row
            assert row[column] != ""

    def test_drops_internal_and_redundant_columns(self, tmp_path):
        table = _fake_validated_table()[:1]
        out = tmp_path / "out.csv"
        postprocess.write_validation_csv(table, out)
        with open(out) as fh:
            header = next(csv.reader(fh))
        for column in postprocess._CSV_DROPPED_COLUMNS:
            assert column not in header
        # sep_arcsec/vel_diff/id/catalogue_name are still useful for judging a
        # cross-match without opening the dry-run plot -- not dropped.
        assert "name" in header

    def test_missing_external_columns_do_not_raise(self, tmp_path):
        # No crossmatch configured -> the table has no external_* columns at all;
        # the drop step must tolerate columns that were never there.
        table = _fake_validated_table()[:1]
        table.remove_columns(["external_ra", "external_dec", "external_z"])
        out = tmp_path / "out.csv"
        postprocess.write_validation_csv(table, out)  # must not raise
        assert out.exists()


class TestAddDerivedPhysicalColumns:
    def test_matches_direct_conversions_calls(self):
        table = _fake_validated_table()
        result = postprocess.add_derived_physical_columns(table)
        freq = np.asarray(table["freq"])
        assert np.allclose(result["redshift"], conversions.freq_to_redshift(freq))
        assert np.allclose(result["velocity_km_s"], conversions.freq_to_velocity(freq))
        for width_column in ("w20", "w50", "wm50"):
            expected = conversions.freq_width_to_velocity_dispersion(
                np.asarray(table[width_column]), freq
            )
            assert np.allclose(result[f"{width_column}_km_s"], expected)

    def test_hi_mass_matches_direct_conversions_call(self):
        table = _fake_validated_table()
        result = postprocess.add_derived_physical_columns(table)
        freq = np.asarray(table["freq"])
        redshift = conversions.freq_to_redshift(freq)
        expected_mass = conversions.hi_mass(
            np.asarray(table["f_sum"]), redshift, rest_frame="frequency"
        )
        assert np.allclose(result["log_hi_mass_msun"], expected_mass)

    def test_hi_mass_error_scales_with_relative_flux_error(self):
        table = _fake_validated_table()
        result = postprocess.add_derived_physical_columns(table)
        f_sum = np.asarray(table["f_sum"])
        err_f_sum = np.asarray(table["err_f_sum"])
        expected_err = np.abs(err_f_sum / f_sum) / np.log(10)
        assert np.allclose(result["log_hi_mass_msun_err"], expected_err)

    def test_does_not_mutate_the_input_table(self):
        table = _fake_validated_table()
        postprocess.add_derived_physical_columns(table)
        assert "redshift" not in table.colnames

    def test_empty_table_does_not_raise(self):
        # astropy's Cosmology.luminosity_distance raises on a size-0 array rather
        # than returning an empty one -- found live: a QA class with zero sources
        # reviewed so far (a normal state, not an error) crashed the whole
        # postprocess run before this was guarded against.
        table = _fake_validated_table()[:0]
        result = postprocess.add_derived_physical_columns(table)
        assert len(result) == 0
        assert "log_hi_mass_msun" in result.colnames


class TestExtractCubelets:
    def test_copies_matching_files_for_given_names(self, prepared_config, tmp_path):
        deduped = catalogue.read_votable(prepared_config.paths.deduped_catalogue)
        names = [str(n) for n in deduped["name"][:2]]
        output_dir = tmp_path / "true_cubelets"

        count = postprocess.extract_cubelets(
            prepared_config.paths.renamed_cubelets_dir, output_dir, names
        )

        assert count > 0
        copied_files = list(output_dir.iterdir())
        assert len(copied_files) == count
        for name in names:
            prefix = name.replace(" ", "_")
            assert any(f.name.startswith(prefix + "_") for f in copied_files)

    def test_unmatched_name_contributes_zero_files_not_an_error(self, prepared_config, tmp_path):
        output_dir = tmp_path / "true_cubelets"
        count = postprocess.extract_cubelets(
            prepared_config.paths.renamed_cubelets_dir, output_dir, ["SoFiA J999999.99-999999.9"]
        )
        assert count == 0

    def test_preserves_file_content(self, prepared_config, tmp_path):
        deduped = catalogue.read_votable(prepared_config.paths.deduped_catalogue)
        name = str(deduped["name"][0])
        prefix = name.replace(" ", "_")
        output_dir = tmp_path / "true_cubelets"
        postprocess.extract_cubelets(prepared_config.paths.renamed_cubelets_dir, output_dir, [name])

        original = prepared_config.paths.renamed_cubelets_dir / f"{prefix}_mom0.fits"
        copied = output_dir / f"{prefix}_mom0.fits"
        assert copied.read_bytes() == original.read_bytes()


class TestExtractPlots:
    def test_copies_matching_pngs_for_given_names(self, tmp_path):
        dry_run_dir = tmp_path / "dry_run"
        dry_run_dir.mkdir()
        (dry_run_dir / "SoFiA_J000000.00-300000.0.png").write_bytes(b"fake-png-bytes")
        (dry_run_dir / "SoFiA_J000001.00-300000.0.png").write_bytes(b"other-png-bytes")
        output_dir = tmp_path / "true_plots"

        count = postprocess.extract_plots(dry_run_dir, output_dir, ["SoFiA J000000.00-300000.0"])

        assert count == 1
        copied = list(output_dir.iterdir())
        assert len(copied) == 1
        assert copied[0].name == "SoFiA_J000000.00-300000.0.png"
        assert copied[0].read_bytes() == b"fake-png-bytes"

    def test_unmatched_name_contributes_zero_files_not_an_error(self, tmp_path):
        dry_run_dir = tmp_path / "dry_run"
        dry_run_dir.mkdir()
        output_dir = tmp_path / "true_plots"
        count = postprocess.extract_plots(dry_run_dir, output_dir, ["SoFiA J999999.99-999999.9"])
        assert count == 0


@pytest.fixture
def field_mosaic_file(tmp_path):
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
    wcs.wcs.crval = [10.0, -30.0]
    wcs.wcs.crpix = [50, 50]
    wcs.wcs.cdelt = [-0.001, 0.001]
    data = np.zeros((100, 100))
    path = tmp_path / "field_mom0.fits"
    fits.writeto(path, data, wcs.to_header(), overwrite=True)
    return path


def _synthetic_cutout(tmp_path, name, ra, dec, value, size=10):
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.crpix = [size / 2, size / 2]
    wcs.wcs.cdelt = [-0.001, 0.001]
    data = np.full((size, size), value)
    path = tmp_path / f"{name}_mom0.fits"
    fits.writeto(path, data, wcs.to_header(), overwrite=True)
    return path


class TestFieldCenterAndFov:
    def test_returns_the_fields_own_real_center_and_angular_size(self, field_mosaic_file):
        center, fov_arcsec = postprocess.field_center_and_fov(field_mosaic_file)
        # A few pixels' worth of tolerance -- (nx/2, ny/2) is close to but not
        # exactly the array's true center (at nx/2 - 0.5 in 0-based coordinates),
        # a difference that's negligible at any real field's actual scale.
        assert center.ra.deg == pytest.approx(10.0, abs=5e-3)
        assert center.dec.deg == pytest.approx(-30.0, abs=5e-3)
        # 100x100 pixels at 0.001 deg/pixel.
        assert fov_arcsec == pytest.approx(100 * 0.001 * 3600, rel=0.01)


class TestBuildMosaic:
    def test_output_matches_field_mosaic_shape_and_wcs(self, tmp_path, field_mosaic_file):
        cutout = _synthetic_cutout(tmp_path, "src1", ra=10.0, dec=-30.0, value=5.0)
        output = tmp_path / "mosaic.fits"

        data = postprocess.build_mosaic(field_mosaic_file, [cutout], output)

        field_shape = fits.getdata(field_mosaic_file).shape
        assert data.shape == field_shape
        with fits.open(output) as hdul:
            assert hdul[0].data.shape == field_shape
            # 2D output WCS (celestial only), matching what build_validation_figure
            # and the other backends all expect -- not the raw field header's WCS.
            assert WCS(hdul[0].header).pixel_n_dim == 2

    def test_places_cutout_value_near_its_own_sky_position(self, tmp_path, field_mosaic_file):
        cutout = _synthetic_cutout(tmp_path, "src1", ra=10.0, dec=-30.0, value=7.5)
        output = tmp_path / "mosaic.fits"
        data = postprocess.build_mosaic(field_mosaic_file, [cutout], output)

        field_wcs = WCS(fits.getheader(field_mosaic_file))
        x, y = field_wcs.wcs_world2pix(10.0, -30.0, 0)
        region = data[int(y) - 2 : int(y) + 2, int(x) - 2 : int(x) + 2]
        assert region.max() == pytest.approx(7.5, rel=0.01)

    def test_empty_mom0_files_produces_zero_mosaic_not_an_error(self, tmp_path, field_mosaic_file):
        output = tmp_path / "mosaic.fits"
        data = postprocess.build_mosaic(field_mosaic_file, [], output)
        field_shape = fits.getdata(field_mosaic_file).shape
        assert data.shape == field_shape
        assert np.all(data == 0)

    def test_output_has_no_nan_even_where_field_is_uncovered(self, tmp_path, field_mosaic_file):
        # The cutout only covers a small corner of the (much bigger) field -- most of
        # the output should be filled (0, via nan_to_num), never NaN.
        cutout = _synthetic_cutout(tmp_path, "src1", ra=10.0, dec=-30.0, value=1.0)
        output = tmp_path / "mosaic.fits"
        data = postprocess.build_mosaic(field_mosaic_file, [cutout], output)
        assert not np.isnan(data).any()
