from pathlib import Path

import pytest

from hivalidate import catalogue

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "run_sofia_mini"

# Row counts verified directly against each run's XML (`len(parse_single_table(...))`),
# not derived from the code under test. Note: `grep -vc '^#' *_cat.txt` overcounts by
# one per run -- SoFiA's plain-text catalogue has a blank (non-'#') line in its header
# block, which is not a data row.
EXPECTED_ROWS_PER_RUN = {"001": 10, "002": 11, "003": 12, "011": 10, "012": 13}


def test_find_run_catalogues_finds_all_fixture_runs():
    found = catalogue.find_run_catalogues(FIXTURE_DIR)
    assert [p.name for p in found] == sorted(
        f"SB82605_Removal_{n}_cat.xml" for n in EXPECTED_ROWS_PER_RUN
    )


def test_combine_runs_row_count_matches_sum_of_individual_runs():
    paths = catalogue.find_run_catalogues(FIXTURE_DIR)
    combined = catalogue.combine_runs(paths)
    assert len(combined) == sum(EXPECTED_ROWS_PER_RUN.values())


def test_combine_runs_is_sorted_by_ra():
    paths = catalogue.find_run_catalogues(FIXTURE_DIR)
    combined = catalogue.combine_runs(paths)
    ra = list(combined["ra"])
    assert ra == sorted(ra)


def test_combine_runs_adds_source_run_provenance_column():
    paths = catalogue.find_run_catalogues(FIXTURE_DIR)
    combined = catalogue.combine_runs(paths)
    assert set(combined["source_run"]) == {f"SB82605_Removal_{n}" for n in EXPECTED_ROWS_PER_RUN}


def test_combine_runs_rejects_empty_input():
    with pytest.raises(ValueError):
        catalogue.combine_runs([])


def test_deduplicate_positional_catches_known_cross_run_duplicate():
    # Ground truth from the original repo audit: "SoFiA J204524.82-550222.5" is
    # independently detected in both Removal_011 and Removal_012 (adjacent sub-cube
    # runs catching the same source near their shared boundary).
    paths = catalogue.find_run_catalogues(FIXTURE_DIR)
    combined = catalogue.combine_runs(paths)
    before = sum(combined["name"] == "SoFiA J204524.82-550222.5")
    assert before == 2, "fixture assumption changed -- update this test's ground truth"

    result = catalogue.deduplicate_positional(combined)

    after = sum(result.table["name"] == "SoFiA J204524.82-550222.5")
    assert after == 1
    assert result.n_removed >= 1
    assert "SoFiA J204524.82-550222.5" in result.removed_names


def test_deduplicate_positional_keeps_higher_snr_row_of_a_duplicate_pair():
    paths = catalogue.find_run_catalogues(FIXTURE_DIR)
    combined = catalogue.combine_runs(paths)
    dup_rows = combined[combined["name"] == "SoFiA J204524.82-550222.5"]
    better_snr = max(dup_rows["snr"])

    result = catalogue.deduplicate_positional(combined)
    kept_row = result.table[result.table["name"] == "SoFiA J204524.82-550222.5"]
    assert kept_row["snr"][0] == better_snr


def test_deduplicate_positional_leaves_no_remaining_duplicate_pairs():
    # General invariant, not a magic row count: after dedup, no two surviving rows
    # should still match each other under the same spatial+velocity criteria used to
    # find duplicates in the first place. (Discovered while writing this test: this
    # 5-run fixture has 14 near-duplicate pairs/clusters, not just the one exact-name
    # match found by the legacy string-matching script -- adjacent SoFiA runs
    # frequently redetect the same source with a slightly different fitted centroid,
    # which is exactly the gap positional dedup is meant to close.)
    paths = catalogue.find_run_catalogues(FIXTURE_DIR)
    combined = catalogue.combine_runs(paths)
    result = catalogue.deduplicate_positional(combined)
    assert result.n_removed > 0  # this fixture is known to contain duplicates

    reresult = catalogue.deduplicate_positional(result.table)
    assert reresult.n_removed == 0, (
        f"deduplicating an already-deduplicated table should be a no-op, "
        f"but it removed {reresult.removed_names}"
    )


def test_deduplicate_positional_only_merges_sources_with_consistent_velocity():
    # Spot check against a manually-verified triplet: three rows within ~9 arcsec of
    # each other (well inside a single ASKAP beam) and within ~2 km/s in velocity --
    # unambiguously the same physical source detected three times.
    paths = catalogue.find_run_catalogues(FIXTURE_DIR)
    combined = catalogue.combine_runs(paths)
    triplet = {
        "SoFiA J205935.85-550418.3",
        "SoFiA J205934.86-550420.7",
        "SoFiA J205934.81-550420.7",
    }
    result = catalogue.deduplicate_positional(combined)
    surviving = set(result.table["name"]) & triplet
    assert len(surviving) == 1


