"""Post-validation artifacts built from the QA output (`validated_cat.xml`):

- A CSV of just the true-flagged sources -- replaces `legacy/create_validation_csv.py`,
  much simpler now: that script had to reverse-engineer which sources were "true" by
  scanning a directory of PNG filenames and cross-referencing the SoFiA catalogue,
  because the legacy interactive script never wrote the qa flag anywhere durable
  alongside the catalogue. `validated_cat.xml` already has the `qa` column directly.
- A directory of just their cubelets -- replaces `legacy/extract_true_cubelets.py`.
- A mosaic FITS of just their moment-0 maps, reprojected onto the full field --
  replaces `legacy/mosaic_sofia_true_detections.py`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS
from reproject import reproject_interp
from reproject.mosaicking import reproject_and_coadd

from hivalidate import catalogue

#: Matches hivalidate.qa.FLAG_TO_NUMERIC's convention.
QA_TRUE = 1.0


def filter_by_qa(validated_catalogue: Table, qa_values: set[float]) -> Table:
    """`validated_catalogue['qa']` is NaN for anything not yet reviewed -- `np.isin`
    correctly excludes those (NaN is never `in` a set of real numbers) without
    needing special-casing here.
    """
    mask = np.isin(np.asarray(validated_catalogue["qa"], dtype=float), list(qa_values))
    return validated_catalogue[mask]


def write_validation_csv(table: Table, output_path: str | Path) -> None:
    """Thin, stage-specific name for `hivalidate.catalogue.write_csv` -- kept as its
    own function since `hivalidate.cli.postprocess` calling `write_validation_csv`
    reads more clearly at the call site than the generic `write_csv`.
    """
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
