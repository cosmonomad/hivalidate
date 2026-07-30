"""Tests for the continuum cutout backends.

`LocalContinuumBackend` is tested here against a small synthetic FITS mosaic built at
test time (fast, CI-safe, no dependency on the real ~50MB `data/continuum_image/`
file, which isn't in git). It was *also* run live against the real file and real
source positions from `data/run_sofia/` during development -- see the Phase 2 commit
message for the exact commands and output; that's what grounds the WCS/units/error
handling below, not just what the synthetic fixture happens to exercise.

`RacsCasdaBackend` cannot be tested live (no CASDA/OPAL credentials in this
environment) -- see README.md "CASDA / RACS access" for how to verify it yourself.
The tests here mock `astroquery.casda.Casda` to check our own orchestration logic
(login/keyring handling, RACS filtering, cutout/download flow) against the exact
API shape documented at
https://astroquery.readthedocs.io/en/latest/casda/casda.html -- they cannot catch a
real API or auth failure, only a regression in how we call it.
"""

from __future__ import annotations

import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

from hivalidate.cutouts import continuum as continuum_module
from hivalidate.cutouts.base import CutoutUnavailable
from hivalidate.cutouts.continuum import LocalContinuumBackend, RacsCasdaBackend

# Matches the real data/continuum_image mosaic's WCS convention (RA---SIN/DEC--SIN),
# just much smaller: 400x400 px at the same ~2 arcsec/pix scale (real file: 11406x11543).
FIELD_CENTRE = SkyCoord(ra=315.4611, dec=-55.8032, unit="deg")
PIXSCALE_DEG = 0.0005555537726647


@pytest.fixture
def local_continuum_dir(tmp_path):
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
    wcs.wcs.crval = [FIELD_CENTRE.ra.deg, FIELD_CENTRE.dec.deg]
    wcs.wcs.crpix = [200, 200]
    wcs.wcs.cdelt = [-PIXSCALE_DEG, PIXSCALE_DEG]

    data = np.random.default_rng(0).normal(0, 1e-4, size=(400, 400)).astype(np.float32)
    header = wcs.to_header()
    fits.writeto(tmp_path / "mini_continuum.fits", data, header, overwrite=True)
    return tmp_path


class TestLocalContinuumBackend:
    def test_resolves_the_single_fits_file(self, local_continuum_dir):
        backend = LocalContinuumBackend(local_continuum_dir)
        assert backend._resolve_file().name == "mini_continuum.fits"

    def test_raises_clearly_if_zero_or_multiple_fits_files(self, tmp_path):
        backend = LocalContinuumBackend(tmp_path)  # empty dir
        with pytest.raises(CutoutUnavailable, match="found 0"):
            backend._resolve_file()

        (tmp_path / "a.fits").touch()
        (tmp_path / "b.fits").touch()
        backend2 = LocalContinuumBackend(tmp_path)
        with pytest.raises(CutoutUnavailable, match="found 2"):
            backend2._resolve_file()

    def test_check_coverage_true_at_field_centre_false_far_away(self, local_continuum_dir):
        backend = LocalContinuumBackend(local_continuum_dir)
        assert backend.check_coverage(FIELD_CENTRE) is True
        far_away = SkyCoord(ra=10.0, dec=10.0, unit="deg")
        assert backend.check_coverage(far_away) is False

    def test_fetch_returns_correctly_sized_cutout_with_wcs(self, local_continuum_dir):
        backend = LocalContinuumBackend(local_continuum_dir)
        size_arcsec = 20 * 3600 * PIXSCALE_DEG  # ~20 pixels across
        result = backend.fetch(FIELD_CENTRE, size_arcsec)
        assert result.data.ndim == 2
        assert 15 <= result.data.shape[0] <= 25  # mSubimage's own rounding, not exact
        assert result.provenance == "local:mini_continuum.fits"
        # WCS round-trips a real sky position back near the field centre.
        ra, dec = result.wcs.celestial.wcs_pix2world(
            [[result.data.shape[1] / 2, result.data.shape[0] / 2]], 0
        )[0]
        assert ra == pytest.approx(FIELD_CENTRE.ra.deg, abs=0.01)
        assert dec == pytest.approx(FIELD_CENTRE.dec.deg, abs=0.01)

    def test_fetch_outside_footprint_raises_cutout_unavailable(self, local_continuum_dir):
        backend = LocalContinuumBackend(local_continuum_dir)
        far_away = SkyCoord(ra=10.0, dec=10.0, unit="deg")
        with pytest.raises(CutoutUnavailable, match="outside image|mSubimage"):
            backend.fetch(far_away, size_arcsec=30.0)

    def test_is_available_true_for_valid_dir_false_for_empty(self, local_continuum_dir, tmp_path):
        assert LocalContinuumBackend(local_continuum_dir).is_available() == (True, "OK")
        ok, msg = LocalContinuumBackend(tmp_path / "nonexistent").is_available()
        assert not ok


# ---------------------------------------------------------------------------
# RacsCasdaBackend: mocked -- see module docstring.
# ---------------------------------------------------------------------------


class FakeCasdaInstance:
    def __init__(self, login_result=True, cutout_urls=None, download_files=None):
        self._login_result = login_result
        self._cutout_urls = cutout_urls or ["http://example.test/cutout.fits"]
        self._download_files_result = download_files
        self.login_calls = []
        self.cutout_calls = []

    def login(self, *, username):
        self.login_calls.append(username)
        return self._login_result

    def cutout(self, table, *, coordinates, height, width):
        self.cutout_calls.append((table, coordinates, height, width))
        return self._cutout_urls

    def download_files(self, urls, *, savedir):
        if self._download_files_result is not None:
            return self._download_files_result
        # Write a minimal real FITS so the caller's fits.open succeeds.
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
        path = f"{savedir}/racs_cutout.fits"
        fits.writeto(path, np.ones((10, 10)), wcs.to_header(), overwrite=True)
        return [path]


