"""Unit tests for the fallback-chain/cache/retry machinery in cutouts/base.py, using
fake backends -- no network, no real survey dependency. Live backend behaviour is
tested in test_cutouts_optical.py / test_cutouts_continuum.py.
"""

import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS

from hivalidate.cutouts.base import (
    CutoutBackend,
    CutoutCache,
    CutoutResult,
    CutoutUnavailable,
    fetch_with_fallback,
    retry_with_backoff,
)

POSITION = SkyCoord(ra=10.0, dec=-30.0, unit="deg")


def _fake_wcs() -> WCS:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, -30.0]
    wcs.wcs.crpix = [5, 5]
    wcs.wcs.cdelt = [-0.001, 0.001]
    return wcs


class FakeBackend(CutoutBackend):
    def __init__(self, name, *, covers=True, fetch_result=None, fetch_error=None, calls=None):
        self.name = name
        self._covers = covers
        self._fetch_result = fetch_result
        self._fetch_error = fetch_error
        self.fetch_call_count = 0
        self.coverage_call_count = 0

    def check_coverage(self, position):
        self.coverage_call_count += 1
        return self._covers

    def fetch(self, position, size_arcsec):
        self.fetch_call_count += 1
        if self._fetch_error is not None:
            raise self._fetch_error
        return self._fetch_result

    def is_available(self):
        return True, "OK"


def _result(provenance="fake:test"):
    return CutoutResult(data=np.ones((5, 5)), wcs=_fake_wcs(), provenance=provenance)


class TestCutoutCache:
    def test_round_trips_data_and_provenance(self, tmp_path):
        cache = CutoutCache(tmp_path)
        original = _result(provenance="fake:test")
        cache.put("SoFiA J000000.00-300000.0", "fake", 30.0, original)

        loaded = cache.get("SoFiA J000000.00-300000.0", "fake", 30.0)
        assert loaded is not None
        assert np.array_equal(loaded.data, original.data)
        assert loaded.provenance == "fake:test"

    def test_miss_returns_none(self, tmp_path):
        cache = CutoutCache(tmp_path)
        assert cache.get("nonexistent", "fake", 30.0) is None

    def test_different_backend_or_size_is_a_different_cache_entry(self, tmp_path):
        cache = CutoutCache(tmp_path)
        cache.put("src", "backend_a", 30.0, _result())
        assert cache.get("src", "backend_b", 30.0) is None
        assert cache.get("src", "backend_a", 60.0) is None
        assert cache.get("src", "backend_a", 30.0) is not None


class TestFetchWithFallback:
    def test_returns_first_successful_backend(self):
        good = FakeBackend("good", fetch_result=_result("good:1"))
        result = fetch_with_fallback(POSITION, 30.0, "src", [good])
        assert result.provenance == "good:1"
        assert good.fetch_call_count == 1

    def test_falls_through_on_cutout_unavailable(self):
        bad = FakeBackend("bad", fetch_error=CutoutUnavailable("no data"))
        good = FakeBackend("good", fetch_result=_result("good:1"))
        result = fetch_with_fallback(POSITION, 30.0, "src", [bad, good])
        assert result.provenance == "good:1"
        assert bad.fetch_call_count == 1
        assert good.fetch_call_count == 1

    def test_skips_backend_that_reports_no_coverage_without_calling_fetch(self):
        no_coverage = FakeBackend("no_coverage", covers=False)
        good = FakeBackend("good", fetch_result=_result("good:1"))
        result = fetch_with_fallback(POSITION, 30.0, "src", [no_coverage, good])
        assert result.provenance == "good:1"
        assert no_coverage.fetch_call_count == 0  # coverage check short-circuited it

    def test_raises_with_combined_reasons_when_every_backend_fails(self):
        a = FakeBackend("a", fetch_error=CutoutUnavailable("reason a"))
        b = FakeBackend("b", covers=False)
        with pytest.raises(CutoutUnavailable, match="reason a"):
            fetch_with_fallback(POSITION, 30.0, "src", [a, b])

    def test_cache_hit_skips_backend_entirely(self, tmp_path):
        cache = CutoutCache(tmp_path)
        cache.put("src", "good", 30.0, _result("good:cached"))
        good = FakeBackend("good", fetch_result=_result("good:live"))

        result = fetch_with_fallback(POSITION, 30.0, "src", [good], cache=cache)
        assert result.provenance == "good:cached"
        assert good.fetch_call_count == 0

    def test_successful_fetch_populates_cache(self, tmp_path):
        cache = CutoutCache(tmp_path)
        good = FakeBackend("good", fetch_result=_result("good:live"))
        fetch_with_fallback(POSITION, 30.0, "src", [good], cache=cache)
        assert cache.get("src", "good", 30.0).provenance == "good:live"


class TestRetryWithBackoff:
    def test_succeeds_on_first_try(self):
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        assert retry_with_backoff(fn, max_retries=3, retryable_exceptions=(ValueError,)) == "ok"
        assert len(calls) == 1

    def test_retries_then_succeeds(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("transient")
            return "ok"

        result = retry_with_backoff(fn, max_retries=5, retryable_exceptions=(ValueError,))
        assert result == "ok"
        assert attempts["n"] == 3

    def test_exhausts_retries_and_raises_cutout_unavailable(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)

        def fn():
            raise ValueError("always fails")

        with pytest.raises(CutoutUnavailable):
            retry_with_backoff(fn, max_retries=3, retryable_exceptions=(ValueError,))

    def test_non_retryable_exception_propagates_immediately(self):
        def fn():
            raise KeyError("not retryable")

        with pytest.raises(KeyError):
            retry_with_backoff(fn, max_retries=3, retryable_exceptions=(ValueError,))
