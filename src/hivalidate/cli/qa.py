"""Interactive review of dry-run output. Run this locally (on a machine with a
display), not on HPC -- see `hivalidate.qa`'s module docstring for why. Run
`hivalidate-dry-run` first.

Resumable: Ctrl-C or the 'q' (save & quit) flag at any point saves everything
reviewed so far; re-running this command picks up where you left off. 'b' (back)
re-opens the previous source so a mis-keyed flag doesn't require restarting.
"""

from __future__ import annotations

import logging
import sys

from hivalidate import qa
from hivalidate.cli._common import base_parser, configure_logging
from hivalidate.config import Config

logger = logging.getLogger(__name__)


def run(config: Config) -> dict:
    manifest_path = config.paths.dry_run_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"{manifest_path} does not exist -- run hivalidate-dry-run first")
    return qa.run_qa_session(
        config,
        prompt_fn=qa.default_prompt,
        display_fn=qa.default_display,
        close_fn=qa.default_close,
    )


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)
    try:
        run(config)
    except KeyboardInterrupt:
        logger.info("Interrupted -- progress up to the last reviewed source was already saved.")


if __name__ == "__main__":
    sys.exit(main())
