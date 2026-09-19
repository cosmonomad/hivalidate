from pathlib import Path

import pytest

from hivalidate.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_example_field_config():
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    assert config.field_name == "SB82605_mini"
    assert config.paths.raw_sofia_dir == (FIXTURES / "run_sofia_mini").resolve()


def test_relative_paths_resolve_against_config_file_directory():
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    assert config.paths.raw_sofia_dir.is_absolute()
    assert config.paths.raw_sofia_dir.is_dir()


def test_missing_raw_sofia_dir_raises_before_any_pipeline_stage_runs(tmp_path):
    bad_config = {
        "field_name": "bogus",
        "paths": {
            "raw_sofia_dir": str(tmp_path / "does_not_exist"),
            "work_dir": str(tmp_path / "work"),
        },
    }
    with pytest.raises(ValueError, match="raw_sofia_dir"):
        Config.from_dict(bad_config)


def test_missing_required_key_raises_clear_error():
    with pytest.raises(ValueError, match="paths"):
        Config.from_dict({"field_name": "bogus"})


def test_dedup_settings_default_to_documented_values():
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    assert config.dedup.sep_arcsec == 30.0
    assert config.dedup.vel_tol_wm50_factor == 0.6


class TestCrossmatchSettings:
    def test_defaults_to_unset_when_no_crossmatch_section_given(self):
        config = Config.from_yaml(FIXTURES / "config_mini.yaml")
        assert config.crossmatch.sep_arcsec is None
        assert config.crossmatch.vel_tol_base_km_s is None
        assert config.crossmatch.vel_tol_wm50_factor is None

    def test_resolved_falls_back_entirely_to_dedup_when_all_unset(self, tmp_path):
        raw = {
            "field_name": "bogus",
            "paths": {"raw_sofia_dir": str(tmp_path), "work_dir": str(tmp_path / "work")},
            "dedup": {"sep_arcsec": 15.0, "vel_tol_base_km_s": 20.0, "vel_tol_wm50_factor": 0.4},
        }
        config = Config.from_dict(raw)
        resolved = config.crossmatch.resolved(config.dedup)
        assert resolved.sep_arcsec == 15.0
        assert resolved.vel_tol_base_km_s == 20.0
        assert resolved.vel_tol_wm50_factor == 0.4

    def test_resolved_uses_explicit_crossmatch_values_over_dedups(self, tmp_path):
        raw = {
            "field_name": "bogus",
            "paths": {"raw_sofia_dir": str(tmp_path), "work_dir": str(tmp_path / "work")},
            "dedup": {"sep_arcsec": 15.0, "vel_tol_base_km_s": 20.0, "vel_tol_wm50_factor": 0.4},
            "crossmatch": {"sep_arcsec": 60.0},
        }
        config = Config.from_dict(raw)
        resolved = config.crossmatch.resolved(config.dedup)
        # Explicitly overridden field takes the crossmatch: value...
        assert resolved.sep_arcsec == 60.0
        # ...but a field left unset in crossmatch: still falls back to dedup's.
        assert resolved.vel_tol_base_km_s == 20.0
        assert resolved.vel_tol_wm50_factor == 0.4

    def test_changing_dedup_alone_does_not_change_an_explicit_crossmatch_override(
        self, tmp_path
    ):
        # The exact scenario this feature was added for: retuning dedup's own
        # tolerance must not silently move a crossmatch tolerance that was
        # deliberately set independently.
        raw = {
            "field_name": "bogus",
            "paths": {"raw_sofia_dir": str(tmp_path), "work_dir": str(tmp_path / "work")},
            "dedup": {"sep_arcsec": 15.0},
            "crossmatch": {"sep_arcsec": 60.0},
        }
        config = Config.from_dict(raw)
        assert config.crossmatch.resolved(config.dedup).sep_arcsec == 60.0

        raw["dedup"]["sep_arcsec"] = 45.0
        retuned_config = Config.from_dict(raw)
        assert retuned_config.crossmatch.resolved(retuned_config.dedup).sep_arcsec == 60.0


def test_derived_paths_are_under_work_dir(tmp_path):
    raw = {
        "field_name": "bogus",
        "paths": {"raw_sofia_dir": str(tmp_path), "work_dir": str(tmp_path / "work")},
    }
    config = Config.from_dict(raw)
    assert config.paths.combined_catalogue.parent == config.paths.work_dir
    assert config.paths.dry_run_dir.parent == config.paths.work_dir
