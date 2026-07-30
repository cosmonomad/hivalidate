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

## Physical conversions (filled in during Phase 1 -- conversions.py)

- **[HImass]** TBD -- verify against literature before finalizing; see
  `src/hivalidate/conversions.py` docstrings for the equation as implemented.
- **[ColumnDensity]** TBD -- verify against literature before finalizing; see
  `src/hivalidate/conversions.py` docstrings for the equation as implemented.
