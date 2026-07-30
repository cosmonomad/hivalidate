"""End-to-end test of the Phase 1 pipeline (combine -> dedup -> rename) against the
run_sofia_mini fixture. Exercises the CLI stage `run()` functions directly (not via
subprocess) so failures show a normal Python traceback, but otherwise drives them
exactly as `hivalidate-combine`/`-dedup`/`-rename` would.
"""

from pathlib import Path

from hivalidate import catalogue
from hivalidate.cli import combine, dedup, rename
from hivalidate.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


def _load_config(tmp_path):
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    config.paths.work_dir = tmp_path / "work"  # keep test output out of the fixture dir
    return config


def test_combine_dedup_rename_pipeline_end_to_end(tmp_path):
    config = _load_config(tmp_path)

    combine.run(config)
    assert config.paths.combined_catalogue.exists()
    combined = catalogue.read_votable(config.paths.combined_catalogue)
    assert len(combined) == 56  # see test_catalogue.py for how this was verified

    dedup.run(config)
    assert config.paths.deduped_catalogue.exists()
    deduped = catalogue.read_votable(config.paths.deduped_catalogue)
    assert len(deduped) < len(combined)  # this fixture is known to contain duplicates
    assert len(set(deduped["name"])) == len(deduped)  # no exact-name duplicates remain

    rename.run(config)
    renamed_files = list(config.paths.renamed_cubelets_dir.iterdir())
    assert len(renamed_files) > 0

    # Every renamed file's source name must be one that survived dedup -- this is the
    # whole point of filtering rename by keep_names (a duplicate detection's cubelets
    # must not end up in the final directory).
    kept_names = set(deduped["name"].astype(str).tolist())
    kept_names_underscored = {n.replace(" ", "_") for n in kept_names}
    for f in renamed_files:
        # filenames are "<name>_<suffix>.<ext>"; recover name via known suffixes
        matched = [n for n in kept_names_underscored if f.name.startswith(n + "_")]
        assert matched, f"{f.name} does not correspond to any surviving source"

    # Precise regression check for the bug this test suite caught during development:
    # "SoFiA J204524.82-550222.5" is detected in both Removal_011 and Removal_012 with
    # the *identical* name string, so a name-only keep-filter can't tell which run's
    # cubelets should survive -- only (source_run, id) can. Confirm the copied file's
    # bytes match the *surviving* run's original cubelet, not the removed one's.
    dup_name = "SoFiA J204524.82-550222.5"
    dup_rows = deduped[deduped["name"] == dup_name]
    assert len(dup_rows) == 1, "fixture assumption changed -- update this test"
    surviving_run, surviving_id = str(dup_rows["source_run"][0]), str(dup_rows["id"][0])

    copied = config.paths.renamed_cubelets_dir / "SoFiA_J204524.82-550222.5_cube.fits"
    expected_source = (
        FIXTURES
        / "run_sofia_mini"
        / f"{surviving_run}_cubelets"
        / f"{surviving_run}_{surviving_id}_cube.fits"
    )
    assert copied.read_bytes() == expected_source.read_bytes()


def test_dedup_fails_clearly_if_combine_was_not_run_first(tmp_path):
    config = _load_config(tmp_path)
    try:
        dedup.run(config)
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "hivalidate-combine" in str(exc)


def test_rename_fails_clearly_if_dedup_was_not_run_first(tmp_path):
    config = _load_config(tmp_path)
    combine.run(config)
    try:
        rename.run(config)
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "hivalidate-dedup" in str(exc)
