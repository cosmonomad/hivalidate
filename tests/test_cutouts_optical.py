"""Tests for the optical cutout backends.

Two tiers: fast mocked unit tests (always run) that check our own logic -- URL/pixel
construction, error handling, provenance strings -- and a `network`-marked class that
hits the real services. Neither SkyView nor Legacy Survey need credentials, so the
network tests were actually run during development (`pytest -m network
tests/test_cutouts_optical.py`) to confirm both backends really work, not just that
they're plausible against the docs. They're excluded from the default test run
(`addopts = "-m 'not network'"` in pyproject.toml) so CI stays fast and independent of
an external service being up.
"""

import io

import numpy as np
import pytest
import requests
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits

from hivalidate.cutouts.base import CutoutUnavailable
from hivalidate.cutouts.optical import LegacySurveyBackend, SkyViewBackend

POSITION = SkyCoord(ra=315.4611, dec=-55.8032, unit="deg")  # a real source from data/run_sofia


class FakeHDU:
    def __init__(self, data, header):
        self.data = data
        self.header = header


def _fake_skyview_header():
    return fits.Header(
        {
            "CTYPE1": "RA---SIN",
            "CTYPE2": "DEC--SIN",
            "CRVAL1": 315.4611,
            "CRVAL2": -55.8032,
            "CRPIX1": 5,
            "CRPIX2": 5,
            "CDELT1": -1.0 / 3600,
            "CDELT2": 1.0 / 3600,
        }
    )


