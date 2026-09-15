"""Cross-match HI detections against an external spectroscopic redshift catalogue
(e.g. DESI, GAMA) by position + velocity -- the `search_gama`-style logic PLAN.md
reserved `paths.external_redshift_catalogue` for, but that was never implemented
until now (see that config field's docstring history: an explicit v1 non-goal).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy import units as u
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
    catalogue_name: str = "External",
) -> CrossmatchResult:
    """Cross-match each row of `hi_table` (a SoFiA catalogue) against
    `external_table` (see `read_external_catalogue`) by position + velocity -- the
    same tolerance style `catalogue.deduplicate_positional` uses for self-matching
    (``vel_tol_wm50_factor * wm50_velocity + vel_tol_base_km_s``), reused here
    against an independent optical/spectroscopic redshift instead of another HI
    detection.

    Every external-catalogue row within `sep_arcsec` of an HI row is considered a
    candidate, not just the single nearest one: an earlier version used
    `SkyCoord.match_to_catalog_sky` (nearest position only) and rejected that
    source entirely if the *nearest* candidate failed the velocity tolerance, even
    when a farther-but-still-within-`sep_arcsec` candidate was a good velocity
    match -- confirmed against real data (dev session 2026-09-15): a positionally
    closer but physically unrelated interloper (11,531 km/s away) masked a real
    counterpart sitting 15" away (13-16 km/s away) for one source. Among the
    candidates that pass *both* tolerances, the closest in position wins, since
    position is the more reliable end of a broad-lined HI detection's centroid.

    Adds six columns to a copy of `hi_table`, NaN (or, for `external_catalogue_name`,
    empty) where a row has no match within tolerance:

    - ``external_z``: the matched row's redshift
    - ``external_ra``/``external_dec``: the matched row's sky position -- kept (not
      just the redshift) so `plotting.build_validation_figure` can overlay the
      actual matched source on the optical panel, the way the legacy script did for
      GAMA cross-matches
    - ``external_sep_arcsec``: angular separation to the matched row
    - ``external_vel_diff_km_s``: |HI velocity - matched optical velocity|
    - ``external_catalogue_name``: `catalogue_name` verbatim, for every row -- lets
      the figure label a match "DESI z=..." / "GAMA z=..." instead of a generic
      "External z=...", per direct user feedback that the generic label wasn't
      informative enough once more than one kind of catalogue could be in play.

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
    external_catalogue_name = np.full(n, "", dtype=object)

    if n > 0 and len(external_table) > 0:
        hi_coords = SkyCoord(ra=hi_table["ra"], dec=hi_table["dec"], unit="deg")
        ext_ra = np.asarray(external_table[ra_column])
        ext_dec = np.asarray(external_table[dec_column])
        ext_coords = SkyCoord(ra=ext_ra, dec=ext_dec, unit="deg")

        hi_velocity_km_s = conversions.freq_to_velocity(np.asarray(hi_table["freq"]))
        hi_wm50_velocity_km_s = conversions.freq_width_to_velocity_dispersion(
            np.asarray(hi_table["wm50"]), np.asarray(hi_table["freq"])
        )
        ext_z = np.asarray(external_table[z_column])
        ext_velocity_km_s = conversions.redshift_to_velocity(ext_z)
        vel_tol_km_s = vel_tol_wm50_factor * hi_wm50_velocity_km_s + vel_tol_base_km_s

        # a.search_around_sky(b, sep) returns (idx_into_b, idx_into_a, sep2d, d3d) --
        # the "self" indices come second, not first (verified empirically, not just
        # assumed from the name).
        idx_ext_pairs, idx_hi_pairs, sep2d, _ = hi_coords.search_around_sky(
            ext_coords, sep_arcsec * u.arcsec
        )
        vel_diff_km_s = np.abs(hi_velocity_km_s[idx_hi_pairs] - ext_velocity_km_s[idx_ext_pairs])
        within_vel = vel_diff_km_s <= vel_tol_km_s[idx_hi_pairs]

        idx_hi_pairs = idx_hi_pairs[within_vel]
        idx_ext_pairs = idx_ext_pairs[within_vel]
        sep_arcsec_pairs = sep2d.arcsec[within_vel]
        vel_diff_km_s = vel_diff_km_s[within_vel]

        if len(idx_hi_pairs) > 0:
            # Among each HI row's surviving candidates (passing both tolerances),
            # keep only the closest in position: sort by (hi row, separation), then
            # take the first row of each group.
            order = np.lexsort((sep_arcsec_pairs, idx_hi_pairs))
            idx_hi_sorted = idx_hi_pairs[order]
            first_of_group = np.concatenate(([True], idx_hi_sorted[1:] != idx_hi_sorted[:-1]))
            best = order[first_of_group]

            matched_hi_idx = idx_hi_pairs[best]
            matched_ext_idx = idx_ext_pairs[best]
            external_z[matched_hi_idx] = ext_z[matched_ext_idx]
            external_ra[matched_hi_idx] = ext_ra[matched_ext_idx]
            external_dec[matched_hi_idx] = ext_dec[matched_ext_idx]
            external_sep_arcsec[matched_hi_idx] = sep_arcsec_pairs[best]
            external_vel_diff_km_s[matched_hi_idx] = vel_diff_km_s[best]
            external_catalogue_name[matched_hi_idx] = catalogue_name

    hi_table["external_z"] = external_z
    hi_table["external_ra"] = external_ra
    hi_table["external_dec"] = external_dec
    hi_table["external_sep_arcsec"] = external_sep_arcsec
    hi_table["external_vel_diff_km_s"] = external_vel_diff_km_s
    hi_table["external_catalogue_name"] = external_catalogue_name
    return CrossmatchResult(table=hi_table, n_matched=int(np.sum(~np.isnan(external_z))))
