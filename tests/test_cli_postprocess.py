"""End-to-end test of the postprocess CLI stage, building a real validated_cat.xml
via combine -> dedup -> rename -> dry-run -> qa (stubbed cutouts, scripted QA
responses, no network, no real display) against the fixture.
"""

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hivalidate import catalogue, qa
from hivalidate import postprocess as postprocess_lib
from hivalidate.cli import combine, dedup, dry_run, postprocess, rename
from hivalidate.config import Config
from hivalidate.cutouts.base import CutoutBackend, CutoutResult

FIXTURES = Path(__file__).parent / "fixtures"


class StubCutoutBackend(CutoutBackend):
    name = "stub"

    def fetch(self, position, size_arcsec):
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.crval = [315.0, -55.0]
        wcs.wcs.crpix = [10, 10]
        wcs.wcs.cdelt = [-1.7 / 3600, 1.7 / 3600]
        return CutoutResult(data=np.ones((20, 20)), wcs=wcs, provenance="stub:test")

    def is_available(self):
        return True, "stub"


def _scripted(responses):
    it = iter(responses)
    return lambda source, position, total: next(it)


@pytest.fixture
def validated_config(tmp_path, monkeypatch):
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    config.paths.work_dir = tmp_path / "work"
    combine.run(config)
    dedup.run(config)
    rename.run(config)

    deduped = catalogue.read_votable(config.paths.deduped_catalogue)
    catalogue.write_votable(deduped[:5], config.paths.deduped_catalogue)

    monkeypatch.setattr(dry_run, "build_optical_chain", lambda cfg: [StubCutoutBackend()])
    monkeypatch.setattr(dry_run, "build_continuum_chain", lambda cfg: [StubCutoutBackend()])
    dry_run.run(config)

    # 2 true, 1 false, 1 uncertain, 1 duplicate -- mixed flags to prove filtering
    # (and the per-class directory split) is selective across every reviewed class.
    responses = _scripted([("t", ""), ("f", ""), ("u", ""), ("d", ""), ("t", "")])
    qa.run_qa_session(config, responses, lambda p: p, lambda h: None)

    return config


def _read_csv_rows(csv_path):
    import csv as csv_module

    with open(csv_path) as fh:
        return list(csv_module.DictReader(fh))


class TestPostprocessCli:
    @pytest.mark.parametrize(
        "class_name,expected_count",
        [("true", 2), ("false", 1), ("uncertain", 1), ("duplicate", 1)],
    )
    def test_writes_csv_with_only_that_classs_flagged_sources(
        self, validated_config, class_name, expected_count
    ):
        postprocess.run(validated_config)
        csv_path = (
            validated_config.paths.postprocess_dir / class_name / f"validated_{class_name}.csv"
        )
        assert csv_path.exists()
        assert len(_read_csv_rows(csv_path)) == expected_count

    @pytest.mark.parametrize("class_name", ["true", "false", "uncertain", "duplicate"])
    def test_extracts_cubelets_only_for_that_classs_sources(self, validated_config, class_name):
        postprocess.run(validated_config)
        validated = catalogue.read_votable(validated_config.paths.qa_dir / "validated_cat.xml")
        qa_value = postprocess_lib.QA_CLASSES[class_name]
        this_class_names = {
            str(n).replace(" ", "_") for n in validated[validated["qa"] == qa_value]["name"]
        }
        other_class_names = {
            str(n).replace(" ", "_") for n in validated[validated["qa"] != qa_value]["name"]
        }

        cubelets_dir = validated_config.paths.postprocess_dir / class_name / "cubelets"
        cubelet_files = list(cubelets_dir.iterdir())
        assert len(cubelet_files) > 0
        for f in cubelet_files:
            assert any(f.name.startswith(n + "_") for n in this_class_names)
            assert not any(f.name.startswith(n + "_") for n in other_class_names)

    @pytest.mark.parametrize("class_name", ["true", "false", "uncertain", "duplicate"])
    def test_extracts_dry_run_plots_only_for_that_classs_sources(
        self, validated_config, class_name
    ):
        postprocess.run(validated_config)
        validated = catalogue.read_votable(validated_config.paths.qa_dir / "validated_cat.xml")
        qa_value = postprocess_lib.QA_CLASSES[class_name]
        this_class_names = {
            str(n).replace(" ", "_") for n in validated[validated["qa"] == qa_value]["name"]
        }

        plots_dir = validated_config.paths.postprocess_dir / class_name / "plots"
        plot_files = list(plots_dir.iterdir())
        assert len(plot_files) == len(this_class_names)
        assert {f.stem for f in plot_files} == this_class_names

    def test_builds_mosaic_when_field_mosaic_configured(self, validated_config):
        # config_mini.yaml has no field_mosaic -- point it at a tiny synthetic one to
        # exercise the mosaic branch end-to-end through the real CLI.
        field_wcs = WCS(naxis=2)
        field_wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
        field_wcs.wcs.crval = [315.0, -55.0]
        field_wcs.wcs.crpix = [500, 500]
        field_wcs.wcs.cdelt = [-0.0005, 0.0005]
        field_path = validated_config.paths.work_dir / "field_mom0.fits"
        fits.writeto(field_path, np.zeros((1000, 1000)), field_wcs.to_header(), overwrite=True)
        validated_config.paths.field_mosaic = field_path

        postprocess.run(validated_config)

        mosaic_path = validated_config.paths.postprocess_dir / "true" / "mosaic_true.fits"
        assert mosaic_path.exists()
        assert fits.getdata(mosaic_path).shape == (1000, 1000)

    def test_skips_mosaic_when_not_configured(self, validated_config):
        assert validated_config.paths.field_mosaic is None
        postprocess.run(validated_config)
        assert not (validated_config.paths.postprocess_dir / "true" / "mosaic_true.fits").exists()

    def test_does_not_build_mosaics_for_non_true_classes(self, validated_config):
        field_wcs = WCS(naxis=2)
        field_wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
        field_wcs.wcs.crval = [315.0, -55.0]
        field_wcs.wcs.crpix = [500, 500]
        field_wcs.wcs.cdelt = [-0.0005, 0.0005]
        field_path = validated_config.paths.work_dir / "field_mom0.fits"
        fits.writeto(field_path, np.zeros((1000, 1000)), field_wcs.to_header(), overwrite=True)
        validated_config.paths.field_mosaic = field_path

        postprocess.run(validated_config)

        for class_name in ("false", "uncertain", "duplicate"):
            assert not list(
                (validated_config.paths.postprocess_dir / class_name).glob("mosaic_*.fits")
            )

    def test_fails_clearly_if_qa_was_not_run(self, tmp_path):
        config = Config.from_yaml(FIXTURES / "config_mini.yaml")
        config.paths.work_dir = tmp_path / "work"
        with pytest.raises(SystemExit, match="hivalidate-qa"):
            postprocess.run(config)
