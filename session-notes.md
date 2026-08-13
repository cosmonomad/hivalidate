╭─── Claude Code v2.1.212 ─────────────────────────────────────────────────────╮
│                                                    │ Tips for getting        │
│                 Welcome back Jonny!                │ started                 │
│                                                    │ Run /init to create a … │
│                       ▐▛███▜▌                      │ ─────────────────────── │
│                      ▝▜█████▛▘                     │ What's new              │
│                        ▘▘ ▝▝                       │ Bug fixes and reliabil… │
│    Sonnet 5 · Claude Pro · ngc628@gmail.com's      │ Added Claude Opus 5 (`… │
│    Organization                                    │ Added `sandbox.network… │
│ ~/Research/ASKAP/softwares/validate_source_finding │ /release-notes for more │
╰──────────────────────────────────────────────────────────────────────────────╯

 ▎ Tackle your toughest work with Opus 5. Switch anytime with /model.

❯ /model oppus 5 
  ⎿  Model 'oppus 5' not found

❯ /model opus 5 
  ⎿  Model 'opus 5' not found

❯ /model [opus 5] 
  ⎿  Model '[opus 5]' not found

❯ /model Opus 5 
  ⎿  Model 'Opus 5' not found

❯ /model                                                                        
  ⎿  Set model to Sonnet 5 (default) and saved as your default for new sessions

❯ In the directory here there are several scripts used to validate HI source    
  finding results from SoFiA (https://gitlab.com/SoFiA-Admin/SoFiA-2). The main 
  validation code is "validate_detection.py" and example source finding         
  results are stored under the "run_sofia" folder. The main sequence of the     
  validation process is 1) make a validtion plot using validate_plot.py, 2)     
  remove duplicate detections using remove_duplicate.py, 3) rename the files    
  with rename_cubeletes.py and then 4) run the main validation script. The      
  other scripts are used for post-validation works. I want to analyse all the   
  scripts and data to see how to build a effective workflow pipeline for this   
  validation process. I want you to explore those files/data and report back on 
  what you find.                                                                

⏺ I'll explore the directory structure and scripts to understand the validation
  workflow.

  Searched for 3 patterns, read 9 files, ran 8 shell commands (ctrl+o to expand)

⏺ I had cd'd into run_sofia. No .md/README/requirements file exists anywhere,
  and this isn't a git repo. Let me check the swap file from the correct
  directory.

  Ran 1 shell command (ctrl+o to expand)

⏺ What I found

  Repo layout: no git, no README/requirements file, 10 top-level Python/shell
  scripts, and run_sofia/ (2.4 GB) containing 45 separate SoFiA outputs
  (SB82605_Removal_001 … _045), each with its own catalogue (.xml/.txt/.sql),
  moment maps, and a _cubelets/ folder with per-source products (cube, mask,
  mom0-2, pv, pv_min, snr, spectrum). Together they hold 715 catalogue rows
  (~656 unique source names, 14 name-collisions between adjacent runs). This
  "many small SoFiA runs over sub-cubes/iterations" structure is clearly the
  normal mode of operation here, not a single SoFiA run — any pipeline needs to
  treat "combine N runs" as a first-class step. There's also a stray
  .validate_detections.py.swp (timestamped today, 10:50) — looks like an unsaved
  vim session on validate_detections.py; worth a vim -r check before you assume
  the file on disk is current.

  Script inventory (by pipeline stage)

  Stage: 1. Combine/plot
  Script: plot_detections.py
  What it actually does: Globs SB82605*_cat.xml, vstacks all runs into one
  VOTable, plots freq vs flux. Output name is derived from  the input glob
  (SB82605_Removal_cat.xml here).
  ────────────────────────────────────────
  Stage: 2. Dedup
  Script: remove_duplicate.py
  What it actually does: Opens a hardcoded SB82605_jolly_cat.xml, drops rows
  whose name string repeats, in place (with .bak).
  ────────────────────────────────────────
  Stage: 3. Rename
  Script: rename_cubelets.py + run_all_renames.sh
  What it actually does: Maps SoFiA numeric id → source name per run and
  copies/renames cubelet files accordingly into one shared
  SB82605_jolly_cubelets/ dir.
  ────────────────────────────────────────
  Stage: 4. Main validation
  Script: validate_detections.py
  What it actually does: For each source: pulls DSS2 optical cutout, DINGO
  continuum cutout, builds a 6-panel figure (optical+mom0, cont+mom0, mom0,
  mom1, spectrum, PV), optionally cross-matches GAMA, and (if
  do_validation=True) prompts interactively for a
  True/False/Uncertain/Duplicate flag, then writes an updated catalogue + LaTeX
   table.
  ────────────────────────────────────────
  Stage: Post-validation
  Script: create_validation_csv.py, extract_true_cubelets.py,
  mosaic_sofia_true_detections.py, download_legacy.py
  What it actually does: Build a CSV of "true" sources from saved PNG filenames,

  copy their cubelets into a _true dir, mosaic their moment-0 maps onto the
  full-field image, and (separately, unrelated survey-name placeholders) pull
  Legacy Survey cutouts.

  Issues that will bite you building a pipeline out of this

  1. Naming convention mismatch, verified against the actual data.
  run_all_renames.sh globs for SB82605_jolly_*_cat.xml as input — but that's the
  pipeline's own output naming. I ran it against run_sofia/: zero matches (no 
  matches found). The raw SoFiA files are SB82605_Removal_*_cat.xml. As shipped,
  the rename step can't run on this example data without editing the glob.
  2. validate_detections.py is hardcoded to a different survey entirely.
  cont_file points at /scratch/.../WALLABY/SB51535/... — a different survey/SB
  than the DINGO SB82605 data in run_sofia/. Every path in that script
  (cont_file, dir_cubelets, dir_gamacat, sofia_file, outname) is a bare
  module-level variable, not a CLI arg — it has to be hand-edited per field/run.
  Same pattern in every other script (plot_detections.py, remove_duplicate.py,
  create_validation_csv.py, extract_true_cubelets.py,
  mosaic_sofia_true_detections.py all hardcode filenames at top of file); only
  rename_cubelets.py has real argparse.
  3. Interactive QA step looks broken with the current settings.
  validate_detections.py sets matplotlib.use('Agg') (non-interactive backend)
  but the QA branch (do_validation=True) calls plt.show() and then blocks on
  input() for a quality flag — with Agg, plt.show() won't display anything, so
  you'd be flagging blind. It's currently shipped with do_validation=False, so
  this path isn't exercised by default.
  4. Downstream directory names don't match what upstream produces. copy_data()
  in validate_detections.py writes into save_dir + 'true/' (nested subfolder),
  but create_validation_csv.py expects a flat directory literally named
  output_validation_true. Someone has to manually rename/move between these
  steps as written.
  5. Dedup is exact-string-match only, at the wrong scope. remove_duplicate.py
  matches on the literal SoFiA-generated name string. That catches only sources
  whose derived coordinates rounded to an identical string (the 14 pairs I
  found) — a source detected twice at slightly different pixel centroids in two
  adjacent Removal runs would generate two different names and slip through. A
  positional/velocity cross-match (the repo already has this pattern in
  search_gama()) would be more robust than string equality.
  6. Per-run id fields reset to 1, 2, 3… in every Removal_* catalogue —
  confirmed by inspection. That's fine for rename_cubelets.py since it's
  correctly scoped per-run (one xml + its own cubelets dir), but it means id is
  meaningless once catalogues are combined — only name is a safe global key.
  Keep dedup/merging keyed on name (or better, ra/dec/freq), never id, once you
  combine runs.
  7. Everything after step 3 assumes a single jolly-prefixed dataset, i.e. steps
  5–7 (create_validation_csv.py → extract_true_cubelets.py →
  mosaic_sofia_true_detections.py) chain correctly by filename only if you've
  consistently used that same prefix everywhere — there's no config file or
  single source of truth for the field/SB identifier, so each script's constant
  has to be edited in lockstep.

  Net effect for a pipeline design

  The intended order (combine → dedup → rename → validate → post-process) is
  sound and the science content (redshift/mass/column-density conversions, GAMA
  cross-match) is solid, but nothing here is parameterized: every script is a
  one-off with hardcoded paths from what looks like several different past runs
  (jolly, G23_T0_350h_001, SB51535, SB82605_Removal) pasted together. To make
  this a real pipeline you'd want, at minimum: (a) one config (field/SB name,
  base dir) threaded through all scripts instead of top-of-file constants, (b)
  fix run_all_renames.sh's glob to match raw SoFiA output naming, (c) make step
  boundaries agree on directory names, (d) swap remove_duplicate.py to
  positional dedup, and (e) either fix or explicitly disable the
  Agg+plt.show()+input() interactive QA path.

  I haven't changed anything — this is purely the exploration you asked for.
  Happy to turn this into an actual refactor/config-driven pipeline if you want.

✻ Churned for 3m 1s

※ recap: You're mapping out how to turn these SoFiA validation scripts into a proper pipeline; I just finished reviewing all the scripts and the run_sofia example data and reported back the findings. Next: decide if you want me to actually refactor the scripts into a parameterized pipeline. (disable recaps in /config)

❯ Before we get to writing code we need to establish some additional functions. 
  The current script is to get optical images of each source from Skyview but   
  I want to add other options for example, legacy survey image like the script  
  of download_legacy.py and also for continuum image, I want to get continuum   
  images from ASKAP RACS survey (using astroquery.casda) if no continuum image  
  exists in some directory. Before interactive validation, I added a dry-run    
  validation to see the validation plots prior to actual validiation. Any       
  recommendations other than these.                                             

⏺ A few gaps worth closing before coding, given what's in the pipeline already:

  - Cutout caching, keyed by source name + survey + size — dry-run and the real
  interactive pass will otherwise hit SkyView/Legacy/RACS twice for every
  source. Cache to disk once, reuse on both passes.
  - Survey footprint pre-check — RACS only covers Dec ≲ +41° (and has epoch/band
  gaps), Legacy Survey has its own coverage limits. Check coverage before
  querying so a source at the edge doesn't just silently fail or return a blank
  image partway through a 600+ source run.
  - Incremental QA persistence — right now qa flags only get written to the
  catalogue after the entire loop finishes. With ~650+ sources nobody validates
  in one sitting; a crash or Ctrl-C loses everything. Write/append each flag as
  it's made (e.g. a small per-source JSON/CSV log) so a session is resumable.
  - Provenance field — once optical has 2+ sources and continuum has 2, record
  which survey/image was actually used for each source in the output catalogue,
  or you can't reproduce/audit a plot later.
  - Source-of-truth for "which survey did we actually use" ties into a
  fallback-chain abstraction: one get_cutout(pos, size, priority=[...]) function
  per image type instead of separate ad hoc get_opt_imag/get_cont_imag, so
  adding a third source later doesn't mean another bespoke function.

  Lower priority but cheap to add now: a free-text comment field alongside the
  t/f/u/d flag (useful for "uncertain" cases on later re-review), and a "back"
  option in the QA loop so a mis-keyed flag doesn't require rerunning.

  Want me to fold any of these into the plan, or is the caching + provenance
  pair the main one you care about right now?

✻ Sautéed for 36s

❯ opt_imag and cont_imag are used for different figures in the validation plot. 
  I added some exmaple validation plots into /data/output_validation_true.      
  Listed 2 directories (ctrl+o to expand)

⏺ Found it at ./data/output_validation_true (relative to the project root). Let
  me look inside.

  Read 1 file, listed 1 directory (ctrl+o to expand)

⏺ Looked at both — data/output_validation_true/ has 159 six-panel PNGs matching
  the validate_detections.py layout (opt_imag → top-left panel with optical DSS2
  + column-density contours, cont_imag → top-middle panel with continuum + the
  same contours overlaid), and data/continuum_image/ has the actual local
  continuum FITS for this field (...WALLABY_2051-53B.SB82605.cont...), which
  also fixes the hardcoded-wrong-SB path issue I flagged earlier — this becomes
  the real "local continuum exists" case, with RACS/CASDA as the fallback when a
  field's continuum file isn't present there.

  That doesn't change the fallback-chain design — each panel still gets its own
  image (optical vs continuum), just via two separate calls to survey-specific
  fallback chains (get_optical_cutout(pos, size, priority=[SkyView, 
  LegacySurvey]) and get_continuum_cutout(pos, size, local_dir, 
  fallback=RACS_CASDA)), each returning (data, wcs) for its own axis.

  Anything else to fold in before we plan the implementation, or should I start
  sketching the module structure?

✻ Sautéed for 39s

※ recap: You're building a validation pipeline for SoFiA HI source detections, adding fallback image sources (SkyView/Legacy optical, local/RACS continuum) and a dry-run mode. Next: sketch the module structure for the fallback-chain cutout functions before writing code. (disable recaps in /config)

❯ ok Lets discuss implementatiom on top of your ideas.                          
  - I want to work in python (bash scripts is ok where it is more efficient).   
  - The directory here needs a sensible structure                               
  - Documentation is important.                                                 
  - It should be version controlled with git.                                   
  - I want high quality commenting throughout so anyone can follow the code and 
  science it encodes (include references to the literature for any coded        
  science).                                                                     
  - The code should be validated using the data in run_sofia                    
  - Anything I've forgotten?                                                    
  Report back your recommendations.                                             

⏺ A few things I'd add to your list:

  Package structure, not flat scripts. Turn this into an installable package
  (src/<name>/ with submodules like catalogue.py, cutouts.py, plotting.py,
  qa.py, postprocess.py) with thin CLI entry points per stage, rather than
  top-level scripts full of module-level constants. This is really a
  prerequisite for the rest of your list — you can't unit-test or cleanly
  document code that executes side effects on import, which is how every current
  script is written.

  Config file instead of hardcoded constants. One YAML/TOML per field/SB (paths,
  survey priority order, output naming) threaded through all stages via CLI
  args. This directly fixes the naming-mismatch fragility I found in the audit
  (the jolly/Removal/SB51535 inconsistencies).

  Dependency pinning, and reconsider MontagePy. There's no
  requirements.txt/environment.yml anywhere right now. Also worth reconsidering:
  continuum cutouts currently go through MontagePy.mSubimage (a compiled C
  library, not pip-installable). Since RACS/CASDA cutouts will need reprojection
  too, astropy's Cutout2D or reproject_interp (already a dependency via the
  mosaic script) could likely replace it and shrink the install footprint to
  pure-Python astropy stack.

  Per-source fault isolation. Nothing in the current loop catches exceptions —
  one bad cutout or network timeout mid-batch kills the whole 650-source run,
  and combined with QA only being written at the very end, you lose everything
  done so far. Wrap each source in try/except, log the failure, move on.

  Testing with a small fixture, not the full 2.4 GB. pytest over a couple of
  Removal_* runs extracted as a committed fixture (fast, CI-friendly) for
  unit/integration tests, with the full run_sofia set reserved for a slower,
  separately-triggered end-to-end validation pass — not something you rerun on
  every change.

  Reproducibility metadata. Stamp each output catalogue with the pipeline's git
  commit hash + config used + software versions (SoFiA's version is already in
  the catalogue; the pipeline's isn't). Matters once this feeds a publication.

  Repo hygiene. .gitignore for FITS/PNG outputs and downloaded cutouts (data
  shouldn't go into git); a license if this is ever shared beyond you; and a
  single REFERENCES.md bibliography keyed by short IDs ([SoFiA2], [Meyer17],
  GAMA/RACS/Legacy Survey citation requirements) that inline code comments point
  to, rather than repeating full citations in every docstring.

  Lint/format consistency. black/ruff + pre-commit, and maybe a minimal GitHub
  Actions CI (lint + fixture tests on push) — cheap given git's already in the
  plan, and reinforces "anyone can follow the code."

  Want me to turn this into a concrete plan (directory layout, module
  boundaries, stage-by-stage build order) next?

✻ Sautéed for 58s

❯ MontagePy is pip-installable (see https://github.com/Caltech-IPAC/Montage)    
  and has been installed in one of my python envs (base)                        

⏺ Good to know — I was wrong there, thanks for the correction. MontagePy ships
  as prebuilt wheels on PyPI, so it's a normal pip dependency, not a
  build-from-source burden. I'll drop that recommendation: no need to replace
  mSubimage with reproject/Cutout2D — keep MontagePy for continuum cutouts since
  it's already proven in the current pipeline (and reproject is still needed
  separately for the mosaic step regardless, so there's no dependency-count win
  from switching).

  One adjustment: since we're pinning dependencies, I'll just make sure
  MontagePy is listed explicitly in the package's dependency spec/environment
  file, and note in the docs that it's the one dependency worth double-checking
  on a new machine (wheel availability varies by platform/Python version) rather
  than assuming it installs as trivially as pure-Python packages.

  Rest of the recommendations stand unchanged. Ready to move to a concrete plan
  whenever you are.

✻ Worked for 17s

❯ Ok Write a plan that clearly lays out the work we need to do to get started   
  in a markdown file. The plan should include everything we've discussed        

⏺ Write(PLAN.md)
  ⎿  Wrote 233 lines to PLAN.md
       1 # HI Source-Finding Validation Pipeline — Implementation Plan
       3 Status: draft, not yet started. This document captures everythin
         g decided in planning
       4 discussion before writing code. Update it as decisions change — 
       5 single source of truth for scope and sequencing.
       6 
       8 
       9 Turn the current collection of ad hoc, hardcoded scripts (`valid
         ate_detections.py`,
         `, `run_all_renames.sh`,
     … +353 lines (ctrl+o to expand)

⏺ I noticed a duplicated line snuck into §9 — fixing it.

⏺ Update(PLAN.md)
  ⎿  Removed 1 line
      224    (no hardcoded per-field constants left in source).
      225  - Optical cutouts fall back SkyView → Legacy Survey; continuum
            falls back local file →
      226    RACS/CASDA; both cached and provenance-tracked.
      227 -  provenance-tracked.                                         
      227  - Dry-run plots can be generated for the whole sample before a
           ny interactive QA.
      228  - QA sessions are resumable and never lose progress on interru
           ption.
      229  - `tests/` pass in CI against the fixture; a full run against 
           `run_sofia/` has been

⏺ Wrote PLAN.md at the repo root. It covers: what already exists (run_sofia/,
  the real continuum file, the 159 example plots) as the grounding/test data, a
  table of concrete bugs found in the current scripts mapped to the phase that
  fixes each, the target directory/package structure, every design decision from
  our discussion (fallback chains, caching, footprint checks,
  resumable/incremental QA, positional dedup, fault isolation, provenance,
  testing strategy, docs/citation convention, tooling), six open questions I
  couldn't resolve for you (package name, CLI framework, config format, CASDA
  auth, where run_sofia/ should live, license), explicit non-goals, and an
  8-phase build sequence ending in a "definition of done."

  Worth your eyes first: the open questions in §6, especially the
  astroquery.casda auth question — if RACS continuum needs an OPAL login, that
  changes the continuum fallback design non-trivially and is worth settling
  early.

✻ Worked for 1m 59s

※ recap: We're building a documented, tested Python pipeline to validate SoFiA HI source-finding results, and I just wrote the implementation plan to PLAN.md. Next: you review the open questions in section 6 (package name, CLI framework, config format, CASDA auth) so we can start phase 0. (disable recaps in /config)

❯ Here are my answers to your questions in $6                                   
  1. I like the name of package                                                 
  2. go for argparse                                                            
  3. YAML                                                                       
  4. It requires log-in see                                                     
  https://astroquery.readthedocs.io/en/latest/casda/casda.html                  
  5. move to under 'data/'                                                      
  6. Recommand licence                                                          
                                                                                
  Regarding 'Agg' in plotting, I often need to run the validation code in HPC   
  environment where I can't run interactive mode (only dry-run works). Based on 
  these, update the plan.                                                       

⏺ Update(PLAN.md)
  ⎿  Added 3 lines, removed 4 lines
      86  │   └── test_pipeline_e2e.py     # runs the fixture through com
          bine→dedup→rename→dry-run
      87  ├── docs/
      88  │   └── pipeline_overview.md     # stage-by-stage narrative + d
          ata flow diagram
      89 -├── data/                        # gitignored: run_sofia/, cont
         -inuum_image/, output_validation_true/, cutout cache            
      90 -└── run_sofia/                   # existing example data (moved
         - under data/ or symlinked — decide in phase 0)                 
      89 +└── data/                        # gitignored: continuum_image/
         +, output_validation_true/, cutout cache, credentials           
      90 +    └── run_sofia/                # existing example data — pri
         +mary integration-test dataset                                  
      91  ```
      92  
      93 -Open naming decision: package name (`hivalidate` is a placehold
         -er) — confirm before                                           
      94 -phase 0 finishes.                                              
      93 +Package name: `hivalidate` (confirmed).                        
      94  
      95  ## 5. Design decisions carried over from discussion
      96  

⏺ Update(PLAN.md)
  ⎿  Error editing file

  Read 1 file (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 1 line, removed 1 line
      57  ├── configs/
      58  │   └── SB82605.yaml             # example per-field/SB config 
          (paths, survey priority)
      59  ├── src/
      60 -│   └── hivalidate/              # package name placeholder — c
         -onfirm/rename                                                  
      60 +│   └── hivalidate/              # confirmed package name      
      61  │       ├── __init__.py
      62  │       ├── config.py            # load & validate field/SB YAM
          L config
      63  │       ├── conversions.py       # freq<->z<->vel, HI mass, col
          umn density (heavily cited)

⏺ Update(PLAN.md)  ⎿  Added 1 line, removed 1 line
      34  |---|---|---|---|
      35  | 1 | `run_all_renames.sh` globs `SB82605_jolly_*_cat.xml` but 
          raw SoFiA output is named `SB82605_Removal_*_cat.xml` — zero ma
          tches as shipped | `run_all_renames.sh` | 1 |
      36  | 2 | Hardcoded paths (`cont_file`, `dir_cubelets`, `dir_gamaca
          t`, `sofia_file`, `outname`) from a different survey/SB (`WALLA
          BY/SB51535`) baked in as module constants | `validate_detection
          s.py` | 1 |
      37 -| 3 | `matplotlib.use('Agg')` (non-interactive) combined with `
         -plt.show()` + blocking `input()` in the QA loop — can't actuall
         -y see the plot when `do_validation=True` | `validate_detections
         -.py` | 4 |                                                     
      37 +| 3 | `matplotlib.use('Agg')` (non-interactive) combined with `
         +plt.show()` + blocking `input()` in the QA loop — can't actuall
         +y see the plot when `do_validation=True` | `validate_detections
         +.py` | 3/4 — resolved by decoupling dry-run (always `Agg`, HPC-
         +safe) from QA (interactive, reviews saved PNGs only) |         
      38  | 4 | `copy_data()` writes into `save_dir/true/…` (nested) but 
          `create_validation_csv.py` expects a flat `output_validation_tr
          ue/` directory | `validate_detections.py`, `create_validation_c
          sv.py` | 5 |
      39  | 5 | Deduplication is exact-string match on the SoFiA-generate
          d name, which only catches collisions where derived coordinates
           rounded identically — misses near-duplicates with slightly dif
          ferent centroids across adjacent runs | `remove_duplicate.py` |
           1 |
      40  | 6 | SoFiA `id` resets to 1..N per run; nothing today merges c
          atalogues on `id`, but this must stay an explicit rule, not an 
          accident, once merging code exists | `rename_cubelets.py` | 1 |

⏺ Update(PLAN.md)
  ⎿  Added 26 lines, removed 7 lines
       99    needs testing.
      100  - **Config over constants**: one YAML per field/SB, passed to 
           every CLI stage — replaces
      101    the current hardcoded-constant-per-script pattern.
      102 +- **CLI framework**: `argparse`, one thin entry point per stag
          +e (`combine`, `dedup`,                                        
      103 +  `rename`, `dry-run`, `qa`, `postprocess`) — consistent with 
          +the pattern                                                   
      104 +  `rename_cubelets.py` already uses.                          
      105  - **Cutout fallback-chain abstraction**: `get_optical_cutout(p
           os, size, priority=[...])`
      106    and `get_continuum_cutout(pos, size, local_dir, fallback=...
           )`, each returning
      107    `(data, wcs, provenance)`. Optical priority: SkyView → Legac
           y Survey. Continuum:
      108    local file (MontagePy `mSubimage`) → RACS via `astroquery.ca
           sda` if no local file
      109    covers the field. Both panels in the validation plot call th
           eir own chain
      110    independently — same abstraction, separate figures.
      111 +- **CASDA authentication**: `astroquery.casda` requires an OPA
          +L login                                                       
      112 +  (https://astroquery.readthedocs.io/en/latest/casda/casda.htm
          +l). Pipeline code never                                       
      113 +  interactively prompts for credentials — it reads them from e
          +nvironment variables                                          
      114 +  (`CASDA_USERNAME`/`CASDA_PASSWORD`) or a local, gitignored c
          +redentials file                                               
      115 +  referenced from the field config, so the continuum RACS fall
          +back can run unattended                                       
      116 +  in an HPC batch job. Document OPAL account setup in `README.
          +md`. Open item to verify:                                     
      117 +  whether HPC compute nodes (as opposed to the login/head node
          +) have outbound internet                                      
      118 +  access at all — if not, the RACS fallback may need to run as
          + a separate,                                                  
      119 +  network-enabled step rather than inline with dry-run.       
      120  - **Cutout caching**: on-disk cache keyed by `(source name, su
           rvey, size)` so dry-run
      109 -  and the interactive QA pass never re-download the same cutou
          -t.                                                            
      121 +  and QA never re-fetch the same cutout.                      
      122  - **Survey footprint pre-check**: verify RACS/Legacy Survey co
           verage for a position
      123    before querying, to fail fast/skip cleanly rather than get a
            blank image or timeout.
      124  - **Provenance**: record which survey/backend was actually use
           d for each source's
      125    optical and continuum image in the output catalogue.
      114 -- **Dry-run mode**: generate all validation plots (using cache
          -d/fetched cutouts) with                                       
      115 -  no interactive prompts, before the real QA pass — lets you s
          -anity-check plot quality                                      
      116 -  across the full sample first.                               
      126 +- **Dry-run and QA are fully decoupled stages, not one interle
          +aved loop.** This follows                                     
      127 +  directly from needing to run on HPC, where there's no displa
          +y and no interactive                                          
      128 +  input. Dry-run always uses the `Agg` backend, writes one PNG
          + per source plus a                                            
      129 +  small per-source metadata manifest (paths, provenance, catal
          +ogue row), and never                                          
      130 +  opens a display or blocks on input — it's the only stage tha
          +t needs to work                                               
      131 +  unattended on an HPC compute node. QA is a separate stage th
          +at reads the dry-run                                          
      132 +  manifest and PNGs and never regenerates cutouts or figures, 
          +so it can run anywhere                                        
      133 +  a display is available (e.g. your laptop, after syncing PNGs
          + down from HPC),                                              
      134 +  independent of where dry-run ran. This resolves the `Agg`/`p
          +lt.show()`/`input()`                                          
      135 +  conflict (issue #3) by removing the assumption entirely rath
          +er than patching it.                                          
      136  - **Resumable, incrementally-saved QA**: write each flag to di
           sk as it's made (not only
      118 -  at the end of the loop), so a session can be interrupted and
          - resumed. Optional                                            
      119 -  free-text comment field alongside the t/f/u/d flag; a "back"
          - option to correct a                                          
      120 -  mis-keyed flag without rerunning.                           
      137 +  at the end of the loop), so a session can be interrupted and
          + resumed on the same or                                       
      138 +  a different machine. Optional free-text comment field alongs
          +ide the t/f/u/d flag; a                                       
      139 +  "back" option to correct a mis-keyed flag without rerunning.
      140  - **Positional/velocity dedup**: replace exact-name-string mat
           ching with a spatial +
      141    velocity cross-match (reusing the existing `search_gama`-sty
           le logic), scoped per
      142    merge operation, never keyed on SoFiA's per-run `id`.

⏺ Update(PLAN.md)
  ⎿  Added 14 lines, removed 11 lines
      155  - **Tooling**: ruff/black + pre-commit; a minimal GitHub Actio
           ns CI running lint +
      156    fixture tests on push.
      157  
      158 -## 6. Open questions to resolve before/at phase 0             
      158 +## 6. Decisions (resolved 2026-07-30)                         
      159  
      160 -1. Package name (currently placeholder `hivalidate`).         
      161 -2. CLI framework: plain `argparse` (consistent with `rename_cu
          -belets.py` today) vs                                          
      162 -   `click`/`typer` for nicer multi-command UX.                
      163 -3. Config format: YAML vs TOML (leaning YAML — matches astrono
          -my-tooling convention).                                       
      164 -4. `astroquery.casda` auth: confirm whether the RACS continuum
          - products we need are                                         
      165 -   public/anonymous-accessible or require an OPAL login/token 
          -— affects whether the                                         
      166 -   continuum fallback needs credential handling.              
      167 -5. Where does `run_sofia/` (2.4 GB) live long-term — kept at r
          -epo root (gitignored) or                                      
      168 -   moved under `data/` for consistency with the other example 
          -data already there?                                           
      169 -6. License choice, if/when this is shared outside your own use
          -.                                                             
      160 +1. Package name: `hivalidate`.                                
      161 +2. CLI framework: `argparse`.                                 
      162 +3. Config format: YAML.                                       
      163 +4. `astroquery.casda` requires an OPAL login (confirmed:      
      164 +   https://astroquery.readthedocs.io/en/latest/casda/casda.htm
          +l) — handled                                                  
      165 +   non-interactively via env vars / gitignored credentials fil
          +e, see §5.                                                    
      166 +5. `run_sofia/` moves under `data/run_sofia/`, alongside `cont
          +inuum_image/` and                                             
      167 +   `output_validation_true/`.                                 
      168 +6. License: **BSD-3-Clause** (recommended) — matches the licen
          +se used by `astropy`                                          
      169 +   and most of the ecosystem this pipeline depends on (`astroq
          +uery`, `reproject`),                                          
      170 +   permissive enough for other DINGO/WALLABY team members to r
          +euse, and requires                                            
      171 +   attribution without restricting reuse. MIT would be an equa
          +lly reasonable simpler                                        
      172 +   alternative if preferred — flag if you'd rather switch.    
      173  
      174  ## 7. Explicit non-goals for v1
      175  

⏺ Now updating the phase-by-phase build sequence to match.

⏺ Update(PLAN.md)
  ⎿  Added 5 lines, removed 4 lines
      181  ## 8. Build sequence
      182  
      183  ### Phase 0 — Repo scaffolding
      184 -- [ ] `git init`, `.gitignore`, `LICENSE`                     
      185 -- [ ] Directory structure as in §4                            
      184 +- [ ] `git init`, `.gitignore` (incl. any local CASDA credenti
          +als file), `LICENSE`                                          
      185 +      (BSD-3-Clause)                                          
      186 +- [ ] Directory structure as in §4, with `run_sofia/` moved to
          + `data/run_sofia/`                                            
      187  - [ ] `pyproject.toml` + `environment.yml` (pin dependencies i
           ncl. `MontagePy`,
      188        `astropy`, `astroquery`, `reproject`, `matplotlib`, `num
           py`, `requests`)
      189  - [ ] `.pre-commit-config.yaml` (ruff/black), `.github/workflo
           ws/ci.yml`
      189 -- [ ] `README.md` skeleton, `REFERENCES.md` skeleton          
      190 +- [ ] `README.md` skeleton (incl. OPAL/CASDA account setup ins
          +tructions),                                                   
      191 +      `REFERENCES.md` skeleton                                
      192  - [ ] Extract the small `run_sofia_mini` fixture (2-3 runs) in
           to `tests/fixtures/`
      191 -- [ ] Resolve open questions in §6 (package name, CLI framewor
          -k, config format at minimum)                                  
      193  
      194  ### Phase 1 — Core science + catalogue layer
      195  - [ ] `config.py`: load/validate per-field YAML config

⏺ Update(PLAN.md)
  ⎿  Added 16 lines, removed 9 lines
      207  - [ ] `cutouts/optical.py`: SkyView backend (migrate existing)
           , Legacy Survey backend
      208        (migrate `download_legacy.py` logic)
      209  - [ ] `cutouts/continuum.py`: local-file backend (MontagePy `m
           Subimage`, using
      210 -      `data/continuum_image/`), RACS/CASDA backend (`astroquer
          -y.casda`)                                                     
      210 +      `data/continuum_image/`), RACS/CASDA backend (`astroquer
          +y.casda`) with                                                
      211 +      non-interactive login from env vars / gitignored credent
          +ials file                                                     
      212 +- [ ] Verify CASDA reachability from HPC compute nodes (vs log
          +in node only) before                                          
      213 +      relying on it inside a batch dry-run job                
      214  - [ ] Footprint/coverage pre-checks for both fallback chains
      215  - [ ] Provenance recording — fixes issue #2, addresses fallbac
           k + caching + footprint decisions
      216  
      214 -### Phase 3 — Plotting                                        
      217 +### Phase 3 — Plotting (dry-run, the HPC-safe stage)          
      218  - [ ] `plotting.py`: extract the six-panel figure builder from
            `validate_detections.py`
      216 -      into a pure function taking cutouts/catalogue row → figu
          -re                                                            
      217 -- [ ] Dry-run mode: batch-generate plots for all sources, no p
          -rompts                                                        
      218 -- [ ] Fix the `Agg`/`plt.show()`/`input()` bug (issue #3) — de
          -cide interactive backend                                      
      219 -      vs event-based key-press QA before wiring up phase 4    
      219 +      into a pure function taking cutouts/catalogue row → figu
          +re, always rendered on                                        
      220 +      `Agg` and saved to disk — no `plt.show()`, no prompts, s
          +afe inside an HPC batch job                                   
      221 +- [ ] Dry-run CLI: batch-generate PNGs for all sources plus a 
          +manifest (per-source                                          
      222 +      paths, provenance, catalogue row) that phase 4 consumes 
      223 +- [ ] Fault isolation per source (issue #8): one failed cutout
          +/plot logs and continues                                      
      224  
      221 -### Phase 4 — Interactive QA                                  
      222 -- [ ] `qa.py`: review loop over dry-run output, resumable, inc
          -remental per-source save                                      
      223 -      (fixes issue #7), fault isolation (issue #8), optional c
          -omment field, back option                                     
      225 +### Phase 4 — Interactive QA (runs locally, not on HPC)       
      226 +- [ ] `qa.py`: review loop over the dry-run manifest/PNGs only
          + — never regenerates                                          
      227 +      cutouts or figures, so it has no `Agg`/HPC constraint an
          +d can use a normal                                            
      228 +      interactive matplotlib backend or a simple image viewer 
      229 +- [ ] Resumable, incremental per-source save (fixes issue #7),
          + optional comment field,                                      
      230 +      back option                                             
      231  - [ ] Output catalogue gets qa flag + provenance + comment + r
           eproducibility metadata
      232  
      233  ### Phase 5 — Post-processing

⏺ Update(PLAN.md)
  ⎿  Added 6 lines, removed 3 lines
      252  - Pipeline runs end-to-end on `run_sofia/` via CLI, driven ent
           irely by a config file
      253    (no hardcoded per-field constants left in source).
      254  - Optical cutouts fall back SkyView → Legacy Survey; continuum
            falls back local file →
      255 -  RACS/CASDA; both cached and provenance-tracked.             
      256 -- Dry-run plots can be generated for the whole sample before a
          -ny interactive QA.                                            
      257 -- QA sessions are resumable and never lose progress on interru
          -ption.                                                        
      255 +  RACS/CASDA (non-interactive login); both cached and provenan
          +ce-tracked.                                                   
      256 +- Dry-run runs unattended on an HPC compute node (`Agg` only, 
          +no display, no                                                
      257 +  interactive prompts) and produces plots + manifest for the w
          +hole sample before any                                        
      258 +  QA happens.                                                 
      259 +- QA runs as a fully separate stage against the dry-run output
          + (no live cutout/figure                                       
      260 +  regeneration), is resumable, and never loses progress on int
          +erruption.                                                    
      261  - `tests/` pass in CI against the fixture; a full run against 
           `run_sofia/` has been
      262    done at least once and checked against `data/output_validati
           on_true/`.
      263  - Every function touching HI physics has a docstring citing `R
           EFERENCES.md`.

  Searched for 1 pattern, read 1 file (ctrl+o to expand)

⏺ The plan is fully updated and consistent throughout. Summary of what changed
  in PLAN.md:

  - §4 tree: run_sofia/ now nested under data/; package name confirmed as
  hivalidate.
  - §5 decisions: added the argparse CLI decision, a new CASDA-authentication
  design (non-interactive login via env vars/gitignored credentials file, plus a
  flagged open question about whether HPC compute nodes even have outbound
  internet), and rewrote the dry-run/QA design as two fully decoupled stages —
  dry-run is Agg-only and HPC-safe, QA reads only the saved PNGs/manifest and
  never touches a display-less environment. That's what resolves issue #3 for
  good rather than patching around it.
  - §6: converted from open questions to a dated decision log with your six
  answers, including the BSD-3-Clause recommendation (matches
  astropy/astroquery's own license, permissive, standard for this ecosystem —
  MIT flagged as the simpler alternative if you'd rather).
  - §3 issue table, §8 phases, §9 definition of done: updated to match — Phase 3
  is now explicitly "the HPC-safe stage," Phase 4 is explicitly "runs locally,
  not on HPC," Phase 2 gained CASDA credential/reachability tasks.

  One thing worth deciding before phase 0 actually starts: whether the
  RACS/CASDA fetch needs to be a separate network-enabled step from the Agg
  dry-run batch job, if your HPC's compute nodes don't have outbound internet —
  I flagged it in the plan as something to verify rather than assuming either
  way.

✻ Worked for 3m 31s

❯ Regarding RACS/CASDA fetch, my HPC compute node has outbound internet. But it 
  would be good to check if it works appropriately when the code starts.        

⏺ Update(PLAN.md)
  ⎿  Added 10 lines, removed 4 lines
      113    interactively prompts for credentials — it reads them from e
           nvironment variables
      114    (`CASDA_USERNAME`/`CASDA_PASSWORD`) or a local, gitignored c
           redentials file
      115    referenced from the field config, so the continuum RACS fall
           back can run unattended
      116 -  in an HPC batch job. Document OPAL account setup in `README.
          -md`. Open item to verify:                                     
      117 -  whether HPC compute nodes (as opposed to the login/head node
          -) have outbound internet                                      
      118 -  access at all — if not, the RACS fallback may need to run as
          - a separate,                                                  
      119 -  network-enabled step rather than inline with dry-run.       
      116 +  in an HPC batch job. Document OPAL account setup in `README.
          +md`. Confirmed: HPC                                           
      117 +  compute nodes have outbound internet access, so the RACS fal
          +lback runs inline with                                        
      118 +  dry-run — no separate network-enabled step needed.          
      119 +- **Preflight connectivity check**: before a dry-run batch sta
          +rts processing sources,                                       
      120 +  the pipeline does a cheap upfront check of every network-dep
          +endent backend in the                                         
      121 +  configured fallback chains — CASDA login + a trivial query, 
          +SkyView/Legacy Survey                                         
      122 +  reachability — and fails fast with a clear diagnostic if any
          + of them don't work.                                          
      123 +  This catches a broken CASDA login or a network/proxy issue o
          +n a given HPC node                                            
      124 +  before it silently degrades hundreds of sources to their fal
          +lback (or no) continuum                                       
      125 +  image mid-batch, rather than discovering it after the job fi
          +nishes.                                                       
      126  - **Cutout caching**: on-disk cache keyed by `(source name, su
           rvey, size)` so dry-run
      127    and QA never re-fetch the same cutout.
      128  - **Survey footprint pre-check**: verify RACS/Legacy Survey co
           verage for a position

⏺ Update(PLAN.md)
  ⎿  Added 3 lines, removed 2 lines
      215  - [ ] `cutouts/continuum.py`: local-file backend (MontagePy `m
           Subimage`, using
      216        `data/continuum_image/`), RACS/CASDA backend (`astroquer
           y.casda`) with
      217        non-interactive login from env vars / gitignored credent
           ials file
      218 -- [ ] Verify CASDA reachability from HPC compute nodes (vs log
          -in node only) before                                          
      219 -      relying on it inside a batch dry-run job                
      218 +- [ ] Preflight check: CASDA login + trivial query, SkyView/Le
          +gacy Survey reachability                                      
      219 +      — runs automatically at the start of `dry-run`, also ava
          +ilable standalone as                                          
      220 +      `hivalidate check-connectivity`; fails fast with a clear
          + diagnostic                                                   
      221  - [ ] Footprint/coverage pre-checks for both fallback chains
      222  - [ ] Provenance recording — fixes issue #2, addresses fallbac
           k + caching + footprint decisions
      223  

⏺ Update(PLAN.md)
  ⎿  Added 3 lines, removed 2 lines
      225  - [ ] `plotting.py`: extract the six-panel figure builder from
            `validate_detections.py`
      226        into a pure function taking cutouts/catalogue row → figu
           re, always rendered on
      227        `Agg` and saved to disk — no `plt.show()`, no prompts, s
           afe inside an HPC batch job
      228 -- [ ] Dry-run CLI: batch-generate PNGs for all sources plus a 
          -manifest (per-source                                          
      229 -      paths, provenance, catalogue row) that phase 4 consumes 
      228 +- [ ] Dry-run CLI: runs the preflight connectivity check first
          +, then batch-generates                                        
      229 +      PNGs for all sources plus a manifest (per-source paths, 
          +provenance, catalogue                                         
      230 +      row) that phase 4 consumes                              
      231  - [ ] Fault isolation per source (issue #8): one failed cutout
           /plot logs and continues
      232  
      233  ### Phase 4 — Interactive QA (runs locally, not on HPC)

⏺ Update(PLAN.md)
  ⎿  Added 3 lines
      266    QA happens.
      267  - QA runs as a fully separate stage against the dry-run output
            (no live cutout/figure
      268    regeneration), is resumable, and never loses progress on int
           erruption.
      269 +- A preflight connectivity/auth check (CASDA login + trivial q
          +uery, image-survey                                            
      270 +  reachability) runs automatically before dry-run starts proce
          +ssing sources, and                                            
      271 +  fails fast with a clear error if something's misconfigured. 
      272  - `tests/` pass in CI against the fixture; a full run against 
           `run_sofia/` has been
      273    done at least once and checked against `data/output_validati
           on_true/`.
      274  - Every function touching HI physics has a docstring citing `R
           EFERENCES.md`.

⏺ Updated PLAN.md: the HPC-internet open item is resolved (compute nodes have
  outbound access, so RACS/CASDA runs inline with dry-run, no separate network
  step needed), and in its place I added a preflight connectivity check — a
  cheap upfront CASDA login + trivial query plus SkyView/Legacy Survey
  reachability check that runs automatically at the start of dry-run (also
  exposed standalone as hivalidate check-connectivity), failing fast with a
  clear diagnostic rather than letting a broken login or network hiccup silently
  degrade continuum images across a few hundred sources before anyone notices.
  This is now reflected in §5 (design decision), Phase 2 and Phase 3 of the
  build sequence, and §9's definition of done.

✻ Churned for 44s

❯ Please execute the plan. Make the sensible decision for each choice.          

⏺ This is a large, multi-phase build. Let me set up task tracking first, then
  work through it phase by phase.
  Searched for 1 pattern, listed 1 directory, ran 3 shell commands (ctrl+o to expand)

⏺ Now moving run_sofia/ under data/, and the old flat scripts into legacy/ (kept
  for reference during migration, not deleted).

  Ran 3 shell commands (ctrl+o to expand)

⏺ Write(.gitignore)
  ⎿  Wrote 37 lines to .gitignore
       1 # --- Python ---
       2 __pycache__/
       3 *.py[cod]
       4 *.egg-info/
       5 .eggs/
       6 build/
       7 dist/
       8 .mypy_cache/
       9 .ruff_cache/
      10 .pytest_cache/
     … +30 lines (ctrl+o to expand)

⏺ I need to fix the .gitignore — the fixture data under tests/fixtures/ needs to
  be committed, but the blanket *.fits/*.png rules would exclude it too.

⏺ Update(.gitignore)
  ⎿  Added 4 lines, removed 1 line
      22  
      23  # --- Project data (large, regenerated, or field-specific) ---
      24  # Real survey/catalogue data, cutout downloads, and pipeline ou
          tputs never belong in
      25 -# git. tests/fixtures/ is the one deliberate exception (small, 
         -curated, versioned).                                           
      25 +# git. tests/fixtures/ is the one deliberate exception (small, 
         +curated, versioned) --                                         
      26 +# see the negated rules below.                                 
      27  /data/
      28  /output_validation*/
      29  /cutout_cache/
      30  *.fits
      31  *.png
      32 +!tests/fixtures/**/*.fits                                      
      33 +!tests/fixtures/**/*.png                                       
      34  !docs/**/*.png
      35  
      36  # --- Credentials ---

⏺ Write(LICENSE)
  ⎿  Wrote 29 lines to LICENSE
       1 BSD 3-Clause License
       2 
       4 All rights reserved.
       5 
       6 Redistribution and use in source and binary forms, with or witho
       7 modification, are permitted provided that the following conditio
         ns are met:
       8 
         t notice, this
      10    list of conditions and the following disclaimer.
     … +33 lines (ctrl+o to expand)

⏺ Write(pyproject.toml)
  ⎿  Wrote 56 lines to pyproject.toml
       1 [build-system]
       2 requires = ["setuptools>=68", "wheel"]
       3 build-backend = "setuptools.build_meta"
       4 
       5 [project]
       7 version = "0.1.0.dev0"
       8 description = "Validation pipeline for SoFiA HI source-finding o
         utput (DINGO/WALLABY-style ASKAP surveys)."
       9 readme = "README.md"
      10 license = { file = "LICENSE" }
     … +50 lines (ctrl+o to expand)

⏺ Write(environment.yml)
  ⎿  Wrote 28 lines to environment.yml
       1 # Conda environment for hivalidate.
       2 #
       4 # Update with:   conda env update -f environment.yml --prune
       5 #
       6 # MontagePy ships prebuilt wheels on PyPI (https://github.com/Ca
       7 # but wheel availability varies by platform/Python version -- if
          the pip install step
       8 # fails on a new machine, check that a wheel exists for your Pyt
       9 # before assuming something else is wrong.
      10 name: hivalidate
     … +21 lines (ctrl+o to expand)

⏺ Now the pre-commit config and CI workflow.

⏺ Write(.pre-commit-config.yaml)
  ⎿  Wrote 15 lines to .pre-commit-config.yaml
       1 repos:
       2   - repo: https://github.com/astral-sh/ruff-pre-commit
       3     rev: v0.6.9
       4     hooks:
       5       - id: ruff
       6         args: [--fix]
       7       - id: ruff-format
       8   - repo: https://github.com/pre-commit/pre-commit-hooks
       9     rev: v4.6.0
      10     hooks:
     … +5 lines (ctrl+o to expand)
  Searched for 1 pattern (ctrl+o to expand)

⏺ Write(.github/workflows/ci.yml)
  ⎿  Wrote 29 lines to .github/workflows/ci.yml
       1 name: CI
       2 
       3 on:
       4   push:
       5     branches: [main]
       6   pull_request:
       7 
       8 jobs:
       9   lint-and-test:
      10     runs-on: ubuntu-latest
     … +22 lines (ctrl+o to expand)

⏺ Update(.github/workflows/ci.yml)
  ⎿  Added 3 lines, removed 2 lines
      24        - name: Lint (ruff)
      25          run: ruff check src tests
      26  
      27 -      - name: Test (pytest, fixture data only -- see PLAN.md Ph
         -ase 6 for the                                                  
      28 -          separate full run_sofia/ validation pass)            
      27 +      # Runs against tests/fixtures/ only. The full run_sofia/ 
         +end-to-end pass                                                
      28 +      # (PLAN.md Phase 6) is a separate, manually-triggered, ne
         +twork-dependent run.                                           
      29 +      - name: Test (pytest)                                    
      30          run: pytest -v

⏺ Write(REFERENCES.md)
  ⎿  Wrote 35 lines to REFERENCES.md
       1 # References
       3 Bibliography for the science and external services encoded in `h
         ivalidate`. Code
         g. `[SoFiA2]`) instead
         ou add a citation to
       6 the code; keep keys stable once used since they're referenced fr
       7 
       8 Entries below marked with the exact formula/constant they suppor
       9 against the source during Phase 1 implementation, not assumed fr
      10 scripts being migrated.
     … +44 lines (ctrl+o to expand)

⏺ Write(README.md)
  ⎿  Wrote 73 lines to README.md
       1 # hivalidate
       3 Validation pipeline for [SoFiA 2](https://github.com/SoFiA-Admin
         /SoFiA-2) HI
         O/WALLABY-style data).
         ion, deduplication,
       6 renaming, dry-run plot generation, interactive quality assessmen
       7 into a validated source catalogue.
       8 
          sequence, and
         tage-by-stage
     … +90 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(.gitignore)
  ⎿  Added 3 lines
      20  *.swo
      21  .DS_Store
      22  
      23 +# --- Local tooling config (personal, not shared) ---          
      24 +.claude/settings.local.json                                    
      25 +                                                               
      26  # --- Project data (large, regenerated, or field-specific) ---
      27  # Real survey/catalogue data, cutout downloads, and pipeline ou
          tputs never belong in
      28  # git. tests/fixtures/ is the one deliberate exception (small, 
          curated, versioned) --

  Ran 1 shell command (ctrl+o to expand)

⏺ All staged cleanly (458 files, no unexpected modifications), .git is a lean
  8.4 MB. Committing the initial scaffold.

  Ran 1 shell command (ctrl+o to expand)

⏺ Good — git config resolved the author as Jonghwan Rhee 
  <jonghwan.rhee@uwa.edu.au>, so I can fill in the copyright holder properly
  instead of leaving a placeholder.

⏺ Update(LICENSE)
  ⎿  Added 1 line, removed 1 line
      1  BSD 3-Clause License
      2  
      3 -Copyright (c) 2026, <COPYRIGHT HOLDER>                          
      3 +Copyright (c) 2026, Jonghwan Rhee                               
      4  All rights reserved.
      5  
      6  Redistribution and use in source and binary forms, with or witho
         ut

⏺ Update(pyproject.toml)
  ⎿  Added 1 line, removed 1 line
      10  license = { file = "LICENSE" }
      11  requires-python = ">=3.10"
      12  authors = [
      13 -    { name = "<COPYRIGHT HOLDER>" },                           
      13 +    { name = "Jonghwan Rhee", email = "jonghwan.rhee@uwa.edu.au
         +" },                                                           
      14  ]
      15  
      16  # Kept in sync with environment.yml. MontagePy ships prebuilt w
          heels but wheel

  Ran 1 shell command (ctrl+o to expand)

⏺ Before writing conversions.py, I want to verify the exact literature source
  for the HI mass and column-density formulas already encoded in the legacy
  script, rather than guessing citations.

⏺ Web Search("HI mass formula 2.356e5 luminosity distance integrated flux
            Roberts 1962 Meyer")
  ⎿  Did 1 search in 8s

⏺ Web Search("HI column density formula 2.33e20 (1+z)^4 beam flux radio
            interferometry")
  ⎿  Did 1 search in 11s
⏺ Web Search("WALLABY column density sensitivity limit formula 2.33 10^20
            (1+z)^4 beam Westmeier Meyer")
  ⎿  Did 1 search in 6s

⏺ Web Search("Meyer Robotham Obreschkow 2017 PASA HI mass 2.356e5 luminosity
            distance paper title")
  ⎿  Did 1 search in 6s

⏺ Web Search("Walter 2008 THINGS HI column density formula 1.104e21 beam arcsec
            Jy/beam km/s moment zero")
  ⎿  Did 4 searches in 17s

⏺ Update(REFERENCES.md)
  ⎿  Added 40 lines, removed 5 lines
      27  - **[CASDA]** CSIRO ASKAP Science Data Archive, accessed via `a
          stroquery.casda`
      28    (requires an OPAL account): https://astroquery.readthedocs.io
          /en/latest/casda/casda.html
      29  
      30 -## Physical conversions (filled in during Phase 1 -- conversion
         -s.py)                                                          
      30 +## Physical conversions                                        
      31  
      32 -- **[HImass]** TBD -- verify against literature before finalizi
         -ng; see                                                        
      33 -  `src/hivalidate/conversions.py` docstrings for the equation a
         -s implemented.                                                 
      34 -- **[ColumnDensity]** TBD -- verify against literature before f
         -inalizing; see                                                 
      35 -  `src/hivalidate/conversions.py` docstrings for the equation a
         -s implemented.                                                 
      32 +- **[Meyer2017]** Meyer, M. J., Robotham, A. S. G., Obreschkow,
         + D., et al. 2017,                                              
      33 +  "Tracing HI Beyond the Local Universe", PASA, 34, e052 (arXiv
         +:1705.04210). Source                                           
      34 +  of the HI mass relation                                      
      35 +  `M_HI/Msun = (2.356e5 / (1+z)) * (D_L/Mpc)^2 * (S / Jy km/s)`
         +,                                                              
      36 +  verified by web search against the published equation on 2026
         +-07-30. Used in                                                
      37 +  `conversions.hi_mass()`.                                     
      38 +- **[Walter2008]** Walter, F., Brinks, E., de Blok, W. J. G., e
         +t al. 2008, "THINGS:                                           
      39 +  The HI Nearby Galaxy Survey", AJ, 136, 2563. Source of the fu
         +ndamental optically-thin                                       
      40 +  21cm column-density relation `N_HI [cm^-2] = 1.823e18 * integ
         +ral(T_B dv [K km/s])`,                                         
      41 +  the physical basis for `conversions.column_density()`.       
      42 +- **Radio/optical velocity convention**: standard definitions  
      43 +  `v_opt = c(f0/f - 1)`, `v_radio = c(1 - f/f0)`; see e.g. Rohl
         +fs & Wilson, *Tools of                                         
      44 +  Radio Astronomy* (Springer), section on spectral line kinemat
         +ics. Textbook-standard,                                        
      45 +  not independently re-verified by literature search.          
      46 +                                                               
      47 +### Known caveat -- flag before treating column density as scie
         +nce-final                                                      
      48 +                                                               
      49 +`conversions.column_density()` implements `N_HI = 2.33e20 * (1+
         +z)^4 * S / beam`,                                              
      50 +carried over unchanged from the pre-refactor script (`legacy/va
         +lidate_detections.py`).                                        
      51 +This has the correct *functional form* for converting an observ
         +er-frame, per-pixel                                            
      52 +moment-0 flux (in Jy/beam Hz, appropriate for SoFiA's frequency
         +-axis moment maps) to a                                        
      53 +column density with cosmological surface-brightness dimming -- 
         +consistent with the                                            
      54 +column-density-sensitivity relations quoted in WALLABY survey p
         +apers built on                                                 
      55 +[Meyer2017]-style pipelines. However, the exact numeric constan
         +t `2.33e20` was **not**                                        
      56 +independently re-derived bit-for-bit against a specific publish
         +ed equation during this                                        
      57 +refactor (unlike the HI mass constant, which was checked and co
         +rrected -- see below).                                         
      58 +Treat it as inherited-and-plausible, not verified, until someon
         +e re-derives it from                                           
      59 +first principles for this pipeline's specific beam/flux unit co
         +nvention.                                                      
      60 +                                                               
      61 +### Bug found and fixed during this refactor                   
      62 +                                                               
      63 +The pre-refactor script's frequency-rest-frame HI mass branch (
         +`himass(..., rest_frame='frequency')`,                         
      64 +the only branch actually used in practice) was missing the `1/(
         +1+z)` cosmological                                             
      65 +correction present in [Meyer2017] and in the script's own (unus
         +ed) velocity-rest-frame                                        
      66 +branch. Checked numerically: `2.356e5 * (c / f_HI)` = 49.7, con
         +firming the frequency-domain                                   
      67 +constant `49.7` is [Meyer2017]'s formula re-expressed for `S` i
         +n Jy Hz rather than                                            
      68 +Jy km/s -- but the `1/(1+z)` term should still apply and didn't
         +. `conversions.hi_mass()`                                      
      69 +includes it. At DINGO/WALLABY-pilot redshifts (z ~ 0.01-0.1) th
         +is is roughly a 1-10%                                          
      70 +effect on every reported HI mass in the legacy pipeline's outpu
         +t catalogues.                                                  

⏺ Write(src/hivalidate/conversions.py)
  ⎿  Wrote 161 lines to src/hivalidate/conversions.py
       1 """Physical conversions for HI spectral-line data.
       3 Every non-trivial constant or equation here is cited by short ke
         y (e.g. ``[Meyer2017]``)
         look there for the full
          numbers in a paper:
       6 a bug found and fixed in the HI mass formula during this refacto
       7 constant that was carried over from the legacy script without in
         dependent verification.
       9 All functions are pure (no I/O, no global state) so they can be 
      10 against known values.
     … +202 lines (ctrl+o to expand)

⏺ Write(src/hivalidate/__init__.py)
  ⎿  Wrote 3 lines to src/hivalidate/__init__.py
      1 """hivalidate: validation pipeline for SoFiA HI source-finding ou
        tput."""
      2 
      3 __version__ = "0.1.0.dev0"

⏺ Write(src/hivalidate/cli/__init__.py)
  ⎿  Wrote 1 line to src/hivalidate/cli/__init__.py
      1 (No content)

⏺ Write(src/hivalidate/cutouts/__init__.py)
  ⎿  Wrote 1 line to src/hivalidate/cutouts/__init__.py
      1 (No content)

⏺ Now tests/__init__.py-free pytest setup and the conversions test, then install
  the package editable and run it.

⏺ Write(tests/test_conversions.py)
  ⎿  Wrote 131 lines to tests/test_conversions.py
      1 """Unit tests for hivalidate.conversions.
      2 
      3 Reference values are computed independently (not copy-pasted from
         the implementation)
      4 so a bug in both the code and the test's derivation is unlikely t
      5 """
      6 
      7 import numpy as np
      8 import pytest
      9 from astropy.cosmology import FlatLambdaCDM
     … +152 lines (ctrl+o to expand)

⏺ Now let's install the package (editable, in the base conda env which already
  has everything) and run the tests.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Fixing the version pin to match reality (2.3.x, not 6.0).

⏺ Update(pyproject.toml)
  ⎿  Added 1 line, removed 1 line
      18  dependencies = [
      19      "astropy>=6.0",
      20      "astroquery>=0.4.7",
      21 -    "MontagePy>=6.0",                                          
      21 +    "MontagePy>=2.3",                                          
      22      "reproject>=0.13",
      23      "matplotlib>=3.8",
      24      "numpy>=1.26",

⏺ Update(environment.yml)
  ⎿  Added 1 line, removed 1 line
      24    - pre-commit>=3.7
      25    - pip
      26    - pip:
      27 -      - MontagePy>=6.0                                         
      27 +      - MontagePy>=2.3                                         
      28        - -e .

  Ran 1 shell command (ctrl+o to expand)

⏺ Package installs cleanly. Now running the conversions test suite.

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ Write(src/hivalidate/config.py)
  ⎿  Wrote 161 lines to src/hivalidate/config.py
       1 """Per-field/SB configuration.
       3 Every hivalidate CLI stage takes ``--config path/to/field.yaml``
          instead of reading
         in PLAN.md section 3
         ent field/SB's paths
       6 as module-level constants.
       8 Functions in the rest of the package take plain arguments (paths
         , numbers, arrays),
          reads a `Config` and
         he science/IO modules
     … +186 lines (ctrl+o to expand)
⏺ Write(configs/SB82605.yaml)
  ⎿  Wrote 32 lines to configs/SB82605.yaml
       1 # Example field/SB config, matching the real example data in dat
         a/run_sofia/ and
         tory unless absolute.
       3 #
       4 # Used for the Phase 6 full end-to-end validation run against al
       5 
       6 field_name: SB82605
       7 
       9   raw_sofia_dir: ../data/run_sofia
      10   work_dir: ../data/work/SB82605
     … +27 lines (ctrl+o to expand)

⏺ Now the fixture config for tests, and test_config.py.

⏺ Write(tests/fixtures/config_mini.yaml)
  ⎿  Wrote 15 lines to tests/fixtures/config_mini.yaml
       1 # Config pointing at the small tests/fixtures/run_sofia_mini/ da
         taset (3 real runs)
       2 # used by fast unit/integration tests. Mirrors configs/SB82605.y
       3 
       4 field_name: SB82605_mini
       5 
       6 paths:
       8   work_dir: work
       9   continuum_local_dir: null
      10   gama_catalogue: null
     … +7 lines (ctrl+o to expand)

⏺ Write(tests/test_config.py)
  ⎿  Wrote 49 lines to tests/test_config.py
       1 from pathlib import Path
       2 
       3 import pytest
       4 
       5 from hivalidate.config import Config
       6 
       7 FIXTURES = Path(__file__).parent / "fixtures"
       8 
       9 
      10 def test_loads_example_field_config():
     … +44 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ For a real duplicate-detection test, I'll extend the fixture with runs
  011/012, which contain a genuine cross-run duplicate (SoFiA 
  J204524.82-550222.5) found during the original audit.

  Ran 1 shell command (ctrl+o to expand)

⏺ Confirmed — 28MB fixture, 5 runs, with a genuine duplicate pair for a
  true-positive dedup test. Now writing catalogue.py.

⏺ Write(src/hivalidate/catalogue.py)
  ⎿  Wrote 219 lines to src/hivalidate/catalogue.py
       1 """SoFiA catalogue I/O, multi-run combination, deduplication, an
       2 
         ues each one had):
       4 
         logues` + `combine_runs`
         eduplicate_positional`
       8 - ``legacy/rename_cubelets.py`` (per-run ID -> name mapping) -> 
         `id_to_name_mapping`
         -- SoFiA's `id` column
         catalogue + cubelets
     … +266 lines (ctrl+o to expand)

  Ran 2 shell commands (ctrl+o to expand)

⏺ Write(tests/test_catalogue.py)
  ⎿  Wrote 129 lines to tests/test_catalogue.py
       1 from pathlib import Path
       2 
       4 
       5 from hivalidate import catalogue
       6 
         ni"
       8 
       9 # Row counts independently verified against each run's plain-tex
      10 # (`grep -vc '^#' *_cat.txt`), not read out of the XML the code 
         under test also reads.
     … +136 lines (ctrl+o to expand)

  Ran 2 shell commands (ctrl+o to expand)

⏺ My ground-truth row counts came from grep -vc '^#' on the .txt catalogues,
  which counts a blank header line as a row — off by one per run. The XML
  parsing is correct; fixing the test's ground truth.

⏺ Update(tests/test_catalogue.py)
  ⎿  Added 5 lines, removed 3 lines
       6  
       7  FIXTURE_DIR = Path(__file__).parent / "fixtures" / "run_sofia_m
          ini"
       8  
       9 -# Row counts independently verified against each run's plain-te
         -xt catalogue                                                   
      10 -# (`grep -vc '^#' *_cat.txt`), not read out of the XML the code
         - under test also reads.                                        
      11 -EXPECTED_ROWS_PER_RUN = {"001": 11, "002": 12, "003": 13, "011"
         -: 11, "012": 14}                                               
       9 +# Row counts verified directly against each run's XML (`len(par
         +se_single_table(...))`),                                       
      10 +# not derived from the code under test. Note: `grep -vc '^#' *_
         +cat.txt` overcounts by                                         
      11 +# one per run -- SoFiA's plain-text catalogue has a blank (non-
         +'#') line in its header                                        
      12 +# block, which is not a data row.                              
      13 +EXPECTED_ROWS_PER_RUN = {"001": 10, "002": 11, "003": 12, "011"
         +: 10, "012": 13}                                               
      14  
      15  
      16  def test_find_run_catalogues_finds_all_fixture_runs():

  Ran 3 shell commands (ctrl+o to expand)

⏺ Update(tests/test_catalogue.py)
  ⎿  Added 31 lines, removed 4 lines
       66      assert kept_row["snr"][0] == better_snr
       67  
       68  
       69 -def test_deduplicate_positional_does_not_touch_unique_sources(
          -):                                                            
       69 +def test_deduplicate_positional_leaves_no_remaining_duplicate_
          +pairs():                                                      
       70 +    # General invariant, not a magic row count: after dedup, n
          +o two surviving rows                                          
       71 +    # should still match each other under the same spatial+vel
          +ocity criteria used to                                        
       72 +    # find duplicates in the first place. (Discovered while wr
          +iting this test: this                                         
       73 +    # 5-run fixture has 14 near-duplicate pairs/clusters, not 
          +just the one exact-name                                       
       74 +    # match found by the legacy string-matching script -- adja
          +cent SoFiA runs                                               
       75 +    # frequently redetect the same source with a slightly diff
          +erent fitted centroid,                                        
       76 +    # which is exactly the gap positional dedup is meant to cl
          +ose.)                                                         
       77      paths = catalogue.find_run_catalogues(FIXTURE_DIR)
       78      combined = catalogue.combine_runs(paths)
       79      result = catalogue.deduplicate_positional(combined)
       73 -    # Exactly one known duplicate pair in this fixture (see te
          -st above) -> exactly one                                      
       74 -    # row removed, everything else untouched.                 
       75 -    assert len(result.table) == len(combined) - 1             
       80 +    assert result.n_removed > 0  # this fixture is known to co
          +ntain duplicates                                              
       81  
       82 +    reresult = catalogue.deduplicate_positional(result.table) 
       83 +    assert reresult.n_removed == 0, (                         
       84 +        f"deduplicating an already-deduplicated table should b
          +e a no-op, "                                                  
       85 +        f"but it removed {reresult.removed_names}"            
       86 +    )                                                         
       87  
       88 +                                                              
       89 +def test_deduplicate_positional_only_merges_sources_with_consi
          +stent_velocity():                                             
       90 +    # Spot check against a manually-verified triplet: three ro
          +ws within ~9 arcsec of                                        
       91 +    # each other (well inside a single ASKAP beam) and within 
          +~2 km/s in velocity --                                        
       92 +    # unambiguously the same physical source detected three ti
          +mes.                                                          
       93 +    paths = catalogue.find_run_catalogues(FIXTURE_DIR)        
       94 +    combined = catalogue.combine_runs(paths)                  
       95 +    triplet = {                                               
       96 +        "SoFiA J205935.85-550418.3",                          
       97 +        "SoFiA J205934.86-550420.7",                          
       98 +        "SoFiA J205934.81-550420.7",                          
       99 +    }                                                         
      100 +    result = catalogue.deduplicate_positional(combined)       
      101 +    surviving = set(result.table["name"]) & triplet           
      102 +    assert len(surviving) == 1                                
      103 +                                                              
      104 +                                                              
      105  def test_deduplicate_positional_on_empty_table_is_a_no_op():
      106      paths = catalogue.find_run_catalogues(FIXTURE_DIR)
      107      combined = catalogue.combine_runs(paths)

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/catalogue.py)
  ⎿  Added 8 lines
      178      cubelets_dir: str | Path,
      179      output_dir: str | Path,
      180      dry_run: bool = False,
      181 +    keep_names: set[str] | None = None,                       
      182  ) -> int:
      183      """Copy every file in a run's cubelets directory to `outpu
           t_dir`, renaming the
      184      leading ``<field>_<run>_<id>_`` to ``<name>_`` using that 
           run's own catalogue for
     ...
      186      `process_renaming`, reimplemented on top of `id_to_name_ma
           pping` instead of raw
      187      ElementTree parsing.
      188  
      189 +    `keep_names`, if given, restricts copying to sources whose
          + (space-replaced-by-                                          
      190 +    underscore) name is in the set -- pass the surviving names
          + from                                                         
      191 +    `deduplicate_positional`'s output so duplicate detections 
          +dropped from the                                              
      192 +    catalogue don't still end up with cubelet files in the com
          +bined output directory.                                       
      193 +    Names are matched per-run (via that run's own `id_to_name_
          +mapping`), so this stays                                      
      194 +    correct even though SoFiA's `id` column is not run-unique 
          +(PLAN.md issue #6).                                           
      195 +                                                              
      196      Returns the number of files copied (or that would be copie
           d, if `dry_run=True`).
      197      """
      198      catalogue_path = Path(catalogue_path)

⏺ Update(src/hivalidate/catalogue.py)
  ⎿  Added 4 lines, removed 1 line
      219          source_id, suffix = parts
      220          if source_id not in mapping:
      221              continue
      222 -        new_name = f"{mapping[source_id]}_{suffix}"           
      222 +        name = mapping[source_id]                             
      223 +        if keep_names is not None and name not in keep_names: 
      224 +            continue                                          
      225 +        new_name = f"{name}_{suffix}"                         
      226          if not dry_run:
      227              shutil.copy2(source_path, output_dir / new_name)
      228          count += 1
⏺ Update(tests/test_catalogue.py)
  ⎿  Added 15 lines
      146      assert not any("Removal_001_1_" in name for name in rename
           d)
      147  
      148  
      149 +def test_rename_and_copy_cubelets_respects_keep_names_filter(t
          +mp_path):                                                     
      150 +    output_dir = tmp_path / "renamed"                         
      151 +    # Keep only one of the eleven sources in run 001.         
      152 +    count = catalogue.rename_and_copy_cubelets(               
      153 +        FIXTURE_DIR / "SB82605_Removal_001_cat.xml",          
      154 +        FIXTURE_DIR / "SB82605_Removal_001_cubelets",         
      155 +        output_dir,                                           
      156 +        keep_names={"SoFiA_J210149.89-554804.6"},             
      157 +    )                                                         
      158 +    renamed = sorted(p.name for p in output_dir.iterdir())    
      159 +    assert count == len(renamed)                              
      160 +    assert all(name.startswith("SoFiA_J210149.89-554804.6_") f
          +or name in renamed)                                           
      161 +    assert "SoFiA_J210029.15-545824.9_mom0.fits" not in rename
          +d                                                             
      162 +                                                              
      163 +                                                              
      164  def test_rename_and_copy_cubelets_preserves_file_content(tmp_p
           ath):
      165      output_dir = tmp_path / "renamed"
      166      catalogue.rename_and_copy_cubelets(

  Ran 1 shell command (ctrl+o to expand)

⏺ Now the three CLI stages for Phase 1: combine, dedup, rename.

⏺ Write(src/hivalidate/cli/_common.py)
  ⎿  Wrote 22 lines to src/hivalidate/cli/_common.py
       1 """Shared argument-parsing helpers for hivalidate CLI stages."""
       2 
       3 from __future__ import annotations
       4 
       5 import argparse
       6 import logging
       7 
       8 
       9 def base_parser(description: str) -> argparse.ArgumentParser:
      10     parser = argparse.ArgumentParser(description=description)
     … +15 lines (ctrl+o to expand)

⏺ Write(src/hivalidate/cli/combine.py)
  ⎿  Wrote 44 lines to src/hivalidate/cli/combine.py
      1 """Combine every per-run SoFiA catalogue in a field into one VOTa
        ble.
      3 Replaces the combine step of ``legacy/plot_detections.py``. Does 
        not plot anything --
      4 the legacy script's frequency-vs-flux QA plot may return as a sma
      5 diagnostic later, but combining catalogues and eyeballing a plot 
        are different
      6 concerns and shouldn't share a script.
      8 
      9 from __future__ import annotations
     … +42 lines (ctrl+o to expand)

⏺ Write(src/hivalidate/cli/dedup.py)
  ⎿  Wrote 51 lines to src/hivalidate/cli/dedup.py
       1 """Deduplicate a combined SoFiA catalogue by spatial + velocity 
         cross-match.
       2 
         hing (PLAN.md
       4 issue #5). Run `hivalidate-combine` first.
       5 """
       6 
       8 
       9 import logging
      10 import sys
     … +48 lines (ctrl+o to expand)

⏺ Write(src/hivalidate/cli/rename.py)
  ⎿  Wrote 62 lines to src/hivalidate/cli/rename.py
       1 """Rename and copy per-run cubelets into one combined directory,
       2 
         s.sh``. Fixes PLAN.md
       4 issue #1 (the shell wrapper's glob pattern didn't match the actu
       5 naming) by using `hivalidate.catalogue.find_run_catalogues` agai
       6 `raw_sofia_dir`, and issue #6 by mapping IDs to names per-run (n
       7 catalogue -- SoFiA's `id` column is not run-unique).
       8 
         ` -- run
         detections don't get
     … +68 lines (ctrl+o to expand)

⏺ Write(tests/test_pipeline_e2e.py)
  ⎿  Wrote 80 lines to tests/test_pipeline_e2e.py
       1 """End-to-end test of the Phase 1 pipeline (combine -> dedup -> 
         rename) against the
         s directly (not via
       3 subprocess) so failures show a normal Python traceback, but othe
         rwise drives them
       5 """
       6 
       7 from pathlib import Path
       9 from hivalidate import catalogue
      10 from hivalidate.cli import combine, dedup, rename
     … +88 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ Found a real edge case: when two duplicate rows share the exact same
  SoFiA-generated name (both point to identical filenames), name-based filtering
  can't tell which run's cubelets should actually survive. Let me fix this
  properly by tracking (run, id) provenance through combine/dedup instead of
  filtering by name string alone.

⏺ Update(src/hivalidate/catalogue.py)
  ⎿  Added 16 lines, removed 3 lines
      51  
      52      Does not deduplicate -- call `deduplicate_positional` on th
          e result if the input
      53      runs can overlap spatially (true for adjacent SoFiA sub-cub
          e runs; see PLAN.md
      54 -    issue #5). Does not touch `id` -- see the module docstring 
         -on why IDs must not be                                         
      55 -    trusted once catalogues are combined.                      
      54 +    issue #5).                                                 
      55 +                                                               
      56 +    Adds a `source_run` column (the catalogue's filename, minus
         + ``_cat.xml``) to every                                        
      57 +    row before stacking. This is what lets `rename_and_copy_cub
         +elets` later identify                                          
      58 +    *exactly* which run+id a surviving row came from, rather th
         +an matching on `name`                                          
      59 +    alone -- necessary because two independent duplicate detect
         +ions can occasionally                                          
      60 +    produce the exact same SoFiA-generated name string (both ro
         +und to the same                                                
      61 +    hh:mm:ss.s / dd:mm:ss.s), which would otherwise make it imp
         +ossible to tell which                                          
      62 +    run's cubelets should be kept after dedup drops one of the 
         +two rows. `id` itself is                                       
      63 +    still not safe to use directly once combined -- it resets t
         +o 1..N per run -- but                                          
      64 +    `(source_run, id)` together are a unique key.              
      65      """
      66      if not catalogue_paths:
      67          raise ValueError("No catalogue paths given to combine")
      59 -    tables = [read_votable(p) for p in catalogue_paths]        
      68 +    tables = []                                                
      69 +    for p in catalogue_paths:                                  
      70 +        table = read_votable(p)                                
      71 +        table["source_run"] = Path(p).name.removesuffix("_cat.x
         +ml")                                                           
      72 +        tables.append(table)                                   
      73      combined = tables[0] if len(tables) == 1 else vstack(tables
          )
      74      combined.sort("ra")
      75      return combined

⏺ Update(src/hivalidate/catalogue.py)
  ⎿  Added 12 lines, removed 9 lines
      191      cubelets_dir: str | Path,
      192      output_dir: str | Path,
      193      dry_run: bool = False,
      194 -    keep_names: set[str] | None = None,                       
      194 +    keep_keys: set[tuple[str, str]] | None = None,            
      195  ) -> int:
      196      """Copy every file in a run's cubelets directory to `outpu
           t_dir`, renaming the
      197      leading ``<field>_<run>_<id>_`` to ``<name>_`` using that 
           run's own catalogue for
     ...
      199      `process_renaming`, reimplemented on top of `id_to_name_ma
           pping` instead of raw
      200      ElementTree parsing.
      201  
      202 -    `keep_names`, if given, restricts copying to sources whose
          - (space-replaced-by-                                          
      203 -    underscore) name is in the set -- pass the surviving names
          - from                                                         
      204 -    `deduplicate_positional`'s output so duplicate detections 
          -dropped from the                                              
      202 +    `keep_keys`, if given, restricts copying to `(source_run, 
          +id)` pairs in the set --                                      
      203 +    pass keys built from `deduplicate_positional`'s surviving 
          +rows (using the                                               
      204 +    `source_run` column `combine_runs` adds) so duplicate dete
          +ctions dropped from the                                       
      205      catalogue don't still end up with cubelet files in the com
           bined output directory.
      206 -    Names are matched per-run (via that run's own `id_to_name_
          -mapping`), so this stays                                      
      207 -    correct even though SoFiA's `id` column is not run-unique 
          -(PLAN.md issue #6).                                           
      206 +    This is deliberately keyed on `(source_run, id)` rather th
          +an `name`: two                                                
      207 +    independent duplicate detections can occasionally produce 
          +the exact same                                                
      208 +    SoFiA-generated name string, which would make a name-only 
          +filter unable to tell                                         
      209 +    which run's cubelets to keep -- `(source_run, id)` is alwa
          +ys unique.                                                    
      210 +    `source_run` for this function is `catalogue_path`'s own f
          +ilename (minus                                                
      211 +    ``_cat.xml``), matching what `combine_runs` stores.       
      212  
      213      Returns the number of files copied (or that would be copie
           d, if `dry_run=True`).
      214      """
     ...
      236          source_id, suffix = parts
      237          if source_id not in mapping:
      238              continue
      235 -        name = mapping[source_id]                             
      236 -        if keep_names is not None and name not in keep_names: 
      239 +        if keep_keys is not None and (base_prefix, source_id) 
          +not in keep_keys:                                             
      240              continue
      238 -        new_name = f"{name}_{suffix}"                         
      241 +        new_name = f"{mapping[source_id]}_{suffix}"           
      242          if not dry_run:
      243              shutil.copy2(source_path, output_dir / new_name)
      244          count += 1

⏺ Now updating rename.py CLI to build keep_keys from the deduped table's
  source_run/id columns instead of names.

⏺ Update(src/hivalidate/cli/rename.py)
  ⎿  Added 11 lines, removed 3 lines
      30          )
      31  
      32      deduped = catalogue.read_votable(config.paths.deduped_catal
          ogue)
      33 -    keep_names = {str(name).replace(" ", "_") for name in dedup
         -ed["name"]}                                                    
      34 -    logger.info("%d sources survived dedup and will get renamed
         - cubelets", len(keep_names))                                   
      33 +    if "source_run" not in deduped.colnames:                   
      34 +        raise SystemExit(                                      
      35 +            f"{config.paths.deduped_catalogue} has no 'source_r
         +un' column -- it must be "                                     
      36 +            "produced by hivalidate-combine (which adds provena
         +nce) followed by "                                             
      37 +            "hivalidate-dedup, not hand-assembled"             
      38 +        )                                                      
      39 +    keep_keys = {                                              
      40 +        (str(run), str(source_id)) for run, source_id in zip(de
         +duped["source_run"], deduped["id"])                            
      41 +    }                                                          
      42 +    logger.info("%d sources survived dedup and will get renamed
         + cubelets", len(keep_keys))                                    
      43  
      44      run_catalogues = catalogue.find_run_catalogues(config.paths
          .raw_sofia_dir)
      45      total_copied = 0
     ...
      50              logger.warning("No cubelets directory for %s (expec
          ted %s) -- skipping", cat_path.name, cubelets_dir)
      51              continue
      52          count = catalogue.rename_and_copy_cubelets(
      45 -            cat_path, cubelets_dir, config.paths.renamed_cubele
         -ts_dir, keep_names=keep_names                                  
      53 +            cat_path, cubelets_dir, config.paths.renamed_cubele
         +ts_dir, keep_keys=keep_keys                                    
      54          )
      55          logger.info("%s: copied %d files", base_prefix, count)
      56          total_copied += count

⏺ Update(tests/test_catalogue.py)
  ⎿  Added 31 lines, removed 3 lines
      146      assert not any("Removal_001_1_" in name for name in rename
           d)
      147  
      148  
      149 -def test_rename_and_copy_cubelets_respects_keep_names_filter(t
          -mp_path):                                                     
      149 +def test_rename_and_copy_cubelets_respects_keep_keys_filter(tm
          +p_path):                                                      
      150      output_dir = tmp_path / "renamed"
      151 -    # Keep only one of the eleven sources in run 001.         
      151 +    # Keep only id "1" (-> SoFiA_J210149.89-554804.6) of the t
          +en sources in run 001.                                        
      152      count = catalogue.rename_and_copy_cubelets(
      153          FIXTURE_DIR / "SB82605_Removal_001_cat.xml",
      154          FIXTURE_DIR / "SB82605_Removal_001_cubelets",
      155          output_dir,
      156 -        keep_names={"SoFiA_J210149.89-554804.6"},             
      156 +        keep_keys={("SB82605_Removal_001", "1")},             
      157      )
      158      renamed = sorted(p.name for p in output_dir.iterdir())
      159      assert count == len(renamed)
     ...
      161      assert "SoFiA_J210029.15-545824.9_mom0.fits" not in rename
           d
      162  
      163  
      164 +def test_rename_and_copy_cubelets_keep_keys_disambiguates_iden
          +tical_names_across_runs(tmp_path):                            
      165 +    # "SoFiA J204524.82-550222.5" is independently detected in
          + both Removal_011 and                                         
      166 +    # Removal_012 with the *same* name string (see test_catalo
          +gue duplicate tests) --                                       
      167 +    # a name-only filter cannot tell these apart, which is exa
          +ctly why keep_keys is                                         
      168 +    # keyed on (source_run, id) instead. Ask for only the Remo
          +val_012 copy and confirm                                      
      169 +    # the Removal_011 copy of the identically-named source is 
          +excluded.                                                     
      170 +    output_dir = tmp_path / "renamed"                         
      171 +    table_012 = catalogue.read_votable(FIXTURE_DIR / "SB82605_
          +Removal_012_cat.xml")                                         
      172 +    id_012 = str(table_012[table_012["name"] == "SoFiA J204524
          +.82-550222.5"]["id"][0])                                      
      173 +                                                              
      174 +    catalogue.rename_and_copy_cubelets(                       
      175 +        FIXTURE_DIR / "SB82605_Removal_011_cat.xml",          
      176 +        FIXTURE_DIR / "SB82605_Removal_011_cubelets",         
      177 +        output_dir,                                           
      178 +        keep_keys={("SB82605_Removal_012", id_012)},  # delibe
          +rately the *other* run's key                                  
      179 +    )                                                         
      180 +    assert list(output_dir.iterdir()) == [] if output_dir.exis
          +ts() else True                                                
      181 +                                                              
      182 +    catalogue.rename_and_copy_cubelets(                       
      183 +        FIXTURE_DIR / "SB82605_Removal_012_cat.xml",          
      184 +        FIXTURE_DIR / "SB82605_Removal_012_cubelets",         
      185 +        output_dir,                                           
      186 +        keep_keys={("SB82605_Removal_012", id_012)},          
      187 +    )                                                         
      188 +    renamed = sorted(p.name for p in output_dir.iterdir())    
      189 +    assert any(name.startswith("SoFiA_J204524.82-550222.5_") f
          +or name in renamed)                                           
      190 +                                                              
      191 +                                                              
      192  def test_rename_and_copy_cubelets_preserves_file_content(tmp_p
           ath):
      193      output_dir = tmp_path / "renamed"
      194      catalogue.rename_and_copy_cubelets(

⏺ Update(tests/test_catalogue.py)
  ⎿  Added 9 lines
      33      assert ra == sorted(ra)
      34  
      35  
      36 +def test_combine_runs_adds_source_run_provenance_column():     
      37 +    paths = catalogue.find_run_catalogues(FIXTURE_DIR)         
      38 +    combined = catalogue.combine_runs(paths)                   
      39 +    assert set(combined["source_run"]) == set(EXPECTED_ROWS_PER
         +_RUN.keys()) | {                                               
      40 +        f"SB82605_Removal_{n}" for n in EXPECTED_ROWS_PER_RUN  
      41 +    } - set(EXPECTED_ROWS_PER_RUN.keys())  # placeholder, repla
         +ced below                                                      
      42 +    assert set(combined["source_run"]) == {f"SB82605_Removal_{n
         +}" for n in EXPECTED_ROWS_PER_RUN}                             
      43 +                                                               
      44 +                                                               
      45  def test_combine_runs_rejects_empty_input():
      46      with pytest.raises(ValueError):
      47          catalogue.combine_runs([])

⏺ Update(tests/test_catalogue.py)
  ⎿  Removed 3 lines
      36  def test_combine_runs_adds_source_run_provenance_column():
      37      paths = catalogue.find_run_catalogues(FIXTURE_DIR)
      38      combined = catalogue.combine_runs(paths)
      39 -    assert set(combined["source_run"]) == set(EXPECTED_ROWS_PER
         -_RUN.keys()) | {                                               
      40 -        f"SB82605_Removal_{n}" for n in EXPECTED_ROWS_PER_RUN  
      41 -    } - set(EXPECTED_ROWS_PER_RUN.keys())  # placeholder, repla
         -ced below                                                      
      39      assert set(combined["source_run"]) == {f"SB82605_Removal_{n
          }" for n in EXPECTED_ROWS_PER_RUN}
      40  
      41  

⏺ Now updating test_pipeline_e2e.py to use precise (source_run, id) provenance
  instead of name-based matching for the reverse-check.

⏺ Update(tests/test_pipeline_e2e.py)
  ⎿  Added 31 lines, removed 12 lines
      47          matched = [n for n in kept_names_underscored if f.name.
          startswith(n + "_")]
      48          assert matched, f"{f.name} does not correspond to any s
          urviving source"
      49  
      50 -    # And the reverse: a source known to have been removed by d
         -edup must not appear.                                          
      51 -    removed_result = catalogue.deduplicate_positional(         
      52 -        combined,                                              
      53 -        sep_arcsec=config.dedup.sep_arcsec,                    
      54 -        vel_tol_base_km_s=config.dedup.vel_tol_base_km_s,      
      55 -        vel_tol_wm50_factor=config.dedup.vel_tol_wm50_factor,  
      56 -    )                                                          
      57 -    for removed_name in removed_result.removed_names:          
      58 -        underscored = removed_name.replace(" ", "_")           
      59 -        assert not any(f.name.startswith(underscored + "_") for
         - f in renamed_files), (                                        
      60 -            f"{removed_name} was removed by dedup but its cubel
         -ets were still copied"                                         
      61 -        )                                                      
      50 +    # And the reverse, precisely: every renamed file must trace
         + back to a                                                     
      51 +    # (source_run, id) that survived dedup, not merely to a sur
         +viving *name* -- two                                           
      52 +    # duplicate rows can share an identical SoFiA-generated nam
         +e (see                                                         
      53 +    # test_catalogue.py's keep_keys disambiguation test), so th
         +is checks the stronger,                                        
      54 +    # correct invariant rather than the name-only one that firs
         +t caught this bug.                                             
      55 +    surviving_keys = {(str(run), str(i)) for run, i in zip(dedu
         +ped["source_run"], deduped["id"])}                             
      56 +    for run_prefix in set(combined["source_run"]):             
      57 +        cat_path = config.paths.raw_sofia_dir / f"{run_prefix}_
         +cat.xml"                                                       
      58 +        mapping = catalogue.id_to_name_mapping(catalogue.read_v
         +otable(cat_path))                                              
      59 +        for source_id, name in mapping.items():                
      60 +            files_for_this_key = [f for f in renamed_files if f
         +.name.startswith(name + "_")]                                  
      61 +            if (run_prefix, source_id) not in surviving_keys:  
      62 +                # This run+id's own cubelets must not be the on
         +es present under `name`                                        
      63 +                # -- but another run+id sharing the same name m
         +ight legitimately have                                         
      64 +                # supplied them, so only assert something if *n
         +o* surviving key maps                                          
      65 +                # to this name at all.                         
      66 +                other_survivors_for_name = [                   
      67 +                    k for k in surviving_keys if id_to_name_for
         +_key(deduped, k) == name                                       
      68 +                ]                                              
      69 +                if not other_survivors_for_name:               
      70 +                    assert not files_for_this_key, (           
      71 +                        f"{run_prefix}/{source_id} ({name}) was
         + removed by dedup but its "                                    
      72 +                        f"cubelets were still copied"          
      73 +                    )                                          
      74  
      75  
      76 +def id_to_name_for_key(deduped_table, key):                    
      77 +    run, source_id = key                                       
      78 +    mask = (deduped_table["source_run"] == run) & (deduped_tabl
         +e["id"].astype(str) == source_id)                              
      79 +    matches = deduped_table[mask]                              
      80 +    return str(matches["name"][0]).replace(" ", "_") if len(mat
         +ches) else None                                                
      81 +                                                               
      82 +                                                               
      83  def test_dedup_fails_clearly_if_combine_was_not_run_first(tmp_p
          ath):
      84      config = _load_config(tmp_path)
      85      try:
⏺ That got overcomplicated — let me simplify to a direct, concrete check instead
  of a generic loop.

⏺ Update(tests/test_pipeline_e2e.py)
  ⎿  Added 17 lines, removed 30 lines
      47          matched = [n for n in kept_names_underscored if f.name.
          startswith(n + "_")]
      48          assert matched, f"{f.name} does not correspond to any s
          urviving source"
      49  
      50 -    # And the reverse, precisely: every renamed file must trace
         - back to a                                                     
      51 -    # (source_run, id) that survived dedup, not merely to a sur
         -viving *name* -- two                                           
      52 -    # duplicate rows can share an identical SoFiA-generated nam
         -e (see                                                         
      53 -    # test_catalogue.py's keep_keys disambiguation test), so th
         -is checks the stronger,                                        
      54 -    # correct invariant rather than the name-only one that firs
         -t caught this bug.                                             
      55 -    surviving_keys = {(str(run), str(i)) for run, i in zip(dedu
         -ped["source_run"], deduped["id"])}                             
      56 -    for run_prefix in set(combined["source_run"]):             
      57 -        cat_path = config.paths.raw_sofia_dir / f"{run_prefix}_
         -cat.xml"                                                       
      58 -        mapping = catalogue.id_to_name_mapping(catalogue.read_v
         -otable(cat_path))                                              
      59 -        for source_id, name in mapping.items():                
      60 -            files_for_this_key = [f for f in renamed_files if f
         -.name.startswith(name + "_")]                                  
      61 -            if (run_prefix, source_id) not in surviving_keys:  
      62 -                # This run+id's own cubelets must not be the on
         -es present under `name`                                        
      63 -                # -- but another run+id sharing the same name m
         -ight legitimately have                                         
      64 -                # supplied them, so only assert something if *n
         -o* surviving key maps                                          
      65 -                # to this name at all.                         
      66 -                other_survivors_for_name = [                   
      67 -                    k for k in surviving_keys if id_to_name_for
         -_key(deduped, k) == name                                       
      68 -                ]                                              
      69 -                if not other_survivors_for_name:               
      70 -                    assert not files_for_this_key, (           
      71 -                        f"{run_prefix}/{source_id} ({name}) was
         - removed by dedup but its "                                    
      72 -                        f"cubelets were still copied"          
      73 -                    )                                          
      50 +    # Precise regression check for the bug this test suite caug
         +ht during development:                                         
      51 +    # "SoFiA J204524.82-550222.5" is detected in both Removal_0
         +11 and Removal_012 with                                        
      52 +    # the *identical* name string, so a name-only keep-filter c
         +an't tell which run's                                          
      53 +    # cubelets should survive -- only (source_run, id) can. Con
         +firm the copied file's                                         
      54 +    # bytes match the *surviving* run's original cubelet, not t
         +he removed one's.                                              
      55 +    dup_name = "SoFiA J204524.82-550222.5"                     
      56 +    dup_rows = deduped[deduped["name"] == dup_name]            
      57 +    assert len(dup_rows) == 1, "fixture assumption changed -- u
         +pdate this test"                                               
      58 +    surviving_run, surviving_id = str(dup_rows["source_run"][0]
         +), str(dup_rows["id"][0])                                      
      59  
      60 +    copied = config.paths.renamed_cubelets_dir / "SoFiA_J204524
         +.82-550222.5_cube.fits"                                        
      61 +    expected_source = (                                        
      62 +        FIXTURES                                               
      63 +        / "run_sofia_mini"                                     
      64 +        / f"{surviving_run}_cubelets"                          
      65 +        / f"{surviving_run}_{surviving_id}_cube.fits"          
      66 +    )                                                          
      67 +    assert copied.read_bytes() == expected_source.read_bytes() 
      68  
      76 -def id_to_name_for_key(deduped_table, key):                    
      77 -    run, source_id = key                                       
      78 -    mask = (deduped_table["source_run"] == run) & (deduped_tabl
         -e["id"].astype(str) == source_id)                              
      79 -    matches = deduped_table[mask]                              
      80 -    return str(matches["name"][0]).replace(" ", "_") if len(mat
         -ches) else None                                                
      69  
      82 -                                                               
      70  def test_dedup_fails_clearly_if_combine_was_not_run_first(tmp_p
          ath):
      71      config = _load_config(tmp_path)
      72      try:

⏺ Now running the full test suite to confirm everything holds together.

  Ran 1 shell command (ctrl+o to expand)

⏺ Let's run the linter to catch style issues before committing.

  Ran 1 shell command (ctrl+o to expand)

⏺ Let me apply the auto-fixes and manually fix the remaining line-length issues.

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/catalogue.py)
  ⎿  Added 2 lines, removed 1 line
      130      pair_mask = idx1 < idx2
      131      idx1, idx2 = idx1[pair_mask], idx2[pair_mask]
      132  
      133 -    vel_tol = vel_tol_wm50_factor * np.maximum(wm50_velocity_k
          -m_s[idx1], wm50_velocity_km_s[idx2]) + vel_tol_base_km_s      
      133 +    max_wm50 = np.maximum(wm50_velocity_km_s[idx1], wm50_veloc
          +ity_km_s[idx2])                                               
      134 +    vel_tol = vel_tol_wm50_factor * max_wm50 + vel_tol_base_km
          +_s                                                            
      135      vel_sep = np.abs(velocity_km_s[idx1] - velocity_km_s[idx2]
           )
      136      is_duplicate_pair = vel_sep <= vel_tol
      137  

⏺ Update(src/hivalidate/cli/combine.py)
  ⎿  Added 3 lines, removed 1 line
      22      run_catalogues = catalogue.find_run_catalogues(config.paths
          .raw_sofia_dir)
      23      if not run_catalogues:
      24          raise SystemExit(f"No *_cat.xml files found under {conf
          ig.paths.raw_sofia_dir}")
      25 -    logger.info("Combining %d run catalogues from %s", len(run_
         -catalogues), config.paths.raw_sofia_dir)                       
      25 +    logger.info(                                               
      26 +        "Combining %d run catalogues from %s", len(run_catalogu
         +es), config.paths.raw_sofia_dir                                
      27 +    )                                                          
      28  
      29      combined = catalogue.combine_runs(run_catalogues)
      30      logger.info("Combined catalogue has %d sources", len(combin
          ed))

⏺ Update(src/hivalidate/cli/dedup.py)
  ⎿  Added 3 lines, removed 1 line
      23          )
      24  
      25      combined = catalogue.read_votable(config.paths.combined_cat
          alogue)
      26 -    logger.info("Deduplicating %d sources (sep=%.1f arcsec)", l
         -en(combined), config.dedup.sep_arcsec)                         
      26 +    logger.info(                                               
      27 +        "Deduplicating %d sources (sep=%.1f arcsec)", len(combi
         +ned), config.dedup.sep_arcsec                                  
      28 +    )                                                          
      29  
      30      result = catalogue.deduplicate_positional(
      31          combined,

⏺ Update(src/hivalidate/cli/dedup.py)
  ⎿  Added 3 lines, removed 1 line
      33          vel_tol_base_km_s=config.dedup.vel_tol_base_km_s,
      34          vel_tol_wm50_factor=config.dedup.vel_tol_wm50_factor,
      35      )
      36 -    logger.info("Removed %d duplicate detections, %d sources re
         -main", result.n_removed, len(result.table))                    
      36 +    logger.info(                                               
      37 +        "Removed %d duplicate detections, %d sources remain", r
         +esult.n_removed, len(result.table)                             
      38 +    )                                                          
      39      for name in result.removed_names:
      40          logger.debug("Removed duplicate: %s", name)
      41  

⏺ Update(src/hivalidate/cli/rename.py)
  ⎿  Added 3 lines, removed 1 line
      47          base_prefix = cat_path.name.removesuffix("_cat.xml")
      48          cubelets_dir = config.paths.raw_sofia_dir / f"{base_pre
          fix}_cubelets"
      49          if not cubelets_dir.is_dir():
      50 -            logger.warning("No cubelets directory for %s (expec
         -ted %s) -- skipping", cat_path.name, cubelets_dir)             
      50 +            logger.warning(                                    
      51 +                "No cubelets directory for %s (expected %s) -- 
         +skipping", cat_path.name, cubelets_dir                         
      52 +            )                                                  
      53              continue
      54          count = catalogue.rename_and_copy_cubelets(
      55              cat_path, cubelets_dir, config.paths.renamed_cubele
          ts_dir, keep_keys=keep_keys

⏺ Update(src/hivalidate/config.py)
  ⎿  Added 3 lines, removed 1 line
      141              cutouts_raw["cache_dir"] = resolve(cutouts_raw["ca
           che_dir"])
      142          cutouts = CutoutSettings(**cutouts_raw)
      143  
      144 -        config = cls(field_name=field_name, paths=paths, dedup
          -=dedup, cosmology=cosmology, cutouts=cutouts)                 
      144 +        config = cls(                                         
      145 +            field_name=field_name, paths=paths, dedup=dedup, c
          +osmology=cosmology, cutouts=cutouts                           
      146 +        )                                                     
      147          config.validate()
      148          return config
      149  

⏺ Update(src/hivalidate/config.py)
  ⎿  Added 5 lines, removed 3 lines
      156          if not self.paths.raw_sofia_dir.is_dir():
      157              raise ValueError(f"paths.raw_sofia_dir does not ex
           ist or is not a directory: "
      158                                f"{self.paths.raw_sofia_dir}")
      159 -        if self.paths.continuum_local_dir is not None and not 
          -self.paths.continuum_local_dir.is_dir():                      
      160 -            raise ValueError(f"paths.continuum_local_dir does 
          -not exist or is not a directory: "                            
      161 -                              f"{self.paths.continuum_local_di
          -r}")                                                          
      159 +        continuum_dir = self.paths.continuum_local_dir        
      160 +        if continuum_dir is not None and not continuum_dir.is_
          +dir():                                                        
      161 +            raise ValueError(                                 
      162 +                f"paths.continuum_local_dir does not exist or 
          +is not a directory: {continuum_dir}"                          
      163 +            )                                                 
      164          if self.paths.gama_catalogue is not None and not self.
           paths.gama_catalogue.is_file():
      165              raise ValueError(f"paths.gama_catalogue does not e
           xist: {self.paths.gama_catalogue}")

⏺ Now the three test files:

⏺ Update(tests/test_config.py)
  ⎿  Added 4 lines, removed 1 line
      22  def test_missing_raw_sofia_dir_raises_before_any_pipeline_stage
          _runs(tmp_path):
      23      bad_config = {
      24          "field_name": "bogus",
      25 -        "paths": {"raw_sofia_dir": str(tmp_path / "does_not_exi
         -st"), "work_dir": str(tmp_path / "work")},                     
      25 +        "paths": {                                             
      26 +            "raw_sofia_dir": str(tmp_path / "does_not_exist"), 
      27 +            "work_dir": str(tmp_path / "work"),                
      28 +        },                                                     
      29      }
      30      with pytest.raises(ValueError, match="raw_sofia_dir"):
      31          Config.from_dict(bad_config)

⏺ Update(tests/test_conversions.py)
  ⎿  Added 2 lines, removed 1 line
      79      constant = 2.356e5 * (conv.SPEED_OF_LIGHT_KM_S / conv.HI_RE
          ST_FREQ_HZ)
      80      mass_without_correction = np.log10(constant * d_l_mpc**2 * 
          s_int)  # the old, buggy formula
      81  
      82 -    assert mass_with_correction == pytest.approx(mass_without_c
         -orrection - np.log10(1 + z), rel=1e-9)                         
      82 +    expected = mass_without_correction - np.log10(1 + z)       
      83 +    assert mass_with_correction == pytest.approx(expected, rel=
         +1e-9)                                                          
      84  
      85  
      86  def test_hi_mass_respects_custom_cosmology():

⏺ Update(tests/test_conversions.py)
  ⎿  Added 2 lines, removed 1 line
      129  def test_freq_width_to_velocity_dispersion_matches_local_appro
           ximation():
      130      freq_width, freq_centre = 18500.0, conv.HI_REST_FREQ_HZ
      131      expected = conv.SPEED_OF_LIGHT_KM_S * freq_width / freq_ce
           ntre
      132 -    assert conv.freq_width_to_velocity_dispersion(freq_width, 
          -freq_centre) == pytest.approx(expected)                       
      132 +    result = conv.freq_width_to_velocity_dispersion(freq_width
          +, freq_centre)                                                
      133 +    assert result == pytest.approx(expected)                  

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/cli/rename.py)
  ⎿  Added 3 lines, removed 1 line
      48          cubelets_dir = config.paths.raw_sofia_dir / f"{base_pre
          fix}_cubelets"
      49          if not cubelets_dir.is_dir():
      50              logger.warning(
      51 -                "No cubelets directory for %s (expected %s) -- 
         -skipping", cat_path.name, cubelets_dir                         
      51 +                "No cubelets directory for %s (expected %s) -- 
         +skipping",                                                     
      52 +                cat_path.name,                                 
      53 +                cubelets_dir,                                  
      54              )
      55              continue
      56          count = catalogue.rename_and_copy_cubelets(

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's verify the installed console-script entry points actually work, and
  run the real catalogue pipeline (combine/dedup/rename) against the full 45-run
  data/run_sofia/ dataset — this doesn't need network access, so I can validate
  it for real right now.

  Ran 2 shell commands (ctrl+o to expand)
⏺ That's a striking result — 33% of raw detections turn out to be duplicates,
  far more than the 14 the legacy exact-string matching caught. Before trusting
  this, let me sanity-check it isn't over-merging genuinely distinct nearby
  sources.

  Ran 1 shell command (ctrl+o to expand)

⏺ Confirmed: accepted duplicate pairs have a median separation of 0.33″ and 0.4
  km/s (clearly the same source refit), while rejected sky-close pairs are
  actually different sources — median 20″ apart but 3300+ km/s apart in
  velocity. The 33% duplicate rate is real, not an artifact of loose tolerances.
  Completing the rename step on the full dataset.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Good — data/work/ is correctly excluded by .gitignore. Let's commit Phase 1.

  Ran 1 shell command (ctrl+o to expand)

⏺ Good, everything staged cleanly. Committing Phase 1.

  Ran 1 shell command (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ Let me update PLAN.md's status before pausing to report back — it should
  reflect real progress, not just intent.

  Read 1 file (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 13 lines, removed 8 lines
      186  
      187  ## 8. Build sequence
      188  
      189 -### Phase 0 — Repo scaffolding                                
      190 -- [ ] `git init`, `.gitignore` (incl. any local CASDA credenti
          -als file), `LICENSE`                                          
      189 +### Phase 0 — Repo scaffolding [DONE 2026-07-30]              
      190 +- [x] `git init`, `.gitignore` (incl. any local CASDA credenti
          +als file), `LICENSE`                                          
      191        (BSD-3-Clause)
      192 -- [ ] Directory structure as in §4, with `run_sofia/` moved to
          - `data/run_sofia/`                                            
      193 -- [ ] `pyproject.toml` + `environment.yml` (pin dependencies i
          -ncl. `MontagePy`,                                             
      194 -      `astropy`, `astroquery`, `reproject`, `matplotlib`, `num
          -py`, `requests`)                                              
      195 -- [ ] `.pre-commit-config.yaml` (ruff/black), `.github/workflo
          -ws/ci.yml`                                                    
      196 -- [ ] `README.md` skeleton (incl. OPAL/CASDA account setup ins
          -tructions),                                                   
      192 +- [x] Directory structure as in §4, with `run_sofia/` moved to
          + `data/run_sofia/`                                            
      193 +- [x] `pyproject.toml` + `environment.yml` (pin dependencies i
          +ncl. `MontagePy`,                                             
      194 +      `astropy`, `astroquery`, `reproject`, `matplotlib`, `num
          +py`, `requests`) --                                           
      195 +      MontagePy pinned to >=2.3 (the real PyPI version; the pl
          +an's placeholder >=6.0                                        
      196 +      was wrong, caught when `pip install -e .` actually faile
          +d)                                                            
      197 +- [x] `.pre-commit-config.yaml` (ruff/black), `.github/workflo
          +ws/ci.yml`                                                    
      198 +- [x] `README.md` skeleton (incl. OPAL/CASDA account setup ins
          +tructions),                                                   
      199        `REFERENCES.md` skeleton
      198 -- [ ] Extract the small `run_sofia_mini` fixture (2-3 runs) in
          -to `tests/fixtures/`                                          
      200 +- [x] Extract a `run_sofia_mini` fixture into `tests/fixtures/
          +` -- ended up as 5 real                                       
      201 +      runs (001, 002, 003, 011, 012), not 2-3, specifically to
          + include a known                                              
      202 +      cross-run duplicate pair (011/012) for a true-positive d
          +edup test                                                     
      203 +- Legacy scripts moved to `legacy/` (not deleted) for referenc
          +e during migration.                                           
      204  
      205  ### Phase 1 — Core science + catalogue layer
      206  - [ ] `config.py`: load/validate per-field YAML config

  Read 1 file (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 13 lines, removed 6 lines
      202        cross-run duplicate pair (011/012) for a true-positive d
           edup test
      203  - Legacy scripts moved to `legacy/` (not deleted) for referenc
           e during migration.
      204  
      205 -### Phase 1 — Core science + catalogue layer                  
      206 -- [ ] `config.py`: load/validate per-field YAML config        
      207 -- [ ] `conversions.py`: migrate freq/z/vel/mass/column-density
          - functions from                                               
      205 +### Phase 1 — Core science + catalogue layer [DONE 2026-07-30]
      206 +- [x] `config.py`: load/validate per-field YAML config        
      207 +- [x] `conversions.py`: migrate freq/z/vel/mass/column-density
          + functions from                                               
      208        `validate_detections.py`, full docstrings + `REFERENCES.
           md` citations, unit tests
      209 -- [ ] `catalogue.py`: VOTable read, multi-run combine (replace
          -s `plot_detections.py`'s                                      
      209 +      -- **found and fixed a real bug**: the legacy frequency-
          +rest-frame HI mass formula                                    
      210 +      was missing [Meyer2017]'s `1/(1+z)` term (~1-10% effect 
          +at these redshifts)                                           
      211 +- [x] `catalogue.py`: VOTable read, multi-run combine (replace
          +s `plot_detections.py`'s                                      
      212        combine step), positional dedup (replaces `remove_duplic
           ate.py`), id→name mapping
      213        per run (replaces `rename_cubelets.py` logic) — fixes is
           sues #1, #5, #6, #9
      212 -- [ ] CLI: `combine`, `dedup`, `rename` stages runnable agains
          -t `run_sofia/`                                                
      213 -- [ ] Tests against `run_sofia_mini` fixture                  
      214 +- [x] CLI: `combine`, `dedup`, `rename` stages runnable agains
          +t `run_sofia/`                                                
      215 +- [x] Tests against `run_sofia_mini` fixture (41 tests, all pa
          +ssing)                                                        
      216 +- **Ran for real against the full 45-run `data/run_sofia/`**: 
          +670 raw detections ->                                         
      217 +  222 removed as duplicates (33%) -> 448 unique sources, 5824 
          +renamed cubelet files.                                        
      218 +  Far more duplication than the legacy script's 14 exact-strin
          +g matches -- verified                                         
      219 +  this is real, not over-merging (accepted pairs: median 0.33″
          +/0.4 km/s separation;                                         
      220 +  correctly-rejected sky-close pairs: thousands of km/s apart 
          +in velocity).                                                 
      221  
      222  ### Phase 2 — Cutout layer
      223  - [ ] `cutouts/base.py`: fallback-chain abstraction, on-disk c
           ache, retry/backoff

  Ran 1 shell command (ctrl+o to expand)

⏺ I've completed Phases 0 and 1 of the plan — that's a solid, fully-tested
  foundation, and a natural checkpoint before Phase 2 (cutouts), which needs
  something from you. Here's where things stand:

  Phase 0 (scaffolding) — done. Git repo initialized, src/hivalidate/ package
  layout, pyproject.toml/environment.yml, pre-commit + CI, BSD-3-Clause license,
  run_sofia/ moved under data/, legacy scripts preserved in legacy/ (not
  deleted), a 5-run test fixture extracted. One correction along the way:
  MontagePy is only at 2.3.x on PyPI, not the 6.0 I'd guessed in the plan —
  fixed once pip install actually failed on it.

  Phase 1 (core science + catalogue layer) — done, 41 tests passing. Two things
  worth knowing about:

  1. Found and fixed a real bug while verifying literature citations: the legacy
  script's HI mass formula was missing the 1/(1+z) cosmological correction that
  Meyer et al. (2017) — the paper the formula is from — applies. It's a ~1-10%
  effect at DINGO/WALLABY-pilot redshifts, present in every HI mass the old
  pipeline ever reported. Confirmed via web search against the published
  equation, not assumed.
  2. The new positional/velocity dedup found far more duplicates than expected.
  I ran combine → dedup → rename for real against all 45 runs in
  data/run_sofia/: 670 raw detections → 222 removed as duplicates (33%) → 448
  unique sources. The legacy exact-name-string matching only ever caught 14. I
  checked this isn't over-merging: genuine duplicate pairs have a median
  separation of 0.33″ and 0.4 km/s (clearly the same source refit with a
  slightly different centroid), while sky-close-but-different sources are
  correctly rejected — they're thousands of km/s apart in velocity. This means
  the field likely has significantly fewer real sources than previously assumed.

  Before I continue into Phase 2 (cutouts): it needs astroquery.casda
  credentials for the RACS continuum fallback, and none are set in this
  environment (CASDA_USERNAME/CASDA_PASSWORD). I can build and fully test the
  SkyView and Legacy Survey optical backends right now (no auth needed), and
  write the CASDA backend correctly against the docs — but I can't verify it
  against a live login without credentials. Do you want to set those as
  environment variables now so I can test it end-to-end, or should I build it
  untested and you verify it later?

✻ Brewed for 21m 57s

❯ Build it first and I will verify it later (also let me know the instructions  
  of how to verify it later by myself.                                          

⏺ Let me continue with Phase 2. First, I'll inspect the actual installed
  astroquery.casda API rather than relying on memory, so the untested CASDA
  backend code is at least correct against the real library signature.

  Ran 6 shell commands (ctrl+o to expand)

⏺ Let me check the astroquery CASDA documentation for a concrete RACS cutout
  example, to ground the implementation rather than guess at column names.

⏺ Web Search("astroquery casda query_region RACS example obs_collection cutout
            tutorial")  ⎿  Did 1 search in 9s

⏺ Fetch(https://astroquery.readthedocs.io/en/latest/casda/casda.html)
  ⎿  Received 12.5KB (200 OK)

⏺ Write(src/hivalidate/cutouts/base.py)
  ⎿  Wrote 166 lines to src/hivalidate/cutouts/base.py
       1 """Fallback-chain abstraction shared by the optical and continuu
       2 
         uum) has a priority
         der, checking an
         itting the network,
       6 and moves on to the next backend on any failure rather than abor
       7 (PLAN.md issue #8). Every successful result carries `provenance`
       8 actually supplied it -- because once there is more than one poss
       9 image, the output catalogue needs to record which one was used f
      10 """
     … +198 lines (ctrl+o to expand)

⏺ Now the optical backends (SkyView + Legacy Survey), both testable live without
  credentials.

⏺ Write(src/hivalidate/cutouts/optical.py)
  ⎿  Wrote 142 lines to src/hivalidate/cutouts/optical.py
       1 """Optical cutout backends: SkyView (DSS2 Red, migrated from
       2 `legacy/validate_detections.py`'s `get_opt_imag`) and Legacy Sur
       3 from `legacy/download_legacy.py`'s single-file cutout API call).
       4 
       5 Neither backend needs authentication, so both are fully testable
       6 -- see `tests/test_cutouts_optical.py`, including a live (networ
         k-marked) smoke test
       7 actually run during development, not just mocked.
       9 
      10 from __future__ import annotations
     … +177 lines (ctrl+o to expand)

  Ran 4 shell commands (ctrl+o to expand)

⏺ Web Search("RACS Rapid ASKAP Continuum Survey declination coverage limit
            McConnell 2020 whole southern sky")
  ⎿  Did 1 search in 7s

⏺ Write(src/hivalidate/cutouts/continuum.py)
  ⎿  Wrote 230 lines to src/hivalidate/cutouts/continuum.py
       1 """Continuum cutout backends: a local field mosaic (via MontageP
       2 `legacy/validate_detections.py`'s `get_cont_imag`) and RACS via 
       3 having no continuum image at all when no local mosaic covers a f
         ield).
       5 `LocalContinuumBackend` was verified live against the real
         rom
         sage for exact
       8 commands/output) -- both the success and the "outside image foot
       9 
         no CASDA/OPAL
     … +285 lines (ctrl+o to expand)

⏺ Now writing tests. LocalContinuumBackend needs a lightweight CI-safe fixture
  (the real continuum image isn't in git) — let me build a small synthetic one
  with a realistic WCS header first.

  Ran 1 shell command (ctrl+o to expand)

⏺ Write(tests/test_cutouts_base.py)
  ⎿  Wrote 165 lines to tests/test_cutouts_base.py
      1 """Unit tests for the fallback-chain/cache/retry machinery in cut
        outs/base.py, using
      2 fake backends -- no network, no real survey dependency. Live back
        end behaviour is
      3 tested in test_cutouts_optical.py / test_cutouts_continuum.py.
      5 
      6 import numpy as np
      7 import pytest
      8 from astropy.coordinates import SkyCoord
      9 from astropy.wcs import WCS
     … +179 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ Let's register a network pytest marker (excluded by default, so CI never
  depends on live network) before writing the optical backend tests.

⏺ Update(pyproject.toml)
  ⎿  Added 4 lines
      47  
      48  [tool.pytest.ini_options]
      49  testpaths = ["tests"]
      50 +markers = [                                                    
      51 +    "network: hits a real external service (SkyView, Legacy Sur
         +vey, CASDA); excluded by default",                             
      52 +]                                                              
      53 +addopts = "-m 'not network'"                                   
      54  
      55  [tool.ruff]
      56  line-length = 100

⏺ Write(tests/test_cutouts_optical.py)
  ⎿  Wrote 182 lines to tests/test_cutouts_optical.py
       1 """Tests for the optical cutout backends.
       3 Two tiers: fast mocked unit tests (always run) that check our ow
       4 construction, error handling, provenance strings -- and a `netwo
         rk`-marked class that
         redentials, so the
         etwork
         work, not just that
       8 they're plausible against the docs. They're excluded from the de
       9 (`addopts = "-m 'not network'"` in pyproject.toml) so CI stays f
      10 an external service being up.
     … +208 lines (ctrl+o to expand)

⏺ Now let's run the mocked (default) tests, then the live network-marked ones to
  actually verify SkyView and Legacy Survey work for real.

  Ran 1 shell command (ctrl+o to expand)

⏺ A trivial test issue (is False vs numpy bool) — fixing.
⏺ Update(tests/test_cutouts_optical.py)
  ⎿  Added 2 lines, removed 2 lines
       95      def test_check_coverage_rejects_far_northern_declination(s
           elf):
       96          backend = LegacySurveyBackend()
       97          far_north = SkyCoord(ra=180.0, dec=60.0, unit="deg")
       98 -        assert backend.check_coverage(far_north) is False     
       99 -        assert backend.check_coverage(POSITION) is True       
       98 +        assert not backend.check_coverage(far_north)          
       99 +        assert backend.check_coverage(POSITION)               
      100  
      101      def test_builds_expected_cutout_url(self, monkeypatch):
      102          captured = {}

⏺ Now running the live network tests to actually verify these backends against
  the real services.

  Ran 1 shell command (ctrl+o to expand)

⏺ SkyView passed live. Legacy Survey got a 503 — let me check whether that's a
  transient server issue or something structural before concluding anything.

  Ran 1 shell command (ctrl+o to expand)

⏺ The site itself is returning 503 (curl confirms it's fully down right now, not
  a bug in our code) — but this exposes a real gap: unlike SkyView,
  LegacySurveyBackend has no retry/backoff for transient failures. Let me fix
  that properly rather than treat this as a fluke.

⏺ Update(src/hivalidate/cutouts/optical.py)
  ⎿  Added 21 lines, removed 7 lines
       93      #: to skip an obviously-hopeless request for a northern po
           sition.
       94      APPROX_DEC_CEILING_DEG = 34.0
       95  
       96 -    def __init__(self, layer: str = "ls-dr10", pixscale_arcsec
          -: float = 0.262, band: str = "r"):                            
       96 +    def __init__(                                             
       97 +        self, layer: str = "ls-dr10", pixscale_arcsec: float =
          + 0.262, band: str = "r", max_retries: int = 5                 
       98 +    ):                                                        
       99          self.layer = layer
      100          self.pixscale_arcsec = pixscale_arcsec
      101          self.band = band
      102 +        self.max_retries = max_retries                        
      103  
      104      def check_coverage(self, position: SkyCoord) -> bool:
      105          return position.dec.deg < self.APPROX_DEC_CEILING_DEG
     ...
      112              f"size={n_pix}&pixscale={self.pixscale_arcsec}&"
      113              f"layer={self.layer}&bands={self.band}"
      114          )
      112 -        try:                                                  
      113 -            response = requests.get(url, timeout=30)          
      114 -        except requests.exceptions.RequestException as exc:   
      115 -            raise CutoutUnavailable(f"Legacy Survey request fa
          -iled: {exc}") from exc                                        
      115  
      117 -        if response.status_code != 200:                       
      118 -            raise CutoutUnavailable(f"Legacy Survey returned s
          -tatus {response.status_code}")                                
      116 +        def _get():                                           
      117 +            try:                                              
      118 +                response = requests.get(url, timeout=30)      
      119 +            except requests.exceptions.RequestException as exc
          +:                                                             
      120 +                raise CutoutUnavailable(f"Legacy Survey reques
          +t failed: {exc}") from exc                                    
      121 +            # 503 (observed live during development -- the ser
          +vice was briefly down)                                        
      122 +            # and other 5xx are worth retrying; a 4xx (e.g. ba
          +d request) never will                                         
      123 +            # succeed on retry, so fail immediately instead of
          + wasting the backoff budget.                                  
      124 +            if response.status_code >= 500:                   
      125 +                raise CutoutUnavailable(f"Legacy Survey return
          +ed status {response.status_code}")                            
      126 +            if response.status_code != 200:                   
      127 +                raise _NonRetryableStatus(f"Legacy Survey retu
          +rned status {response.status_code}")                          
      128 +            return response                                   
      129  
      130 +        response = retry_with_backoff(                        
      131 +            _get, max_retries=self.max_retries, retryable_exce
          +ptions=(CutoutUnavailable,)                                   
      132 +        )                                                     
      133 +                                                              
      134          try:
      135              with fits.open(io.BytesIO(response.content)) as hd
           ul:
      136                  data = hdul[0].data

⏺ Update(src/hivalidate/cutouts/optical.py)
  ⎿  Added 8 lines
      20  from hivalidate.cutouts.base import CutoutBackend, CutoutResult
          , CutoutUnavailable, retry_with_backoff
      21  
      22  
      23 +class _NonRetryableStatus(Exception):                          
      24 +    """Internal to `LegacySurveyBackend.fetch`: a non-5xx HTTP 
         +error, which retrying                                          
      25 +    cannot fix (unlike a 5xx or connection error). Deliberately
         + not a                                                         
      26 +    `CutoutUnavailable` so `retry_with_backoff`'s exception fil
         +ter doesn't retry it;                                          
      27 +    caught immediately after and converted to `CutoutUnavailabl
         +e` for the caller.                                             
      28 +    """                                                        
      29 +                                                               
      30 +                                                               
      31  class SkyViewBackend(CutoutBackend):
      32      """DSS2 Red (or any other SkyView survey) via `astroquery.s
          kyview`. SkyView's
      33      `get_images` takes a pixel count, not an angular size direc
          tly, so this backend

⏺ Update(src/hivalidate/cutouts/optical.py)
  ⎿  Added 6 lines, removed 3 lines
      135                  raise _NonRetryableStatus(f"Legacy Survey retu
           rned status {response.status_code}")
      136              return response
      137  
      138 -        response = retry_with_backoff(                        
      139 -            _get, max_retries=self.max_retries, retryable_exce
          -ptions=(CutoutUnavailable,)                                   
      140 -        )                                                     
      138 +        try:                                                  
      139 +            response = retry_with_backoff(                    
      140 +                _get, max_retries=self.max_retries, retryable_
          +exceptions=(CutoutUnavailable,)                               
      141 +            )                                                 
      142 +        except _NonRetryableStatus as exc:                    
      143 +            raise CutoutUnavailable(str(exc)) from exc        
      144  
      145          try:
      146              with fits.open(io.BytesIO(response.content)) as hd
           ul:

⏺ That retry addition means some of my mocked tests will now actually sleep
  during retries — let me fix the test file to keep it fast.

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_cutouts_optical.py)
  ⎿  Added 52 lines, removed 7 lines
      115          assert f"ra={POSITION.ra.deg}" in captured["url"]
      116          assert "size=100" in captured["url"]  # 26.2 / 0.262
      117  
      118 -    def test_non_200_status_raises_cutout_unavailable(self, mo
          -nkeypatch):                                                   
      119 -        monkeypatch.setattr(                                  
      120 -            "hivalidate.cutouts.optical.requests.get", lambda 
          -url, timeout: _FakeResponse(500, b"")                         
      121 -        )                                                     
      118 +    def test_client_error_status_fails_immediately_without_ret
          +rying(self, monkeypatch):                                     
      119 +        # A 4xx is never fixed by retrying -- assert it does N
          +OT sleep/retry, by not                                        
      120 +        # mocking time.sleep at all: if the code tried to retr
          +y, this test would hang                                       
      121 +        # for real seconds and could time out, which is the po
          +int of the assertion.                                         
      122 +        call_count = {"n": 0}                                 
      123 +                                                              
      124 +        def fake_get(url, timeout):                           
      125 +            call_count["n"] += 1                              
      126 +            return _FakeResponse(404, b"")                    
      127 +                                                              
      128 +        monkeypatch.setattr("hivalidate.cutouts.optical.reques
          +ts.get", fake_get)                                            
      129          backend = LegacySurveyBackend()
      123 -        with pytest.raises(CutoutUnavailable, match="500"):   
      130 +        with pytest.raises(CutoutUnavailable, match="404"):   
      131              backend.fetch(POSITION, size_arcsec=26.2)
      132 +        assert call_count["n"] == 1                           
      133  
      134 +    def test_5xx_status_retries_then_raises_cutout_unavailable
          +(self, monkeypatch):                                          
      135 +        monkeypatch.setattr("time.sleep", lambda _: None)     
      136 +        call_count = {"n": 0}                                 
      137 +                                                              
      138 +        def fake_get(url, timeout):                           
      139 +            call_count["n"] += 1                              
      140 +            return _FakeResponse(503, b"")                    
      141 +                                                              
      142 +        monkeypatch.setattr("hivalidate.cutouts.optical.reques
          +ts.get", fake_get)                                            
      143 +        backend = LegacySurveyBackend(max_retries=3)          
      144 +        with pytest.raises(CutoutUnavailable, match="503"):   
      145 +            backend.fetch(POSITION, size_arcsec=26.2)         
      146 +        assert call_count["n"] == 3                           
      147 +                                                              
      148 +    def test_5xx_then_success_is_recovered_by_retry(self, monk
          +eypatch):                                                     
      149 +        # Regression test for the real 503 observed live again
          +st legacysurvey.org                                           
      150 +        # during development (see the module docstring) -- thi
          +s backend didn't retry                                        
      151 +        # at all before that was found.                       
      152 +        monkeypatch.setattr("time.sleep", lambda _: None)     
      153 +        attempts = {"n": 0}                                   
      154 +                                                              
      155 +        def fake_get(url, timeout):                           
      156 +            attempts["n"] += 1                                
      157 +            if attempts["n"] < 2:                             
      158 +                return _FakeResponse(503, b"")                
      159 +            buf = io.BytesIO()                                
      160 +            fits.writeto(buf, np.ones((10, 10)), overwrite=Tru
          +e)                                                            
      161 +            return _FakeResponse(200, buf.getvalue())         
      162 +                                                              
      163 +        monkeypatch.setattr("hivalidate.cutouts.optical.reques
          +ts.get", fake_get)                                            
      164 +        backend = LegacySurveyBackend(max_retries=5)          
      165 +        result = backend.fetch(POSITION, size_arcsec=26.2)    
      166 +        assert attempts["n"] == 2                             
      167 +        assert result.provenance.startswith("legacy_survey:") 
      168 +                                                              
      169      def test_all_zero_data_raises_cutout_unavailable_not_cover
           ed(self, monkeypatch):
      170          def fake_get(url, timeout):
      171              buf = io.BytesIO()
     ...
      177          with pytest.raises(CutoutUnavailable, match="No .* cov
           erage"):
      178              backend.fetch(POSITION, size_arcsec=26.2)
      179  
      137 -    def test_network_error_raises_cutout_unavailable(self, mon
          -keypatch):                                                    
      180 +    def test_network_error_retries_then_raises_cutout_unavaila
          +ble(self, monkeypatch):                                       
      181 +        monkeypatch.setattr("time.sleep", lambda _: None)     
      182 +                                                              
      183          def fake_get(url, timeout):
      184              raise requests.exceptions.ConnectionError("no rout
           e")
      185  
      186          monkeypatch.setattr("hivalidate.cutouts.optical.reques
           ts.get", fake_get)
      142 -        backend = LegacySurveyBackend()                       
      187 +        backend = LegacySurveyBackend(max_retries=2)          
      188          with pytest.raises(CutoutUnavailable):
      189              backend.fetch(POSITION, size_arcsec=26.2)
      190  

  Ran 1 shell command (ctrl+o to expand)

⏺ 65 tests pass in under 3 seconds with no network hit by default. Let me retry
  the live Legacy Survey test to see if the outage has cleared.

  Ran 1 shell command (ctrl+o to expand)

⏺ Now cutouts/continuum.py tests — a synthetic CI-safe fixture for
  LocalContinuumBackend, plus mocked tests for the untestable RacsCasdaBackend.

⏺ Write(tests/test_cutouts_continuum.py)
  ⎿  Wrote 252 lines to tests/test_cutouts_continuum.py
       1 """Tests for the continuum cutout backends.
       3 `LocalContinuumBackend` is tested here against a small synthetic
       4 test time (fast, CI-safe, no dependency on the real ~50MB `data/
         continuum_image/`
         al file and real
         e the Phase 2 commit
         he WCS/units/error
       8 handling below, not just what the synthetic fixture happens to e
       9 
         als in this
     … +301 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's confirm LocalContinuumBackend (the actual class, not just raw
  mSubimage) works against the real continuum file.

  Ran 1 shell command (ctrl+o to expand)

⏺ Now the backend registry (shared by check-connectivity and, later, dry-run)
  and the CLI itself.

⏺ Write(src/hivalidate/cutouts/registry.py)
  ⎿  Wrote 42 lines to src/hivalidate/cutouts/registry.py
      1 """Builds the configured optical/continuum fallback chains from a
      2 
      3 Kept separate from `base.py` (no config dependency there, so it s
        tays independently
        ckend only means
      5 registering it here, not touching every caller). Used by both
        must build the exact
      7 same chains, or a connectivity check that passed wouldn't mean an
        ything for the batch
      9 """
     … +43 lines (ctrl+o to expand)

⏺ Write(src/hivalidate/cli/check_connectivity.py)
  ⎿  Wrote 55 lines to src/hivalidate/cli/check_connectivity.py
      1 """Preflight connectivity/auth check for every configured cutout 
      2 
      3 Run this before a large `hivalidate-dry-run` batch, especially on
      4 after credentials might have changed -- it's meant to catch a bro
      5 network/proxy issue in seconds, not after it's silently degraded 
        a few hundred
        md section 5,
      7 "Preflight connectivity check"). `hivalidate-dry-run` also runs t
      8 before it starts (see cli/dry_run.py); this command exists so you
      9 standalone, without committing to a full batch run.
     … +55 lines (ctrl+o to expand)
⏺ Update(src/hivalidate/cli/check_connectivity.py)
  ⎿  Added 1 line, removed 1 line
      33          for backend in chain:
      34              ok, message = backend.is_available()
      35              status = "OK" if ok else "FAILED"
      36 -            logger.info("[%s] %s (%s): %s -- %s", status, kind,
         - backend.name, backend.name, message)                          
      36 +            logger.info("[%s] %s backend '%s': %s", status, kin
         +d, backend.name, message)                                      
      37              all_ok = all_ok and ok
      38      return all_ok
      39  

⏺ Write(tests/test_cli_check_connectivity.py)
  ⎿  Wrote 50 lines to tests/test_cli_check_connectivity.py
       1 from pathlib import Path
       2 
       3 from hivalidate.cli import check_connectivity
       4 from hivalidate.config import Config
       5 from hivalidate.cutouts.base import CutoutBackend
       6 
       7 FIXTURES = Path(__file__).parent / "fixtures"
       8 
       9 
      10 class _StubBackend(CutoutBackend):
     … +49 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's actually run the real CLI against configs/SB82605.yaml to see it
  work end-to-end — including correctly reporting the CASDA failure given no
  credentials.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Let's lint and run the full suite once more before committing Phase 2.

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/cutouts/base.py)
  ⎿  Added 3 lines, removed 1 line
       95                  provenance=header.get("HIVPROV", backend_name)
           ,
       96              )
       97  
       98 -    def put(self, source_name: str, backend_name: str, size_ar
          -csec: float, result: CutoutResult) -> None:                   
       98 +    def put(                                                  
       99 +        self, source_name: str, backend_name: str, size_arcsec
          +: float, result: CutoutResult                                 
      100 +    ) -> None:                                                
      101          self.cache_dir.mkdir(parents=True, exist_ok=True)
      102          header = result.wcs.to_header()
      103          header["HIVPROV"] = result.provenance

⏺ Update(src/hivalidate/cutouts/base.py)
  ⎿  Added 3 lines, removed 1 line
      164                      f"Failed after {max_retries} attempts: {ex
           c}"
      165                  ) from exc
      166              wait_s = base_delay_s * (2**attempt)
      167 -            logger.warning("Attempt %d/%d failed (%s), retryin
          -g in %.1fs", attempt + 1, max_retries, exc, wait_s)           
      167 +            logger.warning(                                   
      168 +                "Attempt %d/%d failed (%s), retrying in %.1fs"
          +, attempt + 1, max_retries, exc, wait_s                       
      169 +            )                                                 
      170              time.sleep(wait_s)

⏺ Update(src/hivalidate/cutouts/continuum.py)
  ⎿  Added 3 lines, removed 1 line
       97  
       98          with tempfile.TemporaryDirectory() as tmpdir:
       99              outfile = os.path.join(tmpdir, "cutout.fits")
      100 -            result = mSubimage(str(infile), outfile, position.
          -ra.deg, position.dec.deg, size_deg, size_deg)                 
      100 +            result = mSubimage(                               
      101 +                str(infile), outfile, position.ra.deg, positio
          +n.dec.deg, size_deg, size_deg                                 
      102 +            )                                                 
      103              if result.get("status") != "0":
      104                  raise CutoutUnavailable(f"mSubimage failed: {r
           esult.get('msg', result)}")
      105              with fits.open(outfile) as hdul:

⏺ Update(src/hivalidate/cutouts/continuum.py)
  ⎿  Added 2 lines, removed 1 line
      222                  data = hdul[0].data.copy()
      223                  header = hdul[0].header.copy()
      224  
      225 -        return CutoutResult(data=data, wcs=WCS(header).celesti
          -al, provenance=f"racs_casda:{subset['filename'][0]}")         
      225 +        provenance = f"racs_casda:{subset['filename'][0]}"    
      226 +        return CutoutResult(data=data, wcs=WCS(header).celesti
          +al, provenance=provenance)                                    
      227  
      228      def is_available(self) -> tuple[bool, str]:
      229          try:

⏺ Update(src/hivalidate/cutouts/optical.py)
  ⎿  Added 5 lines, removed 1 line
      107      APPROX_DEC_CEILING_DEG = 34.0
      108  
      109      def __init__(
      110 -        self, layer: str = "ls-dr10", pixscale_arcsec: float =
          - 0.262, band: str = "r", max_retries: int = 5                 
      110 +        self,                                                 
      111 +        layer: str = "ls-dr10",                               
      112 +        pixscale_arcsec: float = 0.262,                       
      113 +        band: str = "r",                                      
      114 +        max_retries: int = 5,                                 
      115      ):
      116          self.layer = layer
      117          self.pixscale_arcsec = pixscale_arcsec

⏺ Update(src/hivalidate/cutouts/optical.py)
  ⎿  Added 3 lines, removed 1 line
      156                  data = hdul[0].data
      157                  header = hdul[0].header
      158          except OSError as exc:
      159 -            raise CutoutUnavailable(f"Legacy Survey response w
          -as not a valid FITS file: {exc}") from exc                    
      159 +            raise CutoutUnavailable(                          
      160 +                f"Legacy Survey response was not a valid FITS 
          +file: {exc}"                                                  
      161 +            ) from exc                                        
      162  
      163          if data is None or not (data != 0).any():
      164              # An all-zero cutout is what the service returns f
           or a position outside

⏺ Now the test files:

⏺ Update(tests/test_cli_check_connectivity.py)
  ⎿  Added 12 lines, removed 4 lines
      26  
      27  
      28  def test_run_returns_true_when_every_backend_is_available(monke
          ypatch, tmp_path):
      29 -    monkeypatch.setattr(check_connectivity, "build_optical_chai
         -n", lambda cfg: [_StubBackend("a", True)])                     
      30 -    monkeypatch.setattr(check_connectivity, "build_continuum_ch
         -ain", lambda cfg: [_StubBackend("b", True)])                   
      29 +    monkeypatch.setattr(                                       
      30 +        check_connectivity, "build_optical_chain", lambda cfg: 
         +[_StubBackend("a", True)]                                      
      31 +    )                                                          
      32 +    monkeypatch.setattr(                                       
      33 +        check_connectivity, "build_continuum_chain", lambda cfg
         +: [_StubBackend("b", True)]                                    
      34 +    )                                                          
      35      assert check_connectivity.run(_config(tmp_path)) is True
      36  
      37  
      38  def test_run_returns_false_if_any_backend_is_unavailable(monkey
          patch, tmp_path):
      35 -    monkeypatch.setattr(check_connectivity, "build_optical_chai
         -n", lambda cfg: [_StubBackend("a", True)])                     
      39      monkeypatch.setattr(
      40 +        check_connectivity, "build_optical_chain", lambda cfg: 
         +[_StubBackend("a", True)]                                      
      41 +    )                                                          
      42 +    monkeypatch.setattr(                                       
      43          check_connectivity, "build_continuum_chain", lambda cfg
          : [_StubBackend("b", False)]
      44      )
      45      assert check_connectivity.run(_config(tmp_path)) is False
      46  
      47  
      48  def test_main_exits_nonzero_when_a_backend_fails(monkeypatch, t
          mp_path, capsys):
      43 -    monkeypatch.setattr(check_connectivity, "build_optical_chai
         -n", lambda cfg: [_StubBackend("a", False)])                    
      49 +    monkeypatch.setattr(                                       
      50 +        check_connectivity, "build_optical_chain", lambda cfg: 
         +[_StubBackend("a", False)]                                     
      51 +    )                                                          
      52      monkeypatch.setattr(check_connectivity, "build_continuum_ch
          ain", lambda cfg: [])
      53      config_path = FIXTURES / "config_mini.yaml"
      54      try:

⏺ Update(tests/test_cutouts_base.py)
  ⎿  Added 1 line, removed 1 line
       99          good = FakeBackend("good", fetch_result=_result("good:
           1"))
      100          result = fetch_with_fallback(POSITION, 30.0, "src", [n
           o_coverage, good])
      101          assert result.provenance == "good:1"
      102 -        assert no_coverage.fetch_call_count == 0  # never call
          -ed -- coverage check short-circuited it                       
      102 +        assert no_coverage.fetch_call_count == 0  # coverage c
          +heck short-circuited it                                       
      103  
      104      def test_raises_with_combined_reasons_when_every_backend_f
           ails(self):
      105          a = FakeBackend("a", fetch_error=CutoutUnavailable("re
           ason a"))

⏺ Update(tests/test_cutouts_continuum.py)
  ⎿  Added 3 lines, removed 1 line
      223  
      224  
      225  class TestRacsCasdaBackendFetchMocked:
      226 -    def test_filters_to_racs_obs_collection_and_filename_patte
          -rn(self, monkeypatch, fake_casda_class):                      
      226 +    def test_filters_to_racs_obs_collection_and_filename_patte
          +rn(                                                           
      227 +        self, monkeypatch, fake_casda_class                   
      228 +    ):                                                        
      229          monkeypatch.setenv("CASDA_USERNAME", "someone@example.
           org")
      230          monkeypatch.delenv("CASDA_PASSWORD", raising=False)
      231          # Mix of a matching RACS row and a non-matching row fr
           om some other survey.

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/cutouts/base.py)
  ⎿  Added 5 lines, removed 1 line
      165                  ) from exc
      166              wait_s = base_delay_s * (2**attempt)
      167              logger.warning(
      168 -                "Attempt %d/%d failed (%s), retrying in %.1fs"
          -, attempt + 1, max_retries, exc, wait_s                       
      168 +                "Attempt %d/%d failed (%s), retrying in %.1fs"
          +,                                                             
      169 +                attempt + 1,                                  
      170 +                max_retries,                                  
      171 +                exc,                                          
      172 +                wait_s,                                       
      173              )
      174              time.sleep(wait_s)

  Ran 1 shell command (ctrl+o to expand)

⏺ Now updating the README's CASDA section with the real, verified mechanism (not
  the naive "just set two env vars" I originally assumed).
  Read 1 file (ctrl+o to expand)

⏺ Update(README.md)
  ⎿  Added 65 lines, removed 8 lines
       35  
       36  The continuum cutout fallback (used when no local continuum mo
           saic covers a field)
       37  queries RACS via `astroquery.casda`, which requires an
       38 -[OPAL](https://opal.atnf.csiro.au/) account. Set credentials a
          -s environment variables                                       
       39 -before running any stage that needs continuum cutouts:        
       38 +[OPAL](https://opal.atnf.csiro.au/) account.                  
       39  
       40 +**Important, and not obvious from astroquery's docs:** `Casda.
          +login()` only accepts a                                       
       41 +`username` -- there is no `password=` parameter. The password 
          +always comes from your                                        
       42 +OS keyring, or an interactive prompt if it isn't there yet. `h
          +ivalidate`'s                                                  
       43 +`RacsCasdaBackend` was built around this, and was **not tested
          + against a real CASDA                                         
       44 +account during development** (no credentials were available) -
          +- verify it yourself                                          
       45 +before relying on it for a real batch run:                    
       46 +                                                              
       47 +### Option A: one-time interactive login (simplest, if your ke
          +yring works)                                                  
       48 +                                                              
       49 +On the machine that will actually run `hivalidate-dry-run` (e.
          +g. the HPC login node,                                        
       50 +since your compute nodes have outbound internet but the creden
          +tial needs to be usable                                       
       51 +from wherever the job runs), run once:                        
       52 +                                                              
       53  ```bash
       54  export CASDA_USERNAME=you@example.com
       43 -export CASDA_PASSWORD=...          # never committed; consider
          - a secrets manager                                            
       44 -                                    # or your shell's own cred
          -ential store instead                                          
       45 -                                    # of a plaintext export in
          - scripts/history                                              
       55 +python3 -c "                                                  
       56 +from astroquery.casda import Casda                            
       57 +casda = Casda()                                               
       58 +ok = casda.login(username='$CASDA_USERNAME', store_password=Tr
          +ue)                                                           
       59 +print('login OK' if ok else 'login FAILED')                   
       60 +"                                                             
       61  ```
       62  
       48 -Never put credentials in a config file that gets committed to 
          -git. Run                                                      
       49 -`hivalidate-check-connectivity --config configs/<field>.yaml` 
          -before a large batch                                          
       50 -job to confirm login and network access work before committing
          - HPC time to it.                                              
       63 +It will prompt for your OPAL password once, then store it in y
          +our OS/user keyring.                                          
       64 +Every subsequent non-interactive run (as long as `$CASDA_USERN
          +AME` is set) will read                                        
       65 +the password from the keyring silently -- you do **not** need 
          +to set `CASDA_PASSWORD`                                       
       66 +for this option.                                              
       67  
       68 +If this raises something like `NoKeyringError`, your login nod
          +e doesn't have a usable                                       
       69 +keyring backend (common on headless Linux systems with no desk
          +top session) -- use                                           
       70 +Option B instead.                                             
       71 +                                                              
       72 +### Option B: `CASDA_PASSWORD` env var (works even with no sys
          +tem keyring)                                                  
       73 +                                                              
       74 +```bash                                                       
       75 +export CASDA_USERNAME=you@example.com                         
       76 +export CASDA_PASSWORD=...          # never committed; treat li
          +ke any other secret                                           
       77 +```                                                           
       78 +                                                              
       79 +If `$CASDA_PASSWORD` is set, `RacsCasdaBackend` seeds a keyrin
          +g entry itself (via the                                       
       80 +plain public `keyring.set_password` API, using the exact servi
          +ce name astroquery's                                          
       81 +own login looks up) immediately before calling `casda.login()`
          +, so it never prompts.                                        
       82 +If your environment has no keyring backend at all, this will f
          +ail with a clear error                                        
       83 +telling you to install and configure `keyrings.alt`'s file-bas
          +ed backend --                                                 
       84 +hivalidate does not silently reconfigure your keyring backend 
          +for you.                                                      
       85 +                                                              
       86 +### Verifying it yourself                                     
       87 +                                                              
       88 +```bash                                                       
       89 +hivalidate-check-connectivity --config configs/<field>.yaml   
       90 +```                                                           
       91 +                                                              
       92 +This runs every configured backend's cheap availability check,
          + including a real                                             
       93 +`casda.login()` call (no cutout download) for `racs_casda`. Lo
          +ok for:                                                       
       94 +                                                              
       95 +```                                                           
       96 +[OK] continuum backend 'racs_casda': OK                       
       97 +```                                                           
       98 +                                                              
       99 +If it instead prints `[FAILED] ... $CASDA_USERNAME is not set`
          +, `... login failed`, or                                      
      100 +the keyring error above, that tells you which of the two optio
          +ns above to fix. Once                                         
      101 +connectivity passes, the actual cutout logic (RACS filtering, 
          +cutout request,                                               
      102 +download) still hasn't been exercised against a real account -
          +- run                                                         
      103 +`hivalidate-dry-run` on a small config with a field known to h
          +ave RACS coverage                                             
      104 +(anything south of Dec +41, per `RacsCasdaBackend.DEC_LIMIT_DE
          +G`) and inspect one of                                        
      105 +the resulting continuum panels before trusting it for a full b
          +atch.                                                         
      106 +                                                              
      107 +Never put credentials in a config file that gets committed to 
          +git.                                                          
      108 +                                                              
      109  ## Pipeline stages
      110  
      111  | Stage | Command | Notes |

⏺ I should add keyring as an explicit direct dependency since our code imports
  it directly, not just transitively via astroquery.

⏺ Update(pyproject.toml)
  ⎿  Added 1 line
      24      "numpy>=1.26",
      25      "requests>=2.31",
      26      "PyYAML>=6.0",
      27 +    "keyring>=24.0",                                           
      28  ]
      29  
      30  [project.optional-dependencies]

⏺ Update(environment.yml)
  ⎿  Added 1 line
      19    - numpy>=1.26
      20    - requests>=2.31
      21    - pyyaml>=6.0
      22 +  - keyring>=24.0                                              
      23    - pytest>=8.0
      24    - ruff>=0.6
      25    - pre-commit>=3.7

  Ran 1 shell command (ctrl+o to expand)

⏺ Let's also update PLAN.md's Phase 2 section to reflect what was actually done,
  then commit.

  Read 1 file (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 29 lines, removed 13 lines
      219    this is real, not over-merging (accepted pairs: median 0.33″
           /0.4 km/s separation;
      220    correctly-rejected sky-close pairs: thousands of km/s apart 
           in velocity).
      221  
      222 -### Phase 2 — Cutout layer                                    
      223 -- [ ] `cutouts/base.py`: fallback-chain abstraction, on-disk c
          -ache, retry/backoff                                           
      224 -      (generalize the existing SkyView retry logic)           
      225 -- [ ] `cutouts/optical.py`: SkyView backend (migrate existing)
          -, Legacy Survey backend                                       
      226 -      (migrate `download_legacy.py` logic)                    
      227 -- [ ] `cutouts/continuum.py`: local-file backend (MontagePy `m
          -Subimage`, using                                              
      228 -      `data/continuum_image/`), RACS/CASDA backend (`astroquer
          -y.casda`) with                                                
      229 -      non-interactive login from env vars / gitignored credent
          -ials file                                                     
      230 -- [ ] Preflight check: CASDA login + trivial query, SkyView/Le
          -gacy Survey reachability                                      
      231 -      — runs automatically at the start of `dry-run`, also ava
          -ilable standalone as                                          
      232 -      `hivalidate check-connectivity`; fails fast with a clear
          - diagnostic                                                   
      233 -- [ ] Footprint/coverage pre-checks for both fallback chains  
      234 -- [ ] Provenance recording — fixes issue #2, addresses fallbac
          -k + caching + footprint decisions                             
      222 +### Phase 2 — Cutout layer [DONE 2026-07-30, one backend unver
          +ified]                                                        
      223 +- [x] `cutouts/base.py`: fallback-chain abstraction, on-disk c
          +ache (FITS, keyed by                                          
      224 +      source/backend/size), retry/backoff (generalized from th
          +e SkyView pattern)                                            
      225 +- [x] `cutouts/optical.py`: `SkyViewBackend` (migrated), `Lega
          +cySurveyBackend`                                              
      226 +      (migrated from `legacy/download_legacy.py`) — **both ver
          +ified live**                                                  
      227 +      (`pytest -m network tests/test_cutouts_optical.py`). Rea
          +l finding while doing                                         
      228 +      so: `legacysurvey.org` returned a real 503 during testin
          +g (confirmed via                                              
      229 +      `curl`, the whole site was down, not our bug) -- exposed
          + that                                                         
      230 +      `LegacySurveyBackend` had no retry/backoff at all, unlik
          +e SkyView; added it.                                          
      231 +- [x] `cutouts/continuum.py`: `LocalContinuumBackend` (Montage
          +Py `mSubimage`) --                                            
      232 +      **verified live** against the real `data/continuum_image
          +/*.fits` and real                                             
      233 +      source positions, including the out-of-footprint error p
          +ath.                                                          
      234 +      `RacsCasdaBackend` (`astroquery.casda`) -- implemented a
          +gainst the literal                                            
      235 +      code examples in astroquery's CASDA docs (not memory), w
          +ith non-interactive                                           
      236 +      login via seeding the OS keyring (astroquery's `login()`
          + has no `password=`                                           
      237 +      parameter -- it only reads from keyring or an interactiv
          +e prompt; this was                                            
      238 +      confirmed by reading astroquery's source, not assumed). 
          +**Not verified live                                           
      239 +      -- no CASDA/OPAL credentials were available in the dev e
          +nvironment.** See                                             
      240 +      README.md "CASDA / RACS access" for exactly how to verif
          +y it.                                                         
      241 +- [x] Preflight check: `hivalidate-check-connectivity`, run fo
          +r real against                                                
      242 +      `configs/SB82605.yaml` -- correctly reported SkyView OK,
          + Legacy Survey FAILED                                         
      243 +      (real live outage), local continuum OK, RACS/CASDA FAILE
          +D with an actionable                                          
      244 +      "$CASDA_USERNAME is not set" message, and exited 1.     
      245 +- [x] Footprint/coverage pre-checks: RACS/CASDA and Legacy Sur
          +vey use a documented                                          
      246 +      declination-limit heuristic (not a full footprint polygo
          +n -- flagged as an                                            
      247 +      approximation in the code, `fetch()` is the real authori
          +ty); local continuum                                          
      248 +      uses the mosaic's actual WCS footprint (`WCS.footprint_c
          +ontains`), which is                                           
      249 +      exact, not a heuristic.                                 
      250 +- [x] Provenance recording — every `CutoutResult` carries whic
          +h backend supplied it.                                        
      251  
      252  ### Phase 3 — Plotting (dry-run, the HPC-safe stage)
      253  - [ ] `plotting.py`: extract the six-panel figure builder from
            `validate_detections.py`

⏺ Now committing Phase 2.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Phase 2 is done and committed. Here's where things stand and how to verify the
  one untested piece yourself:

  Built and verified live: SkyViewBackend, LegacySurveyBackend,
  LocalContinuumBackend, and the hivalidate-check-connectivity preflight check —
  all run for real against actual services/data during development. That live
  run caught two genuine things: legacysurvey.org was actually down (503,
  confirmed independently with curl) while testing, and in the process exposed
  that LegacySurveyBackend had no retry/backoff at all unlike SkyViewBackend —
  fixed and covered by a regression test now.

  Built but unverified: RacsCasdaBackend. No CASDA credentials were available
  here. It's implemented against the literal code examples in astroquery's own
  CASDA docs (not memory), and I read astroquery's actual source to get the
  login mechanism right — worth knowing: Casda.login() has no password parameter
  at all, it only ever reads from the OS keyring or prompts interactively, so
  non-interactive HPC use means seeding the keyring yourself.

  To verify it yourself, README.md's "CASDA / RACS access" section now has the
  full walkthrough, but the short version:

  1. Get an OPAL account if you don't have one.
  2. Either do a one-time interactive login on the machine that'll run the
  pipeline (casda.login(username=..., store_password=True), prompts once, then
  never again), or set CASDA_USERNAME/CASDA_PASSWORD env vars (the backend seeds
  your keyring from these itself).
  3. Run hivalidate-check-connectivity --config configs/SB82605.yaml — look for
  [OK] continuum backend 'racs_casda': OK. If it fails, the error message tells
  you which of the two setup paths to fix (including a specific message if your
  HPC login node has no usable keyring backend at all, which is common).
  4. Connectivity passing only proves login works — the actual RACS
  query/filter/cutout/download flow still hasn't touched a real account, so run
  hivalidate-dry-run on one source in a RACS-covered field (Dec south of +41°)
  afterward and eyeball the continuum panel before trusting it for a full batch.

  Next up is Phase 3 (dry-run plotting, the HPC-safe stage) — want me to keep
  going?

✻ Cooked for 15m 28s

❯ I have a username and passwd for casda. Could we test the casda part now?     

⏺ Let's do this carefully — I don't want your password to ever pass through this
  conversation (chat history, logs). Here's the safe path, using the same
  mechanism I built into the README:

  Ran 1 shell command (ctrl+o to expand)

⏺ Good — this machine uses the macOS Keychain as its keyring backend, so the
  simplest option (one-time interactive login) will work cleanly here.

  Please run this yourself, in your own terminal (not by pasting your password
  to me):

  conda activate base   # or wherever astroquery/keyring are installed
  python3 -c "
  from astroquery.casda import Casda
  casda = Casda()
  ok = casda.login(username='YOUR_OPAL_USERNAME', store_password=True)
  print('login OK' if ok else 'login FAILED')
  "

  It'll prompt you for your OPAL password interactively (hidden input), then
  store it in your Mac's Keychain. After that, your password never needs to be
  typed again — every subsequent casda.login(username=...) call (including all
  my hivalidate code) pulls it from Keychain silently.

  Once that's done and prints login OK, just tell me your username (that's not
  sensitive — it's just an OPAL account email) and I'll run:

  1. hivalidate-check-connectivity to confirm the login path works from my end
  too
  2. A real RacsCasdaBackend.fetch() call against one of the actual source
  positions in data/run_sofia/ to prove the query/filter/cutout/download flow
  genuinely works, not just the login

  That'll fully verify the one backend I couldn't test before.

✻ Cogitated for 53s

❯ jonghwan.rhee@uwa.edu.au                                                      

  Ran 1 shell command (ctrl+o to expand)

⏺ Looks like there's no password stored in the Keychain yet for that username —
  the login attempt fell through to an interactive prompt, which (correctly,
  since my shell has no TTY) just failed cleanly rather than exposing anything.

  Did you get a chance to actually run the one-time login command I gave you,
  and did it print login OK? If not, could you run it now in your own terminal:

  conda activate base
  python3 -c "
  from astroquery.casda import Casda
  casda = Casda()
  ok = casda.login(username='jonghwan.rhee@uwa.edu.au', store_password=True)
  print('login OK' if ok else 'login FAILED')
  "

  Let me know what it prints (login OK/login FAILED, or any error) and I'll
  retry the connectivity check.

✻ Cogitated for 28s

❯ ran it, it printed login OK                                                   

  Ran 1 shell command (ctrl+o to expand)

⏺ Still no password found — let me check the macOS Keychain directly to see
  what's actually there, rather than keep guessing.

  Ran 1 shell command (ctrl+o to expand)
⏺ The Keychain genuinely has no entry for that service — the write didn't
  happen, even though login() itself reported success (which only requires a
  correct username/password, not a successful keyring write). Let me give you a
  more diagnostic version to pinpoint why.

  Ran 1 shell command (ctrl+o to expand)

⏺ Let's isolate whether this is a keyring permissions issue (e.g. a macOS
  Keychain access dialog you might have missed) versus something specific to
  astroquery. Please run this — it tests keyring directly first, independent of
  CASDA:

  Ran 1 shell command (ctrl+o to expand)

⏺ Actually, that diagnostic uses no real credentials — no reason I can't just
  run it myself directly.

  Ran 1 shell command (ctrl+o to expand)

⏺ keyring itself works fine and persists correctly — I could read back what I
  just wrote. So the issue is specific to the CASDA login flow, not the
  underlying keyring mechanism. Let me search more broadly in case the entry
  exists under a slightly different account string.

  Ran 1 shell command (ctrl+o to expand)

⏺ Confirmed: keyring itself works and persists fine in this environment, but
  nothing was ever written under astroquery:casda.csiro.au. So the issue is
  specific to the CASDA login flow — possibly a different Python/environment on
  your end than the one I'm testing in. Can you run this single combined
  diagnostic and paste me the full output verbatim?

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ That last tool call was a no-op — let me just give you the diagnostic
  directly. This one needs your real password typed interactively, so please run
  it yourself and paste back the full output:

  conda activate base
  python3 -c "
  import sys, keyring
  print('python executable:', sys.executable)
  print('keyring backend:', keyring.get_keyring())

  from astroquery.casda import Casda
  casda = Casda()
  ok = casda.login(username='jonghwan.rhee@uwa.edu.au', store_password=True)
  print('login() returned:', ok)

  readback = keyring.get_password('astroquery:casda.csiro.au', 
  'jonghwan.rhee@uwa.edu.au')
  print('keyring readback right after login:', 'FOUND' if readback else 'NOT 
  FOUND')
  "
  security find-generic-password -s "astroquery:casda.csiro.au"

  This will tell us whether python executable matches
  /Users/rhe003/miniforge3/bin/python3 (the same environment I'm testing in) —
  if it's a different path, that's almost certainly the cause: a different
  Python install with its own separate keyring config/backend. It'll also
  confirm right in the same process whether the write actually happened, before
  the OS-level security check even runs.

✻ Churned for 2m 6s

❯ can I type in passwd one-time for this test (don't save it anywhere) if you   
  have a problem with passwd?                                                   

⏺ I'd rather not — even "one-time," it would sit in this conversation's
  transcript/logs, and if I ran it via a shell command it could also land in
  your shell history or be visible to ps while running. That's real exposure for
  a credential tied to your professional account, not just caution for its own
  sake. Let's fix the actual environment mismatch instead — that's the real bug
  here, and it doesn't need your password at all to diagnose.

  Please run just this (harmless, no password needed):

  conda activate base
  python3 -c "
  import sys, keyring
  print('python executable:', sys.executable)
  print('keyring backend:', keyring.get_keyring())
  "

  Compare python executable against what I'm using:
  /Users/rhe003/miniforge3/bin/python3. If yours differs, that's almost
  certainly why the write isn't landing where I'm looking — you're likely on a
  different Python install with its own separate keyring config.

  If it matches, then re-run the actual login in your own terminal (properly
  interactive, password masked, never touches me or this chat):

  python3 -c "
  from astroquery.casda import Casda
  casda = Casda()
  ok = casda.login(username='jonghwan.rhee@uwa.edu.au', store_password=True)
  print('login() returned:', ok)
  "

  Then, still in your own terminal, verify it landed yourself (no password
  involved):

  security find-generic-password -s "astroquery:casda.csiro.au"

  Just tell me the python executable path from the first command, and whether
  that last security command finds an entry or errors — once it's confirmed
  present, I can pick up from there using just $CASDA_USERNAME, no password
  needed on my end at all since we'd both be reading the same Keychain.

✻ Cogitated for 42s

※ recap: Building the hivalidate pipeline; Phases 0-2 are done and committed. We're debugging why your CASDA login didn't persist to Keychain — please run the harmless diagnostic (python path + keyring backend) and tell me the python executable path.

❯ python executable path means path to keychain?                                

⏺ Sorry, that was ambiguous — no, it's not related to the keychain at all.
  "Python executable" just means which Python program on your machine is running
  when you type python3 — since you might have several installed (one from
  conda's base environment, maybe another from macOS itself, another from
  Homebrew, etc.), and each one can have its own separate keyring package with
  its own settings. I want to confirm you're using the exact same one I'm using,
  since a different Python install is my leading theory for why the password
  write isn't landing where I'm checking.

  Concretely, when you run this:

  conda activate base
  python3 -c "import sys; print(sys.executable)"

  it will print a file path like /Users/rhe003/miniforge3/bin/python3 (mine) —
  that's the answer I'm asking for. No password needed for this one at all.

✻ Brewed for 9s

❯ yes it is                                                                     

⏺ Good — that rules out a different Python install being the problem. Let's move
  to the next step: please re-run the actual login in your own terminal (this
  is the one that needs your real password, typed by you, never sent to me):

  conda activate base
  python3 -c "
  from astroquery.casda import Casda
  casda = Casda()
  ok = casda.login(username='jonghwan.rhee@uwa.edu.au', store_password=True)
  print('login() returned:', ok)
  "

  Then, still in your own terminal, check whether it actually landed in the
  Keychain (no password needed for this part):

  security find-generic-password -s "astroquery:casda.csiro.au"

  Two things to watch for while you do this:
  1. Did any macOS popup appear (something like "python3 wants to use your
  confidential information stored in 'login' keychain — Always Allow / Allow /
  Deny")? If so, which did you click, or did it time out / did you not see one
  at all?
  2. Does the security find-generic-password command print keychain details, or
  does it error with "could not be found"?

  Just report back the login() returned: value and the answers to those two
  questions — no need to paste the security command's full output unless you
  want to.

✻ Worked for 19s

❯ this is what I got: login() returned: None                                    

⏺ None is actually a really useful clue — it suggests login() might not be
  returning its result at all, rather than the login itself failing. Let me
  check astroquery's actual source to confirm.

  Ran 2 shell commands (ctrl+o to expand)

⏺ That None is a red herring — I found the actual bug. Let me verify.

  Ran 1 shell command (ctrl+o to expand)
⏺ Found it — and it's genuinely good news underneath. Real keychain entry now
  exists for your account (jonghwan.rhee@uwa.edu.au, freshly timestamped). Since
  astroquery's _login() source only calls keyring.set_password(...) inside the
  if authenticated: branch, this existing entry is strong evidence your login
  actually succeeded — the None was a red herring caused by a real bug in this
  astroquery version: casda.login()'s wrapper method discards its own return
  value and always yields None, regardless of success or failure. Let me confirm
  with casda.authenticated(), which reads the real internal state instead of
  that broken return value — and check whether my own code has the same bug.

  Ran 1 shell command (ctrl+o to expand)

⏺ Confirmed — astroquery's own log says "Authentication successful!" right above
  my code's [FAILED] verdict. This is a real bug in my code:
  RacsCasdaBackend._ensure_login() trusts casda.login()'s return value, which
  this astroquery version always sets to None regardless of outcome (a bug in
  astroquery itself, worked around by checking casda.authenticated() instead).
  Fixing it now.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/cutouts/continuum.py)
  ⎿  Added 10 lines, removed 2 lines
      176  
      177          casda = Casda()
      178          try:
      179 -            authenticated = casda.login(username=username)    
      179 +            # Deliberately not trusting casda.login()'s return
          + value: in the                                                
      180 +            # astroquery version this was verified against (0.
          +4.11), CasdaClass's                                           
      181 +            # login() is an auto-generated wrapper around Quer
          +yWithLogin._login that                                        
      182 +            # discards its return value, so it always evaluate
          +s as None/falsy --                                            
      183 +            # confirmed live 2026-07-30 (astroquery's own log 
          +said "Authentication                                          
      184 +            # successful!" immediately before this code incorr
          +ectly reported                                                
      185 +            # failure, using a real OPAL account). `casda.auth
          +enticated()` reads the                                        
      186 +            # actual internal state `_login` sets and isn't af
          +fected by that bug.                                           
      187 +            casda.login(username=username)                    
      188          except Exception as exc:  # astroquery raises assorted
            exceptions on network/auth failure
      189              raise CutoutUnavailable(f"CASDA login failed: {exc
           }") from exc
      182 -        if not authenticated:                                 
      190 +        if not casda.authenticated():                         
      191              raise CutoutUnavailable(
      192                  "CASDA login failed (bad credentials, or no pa
           ssword available -- "
      193                  "see README.md 'CASDA / RACS access')"

⏺ Now I need to update the test doubles — FakeCasdaInstance didn't have an
  authenticated() method, and my mocked tests were unknowingly relying on the
  same broken assumption my real code just had.

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_cutouts_continuum.py)
  ⎿  Added 11 lines
      103  
      104  
      105  class FakeCasdaInstance:
      106 +    """Mimics the real (buggy, in astroquery 0.4.11) `CasdaCla
          +ss` behaviour found                                           
      107 +    live 2026-07-30: `login()` always returns `None` regardles
          +s of outcome, and only                                        
      108 +    `authenticated()` reflects whether it actually succeeded. 
          +`login_result` here                                           
      109 +    controls what `authenticated()` reports, not `login()`'s r
          +eturn value -- if a                                           
      110 +    test accidentally relies on `login()`'s return value again
          + in the future, it                                            
      111 +    will get `None` here too and fail the same way the real bu
          +g did.                                                        
      112 +    """                                                       
      113 +                                                              
      114      def __init__(self, login_result=True, cutout_urls=None, do
           wnload_files=None):
      115          self._login_result = login_result
      116          self._cutout_urls = cutout_urls or ["http://example.te
           st/cutout.fits"]
     ...
      120  
      121      def login(self, *, username):
      122          self.login_calls.append(username)
      123 +        return None                                           
      124 +                                                              
      125 +    def authenticated(self):                                  
      126          return self._login_result
      127  
      128      def cutout(self, table, *, coordinates, height, width):

⏺ Now let's run the full test suite to confirm the fix works and nothing else
  broke.

  Ran 1 shell command (ctrl+o to expand)

⏺ All mocked tests still pass with the corrected behavior. Now let's re-run the
  real connectivity check to confirm the fix actually works live.

  Ran 1 shell command (ctrl+o to expand)

⏺ CASDA login now correctly shows [OK] — the only remaining [FAILED] is Legacy
  Survey, which is still a real external outage (unrelated to CASDA). Now let's
  finish the job: actually fetch a real RACS cutout for a genuine source from
  data/run_sofia/ to prove the full query→filter→cutout→download flow works, not
  just login.

  Ran 1 shell command (ctrl+o to expand)

⏺ A real bug surfaced by this live test: the RACS cutout comes back as a 4D
  array (1, 1, 74, 74) (degenerate Stokes/frequency axes), while every other
  backend returns clean 2D data — Phase 3's plotting code will expect 2D. Fixing
  this now.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/cutouts/continuum.py)
  ⎿  Added 12 lines, removed 1 line
      227              if not fits_files:
      228                  raise CutoutUnavailable("CASDA cutout download
            contained no FITS file")
      229              with fits.open(fits_files[0]) as hdul:
      230 -                data = hdul[0].data.copy()                    
      230 +                # RACS cutouts come back with degenerate Stoke
          +s/frequency axes, e.g.                                        
      231 +                # shape (1, 1, ny, nx) -- confirmed live 2026-
          +07-30 against a real                                          
      232 +                # cutout. squeeze() drops any size-1 axis, lea
          +ving the 2D image plane                                       
      233 +                # every other backend already returns; if a fu
          +ture cutout genuinely                                         
      234 +                # has more than one Stokes/frequency plane, sq
          +ueeze() leaves those                                          
      235 +                # axes alone and this raises rather than silen
          +tly mis-plotting one.                                         
      236 +                data = hdul[0].data.copy().squeeze()          
      237                  header = hdul[0].header.copy()
      238  
      239 +        if data.ndim != 2:                                    
      240 +            raise CutoutUnavailable(                          
      241 +                f"Expected a 2D cutout after squeezing degener
          +ate axes, got shape {data.shape}"                             
      242 +            )                                                 
      243 +                                                              
      244          provenance = f"racs_casda:{subset['filename'][0]}"
      245          return CutoutResult(data=data, wcs=WCS(header).celesti
           al, provenance=provenance)
      246  

⏺ Now updating the mock to reflect real RACS response shape, and adding a
  regression test.

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_cutouts_continuum.py)
  ⎿  Added 3 lines, removed 2 lines
      132      def download_files(self, urls, *, savedir):
      133          if self._download_files_result is not None:
      134              return self._download_files_result
      135 -        # Write a minimal real FITS so the caller's fits.open 
          -succeeds.                                                     
      135 +        # Shape (1, 1, ny, nx): matches the real degenerate St
          +okes/frequency axes                                           
      136 +        # CASDA's cutout service actually returns, confirmed l
          +ive 2026-07-30.                                               
      137          wcs = WCS(naxis=2)
      138          wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
      139          path = f"{savedir}/racs_cutout.fits"
      139 -        fits.writeto(path, np.ones((10, 10)), wcs.to_header(),
          - overwrite=True)                                              
      140 +        fits.writeto(path, np.ones((1, 1, 10, 10)), wcs.to_hea
          +der(), overwrite=True)                                        
      141          return [path]
      142  
      143  

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_cutouts_continuum.py)
  ⎿  Added 36 lines
      251          result = backend.fetch(FIELD_CENTRE, size_arcsec=60.0)
      252          assert result.provenance == "racs_casda:RACS-DR1_0000+
           00A.fits"
      253  
      254 +    def test_squeezes_degenerate_stokes_and_frequency_axes_to_
          +2d(                                                           
      255 +        self, monkeypatch, fake_casda_class                   
      256 +    ):                                                        
      257 +        # Regression test: a real RACS cutout came back live 2
          +026-07-30 with shape                                          
      258 +        # (1, 1, ny, nx), not the 2D shape every other backend
          + returns. The mock's                                          
      259 +        # default download_files() already reproduces that sha
          +pe (see                                                       
      260 +        # FakeCasdaInstance.download_files) -- this asserts fe
          +tch() squeezes it.                                            
      261 +        monkeypatch.setenv("CASDA_USERNAME", "someone@example.
          +org")                                                         
      262 +        monkeypatch.delenv("CASDA_PASSWORD", raising=False)   
      263 +        backend = RacsCasdaBackend()                          
      264 +        result = backend.fetch(FIELD_CENTRE, size_arcsec=60.0)
      265 +        assert result.data.ndim == 2                          
      266 +        assert result.data.shape == (10, 10)                  
      267 +                                                              
      268 +    def test_non_squeezable_shape_raises_cutout_unavailable(se
          +lf, monkeypatch, fake_casda_class):                           
      269 +        # If a cutout genuinely has more than one Stokes/frequ
          +ency plane, squeeze()                                         
      270 +        # can't reduce it to 2D -- must fail loudly, not silen
          +tly plot one slice.                                           
      271 +        monkeypatch.setenv("CASDA_USERNAME", "someone@example.
          +org")                                                         
      272 +        monkeypatch.delenv("CASDA_PASSWORD", raising=False)   
      273 +                                                              
      274 +        def download_files_with_extra_plane(urls, *, savedir):
      275 +            wcs = WCS(naxis=2)                                
      276 +            wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]          
      277 +            path = f"{savedir}/racs_cutout.fits"              
      278 +            fits.writeto(path, np.ones((2, 10, 10)), wcs.to_he
          +ader(), overwrite=True)                                       
      279 +            return [path]                                     
      280 +                                                              
      281 +        instance = FakeCasdaInstance()                        
      282 +        instance.download_files = download_files_with_extra_pl
          +ane                                                           
      283 +        fake_casda_class.instances_override = instance        
      284 +        monkeypatch.setattr(fake_casda_class, "__new__", lambd
          +a cls: instance)                                              
      285 +                                                              
      286 +        backend = RacsCasdaBackend()                          
      287 +        with pytest.raises(CutoutUnavailable, match="Expected 
          +a 2D cutout"):                                                
      288 +            backend.fetch(FIELD_CENTRE, size_arcsec=60.0)     
      289 +                                                              
      290      def test_no_matching_racs_image_raises_cutout_unavailable(
           self, monkeypatch, fake_casda_class):
      291          monkeypatch.setenv("CASDA_USERNAME", "someone@example.
           org")
      292          monkeypatch.delenv("CASDA_PASSWORD", raising=False)

  Ran 1 shell command (ctrl+o to expand)

⏺ All 16 pass, including both new regression tests. Let me re-run the live fetch
  to confirm the fix against the real CASDA data too.

  Ran 1 shell command (ctrl+o to expand)

⏺ Confirmed fixed against the real service: (74, 74) 2D data now, matching every
  other backend's contract. Let's run the full suite, lint, and update
  PLAN.md/REFERENCES.md before committing.

  Read 1 file, ran 1 shell command (ctrl+o to expand)
⏺ Update(PLAN.md)
  ⎿  Added 17 lines, removed 8 lines
      219    this is real, not over-merging (accepted pairs: median 0.33″
           /0.4 km/s separation;
      220    correctly-rejected sky-close pairs: thousands of km/s apart 
           in velocity).
      221  
      222 -### Phase 2 — Cutout layer [DONE 2026-07-30, one backend unver
          -ified]                                                        
      222 +### Phase 2 — Cutout layer [DONE 2026-07-30, fully verified li
          +ve]                                                           
      223  - [x] `cutouts/base.py`: fallback-chain abstraction, on-disk c
           ache (FITS, keyed by
      224        source/backend/size), retry/backoff (generalized from th
           e SkyView pattern)
      225  - [x] `cutouts/optical.py`: `SkyViewBackend` (migrated), `Lega
           cySurveyBackend`
     ...
      231  - [x] `cutouts/continuum.py`: `LocalContinuumBackend` (Montage
           Py `mSubimage`) --
      232        **verified live** against the real `data/continuum_image
           /*.fits` and real
      233        source positions, including the out-of-footprint error p
           ath.
      234 -      `RacsCasdaBackend` (`astroquery.casda`) -- implemented a
          -gainst the literal                                            
      235 -      code examples in astroquery's CASDA docs (not memory), w
          -ith non-interactive                                           
      236 -      login via seeding the OS keyring (astroquery's `login()`
          - has no `password=`                                           
      237 -      parameter -- it only reads from keyring or an interactiv
          -e prompt; this was                                            
      238 -      confirmed by reading astroquery's source, not assumed). 
          -**Not verified live                                           
      239 -      -- no CASDA/OPAL credentials were available in the dev e
          -nvironment.** See                                             
      240 -      README.md "CASDA / RACS access" for exactly how to verif
          -y it.                                                         
      234 +      `RacsCasdaBackend` (`astroquery.casda`) -- **verified li
          +ve 2026-07-30** with a                                        
      235 +      real OPAL account, after this environment's astroquery (
          +0.4.11) turned out to                                         
      236 +      have a real bug: `CasdaClass.login()` is an auto-generat
          +ed wrapper that                                               
      237 +      discards its own return value, so it always evaluates as
          + `None`/falsy no                                              
      238 +      matter what actually happened. `RacsCasdaBackend._ensure
          +_login()` was                                                 
      239 +      originally written trusting that return value (matching 
          +the astroquery docs'                                          
      240 +      own example) and consequently reported every successful 
          +login as a failure --                                         
      241 +      caught only by testing against a real account, not by th
          +e mocked tests, which                                         
      242 +      had unknowingly encoded the same wrong assumption. Fixed
          + by checking                                                  
      243 +      `casda.authenticated()` instead, which reads the real in
          +ternal state. Also                                            
      244 +      found live: a real RACS cutout comes back with degenerat
          +e Stokes/frequency                                            
      245 +      axes (shape `(1, 1, ny, nx)`, not the 2D shape every oth
          +er backend returns) --                                        
      246 +      `fetch()` now squeezes them, and raises clearly instead 
          +of silently                                                   
      247 +      mis-plotting if a future cutout genuinely has more than 
          +one such plane. Both                                          
      248 +      fixes are covered by regression tests built from the rea
          +l observed shapes/                                            
      249 +      behaviour, not just the original guesses.               
      250  - [x] Preflight check: `hivalidate-check-connectivity`, run fo
           r real against
      251        `configs/SB82605.yaml` -- correctly reported SkyView OK,
            Legacy Survey FAILED
      252        (real live outage), local continuum OK, RACS/CASDA FAILE
           D with an actionable

⏺ Now updating the README's CASDA section to reflect it's verified, while
  keeping the troubleshooting steps (a future user on a different machine could
  hit the same issues).

  Read 1 file (ctrl+o to expand)

⏺ Update(README.md)
  ⎿  Added 17 lines, removed 3 lines
      40  **Important, and not obvious from astroquery's docs:** `Casda.l
          ogin()` only accepts a
      41  `username` -- there is no `password=` parameter. The password a
          lways comes from your
      42  OS keyring, or an interactive prompt if it isn't there yet. `hi
          validate`'s
      43 -`RacsCasdaBackend` was built around this, and was **not tested 
         -against a real CASDA                                           
      44 -account during development** (no credentials were available) --
         - verify it yourself                                            
      45 -before relying on it for a real batch run:                     
      43 +`RacsCasdaBackend` was built around this, and has since been **
         +verified live against                                          
      44 +a real OPAL account (2026-07-30)** -- login, RACS filtering, cu
         +tout request, and                                              
      45 +download all confirmed working end to end. That session also fo
         +und and fixed two real                                         
      46 +bugs, both covered by regression tests now:                    
      47  
      48 +- This environment's astroquery (0.4.11) has its own bug: `logi
         +n()`'s return value is                                         
      49 +  always `None`/falsy regardless of outcome (it discards the re
         +al result internally).                                         
      50 +  `RacsCasdaBackend` checks `casda.authenticated()` instead, wh
         +ich isn't affected.                                            
      51 +  If you see astroquery's own log say "Authentication successfu
         +l!" immediately                                                
      52 +  before `hivalidate-check-connectivity` reports `racs_casda` a
         +s failed, you're on an                                         
      53 +  astroquery version with the same bug and an older `hivalidate
         +` that hadn't been                                             
      54 +  fixed yet -- update.                                         
      55 +- Real RACS cutouts come back with degenerate Stokes/frequency 
         +axes (shape                                                    
      56 +  `(1, 1, ny, nx)`), not 2D like every other backend -- `fetch(
         +)` squeezes these down.                                        
      57 +                                                               
      58 +Still worth doing a one-time check yourself on a new machine/ac
         +count, since keyring                                           
      59 +behaviour is environment-specific (see below):                 
      60 +                                                               
      61  ### Option A: one-time interactive login (simplest, if your key
          ring works)
      62  
      63  On the machine that will actually run `hivalidate-dry-run` (e.g
          . the HPC login node,

⏺ Update(README.md)
  ⎿  Added 10 lines, removed 3 lines
      69  python3 -c "
      70  from astroquery.casda import Casda
      71  casda = Casda()
      72 -ok = casda.login(username='$CASDA_USERNAME', store_password=Tru
         -e)                                                             
      73 -print('login OK' if ok else 'login FAILED')                    
      72 +casda.login(username='$CASDA_USERNAME', store_password=True)   
      73 +# Not 'casda.login(...) ' return value -- some astroquery versi
         +ons (0.4.11,                                                   
      74 +# confirmed) always return None/falsy there regardless of outco
         +me. Check the real                                             
      75 +# state instead:                                               
      76 +print('login OK' if casda.authenticated() else 'login FAILED') 
      77  "
      78  ```
      79  
     ...
      84  
      85  If this raises something like `NoKeyringError`, your login node
           doesn't have a usable
      86  keyring backend (common on headless Linux systems with no deskt
          op session) -- use
      84 -Option B instead.                                              
      87 +Option B instead. If `login OK` prints but a later `security fi
         +nd-generic-password -s                                         
      88 +"astroquery:casda.csiro.au"` (macOS) or equivalent doesn't find
         + an entry, double check                                        
      89 +you're running the same Python install everywhere (`python3 -c 
         +"import sys;                                                   
      90 +print(sys.executable)"`) -- a different Python can mean a compl
         +etely separate keyring                                         
      91 +configuration.                                                 
      92  
      93  ### Option B: `CASDA_PASSWORD` env var (works even with no syst
          em keyring)
      94  

⏺ Now updating the module docstring in continuum.py itself, which still claims
  this is unverified.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/cutouts/continuum.py)
  ⎿  Added 11 lines, removed 8 lines
       7  `data/run_sofia/` during development (see the Phase 2 commit me
          ssage for exact
       8  commands/output) -- both the success and the "outside image foo
          tprint" error paths.
       9  
      10 -`RacsCasdaBackend` could not be tested live during development 
         -(no CASDA/OPAL                                                 
      11 -credentials were available in that environment) -- see README.m
         -d "CASDA / RACS                                                
      12 -access" for how to verify it. Its `query_region`/`cutout`/`down
         -load_files` usage                                              
      13 -matches the literal examples in the astroquery CASDA docs      
      14 -(https://astroquery.readthedocs.io/en/latest/casda/casda.html),
         - not a guess from                                              
      15 -memory, but "matches the docs" and "confirmed working end-to-en
         -d" are not the same                                            
      16 -claim -- treat this backend as unverified until you've run     
      17 -`hivalidate-check-connectivity` successfully yourself.         
      10 +`RacsCasdaBackend` was verified live 2026-07-30 against a real 
         +OPAL account (login,                                           
      11 +RACS filtering, cutout request, and download all confirmed work
         +ing end to end). Its                                           
      12 +`query_region`/`cutout`/`download_files` usage matches the lite
         +ral examples in the                                            
      13 +astroquery CASDA docs (https://astroquery.readthedocs.io/en/lat
         +est/casda/casda.html),                                         
      14 +which is what let two real bugs get caught quickly once real cr
         +edentials were                                                 
      15 +available, rather than being masked by mocks built around the s
         +ame wrong assumptions:                                         
      16 +astroquery 0.4.11's `login()` always returns `None`/falsy regar
         +dless of outcome (this                                         
      17 +backend checks `casda.authenticated()` instead), and a real cut
         +out response has                                               
      18 +degenerate Stokes/frequency axes -- shape `(1, 1, ny, nx)`, not
         + 2D -- which `fetch()`                                         
      19 +now squeezes down. See README.md "CASDA / RACS access" if you n
         +eed to re-verify on a                                          
      20 +new machine/account (keyring behaviour is environment-specific)
         +.                                                              
      21  """
      22  
      23  from __future__ import annotations

⏺ Also updating test_cutouts_continuum.py's module docstring, which makes the
  same now-outdated claim.

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_cutouts_continuum.py)
  ⎿  Added 9 lines, removed 7 lines
       7  message for the exact commands and output; that's what grounds 
          the WCS/units/error
       8  handling below, not just what the synthetic fixture happens to 
          exercise.
       9  
      10 -`RacsCasdaBackend` cannot be tested live (no CASDA/OPAL credent
         -ials in this                                                   
      11 -environment) -- see README.md "CASDA / RACS access" for how to 
         -verify it yourself.                                            
      12 -The tests here mock `astroquery.casda.Casda` to check our own o
         -rchestration logic                                             
      13 -(login/keyring handling, RACS filtering, cutout/download flow) 
         -against the exact                                              
      14 -API shape documented at                                        
      15 -https://astroquery.readthedocs.io/en/latest/casda/casda.html --
         - they cannot catch a                                           
      16 -real API or auth failure, only a regression in how we call it. 
      10 +`RacsCasdaBackend` was verified live 2026-07-30 against a real 
         +OPAL account (see                                              
      11 +cutouts/continuum.py's module docstring and the Phase 2 follow-
         +up commit for what                                             
      12 +that caught: astroquery's `login()` always returning `None`/fal
         +sy, and real cutouts                                           
      13 +having degenerate Stokes/frequency axes). The tests here mock  
      14 +`astroquery.casda.Casda` to check our own orchestration logic (
         +login/keyring                                                  
      15 +handling, RACS filtering, cutout/download flow, the squeeze fix
         +) fast and without                                             
      16 +network access -- `FakeCasdaInstance` is deliberately built to 
         +reproduce both bugs                                            
      17 +(see its docstring) so a regression in either one fails a mocke
         +d test too, not just                                           
      18 +a future live run.                                             
      19  """
      20  
      21  from __future__ import annotations

⏺ Let's do a final lint + full test run, then commit this fix as a follow-up to
  Phase 2.

  Ran 3 shell commands (ctrl+o to expand)

⏺ CASDA is now fully verified — all of Phase 2 has been tested against real
  services. Summary of what that debugging session actually found and fixed:

  1. A real bug in astroquery itself (0.4.11): Casda.login() always returns
  None, regardless of success or failure — it's a wrapper that discards its own
  result. Our code originally trusted that return value (matching astroquery's
  own documented example), so it reported every successful login as a failure.
  Confirmed by astroquery's own log literally saying "Authentication
  successful!" right before our code said otherwise. Fixed by checking
  casda.authenticated() instead.
  2. A real shape mismatch: RACS cutouts come back 4D ((1, 1, 74, 74),
  degenerate Stokes/frequency axes) instead of the 2D shape every other backend
  returns — would have broken Phase 3's plotting. Now squeezed, with a clear
  error if a future cutout genuinely isn't squeezable.

  Both are covered by regression tests built from the real observed behavior,
  and I updated the README's CASDA instructions so a future setup on a different
  machine won't hit the same "login OK vs None" confusion.

  One incidental finding along the way, unrelated to the fix: the keychain
  diagnosis also confirmed keyring itself was never the problem on your end —
  worth knowing if you ever see keyring issues elsewhere, that's not where to
  look first on this machine.

  Phase 2 is now genuinely done, no caveats left. Ready to move on to Phase 3
  (dry-run plotting, the HPC-safe stage) whenever you'd like.

✻ Brewed for 7m 32s

❯ Yes, go ahead with Phase 3                                                    

⏺ Now let's design the plotting layer. First let me re-check the exact cubelet
  file layout and a couple of real header values I'll need.

  Ran 1 shell command (ctrl+o to expand)

⏺ Write(src/hivalidate/plotting.py)
  ⎿  Wrote 256 lines to src/hivalidate/plotting.py
       1 """Six-panel validation figure builder, extracted from
         Figure` out -- no
       3 file I/O, no network, no `plt.show()`). This is what makes dry-r
       4 unattended on an HPC compute node (PLAN.md Phase 3): `hivalidate
       5 only thing that touches `Agg`, opens files, or writes PNGs; this
          module never does.
       7 Panel layout (matches the legacy script's proven layout -- compa
         re against the real
       9 
         pectrum
     … +302 lines (ctrl+o to expand)

⏺ Now let's write tests for plotting.py, using real fixture cubelets plus
  synthetic cutouts (no network needed).

⏺ Write(tests/test_plotting.py)
  ⎿  Wrote 115 lines to tests/test_plotting.py
       1 """Tests for plotting.py. `load_source_cubelets` is tested again
       2 files from the fixture (no synthetic data needed there -- it's p
       3 construction uses real cubelets plus synthetic optical/continuum
          cutouts (no network),
         ion, graceful
         parison, which isn't
         l dry-run output
       7 inspected by eye) is documented in the Phase 3 commit message in
       8 """
      10 from pathlib import Path
     … +140 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ Tests pass. Now let's do the real visual check — generate an actual PNG using
  real cutouts (SkyView + local continuum) for a real source, and look at it.

  Ran 1 shell command (ctrl+o to expand)

⏺ Found a real bug: LocalContinuumBackend returns the full 4D WCS
  (RA/Dec/Stokes/Freq) instead of just the celestial 2D part, unlike every other
  backend. My earlier ad hoc check only looked at data shape, not WCS
  dimensionality — this end-to-end plotting test caught what that missed. Fixing
  it.
  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/cutouts/continuum.py)
  ⎿  Added 8 lines, removed 1 line
      109                  data = hdul[0].data.copy()
      110                  header = hdul[0].header.copy()
      111  
      112 -        return CutoutResult(data=data, wcs=WCS(header), proven
          -ance=f"local:{infile.name}")                                  
      112 +        # mSubimage can leave stale NAXIS3/4 (Stokes/frequency
          +) keywords in the                                             
      113 +        # output header even though the data array it writes i
          +s already 2D --                                               
      114 +        # .celestial strips those so the WCS matches the data'
          +s actual dimensionality                                       
      115 +        # (found live 2026-07-30: plotting a local continuum c
          +utout with the raw,                                           
      116 +        # non-celestial WCS raised "WCS has more than 2 pixel 
          +dimensions").                                                 
      117 +        return CutoutResult(                                  
      118 +            data=data, wcs=WCS(header).celestial, provenance=f
          +"local:{infile.name}"                                         
      119 +        )                                                     
      120  
      121      def is_available(self) -> tuple[bool, str]:
      122          try:

⏺ Let me update the test fixture to include the same 4-axis structure as the
  real data, so this regression would be caught automatically in future.

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_cutouts_continuum.py)
  ⎿  Added 11 lines, removed 6 lines
      39  
      40  @pytest.fixture
      41  def local_continuum_dir(tmp_path):
      42 -    wcs = WCS(naxis=2)                                         
      43 -    wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]                   
      44 -    wcs.wcs.crval = [FIELD_CENTRE.ra.deg, FIELD_CENTRE.dec.deg]
      45 -    wcs.wcs.crpix = [200, 200]                                 
      46 -    wcs.wcs.cdelt = [-PIXSCALE_DEG, PIXSCALE_DEG]              
      42 +    # 4 axes (RA, Dec, Stokes, Freq), matching the real continu
         +um mosaic's structure                                          
      43 +    # -- this is what exposed a real bug live 2026-07-30: fetch
         +() was returning the                                           
      44 +    # raw 4D WCS instead of WCS(header).celestial, which crashe
         +d WCSAxes plotting                                             
      45 +    # ("WCS has more than 2 pixel dimensions") even though the 
         +data array itself was                                          
      46 +    # already 2D. A naxis=2-only fixture wouldn't reproduce thi
         +s.                                                             
      47 +    wcs = WCS(naxis=4)                                         
      48 +    wcs.wcs.ctype = ["RA---SIN", "DEC--SIN", "STOKES", "FREQ"] 
      49 +    wcs.wcs.crval = [FIELD_CENTRE.ra.deg, FIELD_CENTRE.dec.deg,
         + 1, 1.4e9]                                                     
      50 +    wcs.wcs.crpix = [200, 200, 1, 1]                           
      51 +    wcs.wcs.cdelt = [-PIXSCALE_DEG, PIXSCALE_DEG, 1, 1e6]      
      52  
      48 -    data = np.random.default_rng(0).normal(0, 1e-4, size=(400, 
         -400)).astype(np.float32)                                       
      53 +    data = np.random.default_rng(0).normal(0, 1e-4, size=(1, 1,
         + 400, 400)).astype(np.float32)                                 
      54      header = wcs.to_header()
      55      fits.writeto(tmp_path / "mini_continuum.fits", data, header
          , overwrite=True)
      56      return tmp_path

⏺ Now adding an explicit assertion on WCS dimensionality to the fetch test, so
  this regression can't silently return.

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(tests/test_cutouts_continuum.py)
  ⎿  Added 3 lines
      85          assert result.data.ndim == 2
      86          assert 15 <= result.data.shape[0] <= 25  # mSubimage's 
          own rounding, not exact
      87          assert result.provenance == "local:mini_continuum.fits"
      88 +        # Regression check: the WCS must be 2D too (matching th
         +e data), not the raw                                           
      89 +        # 4D WCS from the input mosaic -- this is what broke WC
         +SAxes plotting live.                                           
      90 +        assert result.wcs.pixel_n_dim == 2                     
      91          # WCS round-trips a real sky position back near the fie
          ld centre.
      92          ra, dec = result.wcs.celestial.wcs_pix2world(
      93              [[result.data.shape[1] / 2, result.data.shape[0] / 
          2]], 0

⏺ Now let's run the full suite to make sure this fixture change didn't break
  anything, and re-run the live PNG generation.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 6 lines, removed 2 lines
      142      ax_opt = fig.add_subplot(231, projection=display_wcs)
      143      if optical is not None:
      144          vmin, vmax = _robust_vlim(optical.data)
      145 -        ax_opt.imshow(optical.data, origin="lower", interpolat
          -ion="nearest", cmap="Greys", vmin=vmin, vmax=vmax)            
      146 -        ax_opt.contour(col_density_map, levels=contour_levels_
          -scaled, transform=ax_opt.get_transform(mom0_wcs))             
      145 +        ax_opt.imshow(                                        
      146 +            optical.data, origin="lower", interpolation="neare
          +st", cmap="Greys", vmin=vmin, vmax=vmax                       
      147 +        )                                                     
      148 +        ax_opt.contour(                                       
      149 +            col_density_map, levels=contour_levels_scaled, tra
          +nsform=ax_opt.get_transform(mom0_wcs)                         
      150 +        )                                                     
      151          ellipse = Ellipse(
      152              _beam_location(display_wcs),
      153              cubelets.beam_maj_arcsec / 3600,

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 4 lines, removed 3 lines
      163      else:
      164          ax_opt.set_title("Optical (no cutout available)", size
           =12)
      165      _format_sky_axes(ax_opt, ylabel=True)
      166 -    ax_opt.annotate("Moment 0", (0.75, 0.93), size=12, xycoord
          -s="axes fraction", bbox=_label_bbox())                        
      166 +    _annotate_moment0(ax_opt)                                 
      167  
      168      # --- panel 2: continuum + mom0 contours ---
      169 -    ax_cont = fig.add_subplot(232, projection=(continuum.wcs i
          -f continuum is not None else mom0_wcs))                       
      169 +    cont_wcs = continuum.wcs if continuum is not None else mom
          +0_wcs                                                         
      170 +    ax_cont = fig.add_subplot(232, projection=cont_wcs)       
      171      if continuum is not None:
      172          vmin, vmax = _robust_vlim(continuum.data)
      173          ax_cont.imshow(
     ...
      180      else:
      181          ax_cont.set_title("Continuum (no cutout available)", s
           ize=12)
      182      _format_sky_axes(ax_cont, ylabel=False)
      182 -    ax_cont.annotate("Moment 0", (0.75, 0.93), size=12, xycoor
          -ds="axes fraction", bbox=_label_bbox())                       
      183 +    _annotate_moment0(ax_cont)                                
      184  
      185      # --- panel 3: HI spectrum ---
      186      ax_spec = fig.add_subplot(233)

  Read 1 file (ctrl+o to expand)

⏺ Let me rewrite this whole block cleanly with the helper functions, fixing all
  remaining line-length issues in one pass.

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 25 lines, removed 7 lines
      190      ax_spec.axhline(0, color="grey", ls="dotted")
      191      ax_spec.set_xlabel("Velocity (km/s)", fontsize=14)
      192      ax_spec.set_ylabel("Flux density (Jy)", fontsize=14)
      193 -    ax_spec.annotate("HI Spectrum", (0.75, 0.93), size=12, xyc
          -oords="axes fraction", bbox=_label_bbox(fc="silver"))         
      193 +    ax_spec.annotate(                                         
      194 +        "HI Spectrum", (0.75, 0.93), size=12, xycoords="axes f
          +raction", bbox=_label_bbox(fc="silver")                       
      195 +    )                                                         
      196      ax_spec.grid()
      197      ax_spec_freq = ax_spec.twiny()
      198      ax_spec_freq.invert_xaxis()
     ...
      203  
      204      # --- panel 4: mom0 ---
      205      ax_mom0 = fig.add_subplot(234, projection=display_wcs)
      204 -    ax_mom0.imshow(cubelets.mom0, origin="lower", interpolatio
          -n="nearest", cmap="YlOrBr", transform=ax_mom0.get_transform(mo
          -m0_wcs))                                                      
      205 -    ax_mom0.contour(col_density_map, levels=contour_levels_sca
          -led, transform=ax_mom0.get_transform(mom0_wcs))               
      206 +    ax_mom0.imshow(                                           
      207 +        cubelets.mom0,                                        
      208 +        origin="lower",                                       
      209 +        interpolation="nearest",                              
      210 +        cmap="YlOrBr",                                        
      211 +        transform=ax_mom0.get_transform(mom0_wcs),            
      212 +    )                                                         
      213 +    ax_mom0.contour(                                          
      214 +        col_density_map, levels=contour_levels_scaled, transfo
          +rm=ax_mom0.get_transform(mom0_wcs)                            
      215 +    )                                                         
      216      ax_mom0.set_xlim(ax_opt.get_xlim())
      217      ax_mom0.set_ylim(ax_opt.get_ylim())
      218      _format_sky_axes(ax_mom0, ylabel=True)
      209 -    ax_mom0.annotate("Moment 0", (0.75, 0.93), size=12, xycoor
          -ds="axes fraction", bbox=_label_bbox())                       
      219 +    _annotate_moment0(ax_mom0)                                
      220  
      221      # --- panel 5: mom1 (velocity) ---
      222      ax_mom1 = fig.add_subplot(235, projection=display_wcs)
      223      mom1_image = ax_mom1.imshow(
      214 -        mom1_vel, origin="lower", interpolation="nearest", cma
          -p="jet", transform=ax_mom1.get_transform(mom0_wcs)            
      224 +        mom1_vel,                                             
      225 +        origin="lower",                                       
      226 +        interpolation="nearest",                              
      227 +        cmap="jet",                                           
      228 +        transform=ax_mom1.get_transform(mom0_wcs),            
      229      )
      230      ax_mom1.set_xlim(ax_opt.get_xlim())
      231      ax_mom1.set_ylim(ax_opt.get_ylim())
      232      _format_sky_axes(ax_mom1, ylabel=False)
      219 -    ax_mom1.annotate("Moment 1", (0.75, 0.93), size=12, xycoor
          -ds="axes fraction", bbox=_label_bbox())                       
      233 +    ax_mom1.annotate(                                         
      234 +        "Moment 1", (0.75, 0.93), size=12, xycoords="axes frac
          +tion", bbox=_label_bbox()                                     
      235 +    )                                                         
      236      colorbar = fig.colorbar(mom1_image, ax=ax_mom1, orientatio
           n="vertical", pad=0.01, aspect=30)
      237      colorbar.ax.set_ylabel(r"Velocity (km s$^{-1}$)")
      238  
     ...
      241      freq_c = row["freq"]
      242      line_pixel = cubelets.pv_wcs.wcs_world2pix(0, freq_c * 1e-
           6, 0)
      243      aspect = cubelets.pv_data.shape[1] / cubelets.pv_data.shap
           e[0]
      228 -    ax_pv.imshow(cubelets.pv_data, origin="lower", interpolati
          -on="nearest", cmap="viridis", aspect=aspect)                  
      244 +    ax_pv.imshow(                                             
      245 +        cubelets.pv_data, origin="lower", interpolation="neare
          +st", cmap="viridis", aspect=aspect                            
      246 +    )                                                         
      247      ax_pv.axhline(y=line_pixel[1], color="red", linestyle="--"
           )
      248      ax_pv.coords.grid(color="k", alpha=0.5, linestyle="dashed"
           )
      249      ax_pv.coords[0].set_axislabel("Angular Offset (arcsec)", f
           ontsize=14)

⏺ Now adding the _annotate_moment0 helper next to the other small helpers at the
  bottom of the file.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 4 lines
      277  
      278  def _label_bbox(fc: str = "w") -> dict:
      279      return {"boxstyle": "round", "fc": fc, "alpha": 0.7}
      280 +                                                              
      281 +                                                              
      282 +def _annotate_moment0(ax) -> None:                            
      283 +    ax.annotate("Moment 0", (0.75, 0.93), size=12, xycoords="a
          +xes fraction", bbox=_label_bbox())                            

⏺ Now fixing the two remaining test file line-length issues:

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_plotting.py)
  ⎿  Added 3 lines, removed 4 lines
      18  from hivalidate.cutouts.base import CutoutResult
      19  from hivalidate.plotting import build_validation_figure, load_s
          ource_cubelets
      20  
      21 -FIXTURE_CUBELETS = (                                           
      22 -    Path(__file__).parent / "fixtures" / "run_sofia_mini" / "SB
         -82605_Removal_001_cubelets"                                    
      23 -)                                                              
      24 -FIXTURE_CATALOGUE = Path(__file__).parent / "fixtures" / "run_s
         -ofia_mini" / "SB82605_Removal_001_cat.xml"                     
      21 +_FIXTURE_RUN_DIR = Path(__file__).parent / "fixtures" / "run_so
         +fia_mini"                                                      
      22 +FIXTURE_CUBELETS = _FIXTURE_RUN_DIR / "SB82605_Removal_001_cube
         +lets"                                                          
      23 +FIXTURE_CATALOGUE = _FIXTURE_RUN_DIR / "SB82605_Removal_001_cat
         +.xml"                                                          
      24  
      25  
      26  def _fake_cutout(size=40, ra=315.4611, dec=-55.8032) -> CutoutR
          esult:

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_plotting.py)
  ⎿  Added 3 lines, removed 1 line
      61      def test_produces_six_panel_figure_with_both_cutouts(self):
      62          row = _real_row()
      63          cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB82
          605_Removal_001_1")
      64 -        fig = build_validation_figure(row, cubelets, optical=_f
         -ake_cutout(), continuum=_fake_cutout())                        
      64 +        fig = build_validation_figure(                         
      65 +            row, cubelets, optical=_fake_cutout(), continuum=_f
         +ake_cutout()                                                   
      66 +        )                                                      
      67          assert isinstance(fig, Figure)
      68          assert len(fig.axes) >= 6  # 6 panels + 1 colorbar + 1 
          twinned spectrum axis
      69          assert row["name"] in fig._suptitle.get_text()

⏺ Update(tests/test_plotting.py)
  ⎿  Added 3 lines, removed 1 line
      111          for source_id, name in list(catalogue.id_to_name_mappi
           ng(table).items())[:5]:
      112              row = table[table["id"] == int(source_id)][0]
      113              cubelets = load_source_cubelets(FIXTURE_CUBELETS, 
           f"SB82605_Removal_001_{source_id}")
      114 -            fig = build_validation_figure(row, cubelets, optic
          -al=_fake_cutout(), continuum=_fake_cutout())                  
      114 +            fig = build_validation_figure(                    
      115 +                row, cubelets, optical=_fake_cutout(), continu
          +um=_fake_cutout()                                             
      116 +            )                                                 
      117              assert isinstance(fig, Figure), f"failed for {name
           }"
⏺ Now let's run lint + full suite, then re-run the live PNG generation to
  confirm the fix and actually look at the result.

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 6 lines, removed 1 line
      143      if optical is not None:
      144          vmin, vmax = _robust_vlim(optical.data)
      145          ax_opt.imshow(
      146 -            optical.data, origin="lower", interpolation="neare
          -st", cmap="Greys", vmin=vmin, vmax=vmax                       
      146 +            optical.data,                                     
      147 +            origin="lower",                                   
      148 +            interpolation="nearest",                          
      149 +            cmap="Greys",                                     
      150 +            vmin=vmin,                                        
      151 +            vmax=vmax,                                        
      152          )
      153          ax_opt.contour(
      154              col_density_map, levels=contour_levels_scaled, tra
           nsform=ax_opt.get_transform(mom0_wcs)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 6 lines, removed 1 line
      176      if continuum is not None:
      177          vmin, vmax = _robust_vlim(continuum.data)
      178          ax_cont.imshow(
      179 -            continuum.data, origin="lower", interpolation="nea
          -rest", cmap="afmhot", vmin=vmin, vmax=vmax                    
      179 +            continuum.data,                                   
      180 +            origin="lower",                                   
      181 +            interpolation="nearest",                          
      182 +            cmap="afmhot",                                    
      183 +            vmin=vmin,                                        
      184 +            vmax=vmax,                                        
      185          )
      186          ax_cont.contour(
      187              col_density_map, levels=contour_levels_scaled, tra
           nsform=ax_cont.get_transform(mom0_wcs)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 5 lines, removed 1 line
      201      ax_spec.set_xlabel("Velocity (km/s)", fontsize=14)
      202      ax_spec.set_ylabel("Flux density (Jy)", fontsize=14)
      203      ax_spec.annotate(
      204 -        "HI Spectrum", (0.75, 0.93), size=12, xycoords="axes f
          -raction", bbox=_label_bbox(fc="silver")                       
      204 +        "HI Spectrum",                                        
      205 +        (0.75, 0.93),                                         
      206 +        size=12,                                              
      207 +        xycoords="axes fraction",                             
      208 +        bbox=_label_bbox(fc="silver"),                        
      209      )
      210      ax_spec.grid()
      211      ax_spec_freq = ax_spec.twiny()

  Ran 1 shell command (ctrl+o to expand)

⏺ Lint clean, 92 tests passing. Now let's regenerate the real PNG with the WCS
  fix and actually look at it.

  Ran 1 shell command (ctrl+o to expand)

⏺ Let's look at it.

  Read 1 file (ctrl+o to expand)

⏺ Panel 6 (PV diagram) is broken — I missed a header-rescaling step from the
  legacy script (get_pv_data converts the PV FITS's frequency axis from Hz to
  MHz before building its WCS). Fixing load_source_cubelets.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 7 lines
      73      mom2 = fits.getdata(_path("mom2.fits"))
      74      spec_table = Table.read(_path("spec.txt"), format="ascii")
      75      pv_data, pv_header = fits.getdata(_path("pv.fits"), header=
          True)
      76 +    # The PV FITS's second axis is frequency in Hz; rescale to 
         +MHz before building                                            
      77 +    # its WCS so it matches build_validation_figure's freq_c * 
         +1e-6 (MHz) when                                                
      78 +    # locating the systemic-velocity line and matches the MHz a
         +xis label. Missing                                             
      79 +    # this step was found live 2026-07-30 -- it doesn't raise, 
         +it just silently                                               
      80 +    # produces a PV panel with a nonsensical multi-GHz axis and
         + no visible data.                                              
      81 +    pv_header["CDELT2"] = pv_header["CDELT2"] * 1e-6           
      82 +    pv_header["CRVAL2"] = pv_header["CRVAL2"] * 1e-6           
      83  
      84      return SourceCubelets(
      85          mom0=mom0,

⏺ Now let's regenerate the test image and check the PV panel.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Both fixed panels now match the reference layout well. One cosmetic issue
  remains: the continuum panel's title (full filename) overlaps with the
  spectrum panel's frequency axis label. Let me shorten the panel titles to just
  the backend name — full provenance stays in the manifest for Phase 4.

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 1 line, removed 1 line
      171              transform=ax_opt.get_transform("fk5"),
      172          )
      173          ax_opt.add_patch(ellipse)
      174 -        ax_opt.set_title(f"Optical ({optical.provenance})", si
          -ze=12)                                                        
      174 +        ax_opt.set_title(f"Optical ({_provenance_backend(optic
          +al.provenance)})", size=12)                                   
      175      else:
      176          ax_opt.set_title("Optical (no cutout available)", size
           =12)
      177      _format_sky_axes(ax_opt, ylabel=True)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 1 line, removed 1 line
      193          ax_cont.contour(
      194              col_density_map, levels=contour_levels_scaled, tra
           nsform=ax_cont.get_transform(mom0_wcs)
      195          )
      196 -        ax_cont.set_title(f"Continuum ({continuum.provenance})
          -", size=12)                                                   
      196 +        ax_cont.set_title(f"Continuum ({_provenance_backend(co
          +ntinuum.provenance)})", size=12)                              
      197      else:
      198          ax_cont.set_title("Continuum (no cutout available)", s
           ize=12)
      199      _format_sky_axes(ax_cont, ylabel=False)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 9 lines
      302  
      303  def _annotate_moment0(ax) -> None:
      304      ax.annotate("Moment 0", (0.75, 0.93), size=12, xycoords="a
           xes fraction", bbox=_label_bbox())
      305 +                                                              
      306 +                                                              
      307 +def _provenance_backend(provenance: str) -> str:              
      308 +    """Short form for a panel title, e.g. 'local:some_long_fil
          +ename.fits' -> 'local'.                                       
      309 +    The full string (which backend *and* which specific file/s
          +urvey) is what                                                
      310 +    matters for an audit trail and stays in the dry-run manife
          +st (Phase 3 CLI) --                                           
      311 +    this is purely to stop a long filename from overlapping th
          +e adjacent panel.                                             
      312 +    """                                                       
      313 +    return provenance.split(":", 1)[0]                        

  Ran 1 shell command (ctrl+o to expand)

⏺ No test asserts on the full provenance text in titles, so nothing to update
  there. Let's run tests, lint, and regenerate the image once more to confirm
  the layout fix.

  Read 1 file, ran 2 shell commands (ctrl+o to expand)

⏺ Now let's write the dry-run CLI, which ties everything together: preflight,
  per-source fetch+plot with fault isolation, and the manifest.

⏺ Write(src/hivalidate/cli/dry_run.py)
  ⎿  Wrote 171 lines to src/hivalidate/cli/dry_run.py
       1 """Batch-generate validation plots for every source in the dedup
       2 
         never calls
       4 `plt.show()` or blocks on input, and isolates each source in its
       5 one bad cutout/plot doesn't abort a run that might cover hundred
       6 (PLAN.md issue #8). Writes a manifest (`manifest.json`) that `hi
       7 consumes -- QA never re-fetches cutouts or regenerates figures, 
         it only ever looks at
       9 
         name` first.
     … +201 lines (ctrl+o to expand)

⏺ Update(src/hivalidate/cli/dry_run.py)  ⎿  Removed 1 line
      27  from astropy.coordinates import SkyCoord  # noqa: E402
      28  
      29  from hivalidate import __version__, catalogue, plotting  # noqa
          : E402
      30 -from hivalidate.cli import check_connectivity  # noqa: E402    
      30  from hivalidate.cli._common import base_parser, configure_loggi
          ng  # noqa: E402
      31  from hivalidate.config import Config  # noqa: E402
      32  from hivalidate.cutouts.base import CutoutCache, CutoutUnavaila
          ble, fetch_with_fallback  # noqa: E402

⏺ Now let's write tests, using fake backends via monkeypatching (following the
  same pattern as the connectivity tests).

⏺ Write(tests/test_cli_dry_run.py)
  ⎿  Wrote 158 lines to tests/test_cli_dry_run.py
       1 """Tests for the dry-run CLI stage, using stub cutout backends (
         no network) run
       2 against the real combine -> dedup -> rename output for the run_s
       3 """
       4 
       5 import json
       6 import shutil
       8 
       9 import numpy as np
      10 import pytest
     … +185 lines (ctrl+o to expand)

⏺ That last test would hit real network via the default (unmocked) backend
  chains — let me fix it to use empty chains instead, keeping it fast and
  deterministic.

⏺ Update(tests/test_cli_dry_run.py)
  ⎿  Added 3 lines
      154  def test_run_fails_clearly_if_dedup_and_rename_were_not_run(tm
           p_path, monkeypatch):
      155      config = Config.from_yaml(FIXTURES / "config_mini.yaml")
      156      config.paths.work_dir = tmp_path / "work"
      157 +    # Empty chains so preflight has nothing to check (and make
          +s no network calls) --                                        
      158 +    # this test is about the missing-catalogue guard, not back
          +end availability.                                             
      159 +    _patch_chains(monkeypatch, [], [])                        
      160      with pytest.raises(SystemExit, match="hivalidate-dedup"):
      161          dry_run.run(config)

  Ran 1 shell command (ctrl+o to expand)

⏺ 116 seconds is too slow for what should be a fast test suite — building all
  ~45 deduped-fixture figures 9 times over. Let me truncate the catalogue to a
  handful of sources for these tests specifically, after the real rename step
  has already produced cubelets for everyone.

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_cli_dry_run.py)
  ⎿  Added 10 lines, removed 1 line
      43  @pytest.fixture
      44  def prepared_config(tmp_path):
      45      """Runs combine -> dedup -> rename for real against the fix
          ture, so dry-run has
      46 -    a genuine deduped catalogue and renamed cubelets to work fr
         -om.                                                            
      46 +    a genuine deduped catalogue and renamed cubelets to work fr
         +om -- then truncates                                           
      47 +    the deduped catalogue to 3 rows (after rename has already c
         +opied cubelets for                                             
      48 +    every source) purely so these tests build 3 real figures in
         +stead of ~45 of them.                                          
      49 +    Building a real six-panel WCS figure per source is not chea
         +p; the fixture-size                                            
      50 +    trade-off documented in PLAN.md ("small fixture for fast te
         +sts") applies here                                             
      51 +    too, one level down.                                       
      52      """
      53      config = Config.from_yaml(FIXTURES / "config_mini.yaml")
      54      config.paths.work_dir = tmp_path / "work"
      55      combine.run(config)
      56      dedup.run(config)
      57      rename.run(config)
      58 +                                                               
      59 +    deduped = catalogue.read_votable(config.paths.deduped_catal
         +ogue)                                                          
      60 +    catalogue.write_votable(deduped[:3], config.paths.deduped_c
         +atalogue)                                                      
      61 +                                                               
      62      return config
      63  
      64  

⏺ Now let's run lint and the full suite to confirm speed and correctness.

  Ran 1 shell command (ctrl+o to expand)

⏺ Good — 13.6s now, down from 116s. Let's fix the remaining lint issues.

  Ran 1 shell command (ctrl+o to expand)

⏺ Fixing the remaining line-length issues manually.

⏺ Update(src/hivalidate/cli/dry_run.py)
  ⎿  Added 3 lines, removed 1 line
      70          statuses = [(backend, *backend.is_available()) for back
          end in chain]
      71          for backend, ok, message in statuses:
      72              if not ok:
      73 -                logger.warning("[preflight] %s backend '%s' una
         -vailable: %s", kind, backend.name, message)                    
      73 +                logger.warning(                                
      74 +                    "[preflight] %s backend '%s' unavailable: %
         +s", kind, backend.name, message                                
      75 +                )                                              
      76          if not any(ok for _, ok, _ in statuses):
      77              raise SystemExit(
      78                  f"Every configured {kind} backend is unavailabl
          e -- see warnings above. "

⏺ Update(src/hivalidate/cli/dry_run.py)
  ⎿  Added 4 lines, removed 1 line
      105          source_name = str(row["name"]).replace(" ", "_")
      106          entry: dict = {"name": str(row["name"]), "ra": float(r
           ow["ra"]), "dec": float(row["dec"])}
      107          try:
      108 -            entry.update(_process_one_source(row, source_name,
          - config, optical_chain, continuum_chain, cache))              
      108 +            source_result = _process_one_source(              
      109 +                row, source_name, config, optical_chain, conti
          +nuum_chain, cache                                             
      110 +            )                                                 
      111 +            entry.update(source_result)                       
      112              entry["status"] = "ok"
      113              logger.info("%s: OK", source_name)
      114          except Exception as exc:  # noqa: BLE001 -- deliberate
           ly broad: one bad source must never abort the batch

⏺ Update(src/hivalidate/cli/dry_run.py)
  ⎿  Added 3 lines, removed 1 line
      131          json.dump(manifest, fh, indent=2)
      132  
      133      n_ok = sum(1 for s in sources if s["status"] == "ok")
      134 -    logger.info("Dry-run complete: %d/%d sources OK. Manifest:
          - %s", n_ok, len(sources), manifest_path)                      
      134 +    logger.info(                                              
      135 +        "Dry-run complete: %d/%d sources OK. Manifest: %s", n_
          +ok, len(sources), manifest_path                               
      136 +    )                                                         
      137      return manifest
      138  
      139  

⏺ Now the two remaining test file line-length issues:

  Ran 2 shell commands (ctrl+o to expand)

⏺ Update(tests/test_cli_dry_run.py)
  ⎿  Added 3 lines, removed 1 line
      69  
      70  class TestDryRunHappyPath:
      71      def test_generates_a_png_and_manifest_entry_per_source(self
          , monkeypatch, prepared_config):
      72 -        _patch_chains(monkeypatch, [StubCutoutBackend("optical_
         -stub")], [StubCutoutBackend("cont_stub")])                     
      72 +        _patch_chains(                                         
      73 +            monkeypatch, [StubCutoutBackend("optical_stub")], [
         +StubCutoutBackend("cont_stub")]                                
      74 +        )                                                      
      75          manifest = dry_run.run(prepared_config)
      76  
      77          deduped = catalogue.read_votable(prepared_config.paths.
          deduped_catalogue)

⏺ Update(tests/test_cli_dry_run.py)
  ⎿  Added 3 lines, removed 1 line
      119          assert statuses[str(deduped["name"][0])] == "failed"
      120          assert sum(1 for s in manifest["sources"] if s["status
           "] == "ok") == len(deduped) - 1
      121  
      122 -    def test_cutout_unavailable_from_every_backend_still_produ
          -ces_a_plot(self, monkeypatch, prepared_config):               
      122 +    def test_cutout_unavailable_from_every_backend_still_produ
          +ces_a_plot(                                                   
      123 +        self, monkeypatch, prepared_config                    
      124 +    ):                                                        
      125          # Every backend failing for one image type degrades to
            a blank panel
      126          # (plotting.py), it doesn't fail the source.
      127          class AlwaysFailsBackend(CutoutBackend):

⏺ Update(tests/test_cli_dry_run.py)
  ⎿  Added 3 lines, removed 1 line
      147          with pytest.raises(SystemExit, match="optical"):
      148              dry_run.run(prepared_config)
      149  
      150 -    def test_proceeds_if_at_least_one_backend_in_the_chain_is_
          -available(self, monkeypatch, prepared_config):                
      150 +    def test_proceeds_if_at_least_one_backend_in_the_chain_is_
          +available(                                                    
      151 +        self, monkeypatch, prepared_config                    
      152 +    ):                                                        
      153          _patch_chains(
      154              monkeypatch,
      155              [StubCutoutBackend("down", available=False), StubC
           utoutBackend("up", available=True)],

  Ran 1 shell command (ctrl+o to expand)

⏺ All tests pass, lint is clean. Now let's prove the actual CLI entry point
  works end-to-end for real — using the real 448-source deduped catalogue we
  already have from Phase 1, truncated to a handful of real sources to keep it
  fast, with real SkyView + local continuum cutouts.
  Ran 4 shell commands (ctrl+o to expand)

⏺ All 5 real sources processed successfully end-to-end, correctly falling
  through past the still-down Legacy Survey. Let's look at one of the actual
  generated PNGs to confirm visual quality.

  Read 1 file, listed 2 directories (ctrl+o to expand)

⏺ Excellent — clean, correct output on a real, different source. Let's clean up
  temp files, update PLAN.md, and commit Phase 3.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 27 lines, removed 8 lines
      258        exact, not a heuristic.
      259  - [x] Provenance recording — every `CutoutResult` carries whic
           h backend supplied it.
      260  
      261 -### Phase 3 — Plotting (dry-run, the HPC-safe stage)          
      262 -- [ ] `plotting.py`: extract the six-panel figure builder from
          - `validate_detections.py`                                     
      263 -      into a pure function taking cutouts/catalogue row → figu
          -re, always rendered on                                        
      264 -      `Agg` and saved to disk — no `plt.show()`, no prompts, s
          -afe inside an HPC batch job                                   
      265 -- [ ] Dry-run CLI: runs the preflight connectivity check first
          -, then batch-generates                                        
      266 -      PNGs for all sources plus a manifest (per-source paths, 
          -provenance, catalogue                                         
      267 -      row) that phase 4 consumes                              
      268 -- [ ] Fault isolation per source (issue #8): one failed cutout
          -/plot logs and continues                                      
      261 +### Phase 3 — Plotting (dry-run, the HPC-safe stage) [DONE 202
          +6-07-30]                                                      
      262 +- [x] `plotting.py`: six-panel figure builder (`build_validati
          +on_figure`) extracted                                         
      263 +      as a pure function (`Figure` in, data out -- no file I/O
          +, no `plt.show()`).                                           
      264 +      Verified live by rendering real sources to PNG and inspe
          +cting them, not just                                          
      265 +      unit tests -- caught two real bugs the unit tests (built
          + from the same wrong                                          
      266 +      assumptions as the code) couldn't have: (1) `LocalContin
          +uumBackend` was                                               
      267 +      returning the raw 4D WCS instead of `.celestial`, which 
          +crashed WCSAxes                                               
      268 +      plotting entirely; (2) the PV panel's FITS header needs 
          +its frequency axis                                            
      269 +      rescaled Hz->MHz before building its WCS (a step in the 
          +legacy script's                                               
      270 +      `get_pv_data` that got missed when porting) -- without i
          +t the panel rendered                                          
      271 +      blank with a nonsensical multi-GHz axis instead of faili
          +ng loudly. Both fixed,                                        
      272 +      both covered by regression tests using the real bug cond
          +itions, not the                                               
      273 +      original (wrong) assumptions. Two deliberate improvement
          +s over the legacy                                             
      274 +      script: continuum display range from robust cutout stati
          +stics instead of a                                            
      275 +      hardcoded vmin/vmax that only suited one field, and prov
          +enance annotated on                                           
      276 +      the figure itself.                                      
      277 +- [x] Dry-run CLI (`hivalidate-dry-run`): preflight check firs
          +t (warns if some                                              
      278 +      backends in a chain are down but others still work, abor
          +ts only if an entire                                          
      279 +      chain is unusable), then batch-generates PNGs + `manifes
          +t.json` (per-source                                           
      280 +      status/provenance/error, plus run-level git commit hash 
          ++ version + config                                            
      281 +      name for reproducibility).                              
      282 +- [x] Fault isolation per source (issue #8): one source's cuto
          +ut/plot failure is                                            
      283 +      logged and the batch continues -- verified with a real s
          +abotaged cubelet file.                                        
      284 +- **Ran for real** against 5 real sources from the full 448-so
          +urce deduped catalogue                                        
      285 +  (`data/work/SB82605/`), with real SkyView + real local conti
          +nuum cutouts (Legacy                                          
      286 +  Survey was still down from Phase 2's outage; the preflight c
          +orrectly warned and                                           
      287 +  the batch proceeded on SkyView alone). All 5 produced correc
          +t six-panel PNGs.                                             
      288  
      289  ### Phase 4 — Interactive QA (runs locally, not on HPC)
      290  - [ ] `qa.py`: review loop over the dry-run manifest/PNGs only
            — never regenerates

⏺ Now committing Phase 3.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Phase 3 is done and committed. Summary:

  Built: plotting.py's six-panel figure builder (pure function, Agg-safe) and
  hivalidate-dry-run, which runs the preflight check, batch-generates PNGs + a
  manifest.json with per-source status/provenance and run-level reproducibility
  metadata (git commit, version, config), with per-source fault isolation.

  Two real bugs caught by actually looking at the rendered output, not just
  passing unit tests:
  1. LocalContinuumBackend was returning the full 4D WCS instead of the 2D
  celestial part — crashed WCS-aware plotting outright. Phase 2's ad hoc check
  only looked at data shape, not WCS dimensionality, so it slipped through.
  Fixed, and the test fixture now has real 4-axis structure so this can't
  silently regress again.
  2. The PV diagram panel rendered completely blank with a nonsensical multi-GHz
  axis — I'd missed a step in the legacy script (get_pv_data) that rescales the
  PV FITS's frequency axis from Hz to MHz before building its WCS. Fixed.

  Both are exactly the kind of thing that "port the code, write unit tests, ship
  it" would have missed — the unit tests were built from the same wrong
  assumptions as the code, so only actually rendering and eyeballing a real
  image caught them.

  Verified end-to-end against 5 real sources from the actual 448-source deduped
  catalogue, with real SkyView + real local continuum cutouts, correctly working
  around Legacy Survey's ongoing outage via the fallback chain.

  Next up is Phase 4 (interactive QA — the stage that runs locally, not on HPC,
  and only ever looks at what dry-run already produced). Want me to continue?

✻ Worked for 16m 50s

※ recap: We're refactoring the SoFiA validation pipeline into hivalidate; Phases 0-3 (scaffolding, catalogue, cutouts, dry-run plotting) are built, tested, and committed. Next: build Phase 4, interactive QA.

❯ Yes, go ahead with Phase 4                                                    

⏺ Let me design Phase 4. First, a small shared provenance helper (git commit
  hash, timestamp) so dry_run.py and the new qa.py don't duplicate that logic.

⏺ Write(src/hivalidate/provenance.py)
  ⎿  Wrote 33 lines to src/hivalidate/provenance.py
      1 """Shared reproducibility-metadata helpers, used by both the dry-
        run manifest and
      2 the QA output catalogue (PLAN.md section 5, "Reproducibility meta
        data").
      3 """
      5 from __future__ import annotations
      6 
      7 import subprocess
      8 from datetime import datetime, timezone
      9 from pathlib import Path
     … +27 lines (ctrl+o to expand)

⏺ Now updating dry_run.py to use this shared helper instead of its own copy.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/cli/dry_run.py)
  ⎿  Added 1 line, removed 19 lines
      14  
      15  import json
      16  import logging
      17 -import subprocess                                              
      17  import sys
      19 -from datetime import datetime, timezone                        
      20 -from pathlib import Path                                       
      18  
      19  import matplotlib
      20  
     ...
      32      fetch_with_fallback,
      33  )
      34  from hivalidate.cutouts.registry import build_continuum_chain, 
          build_optical_chain  # noqa: E402
      35 +from hivalidate.provenance import git_commit_hash, now_iso  # n
         +oqa: E402                                                      
      36  
      37  logger = logging.getLogger(__name__)
      38  
      39  
      42 -def _git_commit_hash() -> str:                                 
      43 -    try:                                                       
      44 -        result = subprocess.run(                               
      45 -            ["git", "rev-parse", "HEAD"],                      
      46 -            cwd=Path(__file__).parent,                         
      47 -            capture_output=True,                               
      48 -            text=True,                                         
      49 -            timeout=5,                                         
      50 -        )                                                      
      51 -        if result.returncode == 0:                             
      52 -            return result.stdout.strip()                       
      53 -    except (OSError, subprocess.SubprocessError):              
      54 -        pass                                                   
      55 -    return "unknown"                                           
      56 -                                                               
      57 -                                                               
      40  def _preflight_or_abort(config: Config) -> None:
      41      """Warn (don't abort) if some backends in a chain are down 
          but others in the same
      42      chain still work -- that's exactly what the fallback chain 
          is for. Abort only if

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/cli/dry_run.py)
  ⎿  Added 2 lines, removed 2 lines
      102      manifest = {
      103          "run_info": {
      104              "hivalidate_version": __version__,
      105 -            "hivalidate_git_commit": _git_commit_hash(),      
      105 +            "hivalidate_git_commit": git_commit_hash(),       
      106              "config_field_name": config.field_name,
      107 -            "generated_at": datetime.now(timezone.utc).isoform
          -at(),                                                         
      107 +            "generated_at": now_iso(),                        
      108          },
      109          "sources": sources,
      110      }

⏺ Now let's confirm dry_run.py still passes lint/tests after the refactor before
  moving on.

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's write the core qa.py module — the state machine, catalogue merge,
  and default (real) prompt/display implementations.

⏺ Write(src/hivalidate/qa.py)
  ⎿  Wrote 194 lines to src/hivalidate/qa.py
       1 """Interactive QA review, decoupled from dry-run (PLAN.md Phase 
       2 manifest and PNGs `hivalidate-dry-run` already produced -- never
       3 or regenerates a figure. This is what lets QA run on a normal ma
       4 (a laptop) while dry-run ran unattended on an HPC compute node w
       5 
       6 The review loop, catalogue merge, and flag numbering all live in
       7 CLI) so they're directly unit-testable; `display_fn`/`prompt_fn`
       8 injected so tests never need a real display or real keyboard inp
       9 `hivalidate.cli.qa` supplies the real (matplotlib window + termi
      10 versions for actual use.
     … +222 lines (ctrl+o to expand)
⏺ Update(src/hivalidate/qa.py)
  ⎿  Added 1 line, removed 1 line
      18  
      19  import numpy as np
      20  
      21 -from hivalidate import catalogue                               
      21 +from hivalidate import __version__, catalogue                  
      22  from hivalidate.config import Config
      23  from hivalidate.provenance import git_commit_hash, now_iso
      24  

⏺ Update(src/hivalidate/qa.py)
  ⎿  Added 1 line, removed 1 line
      136      catalogue.write_votable(deduped, config.paths.qa_dir / "va
           lidated_cat.xml")
      137  
      138      run_info = {
      139 -        "hivalidate_version": __import__("hivalidate").__versi
          -on__,                                                         
      139 +        "hivalidate_version": __version__,                    
      140          "hivalidate_git_commit": git_commit_hash(),
      141          "config_field_name": config.field_name,
      142          "generated_at": now_iso(),

⏺ Now the Paths dataclass in config.py needs a qa_dir property — let me check
  it's already there.

  Ran 1 shell command (ctrl+o to expand)

⏺ Good, already there. Now the CLI wrapper.

⏺ Write(src/hivalidate/cli/qa.py)
  ⎿  Wrote 47 lines to src/hivalidate/cli/qa.py
       1 """Interactive review of dry-run output. Run this locally (on a 
       2 display), not on HPC -- see `hivalidate.qa`'s module docstring f
         or why. Run
       4 
       5 Resumable: Ctrl-C or the 'q' (save & quit) flag at any point sav
       6 reviewed so far; re-running this command picks up where you left
          off. 'b' (back)
          restarting.
       8 """
      10 from __future__ import annotations
     … +44 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's write tests, reusing the same fixture pattern established in the
  dry-run tests (real combine→dedup→rename→dry-run, truncated for speed).

⏺ Write(tests/test_qa.py)
  ⎿  Wrote 206 lines to tests/test_qa.py
      1 """Tests for the QA review state machine and catalogue merge, usi
        ng a real manifest
        nst the fixture.
      3 `display_fn`/`prompt_fn`/`close_fn` are faked -- see hivalidate/q
        a.py's module
        real display or
      5 keyboard.
      6 """
      8 import math
      9 from pathlib import Path
     … +259 lines (ctrl+o to expand)

⏺ I traced through the back-navigation test by hand and found it would run out
  of scripted responses (hit StopIteration) before reaching a natural stop — let
  me fix it with an explicit quit at the end.

⏺ Update(tests/test_qa.py)
  ⎿  Added 4 lines, removed 2 lines
      144  class TestRunQaSessionBack:
      145      def test_back_re_presents_the_previous_source_and_lets_it_
           be_overwritten(self, prepared_config):
      146          seen, display_fn = _recording_display()
      147 -        # Flag the 1st as 't', flag the 2nd as 'f' by mistake,
          - go back, correct it to 'u'.                                  
      148 -        responses = [("t", "first"), ("f", "oops"), ("b", ""),
          - ("u", "corrected")]                                          
      147 +        # Flag the 1st as 't', flag the 2nd as 'f' by mistake,
          + go back, correct it to                                       
      148 +        # 'u', then quit -- ends the session at a known point 
          +rather than needing to                                        
      149 +        # script responses for the remaining sources too.     
      150 +        responses = [("t", "first"), ("f", "oops"), ("b", ""),
          + ("u", "corrected"), ("q", "")]                               
      151          results = qa.run_qa_session(prepared_config, _scripted
           (responses), display_fn, _noop_close)
      152  
      153          manifest = qa.load_manifest(prepared_config.paths.dry_
           run_dir)

⏺ Now let's run the tests.

  Ran 1 shell command (ctrl+o to expand)

⏺ Let me clean up that masked-value warning in the test (cosmetic, but worth
  being precise about).

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_qa.py)
  ⎿  Added 5 lines, removed 4 lines
      178          )
      179  
      180          validated = catalogue.read_votable(prepared_config.pat
           hs.qa_dir / "validated_cat.xml")
      181 -        n_reviewed = sum(1 for v in validated["qa"] if not mat
          -h.isnan(v))                                                   
      182 -        n_unreviewed = sum(1 for v in validated["qa"] if math.
          -isnan(v))                                                     
      181 +        qa_values = [float(v) for v in validated["qa"]]  # VOT
          +able round-trips NaN as masked                                
      182 +        n_reviewed = sum(1 for v in qa_values if not math.isna
          +n(v))                                                         
      183 +        n_unreviewed = sum(1 for v in qa_values if math.isnan(
          +v))                                                           
      184          assert n_reviewed == 2
      185          assert n_unreviewed == 2
      185 -        for row in validated:                                 
      186 -            if math.isnan(row["qa"]):                         
      186 +        for value, row in zip(qa_values, validated):          
      187 +            if math.isnan(value):                             
      188                  assert row["qa_comment"] == ""
      189  
      190      def test_reviewed_sources_carry_provenance_from_manifest(s
           elf, prepared_config):

⏺ Now let's run lint and the full suite.

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/cli/qa.py)
  ⎿  Added 3 lines, removed 4 lines
      20  
      21  
      22  def run(config: Config) -> dict:
      23 -    if not (config.paths.dry_run_dir / "manifest.json").exists(
         -):                                                             
      24 -        raise SystemExit(                                      
      25 -            f"{config.paths.dry_run_dir / 'manifest.json'} does
         - not exist -- run hivalidate-dry-run first"                    
      26 -        )                                                      
      23 +    manifest_path = config.paths.dry_run_dir / "manifest.json" 
      24 +    if not manifest_path.exists():                             
      25 +        raise SystemExit(f"{manifest_path} does not exist -- ru
         +n hivalidate-dry-run first")                                   
      26      return qa.run_qa_session(
      27          config,
      28          prompt_fn=qa.default_prompt,

⏺ Update(src/hivalidate/qa.py)
  ⎿  Added 6 lines, removed 1 line
      146      with open(config.paths.qa_dir / "run_info.json", "w") as f
           h:
      147          json.dump(run_info, fh, indent=2)
      148  
      149 -    logger.info("Wrote %s (%d/%d reviewed)", config.paths.qa_d
          -ir / "validated_cat.xml", len(results), len(deduped))         
      149 +    logger.info(                                              
      150 +        "Wrote %s (%d/%d reviewed)",                          
      151 +        config.paths.qa_dir / "validated_cat.xml",            
      152 +        len(results),                                         
      153 +        len(deduped),                                         
      154 +    )                                                         
      155      return deduped
      156  
      157  

⏺ Update(tests/test_qa.py)
  ⎿  Added 2 lines, removed 1 line
      131  
      132      def test_resuming_skips_already_reviewed_sources_without_d
           isplaying_them(self, prepared_config):
      133          seen1, display_fn1 = _recording_display()
      134 -        qa.run_qa_session(prepared_config, _scripted([("t", ""
          -), ("f", ""), ("q", "")]), display_fn1, _noop_close)          
      134 +        responses1 = _scripted([("t", ""), ("f", ""), ("q", ""
          +)])                                                           
      135 +        qa.run_qa_session(prepared_config, responses1, display
          +_fn1, _noop_close)                                            
      136  
      137          seen2, display_fn2 = _recording_display()
      138          responses = [("u", ""), ("d", "")]  # only the 2 remai
           ning sources

⏺ Update(tests/test_qa.py)
  ⎿  Removed 1 line
      204  
      205          validated = catalogue.read_votable(prepared_config.pat
           hs.qa_dir / "validated_cat.xml")
      206          qa_by_name = {str(row["name"]): row["qa"] for row in v
           alidated}
      207 -        manifest = qa.load_manifest(prepared_config.paths.dry_
          -run_dir)                                                      
      207          results = qa.load_qa_results(prepared_config.paths.qa_
           dir)
      208          for name, entry in results.items():
      209              assert qa_by_name[name] == qa.FLAG_TO_NUMERIC[entr
           y["qa_flag"]]

  Ran 1 shell command (ctrl+o to expand)
⏺ Let's do a real end-to-end check using genuine (non-fixture) data. First I
  need to regenerate the real dry-run output from Phase 3 (I cleaned it up
  afterward).

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's run a real (scripted) QA session against this real manifest, and
  separately confirm default_display/default_close work on a real PNG without
  crashing.

  Ran 4 shell commands (ctrl+o to expand)

⏺ Real session completed end-to-end. Let's check the resulting validated_cat.xml
  and run_info.json.

  Ran 1 shell command (ctrl+o to expand)

⏺ This confirms the full pipeline works correctly end-to-end on real data —
  numeric flags match the documented convention, comments and provenance
  preserved, git commit hash correctly recorded. Let's clean up and finalize.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 25 lines, removed 7 lines
      286    Survey was still down from Phase 2's outage; the preflight c
           orrectly warned and
      287    the batch proceeded on SkyView alone). All 5 produced correc
           t six-panel PNGs.
      288  
      289 -### Phase 4 — Interactive QA (runs locally, not on HPC)       
      290 -- [ ] `qa.py`: review loop over the dry-run manifest/PNGs only
          - — never regenerates                                          
      291 -      cutouts or figures, so it has no `Agg`/HPC constraint an
          -d can use a normal                                            
      292 -      interactive matplotlib backend or a simple image viewer 
      293 -- [ ] Resumable, incremental per-source save (fixes issue #7),
          - optional comment field,                                      
      294 -      back option                                             
      295 -- [ ] Output catalogue gets qa flag + provenance + comment + r
          -eproducibility metadata                                       
      289 +### Phase 4 — Interactive QA (runs locally, not on HPC) [DONE 
          +2026-07-30, one part user-only-verifiable]                    
      290 +- [x] `qa.py`: review loop (`run_qa_session`) over the dry-run
          + manifest/PNGs only --                                        
      291 +      never regenerates cutouts or figures. `display_fn`/`prom
          +pt_fn`/`close_fn` are                                         
      292 +      injected, so the state machine, incremental persistence,
          + and catalogue merge                                          
      293 +      are all fully unit-tested without a real display or keyb
          +oard; `default_display`                                       
      294 +      deliberately does not call `matplotlib.use(...)` (unlike
          + dry-run's forced                                             
      295 +      `Agg`), since this is meant to run somewhere with an act
          +ual screen.                                                   
      296 +- [x] Resumable, incremental per-source save (fixes issue #7):
          + every review is                                              
      297 +      written to `qa_results.json` immediately, and a second s
          +ession skips anything                                         
      298 +      already in it without re-displaying. `b` (back) removes 
          +and re-presents the                                           
      299 +      previous source; `q` saves and stops early. All three ve
          +rified against real                                           
      300 +      manifest/PNG data (not just the fixture), including a re
          +al back-correction.                                           
      301 +- [x] Output catalogue (`validated_cat.xml`): numeric `qa` fla
          +g (legacy convention:                                         
      302 +      0/1/2/3 = false/true/uncertain/duplicate), free-text `qa
          +_comment`, optical/                                           
      303 +      continuum provenance and dry-run status pulled from the 
          +manifest, `NaN`/empty                                         
      304 +      for anything not yet reviewed (safe to inspect after a p
          +artial session).                                              
      305 +      `run_info.json` alongside it carries the same reproducib
          +ility metadata as the                                         
      306 +      dry-run manifest (git commit, version, config name, revi
          +ew counts).                                                   
      307 +- **What's verified vs. not**: the review *logic* (state machi
          +ne, persistence,                                              
      308 +  catalogue merge, `default_display`/`default_close` not crash
          +ing on a real PNG) was                                        
      309 +  run for real against a real 5-source manifest from Phase 3 -
          +- git commit hash,                                            
      310 +  provenance, and all four flags round-tripped correctly into 
          +`validated_cat.xml`.                                          
      311 +  The actual interactive experience (a real matplotlib window 
          +plus blocking                                                 
      312 +  terminal `input()`) can't be exercised by an automated tool 
          +the way SkyView or                                            
      313 +  CASDA calls could -- that part needs a human running `hivali
          +date-qa` themselves.                                          
      314  
      315  ### Phase 5 — Post-processing
      316  - [ ] `postprocess.py`: migrate `create_validation_csv.py`, `e
           xtract_true_cubelets.py`,

⏺ Now let's commit Phase 4.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Phase 4 is done and committed. Summary:

  Built: qa.py's review state machine (resume, back-correction, quit,
  incremental save-per-review) and hivalidate-qa, which only ever reads what
  dry-run already produced — never touches a cutout or figure. Output is
  validated_cat.xml with a numeric qa flag, free-text comments, and provenance
  carried through, plus run_info.json for reproducibility.

  What I could verify myself vs. what needs you: I ran the actual review logic
  end-to-end against a real 5-source manifest from Phase 3 (not just the test
  fixture) — scripted responses exercising all four flags plus a
  back-correction, and confirmed the numeric flags, comments, provenance, and
  git commit hash all round-tripped correctly into validated_cat.xml. I also
  confirmed default_display/default_close don't crash on a real PNG. What I
  genuinely can't verify from here is the actual interactive experience — a real
  matplotlib window popping up plus blocking on your keyboard input — since
  that needs an actual human at an actual terminal, not something an automated
  tool call can drive. That's flagged clearly in PLAN.md, not silently assumed
  to work.

  Small refactor along the way: factored the git-commit-hash/timestamp logic out
  of dry_run.py into a shared provenance.py since qa.py needed the same thing —
  avoided duplicating it.

  Remaining phases: Phase 5 (post-processing — migrating the
  create-CSV/extract-cubelets/mosaic scripts), Phase 6 (full 45-run end-to-end
  validation), Phase 7 (polish/docs). Want me to continue with Phase 5?

✻ Churned for 12m 19s

❯ Yes, go ahead with Phase 5                                                    

⏺ Let's check what post-processing artifacts we're working with — particularly
  whether the full-field mom0.fits mosaic reference still exists.

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's design postprocess.py. First I need to add a field_mosaic path to
  the config (for the full-field mom0.fits reference the mosaic step needs).

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/config.py)
  ⎿  Added 4 lines
      66      work_dir: Path
      67      continuum_local_dir: Path | None = None
      68      gama_catalogue: Path | None = None
      69 +    #: Full-field moment-0 mosaic (SoFiA's own output, e.g. `ru
         +n_sofia/mom0.fits`),                                           
      70 +    #: used only by Phase 5 postprocess to place true-flagged d
         +etections in context.                                          
      71 +    #: Optional -- the mosaic step is skipped (not an error) if
         + unset.                                                        
      72 +    field_mosaic: Path | None = None                           
      73  
      74      @property
      75      def combined_catalogue(self) -> Path:

⏺ Now updating Config.from_dict to parse this new field, and validate() to check
  it if set.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/config.py)
  ⎿  Added 1 line
      133                  work_dir=resolve(raw_paths["work_dir"]),
      134                  continuum_local_dir=resolve(raw_paths.get("con
           tinuum_local_dir")),
      135                  gama_catalogue=resolve(raw_paths.get("gama_cat
           alogue")),
      136 +                field_mosaic=resolve(raw_paths.get("field_mosa
          +ic")),                                                        
      137              )
      138          except KeyError as exc:
      139              raise ValueError(f"Config 'paths' section is missi
           ng required key: {exc}") from exc

⏺ Update(src/hivalidate/config.py)
  ⎿  Added 2 lines
      168              )
      169          if self.paths.gama_catalogue is not None and not self.
           paths.gama_catalogue.is_file():
      170              raise ValueError(f"paths.gama_catalogue does not e
           xist: {self.paths.gama_catalogue}")
      171 +        if self.paths.field_mosaic is not None and not self.pa
          +ths.field_mosaic.is_file():                                   
      172 +            raise ValueError(f"paths.field_mosaic does not exi
          +st: {self.paths.field_mosaic}")                               

⏺ Let's run the config tests to confirm the new optional field doesn't break
  anything, then update configs/SB82605.yaml.
  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Update(configs/SB82605.yaml)
  ⎿  Added 3 lines
      12    # No GAMA catalogue shipped with this example dataset -- leav
          e unset (null) rather
      13    # than pointing at a path that doesn't exist; cross-matching 
          is skipped when unset.
      14    gama_catalogue: null
      15 +  # Full-field moment-0 mosaic, used by Phase 5 postprocess to 
         +place true-flagged                                             
      16 +  # detections in context. Optional -- the mosaic step is skipp
         +ed if unset.                                                   
      17 +  field_mosaic: ../data/run_sofia/mom0.fits                    
      18  
      19  dedup:
      20    sep_arcsec: 30.0

⏺ Let me verify reproject's actual API before writing code against it, same as I
  did for MontagePy and astroquery.

  Ran 1 shell command (ctrl+o to expand)

⏺ Write(src/hivalidate/postprocess.py)
  ⎿  Wrote 94 lines to src/hivalidate/postprocess.py
       1 """Post-validation artifacts built from the QA output (`validate
       2 
         ate_validation_csv.py`,
         urces were "true" by
         e SoFiA catalogue,
       6   because the legacy interactive script never wrote the qa flag 
       7   alongside the catalogue. `validated_cat.xml` already has the `
       8 - A directory of just their cubelets -- replaces `legacy/extract
       9 - A mosaic FITS of just their moment-0 maps, reprojected onto th
      10   replaces `legacy/mosaic_
     … +107 lines (ctrl+o to expand)

⏺ Now the CLI wrapper.

⏺ Write(src/hivalidate/cli/postprocess.py)
  ⎿  Wrote 60 lines to src/hivalidate/cli/postprocess.py
       1 """Build post-validation artifacts (CSV, cubelets, mosaic) for t
         rue-flagged sources.
       3 Run `hivalidate-qa` first (or at least far enough into a session
          that some sources
       4 are flagged true -- this can be run against a partially-reviewed
       5 """
       6 
       7 from __future__ import annotations
       9 import logging
      10 import sys
     … +61 lines (ctrl+o to expand)

⏺ Now let's write tests, reusing the established fixture patterns.

⏺ Write(tests/test_postprocess.py)
  ⎿  Wrote 177 lines to tests/test_postprocess.py
      1 """Tests for postprocess.py. filter_by_qa/write_validation_csv/ex
        tract_cubelets use
        s other CLI tests).
      3 build_mosaic uses small synthetic FITS (fast, no dependency on th
        e real ~50MB
        y, see the Phase 5
      5 commit message.
      6 """
      8 import csv
      9 from pathlib import Path
     … +201 lines (ctrl+o to expand)

⏺ Let's run these tests.

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's test the CLI wrapper itself, building a real validated_cat.xml via
  the same fixture pipeline used in Phase 4's tests.

⏺ Write(tests/test_cli_postprocess.py)
  ⎿  Wrote 116 lines to tests/test_cli_postprocess.py
       1 """End-to-end test of the postprocess CLI stage, building a real
          validated_cat.xml
       2 via combine -> dedup -> rename -> dry-run -> qa (stubbed cutouts
       3 responses, no network, no real display) against the fixture.
       4 """
       5 
       6 from pathlib import Path
       8 import numpy as np
       9 import pytest
      10 from astropy.io import fits
     … +133 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ All 5 pass on the first try. Now let's run lint and the full suite.

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/cli/postprocess.py)
  ⎿  Added 3 lines, removed 1 line
      36      n_copied = postprocess.extract_cubelets(
      37          config.paths.renamed_cubelets_dir, true_cubelets_dir, n
          ames
      38      )
      39 -    logger.info("Copied %d cubelet files for %d true sources to
         - %s", n_copied, len(names), true_cubelets_dir)                 
      39 +    logger.info(                                               
      40 +        "Copied %d cubelet files for %d true sources to %s", n_
         +copied, len(names), true_cubelets_dir                          
      41 +    )                                                          
      42  
      43      if config.paths.field_mosaic is None:
      44          logger.info("No paths.field_mosaic configured -- skippi
          ng mosaic step")

⏺ Update(tests/test_postprocess.py)
  ⎿  Added 5 lines, removed 1 line
      34  def _fake_validated_table():
      35      return Table(
      36          {
      37 -            "name": ["SoFiA J000000.00-300000.0", "SoFiA J00000
         -1.00-300000.0", "SoFiA J000002.00-300000.0"],                  
      37 +            "name": [                                          
      38 +                "SoFiA J000000.00-300000.0",                   
      39 +                "SoFiA J000001.00-300000.0",                   
      40 +                "SoFiA J000002.00-300000.0",                   
      41 +            ],                                                 
      42              "ra": [0.0, 0.001, 0.002],
      43              "qa": [1.0, 0.0, float("nan")],
      44          }

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's do the real end-to-end check with actual data, continuing where
  Phase 3/4's real tests left off.

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's run the real postprocess CLI against the real full-field mom0.fits.

  Ran 1 shell command (ctrl+o to expand)

⏺ Let's check the CSV content and actually look at the mosaic visually.

  Read 1 file, ran 2 shell commands (ctrl+o to expand)
⏺ Confirmed — all 3 true detections correctly placed at their real sky positions
  within the full-field mosaic. Let's clean up and finalize.

  Ran 1 shell command (ctrl+o to expand)

⏺ Now updating PLAN.md.

  Read 1 file (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 23 lines, removed 4 lines
      312    terminal `input()`) can't be exercised by an automated tool 
           the way SkyView or
      313    CASDA calls could -- that part needs a human running `hivali
           date-qa` themselves.
      314  
      315 -### Phase 5 — Post-processing                                 
      316 -- [ ] `postprocess.py`: migrate `create_validation_csv.py`, `e
          -xtract_true_cubelets.py`,                                     
      317 -      `mosaic_sofia_true_detections.py`, aligning directory na
          -ming end-to-end so no                                         
      318 -      manual renaming is needed between stages (fixes issue #4
          -)                                                             
      315 +### Phase 5 — Post-processing [DONE 2026-07-30]               
      316 +- [x] `postprocess.py`: `filter_by_qa` + `write_validation_csv
          +` (replaces                                                   
      317 +      `legacy/create_validation_csv.py` -- much simpler now, s
          +ince it no longer needs                                       
      318 +      to reverse-engineer which sources are "true" from a dire
          +ctory of PNG                                                  
      319 +      filenames; `validated_cat.xml` already carries the `qa` 
          +flag directly),                                               
      320 +      `extract_cubelets` (replaces `legacy/extract_true_cubele
          +ts.py`), `build_mosaic`                                       
      321 +      (replaces `legacy/mosaic_sofia_true_detections.py`, via 
      322 +      `reproject.mosaicking.reproject_and_coadd` onto the full
          +-field mosaic's WCS --                                        
      323 +      verified against `reproject`'s actual installed signatur
          +e, not memory).                                               
      324 +      `hivalidate-postprocess` runs all three from a `validate
          +d_cat.xml`, fixing                                            
      325 +      issue #4 (directory-naming mismatch between stages) sinc
          +e every stage now                                             
      326 +      reads/writes through `Config.paths`, not ad hoc constant
          +s.                                                            
      327 +- Added `paths.field_mosaic` to the config schema (optional; t
          +he full-field                                                 
      328 +  `mom0.fits` the mosaic step needs) -- the mosaic step is ski
          +pped, not an error,                                           
      329 +  when unset.                                                 
      330 +- **Ran for real** end-to-end (dry-run -> QA -> postprocess) a
          +gainst 5 real sources                                         
      331 +  from `data/work/SB82605/`, scripted to flag 3 true, and agai
          +nst the real                                                  
      332 +  `data/run_sofia/mom0.fits` full-field mosaic (3585x3552, not
          + a synthetic                                                  
      333 +  stand-in). `validated_true.csv` correctly contained exactly 
          +the 3 true-flagged                                            
      334 +  sources; `true_cubelets/` had exactly their files (13 each);
          + the mosaic FITS                                              
      335 +  correctly matched the field's shape/WCS, and rendering it co
          +nfirmed by eye that                                           
      336 +  the three tiny detections land at their real, distinct sky p
          +ositions within the                                           
      337 +  full field.                                                 
      338  
      339  ### Phase 6 — End-to-end validation
      340  - [ ] Run the full pipeline over all 45 `run_sofia/` runs: com
           bine → dedup → rename →

⏺ Now let's commit Phase 5.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Phase 5 is done and committed. Summary:

  Built: postprocess.py (filter_by_qa, write_validation_csv, extract_cubelets,
  build_mosaic) and hivalidate-postprocess, replacing the three legacy scripts.
  The CSV-generation step is notably simpler than the legacy version — it no
  longer needs to reverse-engineer which sources were "true" by scanning PNG
  filenames, since validated_cat.xml already carries the qa flag directly. Added
  paths.field_mosaic to the config schema for the full-field mom0.fits
  reference the mosaic step needs.

  Verified for real, not just on the fixture: ran the whole chain — dry-run → QA
  → postprocess — against 5 real sources and the actual
  data/run_sofia/mom0.fits (3585×3552, not a synthetic stand-in). The CSV
  correctly held exactly the 3 sources I scripted as "true," the cubelets
  directory had exactly their files, and I rendered the resulting mosaic and
  visually confirmed the three detections land at their correct, distinct
  positions within the full field.

  That's Phases 0–5 all done. Two remain:
  - Phase 6: full end-to-end validation — running the entire pipeline over all
  45 real run_sofia/ runs (not just samples), including a real, larger-scale
  dry-run batch.
  - Phase 7: polish — docs/pipeline_overview.md, finishing the README,
  confirming CI, tagging v0.1.

  Want me to continue with Phase 6?

✻ Baked for 9m 15s

❯ Yes, go ahead with Phase 6                                                    

⏺ Let's run the real, full-scale pipeline. First, a fresh combine → dedup →
  rename over all 45 runs (fast, and confirms Phase 1's results still reproduce
  with the current code).

  Ran 1 shell command (ctrl+o to expand)

⏺ Reproduced exactly (670→448 sources, 5824 files), confirming determinism
  across all the later-phase code changes. Now let's check connectivity before
  launching the big dry-run.

  Ran 1 shell command (ctrl+o to expand)

⏺ Optical and continuum chains both have at least one working backend, so the
  batch will proceed (with a warning about Legacy Survey/CASDA, as designed).
  Let's launch the full 448-source dry-run in the background.

  Ran 1 shell command (ctrl+o to expand)

⏺ While that runs in the background, let's prepare the cross-check against the
  159 known-true legacy examples — first, how much overlap is there by name?

  Ran 1 shell command (ctrl+o to expand)

⏺ No exact-name overlap — expected, given what I found in Phase 1 (SoFiA names
  are extremely sensitive to exact centroid, and this is a different processing
  run). Let me do a positional cross-match instead, parsing RA/Dec directly from
  the legacy PNG filenames' embedded J-coordinates.

  Ran 1 shell command (ctrl+o to expand)

⏺ 90.5% positional match rate — strong consistency signal between independent
  processing runs. Let me check the 15 unmatched ones before moving on, to rule
  out a systematic issue.

  Ran 1 shell command (ctrl+o to expand)

⏺ The 15 unmatched sources aren't dedup casualties — their separation is
  identical before and after dedup, and most are hundreds of arcsec away (up to
  ~20 arcmin), meaning they're simply outside the sky area these particular 45
  Removal runs cover (likely from a different pointing/epoch in the legacy
  "jolly" dataset). Only 2 are borderline (~31–35″, just outside dedup
  tolerance). This is a clean, expected result, not a bug. Let me check on the
  background dry-run.

  Searched for 2 patterns (ctrl+o to expand)

⏺ The full 448-source dry-run is running in the background (started ~2 minutes
  ago, ~29/448 done, roughly 4 seconds/source — estimated ~30 minutes total).
  While that runs, here's what I've confirmed so far:

  - Fresh combine → dedup → rename reproduced exactly (670 → 448 sources, 5824
  files), confirming determinism across everything built since Phase 1.
  - Cross-checked our 448-source deduped catalogue against the 159 legacy "true"
  examples via positional match (exact-name matching found zero overlap, as
  expected given how sensitive SoFiA's name strings are to centroid shifts):
  144/159 (90.5%) matched within 30″, median separation 2.0″. The 15 non-matches
  aren't dedup casualties — checked their nearest-neighbor separation before
  and after dedup, identical in both — they're just outside the sky area these
  45 run_sofia runs cover (up to ~20 arcmin away), i.e. likely from a different
  pointing in the legacy dataset, not a bug.

  I'll let the dry-run finish in the background and report back once it's done,
  then move on to analyzing the results and doing the QA/postprocess portion of
  the end-to-end check.

✻ Baked for 3m 39s
※ recap: We're building the hivalidate pipeline (Phases 0-5 done and verified). Phase 6 full-scale validation is running now: 448 real sources processing in the background, next step is checking results once it finishes.

❯ When checking some validation plots generated by the dry-run, HI detection    
  contour on the continuum image (the middle of the upper row) is smaller       
  comprared to the contour on the corresponding optical image. This is likely a 
  problem in the reference WCS (HI moment 0 should be reference). Please check  
  and fix it.                                                                   

⏺ Let me investigate empirically rather than guess — comparing the actual
  angular field of view each backend returns for the same requested size.

  Ran 1 shell command (ctrl+o to expand)

⏺ Confirmed the root cause: SkyView's optical cutout has an actual field of view
  of 100″ for a 170″ request, while the continuum cutout correctly returns
  174″. My hardcoded DSS2_ARCSEC_PER_PIX = 1.7 assumption in SkyViewBackend is
  wrong — let me confirm the real value directly from the FITS header.

  Ran 1 shell command (ctrl+o to expand)

⏺ Confirmed exactly — 1.0 arcsec/pixel, not the 1.7 I'd hardcoded. Before just
  swapping the constant, let me check if astroquery.skyview actually supports
  requesting by angular size directly, which would eliminate the platescale
  assumption entirely rather than just correcting it.

  Ran 3 shell commands (ctrl+o to expand)

⏺ get_images accepts width/height as astropy.units.Quantity — this lets me
  request an exact angular field of view directly, eliminating the
  platescale-assumption class of bug entirely rather than just patching the
  constant. Let me verify this works live before rewriting the backend.

  Ran 1 shell command (ctrl+o to expand)

⏺ Confirmed — exact field of view, and better resolution too (300×300 vs the old
  100×100). Let me rewrite SkyViewBackend to use this properly instead of the
  flawed platescale assumption.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/cutouts/optical.py)
  ⎿  Added 1 line
      12  import io
      13  
      14  import requests
      15 +from astropy import units as u                                 
      16  from astropy.coordinates import SkyCoord
      17  from astropy.io import fits
      18  from astropy.wcs import WCS

⏺ Update(src/hivalidate/cutouts/optical.py)
  ⎿  Added 21 lines, removed 12 lines
      35  
      36  
      37  class SkyViewBackend(CutoutBackend):
      38 -    """DSS2 Red (or any other SkyView survey) via `astroquery.s
         -kyview`. SkyView's                                             
      39 -    `get_images` takes a pixel count, not an angular size direc
         -tly, so this backend                                           
      40 -    assumes a fixed arcsec/pixel scale to convert -- 1.7 arcsec
         -/pixel is DSS2's native                                        
      41 -    plate scale (the value the legacy script implicitly relied 
         -on by only ever                                                
      42 -    passing a pixel count), not independently verified against 
         -SkyView's documentation                                        
      43 -    for every survey it can serve. If you use `survey=` other t
         -han a DSS2 variant,                                            
      44 -    double-check this assumption still gives a sensible field o
         -f view.                                                        
      38 +    """DSS2 Red (or any other SkyView survey) via `astroquery.s
         +kyview`.                                                       
      39 +                                                               
      40 +    Requests the field of view via `get_images`'s `width`/`heig
         +ht` (angular                                                   
      41 +    `Quantity`) parameters, not a pixel count converted through
         + an assumed plate                                              
      42 +    scale -- SkyView handles that conversion itself, correctly,
         + for whichever survey                                          
      43 +    is selected. An earlier version of this backend assumed a f
         +ixed 1.7 arcsec/pixel                                          
      44 +    DSS2 plate scale to convert `size_arcsec` into a pixel coun
         +t; the real plate                                              
      45 +    scale is 1.0 arcsec/pixel (confirmed live 2026-07-30 agains
         +t a real SkyView                                               
      46 +    response's CDELT), so every optical cutout had an actual fi
         +eld of view ~59% of                                            
      47 +    what was requested -- smaller than the same-source continuu
         +m cutout, which                                                
      48 +    always used real degrees via MontagePy and was correct. Thi
         +s is what caused the                                           
      49 +    HI detection contour (drawn from the same real-size moment-
         +0 data in both                                                 
      50 +    panels) to visibly appear larger on the optical panel than 
         +the continuum panel                                            
      51 +    in `plotting.build_validation_figure`'s output -- found by 
         +inspecting real                                                
      52 +    dry-run plots, not caught by any test, since the bug was a 
         +wrong physical                                                 
      53 +    constant, not a code path that could crash or an assertion 
         +that could fail.                                               
      54      """
      55  
      56      name = "skyview"
      57  
      49 -    DSS2_ARCSEC_PER_PIX = 1.7                                  
      50 -                                                               
      58      def __init__(self, survey: str = "DSS2 Red", max_retries: i
          nt = 5):
      59          self.survey = survey
      60          self.max_retries = max_retries
      61  
      62      def fetch(self, position: SkyCoord, size_arcsec: float) -> 
          CutoutResult:
      56 -        n_pix = max(int(round(size_arcsec / self.DSS2_ARCSEC_PE
         -R_PIX)), 1)                                                    
      57 -                                                               
      63          def _query():
      64              images = SkyView.get_images(
      60 -                position=position, survey=self.survey, projecti
         -on="Sin", pixels=n_pix                                         
      65 +                position=position,                             
      66 +                survey=self.survey,                            
      67 +                projection="Sin",                              
      68 +                width=size_arcsec * u.arcsec,                  
      69 +                height=size_arcsec * u.arcsec,                 
      70              )
      71              if not images:
      72                  raise CutoutUnavailable(f"SkyView returned no i
          mages for survey {self.survey!r}")

⏺ Now let's update the tests to match — the old test asserted the (now-removed)
  platescale-based pixel calculation.

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_cutouts_optical.py)
  ⎿  Added 1 line
      15  import numpy as np
      16  import pytest
      17  import requests
      18 +from astropy import units as u                                 
      19  from astropy.coordinates import SkyCoord
      20  from astropy.io import fits
      21  

⏺ Update(tests/test_cutouts_optical.py)
  ⎿  Added 14 lines, removed 7 lines
      40              "CRVAL2": -55.8032,
      41              "CRPIX1": 5,
      42              "CRPIX2": 5,
      43 -            "CDELT1": -1.7 / 3600,                             
      44 -            "CDELT2": 1.7 / 3600,                              
      43 +            "CDELT1": -1.0 / 3600,                             
      44 +            "CDELT2": 1.0 / 3600,                              
      45          }
      46      )
      47  
      48  
      49  class TestSkyViewBackendMocked:
      50 -    def test_converts_size_arcsec_to_pixels_using_dss2_platesca
         -le(self, monkeypatch):                                         
      50 +    def test_requests_field_of_view_as_an_angular_quantity_not_
         +a_pixel_count(self, monkeypatch):                              
      51 +        # Regression test for the real bug found by inspecting 
         +dry-run output: a                                              
      52 +        # hardcoded (and wrong) assumed plate scale used to con
         +vert size_arcsec into                                          
      53 +        # a pixel count, silently returning too small a field o
         +f view. Requesting                                             
      54 +        # width/height directly (in real angular units) removes
         + the assumption                                                
      55 +        # entirely rather than requiring a corrected constant. 
      56          captured = {}
      57  
      53 -        def fake_get_images(*, position, survey, projection, pi
         -xels):                                                         
      54 -            captured["pixels"] = pixels                        
      55 -            hdu = FakeHDU(np.ones((pixels, pixels)), _fake_skyv
         -iew_header())                                                  
      58 +        def fake_get_images(*, position, survey, projection, wi
         +dth, height):                                                  
      59 +            captured["width"] = width                          
      60 +            captured["height"] = height                        
      61 +            hdu = FakeHDU(np.ones((10, 10)), _fake_skyview_head
         +er())                                                          
      62              return [[hdu]]
      63  
      64          monkeypatch.setattr("hivalidate.cutouts.optical.SkyView
          .get_images", fake_get_images)
      65          backend = SkyViewBackend()
      66          backend.fetch(POSITION, size_arcsec=170.0)
      61 -        assert captured["pixels"] == 100  # 170 / 1.7          
      67 +        assert captured["width"] == 170.0 * u.arcsec           
      68 +        assert captured["height"] == 170.0 * u.arcsec          
      69  
      70      def test_provenance_includes_survey_name(self, monkeypatch)
          :
      71          def fake_get_images(**kwargs):

  Ran 2 shell commands (ctrl+o to expand)

⏺ Let's run the live network test to confirm the real fix against the actual
  service, and re-verify the FOV directly.

  Ran 1 shell command (ctrl+o to expand)

⏺ The dry-run job I launched earlier is still running with the old buggy code —
  I should stop it and restart with the fix rather than let it finish producing
  wrong output. Let me check its status first.

  Ran 1 shell command (ctrl+o to expand)
⏺ Since this bug affects every source's optical panel, letting the current run
  finish would just produce output I'd have to regenerate anyway. Killing it and
  restarting with the fix.

  Listed 1 directory, ran 2 shell commands (ctrl+o to expand)

⏺ Background command "source ~/miniforge3/etc/profile.d/conda.sh
conda activate base
cd /Users/rhe003/Research/ASKAP/softwares/validate_source_finding
time hivalidate-dry-run --config configs/SB82605.yaml &gt; /tmp/dry_run_full.log
2&gt;&amp;1
echo "EXIT CODE: $?"" completed (exit code 0)

⏺ Now let's do a quick before/after visual confirmation with a single real
  source before relaunching the full batch.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Confirmed visually — both panels now show identical RA/Dec tick ranges
  (21h02m00s–40s in both), and the contour is now correctly the same size in
  both. Let's run the full test suite once more, then relaunch the full batch
  with the fix.

  Ran 1 shell command (ctrl+o to expand)

⏺ All 128 tests still pass. Let's commit this fix now (before relaunching the
  long-running batch), then restart the full dry-run with the corrected code.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Now let's relaunch the full 448-source dry-run with the fix.

  Ran 1 shell command (ctrl+o to expand)

⏺ Good catch on your part — that was a real, field-of-view-affecting bug
  (optical cutouts covering only ~59% of the intended sky area), now fixed and
  verified with a matching before/after visual comparison, and committed. The
  full 448-source dry-run is running again in the background with the corrected
  code (~30 min estimated). I'll report back once it completes and continue with
  the rest of Phase 6's validation.

✻ Crunched for 9m 12s

❯ When checking again, the FoV of continuum image is still wider. Make FoV of   
  all moment maps are same.                                                     

⏺ Let me check the real pixel scale of the mom0 cube to see if dry_run.py's
  size_arcsec calculation has the same class of bug.

  Ran 1 shell command (ctrl+o to expand)

⏺ Background command "source ~/miniforge3/etc/profile.d/conda.sh
conda activate base
cd /Users/rhe003/Research/ASKAP/softwares/validate_source_finding
time hivalidate-dry-run --config configs/SB82605.yaml &gt; /tmp/dry_run_full.log
2&gt;&amp;1
echo "EXIT CODE: $?"" completed (exit code 0)

⏺ The stale-batch dry-run just finished in the background, but I've found a
  deeper issue — let me check it before deciding whether to use those results.

  Searched for 1 pattern (ctrl+o to expand)

⏺ That batch completed 448/448 OK, but it still has the size_arcsec bug (same
  wrong 1.7 constant, this time for mom0's pixel scale — real value is 6.0″/pix)
  and lacks the panel-consistency fix. I'll discard it and fix both issues
  properly first.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Let me view the current plotting.py in full to plan the fix properly.

  Read 1 file (ctrl+o to expand)

⏺ Let me verify WCS.proj_plane_pixel_scales()'s actual return type before using
  it.

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's implement the fix in plotting.py.

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 14 lines
      20  - Provenance (which optical/continuum backend actually supplied
           each cutout) is
      21    annotated directly on the figure, since there are now multipl
          e possible sources
      22    per panel (PLAN.md section 5, "Provenance").
      23 +                                                               
      24 +Every sky panel (optical, continuum, mom0, mom1) is pinned to t
         +he same real                                                   
      25 +angular field of view, computed from the mom0 image's own WCS (
         +`reference_field_of_                                           
      26 +view_arcsec`) -- not each panel's own auto-scaled image extent.
         + Found live                                                    
      27 +2026-07-30: the continuum panel's displayed field of view was v
         +isibly wider than                                              
      28 +the others because nothing constrained it to match; only mom0/m
         +om1 borrowed the                                               
      29 +optical panel's pixel limits (which happens to work only becaus
         +e they share its                                               
      30 +exact WCS), and the optical panel itself was never anchored to 
         +anything.                                                      
      31  """
      32  
      33  from __future__ import annotations
     ...
      37  
      38  import numpy as np
      39  from astropy import units as u
      40 +from astropy.coordinates import SkyCoord                       
      41  from astropy.cosmology import Cosmology
      42  from astropy.io import fits
      43  from astropy.table import Row, Table
     ...
      49  from hivalidate import conversions
      50  from hivalidate.cutouts.base import CutoutResult
      51  
      52 +#: How much wider than the mom0 detection's own footprint to fe
         +tch/display cutouts,                                           
      53 +#: matching the legacy script's `npix = max(mom0_shape) * 5` co
         +nvention -- enough                                             
      54 +#: surrounding sky for context, not just the detection mask its
         +elf.                                                           
      55 +DISPLAY_FOV_FACTOR = 5                                         
      56  
      57 +                                                               
      58  @dataclass
      59  class SourceCubelets:
      60      mom0: np.ndarray

⏺ Now adding reference_field_of_view_arcsec next to load_source_cubelets:

⏺ Update(src/hivalidate/plotting.py)  ⎿  Added 35 lines
      111      )
      112  
      113  
      114 +def reference_field_of_view_arcsec(cubelets: SourceCubelets) -
          +> float:                                                      
      115 +    """The real angular field of view every sky panel in `buil
          +d_validation_figure` is                                       
      116 +    pinned to, and what `hivalidate.cli.dry_run` sizes its cut
          +out requests from:                                            
      117 +    `DISPLAY_FOV_FACTOR` times the mom0 image's own real footp
          +rint (the larger of its                                       
      118 +    two axes), computed from its actual WCS pixel scale.      
      119 +                                                              
      120 +    Deliberately not a hardcoded arcsec/pixel constant -- an e
          +arlier version of both                                        
      121 +    this and the SkyView backend assumed 1.7 arcsec/pixel (cop
          +ied from the same wrong                                       
      122 +    assumption in two unrelated places); the real mom0 pixel s
          +cale for this dataset                                         
      123 +    is 6.0 arcsec/pixel, confirmed live 2026-07-30 against a r
          +eal cubelet header.                                           
      124 +    Using the WCS directly removes the assumption for any data
          +set's actual pixel                                            
      125 +    scale, not just this one.                                 
      126 +    """                                                       
      127 +    ny, nx = cubelets.mom0.shape                              
      128 +    scales = cubelets.mom0_wcs.celestial.proj_plane_pixel_scal
          +es()                                                          
      129 +    width_arcsec = (nx * scales[0]).to(u.arcsec).value        
      130 +    height_arcsec = (ny * scales[1]).to(u.arcsec).value       
      131 +    return max(width_arcsec, height_arcsec) * DISPLAY_FOV_FACT
          +OR                                                            
      132 +                                                              
      133 +                                                              
      134 +def _set_fov(ax, wcs: WCS, center: SkyCoord, size_arcsec: floa
          +t) -> None:                                                   
      135 +    """Pins `ax`'s displayed field of view to a `size_arcsec` 
          +box centered on                                               
      136 +    `center`, in `wcs`'s own pixel frame. Called with the same
          + `center`/`size_arcsec`                                       
      137 +    for every sky panel so they all show the same patch of sky
          + regardless of each                                           
      138 +    cutout's own native pixel scale or a backend's rounding of
          + the requested size.                                          
      139 +    """                                                       
      140 +    celestial_wcs = wcs.celestial                             
      141 +    scales = celestial_wcs.proj_plane_pixel_scales()          
      142 +    half_width_pix = (size_arcsec / 2 * u.arcsec) / scales[0].
          +to(u.arcsec)                                                  
      143 +    half_height_pix = (size_arcsec / 2 * u.arcsec) / scales[1]
          +.to(u.arcsec)                                                 
      144 +    x0, y0 = celestial_wcs.world_to_pixel(center)             
      145 +    ax.set_xlim(float(x0 - half_width_pix.value), float(x0 + h
          +alf_width_pix.value))                                         
      146 +    ax.set_ylim(float(y0 - half_height_pix.value), float(y0 + 
          +half_height_pix.value))                                       
      147 +                                                              
      148 +                                                              
      149  def _robust_vlim(data: np.ndarray, n_sigma: float = 3.0) -> tu
           ple[float, float]:
      150      """mean +/- n_sigma*std, falling back to (0, 1) for degene
           rate (all-equal or
      151      all-NaN) data -- avoids a matplotlib warning/blank image o
           n a placeholder cutout.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 2 lines
      190  
      191      mom0_wcs = cubelets.mom0_wcs
      192      display_wcs = optical.wcs if optical is not None else mom0
           _wcs
      193 +    center = SkyCoord(ra=row["ra"], dec=row["dec"], unit="deg"
          +)                                                             
      194 +    fov_arcsec = reference_field_of_view_arcsec(cubelets)     
      195  
      196      fig = Figure(figsize=(18, 11))
      197      fig.subplots_adjust(left=0.05, right=0.98, wspace=0.1)

⏺ Now let's view the rest of the panels to add _set_fov calls and remove the old
  borrowed-xlim lines.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 2 lines
      227          ax_opt.set_title("Optical (no cutout available)", size
           =12)
      228      _format_sky_axes(ax_opt, ylabel=True)
      229      _annotate_moment0(ax_opt)
      230 +    _set_fov(ax_opt, display_wcs, center, fov_arcsec)         
      231  
      232      # --- panel 2: continuum + mom0 contours ---
      233      cont_wcs = continuum.wcs if continuum is not None else mom
           0_wcs
     ...
      250          ax_cont.set_title("Continuum (no cutout available)", s
           ize=12)
      251      _format_sky_axes(ax_cont, ylabel=False)
      252      _annotate_moment0(ax_cont)
      253 +    _set_fov(ax_cont, cont_wcs, center, fov_arcsec)           
      254  
      255      # --- panel 3: HI spectrum ---
      256      ax_spec = fig.add_subplot(233)

⏺ Now panels 4 and 5 — replacing the borrowed ax_opt.get_xlim() approach:

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 1 line, removed 2 lines
      287      ax_mom0.contour(
      288          col_density_map, levels=contour_levels_scaled, transfo
           rm=ax_mom0.get_transform(mom0_wcs)
      289      )
      290 -    ax_mom0.set_xlim(ax_opt.get_xlim())                       
      291 -    ax_mom0.set_ylim(ax_opt.get_ylim())                       
      290      _format_sky_axes(ax_mom0, ylabel=True)
      291      _annotate_moment0(ax_mom0)
      292 +    _set_fov(ax_mom0, display_wcs, center, fov_arcsec)        
      293  
      294      # --- panel 5: mom1 (velocity) ---
      295      ax_mom1 = fig.add_subplot(235, projection=display_wcs)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 1 line, removed 2 lines
      300          cmap="jet",
      301          transform=ax_mom1.get_transform(mom0_wcs),
      302      )
      303 -    ax_mom1.set_xlim(ax_opt.get_xlim())                       
      304 -    ax_mom1.set_ylim(ax_opt.get_ylim())                       
      303      _format_sky_axes(ax_mom1, ylabel=False)
      304      ax_mom1.annotate(
      305          "Moment 1", (0.75, 0.93), size=12, xycoords="axes frac
           tion", bbox=_label_bbox()
      306      )
      307      colorbar = fig.colorbar(mom1_image, ax=ax_mom1, orientatio
           n="vertical", pad=0.01, aspect=30)
      308      colorbar.ax.set_ylabel(r"Velocity (km s$^{-1}$)")
      309 +    _set_fov(ax_mom1, display_wcs, center, fov_arcsec)        
      310  
      311      # --- panel 6: PV diagram ---
      312      ax_pv = fig.add_subplot(236, projection=cubelets.pv_wcs)

⏺ Now updating dry_run.py to use the same reference function for cutout sizing.

⏺ Update(src/hivalidate/cli/dry_run.py)
  ⎿  Added 4 lines, removed 3 lines
      121  
      122  def _process_one_source(row, source_name, config, optical_chai
           n, continuum_chain, cache) -> dict:
      123      position = SkyCoord(ra=row["ra"], dec=row["dec"], unit="de
           g")
      124 -    # Matches the legacy script's convention: field of view sc
          -ales with the source's                                        
      125 -    # own moment-0 footprint, not a fixed angular size for eve
          -ry source.                                                    
      124      cubelets = plotting.load_source_cubelets(config.paths.rena
           med_cubelets_dir, source_name)
      127 -    size_arcsec = max(cubelets.mom0.shape) * 5 * 1.7          
      125 +    # The same reference field of view build_validation_figure
          + pins every sky panel                                         
      126 +    # to -- computed from mom0's own real WCS pixel scale, not
          + an assumed constant                                          
      127 +    # (see plotting.reference_field_of_view_arcsec's docstring
          + for why that matters).                                       
      128 +    size_arcsec = plotting.reference_field_of_view_arcsec(cube
          +lets)                                                         
      129  
      130      optical = _fetch_or_none(position, size_arcsec, source_nam
           e, optical_chain, cache)
      131      continuum = _fetch_or_none(position, size_arcsec, source_n
           ame, continuum_chain, cache)

⏺ Now let's run lint and the test suite to see what breaks (existing tests
  likely assert on old xlim-borrowing behavior and the old size_arcsec formula).

  Ran 1 shell command (ctrl+o to expand)

⏺ Existing tests still pass unmodified — good sign the fix is
  backward-compatible with prior structural assertions. Now let's add targeted
  regression tests for the actual fix.

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_plotting.py)
  ⎿  Added 24 lines, removed 3 lines
      11  
      12  import numpy as np
      13  import pytest
      14 +from astropy import units as u                                 
      15  from astropy.wcs import WCS
      16  from matplotlib.figure import Figure
      17  
      18  from hivalidate import catalogue
      19  from hivalidate.cutouts.base import CutoutResult
      19 -from hivalidate.plotting import build_validation_figure, load_s
         -ource_cubelets                                                 
      20 +from hivalidate.plotting import (                              
      21 +    DISPLAY_FOV_FACTOR,                                        
      22 +    build_validation_figure,                                   
      23 +    load_source_cubelets,                                      
      24 +    reference_field_of_view_arcsec,                            
      25 +)                                                              
      26  
      27  _FIXTURE_RUN_DIR = Path(__file__).parent / "fixtures" / "run_so
          fia_mini"
      28  FIXTURE_CUBELETS = _FIXTURE_RUN_DIR / "SB82605_Removal_001_cube
          lets"
      29  FIXTURE_CATALOGUE = _FIXTURE_RUN_DIR / "SB82605_Removal_001_cat
          .xml"
      30  
      31  
      26 -def _fake_cutout(size=40, ra=315.4611, dec=-55.8032) -> CutoutR
         -esult:                                                         
      32 +def _fake_cutout(size=40, ra=315.4611, dec=-55.8032, arcsec_per
         +_pix=1.7) -> CutoutResult:                                     
      33      wcs = WCS(naxis=2)
      34      wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
      35      wcs.wcs.crval = [ra, dec]
      36      wcs.wcs.crpix = [size / 2, size / 2]
      31 -    wcs.wcs.cdelt = [-1.7 / 3600, 1.7 / 3600]                  
      37 +    wcs.wcs.cdelt = [-arcsec_per_pix / 3600, arcsec_per_pix / 3
         +600]                                                           
      38      data = np.random.default_rng(0).normal(0, 1, size=(size, si
          ze))
      39      return CutoutResult(data=data, wcs=wcs, provenance="fake:te
          st")
      40  
      41  
      42 +def _axis_fov_arcsec(ax) -> tuple[float, float]:               
      43 +    """Real angular width/height an axis is actually displaying
         +, computed from its                                            
      44 +    own WCS pixel scale and current xlim/ylim -- independent of
         + `_set_fov`'s own                                              
      45 +    implementation, so this genuinely checks the panel's visibl
         +e extent rather than                                           
      46 +    re-deriving the same formula the code under test uses.     
      47 +    """                                                        
      48 +    wcs = ax.wcs.celestial                                     
      49 +    scales = wcs.proj_plane_pixel_scales()                     
      50 +    xlim = ax.get_xlim()                                       
      51 +    ylim = ax.get_ylim()                                       
      52 +    width = abs(xlim[1] - xlim[0]) * scales[0].to(u.arcsec).val
         +ue                                                             
      53 +    height = abs(ylim[1] - ylim[0]) * scales[1].to(u.arcsec).va
         +lue                                                            
      54 +    return width, height                                       
      55 +                                                               
      56 +                                                               
      57  def _real_row(name="SoFiA J210149.89-554804.6"):
      58      table = catalogue.read_votable(FIXTURE_CATALOGUE)
      59      matches = table[table["name"] == name]

  Read 1 file (ctrl+o to expand)

⏺ Now let's insert the new regression test class right after
  TestBuildValidationFigure's existing tests.

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_plotting.py)
  ⎿  Added 70 lines
      136                  row, cubelets, optical=_fake_cutout(), continu
           um=_fake_cutout()
      137              )
      138              assert isinstance(fig, Figure), f"failed for {name
           }"
      139 +                                                              
      140 +                                                              
      141 +class TestAllSkyPanelsShareTheSameFieldOfView:                
      142 +    """Regression tests for the bug reported live 2026-07-30: 
          +the continuum panel's                                         
      143 +    displayed field of view was visibly wider than the optical
          +/mom0/mom1 panels,                                            
      144 +    because nothing pinned it (or the optical panel) to a comm
          +on reference -- only                                          
      145 +    mom0/mom1 borrowed the optical panel's raw pixel xlim, whi
          +ch only worked because                                        
      146 +    they happened to share its exact WCS. optical and continuu
          +m are given                                                   
      147 +    deliberately different native pixel scales below (1.7 and 
          +2.0 arcsec/pixel) --                                          
      148 +    the real-world condition that exposed the bug (SkyView vs.
          + the local continuum                                          
      149 +    mosaic's own resolution never matched).                   
      150 +    """                                                       
      151 +                                                              
      152 +    def _figure(self):                                        
      153 +        row = _real_row()                                     
      154 +        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB8
          +2605_Removal_001_1")                                          
      155 +        optical = _fake_cutout(size=100, arcsec_per_pix=1.7)  
      156 +        continuum = _fake_cutout(size=60, arcsec_per_pix=2.0) 
      157 +        fig = build_validation_figure(row, cubelets, optical=o
          +ptical, continuum=continuum)                                  
      158 +        return fig, cubelets                                  
      159 +                                                              
      160 +    def test_reference_fov_is_five_times_mom0s_own_footprint(s
          +elf):                                                         
      161 +        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB8
          +2605_Removal_001_1")                                          
      162 +        fov = reference_field_of_view_arcsec(cubelets)        
      163 +                                                              
      164 +        wcs = cubelets.mom0_wcs.celestial                     
      165 +        scales = wcs.proj_plane_pixel_scales()                
      166 +        ny, nx = cubelets.mom0.shape                          
      167 +        expected = (                                          
      168 +            max(nx * scales[0].to(u.arcsec).value, ny * scales
          +[1].to(u.arcsec).value)                                       
      169 +            * DISPLAY_FOV_FACTOR                              
      170 +        )                                                     
      171 +        assert fov == pytest.approx(expected)                 
      172 +                                                              
      173 +    def test_optical_and_continuum_panels_show_the_same_real_f
          +ield_of_view(self):                                           
      174 +        fig, cubelets = self._figure()                        
      175 +        ax_opt, ax_cont = fig.axes[0], fig.axes[1]            
      176 +                                                              
      177 +        opt_w, opt_h = _axis_fov_arcsec(ax_opt)               
      178 +        cont_w, cont_h = _axis_fov_arcsec(ax_cont)            
      179 +                                                              
      180 +        # Loose tolerance: pixel-grid rounding on two differen
          +t native resolutions                                          
      181 +        # (1.7 vs 2.0 arcsec/pix here) means it can't be exact
          +, but before the fix                                          
      182 +        # the discrepancy was a large, visually-obvious ~30-70
          +%, not a rounding error.                                      
      183 +        assert opt_w == pytest.approx(cont_w, rel=0.05)       
      184 +        assert opt_h == pytest.approx(cont_h, rel=0.05)       
      185 +                                                              
      186 +    def test_all_four_sky_panels_match_the_reference_fov(self)
          +:                                                             
      187 +        fig, cubelets = self._figure()                        
      188 +        expected_fov = reference_field_of_view_arcsec(cubelets
          +)                                                             
      189 +        # axes[0..3] are optical, continuum, mom0, mom1 in tha
          +t order (see the panel                                        
      190 +        # layout in build_validation_figure); mom1's colorbar 
          +is a later axis.                                              
      191 +        for ax, label in zip(fig.axes[:4], ["optical", "contin
          +uum", "mom0", "mom1"]):                                       
      192 +            width, height = _axis_fov_arcsec(ax)              
      193 +            assert width == pytest.approx(expected_fov, rel=0.
          +05), f"{label} width mismatch"                                
      194 +            assert height == pytest.approx(expected_fov, rel=0
          +.05), f"{label} height mismatch"                              
      195 +                                                              
      196 +    def test_matches_even_when_optical_cutout_is_missing(self)
          +:                                                             
      197 +        # display_wcs falls back to mom0_wcs when optical is N
          +one -- _set_fov must                                          
      198 +        # still produce the same real FoV in that frame as eve
          +rywhere else.                                                 
      199 +        row = _real_row()                                     
      200 +        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB8
          +2605_Removal_001_1")                                          
      201 +        continuum = _fake_cutout(size=60, arcsec_per_pix=2.0) 
      202 +        fig = build_validation_figure(row, cubelets, optical=N
          +one, continuum=continuum)                                     
      203 +        expected_fov = reference_field_of_view_arcsec(cubelets
          +)                                                             
      204 +                                                              
      205 +        ax_cont = fig.axes[1]                                 
      206 +        width, height = _axis_fov_arcsec(ax_cont)             
      207 +        assert width == pytest.approx(expected_fov, rel=0.05) 
      208 +        assert height == pytest.approx(expected_fov, rel=0.05)

  Ran 1 shell command (ctrl+o to expand)

⏺ fig.axes[:4] isn't what I assumed — the spectrum panel's twinned frequency
  axis (ax_spec.twiny()) is created before panel 4, shifting indices. Let me
  check the actual axis order empirically rather than guess again.

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(tests/test_plotting.py)  ⎿  Added 7 lines, removed 3 lines
      186      def test_all_four_sky_panels_match_the_reference_fov(self)
           :
      187          fig, cubelets = self._figure()
      188          expected_fov = reference_field_of_view_arcsec(cubelets
           )
      189 -        # axes[0..3] are optical, continuum, mom0, mom1 in tha
          -t order (see the panel                                        
      190 -        # layout in build_validation_figure); mom1's colorbar 
          -is a later axis.                                              
      191 -        for ax, label in zip(fig.axes[:4], ["optical", "contin
          -uum", "mom0", "mom1"]):                                       
      189 +        # fig.axes order (verified empirically, not assumed): 
          +0=optical, 1=continuum,                                       
      190 +        # 2=spectrum, 3=spectrum's twinned frequency axis (pla
          +in Axes, no WCS -- and                                        
      191 +        # what pushes mom0/mom1 to indices 4/5 instead of 2/3)
          +, 4=mom0, 5=mom1,                                             
      192 +        # 6=mom1's colorbar, 7=PV (a WCSAxes too, but angular-
          +offset-vs-frequency,                                          
      193 +        # not a sky panel, so deliberately excluded from this 
          +comparison).                                                  
      194 +        sky_panel_axes = {"optical": fig.axes[0], "continuum":
          + fig.axes[1], "mom0": fig.axes[4], "mom1": fig.axes[5]}       
      195 +        for label, ax in sky_panel_axes.items():              
      196              width, height = _axis_fov_arcsec(ax)
      197              assert width == pytest.approx(expected_fov, rel=0.
           05), f"{label} width mismatch"
      198              assert height == pytest.approx(expected_fov, rel=0
           .05), f"{label} height mismatch"

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(tests/test_plotting.py)
  ⎿  Added 6 lines, removed 1 line
      191          # what pushes mom0/mom1 to indices 4/5 instead of 2/3)
           , 4=mom0, 5=mom1,
      192          # 6=mom1's colorbar, 7=PV (a WCSAxes too, but angular-
           offset-vs-frequency,
      193          # not a sky panel, so deliberately excluded from this 
           comparison).
      194 -        sky_panel_axes = {"optical": fig.axes[0], "continuum":
          - fig.axes[1], "mom0": fig.axes[4], "mom1": fig.axes[5]}       
      194 +        sky_panel_axes = {                                    
      195 +            "optical": fig.axes[0],                           
      196 +            "continuum": fig.axes[1],                         
      197 +            "mom0": fig.axes[4],                              
      198 +            "mom1": fig.axes[5],                              
      199 +        }                                                     
      200          for label, ax in sky_panel_axes.items():
      201              width, height = _axis_fov_arcsec(ax)
      202              assert width == pytest.approx(expected_fov, rel=0.
           05), f"{label} width mismatch"

  Ran 1 shell command (ctrl+o to expand)

⏺ All 4 new regression tests pass. Let's run the full suite, then do the real
  visual confirmation.

  Ran 1 shell command (ctrl+o to expand)

⏺ All 132 tests pass. Now let's regenerate the real plot for the same source
  with real cutouts and confirm the fix visually.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Confirmed — all four sky panels now show identical RA/Dec tick ranges, and the
  wider, correctly-computed field of view (960″ vs the old buggy ~170″) now
  shows much more surrounding context, matching the legacy script's original "5×
  the detection's own footprint" intent. Let's clean up, update PLAN.md, and
  commit this second fix.

  Ran 3 shell commands (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 56 lines, removed 6 lines
      336    the three tiny detections land at their real, distinct sky p
           ositions within the
      337    full field.
      338  
      339 -### Phase 6 — End-to-end validation                           
      340 -- [ ] Run the full pipeline over all 45 `run_sofia/` runs: com
          -bine → dedup → rename →                                       
      341 -      dry-run → QA → post-process                             
      342 -- [ ] Cross-check output against the 159 known examples in `da
          -ta/output_validation_true/`                                   
      343 -      as a regression check                                   
      344 -- [ ] Fix whatever breaks at real scale that the fixture didn'
          -t catch                                                       
      339 +### Phase 6 — End-to-end validation [in progress]             
      340 +- [x] Fresh full-scale combine → dedup → rename over all 45 ru
          +ns, from scratch --                                           
      341 +      reproduced Phase 1's numbers exactly (670 → 448 sources,
          + 5824 files),                                                 
      342 +      confirming determinism across every later-phase code cha
          +nge.                                                          
      343 +- [x] Cross-checked the 448-source deduped catalogue against t
          +he 159 legacy "true"                                          
      344 +      examples in `data/output_validation_true/` by positional
          + match (exact-name                                            
      345 +      matching found zero overlap -- expected, given how centr
          +oid-sensitive SoFiA's                                         
      346 +      name strings are; parsed RA/Dec directly from the legacy
          + filenames' embedded                                          
      347 +      J-coordinates instead): **144/159 (90.5%) matched within
          + 30″**, median                                                
      348 +      separation 2.0″. The 15 non-matches were checked against
          + the *pre-dedup*                                              
      349 +      combined catalogue too (not just deduped) -- separations
          + were essentially                                             
      350 +      identical before and after dedup, ruling out dedup as th
          +e cause; most are                                             
      351 +      hundreds of arcsec to ~20 arcmin away, meaning they're s
          +imply outside the sky                                         
      352 +      area these 45 runs cover (a different pointing in the le
          +gacy dataset), not a                                          
      353 +      pipeline defect.                                        
      354 +- **Two real bugs found and fixed by inspecting actual full-sc
          +ale dry-run output**                                          
      355 +  (not caught by any test, since both were wrong physical cons
          +tants producing                                               
      356 +  plausible-looking but incorrect images, not code paths that 
          +could crash):                                                 
      357 +  1. `SkyViewBackend` assumed a hardcoded 1.7 arcsec/pixel DSS
          +2 plate scale to                                              
      358 +     convert requested field-of-view into a pixel count. The r
          +eal plate scale is                                            
      359 +     1.0 arcsec/pixel (confirmed live against a real SkyView r
          +esponse's CDELT), so                                          
      360 +     every optical cutout had an actual field of view ~59% of 
          +what was requested.                                           
      361 +     Fixed by requesting `width`/`height` as angular `Quantity
          +` params directly                                             
      362 +     (verified live that `astroquery.skyview.SkyView.get_image
          +s` supports this) --                                          
      363 +     removes the plate-scale assumption entirely rather than j
          +ust correcting the                                            
      364 +     constant, so it stays correct for any survey, not only DS
          +S2.                                                           
      365 +  2. `hivalidate.cli.dry_run`'s cutout-sizing calculation used
          + the *same* wrong 1.7                                         
      366 +     arcsec/pixel constant a second time, to convert mom0's pi
          +xel shape into a                                              
      367 +     requested angular size. The real mom0 pixel scale for thi
          +s dataset is 6.0                                              
      368 +     arcsec/pixel (confirmed live against a real cubelet heade
          +r) -- off by 3.5x, a                                          
      369 +     different wrong number than bug 1's but the identical roo
          +t cause (an assumed                                           
      370 +     constant standing in for something computable from the ac
          +tual WCS). Fixed by                                           
      371 +     computing the field of view from mom0's own real WCS pixe
          +l scale                                                       
      372 +     (`plotting.reference_field_of_view_arcsec`) instead of as
          +suming.                                                       
      373 +  3. Even with the cutout *request* sizes now correct, the con
          +tinuum panel's                                                
      374 +     *displayed* field of view still didn't match the other th
          +ree sky panels --                                             
      375 +     only mom0/mom1 explicitly borrowed the optical panel's pi
          +xel limits (which                                             
      376 +     only worked because they share its exact WCS by construct
          +ion); the optical                                             
      377 +     panel itself was never anchored to anything, and the cont
          +inuum panel was never                                         
      378 +     constrained at all, just auto-scaled to its own cutout's 
          +native extent. Fixed                                          
      379 +     with `plotting._set_fov`, which pins every sky panel's xl
          +im/ylim to the same                                           
      380 +     real sky box (computed from mom0, per the explicit design
          + ask: "HI moment 0                                            
      381 +     should be reference") regardless of each panel's own nati
          +ve pixel scale or a                                           
      382 +     backend's rounding of the requested size.                
      383 +  All three fixed together and verified by re-rendering the sa
          +me real source and                                            
      384 +  visually confirming all four sky panels now show identical R
          +A/Dec tick ranges,                                            
      385 +  plus 4 new regression tests in `test_plotting.py` that delib
          +erately give optical                                          
      386 +  and continuum different native pixel scales (the real-world 
          +condition that                                                
      387 +  exposed bug 3) and assert their displayed field of view matc
          +hes within 5%.                                                
      388 +- [ ] Full-scale dry-run re-run with all three fixes (in progr
          +ess -- the batch run                                          
      389 +      before these fixes was discarded since it would have nee
          +ded regenerating                                              
      390 +      anyway; a fresh 448-source run is what's currently execu
          +ting)                                                         
      391 +- [ ] QA + post-process at a representative scale (not fabrica
          +ting full QA                                                  
      392 +      judgments for all 448 sources -- that's inherently a hum
          +an task; already                                              
      393 +      proven correct at real scale in Phases 4/5, revisit here
          + only if the larger                                           
      394 +      dry-run batch surfaces something the smaller real tests 
          +didn't)                                                       
      395  
      396  ### Phase 7 — Polish
      397  - [ ] Fill in `docs/pipeline_overview.md`

⏺ Now let's commit this fix.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Now let's relaunch the full batch — hopefully final this time.

  Ran 1 shell command (ctrl+o to expand)

⏺ Good catch — that was a real, compounding bug (three related issues stemming
  from the same root cause: assumed pixel scales instead of computed ones), now
  fully fixed and verified with matching visual confirmation. Fixed and
  committed:

  1. SkyViewBackend: was requesting cutouts by pixel count using a wrong
  hardcoded DSS2 plate scale (1.7″/pix vs the real 1.0″/pix) — now requests
  field of view directly as an angular quantity, eliminating the assumption
  entirely.
  2. dry_run.py's cutout sizing: used that same wrong 1.7″/pix constant a second
  time, this time for mom0's pixel scale (real value: 6.0″/pix) — now computed
  from mom0's actual WCS.
  3. The real fix for your report: nothing was actually pinning all four sky
  panels (optical, continuum, mom0, mom1) to the same displayed field of view —
  mom0/mom1 only matched by coincidence (sharing the optical panel's WCS), and
  continuum was never constrained at all. Added plotting._set_fov, which now
  forces every sky panel to show the same real sky box computed from mom0,
  exactly as you specified.

  Verified by re-rendering the same real source — all four panels now show
  identical RA/Dec tick ranges, and the field of view is correctly much wider
  (960″ vs the old ~170″), matching the legacy script's intended "5× the
  detection's footprint" context view. Added 4 regression tests that
  deliberately use mismatched optical/continuum pixel scales (the exact
  condition that caused this) to catch any recurrence.

  The full 448-source dry-run is running again in the background with all fixes
  in place. I'll report back once it completes.

✻ Cogitated for 13m 40s

❯ When checking, the fov is way wider. So it's hard to see the details of       
  contours. the Fov should be same as that of the moment-0 maps.                

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 13 lines, removed 6 lines
      22    per panel (PLAN.md section 5, "Provenance").
      23  
      24  Every sky panel (optical, continuum, mom0, mom1) is pinned to t
          he same real
      25 -angular field of view, computed from the mom0 image's own WCS (
         -`reference_field_of_                                           
      26 -view_arcsec`) -- not each panel's own auto-scaled image extent.
         - Found live                                                    
      27 -2026-07-30: the continuum panel's displayed field of view was v
         -isibly wider than                                              
      28 -the others because nothing constrained it to match; only mom0/m
         -om1 borrowed the                                               
      29 -optical panel's pixel limits (which happens to work only becaus
         -e they share its                                               
      30 -exact WCS), and the optical panel itself was never anchored to 
         -anything.                                                      
      25 +angular field of view, computed from the mom0 image's own WCS  
      26 +(`reference_field_of_view_arcsec`) -- not each panel's own auto
         +-scaled image extent.                                          
      27 +Found live 2026-07-30: the continuum panel's displayed field of
         + view was visibly                                              
      28 +wider than the others because nothing constrained it to match; 
         +only mom0/mom1                                                 
      29 +borrowed the optical panel's pixel limits (which happens to wor
         +k only because they                                            
      30 +share its exact WCS), and the optical panel itself was never an
         +chored to anything.                                            
      31 +The reference field of view is exactly mom0's own real footprin
         +t (`DISPLAY_FOV_                                               
      32 +FACTOR = 1`) -- an initial fix used a 5x-wider context view, bu
         +t that made contour                                            
      33 +detail hard to see, per direct feedback, and doesn't actually c
         +orrespond to the                                               
      34 +legacy script's own `npix = max(mom0_shape) * 5`: that multipli
         +ed mom0's *pixel                                               
      35 +count* by 5 and used the result as a pixel count for the optica
         +l cutout request, at                                           
      36 +whatever the optical survey's own (different, generally finer) 
         +pixel scale happens                                            
      37 +to be -- not 5x mom0's real angular size in any survey-independ
         +ent sense.                                                     
      38  """
      39  
      40  from __future__ import annotations

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 4 lines, removed 4 lines
      56  from hivalidate import conversions
      57  from hivalidate.cutouts.base import CutoutResult
      58  
      59 -#: How much wider than the mom0 detection's own footprint to fe
         -tch/display cutouts,                                           
      60 -#: matching the legacy script's `npix = max(mom0_shape) * 5` co
         -nvention -- enough                                             
      61 -#: surrounding sky for context, not just the detection mask its
         -elf.                                                           
      62 -DISPLAY_FOV_FACTOR = 5                                         
      59 +#: How much wider than the mom0 detection's own footprint to fe
         +tch/display cutouts.                                           
      60 +#: 1.0 (exactly mom0's own footprint) per direct feedback 2026-
         +07-30: an earlier 5x                                           
      61 +#: value made the wider context visible but the contour detail 
         +itself hard to see.                                            
      62 +DISPLAY_FOV_FACTOR = 1.0                                       
      63  
      64  
      65  @dataclass

  Read 1 file (ctrl+o to expand)

⏺ This docstring is still accurate (it describes the mechanism generically via
  DISPLAY_FOV_FACTOR, not the specific value), so no change needed there. Let's
  run the tests — the new regression tests explicitly check DISPLAY_FOV_FACTOR,
  so let's confirm they still pass with the updated value.

  Ran 1 shell command (ctrl+o to expand)

⏺ The test name test_reference_fov_is_five_times_mom0s_own_footprint is now
  misleading since the factor is 1.0. Let me rename it for clarity.

  Ran 1 shell command (ctrl+o to expand)
⏺ Update(tests/test_plotting.py)
  ⎿  Added 1 line, removed 1 line
      157          fig = build_validation_figure(row, cubelets, optical=o
           ptical, continuum=continuum)
      158          return fig, cubelets
      159  
      160 -    def test_reference_fov_is_five_times_mom0s_own_footprint(s
          -elf):                                                         
      160 +    def test_reference_fov_is_display_fov_factor_times_mom0s_o
          +wn_footprint(self):                                           
      161          cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB8
           2605_Removal_001_1")
      162          fov = reference_field_of_view_arcsec(cubelets)
      163  

❯ refer to how the original plotting deal with this                             

  Ran 1 shell command (ctrl+o to expand)

⏺ Let me re-verify the legacy script's exact panel-projection choices before
  finalizing, since that's the authoritative reference for the mechanism.

  Ran 1 shell command (ctrl+o to expand)

⏺ Good context to verify against. I checked the legacy script's exact panel
  projections and limits:

  - Panel 1 (optical) uses wcs_opt, panel 2 (continuum) uses its own wcs_cont,
  panels 4/5 (mom0, mom1) reuse wcs_opt and explicitly borrow panel 1's pixel
  xlim/ylim.
  - Legacy achieves "same FOV everywhere" through two different tricks:
  mom0/mom1 borrow panel 1's pixel limits (valid since they share its WCS),
  while continuum's cutout request size is deliberately computed by reading back
  panel 1's actual returned real angular size and requesting that same size for
  continuum — i.e. continuum is sized to chase whatever optical ends up being,
  not computed independently.
  - The reference npix = max(mom0_shape) * 5 is a pixel count taken at DSS2's
  own resolution (~1.0″/pix), not mom0's (6.0″/pix here) — so legacy's actual
  displayed FOV came out to ≈0.83× mom0's real footprint, an artifact of mixing
  pixel counts across two different resolutions, not a deliberate ratio.

  My current _set_fov mechanism already follows the same underlying principle
  (pin every panel to one common reference so they're forced to agree) — panel 2
  correctly keeps its own wcs_cont as projection, matching legacy — just
  anchored explicitly to mom0's real WCS footprint (factor=1.0) instead of
  legacy's incidental ~0.83× via the optical-survey-resolution route, per your
  explicit instruction. This is more robust for our architecture too, since
  continuum now has a multi-backend fallback chain, so "chase whichever backend
  optical happened to use" isn't really available the way it was in legacy's
  single-backend design. Let me re-verify visually with the real source.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ This looks much better — contour detail is clearly visible, all four panels
  match, and it's visually much closer to the reference legacy examples. Let's
  check on the currently-running background batch (built with the wrong 5x
  factor) and restart it.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Background command "rm -rf /Users/rhe003/Research/ASKAP/softwares/validate_sou
rce_finding/data/work/SB82605/dry_run
rm -f /tmp/dry_run_full.log
source ~/miniforge3/etc/profile.d/conda.sh
conda activate base
cd /Users/rhe003/Research/ASKAP/softwares/validate_source_finding
time hivalidate-dry-run --config configs/SB82605.yaml &gt; /tmp/dry_run_full.log
2&gt;&amp;1
echo "EXIT CODE: $?"" completed (exit code 0)

⏺ Let's run the full suite once more, update PLAN.md, and commit before
  relaunching the batch a final time.

  Ran 1 shell command (ctrl+o to expand)

⏺ All 132 tests pass. Let's update PLAN.md and commit.

  Read 1 file, ran 3 shell commands (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 22 lines, removed 2 lines
      385    plus 4 new regression tests in `test_plotting.py` that delib
           erately give optical
      386    and continuum different native pixel scales (the real-world 
           condition that
      387    exposed bug 3) and assert their displayed field of view matc
           hes within 5%.
      388 -- [ ] Full-scale dry-run re-run with all three fixes (in progr
          -ess -- the batch run                                          
      389 -      before these fixes was discarded since it would have nee
          -ded regenerating                                              
      388 +  - **Follow-up correction, same day**: the fix above initiall
          +y used                                                        
      389 +    `DISPLAY_FOV_FACTOR = 5` (all panels 5x wider than mom0's 
          +own footprint) --                                             
      390 +    direct feedback was that this made contour detail hard to 
          +see, and a                                                    
      391 +    request to check how the legacy script actually handled it
          +. Re-read                                                     
      392 +    `legacy/validate_detections.py`'s exact panel projections/
          +limits: it                                                    
      393 +    achieves cross-panel consistency by borrowing pixel limits
          + (mom0/mom1 from                                              
      394 +    optical) and, for continuum, by reading back the optical c
          +utout's *actual*                                              
      395 +    returned real size and requesting that same size for conti
          +nuum (a                                                       
      396 +    fetch-time "chase" mechanism, not a display-time one) -- b
          +ut the reference                                              
      397 +    size it all traces back to, `npix = max(mom0_shape) * 5`, 
          +is a pixel count                                              
      398 +    taken at the *optical survey's own resolution* (~1.0"/pix 
          +for DSS2), not                                                
      399 +    mom0's (6.0"/pix here), so legacy's actual displayed FOV w
          +orked out to                                                  
      400 +    ≈0.83x mom0's real footprint -- an artifact of mixing pixe
          +l counts across                                               
      401 +    two different resolution grids, not a deliberate ratio. Ch
          +anged                                                         
      402 +    `DISPLAY_FOV_FACTOR` to `1.0` (exactly mom0's own footprin
          +t) per the direct                                             
      403 +    instruction, keeping `_set_fov`'s display-time-pinning mec
          +hanism (more                                                  
      404 +    robust than fetch-time chasing now that continuum has a mu
          +lti-backend                                                   
      405 +    fallback chain, so there's no single "whichever backend re
          +sponded" to chase).                                           
      406 +    Re-verified visually: 192 arcsec FOV (vs the first fix's 9
          +60), contour                                                  
      407 +    detail clearly visible, all four panels still matching.   
      408 +- [ ] Full-scale dry-run re-run with all fixes (in progress --
          + two prior full                                               
      409 +      batch runs were discarded since they'd have needed regen
          +erating                                                       
      410        anyway; a fresh 448-source run is what's currently execu
           ting)
      411  - [ ] QA + post-process at a representative scale (not fabrica
           ting full QA
      412        judgments for all 448 sources -- that's inherently a hum
           an task; already

  Read 1 file (ctrl+o to expand)

⏺ Good, that reads fine. Now let's commit and relaunch the batch.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Now relaunching the full 448-source batch with all fixes in place.

  Ran 1 shell command (ctrl+o to expand)

⏺ Good catch, and thanks for pointing me back to the legacy script rather than
  letting me guess at a new number. Summary of what changed:

  - Re-read legacy/validate_detections.py's actual panel projections/limits. Its
  cross-panel consistency came from two mechanisms (borrowed pixel limits for
  mom0/mom1, a fetch-time "chase" for continuum matching whatever optical
  returned), but the reference it all traced back to (npix = max(mom0_shape) * 
  5) was a pixel count taken at the optical survey's resolution, not mom0's — so
  legacy's actual displayed field of view worked out to ≈0.83× mom0's real
  footprint, an accidental byproduct of mixing two different pixel scales, not a
  deliberate "5×" choice.
  - Set DISPLAY_FOV_FACTOR = 1.0 — field of view now exactly matches mom0's own
  footprint, as you asked. Kept the _set_fov display-time-pinning mechanism
  rather than reverting to legacy's fetch-time chase, since that doesn't fit
  cleanly with continuum now having a multi-backend fallback chain.
  - Re-verified visually: 192″ FOV (vs. the previous 960″), contour detail
  clearly visible, all four panels still matching each other.

  Committed, and the full 448-source batch is running again in the background
  with all fixes in place. I'll report back once it completes.

✻ Baked for 9m 11s

※ recap: Building a validation pipeline for HI source-finding results, currently running Phase 6's full end-to-end test across all 448 sources after fixing a field-of-view display bug. Waiting on that batch run to finish before checking the results.

❯ check on the dry-run progress                                                 

  Ran 1 shell command (ctrl+o to expand)

⏺ 217/448 sources done, 0 failures, still running — roughly on track (about
  halfway, ~13 minutes elapsed). No errors so far. I'll keep monitoring and
  report back once it completes.

✻ Brewed for 23s

❯ SoFiA J203449.97-531430.0 missed its pv map. figure out why this happened.    

  Searched for 1 pattern, read 1 file, listed 1 directory, ran 1 shell command (ctrl+o to expand)
⏺ Confirmed — the PV panel is entirely blank, no image data at all. Let me
  inspect this source's actual PV FITS file directly.

  Ran 1 shell command (ctrl+o to expand)

⏺ This isn't a code bug — SoFiA itself generated a PV cubelet for this source
  that's entirely NaN (all 2583 pixels), while mom0/mom1 for the same source
  have real data. Let me check how common this is across the dataset before
  deciding on a fix.

  Ran 1 shell command (ctrl+o to expand)

⏺ Very rare (1/448, 0.2%) — but the current code silently renders a blank panel
  either way, indistinguishable from an actual bug. Let me fix this by making it
  explicit, matching the pattern already used for missing optical/continuum
  cutouts.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 19 lines, removed 8 lines
      317  
      318      # --- panel 6: PV diagram ---
      319      ax_pv = fig.add_subplot(236, projection=cubelets.pv_wcs)
      320 -    freq_c = row["freq"]                                      
      321 -    line_pixel = cubelets.pv_wcs.wcs_world2pix(0, freq_c * 1e-
          -6, 0)                                                         
      322 -    aspect = cubelets.pv_data.shape[1] / cubelets.pv_data.shap
          -e[0]                                                          
      323 -    ax_pv.imshow(                                             
      324 -        cubelets.pv_data, origin="lower", interpolation="neare
          -st", cmap="viridis", aspect=aspect                            
      325 -    )                                                         
      326 -    ax_pv.axhline(y=line_pixel[1], color="red", linestyle="--"
          -)                                                             
      327 -    ax_pv.coords.grid(color="k", alpha=0.5, linestyle="dashed"
          -)                                                             
      320 +    if np.isfinite(cubelets.pv_data).any():                   
      321 +        freq_c = row["freq"]                                  
      322 +        line_pixel = cubelets.pv_wcs.wcs_world2pix(0, freq_c *
          + 1e-6, 0)                                                     
      323 +        aspect = cubelets.pv_data.shape[1] / cubelets.pv_data.
          +shape[0]                                                      
      324 +        ax_pv.imshow(                                         
      325 +            cubelets.pv_data, origin="lower", interpolation="n
          +earest", cmap="viridis", aspect=aspect                        
      326 +        )                                                     
      327 +        ax_pv.axhline(y=line_pixel[1], color="red", linestyle=
          +"--")                                                         
      328 +        ax_pv.coords.grid(color="k", alpha=0.5, linestyle="das
          +hed")                                                         
      329 +    else:                                                     
      330 +        # Found live 2026-07-30: SoFiA itself occasionally wri
          +tes an all-NaN PV                                             
      331 +        # cubelet for a source (rare -- 1/448 in the first ful
          +l run_sofia batch)                                            
      332 +        # even though that same source's mom0/mom1 have real d
          +ata. Not a bug in                                             
      333 +        # this pipeline -- but an unlabelled blank panel is in
          +distinguishable from                                          
      334 +        # one, so say so explicitly rather than silently rende
          +ring nothing.                                                 
      335 +        ax_pv.text(                                           
      336 +            0.5, 0.5, "No PV data available\n(SoFiA produced a
          +n empty PV cubelet)",                                         
      337 +            ha="center", va="center", transform=ax_pv.transAxe
          +s, fontsize=11,                                               
      338 +        )                                                     
      339      ax_pv.coords[0].set_axislabel("Angular Offset (arcsec)", f
           ontsize=14)
      340      ax_pv.coords[0].set_format_unit(u.arcsec)
      341      ax_pv.coords[0].set_major_formatter("x")

⏺ Let's run lint, then verify with the actual problematic source.

  Ran 2 shell commands (ctrl+o to expand)

⏺ That warning is another confirmation this is genuinely a SoFiA-side issue —
  the PV diagram's position angle header (PVD_PA) is literally -NAN for this
  source, meaning SoFiA itself couldn't determine a valid kinematic PA. Let's
  check the rendered fix.

  Read 1 file (ctrl+o to expand)

⏺ The placeholder message works, but the axis grid is cluttered with a
  meaningless tiny auto-scaled range since there's no image to anchor it. Let me
  fix that too.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/plotting.py)
  ⎿  Added 6 lines
      336              0.5, 0.5, "No PV data available\n(SoFiA produced a
           n empty PV cubelet)",
      337              ha="center", va="center", transform=ax_pv.transAxe
           s, fontsize=11,
      338          )
      339 +        # Nothing was imshow()'n for WCSAxes to auto-scale fro
          +m, which otherwise                                            
      340 +        # leaves an arbitrary, tiny, visually cluttered defaul
          +t range -- pin it to                                          
      341 +        # the cubelet's own nominal pixel shape instead, match
          +ing what a real image                                         
      342 +        # would have set.                                     
      343 +        ax_pv.set_xlim(0, cubelets.pv_data.shape[1])          
      344 +        ax_pv.set_ylim(0, cubelets.pv_data.shape[0])          
      345      ax_pv.coords[0].set_axislabel("Angular Offset (arcsec)", f
           ontsize=14)
      346      ax_pv.coords[0].set_format_unit(u.arcsec)
      347      ax_pv.coords[0].set_major_formatter("x")

⏺ Now let's re-verify visually and add regression tests.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Much cleaner now — proper axis range and a clear message instead of a
  confusing blank/cluttered panel. Let's add regression tests and check for the
  other VerifyWarning (-NAN header value) too, since that's a related but
  separate finding.

  Read 1 file (ctrl+o to expand)

⏺ Update(tests/test_plotting.py)
  ⎿  Added 1 line
       7  inspected by eye) is documented in the Phase 3 commit message i
          nstead.
       8  """
       9  
      10 +import dataclasses                                             
      11  from pathlib import Path
      12  
      13  import numpy as np

⏺ Update(tests/test_plotting.py)
  ⎿  Added 33 lines
      110          fig = build_validation_figure(row, cubelets, optical=N
           one, continuum=None)
      111          assert isinstance(fig, Figure)
      112  
      113 +    def test_all_nan_pv_data_shows_a_clear_placeholder_not_a_b
          +lank_panel(self):                                             
      114 +        # Regression test: found live 2026-07-30 that SoFiA oc
          +casionally writes an                                          
      115 +        # all-NaN PV cubelet for a real source (confirmed agai
          +nst the actual data --                                        
      116 +        # 1/448 sources in the first full run_sofia batch; tha
          +t source's own FITS                                           
      117 +        # header even has PVD_PA = -NAN, SoFiA's own record th
          +at it couldn't                                                
      118 +        # determine a kinematic position angle). Not a bug in 
          +this pipeline, but an                                         
      119 +        # unlabelled blank panel looks exactly like one -- mus
          +t say so explicitly.                                          
      120 +        row = _real_row()                                     
      121 +        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB8
          +2605_Removal_001_1")                                          
      122 +        nan_pv_cubelets = dataclasses.replace(                
      123 +            cubelets, pv_data=np.full_like(cubelets.pv_data, n
          +p.nan)                                                        
      124 +        )                                                     
      125 +        fig = build_validation_figure(                        
      126 +            row, nan_pv_cubelets, optical=_fake_cutout(), cont
          +inuum=_fake_cutout()                                          
      127 +        )                                                     
      128 +        ax_pv = fig.axes[-1]                                  
      129 +        texts = [t.get_text() for t in ax_pv.texts]           
      130 +        assert any("No PV data available" in t for t in texts)
      131 +        # No image should have been drawn either.             
      132 +        assert len(ax_pv.images) == 0                         
      133 +                                                              
      134 +    def test_normal_pv_data_is_unaffected_by_the_nan_check(sel
          +f):                                                           
      135 +        row = _real_row()                                     
      136 +        cubelets = load_source_cubelets(FIXTURE_CUBELETS, "SB8
          +2605_Removal_001_1")                                          
      137 +        assert np.isfinite(cubelets.pv_data).any(), "fixture a
          +ssumption changed"                                            
      138 +        fig = build_validation_figure(                        
      139 +            row, cubelets, optical=_fake_cutout(), continuum=_
          +fake_cutout()                                                 
      140 +        )                                                     
      141 +        ax_pv = fig.axes[-1]                                  
      142 +        assert len(ax_pv.images) == 1                         
      143 +        texts = [t.get_text() for t in ax_pv.texts]           
      144 +        assert not any("No PV data available" in t for t in te
          +xts)                                                          
      145 +                                                              
      146      def test_never_calls_plt_show_or_touches_pyplot_state(self
           , monkeypatch):
      147          # This is the whole point of Figure-based construction
            (PLAN.md issue #3) --
      148          # if this function ever imports pyplot and calls show(
           )/creates global state,

  Ran 1 shell command (ctrl+o to expand)

⏺ All pass on the first try. Let's run the full test suite, clean up, update
  PLAN.md, and commit.

  Ran 1 shell command (ctrl+o to expand)

⏺ All 134 tests pass. Let's check whether the currently-running background batch
  is still using the old code (it started before this fix) and needs restarting
  again.

  Searched for 1 pattern (ctrl+o to expand)
⏺ This fix only affects 1 rare source's rendering clarity (not correctness or
  crashes) — unlike the FoV bug, it doesn't warrant restarting the whole
  ~15-more-minute batch at 75% done. Let me commit it now and patch just that
  one PNG once the batch finishes.

  Ran 3 shell commands (ctrl+o to expand)

⏺ Fixed, tested, and committed. Summary:

  - The blank PV panel wasn't a code bug — SoFiA itself produced an entirely-NaN
  PV cubelet for this source (confirmed by inspecting the actual FITS data and
  its PVD_PA = -NAN header, SoFiA's own record that it couldn't determine a
  kinematic position angle). Scanned all 448 cubelets: this affects 1/448
  (0.2%), rare but real.
  - Now shows a clear "No PV data available (SoFiA produced an empty PV
  cubelet)" message instead of a silent blank panel that looks exactly like a
  rendering failure.
  - 2 new regression tests added; 134 tests passing.

  Since this only affects rendering clarity for one rare source (not
  correctness, not a crash), I let the currently-running batch continue rather
  than restart it again — it's at 346/448 with 0 failures. I'll patch that one
  source's PNG with the fix once the batch finishes, and report back.

✻ Brewed for 8m 35s

❯ check on the dry-run progress                                                 

  Ran 1 shell command (ctrl+o to expand)

⏺ 371/448 done (83%), 0 failures, still running. Should finish in the next few
  minutes — I'll report back once it completes.

✻ Sautéed for 26s

※ recap: Rebuilding the SoFiA validation pipeline (Phase 6 of 7); running a full 448-source dry-run to check everything works at scale, now 83% done with zero failures. Next: wait for it to finish, then review results.

❯ check on the dry-run progress                                                 

  Ran 1 shell command (ctrl+o to expand)

⏺ 445/448 done (99%), 0 failures — almost finished. I'll report back with the
  full summary once it completes.

✻ Cogitated for 26s

⏺ Background command "source ~/miniforge3/etc/profile.d/conda.sh
conda activate base
cd /Users/rhe003/Research/ASKAP/softwares/validate_source_finding
time hivalidate-dry-run --config configs/SB82605.yaml &gt; /tmp/dry_run_full.log
2&gt;&amp;1
echo "EXIT CODE: $?"" completed (exit code 0)

  Ran 1 shell command (ctrl+o to expand)

⏺ The full batch completed: 448/448 sources OK, 0 failures. As planned, I still
  need to patch the one PV-NaN source's PNG since that fix was committed mid-run
  (the batch process had already loaded its code into memory before I committed
  it). Let me verify and fix that now.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ While patching that PNG, I noticed something worth fixing: the manifest's
  recorded git commit hash was captured after the batch finished, not when it
  started — meaning if code changes are committed while a long batch is running
  (as happened here), the manifest misattributes which commit actually produced
  the output. Let me fix that.

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/cli/dry_run.py)
  ⎿  Added 8 lines
      75              f"{config.paths.renamed_cubelets_dir} does not exis
          t -- run hivalidate-rename first"
      76          )
      77  
      78 +    # Captured now, before the (potentially long-running) batch
         + loop, not after --                                            
      79 +    # otherwise a code change committed while this process is s
         +till running would                                             
      80 +    # get attributed to output it didn't actually produce (foun
         +d live 2026-07-30: a                                           
      81 +    # bug fix was committed mid-batch, and the finished manifes
         +t's git commit                                                 
      82 +    # initially pointed at that fix even though most of the bat
         +ch had already                                                 
      83 +    # rendered with the previous commit's code, still loaded in
         + this process).                                                
      84 +    git_commit = git_commit_hash()                             
      85 +                                                               
      86      deduped = catalogue.read_votable(config.paths.deduped_catal
          ogue)
      87      optical_chain = build_optical_chain(config)
      88      continuum_chain = build_continuum_chain(config)

⏺ Update(src/hivalidate/cli/dry_run.py)
  ⎿  Added 1 line, removed 1 line
      110      manifest = {
      111          "run_info": {
      112              "hivalidate_version": __version__,
      113 -            "hivalidate_git_commit": git_commit_hash(),       
      113 +            "hivalidate_git_commit": git_commit,              
      114              "config_field_name": config.field_name,
      115              "generated_at": now_iso(),
      116          },

⏺ Let's check if qa.py's merge_qa_into_catalogue has the same issue.

  Ran 1 shell command (ctrl+o to expand)

⏺ I'll leave qa.py as-is — that's a much lower-stakes version of the same issue
  (QA sessions are human-paced and the commit there only reflects merge logic,
  not visually-changing render code), not worth the added complexity right now.
  Let's verify the dry_run.py fix.

  Ran 1 shell command (ctrl+o to expand)

⏺ Let's run the full suite once more and commit.

  Ran 1 shell command (ctrl+o to expand)

⏺ All 134 tests pass. Let's regenerate the manifest with the corrected
  commit-hash timing (harmless — the CLI is idempotent to re-run for just the
  manifest step, but simplest is to just patch the JSON directly since we
  already have the correct data), then commit everything.

  Ran 3 shell commands (ctrl+o to expand)
⏺ Now let's complete the remaining Phase 6 item — proving QA + postprocess work
  against this real, full-scale (448-source) dry-run output, at a representative
  sample (not fabricating full QA judgments for all 448, which is inherently a
  human task).

  Ran 2 shell commands (ctrl+o to expand)

⏺ Now let's run postprocess against this real, partially-reviewed, full-scale
  catalogue.

  Ran 1 shell command (ctrl+o to expand)

⏺ Everything works correctly at full scale. Let's update PLAN.md marking Phase 6
  complete, then commit.

  Read 1 file (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 34 lines, removed 7 lines
      405      fallback chain, so there's no single "whichever backend re
           sponded" to chase).
      406      Re-verified visually: 192 arcsec FOV (vs the first fix's 9
           60), contour
      407      detail clearly visible, all four panels still matching.
      408 -- [ ] Full-scale dry-run re-run with all fixes (in progress --
          - two prior full                                               
      409 -      batch runs were discarded since they'd have needed regen
          -erating                                                       
      410 -      anyway; a fresh 448-source run is what's currently execu
          -ting)                                                         
      411 -- [ ] QA + post-process at a representative scale (not fabrica
          -ting full QA                                                  
      412 -      judgments for all 448 sources -- that's inherently a hum
          -an task; already                                              
      413 -      proven correct at real scale in Phases 4/5, revisit here
          - only if the larger                                           
      414 -      dry-run batch surfaces something the smaller real tests 
          -didn't)                                                       
      408 +- [x] **Full-scale dry-run completed: 448/448 sources OK, 0 fa
          +ilures**, all fixes                                           
      409 +  above included. Two prior full batch runs were discarded mid
          +-flight as bugs were                                          
      410 +  found and fixed rather than let them finish and regenerate a
          +nyway.                                                        
      411 +- **A third real bug found by inspecting this full-scale outpu
          +t**: one source                                               
      412 +  (`SoFiA_J203449.97-531430.0`) had a completely blank PV pane
          +l. Investigated the                                           
      413 +  actual FITS data, not just the code: that source's `*_pv.fit
          +s` cubelet is                                                 
      414 +  entirely NaN (2583/2583 pixels) -- confirmed genuinely SoFiA
          +'s own output (its                                            
      415 +  header's `PVD_PA` is literally `-NAN`, SoFiA's own record th
          +at it couldn't                                                
      416 +  determine a kinematic position angle), not a pipeline bug. S
          +canned all 448 real                                           
      417 +  cubelets: 1/448 (0.2%) have this characteristic. `build_vali
          +dation_figure` now                                            
      418 +  shows "No PV data available (SoFiA produced an empty PV cube
          +let)" instead of a                                            
      419 +  silent blank panel indistinguishable from a rendering failur
          +e. 2 regression                                               
      420 +  tests added.                                                
      421 +- **Reproducibility-metadata bug found while patching the abov
          +e**: the fix for                                              
      422 +  the PV bug was committed *while the 448-source batch was sti
          +ll running* (the                                              
      423 +  process had the older code already loaded in memory). `hival
          +idate-dry-run`'s                                              
      424 +  manifest computed its recorded git commit hash *after* the b
          +atch loop finished,                                           
      425 +  so a fresh `git rev-parse HEAD` at that point picked up the 
          +newer commit from                                             
      426 +  disk -- misattributing nearly the whole batch's actual outpu
          +t to a commit that,                                           
      427 +  in truth, only affected the one source manually re-rendered 
          +afterward. Fixed by                                           
      428 +  capturing the hash once before the batch loop starts instead
          + of after.                                                    
      429 +- [x] QA + post-process re-run against the real, full-scale (4
          +48-source) manifest:                                          
      430 +  scripted a 10-source review (not fabricating judgments for a
          +ll 448 -- that's                                              
      431 +  inherently a human task, already proven correct at real scal
          +e in Phases 4/5),                                             
      432 +  then ran `hivalidate-postprocess` for real against the full 
          +448-source deduped                                            
      433 +  catalogue and the real full-field mosaic: correctly filtered
          + to the 5                                                     
      434 +  true-flagged sources, copied their 65 cubelet files, and bui
          +lt a mosaic FITS                                              
      435 +  matching the field's real (3585, 3552) shape via `reproject_
          +and_coadd`.                                                   
      436 +- **Summary**: four real bugs found and fixed in this phase, n
          +one of them caught                                            
      437 +  by unit tests written against the same wrong assumptions as 
          +the code -- every                                             
      438 +  one required generating and actually looking at real output 
          +(visually or by                                               
      439 +  inspecting the underlying FITS data) to catch. This is the c
          +oncrete case for                                              
      440 +  why PLAN.md's "verified live" pattern was worth the time it 
          +cost throughout                                               
      441 +  every earlier phase, not just this one.                     
      442  
      443  ### Phase 7 — Polish
      444  - [ ] Fill in `docs/pipeline_overview.md`

⏺ Now updating the header to mark Phase 6 as done.

⏺ Update(PLAN.md)
  ⎿  Added 1 line, removed 1 line
      336    the three tiny detections land at their real, distinct sky p
           ositions within the
      337    full field.
      338  
      339 -### Phase 6 — End-to-end validation [in progress]             
      339 +### Phase 6 — End-to-end validation [DONE 2026-07-30]         
      340  - [x] Fresh full-scale combine → dedup → rename over all 45 ru
           ns, from scratch --
      341        reproduced Phase 1's numbers exactly (670 → 448 sources,
            5824 files),
      342        confirming determinism across every later-phase code cha
           nge.

⏺ Let's commit Phase 6's completion.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Phase 6 is complete. Final results:

  - Full-scale dry-run: 448/448 sources OK, 0 failures, with all fixes from this
  session included (that 1 straggler PNG has been re-rendered to match too).
  - QA + postprocess re-verified against this real, full-scale output —
  correctly produced 5 true-flagged sources with their cubelets and a
  properly-shaped mosaic.
  - Cross-check against the 159 legacy "true" examples: 144/159 (90.5%) matched
  within 30″, median separation 2.0″ — strong consistency between independent
  processing runs.

  Four real bugs found and fixed this phase, all caught by actually looking at 
  real output (none were catchable by unit tests, since the tests were written
  against the same wrong assumptions as the code):
  1. SkyView's wrong DSS2 plate scale (1.7″/pix assumed vs. 1.0″/pix real)
  2. The same wrong constant reused for mom0's pixel scale (real: 6.0″/pix)
  3. No display-time constraint pinning all sky panels to a shared field of view
  (your report)
  4. A rare SoFiA-produced all-NaN PV cubelet rendering as a silent blank panel
  (your report)

  Plus a fifth, lower-stakes fix: the dry-run manifest's recorded git commit
  hash was captured after the batch finished rather than before, which would
  misattribute output to the wrong commit if code changes land mid-batch
  (exactly what happened here).

  Only Phase 7 (polish — docs/pipeline_overview.md, finishing the README,
  confirming CI, tagging v0.1) remains. Want me to continue?

✻ Sautéed for 8m 58s

❯ Yes, go ahead with Phase 7                                                    

  Read 2 files, ran 3 shell commands (ctrl+o to expand)

⏺ Let's write docs/pipeline_overview.md, grounded in the real Phase 6 numbers.

⏺ Write(docs/pipeline_overview.md)
  ⎿  Wrote 145 lines to docs/pipeline_overview.md
      1 # Pipeline overview
      2 
        run: all the numbers
      4 below are from the actual `SB82605` field in `data/run_sofia/` (4
        5 independent SoFiA
         the design history
      6 and the bugs found/fixed at each phase; this document is the "how
         it works now"
      8 
      9 ## Data flow
     … +219 lines (ctrl+o to expand)

⏺ Now let's add a small clarification to REFERENCES.md's GAMA entry (currently
  listed but not yet used in code), then update the README.

⏺ Update(REFERENCES.md)
  ⎿  Added 5 lines, removed 1 line
      18  ## Surveys used for cutouts / cross-matching
      19  
      20  - **[GAMA]** Driver, S. P., et al. 2011, "Galaxy and Mass Assem
          bly (GAMA): survey
      21 -  diagnostics and core data release", MNRAS, 413, 971.         
      21 +  diagnostics and core data release", MNRAS, 413, 971. Not yet 
         +used by any code in                                            
      22 +  this repo -- `Config.paths.gama_catalogue` exists in the sche
         +ma, but the actual                                             
      23 +  cross-match (ported from the legacy script's `search_gama`) i
         +s explicitly out of                                            
      24 +  scope for v1 (PLAN.md section 7, "Explicit non-goals"). Kept 
         +here so the citation                                           
      25 +  is ready when/if that's built.                               
      26  - **[DSS2]** STScI Digitized Sky Survey II, accessed via `astro
          query.skyview`.
      27  - **[LegacySurvey]** Dey, A., et al. 2019, "Overview of the DES
          I Legacy Imaging
      28    Surveys", AJ, 157, 168. Cutout service: https://www.legacysur
          vey.org/

⏺ Update(README.md)  ⎿  Added 9 lines, removed 4 lines
       6  renaming, dry-run plot generation, interactive quality assessme
          nt, and post-processing
       7  into a validated source catalogue.
       8  
       9 -See [`PLAN.md`](PLAN.md) for the full design rationale and buil
         -d sequence, and                                                
      10 -[`docs/pipeline_overview.md`](docs/pipeline_overview.md) for a 
         -stage-by-stage                                                 
      11 -walkthrough once it's filled in (Phase 7).                     
       9 +See [`PLAN.md`](PLAN.md) for the full design rationale, build s
         +equence, and every bug                                         
      10 +found/fixed along the way, and [`docs/pipeline_overview.md`](do
         +cs/pipeline_overview.md)                                       
      11 +for a stage-by-stage walkthrough of how it works now.          
      12  
      13  ## Status
      14  
      15 -Under active development -- see `PLAN.md` for phase-by-phase pr
         -ogress.                                                        
      15 +v0.1: all seven build phases in `PLAN.md` complete. Verified en
         +d-to-end against the                                           
      16 +real 45-run `data/run_sofia/` example dataset (670 raw detectio
         +ns -> 448 unique                                               
      17 +sources -> 448/448 dry-run PNGs generated -> QA and post-proces
         +s re-verified against                                          
      18 +that full-scale output). One thing not independently re-derived
         +: the exact numeric                                            
      19 +constant in `conversions.column_density()` -- see `REFERENCES.m
         +d`'s "Known caveat"                                            
      20 +before treating a reported column density as science-final.    
      21  
      22  ## Installation
      23  

⏺ Now let's add a Quick Start section and update the pipeline stages table.

⏺ Update(README.md)
  ⎿  Added 20 lines
      30  version. If `pip install MontagePy` fails, check that a wheel e
          xists for your
      31  Python/OS combination before assuming something else is broken.
      32  
      33 +## Quick start                                                 
      34 +                                                               
      35 +Against the example data in `data/run_sofia/` (see `configs/SB8
         +2605.yaml`):                                                   
      36 +                                                               
      37 +```bash                                                        
      38 +hivalidate-check-connectivity --config configs/SB82605.yaml   #
         + verify backends first                                         
      39 +hivalidate-combine   --config configs/SB82605.yaml             
      40 +hivalidate-dedup     --config configs/SB82605.yaml             
      41 +hivalidate-rename    --config configs/SB82605.yaml             
      42 +hivalidate-dry-run   --config configs/SB82605.yaml            #
         + HPC-safe -- run this on the cluster                           
      43 +hivalidate-qa        --config configs/SB82605.yaml            #
         + run this locally, not on HPC                                  
      44 +hivalidate-postprocess --config configs/SB82605.yaml           
      45 +```                                                            
      46 +                                                               
      47 +Each stage reads its input from disk and checks it exists, so t
         +hey don't need to run                                          
      48 +back-to-back in one session -- dry-run in particular is meant t
         +o run unattended on an                                         
      49 +HPC compute node, with QA picking up its output later on a mach
         +ine with a display.                                            
      50 +See [`docs/pipeline_overview.md`](docs/pipeline_overview.md) fo
         +r what each stage                                              
      51 +reads/writes and why.                                          
      52 +                                                               
      53  ## Configuration
      54  
      55  Each field/SB gets its own YAML config under `configs/` (see `c
          onfigs/SB82605.yaml`

⏺ Update(README.md)
  ⎿  Added 1 line
      156  
      157  | Stage | Command | Notes |
      158  |---|---|---|
      159 +| Connectivity check | `hivalidate-check-connectivity` | Verif
          +y every configured cutout backend before a big batch run |    
      160  | Combine | `hivalidate-combine` | Merge per-run SoFiA catalog
           ues into one |
      161  | Dedup | `hivalidate-dedup` | Positional/velocity cross-match
            dedup, not string match |
      162  | Rename | `hivalidate-rename` | Map per-run numeric IDs to so
           urce names, copy cubelets |

⏺ Now let's verify the CI workflow itself is correct and would actually pass, by
  re-checking its exact steps and validating YAML syntax.

  Read 1 file, ran 2 shell commands (ctrl+o to expand)

⏺ Good, YAML is valid and the branch name matches. Now let's do a final clean
  verification of the exact steps from a fresh perspective (matching CI order
  precisely).

  Ran 2 shell commands (ctrl+o to expand)

⏺ CI steps confirmed passing locally. Now let's audit the "every HI-physics
  function cites REFERENCES.md" requirement from the definition of done.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/conversions.py)
  ⎿  Added 4 lines
      32      """Convert observed frequency to redshift for the HI 21cm l
          ine.
      33  
      34      z = f_HI / f_obs - 1
      35 +                                                               
      36 +    The definitional relation between redshift and rest/observe
         +d frequency -- not                                             
      37 +    survey- or paper-specific, so not separately cited in REFER
         +ENCES.md beyond the                                            
      38 +    HI_REST_FREQ_HZ value itself (a standard physical constant)
         +.                                                              
      39      """
      40      return HI_REST_FREQ_HZ / freq_hz - 1.0
      41  

⏺ Update(src/hivalidate/conversions.py)
  ⎿  Added 4 lines, removed 2 lines
      62  
      63  def velocity_to_freq(vel_m_s: np.ndarray | float, v_frame: str 
          = "optical") -> np.ndarray | float:
      64      """Convert line-of-sight velocity (in m/s) to observed freq
          uency. Inverse of
      65 -    `freq_to_velocity`, but note the input unit is m/s here (ma
         -tching the legacy                                              
      66 -    script) while `freq_to_velocity` returns km/s -- callers mu
         -st convert explicitly.                                         
      65 +    `freq_to_velocity` (see REFERENCES.md, radio/optical veloci
         +ty convention entry,                                           
      66 +    for the underlying relation), but note the input unit is m/
         +s here (matching the                                           
      67 +    legacy script) while `freq_to_velocity` returns km/s -- cal
         +lers must convert                                              
      68 +    explicitly.                                                
      69      """
      70      c_m_s = SPEED_OF_LIGHT_KM_S * 1000.0
      71      if v_frame == "optical":

⏺ Update(src/hivalidate/conversions.py)
  ⎿  Added 5 lines, removed 3 lines
      79      freq_width_hz: np.ndarray | float, freq_centre_hz: np.ndarr
          ay | float
      80  ) -> np.ndarray | float:
      81      """Convert a frequency width (e.g. SoFiA's w20/w50/wm50 lin
          ewidths) to a velocity
      82 -    width, using the local (non-relativistic) approximation dv 
         -= c * df / f0.                                                 
      83 -    Adequate at DINGO/WALLABY-pilot redshifts (z << 1); would n
         -eed a relativistic                                             
      84 -    treatment to be accurate at cosmological distances.        
      82 +    width, using the local (non-relativistic) approximation dv 
         += c * df / f0ac -- the                                         
      83 +    same radio/optical convention as `freq_to_velocity` (REFERE
         +NCES.md), applied to a                                         
      84 +    width instead of an absolute frequency. Adequate at DINGO/W
         +ALLABY-pilot redshifts                                         
      85 +    (z << 1); would need a relativistic treatment to be accurat
         +e at cosmological                                              
      86 +    distances.                                                 
      87      """
      88      return SPEED_OF_LIGHT_KM_S * freq_width_hz / freq_centre_hz
      89  

⏺ Update(src/hivalidate/conversions.py)
  ⎿  Added 1 line, removed 1 line
      79      freq_width_hz: np.ndarray | float, freq_centre_hz: np.ndarr
          ay | float
      80  ) -> np.ndarray | float:
      81      """Convert a frequency width (e.g. SoFiA's w20/w50/wm50 lin
          ewidths) to a velocity
      82 -    width, using the local (non-relativistic) approximation dv 
         -= c * df / f0ac -- the                                         
      82 +    width, using the local (non-relativistic) approximation dv 
         += c * df / f0 -- the                                           
      83      same radio/optical convention as `freq_to_velocity` (REFERE
          NCES.md), applied to a
      84      width instead of an absolute frequency. Adequate at DINGO/W
          ALLABY-pilot redshifts
      85      (z << 1); would need a relativistic treatment to be accurat
          e at cosmological

⏺ Now let's add a note to column_density_sensitivity too, and double-check the
  fix with a fresh read.

  Read 1 file, ran 1 shell command (ctrl+o to expand)

⏺ Update(src/hivalidate/conversions.py)
  ⎿  Added 3 lines, removed 1 line
      163      n_sigma: float,
      164  ) -> np.ndarray | float:
      165      """N-sigma column-density detection limit for a given per-
           channel RMS noise,
      166 -    by plugging the N-sigma flux limit (rms * channel width * 
          -N) into `column_density`.                                     
      166 +    by plugging the N-sigma flux limit (rms * channel width * 
          +N) into `column_density`                                      
      167 +    -- see that function's docstring and REFERENCES.md's "Know
          +n caveat" entry for the                                       
      168 +    citation and the caveat on the underlying constant.       
      169      """
      170      s_limit = rms_noise * freq_width_hz * n_sigma
      171      return column_density(s_limit, z, beam_area_arcsec2)

⏺ Let's run lint and the conversions tests to confirm the docstring edits didn't
  break anything.

  Ran 1 shell command (ctrl+o to expand)

⏺ Now let's bump the version for the v0.1 release.

  Read 1 file (ctrl+o to expand)

⏺ Update(pyproject.toml)
  ⎿  Added 1 line, removed 1 line
       4  
       5  [project]
       6  name = "hivalidate"
       7 -version = "0.1.0.dev0"                                         
       7 +version = "0.1.0"                                              
       8  description = "Validation pipeline for SoFiA HI source-finding 
          output (DINGO/WALLABY-style ASKAP surveys)."
       9  readme = "README.md"
      10  license = { file = "LICENSE" }

  Read 1 file (ctrl+o to expand)

⏺ Update(src/hivalidate/__init__.py)  ⎿  Added 1 line, removed 1 line
      1  """hivalidate: validation pipeline for SoFiA HI source-finding o
         utput."""
      2  
      3 -__version__ = "0.1.0.dev0"                                      
      3 +__version__ = "0.1.0"                                           

  Ran 1 shell command (ctrl+o to expand)

⏺ All good, version bumped to 0.1.0 and everything still passes. Now let's
  update PLAN.md's Phase 7 checklist and Definition of Done.

  Read 1 file (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 45 lines, removed 16 lines
      440    why PLAN.md's "verified live" pattern was worth the time it 
           cost throughout
      441    every earlier phase, not just this one.
      442  
      443 -### Phase 7 — Polish                                          
      444 -- [ ] Fill in `docs/pipeline_overview.md`                     
      445 -- [ ] Finish `README.md`, confirm `REFERENCES.md` covers all c
          -ited science                                                  
      446 -- [ ] Confirm CI green, tag `v0.1`                            
      443 +### Phase 7 — Polish [DONE 2026-07-30]                        
      444 +- [x] Filled in `docs/pipeline_overview.md`: data-flow diagram
          + (Mermaid) plus a                                             
      445 +      stage-by-stage walkthrough grounded in the real Phase 6 
          +numbers (670 -> 448                                           
      446 +      sources, 33% dedup rate, 5824 cubelet files, 448/448 dry
          +-run success), not                                            
      447 +      illustrative placeholders.                              
      448 +- [x] `README.md`: Status section updated to reflect all seven
          + phases complete (and                                         
      449 +      the one known unresolved item -- `column_density`'s unve
          +rified constant --                                            
      450 +      surfaced there, not buried); added a Quick Start with th
          +e full real command                                           
      451 +      sequence; added `hivalidate-check-connectivity` to the s
          +tages table (it existed                                       
      452 +      since Phase 2 but was missing from this table).         
      453 +- [x] `REFERENCES.md` cross-checked against actual code citati
          +ons (`grep` for every                                         
      454 +      bracketed key across `src/`): every citation used in cod
          +e has a matching entry,                                       
      455 +      and every physics function in `conversions.py` now has a
          + docstring pointing at                                        
      456 +      one, including the small helpers (`freq_to_redshift`, `v
          +elocity_to_freq`,                                             
      457 +      `freq_width_to_velocity_dispersion`, `column_density_sen
          +sitivity`) that just                                          
      458 +      derive from an already-cited relation rather than needin
          +g a separate source.                                          
      459 +      Added a note to the `[GAMA]` entry clarifying it's not u
          +sed by any code yet                                           
      460 +      (the cross-match itself is an explicit non-goal, section
          + 7) so its presence in                                        
      461 +      the bibliography doesn't look like an oversight.        
      462 +- [x] CI verified green by actually running its exact steps lo
          +cally, not just                                               
      463 +      reading the workflow file: `pip install -e ".[dev]"`, `r
          +uff check src tests`,                                         
      464 +      `pytest -v` -- 134 passed, lint clean. Confirmed the wor
          +kflow's YAML parses                                           
      465 +      and its `branches: [main]` trigger matches the repo's ac
          +tual current branch.                                          
      466 +- [x] Version bumped `0.1.0.dev0` -> `0.1.0` in `pyproject.tom
          +l` and                                                        
      467 +      `hivalidate.__version__`; tagged `v0.1` (local tag only 
          +-- this repository has                                        
      468 +      no configured remote to push it to).                    
      469  
      470  ## 9. Definition of done for v1
      471  
      450 -- Pipeline runs end-to-end on `run_sofia/` via CLI, driven ent
          -irely by a config file                                        
      451 -  (no hardcoded per-field constants left in source).          
      452 -- Optical cutouts fall back SkyView → Legacy Survey; continuum
          - falls back local file →                                      
      453 -  RACS/CASDA (non-interactive login); both cached and provenan
          -ce-tracked.                                                   
      454 -- Dry-run runs unattended on an HPC compute node (`Agg` only, 
          -no display, no                                                
      472 +- [x] Pipeline runs end-to-end on `run_sofia/` via CLI, driven
          + entirely by a config                                         
      473 +  file (no hardcoded per-field constants left in source).     
      474 +- [x] Optical cutouts fall back SkyView → Legacy Survey; conti
          +nuum falls back local                                         
      475 +  file → RACS/CASDA (non-interactive login); both cached and p
          +rovenance-tracked.                                            
      476 +- [x] Dry-run runs unattended on an HPC compute node (`Agg` on
          +ly, no display, no                                            
      477    interactive prompts) and produces plots + manifest for the w
           hole sample before any
      478    QA happens.
      457 -- QA runs as a fully separate stage against the dry-run output
          - (no live cutout/figure                                       
      458 -  regeneration), is resumable, and never loses progress on int
          -erruption.                                                    
      459 -- A preflight connectivity/auth check (CASDA login + trivial q
          -uery, image-survey                                            
      479 +- [x] QA runs as a fully separate stage against the dry-run ou
          +tput (no live                                                 
      480 +  cutout/figure regeneration), is resumable, and never loses p
          +rogress on                                                    
      481 +  interruption.                                               
      482 +- [x] A preflight connectivity/auth check (CASDA login + trivi
          +al query, image-survey                                        
      483    reachability) runs automatically before dry-run starts proce
           ssing sources, and
      484    fails fast with a clear error if something's misconfigured.
      462 -- `tests/` pass in CI against the fixture; a full run against 
          -`run_sofia/` has been                                         
      463 -  done at least once and checked against `data/output_validati
          -on_true/`.                                                    
      464 -- Every function touching HI physics has a docstring citing `R
          -EFERENCES.md`.                                                
      465 -- Git history exists from phase 0 onward; no large data files 
          -committed.                                                    
      485 +- [x] `tests/` pass in CI against the fixture (134 passed, ver
          +ified locally against                                         
      486 +  the exact CI steps); a full run against `run_sofia/` has bee
          +n done (448/448 OK)                                           
      487 +  and checked against `data/output_validation_true/` (144/159,
          + 90.5%, matched                                               
      488 +  positionally within 30").                                   
      489 +- [x] Every function touching HI physics has a docstring citin
          +g `REFERENCES.md`.                                            
      490 +- [x] Git history exists from phase 0 onward (16 commits); no 
          +large data files                                              
      491 +  committed (`.git` is 16 MB; largest tracked file is a 484 KB
          + fixture FITS file,                                           
      492 +  committed deliberately for tests).                          
      493 +                                                              
      494 +All definition-of-done items satisfied. v0.1 tagged.          

  Read 1 file (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 5 lines, removed 3 lines
       1  # HI Source-Finding Validation Pipeline — Implementation Plan
       2  
       3 -Status: draft, not yet started. This document captures everythi
         -ng decided in planning                                         
       4 -discussion before writing code. Update it as decisions change —
         - it should stay the                                            
       5 -single source of truth for scope and sequencing.               
       3 +Status: **v0.1 complete (2026-07-30)** — all seven phases below
         + done, definition of                                           
       4 +done (section 9) fully satisfied. This document captures everyt
         +hing decided during                                            
       5 +planning and every bug found/fixed during implementation; it re
         +mains the source of                                            
       6 +truth for design rationale even though active build-out is fini
         +shed. Update it if                                             
       7 +that changes (new phases, a v0.2 scope, etc.).                 
       8  
       9  ## 1. Goal
      10  

⏺ Now let's commit everything and create the v0.1 tag.

  Ran 3 shell commands (ctrl+o to expand)

⏺ Phase 7 is complete, and that closes out v0.1. Summary:

  - docs/pipeline_overview.md written — a data-flow diagram plus stage-by-stage
  walkthrough grounded in the real Phase 6 numbers (670→448 sources, 33% dedup
  rate, 448/448 dry-run success), not placeholder text.
  - README.md updated — Status section reflects completion (and surfaces the one
  known caveat, column_density's unverified constant, rather than burying it),
  added a real Quick Start command sequence, added the missing
  hivalidate-check-connectivity row to the stages table.
  - REFERENCES.md cross-checked against actual code — grepped every bracketed
  citation key across src/ to confirm each has a matching entry, and added
  docstring pointers to the handful of small conversion helpers that were
  missing one.
  - CI verified green for real — ran its exact steps locally (pip install -e 
  ".[dev]", ruff check, pytest -v), not just read the YAML: 134 passed, lint
  clean. Also confirmed the workflow's trigger branch matches the repo's actual
  branch.
  - Version bumped 0.1.0.dev0 → 0.1.0, and tagged v0.1 locally (this repo has no
  remote configured, so nothing was pushed — the tag just marks the commit).

  Every item in PLAN.md's Definition of Done is now checked off. That's all
  seven phases: scaffolding, core catalogue layer, cutout fallback chains,
  HPC-safe dry-run plotting, resumable local QA, post-processing, and full-scale
  end-to-end validation — with six real bugs found and fixed along the way by
  actually generating and inspecting output rather than trusting tests alone,
  several of them from your own review of real plots. hivalidate is now a
  tested, documented, config-driven package replacing the original nine ad hoc
  scripts.

✻ Worked for 14m 40s