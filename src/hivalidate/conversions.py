"""Physical conversions for HI spectral-line data.

Every non-trivial constant or equation here is cited by short key (e.g. ``[Meyer2017]``)
against an entry in ``REFERENCES.md`` at the repository root -- look there for the full
citation, and for two things worth reading before trusting these numbers in a paper:
a bug found and fixed in the HI mass formula during this refactor, and a column-density
constant that was carried over from the legacy script without independent verification.

All functions are pure (no I/O, no global state) so they can be unit tested directly
against known values.
"""

from __future__ import annotations

import numpy as np
from astropy.cosmology import Cosmology, FlatLambdaCDM

#: Rest frequency of the HI 21cm hyperfine transition, in Hz.
HI_REST_FREQ_HZ = 1_420_405_751.786

#: Speed of light, in km/s (astropy has this too, but keeping it explicit here keeps
#: these functions dependency-free and easy to unit test in isolation).
SPEED_OF_LIGHT_KM_S = 299_792.458

#: Default cosmology used throughout the legacy pipeline (H0=70, flat LCDM, Om0=0.3).
#: Not from a specific paper -- a common round-number choice for HI survey work.
#: Pass a different `astropy.cosmology.Cosmology` to any function below to override it.
DEFAULT_COSMOLOGY = FlatLambdaCDM(H0=70.0, Om0=0.3, Tcmb0=2.725)


def freq_to_redshift(freq_hz: np.ndarray | float) -> np.ndarray | float:
    """Convert observed frequency to redshift for the HI 21cm line.

    z = f_HI / f_obs - 1

    The definitional relation between redshift and rest/observed frequency -- not
    survey- or paper-specific, so not separately cited in REFERENCES.md beyond the
    HI_REST_FREQ_HZ value itself (a standard physical constant).
    """
    return HI_REST_FREQ_HZ / freq_hz - 1.0


def freq_to_velocity(freq_hz: np.ndarray | float, v_frame: str = "optical") -> np.ndarray | float:
    """Convert observed frequency to line-of-sight velocity.

    Standard optical and radio velocity conventions (see REFERENCES.md, radio/optical
    velocity convention entry):

    - optical: v = c (f_HI / f_obs - 1)
    - radio:   v = c (1 - f_obs / f_HI)

    The two conventions agree at low velocity/redshift and diverge as v -> c; HI survey
    catalogues (including SoFiA's) conventionally quote optical velocities, which is
    also this function's default.
    """
    if v_frame == "optical":
        return SPEED_OF_LIGHT_KM_S * (HI_REST_FREQ_HZ / freq_hz - 1.0)
    elif v_frame == "radio":
        return SPEED_OF_LIGHT_KM_S * (1.0 - freq_hz / HI_REST_FREQ_HZ)
    raise ValueError(f"Unsupported velocity frame: {v_frame!r} (use 'optical' or 'radio')")


def velocity_to_freq(vel_m_s: np.ndarray | float, v_frame: str = "optical") -> np.ndarray | float:
    """Convert line-of-sight velocity (in m/s) to observed frequency. Inverse of
    `freq_to_velocity` (see REFERENCES.md, radio/optical velocity convention entry,
    for the underlying relation), but note the input unit is m/s here (matching the
    legacy script) while `freq_to_velocity` returns km/s -- callers must convert
    explicitly.
    """
    c_m_s = SPEED_OF_LIGHT_KM_S * 1000.0
    if v_frame == "optical":
        return HI_REST_FREQ_HZ / (vel_m_s / c_m_s + 1.0)
    elif v_frame == "radio":
        return HI_REST_FREQ_HZ * (1.0 - vel_m_s / c_m_s)
    raise ValueError(f"Unsupported velocity frame: {v_frame!r} (use 'optical' or 'radio')")


def freq_width_to_velocity_dispersion(
    freq_width_hz: np.ndarray | float, freq_centre_hz: np.ndarray | float
) -> np.ndarray | float:
    """Convert a frequency width (e.g. SoFiA's w20/w50/wm50 linewidths) to a velocity
    width, using the local (non-relativistic) approximation dv = c * df / f0 -- the
    same radio/optical convention as `freq_to_velocity` (REFERENCES.md), applied to a
    width instead of an absolute frequency. Adequate at DINGO/WALLABY-pilot redshifts
    (z << 1); would need a relativistic treatment to be accurate at cosmological
    distances.
    """
    return SPEED_OF_LIGHT_KM_S * freq_width_hz / freq_centre_hz


