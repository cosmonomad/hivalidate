"""Tests for the QA review state machine and catalogue merge, using a real manifest
produced by dry-run (with a stub cutout backend, no network) against the fixture.
`display_fn`/`prompt_fn`/`close_fn` are faked -- see hivalidate/qa.py's module
docstring for why that's the intended way to test this without a real display or
keyboard.
"""

import math
from pathlib import Path

import numpy as np
import pytest
from astropy.wcs import WCS

from hivalidate import catalogue, qa
from hivalidate.cli import combine, dedup, dry_run, rename
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


@pytest.fixture
def prepared_config(tmp_path, monkeypatch):
    """combine -> dedup -> rename -> dry-run for real (stubbed cutouts, no network)
    against a 4-source slice of the fixture -- gives QA a real manifest.json and
    real PNGs to work from, same trade-off as test_cli_dry_run.py's fixture.
    """
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    config.paths.work_dir = tmp_path / "work"
    combine.run(config)
    dedup.run(config)
    rename.run(config)

    deduped = catalogue.read_votable(config.paths.deduped_catalogue)
    catalogue.write_votable(deduped[:4], config.paths.deduped_catalogue)

    monkeypatch.setattr(dry_run, "build_optical_chain", lambda cfg: [StubCutoutBackend()])
    monkeypatch.setattr(dry_run, "build_continuum_chain", lambda cfg: [StubCutoutBackend()])
    dry_run.run(config)

    return config


def _scripted(responses):
    """A prompt_fn that returns each of `responses` in turn, ignoring its args."""
    it = iter(responses)

    def _prompt(source, position, total):
        return next(it)

    return _prompt


def _recording_display():
    seen = []

    def _display(png_path):
        seen.append(png_path)
        return png_path  # handle == the path is fine, close_fn below is a no-op

    return seen, _display


def _noop_close(handle):
    pass


class TestRunQaSessionHappyPath:
    def test_reviews_every_ok_source_in_manifest_order(self, prepared_config):
        manifest = qa.load_manifest(prepared_config.paths.dry_run_dir)
        ok_names = [s["name"] for s in manifest["sources"] if s["status"] == "ok"]
        assert len(ok_names) == 4  # sanity check on the fixture slice

        seen, display_fn = _recording_display()
        responses = [("t", "looks good")] * len(ok_names)
        results = qa.run_qa_session(prepared_config, _scripted(responses), display_fn, _noop_close)

        assert set(results.keys()) == set(ok_names)
        assert all(r["qa_flag"] == "t" for r in results.values())
        assert all(r["comment"] == "looks good" for r in results.values())
        assert len(seen) == len(ok_names)

    def test_persists_results_incrementally_to_disk(self, prepared_config):
        _, display_fn = _recording_display()
        responses = [("t", ""), ("f", ""), ("u", ""), ("d", "")]
        qa.run_qa_session(prepared_config, _scripted(responses), display_fn, _noop_close)

        on_disk = qa.load_qa_results(prepared_config.paths.qa_dir)
        assert len(on_disk) == 4
        assert {r["qa_flag"] for r in on_disk.values()} == {"t", "f", "u", "d"}

    def test_writes_validated_catalogue_and_run_info_at_the_end(self, prepared_config):
        _, display_fn = _recording_display()
        responses = [("t", "")] * 4
        qa.run_qa_session(prepared_config, _scripted(responses), display_fn, _noop_close)

        assert (prepared_config.paths.qa_dir / "validated_cat.xml").exists()
        run_info_path = prepared_config.paths.qa_dir / "run_info.json"
        assert run_info_path.exists()
        import json

        run_info = json.loads(run_info_path.read_text())
        assert run_info["n_reviewed"] == 4
        assert run_info["n_total"] == 4
        assert run_info["config_field_name"] == prepared_config.field_name


