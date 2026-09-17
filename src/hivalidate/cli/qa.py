"""Interactive review of dry-run output. Run this locally (on a machine with a
display), not on HPC -- see `hivalidate.qa`'s module docstring for why. Run
`hivalidate-dry-run` first.

Resumable: Ctrl-C or the 'q' (save & quit) flag at any point saves everything
reviewed so far; re-running this command picks up where you left off. 'b' (back)
re-opens the previous source so a mis-keyed flag doesn't require restarting.

Pass --reassess to instead (also) re-open sources already marked with one or more
given classes, e.g. `--reassess uncertain,duplicate` -- for a second look once more
of the field has been reviewed, without re-reviewing everything already marked
true/false or hand-editing qa_results.json.
"""

from __future__ import annotations

import logging
import sys

from hivalidate import postprocess, qa
from hivalidate.cli._common import base_parser, configure_logging
from hivalidate.config import Config

logger = logging.getLogger(__name__)


def _parse_reassess(reassess: str | None) -> set[str] | None:
    if not reassess:
        return None
    classes = {c.strip() for c in reassess.split(",") if c.strip()}
    unknown = classes - set(postprocess.QA_CLASSES)
    if unknown:
        raise SystemExit(
            f"Unknown --reassess class(es): {sorted(unknown)} -- "
            f"valid: {sorted(postprocess.QA_CLASSES)}"
        )
    return classes


def run(config: Config, reassess_classes: set[str] | None = None) -> dict:
    manifest_path = config.paths.dry_run_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"{manifest_path} does not exist -- run hivalidate-dry-run first")
    return qa.run_qa_session(
        config,
        prompt_fn=qa.default_prompt,
        display_fn=qa.default_display,
        close_fn=qa.default_close,
        reassess_classes=reassess_classes,
    )


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    parser.add_argument(
        "--reassess",
        help="Comma-separated QA classes to also re-open for review "
        "(e.g. 'uncertain,duplicate'), on top of anything not yet reviewed",
    )
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)
    reassess_classes = _parse_reassess(args.reassess)
    try:
        run(config, reassess_classes=reassess_classes)
    except KeyboardInterrupt:
        logger.info("Interrupted -- progress up to the last reviewed source was already saved.")


if __name__ == "__main__":
    sys.exit(main())