def hi_mass(
    s_int: np.ndarray | float,
    z: np.ndarray | float,
    rest_frame: str = "frequency",
    cosmology: Cosmology = DEFAULT_COSMOLOGY,
) -> np.ndarray | float:
    """Integrated HI flux -> log10(HI mass / Msun), following [Meyer2017]:

        M_HI / Msun = (2.356e5 / (1+z)) * (D_L / Mpc)^2 * (S / Jy km/s)

    Parameters
    ----------
    s_int : integrated HI flux. Units depend on `rest_frame`:
        - "velocity": Jy km/s (S directly, as in [Meyer2017])
        - "frequency": Jy Hz (SoFiA's `f_sum` catalogue column; see note below)
    z : redshift
    rest_frame : "frequency" (SoFiA's native units, the default) or "velocity"
    cosmology : `astropy.cosmology.Cosmology` used for the luminosity distance;
        defaults to `DEFAULT_COSMOLOGY`.

    Returns
    -------
    log10(HI mass / Msun)

    Notes
    -----
    The "frequency" branch converts Jy Hz to the Jy km/s convention of [Meyer2017]
    using the local approximation dv = (c / f_HI) df, which multiplies the mass
    constant by c / f_HI = 49.7 / 2.356e5 -- i.e. the constant below is exactly
    2.356e5 * (c / f_HI), not a separately-derived number.

    Bug fixed vs. the legacy script (see REFERENCES.md, "Bug found and fixed"): the
    original `himass()`'s frequency-rest-frame branch omitted the `1/(1+z)` term that
    [Meyer2017] applies and that the script's own (otherwise unused) velocity-rest-frame
    branch included. This function applies it in both branches.
    """
    d_l_mpc = cosmology.luminosity_distance(z).value
    if rest_frame == "frequency":
        freq_domain_constant = 2.356e5 * (SPEED_OF_LIGHT_KM_S / HI_REST_FREQ_HZ)  # ~= 49.7
        mass = freq_domain_constant / (1.0 + z) * d_l_mpc**2 * s_int
    elif rest_frame == "velocity":
        mass = 2.356e5 / (1.0 + z) * d_l_mpc**2 * s_int
    else:
        raise ValueError(f"Unsupported rest_frame: {rest_frame!r} (use 'frequency' or 'velocity')")

    if hasattr(mass, "filled"):
        mass = mass.filled(np.nan)  # masked-array flux values -> NaN mass, not a crash
    return np.log10(mass)


def column_density(
    s_int: np.ndarray | float, z: np.ndarray | float, beam_area_arcsec2: np.ndarray | float
) -> np.ndarray | float:
    """Observer-frame integrated flux (per moment-0 pixel) -> HI column density.

        N_HI = 2.33e20 * (1+z)^4 * S / beam_area

    See REFERENCES.md ("Known caveat") before treating this as science-final: the
    functional form (flux over beam area, with (1+z)^4 cosmological surface-brightness
    dimming) is consistent with the fundamental relation in [Walter2008] and with
    WALLABY-style column-density sensitivity limits, but the exact numeric constant
    was carried over from the legacy script without an independent re-derivation for
    this pipeline's specific flux/beam unit convention.
    """
    return 2.33e20 * (1.0 + z) ** 4 * s_int / beam_area_arcsec2


def column_density_sensitivity(
    rms_noise: np.ndarray | float,
    z: np.ndarray | float,
    beam_area_arcsec2: np.ndarray | float,
    freq_width_hz: np.ndarray | float,
    n_sigma: float,
) -> np.ndarray | float:
    """N-sigma column-density detection limit for a given per-channel RMS noise,
    by plugging the N-sigma flux limit (rms * channel width * N) into `column_density`
    -- see that function's docstring and REFERENCES.md's "Known caveat" entry for the
    citation and the caveat on the underlying constant.
    """
    s_limit = rms_noise * freq_width_hz * n_sigma
    return column_density(s_limit, z, beam_area_arcsec2)
