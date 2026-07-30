# HI Source-Finding Validation Pipeline — Implementation Plan

Status: **v0.1 complete (2026-07-30)** — all seven phases below done, definition of
done (section 9) fully satisfied. This document captures everything decided during
planning and every bug found/fixed during implementation; it remains the source of
truth for design rationale even though active build-out is finished. Update it if
that changes (new phases, a v0.2 scope, etc.).

## 1. Goal

Turn the current collection of ad hoc, hardcoded scripts (`validate_detections.py`,
`plot_detections.py`, `remove_duplicate.py`, `rename_cubelets.py`, `run_all_renames.sh`,
`create_validation_csv.py`, `extract_true_cubelets.py`, `mosaic_sofia_true_detections.py`,
`download_legacy.py`) into a documented, tested, version-controlled Python pipeline for
validating SoFiA HI source-finding output, runnable end-to-end on the example data in
`run_sofia/` and reusable across future survey fields/SBs without hand-editing constants.

## 2. What already exists (ground truth for design + testing)

- `run_sofia/` — 45 independent SoFiA runs (`SB82605_Removal_001` … `_045`), each with its
  own catalogue (`.xml`/`.txt`/`.sql`), moment maps, and a `_cubelets/` dir of per-source
  products. 715 catalogue rows, ~656 unique source names, 14 cross-run name collisions.
  2.4 GB total. **This is the primary integration-test dataset.**
- `data/continuum_image/image.i.WALLABY_2051-53B.SB82605.cont.taylor.0.restored.conv.fits`
  — real local continuum mosaic for this field/SB. Resolves the previous hardcoded
  wrong-SB continuum path in `validate_detections.py`.
- `data/output_validation_true/` — 159 example six-panel validation PNGs for confirmed
  true detections. Reference for expected plot layout and a candidate regression set.
- `MontagePy` — pip-installable, prebuilt wheels, already in the `base` conda env. Keep
  it for continuum cutout extraction (`mSubimage`); no need to replace with
  `reproject`/`Cutout2D`.

## 3. Known issues in the current scripts to fix along the way

| # | Issue | Where | Fix in phase |
|---|---|---|---|
| 1 | `run_all_renames.sh` globs `SB82605_jolly_*_cat.xml` but raw SoFiA output is named `SB82605_Removal_*_cat.xml` — zero matches as shipped | `run_all_renames.sh` | 1 |
| 2 | Hardcoded paths (`cont_file`, `dir_cubelets`, `dir_gamacat`, `sofia_file`, `outname`) from a different survey/SB (`WALLABY/SB51535`) baked in as module constants | `validate_detections.py` | 1 |
| 3 | `matplotlib.use('Agg')` (non-interactive) combined with `plt.show()` + blocking `input()` in the QA loop — can't actually see the plot when `do_validation=True` | `validate_detections.py` | 3/4 — resolved by decoupling dry-run (always `Agg`, HPC-safe) from QA (interactive, reviews saved PNGs only) |
| 4 | `copy_data()` writes into `save_dir/true/…` (nested) but `create_validation_csv.py` expects a flat `output_validation_true/` directory | `validate_detections.py`, `create_validation_csv.py` | 5 |
| 5 | Deduplication is exact-string match on the SoFiA-generated name, which only catches collisions where derived coordinates rounded identically — misses near-duplicates with slightly different centroids across adjacent runs | `remove_duplicate.py` | 1 |
| 6 | SoFiA `id` resets to 1..N per run; nothing today merges catalogues on `id`, but this must stay an explicit rule, not an accident, once merging code exists | `rename_cubelets.py` | 1 |
| 7 | No incremental persistence of QA flags — a crash mid-loop loses all review progress for the session | `validate_detections.py` | 4 |
| 8 | No per-source fault isolation — one bad cutout/network error aborts the whole batch | `validate_detections.py` | 2, 4 |
| 9 | No config/CLI — every script hardcodes paths as module-level constants, requiring manual edits per field/SB | all scripts | 1 |

## 4. Target repository structure

