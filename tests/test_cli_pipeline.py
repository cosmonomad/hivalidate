"""Tests for hivalidate-run-pipeline, the orchestration script that chains the
individual `hivalidate-*` stages together. Uses stub cutout backends (no network)
throughout, same trade-off as test_cli_dry_run.py.
"""

from pathlib import Path

import numpy as np
import pytest
from astropy.wcs import WCS

from hivalidate import catalogue, qa
from hivalidate.cli import check_connectivity, combine, dedup, dry_run, pipeline, rename
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


def _config(tmp_path):
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    config.paths.work_dir = tmp_path / "work"
    return config


def _patch_backend_chains(monkeypatch):
    # Both hivalidate.cli.check_connectivity and hivalidate.cli.dry_run import
    # build_optical_chain/build_continuum_chain directly into their own module
    # namespace, so each needs patching independently -- see PLAN.md's note on why
    # dry-run's preflight and the standalone connectivity check share the same
    # backend-availability logic but not a single patch point.
    for module in (check_connectivity, dry_run):
        monkeypatch.setattr(module, "build_optical_chain", lambda cfg: [StubCutoutBackend()])
        monkeypatch.setattr(module, "build_continuum_chain", lambda cfg: [StubCutoutBackend()])


class TestDryRunMode:
    def test_runs_every_stage_up_to_dry_run_and_stops_before_qa(self, tmp_path, monkeypatch):
        config = _config(tmp_path)
        _patch_backend_chains(monkeypatch)

        pipeline.run_dry_run_mode(config)

        assert config.paths.combined_catalogue.exists()
        assert config.paths.deduped_catalogue.exists()
        assert list(config.paths.renamed_cubelets_dir.iterdir())
        assert (config.paths.dry_run_dir / "manifest.json").exists()
        # Never touched QA -- that's --mode qa's job.
        assert not (config.paths.qa_dir / "validated_cat.xml").exists()

    def test_a_down_backend_in_a_chain_with_a_working_fallback_does_not_abort(
        self, tmp_path, monkeypatch
    ):
        # check-connectivity reporting one backend down must not stop the pipeline --
        # it's dry-run's own preflight (already covered by test_cli_dry_run.py) that
        # decides whether a whole chain being unusable is fatal. Stubs dry_run.run
        # itself (rather than building ~50 real figures again) since the thing under
        # test here is that the earlier connectivity warning doesn't abort the
        # pipeline before dry-run even gets a chance to run its own preflight.
        class DownBackend(StubCutoutBackend):
            name = "down"

            def is_available(self):
                return False, "deliberately down"

        config = _config(tmp_path)
        monkeypatch.setattr(
            check_connectivity,
            "build_optical_chain",
            lambda cfg: [DownBackend(), StubCutoutBackend()],
        )
        monkeypatch.setattr(check_connectivity, "build_continuum_chain", lambda cfg: [])

        called = {}
        monkeypatch.setattr(dry_run, "run", lambda cfg: called.setdefault("ran", True))

        pipeline.run_dry_run_mode(config)  # should not raise
        assert called.get("ran") is True
        # combine/dedup/rename ran for real before the stubbed dry-run call.
        assert config.paths.deduped_catalogue.exists()
        assert list(config.paths.renamed_cubelets_dir.iterdir())


class TestQaMode:
    @pytest.fixture
    def dry_run_done(self, tmp_path, monkeypatch):
        """Builds a real dry_run/manifest.json without going through
        pipeline.run_dry_run_mode -- that path is exercised by TestDryRunMode
        already, and QA mode doesn't care how the manifest was produced. Truncates
        the deduped catalogue to 3 rows first (after rename has copied cubelets for
        every source) so these tests build 3 real figures, not ~50 -- same trade-off
        as test_cli_dry_run.py/test_qa.py's own fixtures.
        """
        config = _config(tmp_path)
        _patch_backend_chains(monkeypatch)
        combine.run(config)
        dedup.run(config)
        rename.run(config)
        deduped = catalogue.read_votable(config.paths.deduped_catalogue)
        catalogue.write_votable(deduped[:3], config.paths.deduped_catalogue)
        dry_run.run(config)
        return config

    def test_fails_clearly_if_dry_run_mode_was_not_run_first(self, tmp_path):
        config = _config(tmp_path)
        with pytest.raises(SystemExit, match="dry-run"):
            pipeline.run_qa_mode(config)

    def test_runs_qa_then_postprocess(self, dry_run_done, monkeypatch):
        config = dry_run_done
        manifest = qa.load_manifest(config.paths.dry_run_dir)
        n_sources = len(manifest["sources"])

        responses = iter([("t", "")] * n_sources)
        monkeypatch.setattr(qa, "default_prompt", lambda source, position, total: next(responses))
        monkeypatch.setattr(qa, "default_display", lambda png_path: png_path)
        monkeypatch.setattr(qa, "default_close", lambda handle: None)

        pipeline.run_qa_mode(config)

        assert (config.paths.qa_dir / "validated_cat.xml").exists()
        assert (config.paths.qa_dir / "validated_cat.csv").exists()
        assert (config.paths.postprocess_dir / "true" / "validated_true.csv").exists()
        validated = catalogue.read_votable(config.paths.qa_dir / "validated_cat.xml")
        assert all(v == 1.0 for v in validated["qa"])

    def test_interrupt_during_qa_skips_postprocess_and_can_be_resumed(
        self, dry_run_done, monkeypatch
    ):
        config = dry_run_done

        def _raises_interrupt(source, position, total):
            raise KeyboardInterrupt

        monkeypatch.setattr(qa, "default_prompt", _raises_interrupt)
        monkeypatch.setattr(qa, "default_display", lambda png_path: png_path)
        monkeypatch.setattr(qa, "default_close", lambda handle: None)

        pipeline.run_qa_mode(config)  # must not raise

        assert not (config.paths.qa_dir / "validated_cat.xml").exists()
        assert not config.paths.postprocess_dir.exists()

        # Resuming with real responses picks up cleanly and reaches postprocess.
        manifest = qa.load_manifest(config.paths.dry_run_dir)
        n_sources = len(manifest["sources"])
        responses = iter([("t", "")] * n_sources)
        monkeypatch.setattr(qa, "default_prompt", lambda source, position, total: next(responses))

        pipeline.run_qa_mode(config)
        assert (config.paths.postprocess_dir / "true" / "validated_true.csv").exists()


class TestMainDispatch:
    def test_dry_run_flag_calls_dry_run_mode(self, monkeypatch, tmp_path):
        called = {}
        monkeypatch.setattr(
            pipeline, "run_dry_run_mode", lambda cfg: called.setdefault("mode", "dry-run")
        )
        pipeline.main(["--config", str(FIXTURES / "config_mini.yaml"), "--mode", "dry-run"])
        assert called["mode"] == "dry-run"

    def test_qa_flag_calls_qa_mode(self, monkeypatch, tmp_path):
        called = {}
        monkeypatch.setattr(pipeline, "run_qa_mode", lambda cfg: called.setdefault("mode", "qa"))
        pipeline.main(["--config", str(FIXTURES / "config_mini.yaml"), "--mode", "qa"])
        assert called["mode"] == "qa"

    def test_rejects_an_invalid_mode(self, capsys):
        with pytest.raises(SystemExit):
            pipeline.main(["--config", str(FIXTURES / "config_mini.yaml"), "--mode", "bogus"])