class TestRunQaSessionQuitAndResume:
    def test_q_stops_early_without_reviewing_remaining_sources(self, prepared_config):
        seen, display_fn = _recording_display()
        responses = [("t", ""), ("f", ""), ("q", "")]  # stop after 2
        results = qa.run_qa_session(prepared_config, _scripted(responses), display_fn, _noop_close)
        assert len(results) == 2
        assert len(seen) == 3  # displayed the 3rd before the user typed 'q'

    def test_resuming_skips_already_reviewed_sources_without_displaying_them(self, prepared_config):
        seen1, display_fn1 = _recording_display()
        responses1 = _scripted([("t", ""), ("f", ""), ("q", "")])
        qa.run_qa_session(prepared_config, responses1, display_fn1, _noop_close)

        seen2, display_fn2 = _recording_display()
        responses = [("u", ""), ("d", "")]  # only the 2 remaining sources
        results = qa.run_qa_session(prepared_config, _scripted(responses), display_fn2, _noop_close)

        assert len(results) == 4
        assert len(seen2) == 2  # the first 2 (already reviewed) were never displayed again


class TestRunQaSessionBack:
    def test_back_re_presents_the_previous_source_and_lets_it_be_overwritten(self, prepared_config):
        seen, display_fn = _recording_display()
        # Flag the 1st as 't', flag the 2nd as 'f' by mistake, go back, correct it to
        # 'u', then quit -- ends the session at a known point rather than needing to
        # script responses for the remaining sources too.
        responses = [("t", "first"), ("f", "oops"), ("b", ""), ("u", "corrected"), ("q", "")]
        results = qa.run_qa_session(prepared_config, _scripted(responses), display_fn, _noop_close)

        manifest = qa.load_manifest(prepared_config.paths.dry_run_dir)
        ok_names = [s["name"] for s in manifest["sources"] if s["status"] == "ok"]
        assert results[ok_names[0]]["qa_flag"] == "t"
        assert results[ok_names[1]]["qa_flag"] == "u"
        assert results[ok_names[1]]["comment"] == "corrected"
        # 2 sources reviewed so far (session stops naturally once responses run out
        # only if it needed more -- here it's exactly consumed after 4 responses and
        # only 2 unique sources have final answers).
        assert len(results) == 2

    def test_back_at_the_very_first_source_is_a_no_op_not_a_crash(self, prepared_config):
        seen, display_fn = _recording_display()
        responses = [("b", ""), ("t", "")]  # back with nothing before it, then proceed
        results = qa.run_qa_session(
            prepared_config, _scripted(responses + [("q", "")] * 5), display_fn, _noop_close
        )
        assert len(results) >= 1


class TestMergeQaIntoCatalogue:
    def test_unreviewed_sources_get_nan_qa_and_empty_comment(self, prepared_config):
        _, display_fn = _recording_display()
        # Only fully review 2 of the 4 sources (quit early).
        qa.run_qa_session(
            prepared_config, _scripted([("t", "a"), ("f", "b"), ("q", "")]), display_fn, _noop_close
        )

        validated = catalogue.read_votable(prepared_config.paths.qa_dir / "validated_cat.xml")
        qa_values = [float(v) for v in validated["qa"]]  # VOTable round-trips NaN as masked
        n_reviewed = sum(1 for v in qa_values if not math.isnan(v))
        n_unreviewed = sum(1 for v in qa_values if math.isnan(v))
        assert n_reviewed == 2
        assert n_unreviewed == 2
        for value, row in zip(qa_values, validated):
            if math.isnan(value):
                assert row["qa_comment"] == ""

    def test_reviewed_sources_carry_provenance_from_manifest(self, prepared_config):
        _, display_fn = _recording_display()
        qa.run_qa_session(prepared_config, _scripted([("t", "")] * 4), display_fn, _noop_close)

        validated = catalogue.read_votable(prepared_config.paths.qa_dir / "validated_cat.xml")
        assert all(p == "stub:test" for p in validated["optical_provenance"])
        assert all(p == "stub:test" for p in validated["continuum_provenance"])
        assert all(s == "ok" for s in validated["dry_run_status"])

    def test_qa_numeric_matches_documented_flag_convention(self, prepared_config):
        _, display_fn = _recording_display()
        responses = [("t", ""), ("f", ""), ("u", ""), ("d", "")]
        qa.run_qa_session(prepared_config, _scripted(responses), display_fn, _noop_close)

        validated = catalogue.read_votable(prepared_config.paths.qa_dir / "validated_cat.xml")
        qa_by_name = {str(row["name"]): row["qa"] for row in validated}
        results = qa.load_qa_results(prepared_config.paths.qa_dir)
        for name, entry in results.items():
            assert qa_by_name[name] == qa.FLAG_TO_NUMERIC[entry["qa_flag"]]
