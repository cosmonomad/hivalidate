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
    id_column: str | None = None,
) -> Table:
    """Read an external spectroscopic redshift catalogue for cross-matching against
    HI detections. Uses astropy's unified I/O (`Table.read`, format auto-detected
    from the file's extension/content) rather than assuming one file format --
    unlike this repo's own SoFiA catalogues (always VOTable XML, see
    `catalogue.read_votable`), an external catalogue's format isn't under this
    pipeline's control and varies by survey/query tool. Confirmed working against a
    real DESI VOTable-XML TAP query result; also handles FITS tables, CSV, etc. --
    anything astropy's `Table.read` can identify without an explicit `format=`.

    `ra_column`/`dec_column`/`z_column` always need to exist -- every other column
    in the source file is read but otherwise ignored. Defaults match the DESI
    catalogue this was built against (`target_ra`/`target_dec`/`z`); pass the
    actual names for a differently-named catalogue (e.g. GAMA's `RA`/`DEC`/`Z`).
    `id_column` (e.g. DESI's `target_id`, GAMA's `CATAID`) is optional -- only
    validated if given, since an ID isn't needed for the match itself, only for
    display (see `crossmatch_redshifts`).
    """
    table = Table.read(path)
    required = [ra_column, dec_column, z_column]
    if id_column is not None:
        required.append(id_column)
    missing = [c for c in required if c not in table.colnames]
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
    id_column: str | None = None,
) -> CrossmatchResult:
    """Cross-match each row of `hi_table` (a SoFiA catalogue) against
    `external_table` (see `read_external_catalogue`) by position + velocity -- the
    same tolerance style `catalogue.deduplicate_positional` uses for self-matching
    (``vel_tol_wm50_factor * wm50_velocity + vel_tol_base_km_s``), reused here
    against an independent optical/spectroscopic redshift instead of another HI
    detection.

    Default provenance (direct user input, dev session 2026-09-19; previously
    undocumented, both here and in the legacy script this was ported from):
    `sep_arcsec`'s default (30") is set by ASKAP's own beam size, since that's what
    limits how precisely a SoFiA-derived HI position can be centroided in the first
    place; `vel_tol_base_km_s`'s default (30 km/s) is set by DESI's typical
    spectroscopic redshift error -- both chosen for the instruments actually in
    play here, not arbitrary round numbers. Empirically validated against real
    NGC4808 DESI crossmatch data the same day: a randomized-position control (200
    trials, DESI positions shifted within the field, breaking any real
    association) found ~0.1 chance matches on average vs. 160 real ones (>99.9%
    estimated purity at these defaults), and `n_matched` is flat across a wide
    range around both defaults (`vel_tol_wm50_factor` 0.4-0.8 and
    `vel_tol_base_km_s` 0-40 all give the identical 160) -- so besides being
    physically motivated, the exact values aren't sitting on a sensitive edge.

    Keeps *every* external-catalogue row within `sep_arcsec` that also passes the
    velocity tolerance, not just one -- an HI detection can legitimately have more
    than one real optical counterpart (an interacting pair, a gas-rich group, a
    tidal feature) since the HI disk is often more spatially extended than any
    single galaxy it overlaps, per direct user feedback. This also matches the
    legacy script's own `search_gama`, which returned and plotted every GAMA match,
    not just the closest -- an earlier version of this function collapsed to a
    single nearest-position match per source, which was a real regression against
    that behaviour (and separately had its own bug: rejecting a source outright
    when its nearest-position candidate failed velocity tolerance even though a
    farther, still-in-range candidate would have passed -- confirmed against real
    data, dev session 2026-09-15, before this rewrite; now moot, since all
    in-tolerance candidates are kept).

    Adds seven columns to a copy of `hi_table`:

    - ``external_z``: matched redshift(s) -- a variable-length float array per row
      (empty if unmatched, length >1 if multiple counterparts), sorted closest-in-
      position first
    - ``external_ra``/``external_dec``: matched sky position(s), same shape as
      `external_z` -- kept (not just the redshift) so
      `plotting.build_validation_figure` can overlay the actual matched source(s)
      on the optical panel, the way the legacy script did for GAMA cross-matches
    - ``external_sep_arcsec``/``external_vel_diff_km_s``: angular separation /
      |HI velocity - optical velocity| for each match, same shape as `external_z`
    - ``external_id``: each match's own catalogue ID (from `id_column`, e.g. DESI's
      `target_id`), same shape as `external_z` -- empty (not just unpopulated) for
      every row if `id_column` is left unset, same as an unmatched row's `external_z`
    - ``external_catalogue_name``: `catalogue_name` verbatim (a single string, not
      an array -- one external catalogue per `crossmatch_redshifts` call), empty
      for a row with no match

    Returns
    -------
    CrossmatchResult with the annotated table and the number of HI rows with at
    least one match (not the total number of match *pairs*, which can be higher).
    """
    hi_table = hi_table.copy()
    n = len(hi_table)
    external_z: list[np.ndarray] = [np.array([], dtype=float) for _ in range(n)]
    external_ra: list[np.ndarray] = [np.array([], dtype=float) for _ in range(n)]
    external_dec: list[np.ndarray] = [np.array([], dtype=float) for _ in range(n)]
    external_sep_arcsec: list[np.ndarray] = [np.array([], dtype=float) for _ in range(n)]
    external_vel_diff_km_s: list[np.ndarray] = [np.array([], dtype=float) for _ in range(n)]
    external_id: list[np.ndarray] = [np.array([], dtype=object) for _ in range(n)]
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
        ext_id = np.asarray(external_table[id_column]) if id_column is not None else None

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
            # Group every surviving candidate by HI row, closest-in-position first
            # within each group.
            order = np.lexsort((sep_arcsec_pairs, idx_hi_pairs))
            idx_hi_sorted = idx_hi_pairs[order]
            boundaries = np.flatnonzero(np.diff(idx_hi_sorted)) + 1
            for hi_group, ext_group, sep_group, vel_group in zip(
                np.split(idx_hi_sorted, boundaries),
                np.split(idx_ext_pairs[order], boundaries),
                np.split(sep_arcsec_pairs[order], boundaries),
                np.split(vel_diff_km_s[order], boundaries),
            ):
                hi_idx = int(hi_group[0])
                external_z[hi_idx] = ext_z[ext_group]
                external_ra[hi_idx] = ext_ra[ext_group]
                external_dec[hi_idx] = ext_dec[ext_group]
                external_sep_arcsec[hi_idx] = sep_group
                external_vel_diff_km_s[hi_idx] = vel_group
                if ext_id is not None:
                    external_id[hi_idx] = ext_id[ext_group]
                external_catalogue_name[hi_idx] = catalogue_name

    # dtype=object forced explicitly, not left to numpy's own inference: a plain
    # `hi_table[col] = [...]` assignment lets numpy pick the array's dtype/shape
    # from the list's actual contents, and when *every* row's array happens to be
    # empty (found live: a crossmatch with zero matches anywhere in the whole
    # table), numpy collapses that to a perfectly rectangular `(n, 0)` float64
    # array instead of an object array of ragged (here, all zero-length) arrays --
    # a real astropy/numpy VOTable round-trip bug for that specific degenerate
    # shape (`IndexError: index 0 is out of bounds for axis 0 with size 0`, from
    # astropy trying to sample a fill value from an empty axis). Forcing
    # dtype=object keeps every row a genuine ragged array regardless of length, so
    # this degenerate case can't arise no matter how many (or how few) rows match.
    hi_table["external_z"] = np.array(external_z, dtype=object)
    hi_table["external_ra"] = np.array(external_ra, dtype=object)
    hi_table["external_dec"] = np.array(external_dec, dtype=object)
    hi_table["external_sep_arcsec"] = np.array(external_sep_arcsec, dtype=object)
    hi_table["external_vel_diff_km_s"] = np.array(external_vel_diff_km_s, dtype=object)
    hi_table["external_id"] = np.array(external_id, dtype=object)
    hi_table["external_catalogue_name"] = external_catalogue_name
    n_matched = sum(1 for z in external_z if len(z) > 0)
    return CrossmatchResult(table=hi_table, n_matched=n_matched)
