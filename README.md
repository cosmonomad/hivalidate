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
[OPAL](https://opal.atnf.csiro.au/) account.

**Important, and not obvious from astroquery's docs:** `Casda.login()` only accepts a
`username` -- there is no `password=` parameter. The password always comes from your
OS keyring, or an interactive prompt if it isn't there yet. `hivalidate`'s
`RacsCasdaBackend` was built around this, and has since been **verified live against
a real OPAL account (2026-07-30)** -- login, RACS filtering, cutout request, and
download all confirmed working end to end. That session also found and fixed two real
bugs, both covered by regression tests now:

- This environment's astroquery (0.4.11) has its own bug: `login()`'s return value is
  always `None`/falsy regardless of outcome (it discards the real result internally).
  `RacsCasdaBackend` checks `casda.authenticated()` instead, which isn't affected.
  If you see astroquery's own log say "Authentication successful!" immediately
  before `hivalidate-check-connectivity` reports `racs_casda` as failed, you're on an
  astroquery version with the same bug and an older `hivalidate` that hadn't been
  fixed yet -- update.
- Real RACS cutouts come back with degenerate Stokes/frequency axes (shape
  `(1, 1, ny, nx)`), not 2D like every other backend -- `fetch()` squeezes these down.

Still worth doing a one-time check yourself on a new machine/account, since keyring
behaviour is environment-specific (see below):

### Option A: one-time interactive login (simplest, if your keyring works)

On the machine that will actually run `hivalidate-dry-run` (e.g. the HPC login node,
since your compute nodes have outbound internet but the credential needs to be usable
from wherever the job runs), run once:

```bash
export CASDA_USERNAME=you@example.com
python3 -c "
from astroquery.casda import Casda
casda = Casda()
casda.login(username='$CASDA_USERNAME', store_password=True)
# Not 'casda.login(...) ' return value -- some astroquery versions (0.4.11,
# confirmed) always return None/falsy there regardless of outcome. Check the real
# state instead:
print('login OK' if casda.authenticated() else 'login FAILED')
"
```

It will prompt for your OPAL password once, then store it in your OS/user keyring.
Every subsequent non-interactive run (as long as `$CASDA_USERNAME` is set) will read
the password from the keyring silently -- you do **not** need to set `CASDA_PASSWORD`
for this option.

If this raises something like `NoKeyringError`, your login node doesn't have a usable
keyring backend (common on headless Linux systems with no desktop session) -- use
Option B instead. If `login OK` prints but a later `security find-generic-password -s
"astroquery:casda.csiro.au"` (macOS) or equivalent doesn't find an entry, double check
you're running the same Python install everywhere (`python3 -c "import sys;
print(sys.executable)"`) -- a different Python can mean a completely separate keyring
configuration.

### Option B: `CASDA_PASSWORD` env var (works even with no system keyring)

```bash
export CASDA_USERNAME=you@example.com
export CASDA_PASSWORD=...          # never committed; treat like any other secret
```

If `$CASDA_PASSWORD` is set, `RacsCasdaBackend` seeds a keyring entry itself (via the
plain public `keyring.set_password` API, using the exact service name astroquery's
own login looks up) immediately before calling `casda.login()`, so it never prompts.
If your environment has no keyring backend at all, this will fail with a clear error
telling you to install and configure `keyrings.alt`'s file-based backend --
hivalidate does not silently reconfigure your keyring backend for you.

### Verifying it yourself

```bash
hivalidate-check-connectivity --config configs/<field>.yaml
```

This runs every configured backend's cheap availability check, including a real
`casda.login()` call (no cutout download) for `racs_casda`. Look for:

```
[OK] continuum backend 'racs_casda': OK
```

If it instead prints `[FAILED] ... $CASDA_USERNAME is not set`, `... login failed`, or
the keyring error above, that tells you which of the two options above to fix. Once
connectivity passes, the actual cutout logic (RACS filtering, cutout request,
download) still hasn't been exercised against a real account -- run
`hivalidate-dry-run` on a small config with a field known to have RACS coverage
(anything south of Dec +41, per `RacsCasdaBackend.DEC_LIMIT_DEG`) and inspect one of
the resulting continuum panels before trusting it for a full batch.

Never put credentials in a config file that gets committed to git.

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
