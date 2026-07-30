"""SoFiA catalogue I/O, multi-run combination, deduplication, and ID->name mapping.

Replaces three legacy scripts (see PLAN.md section 3 for the issues each one had):

- ``legacy/plot_detections.py``'s combine step -> `find_run_catalogues` + `combine_runs`
- ``legacy/remove_duplicate.py`` (exact-name-string match) -> `deduplicate_positional`
  (spatial + velocity cross-match; issue #5)
- ``legacy/rename_cubelets.py`` (per-run ID -> name mapping) -> `id_to_name_mapping`
  + `rename_and_copy_cubelets`, unchanged in approach (issue #6 -- SoFiA's `id` column
  resets to 1..N per run, so this must stay scoped to one run's catalogue + cubelets
  directory at a time, never applied to a combined multi-run catalogue).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io.votable import from_table, parse_single_table
from astropy.table import Table, vstack

from hivalidate import conversions


def read_votable(path: str | Path) -> Table:
    """Read a single SoFiA VOTable catalogue (``*_cat.xml``) into an astropy Table."""
    return parse_single_table(str(path)).to_table(use_names_over_ids=True)


def write_votable(table: Table, path: str | Path) -> None:
    """Write an astropy Table out as a VOTable, matching SoFiA's own format."""
    from_table(table).to_xml(str(path))


def find_run_catalogues(raw_sofia_dir: str | Path, pattern: str = "*_cat.xml") -> list[Path]:
    """Find all per-run SoFiA catalogue files in a directory, sorted for determinism.

    Default pattern matches SoFiA's own naming (``<field>_<run>_cat.xml``); pass a
    narrower pattern if `raw_sofia_dir` contains catalogues from more than one field.
    """
    raw_sofia_dir = Path(raw_sofia_dir)
    return sorted(raw_sofia_dir.glob(pattern))


def combine_runs(catalogue_paths: list[str | Path]) -> Table:
    """Vertically stack multiple per-run SoFiA catalogues into one table, sorted by RA.

    Does not deduplicate -- call `deduplicate_positional` on the result if the input
    runs can overlap spatially (true for adjacent SoFiA sub-cube runs; see PLAN.md
    issue #5).

    Adds a `source_run` column (the catalogue's filename, minus ``_cat.xml``) to every
    row before stacking. This is what lets `rename_and_copy_cubelets` later identify
    *exactly* which run+id a surviving row came from, rather than matching on `name`
    alone -- necessary because two independent duplicate detections can occasionally
    produce the exact same SoFiA-generated name string (both round to the same
    hh:mm:ss.s / dd:mm:ss.s), which would otherwise make it impossible to tell which
    run's cubelets should be kept after dedup drops one of the two rows. `id` itself is
    still not safe to use directly once combined -- it resets to 1..N per run -- but
    `(source_run, id)` together are a unique key.
    """
    if not catalogue_paths:
        raise ValueError("No catalogue paths given to combine")
    tables = []
    for p in catalogue_paths:
        table = read_votable(p)
        table["source_run"] = Path(p).name.removesuffix("_cat.xml")
        tables.append(table)
    combined = tables[0] if len(tables) == 1 else vstack(tables)
    combined.sort("ra")
    return combined


@dataclass
class DedupResult:
    table: Table
    n_removed: int
    removed_names: list[str]


