"""Preflight connectivity/auth check for every configured cutout backend.

Run this before a large `hivalidate-dry-run` batch, especially on a new machine or
after credentials might have changed -- it's meant to catch a broken CASDA login or a
network/proxy issue in seconds, not after it's silently degraded a few hundred
sources' continuum images partway through an HPC batch job (PLAN.md section 5,
"Preflight connectivity check"). `hivalidate-dry-run` also runs this automatically
before it starts (see cli/dry_run.py); this command exists so you can run it
standalone, without committing to a full batch run.

Exits 0 if every configured backend is available, 1 otherwise.
"""

from __future__ import annotations

import logging
import sys

from hivalidate.cli._common import base_parser, configure_logging
from hivalidate.config import Config
from hivalidate.cutouts.registry import build_continuum_chain, build_optical_chain

logger = logging.getLogger(__name__)


def run(config: Config) -> bool:
    """Returns True iff every configured backend is available."""
    all_ok = True
    for kind, chain in [
        ("optical", build_optical_chain(config)),
        ("continuum", build_continuum_chain(config)),
    ]:
        for backend in chain:
            ok, message = backend.is_available()
            status = "OK" if ok else "FAILED"
            logger.info("[%s] %s backend '%s': %s", status, kind, backend.name, message)
            all_ok = all_ok and ok
    return all_ok


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)

    ok = run(config)
    if not ok:
        logger.error("One or more backends failed the connectivity check -- see above")
        sys.exit(1)
    logger.info("All configured backends are available")


if __name__ == "__main__":
    main()
