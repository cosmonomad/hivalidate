"""Cross-match HI detections against an external spectroscopic redshift catalogue
(e.g. DESI, GAMA) by position + velocity -- the `search_gama`-style logic PLAN.md
reserved `paths.external_redshift_catalogue` for, but that was never implemented
until now (see that config field's docstring history: an explicit v1 non-goal).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.table import Table

from hivalidate import conversions


def read_external_catalogue(
    path: str | Path,
    ra_column: str = "target_ra",
    dec_column: str = "target_dec",
    z_column: str = "z",
) -> Table:
    """Read an external spectroscopic redshift catalogue for cross-matching against
    HI detections. Uses astropy's unified I/O (`Table.read`, format auto-detected
    from the file's extension/content) rather than assuming one file format --
    unlike this repo's own SoFiA catalogues (always VOTable XML, see
    `catalogue.read_votable`), an external catalogue's format isn't under this
    pipeline's control and varies by survey/query tool. Confirmed working against a
    real DESI VOTable-XML TAP query result; also handles FITS tables, CSV, etc. --
    anything astropy's `Table.read` can identify without an explicit `format=`.

    Only `ra_column`/`dec_column`/`z_column` need to exist -- every other column in
    the source file is read but otherwise ignored. Defaults match the DESI
    catalogue this was built against (`target_ra`/`target_dec`/`z`); pass the
    actual names for a differently-named catalogue (e.g. GAMA's `RA`/`DEC`/`Z`).
    """
    table = Table.read(path)
    missing = [c for c in (ra_column, dec_column, z_column) if c not in table.colnames]
    if missing:
        raise ValueError(f"{path}: missing expected column(s) {missing!r} -- got {table.colnames}")
    return table


@dataclass
class CrossmatchResult:
    table: Table
    n_matched: int


def crossmatch_redshifts(
    hi_table: Table,
    external_table: Table,
    ra_column: str = "target_ra",
    dec_column: str = "target_dec",
    z_column: str = "z",
    sep_arcsec: float = 30.0,
    vel_tol_base_km_s: float = 30.0,
    vel_tol_wm50_factor: float = 0.6,
) -> CrossmatchResult:
    """Cross-match each row of `hi_table` (a SoFiA catalogue) against
    `external_table` (see `read_external_catalogue`) by position + velocity -- the
    same tolerance style `catalogue.deduplicate_positional` uses for self-matching
    (``vel_tol_wm50_factor * wm50_velocity + vel_tol_base_km_s``), reused here
    against an independent optical/spectroscopic redshift instead of another HI
    detection.

    Each HI row is matched to its single nearest external-catalogue row by sky
    position (`SkyCoord.match_to_catalog_sky` -- closest position wins when more
    than one external row would otherwise qualify, since position is the more
    reliable end of a broad-lined HI detection's centroid); that match only counts
    if it also falls within `sep_arcsec` and the velocity tolerance above.

    Adds five columns to a copy of `hi_table`, NaN where a row has no match within
    tolerance:

    - ``external_z``: the matched row's redshift
    - ``external_ra``/``external_dec``: the matched row's sky position -- kept (not
      just the redshift) so `plotting.build_validation_figure` can overlay the
      actual matched source on the optical panel, the way the legacy script did for
      GAMA cross-matches
    - ``external_sep_arcsec``: angular separation to the matched row
    - ``external_vel_diff_km_s``: |HI velocity - matched optical velocity|

    Returns
    -------
    CrossmatchResult with the annotated table and the number of HI rows matched.
    """
    hi_table = hi_table.copy()
    n = len(hi_table)
    external_z = np.full(n, np.nan)
    external_ra = np.full(n, np.nan)
    external_dec = np.full(n, np.nan)
    external_sep_arcsec = np.full(n, np.nan)
    external_vel_diff_km_s = np.full(n, np.nan)

    if n > 0 and len(external_table) > 0:
        hi_coords = SkyCoord(ra=hi_table["ra"], dec=hi_table["dec"], unit="deg")
        ext_ra = np.asarray(external_table[ra_column])
        ext_dec = np.asarray(external_table[dec_column])
        ext_coords = SkyCoord(ra=ext_ra, dec=ext_dec, unit="deg")

        hi_velocity_km_s = conversions.freq_to_velocity(np.asarray(hi_table["freq"]))
        hi_wm50_velocity_km_s = conversions.freq_width_to_velocity_dispersion(
            np.asarray(hi_table["wm50"]), np.asarray(hi_table["freq"])
        )
        ext_velocity_km_s = conversions.redshift_to_velocity(
            np.asarray(external_table[z_column])
        )

        idx, sep2d, _ = hi_coords.match_to_catalog_sky(ext_coords)
        vel_diff_km_s = np.abs(hi_velocity_km_s - ext_velocity_km_s[idx])
        vel_tol_km_s = vel_tol_wm50_factor * hi_wm50_velocity_km_s + vel_tol_base_km_s
        matched = (sep2d.arcsec <= sep_arcsec) & (vel_diff_km_s <= vel_tol_km_s)

        external_z[matched] = np.asarray(external_table[z_column])[idx[matched]]
        external_ra[matched] = ext_ra[idx[matched]]
        external_dec[matched] = ext_dec[idx[matched]]
        external_sep_arcsec[matched] = sep2d.arcsec[matched]
        external_vel_diff_km_s[matched] = vel_diff_km_s[matched]

    hi_table["external_z"] = external_z
    hi_table["external_ra"] = external_ra
    hi_table["external_dec"] = external_dec
    hi_table["external_sep_arcsec"] = external_sep_arcsec
    hi_table["external_vel_diff_km_s"] = external_vel_diff_km_s
    return CrossmatchResult(table=hi_table, n_matched=int(np.sum(~np.isnan(external_z))))
