"""Optical cutout backends: SkyView (DSS2 Red, migrated from
`legacy/validate_detections.py`'s `get_opt_imag`) and Legacy Survey (new, migrated
from `legacy/download_legacy.py`'s single-file cutout API call).

Neither backend needs authentication, so both are fully testable without credentials
-- see `tests/test_cutouts_optical.py`, including a live (network-marked) smoke test
actually run during development, not just mocked.
"""

from __future__ import annotations

import io

import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from astroquery.skyview import SkyView

from hivalidate.cutouts.base import (
    CutoutBackend,
    CutoutResult,
    CutoutUnavailable,
    retry_with_backoff,
)


class _NonRetryableStatus(Exception):
    """Internal to `LegacySurveyBackend.fetch`: a non-5xx HTTP error, which retrying
    cannot fix (unlike a 5xx or connection error). Deliberately not a
    `CutoutUnavailable` so `retry_with_backoff`'s exception filter doesn't retry it;
    caught immediately after and converted to `CutoutUnavailable` for the caller.
    """


class SkyViewBackend(CutoutBackend):
    """DSS2 Red (or any other SkyView survey) via `astroquery.skyview`. SkyView's
    `get_images` takes a pixel count, not an angular size directly, so this backend
    assumes a fixed arcsec/pixel scale to convert -- 1.7 arcsec/pixel is DSS2's native
    plate scale (the value the legacy script implicitly relied on by only ever
    passing a pixel count), not independently verified against SkyView's documentation
    for every survey it can serve. If you use `survey=` other than a DSS2 variant,
    double-check this assumption still gives a sensible field of view.
    """

    name = "skyview"

    DSS2_ARCSEC_PER_PIX = 1.7

    def __init__(self, survey: str = "DSS2 Red", max_retries: int = 5):
        self.survey = survey
        self.max_retries = max_retries

    def fetch(self, position: SkyCoord, size_arcsec: float) -> CutoutResult:
        n_pix = max(int(round(size_arcsec / self.DSS2_ARCSEC_PER_PIX)), 1)

        def _query():
            images = SkyView.get_images(
                position=position, survey=self.survey, projection="Sin", pixels=n_pix
            )
            if not images:
                raise CutoutUnavailable(f"SkyView returned no images for survey {self.survey!r}")
            return images

        images = retry_with_backoff(
            _query,
            max_retries=self.max_retries,
            retryable_exceptions=(
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout,
                CutoutUnavailable,
            ),
        )
        hdu = images[0][0]
        return CutoutResult(data=hdu.data, wcs=WCS(hdu.header), provenance=f"skyview:{self.survey}")

    def is_available(self) -> tuple[bool, str]:
        try:
            # A minimal real fetch (not just a reachability ping) at a fixed, always-
            # observable test position -- proves the whole path works, at the cost of
            # one small image download during preflight.
            test_position = SkyCoord(ra=0.0, dec=0.0, unit="deg")
            self.fetch(test_position, size_arcsec=17.0)  # ~10 pixels
            return True, "OK"
        except CutoutUnavailable as exc:
            return False, str(exc)


class LegacySurveyBackend(CutoutBackend):
    """DESI Legacy Imaging Surveys cutout service (`legacysurvey.org/viewer`),
    migrated from `legacy/download_legacy.py`. Single-band FITS (not the RGB
    composite the legacy script also produced -- this backend only needs a 2D array +
    WCS to match `SkyViewBackend`'s output shape for the same validation-plot panel).

    Coverage is a known simplification: the real Legacy Survey footprint (DECaLS +
    MzLS/BASS + DES, per layer) is not a simple declination cut, and no attempt is
    made here to encode the real footprint polygon -- `check_coverage` only rules out
    positions definitely outside the DECam-based layers' declination range as a fast
    path; `fetch` (an empty/all-NaN response) is the actual authority on coverage.
    """

    name = "legacy_survey"

    #: Rough declination ceiling for the DECam-based layers (ls-dr9, ls-dr10) this
    #: backend targets. Not the true footprint (see class docstring) -- just enough
    #: to skip an obviously-hopeless request for a northern position.
    APPROX_DEC_CEILING_DEG = 34.0

    def __init__(
        self,
        layer: str = "ls-dr10",
        pixscale_arcsec: float = 0.262,
        band: str = "r",
        max_retries: int = 5,
    ):
        self.layer = layer
        self.pixscale_arcsec = pixscale_arcsec
        self.band = band
        self.max_retries = max_retries

    def check_coverage(self, position: SkyCoord) -> bool:
        return position.dec.deg < self.APPROX_DEC_CEILING_DEG

    def fetch(self, position: SkyCoord, size_arcsec: float) -> CutoutResult:
        n_pix = max(int(round(size_arcsec / self.pixscale_arcsec)), 1)
        url = (
            "https://www.legacysurvey.org/viewer/cutout.fits?"
            f"ra={position.ra.deg}&dec={position.dec.deg}&"
            f"size={n_pix}&pixscale={self.pixscale_arcsec}&"
            f"layer={self.layer}&bands={self.band}"
        )

        def _get():
            try:
                response = requests.get(url, timeout=30)
            except requests.exceptions.RequestException as exc:
                raise CutoutUnavailable(f"Legacy Survey request failed: {exc}") from exc
            # 503 (observed live during development -- the service was briefly down)
            # and other 5xx are worth retrying; a 4xx (e.g. bad request) never will
            # succeed on retry, so fail immediately instead of wasting the backoff budget.
            if response.status_code >= 500:
                raise CutoutUnavailable(f"Legacy Survey returned status {response.status_code}")
            if response.status_code != 200:
                raise _NonRetryableStatus(f"Legacy Survey returned status {response.status_code}")
            return response

        try:
            response = retry_with_backoff(
                _get, max_retries=self.max_retries, retryable_exceptions=(CutoutUnavailable,)
            )
        except _NonRetryableStatus as exc:
            raise CutoutUnavailable(str(exc)) from exc

        try:
            with fits.open(io.BytesIO(response.content)) as hdul:
                data = hdul[0].data
                header = hdul[0].header
        except OSError as exc:
            raise CutoutUnavailable(
                f"Legacy Survey response was not a valid FITS file: {exc}"
            ) from exc

        if data is None or not (data != 0).any():
            # An all-zero cutout is what the service returns for a position outside
            # its actual imaged footprint -- this is the authoritative coverage check
            # `check_coverage`'s declination heuristic can't fully replace.
            raise CutoutUnavailable(f"No {self.layer} coverage at this position (empty cutout)")

        return CutoutResult(data=data, wcs=WCS(header), provenance=f"legacy_survey:{self.layer}")

    def is_available(self) -> tuple[bool, str]:
        try:
            response = requests.head("https://www.legacysurvey.org/viewer/", timeout=10)
            if response.status_code >= 500:
                return False, f"legacysurvey.org returned status {response.status_code}"
            return True, "OK"
        except requests.exceptions.RequestException as exc:
            return False, f"Cannot reach legacysurvey.org: {exc}"