```
validate_source_finding/
├── README.md                    # what this is, how to run it, links to docs/
├── REFERENCES.md                # bibliography, short-key citations (e.g. [SoFiA2], [Meyer17])
├── LICENSE
├── pyproject.toml               # package metadata + dependencies
├── environment.yml              # conda env (incl. MontagePy) as alternative to pip
├── .gitignore                   # FITS/PNG outputs, cutout cache, run_sofia data itself
├── .pre-commit-config.yaml      # ruff/black hooks
├── .github/workflows/ci.yml     # lint + fixture tests on push
├── configs/
│   └── SB82605.yaml             # example per-field/SB config (paths, survey priority)
├── src/
│   └── hivalidate/              # confirmed package name
│       ├── __init__.py
│       ├── config.py            # load & validate field/SB YAML config
│       ├── conversions.py       # freq<->z<->vel, HI mass, column density (heavily cited)
│       ├── catalogue.py         # VOTable I/O, multi-run combine, positional dedup, id->name mapping
│       ├── crossmatch.py        # GAMA crossmatch + self-crossmatch dedup (shared logic)
│       ├── cutouts/
│       │   ├── __init__.py
│       │   ├── base.py          # fallback-chain abstraction + on-disk cache + retry/backoff
│       │   ├── optical.py       # SkyView backend, Legacy Survey backend
│       │   └── continuum.py     # local-file (MontagePy) backend, RACS/CASDA backend
│       ├── plotting.py          # six-panel figure builder; dry-run vs interactive modes
│       ├── qa.py                # interactive review loop, resumable, incremental save
│       ├── postprocess.py       # validation CSV, extract-true-cubelets, mosaic true detections
│       └── cli/                 # one thin entry point per pipeline stage
│           ├── combine.py
│           ├── dedup.py
│           ├── rename.py
│           ├── dry_run.py
│           ├── validate.py
│           └── postprocess.py
├── tests/
│   ├── fixtures/run_sofia_mini/ # 2-3 real Removal runs, copied in, small enough for CI
│   ├── test_conversions.py
│   ├── test_catalogue.py
│   ├── test_cutouts.py
│   └── test_pipeline_e2e.py     # runs the fixture through combine→dedup→rename→dry-run
├── docs/
│   └── pipeline_overview.md     # stage-by-stage narrative + data flow diagram
└── data/                        # gitignored: continuum_image/, output_validation_true/, cutout cache, credentials
    └── run_sofia/                # existing example data — primary integration-test dataset
```

Package name: `hivalidate` (confirmed).

## 5. Design decisions carried over from discussion

- **Language**: Python for all pipeline logic; bash only where it's genuinely simpler
  (e.g. a thin wrapper that loops the CLI over multiple fields), never for logic that
  needs testing.
- **Config over constants**: one YAML per field/SB, passed to every CLI stage — replaces
  the current hardcoded-constant-per-script pattern.
- **CLI framework**: `argparse`, one thin entry point per stage (`combine`, `dedup`,
  `rename`, `dry-run`, `qa`, `postprocess`) — consistent with the pattern
  `rename_cubelets.py` already uses.
- **Cutout fallback-chain abstraction**: `get_optical_cutout(pos, size, priority=[...])`
  and `get_continuum_cutout(pos, size, local_dir, fallback=...)`, each returning
  `(data, wcs, provenance)`. Optical priority: SkyView → Legacy Survey. Continuum:
  local file (MontagePy `mSubimage`) → RACS via `astroquery.casda` if no local file
  covers the field. Both panels in the validation plot call their own chain
  independently — same abstraction, separate figures.