def test_deduplicate_positional_on_empty_table_is_a_no_op():
    paths = catalogue.find_run_catalogues(FIXTURE_DIR)
    combined = catalogue.combine_runs(paths)
    result = catalogue.deduplicate_positional(combined[:0])
    assert len(result.table) == 0
    assert result.n_removed == 0


def test_id_to_name_mapping_matches_known_fixture_values():
    table = catalogue.read_votable(FIXTURE_DIR / "SB82605_Removal_001_cat.xml")
    mapping = catalogue.id_to_name_mapping(table)
    # Verified directly against the XML by hand, not derived from the function under test.
    assert mapping["1"] == "SoFiA_J210149.89-554804.6"
    assert mapping["3"] == "SoFiA_J210029.15-545824.9"
    assert " " not in mapping["1"]


def test_rename_and_copy_cubelets_dry_run_does_not_touch_disk(tmp_path):
    output_dir = tmp_path / "renamed"
    count = catalogue.rename_and_copy_cubelets(
        FIXTURE_DIR / "SB82605_Removal_001_cat.xml",
        FIXTURE_DIR / "SB82605_Removal_001_cubelets",
        output_dir,
        dry_run=True,
    )
    assert count > 0
    assert not output_dir.exists()


def test_rename_and_copy_cubelets_writes_correctly_renamed_files(tmp_path):
    output_dir = tmp_path / "renamed"
    count = catalogue.rename_and_copy_cubelets(
        FIXTURE_DIR / "SB82605_Removal_001_cat.xml",
        FIXTURE_DIR / "SB82605_Removal_001_cubelets",
        output_dir,
    )
    renamed = sorted(p.name for p in output_dir.iterdir())
    assert count == len(renamed)
    assert "SoFiA_J210149.89-554804.6_cube.fits" in renamed
    assert "SoFiA_J210029.15-545824.9_mom0.fits" in renamed
    # Nothing from the original run-scoped filenames should have leaked through.
    assert not any("Removal_001_1_" in name for name in renamed)


def test_rename_and_copy_cubelets_respects_keep_keys_filter(tmp_path):
    output_dir = tmp_path / "renamed"
    # Keep only id "1" (-> SoFiA_J210149.89-554804.6) of the ten sources in run 001.
    count = catalogue.rename_and_copy_cubelets(
        FIXTURE_DIR / "SB82605_Removal_001_cat.xml",
        FIXTURE_DIR / "SB82605_Removal_001_cubelets",
        output_dir,
        keep_keys={("SB82605_Removal_001", "1")},
    )
    renamed = sorted(p.name for p in output_dir.iterdir())
    assert count == len(renamed)
    assert all(name.startswith("SoFiA_J210149.89-554804.6_") for name in renamed)
    assert "SoFiA_J210029.15-545824.9_mom0.fits" not in renamed


def test_rename_and_copy_cubelets_keep_keys_disambiguates_identical_names_across_runs(tmp_path):
    # "SoFiA J204524.82-550222.5" is independently detected in both Removal_011 and
    # Removal_012 with the *same* name string (see test_catalogue duplicate tests) --
    # a name-only filter cannot tell these apart, which is exactly why keep_keys is
    # keyed on (source_run, id) instead. Ask for only the Removal_012 copy and confirm
    # the Removal_011 copy of the identically-named source is excluded.
    output_dir = tmp_path / "renamed"
    table_012 = catalogue.read_votable(FIXTURE_DIR / "SB82605_Removal_012_cat.xml")
    id_012 = str(table_012[table_012["name"] == "SoFiA J204524.82-550222.5"]["id"][0])

    catalogue.rename_and_copy_cubelets(
        FIXTURE_DIR / "SB82605_Removal_011_cat.xml",
        FIXTURE_DIR / "SB82605_Removal_011_cubelets",
        output_dir,
        keep_keys={("SB82605_Removal_012", id_012)},  # deliberately the *other* run's key
    )
    assert list(output_dir.iterdir()) == [] if output_dir.exists() else True

    catalogue.rename_and_copy_cubelets(
        FIXTURE_DIR / "SB82605_Removal_012_cat.xml",
        FIXTURE_DIR / "SB82605_Removal_012_cubelets",
        output_dir,
        keep_keys={("SB82605_Removal_012", id_012)},
    )
    renamed = sorted(p.name for p in output_dir.iterdir())
    assert any(name.startswith("SoFiA_J204524.82-550222.5_") for name in renamed)


def test_rename_and_copy_cubelets_preserves_file_content(tmp_path):
    output_dir = tmp_path / "renamed"
    catalogue.rename_and_copy_cubelets(
        FIXTURE_DIR / "SB82605_Removal_001_cat.xml",
        FIXTURE_DIR / "SB82605_Removal_001_cubelets",
        output_dir,
    )
    original = FIXTURE_DIR / "SB82605_Removal_001_cubelets" / "SB82605_Removal_001_1_cube.fits"
    renamed = output_dir / "SoFiA_J210149.89-554804.6_cube.fits"
    assert renamed.read_bytes() == original.read_bytes()
