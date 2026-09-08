"""Optical cutout backends: SkyView (DSS2 Red, migrated from
`legacy/validate_detections.py`'s `get_opt_imag`) and Legacy Survey (new, migrated
from `legacy/download_legacy.py`'s single-file cutout API call).

Neither backend needs authentication, so both are fully testable without credentials
-- see `tests/test_cutouts_optical.py`, including a live (network-marked) smoke test
actually run during development, not just mocked.
"""

from __future__ import annotations

import io

import numpy as np
import requests
from astropy import units as u
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
    """DSS2 Red (or any other SkyView survey) via `astroquery.skyview`.

    Requests the field of view via `get_images`'s `width`/`height` (angular
    `Quantity`) parameters, not a pixel count converted through an assumed plate
    scale -- SkyView handles that conversion itself, correctly, for whichever survey
    is selected. An earlier version of this backend assumed a fixed 1.7 arcsec/pixel
    DSS2 plate scale to convert `size_arcsec` into a pixel count; the real plate
    scale is 1.0 arcsec/pixel (confirmed live 2026-07-30 against a real SkyView
    response's CDELT), so every optical cutout had an actual field of view ~59% of
    what was requested -- smaller than the same-source continuum cutout, which
    always used real degrees via MontagePy and was correct. This is what caused the
    HI detection contour (drawn from the same real-size moment-0 data in both
    panels) to visibly appear larger on the optical panel than the continuum panel
    in `plotting.build_validation_figure`'s output -- found by inspecting real
    dry-run plots, not caught by any test, since the bug was a wrong physical
    constant, not a code path that could crash or an assertion that could fail.
    """

    name = "skyview"

    def __init__(self, survey: str = "DSS2 Red", max_retries: int = 5):
        self.survey = survey
        self.max_retries = max_retries

    def fetch(self, position: SkyCoord, size_arcsec: float) -> CutoutResult:
        def _query():
            images = SkyView.get_images(
                position=position,
                survey=self.survey,
                projection="Sin",
                width=size_arcsec * u.arcsec,
                height=size_arcsec * u.arcsec,
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


def _combine_bands_for_snr(bands: list[np.ndarray]) -> np.ndarray:
    """Inverse-variance-weighted combination of independent single-band images into
    one 'white light' image with higher signal-to-noise than any single band alone
    -- co-adding independent noise realizations of the same real structure is the
    standard way multi-band imaging helps faint-source visibility (PLAN.md-style
    reasoning: this is what motivated fetching grz instead of one band in the first
    place). Per-band noise is estimated via a robust MAD-based sigma (unlike a plain
    std, this isn't inflated by the handful of bright-star/galaxy pixels also in the
    cutout), and each band is weighted by 1/sigma**2 so a noisier band contributes
    less rather than diluting the combination.
    """
    weighted_sum = np.zeros_like(bands[0], dtype=float)
    weight_total = 0.0
    for band in bands:
        sigma = 1.4826 * np.median(np.abs(band - np.median(band)))
        if sigma == 0:
            continue
        weight = 1.0 / sigma**2
        weighted_sum += band * weight
        weight_total += weight
    if weight_total == 0:
        # Every band was perfectly uniform (only possible with synthetic/test data,
        # never a real cutout) -- nothing to weight, fall back to an unweighted sum.
        return sum(bands)
    return weighted_sum / weight_total


class LegacySurveyBackend(CutoutBackend):
    """DESI Legacy Imaging Surveys cutout service (`legacysurvey.org/viewer`),
    migrated from `legacy/download_legacy.py`. Requests the grz multi-band FITS cube
    and combines the three bands into one higher-signal-to-noise greyscale image
    (`_combine_bands_for_snr`) rather than rendering a single band -- three
    independent noise realizations of the same real source combine to reveal fainter
    structure than any one band shows alone, which is exactly what matters for
    validating a real-but-faint HI detection against its optical counterpart.

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

    #: Requested in this order; the cutout API returns the cube's leading axis in
    #: the same order, combined by `_combine_bands_for_snr` (band identity doesn't
    #: matter beyond that -- unlike an RGB composite, no channel mapping is needed).
    BANDS = "grz"

    def __init__(
        self,
        layer: str = "ls-dr10",
        pixscale_arcsec: float = 0.262,
        max_retries: int = 5,
    ):
        self.layer = layer
        self.pixscale_arcsec = pixscale_arcsec
        self.max_retries = max_retries

    def check_coverage(self, position: SkyCoord) -> bool:
        return position.dec.deg < self.APPROX_DEC_CEILING_DEG

    def fetch(self, position: SkyCoord, size_arcsec: float) -> CutoutResult:
        n_pix = max(int(round(size_arcsec / self.pixscale_arcsec)), 1)
        url = (
            "https://www.legacysurvey.org/viewer/cutout.fits?"
            f"ra={position.ra.deg}&dec={position.dec.deg}&"
            f"size={n_pix}&pixscale={self.pixscale_arcsec}&"
            f"layer={self.layer}&bands={self.BANDS}"
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
                cube = hdul[0].data
                header = hdul[0].header
        except OSError as exc:
            raise CutoutUnavailable(
                f"Legacy Survey response was not a valid FITS file: {exc}"
            ) from exc

        if cube is None or cube.ndim != 3 or cube.shape[0] != len(self.BANDS):
            shape = None if cube is None else cube.shape
            raise CutoutUnavailable(
                f"Legacy Survey response was not the expected {self.BANDS} band cube "
                f"(got shape {shape})"
            )
        if not (cube != 0).any():
            # An all-zero cutout is what the service returns for a position outside
            # its actual imaged footprint -- this is the authoritative coverage check
            # `check_coverage`'s declination heuristic can't fully replace.
            raise CutoutUnavailable(f"No {self.layer} coverage at this position (empty cutout)")

        bands = [np.nan_to_num(cube[i]) for i in range(cube.shape[0])]
        combined = _combine_bands_for_snr(bands)

        return CutoutResult(
            data=combined, wcs=WCS(header).celestial, provenance=f"legacy_survey:{self.layer}"
        )

    def is_available(self) -> tuple[bool, str]:
        try:
            response = requests.head("https://www.legacysurvey.org/viewer/", timeout=10)
            if response.status_code >= 500:
                return False, f"legacysurvey.org returned status {response.status_code}"
            return True, "OK"
        except requests.exceptions.RequestException as exc:
            return False, f"Cannot reach legacysurvey.org: {exc}"