- **CASDA authentication**: `astroquery.casda` requires an OPAL login
  (https://astroquery.readthedocs.io/en/latest/casda/casda.html). Pipeline code never
  interactively prompts for credentials — it reads them from environment variables
  (`CASDA_USERNAME`/`CASDA_PASSWORD`) or a local, gitignored credentials file
  referenced from the field config, so the continuum RACS fallback can run unattended
  in an HPC batch job. Document OPAL account setup in `README.md`. Confirmed: HPC
  compute nodes have outbound internet access, so the RACS fallback runs inline with
  dry-run — no separate network-enabled step needed.
- **Preflight connectivity check**: before a dry-run batch starts processing sources,
  the pipeline does a cheap upfront check of every network-dependent backend in the
  configured fallback chains — CASDA login + a trivial query, SkyView/Legacy Survey
  reachability — and fails fast with a clear diagnostic if any of them don't work.
  This catches a broken CASDA login or a network/proxy issue on a given HPC node
  before it silently degrades hundreds of sources to their fallback (or no) continuum
  image mid-batch, rather than discovering it after the job finishes.
- **Cutout caching**: on-disk cache keyed by `(source name, survey, size)` so dry-run
  and QA never re-fetch the same cutout.
- **Survey footprint pre-check**: verify RACS/Legacy Survey coverage for a position
  before querying, to fail fast/skip cleanly rather than get a blank image or timeout.
- **Provenance**: record which survey/backend was actually used for each source's
  optical and continuum image in the output catalogue.
- **Dry-run and QA are fully decoupled stages, not one interleaved loop.** This follows
  directly from needing to run on HPC, where there's no display and no interactive
  input. Dry-run always uses the `Agg` backend, writes one PNG per source plus a
  small per-source metadata manifest (paths, provenance, catalogue row), and never
  opens a display or blocks on input — it's the only stage that needs to work
  unattended on an HPC compute node. QA is a separate stage that reads the dry-run
  manifest and PNGs and never regenerates cutouts or figures, so it can run anywhere
  a display is available (e.g. your laptop, after syncing PNGs down from HPC),
  independent of where dry-run ran. This resolves the `Agg`/`plt.show()`/`input()`
  conflict (issue #3) by removing the assumption entirely rather than patching it.
- **Resumable, incrementally-saved QA**: write each flag to disk as it's made (not only
  at the end of the loop), so a session can be interrupted and resumed on the same or
  a different machine. Optional free-text comment field alongside the t/f/u/d flag; a
  "back" option to correct a mis-keyed flag without rerunning.
- **Positional/velocity dedup**: replace exact-name-string matching with a spatial +
  velocity cross-match (reusing the existing `search_gama`-style logic), scoped per
  merge operation, never keyed on SoFiA's per-run `id`.
- **Fault isolation**: each source processed in its own try/except in every batch loop
  (cutout fetch, plotting, QA); failures are logged and skipped, never abort the batch.
- **Reproducibility metadata**: every output catalogue gets the pipeline's git commit
  hash, the config used, and key package versions stamped in, alongside SoFiA's own
  version (already present).
- **Testing**: pytest, with a small fixture (2-3 real `Removal_*` runs) for fast
  unit/integration tests suitable for CI; the full 45-run `run_sofia/` set is reserved
  for a slower, manually-triggered full end-to-end validation pass, checked where
  possible against the 159 known-true examples in `data/output_validation_true/`.
- **Documentation**: docstrings throughout, with inline literature references for any
  coded science (HI mass conversion, column density, velocity/redshift conversions,
  etc.) pointing to short keys defined once in `REFERENCES.md`, not repeated inline.
- **Tooling**: ruff/black + pre-commit; a minimal GitHub Actions CI running lint +
  fixture tests on push.

## 6. Decisions (resolved 2026-07-30)

1. Package name: `hivalidate`.
2. CLI framework: `argparse`.
3. Config format: YAML.
4. `astroquery.casda` requires an OPAL login (confirmed:
   https://astroquery.readthedocs.io/en/latest/casda/casda.html) — handled
   non-interactively via env vars / gitignored credentials file, see §5.
5. `run_sofia/` moves under `data/run_sofia/`, alongside `continuum_image/` and
   `output_validation_true/`.
6. License: **BSD-3-Clause** (recommended) — matches the license used by `astropy`
   and most of the ecosystem this pipeline depends on (`astroquery`, `reproject`),
   permissive enough for other DINGO/WALLABY team members to reuse, and requires
   attribution without restricting reuse. MIT would be an equally reasonable simpler
   alternative if preferred — flag if you'd rather switch.

## 7. Explicit non-goals for v1

- Multi-user/crowdsourced QA with inter-rater agreement — not needed at current scale,
  revisit only if requested.
- Automated true/false pre-classification (e.g. ML or SNR/`rel`-threshold auto-accept)
  — flagged as a future idea, not part of this build.

## 8. Build sequence

### Phase 0 — Repo scaffolding [DONE 2026-07-30]
- [x] `git init`, `.gitignore` (incl. any local CASDA credentials file), `LICENSE`
      (BSD-3-Clause)
- [x] Directory structure as in §4, with `run_sofia/` moved to `data/run_sofia/`
- [x] `pyproject.toml` + `environment.yml` (pin dependencies incl. `MontagePy`,
      `astropy`, `astroquery`, `reproject`, `matplotlib`, `numpy`, `requests`) --
      MontagePy pinned to >=2.3 (the real PyPI version; the plan's placeholder >=6.0
      was wrong, caught when `pip install -e .` actually failed)
- [x] `.pre-commit-config.yaml` (ruff/black), `.github/workflows/ci.yml`
- [x] `README.md` skeleton (incl. OPAL/CASDA account setup instructions),
      `REFERENCES.md` skeleton
- [x] Extract a `run_sofia_mini` fixture into `tests/fixtures/` -- ended up as 5 real
      runs (001, 002, 003, 011, 012), not 2-3, specifically to include a known
      cross-run duplicate pair (011/012) for a true-positive dedup test
- Legacy scripts moved to `legacy/` (not deleted) for reference during migration.

### Phase 1 — Core science + catalogue layer [DONE 2026-07-30]
- [x] `config.py`: load/validate per-field YAML config
- [x] `conversions.py`: migrate freq/z/vel/mass/column-density functions from
      `validate_detections.py`, full docstrings + `REFERENCES.md` citations, unit tests
      -- **found and fixed a real bug**: the legacy frequency-rest-frame HI mass formula
      was missing [Meyer2017]'s `1/(1+z)` term (~1-10% effect at these redshifts)
- [x] `catalogue.py`: VOTable read, multi-run combine (replaces `plot_detections.py`'s
      combine step), positional dedup (replaces `remove_duplicate.py`), id→name mapping
      per run (replaces `rename_cubelets.py` logic) — fixes issues #1, #5, #6, #9
- [x] CLI: `combine`, `dedup`, `rename` stages runnable against `run_sofia/`
- [x] Tests against `run_sofia_mini` fixture (41 tests, all passing)
- **Ran for real against the full 45-run `data/run_sofia/`**: 670 raw detections ->
  222 removed as duplicates (33%) -> 448 unique sources, 5824 renamed cubelet files.
  Far more duplication than the legacy script's 14 exact-string matches -- verified
  this is real, not over-merging (accepted pairs: median 0.33″/0.4 km/s separation;
  correctly-rejected sky-close pairs: thousands of km/s apart in velocity).

### Phase 2 — Cutout layer [DONE 2026-07-30, fully verified live]
- [x] `cutouts/base.py`: fallback-chain abstraction, on-disk cache (FITS, keyed by
      source/backend/size), retry/backoff (generalized from the SkyView pattern)
- [x] `cutouts/optical.py`: `SkyViewBackend` (migrated), `LegacySurveyBackend`
      (migrated from `legacy/download_legacy.py`) — **both verified live**
      (`pytest -m network tests/test_cutouts_optical.py`). Real finding while doing
      so: `legacysurvey.org` returned a real 503 during testing (confirmed via
      `curl`, the whole site was down, not our bug) -- exposed that
      `LegacySurveyBackend` had no retry/backoff at all, unlike SkyView; added it.
- [x] `cutouts/continuum.py`: `LocalContinuumBackend` (MontagePy `mSubimage`) --
      **verified live** against the real `data/continuum_image/*.fits` and real
      source positions, including the out-of-footprint error path.
      `RacsCasdaBackend` (`astroquery.casda`) -- **verified live 2026-07-30** with a
      real OPAL account, after this environment's astroquery (0.4.11) turned out to
      have a real bug: `CasdaClass.login()` is an auto-generated wrapper that
      discards its own return value, so it always evaluates as `None`/falsy no
      matter what actually happened. `RacsCasdaBackend._ensure_login()` was
      originally written trusting that return value (matching the astroquery docs'
      own example) and consequently reported every successful login as a failure --
      caught only by testing against a real account, not by the mocked tests, which
      had unknowingly encoded the same wrong assumption. Fixed by checking
      `casda.authenticated()` instead, which reads the real internal state. Also
      found live: a real RACS cutout comes back with degenerate Stokes/frequency
      axes (shape `(1, 1, ny, nx)`, not the 2D shape every other backend returns) --
      `fetch()` now squeezes them, and raises clearly instead of silently
      mis-plotting if a future cutout genuinely has more than one such plane. Both
      fixes are covered by regression tests built from the real observed shapes/
      behaviour, not just the original guesses.
- [x] Preflight check: `hivalidate-check-connectivity`, run for real against
      `configs/SB82605.yaml` -- correctly reported SkyView OK, Legacy Survey FAILED
      (real live outage), local continuum OK, RACS/CASDA FAILED with an actionable
      "$CASDA_USERNAME is not set" message, and exited 1.
- [x] Footprint/coverage pre-checks: RACS/CASDA and Legacy Survey use a documented
      declination-limit heuristic (not a full footprint polygon -- flagged as an
      approximation in the code, `fetch()` is the real authority); local continuum
      uses the mosaic's actual WCS footprint (`WCS.footprint_contains`), which is
      exact, not a heuristic.
- [x] Provenance recording — every `CutoutResult` carries which backend supplied it.

### Phase 3 — Plotting (dry-run, the HPC-safe stage) [DONE 2026-07-30]
- [x] `plotting.py`: six-panel figure builder (`build_validation_figure`) extracted
      as a pure function (`Figure` in, data out -- no file I/O, no `plt.show()`).
      Verified live by rendering real sources to PNG and inspecting them, not just
      unit tests -- caught two real bugs the unit tests (built from the same wrong
      assumptions as the code) couldn't have: (1) `LocalContinuumBackend` was
      returning the raw 4D WCS instead of `.celestial`, which crashed WCSAxes
      plotting entirely; (2) the PV panel's FITS header needs its frequency axis
      rescaled Hz->MHz before building its WCS (a step in the legacy script's
      `get_pv_data` that got missed when porting) -- without it the panel rendered
      blank with a nonsensical multi-GHz axis instead of failing loudly. Both fixed,
      both covered by regression tests using the real bug conditions, not the
      original (wrong) assumptions. Two deliberate improvements over the legacy
      script: continuum display range from robust cutout statistics instead of a
      hardcoded vmin/vmax that only suited one field, and provenance annotated on
      the figure itself.
- [x] Dry-run CLI (`hivalidate-dry-run`): preflight check first (warns if some
      backends in a chain are down but others still work, aborts only if an entire
      chain is unusable), then batch-generates PNGs + `manifest.json` (per-source
      status/provenance/error, plus run-level git commit hash + version + config
      name for reproducibility).
- [x] Fault isolation per source (issue #8): one source's cutout/plot failure is
      logged and the batch continues -- verified with a real sabotaged cubelet file.
- **Ran for real** against 5 real sources from the full 448-source deduped catalogue
  (`data/work/SB82605/`), with real SkyView + real local continuum cutouts (Legacy
  Survey was still down from Phase 2's outage; the preflight correctly warned and
  the batch proceeded on SkyView alone). All 5 produced correct six-panel PNGs.

### Phase 4 — Interactive QA (runs locally, not on HPC) [DONE 2026-07-30, one part user-only-verifiable]
- [x] `qa.py`: review loop (`run_qa_session`) over the dry-run manifest/PNGs only --
      never regenerates cutouts or figures. `display_fn`/`prompt_fn`/`close_fn` are
      injected, so the state machine, incremental persistence, and catalogue merge
      are all fully unit-tested without a real display or keyboard; `default_display`
      deliberately does not call `matplotlib.use(...)` (unlike dry-run's forced
      `Agg`), since this is meant to run somewhere with an actual screen.
- [x] Resumable, incremental per-source save (fixes issue #7): every review is
      written to `qa_results.json` immediately, and a second session skips anything
      already in it without re-displaying. `b` (back) removes and re-presents the
      previous source; `q` saves and stops early. All three verified against real
      manifest/PNG data (not just the fixture), including a real back-correction.
- [x] Output catalogue (`validated_cat.xml`): numeric `qa` flag (legacy convention:
      0/1/2/3 = false/true/uncertain/duplicate), free-text `qa_comment`, optical/
      continuum provenance and dry-run status pulled from the manifest, `NaN`/empty
      for anything not yet reviewed (safe to inspect after a partial session).
      `run_info.json` alongside it carries the same reproducibility metadata as the
      dry-run manifest (git commit, version, config name, review counts).
- **What's verified vs. not**: the review *logic* (state machine, persistence,
  catalogue merge, `default_display`/`default_close` not crashing on a real PNG) was
  run for real against a real 5-source manifest from Phase 3 -- git commit hash,
  provenance, and all four flags round-tripped correctly into `validated_cat.xml`.
  The actual interactive experience (a real matplotlib window plus blocking
  terminal `input()`) can't be exercised by an automated tool the way SkyView or
  CASDA calls could -- that part needs a human running `hivalidate-qa` themselves.

### Phase 5 — Post-processing [DONE 2026-07-30]
- [x] `postprocess.py`: `filter_by_qa` + `write_validation_csv` (replaces
      `legacy/create_validation_csv.py` -- much simpler now, since it no longer needs
      to reverse-engineer which sources are "true" from a directory of PNG
      filenames; `validated_cat.xml` already carries the `qa` flag directly),
      `extract_cubelets` (replaces `legacy/extract_true_cubelets.py`), `build_mosaic`
      (replaces `legacy/mosaic_sofia_true_detections.py`, via
      `reproject.mosaicking.reproject_and_coadd` onto the full-field mosaic's WCS --
      verified against `reproject`'s actual installed signature, not memory).
      `hivalidate-postprocess` runs all three from a `validated_cat.xml`, fixing
      issue #4 (directory-naming mismatch between stages) since every stage now
      reads/writes through `Config.paths`, not ad hoc constants.
- Added `paths.field_mosaic` to the config schema (optional; the full-field
  `mom0.fits` the mosaic step needs) -- the mosaic step is skipped, not an error,
  when unset.
- **Ran for real** end-to-end (dry-run -> QA -> postprocess) against 5 real sources
  from `data/work/SB82605/`, scripted to flag 3 true, and against the real
  `data/run_sofia/mom0.fits` full-field mosaic (3585x3552, not a synthetic
  stand-in). `validated_true.csv` correctly contained exactly the 3 true-flagged
  sources; `true_cubelets/` had exactly their files (13 each); the mosaic FITS
  correctly matched the field's shape/WCS, and rendering it confirmed by eye that
  the three tiny detections land at their real, distinct sky positions within the
  full field.

### Phase 6 — End-to-end validation [DONE 2026-07-30]
- [x] Fresh full-scale combine → dedup → rename over all 45 runs, from scratch --
      reproduced Phase 1's numbers exactly (670 → 448 sources, 5824 files),
      confirming determinism across every later-phase code change.
- [x] Cross-checked the 448-source deduped catalogue against the 159 legacy "true"
      examples in `data/output_validation_true/` by positional match (exact-name
      matching found zero overlap -- expected, given how centroid-sensitive SoFiA's
      name strings are; parsed RA/Dec directly from the legacy filenames' embedded
      J-coordinates instead): **144/159 (90.5%) matched within 30″**, median
      separation 2.0″. The 15 non-matches were checked against the *pre-dedup*
      combined catalogue too (not just deduped) -- separations were essentially
      identical before and after dedup, ruling out dedup as the cause; most are
      hundreds of arcsec to ~20 arcmin away, meaning they're simply outside the sky
      area these 45 runs cover (a different pointing in the legacy dataset), not a
      pipeline defect.
- **Two real bugs found and fixed by inspecting actual full-scale dry-run output**
  (not caught by any test, since both were wrong physical constants producing
  plausible-looking but incorrect images, not code paths that could crash):
  1. `SkyViewBackend` assumed a hardcoded 1.7 arcsec/pixel DSS2 plate scale to
     convert requested field-of-view into a pixel count. The real plate scale is
     1.0 arcsec/pixel (confirmed live against a real SkyView response's CDELT), so
     every optical cutout had an actual field of view ~59% of what was requested.
     Fixed by requesting `width`/`height` as angular `Quantity` params directly
     (verified live that `astroquery.skyview.SkyView.get_images` supports this) --
     removes the plate-scale assumption entirely rather than just correcting the
     constant, so it stays correct for any survey, not only DSS2.
  2. `hivalidate.cli.dry_run`'s cutout-sizing calculation used the *same* wrong 1.7
     arcsec/pixel constant a second time, to convert mom0's pixel shape into a
     requested angular size. The real mom0 pixel scale for this dataset is 6.0
     arcsec/pixel (confirmed live against a real cubelet header) -- off by 3.5x, a
     different wrong number than bug 1's but the identical root cause (an assumed
     constant standing in for something computable from the actual WCS). Fixed by
     computing the field of view from mom0's own real WCS pixel scale
     (`plotting.reference_field_of_view_arcsec`) instead of assuming.
  3. Even with the cutout *request* sizes now correct, the continuum panel's
     *displayed* field of view still didn't match the other three sky panels --
     only mom0/mom1 explicitly borrowed the optical panel's pixel limits (which
     only worked because they share its exact WCS by construction); the optical
     panel itself was never anchored to anything, and the continuum panel was never
     constrained at all, just auto-scaled to its own cutout's native extent. Fixed
     with `plotting._set_fov`, which pins every sky panel's xlim/ylim to the same
     real sky box (computed from mom0, per the explicit design ask: "HI moment 0
     should be reference") regardless of each panel's own native pixel scale or a
     backend's rounding of the requested size.
  All three fixed together and verified by re-rendering the same real source and
  visually confirming all four sky panels now show identical RA/Dec tick ranges,
  plus 4 new regression tests in `test_plotting.py` that deliberately give optical
  and continuum different native pixel scales (the real-world condition that
  exposed bug 3) and assert their displayed field of view matches within 5%.
  - **Follow-up correction, same day**: the fix above initially used
    `DISPLAY_FOV_FACTOR = 5` (all panels 5x wider than mom0's own footprint) --
    direct feedback was that this made contour detail hard to see, and a
    request to check how the legacy script actually handled it. Re-read
    `legacy/validate_detections.py`'s exact panel projections/limits: it
    achieves cross-panel consistency by borrowing pixel limits (mom0/mom1 from
    optical) and, for continuum, by reading back the optical cutout's *actual*
    returned real size and requesting that same size for continuum (a
    fetch-time "chase" mechanism, not a display-time one) -- but the reference
    size it all traces back to, `npix = max(mom0_shape) * 5`, is a pixel count
    taken at the *optical survey's own resolution* (~1.0"/pix for DSS2), not
    mom0's (6.0"/pix here), so legacy's actual displayed FOV worked out to
    ≈0.83x mom0's real footprint -- an artifact of mixing pixel counts across
    two different resolution grids, not a deliberate ratio. Changed
    `DISPLAY_FOV_FACTOR` to `1.0` (exactly mom0's own footprint) per the direct
    instruction, keeping `_set_fov`'s display-time-pinning mechanism (more
    robust than fetch-time chasing now that continuum has a multi-backend
    fallback chain, so there's no single "whichever backend responded" to chase).
    Re-verified visually: 192 arcsec FOV (vs the first fix's 960), contour
    detail clearly visible, all four panels still matching.
- [x] **Full-scale dry-run completed: 448/448 sources OK, 0 failures**, all fixes
  above included. Two prior full batch runs were discarded mid-flight as bugs were
  found and fixed rather than let them finish and regenerate anyway.
- **A third real bug found by inspecting this full-scale output**: one source
  (`SoFiA_J203449.97-531430.0`) had a completely blank PV panel. Investigated the
  actual FITS data, not just the code: that source's `*_pv.fits` cubelet is
  entirely NaN (2583/2583 pixels) -- confirmed genuinely SoFiA's own output (its
  header's `PVD_PA` is literally `-NAN`, SoFiA's own record that it couldn't
  determine a kinematic position angle), not a pipeline bug. Scanned all 448 real
  cubelets: 1/448 (0.2%) have this characteristic. `build_validation_figure` now
  shows "No PV data available (SoFiA produced an empty PV cubelet)" instead of a
  silent blank panel indistinguishable from a rendering failure. 2 regression
  tests added.
- **Reproducibility-metadata bug found while patching the above**: the fix for
  the PV bug was committed *while the 448-source batch was still running* (the
  process had the older code already loaded in memory). `hivalidate-dry-run`'s
  manifest computed its recorded git commit hash *after* the batch loop finished,
  so a fresh `git rev-parse HEAD` at that point picked up the newer commit from
  disk -- misattributing nearly the whole batch's actual output to a commit that,
  in truth, only affected the one source manually re-rendered afterward. Fixed by
  capturing the hash once before the batch loop starts instead of after.
- [x] QA + post-process re-run against the real, full-scale (448-source) manifest:
  scripted a 10-source review (not fabricating judgments for all 448 -- that's
  inherently a human task, already proven correct at real scale in Phases 4/5),
  then ran `hivalidate-postprocess` for real against the full 448-source deduped
  catalogue and the real full-field mosaic: correctly filtered to the 5
  true-flagged sources, copied their 65 cubelet files, and built a mosaic FITS
  matching the field's real (3585, 3552) shape via `reproject_and_coadd`.
- **Summary**: four real bugs found and fixed in this phase, none of them caught
  by unit tests written against the same wrong assumptions as the code -- every
  one required generating and actually looking at real output (visually or by
  inspecting the underlying FITS data) to catch. This is the concrete case for
  why PLAN.md's "verified live" pattern was worth the time it cost throughout
  every earlier phase, not just this one.

### Phase 7 — Polish [DONE 2026-07-30]
- [x] Filled in `docs/pipeline_overview.md`: data-flow diagram (Mermaid) plus a
      stage-by-stage walkthrough grounded in the real Phase 6 numbers (670 -> 448
      sources, 33% dedup rate, 5824 cubelet files, 448/448 dry-run success), not
      illustrative placeholders.
- [x] `README.md`: Status section updated to reflect all seven phases complete (and
      the one known unresolved item -- `column_density`'s unverified constant --
      surfaced there, not buried); added a Quick Start with the full real command
      sequence; added `hivalidate-check-connectivity` to the stages table (it existed
      since Phase 2 but was missing from this table).
- [x] `REFERENCES.md` cross-checked against actual code citations (`grep` for every
      bracketed key across `src/`): every citation used in code has a matching entry,
      and every physics function in `conversions.py` now has a docstring pointing at
      one, including the small helpers (`freq_to_redshift`, `velocity_to_freq`,
      `freq_width_to_velocity_dispersion`, `column_density_sensitivity`) that just
      derive from an already-cited relation rather than needing a separate source.
      Added a note to the `[GAMA]` entry clarifying it's not used by any code yet
      (the cross-match itself is an explicit non-goal, section 7) so its presence in
      the bibliography doesn't look like an oversight.
- [x] CI verified green by actually running its exact steps locally, not just
      reading the workflow file: `pip install -e ".[dev]"`, `ruff check src tests`,
      `pytest -v` -- 134 passed, lint clean. Confirmed the workflow's YAML parses
      and its `branches: [main]` trigger matches the repo's actual current branch.
- [x] Version bumped `0.1.0.dev0` -> `0.1.0` in `pyproject.toml` and
      `hivalidate.__version__`; tagged `v0.1` (local tag only -- this repository has
      no configured remote to push it to).

## 9. Definition of done for v1

- [x] Pipeline runs end-to-end on `run_sofia/` via CLI, driven entirely by a config
  file (no hardcoded per-field constants left in source).
- [x] Optical cutouts fall back SkyView → Legacy Survey; continuum falls back local
  file → RACS/CASDA (non-interactive login); both cached and provenance-tracked.
- [x] Dry-run runs unattended on an HPC compute node (`Agg` only, no display, no
  interactive prompts) and produces plots + manifest for the whole sample before any
  QA happens.
- [x] QA runs as a fully separate stage against the dry-run output (no live
  cutout/figure regeneration), is resumable, and never loses progress on
  interruption.
- [x] A preflight connectivity/auth check (CASDA login + trivial query, image-survey
  reachability) runs automatically before dry-run starts processing sources, and
  fails fast with a clear error if something's misconfigured.
- [x] `tests/` pass in CI against the fixture (134 passed, verified locally against
  the exact CI steps); a full run against `run_sofia/` has been done (448/448 OK)
  and checked against `data/output_validation_true/` (144/159, 90.5%, matched
  positionally within 30").
- [x] Every function touching HI physics has a docstring citing `REFERENCES.md`.
- [x] Git history exists from phase 0 onward (16 commits); no large data files
  committed (`.git` is 16 MB; largest tracked file is a 484 KB fixture FITS file,
  committed deliberately for tests).

All definition-of-done items satisfied. v0.1 tagged.
