"""Post-validation artifacts built from the QA output (`validated_cat.xml`):

- A CSV of each reviewed class's sources -- replaces `legacy/create_validation_csv.py`,
  much simpler now: that script had to reverse-engineer which sources were "true" by
  scanning a directory of PNG filenames and cross-referencing the SoFiA catalogue,
  because the legacy interactive script never wrote the qa flag anywhere durable
  alongside the catalogue. `validated_cat.xml` already has the `qa` column directly.
  Also adds derived physical columns (redshift, velocity, w20/w50/wm50 in km/s,
  HI mass and its error) and drops a few SoFiA/crossmatch columns not useful to a
  human reviewer (`add_derived_physical_columns`, `write_validation_csv`).
- A directory of just that class's cubelets -- replaces `legacy/extract_true_cubelets.py`.
- A directory of just that class's dry-run validation plots, pulled out of the shared
  flat `dry_run/` directory -- so, e.g., every "uncertain" or "duplicate" source can be
  flicked back through later without hunting through hundreds of unrelated PNGs.
- A mosaic FITS of the true class's moment-0 maps, reprojected onto the full field --
  replaces `legacy/mosaic_sofia_true_detections.py`. True-only: "where are the real
  detections" is the only one of these four classes that question makes sense for.
- A PNG of that same mosaic overlaid as contours on an optical background image of
  the whole field, so the overall spatial distribution of real detections can be
  seen against the sky at a glance (`hivalidate.plotting.
  build_true_detections_overview_figure`, built by `hivalidate.cli.postprocess`
  since it needs a network fetch) -- direct user request.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS
from reproject import reproject_interp
from reproject.mosaicking import reproject_and_coadd

from hivalidate import catalogue, conversions

#: Matches hivalidate.qa.FLAG_TO_NUMERIC's convention.
QA_TRUE = 1.0
QA_FALSE = 0.0
QA_UNCERTAIN = 2.0
QA_DUPLICATE = 3.0

#: Every reviewed class postprocess builds a catalogue/cubelets/plots set for, keyed
#: by the subdirectory name it's written under (`postprocess/<class_name>/`).
QA_CLASSES = {
    "true": QA_TRUE,
    "false": QA_FALSE,
    "uncertain": QA_UNCERTAIN,
    "duplicate": QA_DUPLICATE,
}


def filter_by_qa(validated_catalogue: Table, qa_values: set[float]) -> Table:
    """`validated_catalogue['qa']` is NaN for anything not yet reviewed -- `np.isin`
    correctly excludes those (NaN is never `in` a set of real numbers) without
    needing special-casing here.
    """
    mask = np.isin(np.asarray(validated_catalogue["qa"], dtype=float), list(qa_values))
    return validated_catalogue[mask]


#: Columns dropped from the postprocess CSV -- not useful for a human reviewer
#: browsing detections (direct user request). `source_run` is an internal
#: `(source_run, id)` dedup/rename key (PLAN.md issue #6), not physically
#: meaningful; `external_ra`/`external_dec`/`external_z` duplicate what's already
#: visible on the per-source dry-run plot's cross-match overlay and label. Kept:
#: `external_sep_arcsec`/`external_vel_diff_km_s`/`external_id`/
#: `external_catalogue_name`, which are still useful for judging match quality
#: without opening a plot. Silently ignored if a table doesn't have one of these
#: (e.g. no crossmatch was configured, so the external_* columns don't exist).
_CSV_DROPPED_COLUMNS = ["source_run", "external_z", "external_ra", "external_dec"]

#: Display order for the CSV's non-SoFiA columns, applied by `_reorder_csv_columns`
#: -- direct user request: derived physical parameters (redshift/velocity/linewidths/
#: HI mass) right after SoFiA's own catalogue columns end (at `freq_peak`), then the
#: surviving external-catalogue crossmatch columns, then qa/qa_comment last.
_DERIVED_PHYSICAL_COLUMN_ORDER = [
    "redshift",
    "velocity_km_s",
    "w20_km_s",
    "w50_km_s",
    "wm50_km_s",
    "log_hi_mass_msun",
    "log_hi_mass_msun_err",
]
_EXTERNAL_COLUMN_ORDER = [
    "external_catalogue_name",
    "external_id",
    "external_sep_arcsec",
    "external_vel_diff_km_s",
]
_QA_COLUMN_ORDER = ["qa", "qa_comment"]


def add_derived_physical_columns(table: Table) -> Table:
    """Add velocity-domain/redshift/HI-mass columns derived from SoFiA's native
    frequency-domain catalogue columns (`freq`, `w20`/`w50`/`wm50`, `f_sum`,
    `err_f_sum`) -- what a validator actually wants to read off the postprocess CSV,
    rather than raw SoFiA units they'd have to convert by hand (direct user request).

    Returns a copy; does not mutate `table` in place.
    """
    table = table.copy()
    freq_hz = np.asarray(table["freq"])
    redshift = conversions.freq_to_redshift(freq_hz)
    table["redshift"] = redshift
    table["velocity_km_s"] = conversions.freq_to_velocity(freq_hz)
    for width_column in ("w20", "w50", "wm50"):
        table[f"{width_column}_km_s"] = conversions.freq_width_to_velocity_dispersion(
            np.asarray(table[width_column]), freq_hz
        )

    f_sum = np.asarray(table["f_sum"])
    err_f_sum = np.asarray(table["err_f_sum"])
    if len(table) == 0:
        # astropy's Cosmology.luminosity_distance (conversions.hi_mass's main cost)
        # wraps a np.vectorize call that raises on a size-0 input rather than just
        # returning an empty array -- found live: a QA class with zero sources so
        # far (a completely normal, non-error state for postprocess) would otherwise
        # crash the whole run. No cosmology call needed for zero rows anyway.
        log_hi_mass_msun = np.array([], dtype=float)
        log_hi_mass_msun_err = np.array([], dtype=float)
    else:
        log_hi_mass_msun = conversions.hi_mass(f_sum, redshift, rest_frame="frequency")
        # log10(M) = log10(K) + log10(S) for some (measurement-error-independent) K,
        # so d(log10 M) = dS / (S * ln(10)) -- the usual dex-uncertainty propagation
        # for a quantity computed from a base-10 log of something with a linear flux
        # error.
        with np.errstate(divide="ignore", invalid="ignore"):
            log_hi_mass_msun_err = np.abs(err_f_sum / f_sum) / np.log(10)
    table["log_hi_mass_msun"] = log_hi_mass_msun
    table["log_hi_mass_msun_err"] = log_hi_mass_msun_err
    return table


def _reorder_csv_columns(table: Table) -> Table:
    """Put `_DERIVED_PHYSICAL_COLUMN_ORDER` right after SoFiA's own catalogue columns
    (whatever is left once the moved/dropped columns are set aside -- these already
    end at `freq_peak` in every real catalogue this pipeline produces, so nothing
    needs to name that column specifically), then `_EXTERNAL_COLUMN_ORDER`, then
    `_QA_COLUMN_ORDER` last. A moved/ordered column not present in `table` (e.g. no
    crossmatch was configured, so no external_* columns exist) is silently skipped.
    """
    moved = {
        *_DERIVED_PHYSICAL_COLUMN_ORDER,
        *_EXTERNAL_COLUMN_ORDER,
        *_QA_COLUMN_ORDER,
    }
    sofia_columns = [c for c in table.colnames if c not in moved]
    ordered = [
        *sofia_columns,
        *(c for c in _DERIVED_PHYSICAL_COLUMN_ORDER if c in table.colnames),
        *(c for c in _EXTERNAL_COLUMN_ORDER if c in table.colnames),
        *(c for c in _QA_COLUMN_ORDER if c in table.colnames),
    ]
    return table[ordered]


def write_validation_csv(table: Table, output_path: str | Path) -> None:
    """Adds `add_derived_physical_columns`' velocity/redshift/HI-mass columns, drops
    `_CSV_DROPPED_COLUMNS`, reorders the result (`_reorder_csv_columns`), and writes
    it via `hivalidate.catalogue.write_csv` -- kept as its own function since
    `hivalidate.cli.postprocess` calling `write_validation_csv` reads more clearly at
    the call site than the generic `write_csv`, and because this is where the
    postprocess-CSV-specific column transformations belong (the VOTable catalogues
    stay in SoFiA's native units/order).
    """
    table = add_derived_physical_columns(table)
    table.remove_columns([c for c in _CSV_DROPPED_COLUMNS if c in table.colnames])
    table = _reorder_csv_columns(table)
    catalogue.write_csv(table, output_path)


def extract_cubelets(cubelets_dir: str | Path, output_dir: str | Path, names: list[str]) -> int:
    """Copy every cubelet file for each of `names` (as they appear in the catalogue's
    `name` column, e.g. "SoFiA J210149.89-554804.6" -- space-separated, converted to
    the underscore form cubelet filenames actually use) from `cubelets_dir` into
    `output_dir`. Returns the number of files copied.
    """
    cubelets_dir = Path(cubelets_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for name in names:
        prefix = str(name).replace(" ", "_")
        for source_path in cubelets_dir.glob(f"{prefix}_*"):
            shutil.copy2(source_path, output_dir / source_path.name)
            count += 1
    return count


def extract_plots(dry_run_dir: str | Path, output_dir: str | Path, names: list[str]) -> int:
    """Copy each of `names`' dry-run validation PNG (`hivalidate.cli.dry_run` writes
    exactly one, `<source_name>.png`, per source -- unlike cubelets, no glob needed)
    from `dry_run_dir` into `output_dir`. Returns the number of files copied.

    A name with no matching PNG (source failed dry-run, or was never processed)
    contributes zero rather than raising -- a partially-completed dry-run batch is a
    normal state to postprocess against, not an error.
    """
    dry_run_dir = Path(dry_run_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for name in names:
        source_path = dry_run_dir / f"{str(name).replace(' ', '_')}.png"
        if source_path.exists():
            shutil.copy2(source_path, output_dir / source_path.name)
            count += 1
    return count


def build_mosaic(
    field_mosaic_path: str | Path, mom0_files: list[str | Path], output_path: str | Path
) -> np.ndarray:
    """Reproject and coadd `mom0_files` (each a source's cubelet moment-0 map) onto
    the WCS/shape of `field_mosaic_path` (SoFiA's own full-field moment-0 mosaic), so
    true detections can be inspected in their full-field context. Equivalent to
    `legacy/mosaic_sofia_true_detections.py`'s `make_mosaic_fits`.

    An empty `mom0_files` produces an all-zero mosaic (matching the field's own
    shape/WCS) rather than raising -- a field with zero true detections so far is a
    legitimate, if uninteresting, state to export, not an error.
    """
    field_header = fits.getheader(field_mosaic_path)
    wcs = WCS(field_header).celestial
    header = wcs.to_header()
    shape = (field_header["NAXIS2"], field_header["NAXIS1"])

    if mom0_files:
        data, _footprint = reproject_and_coadd(
            [str(f) for f in mom0_files],
            header,
            shape_out=shape,
            reproject_function=reproject_interp,
        )
    else:
        data = np.zeros(shape)
    data = np.nan_to_num(data)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fits.writeto(output_path, data, header, overwrite=True)
    return data


def field_center_and_fov(field_mosaic_path: str | Path) -> tuple[SkyCoord, float]:
    """The real sky position/angular size of `field_mosaic_path`'s own footprint --
    for fetching an optical background image the same size as the field
    (`plotting.build_true_detections_overview_figure`). Same approach as
    `plotting.reference_field_of_view_arcsec` (the real WCS pixel scale, not an
    assumed constant) but for the whole field mosaic instead of one source's mom0.
    """
    header = fits.getheader(field_mosaic_path)
    wcs = WCS(header).celestial
    ny, nx = header["NAXIS2"], header["NAXIS1"]
    scales = wcs.proj_plane_pixel_scales()
    width_arcsec = (nx * scales[0]).to(u.arcsec).value
    height_arcsec = (ny * scales[1]).to(u.arcsec).value
    center = wcs.pixel_to_world(nx / 2, ny / 2)
    return center, max(width_arcsec, height_arcsec)
