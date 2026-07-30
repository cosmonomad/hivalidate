# References

Bibliography for the science and external services encoded in `hivalidate`. Code
comments and docstrings cite entries here by their short key (e.g. `[SoFiA2]`) instead
of repeating full citations inline. Add an entry here whenever you add a citation to
the code; keep keys stable once used since they're referenced from multiple files.

Entries below marked with the exact formula/constant they support were verified
against the source during Phase 1 implementation, not assumed from the pre-existing
scripts being migrated.

## Source finding

- **[SoFiA2]** Westmeier, T., Kitaeff, S., Pallot, D., et al. 2021, "SoFiA 2 -- an
  automated, parallel HI source finding pipeline for the WALLABY survey", ASCL /
  MNRAS. Software: https://github.com/SoFiA-Admin/SoFiA-2

## Surveys used for cutouts / cross-matching

- **[GAMA]** Driver, S. P., et al. 2011, "Galaxy and Mass Assembly (GAMA): survey
  diagnostics and core data release", MNRAS, 413, 971.
- **[DSS2]** STScI Digitized Sky Survey II, accessed via `astroquery.skyview`.
- **[LegacySurvey]** Dey, A., et al. 2019, "Overview of the DESI Legacy Imaging
  Surveys", AJ, 157, 168. Cutout service: https://www.legacysurvey.org/
- **[RACS]** McConnell, D., et al. 2020, "The Rapid ASKAP Continuum Survey I:
  Design and first results", PASA, 37, e048.
- **[CASDA]** CSIRO ASKAP Science Data Archive, accessed via `astroquery.casda`
  (requires an OPAL account): https://astroquery.readthedocs.io/en/latest/casda/casda.html

## Physical conversions

- **[Meyer2017]** Meyer, M. J., Robotham, A. S. G., Obreschkow, D., et al. 2017,
  "Tracing HI Beyond the Local Universe", PASA, 34, e052 (arXiv:1705.04210). Source
  of the HI mass relation
  `M_HI/Msun = (2.356e5 / (1+z)) * (D_L/Mpc)^2 * (S / Jy km/s)`,
  verified by web search against the published equation on 2026-07-30. Used in
  `conversions.hi_mass()`.
- **[Walter2008]** Walter, F., Brinks, E., de Blok, W. J. G., et al. 2008, "THINGS:
  The HI Nearby Galaxy Survey", AJ, 136, 2563. Source of the fundamental optically-thin
  21cm column-density relation `N_HI [cm^-2] = 1.823e18 * integral(T_B dv [K km/s])`,
  the physical basis for `conversions.column_density()`.
- **Radio/optical velocity convention**: standard definitions
  `v_opt = c(f0/f - 1)`, `v_radio = c(1 - f/f0)`; see e.g. Rohlfs & Wilson, *Tools of
  Radio Astronomy* (Springer), section on spectral line kinematics. Textbook-standard,
  not independently re-verified by literature search.

### Known caveat -- flag before treating column density as science-final

`conversions.column_density()` implements `N_HI = 2.33e20 * (1+z)^4 * S / beam`,
carried over unchanged from the pre-refactor script (`legacy/validate_detections.py`).
This has the correct *functional form* for converting an observer-frame, per-pixel
moment-0 flux (in Jy/beam Hz, appropriate for SoFiA's frequency-axis moment maps) to a
column density with cosmological surface-brightness dimming -- consistent with the
column-density-sensitivity relations quoted in WALLABY survey papers built on
[Meyer2017]-style pipelines. However, the exact numeric constant `2.33e20` was **not**
independently re-derived bit-for-bit against a specific published equation during this
refactor (unlike the HI mass constant, which was checked and corrected -- see below).
Treat it as inherited-and-plausible, not verified, until someone re-derives it from
first principles for this pipeline's specific beam/flux unit convention.

### Bug found and fixed during this refactor

The pre-refactor script's frequency-rest-frame HI mass branch (`himass(..., rest_frame='frequency')`,
the only branch actually used in practice) was missing the `1/(1+z)` cosmological
correction present in [Meyer2017] and in the script's own (unused) velocity-rest-frame
branch. Checked numerically: `2.356e5 * (c / f_HI)` = 49.7, confirming the frequency-domain
constant `49.7` is [Meyer2017]'s formula re-expressed for `S` in Jy Hz rather than
Jy km/s -- but the `1/(1+z)` term should still apply and didn't. `conversions.hi_mass()`
includes it. At DINGO/WALLABY-pilot redshifts (z ~ 0.01-0.1) this is roughly a 1-10%
effect on every reported HI mass in the legacy pipeline's output catalogues.