def deduplicate_positional(
    table: Table,
    sep_arcsec: float = 30.0,
    vel_tol_base_km_s: float = 30.0,
    vel_tol_wm50_factor: float = 0.6,
    quality_column: str = "snr",
) -> DedupResult:
    """Remove duplicate detections using a spatial + velocity cross-match, not exact
    name-string equality (see PLAN.md issue #5 -- string matching only catches
    collisions whose SoFiA-generated names happen to round identically, and misses
    near-duplicates with slightly different centroids across adjacent runs).

    Two rows are considered the same physical detection if:

    - their sky positions are within `sep_arcsec` of each other, AND
    - their velocities (derived from `freq`) are within a tolerance that scales with
      linewidth: ``vel_tol_wm50_factor * wm50_velocity + vel_tol_base_km_s`` (the same
      functional form the legacy script used for its GAMA cross-match, reused here for
      self-matching -- a broader galaxy should tolerate a larger velocity offset
      between two independent centroid measurements of the same source).

    Within each group of mutually-matching rows, keeps the row with the highest value
    of `quality_column` (default: `snr`) and drops the rest. This is a deliberate
    choice over the legacy script's "keep whichever row came first alphabetically by
    name" -- keeping the higher-SNR detection is the more defensible default, but pass
    a different `quality_column` (e.g. "rel") if you'd rather rank by SoFiA's
    reliability metric instead.

    Returns
    -------
    DedupResult with the deduplicated table, the number of rows removed, and the
    `name` of each removed row (for logging/audit).
    """
    if len(table) == 0:
        return DedupResult(table=table, n_removed=0, removed_names=[])

    coords = SkyCoord(ra=table["ra"], dec=table["dec"], unit="deg")
    velocity_km_s = conversions.freq_to_velocity(np.asarray(table["freq"]))
    wm50_velocity_km_s = conversions.freq_width_to_velocity_dispersion(
        np.asarray(table["wm50"]), np.asarray(table["freq"])
    )

    idx1, idx2, _, _ = coords.search_around_sky(coords, sep_arcsec * u.arcsec)
    # search_around_sky includes self-matches (i==i) and both (i,j)/(j,i) orderings;
    # keep only i<j so each candidate pair is considered once.
    pair_mask = idx1 < idx2
    idx1, idx2 = idx1[pair_mask], idx2[pair_mask]

    max_wm50 = np.maximum(wm50_velocity_km_s[idx1], wm50_velocity_km_s[idx2])
    vel_tol = vel_tol_wm50_factor * max_wm50 + vel_tol_base_km_s
    vel_sep = np.abs(velocity_km_s[idx1] - velocity_km_s[idx2])
    is_duplicate_pair = vel_sep <= vel_tol

    # Union-Find to group transitively-matching rows (A matches B, B matches C -> one
    # group of 3), then keep only the best row per group by `quality_column`.
    parent = list(range(len(table)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i, j in zip(idx1[is_duplicate_pair], idx2[is_duplicate_pair]):
        union(int(i), int(j))

    groups: dict[int, list[int]] = {}
    for i in range(len(table)):
        groups.setdefault(find(i), []).append(i)

    quality = np.asarray(table[quality_column])
    keep_mask = np.zeros(len(table), dtype=bool)
    removed_names: list[str] = []
    for members in groups.values():
        if len(members) == 1:
            keep_mask[members[0]] = True
            continue
        best = max(members, key=lambda i: quality[i])
        keep_mask[best] = True
        removed_names.extend(str(table["name"][i]) for i in members if i != best)

    deduped = table[keep_mask]
    return DedupResult(table=deduped, n_removed=len(removed_names), removed_names=removed_names)


def id_to_name_mapping(catalogue_table: Table) -> dict[str, str]:
    """Map a single run's SoFiA numeric `id` (as a string) to its source `name`, with
    spaces replaced by underscores to match cubelet filenames (e.g. SoFiA writes
    ``SB82605_Removal_001_<id>_cube.fits`` and the catalogue name is
    ``"SoFiA J210149.89-554804.6"`` -> ``"SoFiA_J210149.89-554804.6"``).

    Must be called with a *single run's* table, never a combined multi-run one -- see
    the module docstring on why `id` resets to 1..N per run (PLAN.md issue #6).
    """
    return {
        str(row_id): str(name).replace(" ", "_")
        for row_id, name in zip(catalogue_table["id"], catalogue_table["name"])
    }


def rename_and_copy_cubelets(
    catalogue_path: str | Path,
    cubelets_dir: str | Path,
    output_dir: str | Path,
    dry_run: bool = False,
    keep_keys: set[tuple[str, str]] | None = None,
) -> int:
    """Copy every file in a run's cubelets directory to `output_dir`, renaming the
    leading ``<field>_<run>_<id>_`` to ``<name>_`` using that run's own catalogue for
    the ID->name mapping. Equivalent to ``legacy/rename_cubelets.py``'s
    `process_renaming`, reimplemented on top of `id_to_name_mapping` instead of raw
    ElementTree parsing.

    `keep_keys`, if given, restricts copying to `(source_run, id)` pairs in the set --
    pass keys built from `deduplicate_positional`'s surviving rows (using the
    `source_run` column `combine_runs` adds) so duplicate detections dropped from the
    catalogue don't still end up with cubelet files in the combined output directory.
    This is deliberately keyed on `(source_run, id)` rather than `name`: two
    independent duplicate detections can occasionally produce the exact same
    SoFiA-generated name string, which would make a name-only filter unable to tell
    which run's cubelets to keep -- `(source_run, id)` is always unique.
    `source_run` for this function is `catalogue_path`'s own filename (minus
    ``_cat.xml``), matching what `combine_runs` stores.

    Returns the number of files copied (or that would be copied, if `dry_run=True`).
    """
    catalogue_path = Path(catalogue_path)
    cubelets_dir = Path(cubelets_dir)
    output_dir = Path(output_dir)

    mapping = id_to_name_mapping(read_votable(catalogue_path))

    # e.g. SB82605_Removal_001_cat.xml -> SB82605_Removal_001
    base_prefix = catalogue_path.name.removesuffix("_cat.xml")

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for source_path in sorted(cubelets_dir.iterdir()):
        filename = source_path.name
        if not filename.startswith(base_prefix + "_"):
            continue
        remainder = filename[len(base_prefix) + 1 :]  # "<id>_<suffix>"
        parts = remainder.split("_", 1)
        if len(parts) < 2:
            continue
        source_id, suffix = parts
        if source_id not in mapping:
            continue
        if keep_keys is not None and (base_prefix, source_id) not in keep_keys:
            continue
        new_name = f"{mapping[source_id]}_{suffix}"
        if not dry_run:
            shutil.copy2(source_path, output_dir / new_name)
        count += 1

    return count
