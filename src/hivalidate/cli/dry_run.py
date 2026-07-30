"""Batch-generate validation plots for every source in the deduped catalogue.

The HPC-safe stage (PLAN.md Phase 3): forces the `Agg` backend, never calls
`plt.show()` or blocks on input, and isolates each source in its own try/except so
one bad cutout/plot doesn't abort a run that might cover hundreds of sources
(PLAN.md issue #8). Writes a manifest (`manifest.json`) that `hivalidate-qa` (Phase 4)
consumes -- QA never re-fetches cutouts or regenerates figures, it only ever looks at
what this command already produced.

Run `hivalidate-combine`, `hivalidate-dedup`, and `hivalidate-rename` first.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # must happen before pyplot/plotting is touched anywhere

import matplotlib.pyplot as plt  # noqa: E402 -- only used to close figures, never to show them
from astropy.coordinates import SkyCoord  # noqa: E402

from hivalidate import __version__, catalogue, plotting  # noqa: E402
from hivalidate.cli._common import base_parser, configure_logging  # noqa: E402
from hivalidate.config import Config  # noqa: E402
from hivalidate.cutouts.base import (  # noqa: E402
    CutoutCache,
    CutoutUnavailable,
    fetch_with_fallback,
)
from hivalidate.cutouts.registry import build_continuum_chain, build_optical_chain  # noqa: E402

logger = logging.getLogger(__name__)


def _git_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def _preflight_or_abort(config: Config) -> None:
    """Warn (don't abort) if some backends in a chain are down but others in the same
    chain still work -- that's exactly what the fallback chain is for. Abort only if
    an entire configured chain is unusable, since every source would fail that image
    type and it's better to find out in seconds than after a long batch run.
    """
    for kind, chain in [
        ("optical", build_optical_chain(config)),
        ("continuum", build_continuum_chain(config)),
    ]:
        if not chain:
            continue
        statuses = [(backend, *backend.is_available()) for backend in chain]
        for backend, ok, message in statuses:
            if not ok:
                logger.warning(
                    "[preflight] %s backend '%s' unavailable: %s", kind, backend.name, message
                )
        if not any(ok for _, ok, _ in statuses):
            raise SystemExit(
                f"Every configured {kind} backend is unavailable -- see warnings above. "
                f"Run hivalidate-check-connectivity for details."
            )


def run(config: Config) -> dict:
    """Returns the manifest dict that was also written to disk (useful for tests)."""
    _preflight_or_abort(config)

    if not config.paths.deduped_catalogue.exists():
        raise SystemExit(
            f"{config.paths.deduped_catalogue} does not exist -- run hivalidate-dedup first"
        )
    if not config.paths.renamed_cubelets_dir.is_dir():
        raise SystemExit(
            f"{config.paths.renamed_cubelets_dir} does not exist -- run hivalidate-rename first"
        )

    deduped = catalogue.read_votable(config.paths.deduped_catalogue)
    optical_chain = build_optical_chain(config)
    continuum_chain = build_continuum_chain(config)
    cache = CutoutCache(config.cutouts.cache_dir) if config.cutouts.cache_dir else None

    config.paths.dry_run_dir.mkdir(parents=True, exist_ok=True)

    sources: list[dict] = []
    for row in deduped:
        source_name = str(row["name"]).replace(" ", "_")
        entry: dict = {"name": str(row["name"]), "ra": float(row["ra"]), "dec": float(row["dec"])}
        try:
            source_result = _process_one_source(
                row, source_name, config, optical_chain, continuum_chain, cache
            )
            entry.update(source_result)
            entry["status"] = "ok"
            logger.info("%s: OK", source_name)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: one bad source must never abort the batch
            entry["status"] = "failed"
            entry["error"] = str(exc)
            logger.error("%s: FAILED: %s", source_name, exc)
        sources.append(entry)

    manifest = {
        "run_info": {
            "hivalidate_version": __version__,
            "hivalidate_git_commit": _git_commit_hash(),
            "config_field_name": config.field_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "sources": sources,
    }
    manifest_path = config.paths.dry_run_dir / "manifest.json"
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)

    n_ok = sum(1 for s in sources if s["status"] == "ok")
    logger.info(
        "Dry-run complete: %d/%d sources OK. Manifest: %s", n_ok, len(sources), manifest_path
    )
    return manifest


def _process_one_source(row, source_name, config, optical_chain, continuum_chain, cache) -> dict:
    position = SkyCoord(ra=row["ra"], dec=row["dec"], unit="deg")
    # Matches the legacy script's convention: field of view scales with the source's
    # own moment-0 footprint, not a fixed angular size for every source.
    cubelets = plotting.load_source_cubelets(config.paths.renamed_cubelets_dir, source_name)
    size_arcsec = max(cubelets.mom0.shape) * 5 * 1.7

    optical = _fetch_or_none(position, size_arcsec, source_name, optical_chain, cache)
    continuum = _fetch_or_none(position, size_arcsec, source_name, continuum_chain, cache)

    fig = plotting.build_validation_figure(row, cubelets, optical=optical, continuum=continuum)
    png_path = config.paths.dry_run_dir / f"{source_name}.png"
    fig.savefig(png_path, bbox_inches="tight", dpi=100)
    plt.close(fig)

    return {
        "png_path": str(png_path),
        "optical_provenance": optical.provenance if optical is not None else None,
        "continuum_provenance": continuum.provenance if continuum is not None else None,
    }


def _fetch_or_none(position, size_arcsec, source_name, chain, cache):
    if not chain:
        return None
    try:
        return fetch_with_fallback(position, size_arcsec, source_name, chain, cache=cache)
    except CutoutUnavailable as exc:
        logger.warning("%s: no cutout available from any backend: %s", source_name, exc)
        return None


def main(argv: list[str] | None = None) -> None:
    parser = base_parser(__doc__ or "")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    config = Config.from_yaml(args.config)
    run(config)


if __name__ == "__main__":
    sys.exit(main())
