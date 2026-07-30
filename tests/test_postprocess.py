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

from hivalidate import catalogue, postprocess
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
