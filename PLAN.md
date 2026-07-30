# HI Source-Finding Validation Pipeline — Implementation Plan

Status: draft, not yet started. This document captures everything decided in planning
discussion before writing code. Update it as decisions change — it should stay the
single source of truth for scope and sequencing.

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

### Phase 4 — Interactive QA (runs locally, not on HPC)
- [ ] `qa.py`: review loop over the dry-run manifest/PNGs only — never regenerates
      cutouts or figures, so it has no `Agg`/HPC constraint and can use a normal
      interactive matplotlib backend or a simple image viewer
- [ ] Resumable, incremental per-source save (fixes issue #7), optional comment field,
      back option
- [ ] Output catalogue gets qa flag + provenance + comment + reproducibility metadata

### Phase 5 — Post-processing
- [ ] `postprocess.py`: migrate `create_validation_csv.py`, `extract_true_cubelets.py`,
      `mosaic_sofia_true_detections.py`, aligning directory naming end-to-end so no
      manual renaming is needed between stages (fixes issue #4)

### Phase 6 — End-to-end validation
- [ ] Run the full pipeline over all 45 `run_sofia/` runs: combine → dedup → rename →
      dry-run → QA → post-process
- [ ] Cross-check output against the 159 known examples in `data/output_validation_true/`
      as a regression check
- [ ] Fix whatever breaks at real scale that the fixture didn't catch

### Phase 7 — Polish
- [ ] Fill in `docs/pipeline_overview.md`
- [ ] Finish `README.md`, confirm `REFERENCES.md` covers all cited science
- [ ] Confirm CI green, tag `v0.1`

## 9. Definition of done for v1

- Pipeline runs end-to-end on `run_sofia/` via CLI, driven entirely by a config file
  (no hardcoded per-field constants left in source).
- Optical cutouts fall back SkyView → Legacy Survey; continuum falls back local file →
  RACS/CASDA (non-interactive login); both cached and provenance-tracked.
- Dry-run runs unattended on an HPC compute node (`Agg` only, no display, no
  interactive prompts) and produces plots + manifest for the whole sample before any
  QA happens.
- QA runs as a fully separate stage against the dry-run output (no live cutout/figure
  regeneration), is resumable, and never loses progress on interruption.
- A preflight connectivity/auth check (CASDA login + trivial query, image-survey
  reachability) runs automatically before dry-run starts processing sources, and
  fails fast with a clear error if something's misconfigured.
- `tests/` pass in CI against the fixture; a full run against `run_sofia/` has been
  done at least once and checked against `data/output_validation_true/`.
- Every function touching HI physics has a docstring citing `REFERENCES.md`.
- Git history exists from phase 0 onward; no large data files committed.
