"""Tests for the dry-run CLI stage, using stub cutout backends (no network) run
against the real combine -> dedup -> rename output for the run_sofia_mini fixture.
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from astropy.wcs import WCS

from hivalidate import catalogue
from hivalidate.cli import combine, dedup, dry_run, rename
from hivalidate.config import Config
from hivalidate.cutouts.base import CutoutBackend, CutoutResult, CutoutUnavailable

FIXTURES = Path(__file__).parent / "fixtures"


class StubCutoutBackend(CutoutBackend):
    def __init__(self, name="stub", available=True, fail_for: set[str] | None = None):
        self.name = name
        self._available = available
        self._fail_for = fail_for or set()

    def fetch(self, position, size_arcsec):
        return CutoutResult(data=np.ones((20, 20)), wcs=_fake_wcs(), provenance=f"{self.name}:test")

    def is_available(self):
        return self._available, "stub"


def _fake_wcs():
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [315.0, -55.0]
    wcs.wcs.crpix = [10, 10]
    wcs.wcs.cdelt = [-1.7 / 3600, 1.7 / 3600]
    return wcs


@pytest.fixture
def prepared_config(tmp_path):
    """Runs combine -> dedup -> rename for real against the fixture, so dry-run has
    a genuine deduped catalogue and renamed cubelets to work from -- then truncates
    the deduped catalogue to 3 rows (after rename has already copied cubelets for
    every source) purely so these tests build 3 real figures instead of ~45 of them.
    Building a real six-panel WCS figure per source is not cheap; the fixture-size
    trade-off documented in PLAN.md ("small fixture for fast tests") applies here
    too, one level down.
    """
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    config.paths.work_dir = tmp_path / "work"
    combine.run(config)
    dedup.run(config)
    rename.run(config)

    deduped = catalogue.read_votable(config.paths.deduped_catalogue)
    catalogue.write_votable(deduped[:3], config.paths.deduped_catalogue)

    return config


def _patch_chains(monkeypatch, optical_chain, continuum_chain):
    monkeypatch.setattr(dry_run, "build_optical_chain", lambda cfg: optical_chain)
    monkeypatch.setattr(dry_run, "build_continuum_chain", lambda cfg: continuum_chain)


class TestDryRunHappyPath:
    def test_generates_a_png_and_manifest_entry_per_source(self, monkeypatch, prepared_config):
        _patch_chains(
            monkeypatch, [StubCutoutBackend("optical_stub")], [StubCutoutBackend("cont_stub")]
        )
        manifest = dry_run.run(prepared_config)

        deduped = catalogue.read_votable(prepared_config.paths.deduped_catalogue)
        assert len(manifest["sources"]) == len(deduped)
        assert all(s["status"] == "ok" for s in manifest["sources"])
        for s in manifest["sources"]:
            assert Path(s["png_path"]).exists()
            assert s["optical_provenance"] == "optical_stub:test"
            assert s["continuum_provenance"] == "cont_stub:test"

    def test_writes_manifest_json_to_disk_matching_return_value(self, monkeypatch, prepared_config):
        _patch_chains(monkeypatch, [StubCutoutBackend()], [StubCutoutBackend()])
        manifest = dry_run.run(prepared_config)
        manifest_path = prepared_config.paths.dry_run_dir / "manifest.json"
        assert manifest_path.exists()
        assert json.loads(manifest_path.read_text()) == manifest

    def test_manifest_run_info_has_provenance_metadata(self, monkeypatch, prepared_config):
        _patch_chains(monkeypatch, [StubCutoutBackend()], [StubCutoutBackend()])
        manifest = dry_run.run(prepared_config)
        run_info = manifest["run_info"]
        assert run_info["config_field_name"] == prepared_config.field_name
        assert "hivalidate_version" in run_info
        assert "hivalidate_git_commit" in run_info
        assert "generated_at" in run_info


class TestDryRunFaultIsolation:
    def test_one_missing_cubelet_does_not_abort_the_whole_batch(self, monkeypatch, prepared_config):
        _patch_chains(monkeypatch, [StubCutoutBackend()], [StubCutoutBackend()])

        # Sabotage exactly one source's cubelets so it fails, without touching the rest.
        deduped = catalogue.read_votable(prepared_config.paths.deduped_catalogue)
        victim_name = str(deduped["name"][0]).replace(" ", "_")
        victim_file = prepared_config.paths.renamed_cubelets_dir / f"{victim_name}_mom0.fits"
        backup = victim_file.with_suffix(".fits.bak")
        shutil.move(victim_file, backup)

        try:
            manifest = dry_run.run(prepared_config)
        finally:
            shutil.move(backup, victim_file)

        statuses = {s["name"]: s["status"] for s in manifest["sources"]}
        assert statuses[str(deduped["name"][0])] == "failed"
        assert sum(1 for s in manifest["sources"] if s["status"] == "ok") == len(deduped) - 1

    def test_cutout_unavailable_from_every_backend_still_produces_a_plot(
        self, monkeypatch, prepared_config
    ):
        # Every backend failing for one image type degrades to a blank panel
        # (plotting.py), it doesn't fail the source.
        class AlwaysFailsBackend(CutoutBackend):
            name = "always_fails"

            def fetch(self, position, size_arcsec):
                raise CutoutUnavailable("nope")

            def is_available(self):
                return True, "reachable but will fail on fetch"

        _patch_chains(monkeypatch, [AlwaysFailsBackend()], [StubCutoutBackend()])
        manifest = dry_run.run(prepared_config)
        assert all(s["status"] == "ok" for s in manifest["sources"])
        assert all(s["optical_provenance"] is None for s in manifest["sources"])


class TestDryRunPreflight:
    def test_aborts_if_entire_optical_chain_is_unavailable(self, monkeypatch, prepared_config):
        _patch_chains(
            monkeypatch, [StubCutoutBackend(available=False)], [StubCutoutBackend(available=True)]
        )
        with pytest.raises(SystemExit, match="optical"):
            dry_run.run(prepared_config)

    def test_proceeds_if_at_least_one_backend_in_the_chain_is_available(
        self, monkeypatch, prepared_config
    ):
        _patch_chains(
            monkeypatch,
            [StubCutoutBackend("down", available=False), StubCutoutBackend("up", available=True)],
            [StubCutoutBackend()],
        )
        manifest = dry_run.run(prepared_config)  # should not raise
        assert len(manifest["sources"]) > 0

    def test_empty_continuum_chain_is_allowed_not_an_error(self, monkeypatch, prepared_config):
        # A field with no continuum_local_dir and racs_casda not configured -- an
        # empty chain is a legitimate config, not something to abort on.
        _patch_chains(monkeypatch, [StubCutoutBackend()], [])
        manifest = dry_run.run(prepared_config)
        assert all(s["continuum_provenance"] is None for s in manifest["sources"])


def test_run_fails_clearly_if_dedup_and_rename_were_not_run(tmp_path, monkeypatch):
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    config.paths.work_dir = tmp_path / "work"
    # Empty chains so preflight has nothing to check (and makes no network calls) --
    # this test is about the missing-catalogue guard, not backend availability.
    _patch_chains(monkeypatch, [], [])
    with pytest.raises(SystemExit, match="hivalidate-dedup"):
        dry_run.run(config)


def _counting_wrapper(real, calls, stop_after=None):
    """Wraps the real `_process_one_source`, recording each source it's called for in
    `calls` -- lets tests assert exactly which sources got (re)processed. `stop_after`,
    if given, raises KeyboardInterrupt once `calls` reaches that length, simulating a
    Ctrl-C partway through the batch. Takes `real` as an argument (rather than reading
    `dry_run._process_one_source` itself) so a test can build a second wrapper after
    the first has already been monkeypatched in, without accidentally wrapping the
    first wrapper instead of the true original.
    """

    def _wrapped(row, source_name, config, optical_chain, continuum_chain, cache):
        calls.append(source_name)
        if stop_after is not None and len(calls) > stop_after:
            raise KeyboardInterrupt
        return real(row, source_name, config, optical_chain, continuum_chain, cache)

    return _wrapped


class TestDryRunResume:
    """Regression coverage for a real bug report: Ctrl-C during a long dry-run batch
    followed by re-running the same command reprocessed every source from scratch
    instead of picking up where it left off. Fixed by writing manifest.json after
    every source (not just once at the end) and skipping any source already recorded
    as "ok" with a PNG still on disk.
    """

    def test_a_second_run_does_not_reprocess_already_completed_sources(
        self, monkeypatch, prepared_config
    ):
        _patch_chains(monkeypatch, [StubCutoutBackend()], [StubCutoutBackend()])
        real = dry_run._process_one_source
        calls: list[str] = []
        monkeypatch.setattr(dry_run, "_process_one_source", _counting_wrapper(real, calls))

        first = dry_run.run(prepared_config)
        assert len(calls) == len(first["sources"])  # first run: everything processed

        calls.clear()
        second = dry_run.run(prepared_config)
        assert calls == []  # second run: nothing re-processed
        assert second["sources"] == first["sources"]

    def test_interrupted_batch_saves_partial_progress_and_resumes_on_rerun(
        self, monkeypatch, prepared_config
    ):
        _patch_chains(monkeypatch, [StubCutoutBackend()], [StubCutoutBackend()])
        deduped = catalogue.read_votable(prepared_config.paths.deduped_catalogue)
        assert len(deduped) == 3  # sanity check on the fixture slice

        real = dry_run._process_one_source
        calls: list[str] = []
        monkeypatch.setattr(
            dry_run, "_process_one_source", _counting_wrapper(real, calls, stop_after=2)
        )
        manifest = dry_run.run(prepared_config)  # must not raise -- KeyboardInterrupt is caught
        assert len(manifest["sources"]) == 2  # 2 completed before the simulated Ctrl-C

        manifest_on_disk = json.loads(
            (prepared_config.paths.dry_run_dir / "manifest.json").read_text()
        )
        assert manifest_on_disk == manifest  # interrupt handling still wrote to disk

        # Resume: only the 1 remaining source should be processed this time -- wraps
        # `real` again (the true original), not whatever's currently monkeypatched in.
        calls.clear()
        monkeypatch.setattr(dry_run, "_process_one_source", _counting_wrapper(real, calls))
        resumed = dry_run.run(prepared_config)
        assert len(calls) == 1
        assert len(resumed["sources"]) == 3
        assert all(s["status"] == "ok" for s in resumed["sources"])

    def test_a_failed_source_is_retried_on_the_next_run(self, monkeypatch, prepared_config):
        _patch_chains(monkeypatch, [StubCutoutBackend()], [StubCutoutBackend()])
        deduped = catalogue.read_votable(prepared_config.paths.deduped_catalogue)
        victim = str(deduped["name"][0])

        real = dry_run._process_one_source

        def _fails_once_for_victim(row, source_name, config, optical_chain, continuum_chain, cache):
            if str(row["name"]) == victim:
                raise RuntimeError("simulated transient failure")
            return real(row, source_name, config, optical_chain, continuum_chain, cache)

        monkeypatch.setattr(dry_run, "_process_one_source", _fails_once_for_victim)
        manifest = dry_run.run(prepared_config)
        statuses = {s["name"]: s["status"] for s in manifest["sources"]}
        assert statuses[victim] == "failed"

        # Fix whatever was wrong and re-run: the previously-failed source must be
        # retried (not skipped like an "ok" one would be), and succeed this time.
        monkeypatch.setattr(dry_run, "_process_one_source", real)
        resumed = dry_run.run(prepared_config)
        resumed_statuses = {s["name"]: s["status"] for s in resumed["sources"]}
        assert resumed_statuses[victim] == "ok"

    def test_a_manifest_from_a_different_field_is_ignored_not_resumed_from(
        self, monkeypatch, prepared_config
    ):
        manifest_path = prepared_config.paths.dry_run_dir / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "run_info": {"config_field_name": "some_other_field"},
                    "sources": [
                        {
                            "name": "not a real source",
                            "status": "ok",
                            "png_path": "/nonexistent.png",
                        }
                    ],
                }
            )
        )

        _patch_chains(monkeypatch, [StubCutoutBackend()], [StubCutoutBackend()])
        real = dry_run._process_one_source
        calls: list[str] = []
        monkeypatch.setattr(dry_run, "_process_one_source", _counting_wrapper(real, calls))
        manifest = dry_run.run(prepared_config)
        assert len(calls) == len(manifest["sources"])  # nothing was skipped as "already done"
