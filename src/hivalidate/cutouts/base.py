"""Fallback-chain abstraction shared by the optical and continuum cutout backends.

Design (see PLAN.md section 5): each image type (optical, continuum) has a priority
list of `CutoutBackend`s. `fetch_with_fallback` tries them in order, checking an
on-disk cache first and a cheap coverage pre-check before ever hitting the network,
and moves on to the next backend on any failure rather than aborting the whole batch
(PLAN.md issue #8). Every successful result carries `provenance` -- which backend
actually supplied it -- because once there is more than one possible source per
image, the output catalogue needs to record which one was used for any given source.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

logger = logging.getLogger(__name__)


class CutoutUnavailable(Exception):
    """Raised by a backend when it cannot supply a cutout for a position -- no
    coverage, a network failure after retries, an auth failure, an empty response.
    `fetch_with_fallback` catches this and moves on to the next backend; it is not
    raised out of `fetch_with_fallback` itself unless every backend fails.
    """


@dataclass
class CutoutResult:
    data: np.ndarray
    wcs: WCS
    provenance: str  # e.g. "skyview:DSS2 Red", "legacy_survey:ls-dr9", "local", "racs"


class CutoutBackend(ABC):
    """One source of cutout images (a specific survey/service). `size_arcsec` is used
    throughout rather than a pixel count so that a cutout covers the same physical
    area on the sky regardless of which backend's native pixel scale supplied it --
    each backend converts to its own pixels/units internally.
    """

    name: str

    def check_coverage(self, position: SkyCoord) -> bool:
        """Cheap, no-network pre-check of whether this backend could plausibly cover
        `position`, to skip a network round-trip when we already know the answer is
        no. Not a guarantee -- `fetch` is always the authoritative check, and a
        backend that returns True here can still legitimately raise
        `CutoutUnavailable`. Default: no cheap check available, always try.
        """
        return True

    @abstractmethod
    def fetch(self, position: SkyCoord, size_arcsec: float) -> CutoutResult:
        """Fetch a cutout, or raise `CutoutUnavailable`."""

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Cheap connectivity/auth check for the preflight check (PLAN.md section 5)
        -- run once before a dry-run batch starts, not per-source. Returns
        (ok, message); message explains the failure (and how to fix it) when not ok.
        """


class CutoutCache:
    """On-disk cache keyed by (source name, backend name, size), as FITS files (data
    + WCS header). Shared across dry-run and QA so neither re-fetches a cutout the
    other already has.
    """

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)

    def _path(self, source_name: str, backend_name: str, size_arcsec: float) -> Path:
        safe_name = source_name.replace(" ", "_")
        return self.cache_dir / f"{safe_name}__{backend_name}__{size_arcsec:.1f}arcsec.fits"

    def get(self, source_name: str, backend_name: str, size_arcsec: float) -> CutoutResult | None:
        path = self._path(source_name, backend_name, size_arcsec)
        if not path.exists():
            return None
        with fits.open(path) as hdul:
            header = hdul[0].header
            return CutoutResult(
                data=hdul[0].data,
                wcs=WCS(header),
                provenance=header.get("HIVPROV", backend_name),
            )

    def put(
        self, source_name: str, backend_name: str, size_arcsec: float, result: CutoutResult
    ) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        header = result.wcs.to_header()
        header["HIVPROV"] = result.provenance
        path = self._path(source_name, backend_name, size_arcsec)
        fits.writeto(path, result.data, header, overwrite=True)


def fetch_with_fallback(
    position: SkyCoord,
    size_arcsec: float,
    source_name: str,
    backends: list[CutoutBackend],
    cache: CutoutCache | None = None,
) -> CutoutResult:
    """Try each backend in order (cache -> coverage check -> fetch), returning the
    first success. Raises `CutoutUnavailable` (with every backend's failure reason)
    only if all of them fail.
    """
    failures: list[str] = []
    for backend in backends:
        if cache is not None:
            cached = cache.get(source_name, backend.name, size_arcsec)
            if cached is not None:
                logger.debug("%s: cache hit for %s", backend.name, source_name)
                return cached

        try:
            if not backend.check_coverage(position):
                logger.info("%s: %s not covered, skipping", backend.name, source_name)
                failures.append(f"{backend.name}: not covered")
                continue
            result = backend.fetch(position, size_arcsec)
        except CutoutUnavailable as exc:
            logger.warning("%s: %s failed: %s", backend.name, source_name, exc)
            failures.append(f"{backend.name}: {exc}")
            continue

        if cache is not None:
            cache.put(source_name, backend.name, size_arcsec, result)
        return result

    raise CutoutUnavailable(
        f"No backend could supply a cutout for {source_name}: {'; '.join(failures)}"
    )


def retry_with_backoff(
    fn,
    *,
    max_retries: int = 5,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    base_delay_s: float = 1.0,
):
    """Exponential-backoff retry, generalized from the retry loop in
    `legacy/validate_detections.py`'s `get_opt_imag` (SkyView could be flaky under
    load). `fn` takes no arguments -- wrap the actual call in a lambda/closure.
    """
    for attempt in range(max_retries):
        try:
            return fn()
        except retryable_exceptions as exc:
            if attempt == max_retries - 1:
                raise CutoutUnavailable(f"Failed after {max_retries} attempts: {exc}") from exc
            wait_s = base_delay_s * (2**attempt)
            logger.warning(
                "Attempt %d/%d failed (%s), retrying in %.1fs",
                attempt + 1,
                max_retries,
                exc,
                wait_s,
            )
            time.sleep(wait_s)