class TestSkyViewBackendMocked:
    def test_requests_field_of_view_as_an_angular_quantity_not_a_pixel_count(self, monkeypatch):
        # Regression test for the real bug found by inspecting dry-run output: a
        # hardcoded (and wrong) assumed plate scale used to convert size_arcsec into
        # a pixel count, silently returning too small a field of view. Requesting
        # width/height directly (in real angular units) removes the assumption
        # entirely rather than requiring a corrected constant.
        captured = {}

        def fake_get_images(*, position, survey, projection, width, height):
            captured["width"] = width
            captured["height"] = height
            hdu = FakeHDU(np.ones((10, 10)), _fake_skyview_header())
            return [[hdu]]

        monkeypatch.setattr("hivalidate.cutouts.optical.SkyView.get_images", fake_get_images)
        backend = SkyViewBackend()
        backend.fetch(POSITION, size_arcsec=170.0)
        assert captured["width"] == 170.0 * u.arcsec
        assert captured["height"] == 170.0 * u.arcsec

    def test_provenance_includes_survey_name(self, monkeypatch):
        def fake_get_images(**kwargs):
            return [[FakeHDU(np.ones((5, 5)), _fake_skyview_header())]]

        monkeypatch.setattr("hivalidate.cutouts.optical.SkyView.get_images", fake_get_images)
        backend = SkyViewBackend(survey="DSS2 Red")
        result = backend.fetch(POSITION, size_arcsec=17.0)
        assert result.provenance == "skyview:DSS2 Red"

    def test_empty_image_list_raises_cutout_unavailable(self, monkeypatch):
        monkeypatch.setattr("hivalidate.cutouts.optical.SkyView.get_images", lambda **kw: [])
        backend = SkyViewBackend(max_retries=1)
        with pytest.raises(CutoutUnavailable):
            backend.fetch(POSITION, size_arcsec=17.0)

    def test_retries_on_connection_error_then_succeeds(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        attempts = {"n": 0}

        def flaky_get_images(**kwargs):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise requests.exceptions.ConnectionError("flaky")
            return [[FakeHDU(np.ones((5, 5)), _fake_skyview_header())]]

        monkeypatch.setattr("hivalidate.cutouts.optical.SkyView.get_images", flaky_get_images)
        backend = SkyViewBackend(max_retries=5)
        result = backend.fetch(POSITION, size_arcsec=17.0)
        assert attempts["n"] == 3
        assert result.provenance == "skyview:DSS2 Red"


def _fake_grz_cube(size=10, fill=1.0):
    return np.full((3, size, size), fill)


class TestLegacySurveyBackendMocked:
    def test_check_coverage_rejects_far_northern_declination(self):
        backend = LegacySurveyBackend()
        far_north = SkyCoord(ra=180.0, dec=60.0, unit="deg")
        assert not backend.check_coverage(far_north)
        assert backend.check_coverage(POSITION)

    def test_builds_expected_cutout_url(self, monkeypatch):
        captured = {}

        def fake_get(url, timeout):
            captured["url"] = url
            buf = io.BytesIO()
            fits.writeto(buf, _fake_grz_cube(), overwrite=True)
            return _FakeResponse(200, buf.getvalue())

        monkeypatch.setattr("hivalidate.cutouts.optical.requests.get", fake_get)
        backend = LegacySurveyBackend(layer="ls-dr10", pixscale_arcsec=0.262)
        backend.fetch(POSITION, size_arcsec=26.2)
        assert "layer=ls-dr10" in captured["url"]
        assert "bands=grz" in captured["url"]
        assert f"ra={POSITION.ra.deg}" in captured["url"]
        assert "size=100" in captured["url"]  # 26.2 / 0.262

    def test_fetch_combines_bands_into_a_higher_snr_single_image(self, monkeypatch):
        # The whole point of fetching all three bands instead of one: independent
        # noise realizations of the same real source should combine to less noise
        # than the noisiest band carries alone (inverse-variance weighting).
        rng = np.random.default_rng(0)
        g = rng.normal(0, 1.0, size=(20, 20))
        r = rng.normal(0, 2.0, size=(20, 20))
        z = rng.normal(0, 3.0, size=(20, 20))
        cube = np.stack([g, r, z])

        def fake_get(url, timeout):
            buf = io.BytesIO()
            fits.writeto(buf, cube, overwrite=True)
            return _FakeResponse(200, buf.getvalue())

        monkeypatch.setattr("hivalidate.cutouts.optical.requests.get", fake_get)
        backend = LegacySurveyBackend()
        result = backend.fetch(POSITION, size_arcsec=26.2)
        assert result.data.ndim == 2
        assert result.data.shape == (20, 20)
        assert result.data.std() < z.std()

    def test_client_error_status_fails_immediately_without_retrying(self, monkeypatch):
        # A 4xx is never fixed by retrying -- assert it does NOT sleep/retry, by not
        # mocking time.sleep at all: if the code tried to retry, this test would hang
        # for real seconds and could time out, which is the point of the assertion.
        call_count = {"n": 0}

        def fake_get(url, timeout):
            call_count["n"] += 1
            return _FakeResponse(404, b"")

        monkeypatch.setattr("hivalidate.cutouts.optical.requests.get", fake_get)
        backend = LegacySurveyBackend()
        with pytest.raises(CutoutUnavailable, match="404"):
            backend.fetch(POSITION, size_arcsec=26.2)
        assert call_count["n"] == 1

    def test_5xx_status_retries_then_raises_cutout_unavailable(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        call_count = {"n": 0}

        def fake_get(url, timeout):
            call_count["n"] += 1
            return _FakeResponse(503, b"")

        monkeypatch.setattr("hivalidate.cutouts.optical.requests.get", fake_get)
        backend = LegacySurveyBackend(max_retries=3)
        with pytest.raises(CutoutUnavailable, match="503"):
            backend.fetch(POSITION, size_arcsec=26.2)
        assert call_count["n"] == 3

    def test_5xx_then_success_is_recovered_by_retry(self, monkeypatch):
        # Regression test for the real 503 observed live against legacysurvey.org
        # during development (see the module docstring) -- this backend didn't retry
        # at all before that was found.
        monkeypatch.setattr("time.sleep", lambda _: None)
        attempts = {"n": 0}

        def fake_get(url, timeout):
            attempts["n"] += 1
            if attempts["n"] < 2:
                return _FakeResponse(503, b"")
            buf = io.BytesIO()
            fits.writeto(buf, _fake_grz_cube(), overwrite=True)
            return _FakeResponse(200, buf.getvalue())

        monkeypatch.setattr("hivalidate.cutouts.optical.requests.get", fake_get)
        backend = LegacySurveyBackend(max_retries=5)
        result = backend.fetch(POSITION, size_arcsec=26.2)
        assert attempts["n"] == 2
        assert result.provenance.startswith("legacy_survey:")

    def test_all_zero_data_raises_cutout_unavailable_not_covered(self, monkeypatch):
        def fake_get(url, timeout):
            buf = io.BytesIO()
            fits.writeto(buf, _fake_grz_cube(fill=0.0), overwrite=True)
            return _FakeResponse(200, buf.getvalue())

        monkeypatch.setattr("hivalidate.cutouts.optical.requests.get", fake_get)
        backend = LegacySurveyBackend()
        with pytest.raises(CutoutUnavailable, match="No .* coverage"):
            backend.fetch(POSITION, size_arcsec=26.2)

    def test_network_error_retries_then_raises_cutout_unavailable(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)

        def fake_get(url, timeout):
            raise requests.exceptions.ConnectionError("no route")

        monkeypatch.setattr("hivalidate.cutouts.optical.requests.get", fake_get)
        backend = LegacySurveyBackend(max_retries=2)
        with pytest.raises(CutoutUnavailable):
            backend.fetch(POSITION, size_arcsec=26.2)


class _FakeResponse:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content


@pytest.mark.network
class TestOpticalBackendsLive:
    """Actually run during development against the real services -- see the module
    docstring. Re-run with `pytest -m network tests/test_cutouts_optical.py -v`
    whenever these backends change, since the mocked tests above can't catch a real
    API contract change.
    """

    def test_skyview_returns_a_real_dss2_cutout(self):
        backend = SkyViewBackend()
        result = backend.fetch(POSITION, size_arcsec=170.0)
        assert result.data.shape[0] > 0
        assert result.provenance == "skyview:DSS2 Red"

    def test_legacy_survey_returns_a_real_cutout_at_a_covered_position(self):
        # POSITION (dec ~ -55.8) is well south of DES/DECaLS's northern edge, but
        # actual DES coverage is patchy in RA/Dec -- this specific position was
        # checked during development to actually have Legacy Survey imaging.
        backend = LegacySurveyBackend()
        result = backend.fetch(POSITION, size_arcsec=26.2)
        assert result.data.shape == (100, 100)
        assert result.provenance.startswith("legacy_survey:")

    def test_skyview_is_available_reports_ok(self):
        ok, msg = SkyViewBackend().is_available()
        assert ok, msg

    def test_legacy_survey_is_available_reports_ok(self):
        ok, msg = LegacySurveyBackend().is_available()
        assert ok, msg