def _fake_racs_table(n_rows=1, obs_collection="The Rapid ASKAP Continuum Survey"):
    return Table(
        {
            "obs_collection": [obs_collection] * n_rows,
            "filename": ["RACS-DR1_0000+00A.fits"] * n_rows,
        }
    )


@pytest.fixture
def fake_casda_class(monkeypatch):
    """Replaces the `Casda` class used inside cutouts/continuum.py with a stand-in
    exposing the same shape (classmethod-style `query_region`/`filter_out_unreleased`,
    instance `login`/`cutout`/`download_files`) but no network calls.
    """

    class FakeCasdaClass:
        query_region_result = _fake_racs_table()
        instances: list[FakeCasdaInstance] = []
        login_result = True

        def __new__(cls):
            instance = FakeCasdaInstance(login_result=cls.login_result)
            cls.instances.append(instance)
            return instance

        @staticmethod
        def query_region(position, radius=None):
            return FakeCasdaClass.query_region_result

        @staticmethod
        def filter_out_unreleased(table):
            return table

    monkeypatch.setattr(continuum_module, "Casda", FakeCasdaClass)
    return FakeCasdaClass


class TestRacsCasdaBackendLoginMocked:
    def test_missing_username_env_raises_clear_error(self, monkeypatch, fake_casda_class):
        monkeypatch.delenv("CASDA_USERNAME", raising=False)
        backend = RacsCasdaBackend()
        with pytest.raises(CutoutUnavailable, match="CASDA_USERNAME"):
            backend._ensure_login()

    def test_password_env_seeds_keyring_before_login(self, monkeypatch, fake_casda_class):
        monkeypatch.setenv("CASDA_USERNAME", "someone@example.org")
        monkeypatch.setenv("CASDA_PASSWORD", "hunter2")
        seeded = {}
        monkeypatch.setattr(
            continuum_module.keyring,
            "set_password",
            lambda service, username, password: seeded.update(
                service=service, username=username, password=password
            ),
        )
        backend = RacsCasdaBackend()
        backend._ensure_login()
        assert seeded == {
            "service": continuum_module._CASDA_KEYRING_SERVICE,
            "username": "someone@example.org",
            "password": "hunter2",
        }

    def test_no_keyring_backend_raises_actionable_error(self, monkeypatch, fake_casda_class):
        monkeypatch.setenv("CASDA_USERNAME", "someone@example.org")
        monkeypatch.setenv("CASDA_PASSWORD", "hunter2")

        def raise_no_keyring(*a, **kw):
            raise continuum_module.keyring.errors.NoKeyringError("no backend")

        monkeypatch.setattr(continuum_module.keyring, "set_password", raise_no_keyring)
        backend = RacsCasdaBackend()
        with pytest.raises(CutoutUnavailable, match="keyring"):
            backend._ensure_login()

    def test_failed_login_raises_cutout_unavailable(self, monkeypatch, fake_casda_class):
        monkeypatch.setenv("CASDA_USERNAME", "someone@example.org")
        monkeypatch.delenv("CASDA_PASSWORD", raising=False)
        fake_casda_class.login_result = False
        backend = RacsCasdaBackend()
        with pytest.raises(CutoutUnavailable, match="login failed"):
            backend._ensure_login()

    def test_login_is_cached_after_first_success(self, monkeypatch, fake_casda_class):
        monkeypatch.setenv("CASDA_USERNAME", "someone@example.org")
        monkeypatch.delenv("CASDA_PASSWORD", raising=False)
        backend = RacsCasdaBackend()
        backend._ensure_login()
        backend._ensure_login()
        assert len(fake_casda_class.instances) == 1  # only constructed once


class TestRacsCasdaBackendFetchMocked:
    def test_filters_to_racs_obs_collection_and_filename_pattern(
        self, monkeypatch, fake_casda_class
    ):
        monkeypatch.setenv("CASDA_USERNAME", "someone@example.org")
        monkeypatch.delenv("CASDA_PASSWORD", raising=False)
        # Mix of a matching RACS row and a non-matching row from some other survey.
        fake_casda_class.query_region_result = Table(
            {
                "obs_collection": ["The Rapid ASKAP Continuum Survey", "Some Other Survey"],
                "filename": ["RACS-DR1_0000+00A.fits", "other_0000+00.fits"],
            }
        )
        backend = RacsCasdaBackend()
        result = backend.fetch(FIELD_CENTRE, size_arcsec=60.0)
        assert result.provenance == "racs_casda:RACS-DR1_0000+00A.fits"

    def test_no_matching_racs_image_raises_cutout_unavailable(self, monkeypatch, fake_casda_class):
        monkeypatch.setenv("CASDA_USERNAME", "someone@example.org")
        monkeypatch.delenv("CASDA_PASSWORD", raising=False)
        fake_casda_class.query_region_result = _fake_racs_table(obs_collection="Some Other Survey")
        backend = RacsCasdaBackend()
        with pytest.raises(CutoutUnavailable, match="No RACS image"):
            backend.fetch(FIELD_CENTRE, size_arcsec=60.0)

    def test_check_coverage_respects_declination_limit(self):
        backend = RacsCasdaBackend()
        assert backend.check_coverage(FIELD_CENTRE)  # dec ~ -55.8, well within RACS
        far_north = SkyCoord(ra=180.0, dec=60.0, unit="deg")
        assert not backend.check_coverage(far_north)
