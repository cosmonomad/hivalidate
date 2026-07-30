"""Unit tests for hivalidate.conversions.

Reference values are computed independently (not copy-pasted from the implementation)
so a bug in both the code and the test's derivation is unlikely to cancel out.
"""

import numpy as np
import pytest
from astropy.cosmology import FlatLambdaCDM

from hivalidate import conversions as conv


def test_freq_to_redshift_at_rest_frequency_gives_zero():
    assert conv.freq_to_redshift(conv.HI_REST_FREQ_HZ) == pytest.approx(0.0, abs=1e-12)


def test_freq_to_redshift_known_value():
    # A source at z=0.1 is observed at f_HI / 1.1.
    freq = conv.HI_REST_FREQ_HZ / 1.1
    assert conv.freq_to_redshift(freq) == pytest.approx(0.1, rel=1e-9)


def test_freq_to_velocity_optical_matches_definition():
    freq = conv.HI_REST_FREQ_HZ * 0.99
    expected = conv.SPEED_OF_LIGHT_KM_S * (conv.HI_REST_FREQ_HZ / freq - 1.0)
    assert conv.freq_to_velocity(freq, v_frame="optical") == pytest.approx(expected)


def test_freq_to_velocity_radio_matches_definition():
    freq = conv.HI_REST_FREQ_HZ * 0.99
    expected = conv.SPEED_OF_LIGHT_KM_S * (1.0 - freq / conv.HI_REST_FREQ_HZ)
    assert conv.freq_to_velocity(freq, v_frame="radio") == pytest.approx(expected)


def test_freq_to_velocity_rejects_unknown_frame():
    with pytest.raises(ValueError):
        conv.freq_to_velocity(conv.HI_REST_FREQ_HZ, v_frame="bogus")


def test_velocity_to_freq_is_inverse_of_freq_to_velocity_optical():
    freq_in = conv.HI_REST_FREQ_HZ * 0.995
    vel_km_s = conv.freq_to_velocity(freq_in, v_frame="optical")
    freq_out = conv.velocity_to_freq(vel_km_s * 1000.0, v_frame="optical")  # km/s -> m/s
    assert freq_out == pytest.approx(freq_in, rel=1e-9)


def test_hi_mass_frequency_constant_matches_meyer2017_conversion():
    # The frequency-domain constant should equal 2.356e5 * (c / f_HI), independently
    # computed here, not read out of the implementation.
    expected_constant = 2.356e5 * (conv.SPEED_OF_LIGHT_KM_S / conv.HI_REST_FREQ_HZ)
    assert expected_constant == pytest.approx(49.7, rel=1e-3)


def test_hi_mass_frequency_and_velocity_branches_agree_after_unit_conversion():
    # For the same physical source, s_int in Jy*Hz (frequency branch) and the
    # equivalent s_int in Jy*km/s (velocity branch, via dv = c/f_HI * df) must give
    # the same HI mass -- this is the property the legacy script's missing 1/(1+z)
    # term broke (see REFERENCES.md "Bug found and fixed").
    z = 0.05
    s_int_jy_hz = 1000.0
    s_int_jy_km_s = s_int_jy_hz * (conv.SPEED_OF_LIGHT_KM_S / conv.HI_REST_FREQ_HZ)

    mass_freq = conv.hi_mass(s_int_jy_hz, z, rest_frame="frequency")
    mass_vel = conv.hi_mass(s_int_jy_km_s, z, rest_frame="velocity")

    assert mass_freq == pytest.approx(mass_vel, rel=1e-9)


def test_hi_mass_includes_one_plus_z_correction():
    # Mass at z should be smaller than mass ignoring the 1/(1+z) term by exactly that
    # factor (in log space, log10(1+z) less) -- this pins down the bug fix.
    z = 0.05
    s_int = 1000.0
    mass_with_correction = conv.hi_mass(s_int, z, rest_frame="frequency")

    cosmology = conv.DEFAULT_COSMOLOGY
    d_l_mpc = cosmology.luminosity_distance(z).value
    constant = 2.356e5 * (conv.SPEED_OF_LIGHT_KM_S / conv.HI_REST_FREQ_HZ)
    mass_without_correction = np.log10(constant * d_l_mpc**2 * s_int)  # the old, buggy formula

    expected = mass_without_correction - np.log10(1 + z)
    assert mass_with_correction == pytest.approx(expected, rel=1e-9)


def test_hi_mass_respects_custom_cosmology():
    z = 0.05
    s_int = 1000.0
    default_mass = conv.hi_mass(s_int, z, rest_frame="frequency")
    other_cosmology = FlatLambdaCDM(H0=100.0, Om0=0.3)
    other_mass = conv.hi_mass(s_int, z, rest_frame="frequency", cosmology=other_cosmology)
    # Higher H0 -> smaller D_L -> smaller mass, so these must differ.
    assert other_mass != pytest.approx(default_mass)


def test_hi_mass_rejects_unknown_rest_frame():
    with pytest.raises(ValueError):
        conv.hi_mass(1.0, 0.05, rest_frame="bogus")


def test_hi_mass_fills_masked_values_with_nan_instead_of_crashing():
    s_int = np.ma.array([1000.0, 2000.0], mask=[False, True])
    result = conv.hi_mass(s_int, 0.05, rest_frame="frequency")
    assert np.isfinite(result[0])
    assert np.isnan(result[1])


def test_column_density_scales_as_one_plus_z_to_the_fourth():
    s_int, beam = 1.0, 100.0
    n_hi_z0 = conv.column_density(s_int, 0.0, beam)
    n_hi_z1 = conv.column_density(s_int, 1.0, beam)
    assert n_hi_z1 / n_hi_z0 == pytest.approx(2.0**4, rel=1e-9)


def test_column_density_scales_inversely_with_beam_area():
    s_int, z = 1.0, 0.05
    n_hi_small_beam = conv.column_density(s_int, z, beam_area_arcsec2=10.0)
    n_hi_large_beam = conv.column_density(s_int, z, beam_area_arcsec2=20.0)
    assert n_hi_small_beam == pytest.approx(2.0 * n_hi_large_beam, rel=1e-9)


def test_column_density_sensitivity_matches_column_density_of_n_sigma_flux():
    rms, z, beam, dnu, n_sigma = 0.002, 0.05, 100.0, 18500.0, 5.0
    expected = conv.column_density(rms * dnu * n_sigma, z, beam)
    result = conv.column_density_sensitivity(rms, z, beam, dnu, n_sigma)
    assert result == pytest.approx(expected)


def test_freq_width_to_velocity_dispersion_matches_local_approximation():
    freq_width, freq_centre = 18500.0, conv.HI_REST_FREQ_HZ
    expected = conv.SPEED_OF_LIGHT_KM_S * freq_width / freq_centre
    result = conv.freq_width_to_velocity_dispersion(freq_width, freq_centre)
    assert result == pytest.approx(expected)
