"""Continuum cutout backends: a local field mosaic (via MontagePy, migrated from
`legacy/validate_detections.py`'s `get_cont_imag`) and RACS via CASDA (new, replaces
having no continuum image at all when no local mosaic covers a field).

`LocalContinuumBackend` was verified live against the real
`data/continuum_image/*.fits` mosaic and real source positions from
`data/run_sofia/` during development (see the Phase 2 commit message for exact
commands/output) -- both the success and the "outside image footprint" error paths.

`RacsCasdaBackend` could not be tested live during development (no CASDA/OPAL
credentials were available in that environment) -- see README.md "CASDA / RACS
access" for how to verify it. Its `query_region`/`cutout`/`download_files` usage
matches the literal examples in the astroquery CASDA docs
(https://astroquery.readthedocs.io/en/latest/casda/casda.html), not a guess from
memory, but "matches the docs" and "confirmed working end-to-end" are not the same
claim -- treat this backend as unverified until you've run
`hivalidate-check-connectivity` successfully yourself.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import keyring
import keyring.errors
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from astroquery.casda import Casda
from MontagePy.main import mSubimage

from hivalidate.cutouts.base import CutoutBackend, CutoutResult, CutoutUnavailable

logger = logging.getLogger(__name__)

#: The exact keyring service name astroquery's Casda class looks up internally
#: (astroquery/casda/core.py `_login`). Not a public constant of astroquery itself --
#: reading this from the library's source is what makes non-interactive login (via
#: pre-seeding the keyring ourselves, see `RacsCasdaBackend._ensure_login`) possible
#: without touching astroquery's private attributes. If a future astroquery version
#: changes this string, non-interactive login breaks with a clear "login failed"
#: error, not a silent wrong-password failure.
_CASDA_KEYRING_SERVICE = "astroquery:casda.csiro.au"


class LocalContinuumBackend(CutoutBackend):
    """A single local continuum mosaic FITS file covering the field (e.g.
    `data/continuum_image/image.i.WALLABY_2051-53B.SB82605.cont.taylor.0.restored.conv.fits`).

    Expects exactly one ``*.fits`` file directly inside `continuum_dir` -- this is a
    deliberate simplification matching the shipped example data (one mosaic per
    field/SB) rather than a general multi-file continuum-image resolver. A field with
    more than one local continuum candidate (different epochs, tiles, ...) needs that
    resolution logic added before this backend can be pointed at it; it will raise
    clearly rather than guess which file to use.
    """

    name = "local"

    def __init__(self, continuum_dir: str | Path):
        self.continuum_dir = Path(continuum_dir)
        self._fits_path: Path | None = None
        self._wcs: WCS | None = None

    def _resolve_file(self) -> Path:
        if self._fits_path is not None:
            return self._fits_path
        candidates = sorted(self.continuum_dir.glob("*.fits"))
        if len(candidates) != 1:
            raise CutoutUnavailable(
                f"Expected exactly one *.fits file in {self.continuum_dir}, found {len(candidates)}"
            )
        self._fits_path = candidates[0]
        return self._fits_path

    def _get_wcs(self) -> WCS:
        if self._wcs is None:
            header = fits.getheader(self._resolve_file())
            self._wcs = WCS(header).celestial
        return self._wcs

    def check_coverage(self, position: SkyCoord) -> bool:
        try:
            wcs = self._get_wcs()
        except CutoutUnavailable:
            return False
        return bool(wcs.footprint_contains(position))

    def fetch(self, position: SkyCoord, size_arcsec: float) -> CutoutResult:
        infile = self._resolve_file()
        size_deg = size_arcsec / 3600.0

        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = os.path.join(tmpdir, "cutout.fits")
            result = mSubimage(
                str(infile), outfile, position.ra.deg, position.dec.deg, size_deg, size_deg
            )
            if result.get("status") != "0":
                raise CutoutUnavailable(f"mSubimage failed: {result.get('msg', result)}")
            with fits.open(outfile) as hdul:
                data = hdul[0].data.copy()
                header = hdul[0].header.copy()

        return CutoutResult(data=data, wcs=WCS(header), provenance=f"local:{infile.name}")

    def is_available(self) -> tuple[bool, str]:
        try:
            self._resolve_file()
        except CutoutUnavailable as exc:
            return False, str(exc)
        return True, "OK"


class RacsCasdaBackend(CutoutBackend):
    """RACS continuum cutouts via CASDA (`astroquery.casda`). See the module
    docstring: implemented against the documented astroquery API, not verified live.

    Non-interactive login (see README.md for the full setup instructions): if
    `password_env` is set, this backend seeds the OS keyring itself (using the exact
    public `keyring.set_password` API astroquery's own login reads from) so
    `casda.login(username=...)` succeeds without an interactive password prompt. If
    the local keyring backend can't store a password (common on headless HPC login
    nodes with no Secret Service daemon -- `keyring.errors.NoKeyringError`), this
    raises a clear, actionable error rather than silently reconfiguring the process's
    keyring backend as a side effect.
    """

    name = "racs_casda"

    #: Coverage limit is genuinely a survey property, not a heuristic -- RACS-low
    #: covers the whole sky south of this declination (McConnell et al. 2020,
    #: [RACS] in REFERENCES.md; verified by web search 2026-07-30).
    DEC_LIMIT_DEG = 41.0

    #: Exact string CASDA uses for RACS's obs_collection, and the RACS-DR1 Stokes I
    #: filename convention, both taken verbatim from the astroquery CASDA docs
    #: example (not guessed) -- see the module docstring for the source URL.
    OBS_COLLECTION = "The Rapid ASKAP Continuum Survey"
    FILENAME_PREFIX = "RACS-DR1_"
    FILENAME_SUFFIX = "A.fits"

    def __init__(self, username_env: str = "CASDA_USERNAME", password_env: str = "CASDA_PASSWORD"):
        self.username_env = username_env
        self.password_env = password_env
        self._casda: Casda | None = None

    def check_coverage(self, position: SkyCoord) -> bool:
        return position.dec.deg < self.DEC_LIMIT_DEG

    def _ensure_login(self) -> Casda:
        if self._casda is not None:
            return self._casda

        username = os.environ.get(self.username_env)
        if not username:
            raise CutoutUnavailable(
                f"${self.username_env} is not set -- see README.md 'CASDA / RACS access'"
            )

        password = os.environ.get(self.password_env)
        if password:
            try:
                keyring.set_password(_CASDA_KEYRING_SERVICE, username, password)
            except keyring.errors.NoKeyringError as exc:
                raise CutoutUnavailable(
                    "No usable keyring backend available to store the CASDA password "
                    f"non-interactively ({exc}). See README.md 'CASDA / RACS access' "
                    "for how to configure a file-based keyring backend on a headless "
                    "HPC login node, or run the one-time interactive login there instead."
                ) from exc

        casda = Casda()
        try:
            authenticated = casda.login(username=username)
        except Exception as exc:  # astroquery raises assorted exceptions on network/auth failure
            raise CutoutUnavailable(f"CASDA login failed: {exc}") from exc
        if not authenticated:
            raise CutoutUnavailable(
                "CASDA login failed (bad credentials, or no password available -- "
                "see README.md 'CASDA / RACS access')"
            )

        self._casda = casda
        return casda

    def fetch(self, position: SkyCoord, size_arcsec: float) -> CutoutResult:
        casda = self._ensure_login()

        try:
            results = Casda.query_region(position, radius=2 * u.arcmin)
        except Exception as exc:
            raise CutoutUnavailable(f"CASDA query_region failed: {exc}") from exc

        public_data = Casda.filter_out_unreleased(results)
        subset = public_data[
            (public_data["obs_collection"] == self.OBS_COLLECTION)
            & np.char.startswith(public_data["filename"], self.FILENAME_PREFIX)
            & np.char.endswith(public_data["filename"], self.FILENAME_SUFFIX)
        ]
        if len(subset) == 0:
            raise CutoutUnavailable("No RACS image found covering this position")

        size = size_arcsec * u.arcsec
        try:
            urls = casda.cutout(subset[:1], coordinates=position, height=size, width=size)
        except Exception as exc:
            raise CutoutUnavailable(f"CASDA cutout request failed: {exc}") from exc
        if not urls:
            raise CutoutUnavailable("CASDA cutout request returned no URLs")

        with tempfile.TemporaryDirectory() as tmpdir:
            filenames = casda.download_files(urls, savedir=tmpdir)
            fits_files = [f for f in filenames if f.endswith(".fits")]
            if not fits_files:
                raise CutoutUnavailable("CASDA cutout download contained no FITS file")
            with fits.open(fits_files[0]) as hdul:
                data = hdul[0].data.copy()
                header = hdul[0].header.copy()

        provenance = f"racs_casda:{subset['filename'][0]}"
        return CutoutResult(data=data, wcs=WCS(header).celestial, provenance=provenance)

    def is_available(self) -> tuple[bool, str]:
        try:
            self._ensure_login()
        except CutoutUnavailable as exc:
            return False, str(exc)
        return True, "OK"
