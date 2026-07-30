# hivalidate

Validation pipeline for [SoFiA 2](https://github.com/SoFiA-Admin/SoFiA-2) HI
source-finding output from ASKAP surveys (developed against DINGO/WALLABY-style data).
Takes raw per-run SoFiA catalogues and cubelets through combination, deduplication,
renaming, dry-run plot generation, interactive quality assessment, and post-processing
into a validated source catalogue.

See [`PLAN.md`](PLAN.md) for the full design rationale and build sequence, and
[`docs/pipeline_overview.md`](docs/pipeline_overview.md) for a stage-by-stage
walkthrough once it's filled in (Phase 7).

## Status

Under active development -- see `PLAN.md` for phase-by-phase progress.

## Installation

```bash
conda env create -f environment.yml
conda activate hivalidate
```

MontagePy ships prebuilt wheels on PyPI, but availability varies by platform/Python
version. If `pip install MontagePy` fails, check that a wheel exists for your
Python/OS combination before assuming something else is broken.

## Configuration

Each field/SB gets its own YAML config under `configs/` (see `configs/SB82605.yaml`
for the example used against `data/run_sofia/`). Every CLI stage takes a config file
as its `--config` argument -- no per-field values are hardcoded in the package.

## CASDA / RACS access

The continuum cutout fallback (used when no local continuum mosaic covers a field)
queries RACS via `astroquery.casda`, which requires an
[OPAL](https://opal.atnf.csiro.au/) account. Set credentials as environment variables
before running any stage that needs continuum cutouts:

```bash
export CASDA_USERNAME=you@example.com
export CASDA_PASSWORD=...          # never committed; consider a secrets manager
                                    # or your shell's own credential store instead
                                    # of a plaintext export in scripts/history
```

Never put credentials in a config file that gets committed to git. Run
`hivalidate-check-connectivity --config configs/<field>.yaml` before a large batch
job to confirm login and network access work before committing HPC time to it.

## Pipeline stages

| Stage | Command | Notes |
|---|---|---|
| Combine | `hivalidate-combine` | Merge per-run SoFiA catalogues into one |
| Dedup | `hivalidate-dedup` | Positional/velocity cross-match dedup, not string match |
| Rename | `hivalidate-rename` | Map per-run numeric IDs to source names, copy cubelets |
| Dry-run | `hivalidate-dry-run` | Batch-generate validation plots, HPC-safe (`Agg`, no prompts) |
| QA | `hivalidate-qa` | Interactive review of dry-run output; run locally, not on HPC |
| Post-process | `hivalidate-postprocess` | Validation CSV, extract true cubelets, mosaic |

## Development

```bash
pip install -e ".[dev]"
pre-commit install
pytest            # runs against tests/fixtures/, not the full data/run_sofia/ set
```

## License

BSD-3-Clause, see [`LICENSE`](LICENSE).
