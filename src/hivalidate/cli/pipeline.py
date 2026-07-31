"""Run the whole hivalidate pipeline in one command, in one of two modes, instead of
invoking each `hivalidate-*` stage from the README's Quick start by hand.

- `--mode dry-run`: check-connectivity, combine, dedup, rename, dry-run. Stops there --
  no interactive QA, so this is safe to run unattended on an HPC compute node
  (PLAN.md section 5). Produces `dry_run/manifest.json` and the validation PNGs for
  `--mode qa` to pick up later, possibly on a different machine.
- `--mode qa`: qa, postprocess. Requires `dry_run/manifest.json` to already exist --
  this mode never touches combine/dedup/rename/dry-run itself, so it never redoes a
  cutout fetch or a dedup pass against whatever `raw_sofia_dir` happens to resolve to
  on the machine you're doing QA on. Run this locally, with a display.

Splits at the same HPC/local boundary `hivalidate-dry-run`/`hivalidate-qa` already
have (see docs/pipeline_overview.md) -- this command doesn't change what each stage
does, only saves typing out the individual commands in sequence.
"""

from __future__ import annotations

import logging
import sys

from hivalidate.cli import check_connectivity, combine, dedup, postprocess, rename
from hivalidate.cli._common import base_parser, configure_logging
from hivalidate.config import Config

logger = logging.getLogger(__name__)


def run_dry_run_mode(config: Config) -> None:
    """check-connectivity -> combine -> dedup -> rename -> dry-run. Stops before QA."""
    # Imported lazily, not at module level: hivalidate.cli.dry_run forces the Agg
    # backend as a side effect of import, which must never happen in a process that
    # also runs --mode qa's real interactive display (see hivalidate.qa's module
    # docstring -- a backend can't be switched after pyplot has already been used).
    from hivalidate.cli import dry_run

    ok = check_connectivity.run(config)
    if not ok:
        logger.warning(
            "One or more cutout backends failed the connectivity check -- continuing, "
            "since a fallback chain with some backends down can still work. "
            "hivalidate-dry-run will abort on its own below if an entire chain is "
            "unusable."
        )

    combine.run(config)
    dedup.run(config)
    rename.run(config)
    dry_run.run(config)


def run_qa_mode(config: Config) -> None:
    """qa -> postprocess. Requires dry_run/manifest.json to already exist (produced by
    --mode dry-run, possibly on a different machine) -- never reruns combine/dedup/
    rename/dry-run itself.
    """
    from hivalidate import qa as qa_module

    manifest_path = config.paths.dry_run_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(
            f"{manifest_path} does not exist -- run `hivalidate-run-pipeline --mode "
            f"dry-run` (or the individual hivalidate-combine/-dedup/-rename/-dry-run "
            f"commands) first, possibly on a different machine, then point this "
            f"config's paths at that output."
        )

    try:
        qa_module.run_qa_session(
            config,
            prompt_fn=qa_module.default_prompt,
            display_fn=qa_module.default_display,
            close_fn=qa_module.default_close,
        )
    except KeyboardInterrupt:
        # Matches hivalidate.cli.qa's own behaviour: qa_results.json is saved
        # incrementally, but validated_cat.xml is only (re)written once run_qa_session
        # returns normally -- an interrupt skips postprocess deliberately rather than
        # running it against a stale/missing validated_cat.xml. Re-run the same
        # command to pick up where you left off (already-reviewed sources are
        # skipped instantly) and it'll reach postprocess.
        logger.info(
            "Interrupted -- progress up to the last reviewed source was already "
            "saved. Re-run the same command to finish QA and continue to postprocess."
        )
        return

    postprocess.run(config)


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["dry-run", "qa"],
        help="'dry-run': check-connectivity+combine+dedup+rename+dry-run (HPC-safe, "
        "stops before QA). 'qa': qa+postprocess (run locally, after --mode dry-run "
        "has already produced dry_run/manifest.json).",
    )
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)

    if args.mode == "dry-run":
        run_dry_run_mode(config)
    else:
        run_qa_mode(config)


if __name__ == "__main__":
    sys.exit(main())
