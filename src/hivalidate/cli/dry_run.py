"""Batch-generate validation plots for every source in the deduped catalogue.

The HPC-safe stage (PLAN.md Phase 3): forces the `Agg` backend, never calls
`plt.show()` or blocks on input, and isolates each source in its own try/except so
one bad cutout/plot doesn't abort a run that might cover hundreds of sources
(PLAN.md issue #8). Writes a manifest (`manifest.json`) that `hivalidate-qa` (Phase 4)
consumes -- QA never re-fetches cutouts or regenerates figures, it only ever looks at
what this command already produced.

Resumable: `manifest.json` is (re)written after every source, not just once at the
end, and a re-run skips any source already recorded as "ok" with a PNG still on disk
-- so interrupting a long batch (Ctrl-C, a killed HPC job) and re-running the same
command picks up roughly where it left off instead of reprocessing (and re-fetching
cutouts for) everything from scratch. A source previously recorded as "failed" is
always retried, since whatever caused the failure might not reproduce (e.g. a
transient network error).

Run `hivalidate-combine`, `hivalidate-dedup`, and `hivalidate-rename` first.
"""

from __future__ import annotations

import json
import logging
import sys
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
from hivalidate.provenance import git_commit_hash, now_iso  # noqa: E402

logger = logging.getLogger(__name__)


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


def _load_resumable_sources(manifest_path: Path, config: Config) -> dict[str, dict]:
    """Returns `{name: entry}` for sources a previous (possibly interrupted) run of
    this same field already finished -- these are skipped by `run()` rather than
    reprocessed. Only "ok" entries whose PNG still exists on disk count as done; see
    this module's docstring for why "failed" entries are excluded (always retried).
    """
    if not manifest_path.exists():
        return {}

    with open(manifest_path) as fh:
        try:
            previous = json.load(fh)
        except json.JSONDecodeError:
            # A hard kill (not a clean Ctrl-C, which always finishes its own write)
            # can truncate manifest.json mid-write -- start this batch from scratch
            # rather than crash on a corrupt resume file.
            logger.warning(
                "%s is not valid JSON -- treating this as a fresh batch, not a resume",
                manifest_path,
            )
            return {}

    previous_field = previous.get("run_info", {}).get("config_field_name")
    if previous_field != config.field_name:
        logger.warning(
            "%s belongs to a different field (%r, expected %r) -- treating this as a "
            "fresh batch, not a resume",
            manifest_path,
            previous_field,
            config.field_name,
        )
        return {}

    return {
        entry["name"]: entry
        for entry in previous.get("sources", [])
        if entry.get("status") == "ok" and Path(entry.get("png_path", "")).exists()
    }


def _write_manifest(
    manifest_path: Path, sources: list[dict], git_commit: str, config: Config
) -> dict:
    manifest = {
        "run_info": {
            "hivalidate_version": __version__,
            "hivalidate_git_commit": git_commit,
            "config_field_name": config.field_name,
            "generated_at": now_iso(),
        },
        "sources": sources,
    }
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


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

    # Captured now, before the (potentially long-running) batch loop, not after --
    # otherwise a code change committed while this process is still running would
    # get attributed to output it didn't actually produce (found live 2026-07-30: a
    # bug fix was committed mid-batch, and the finished manifest's git commit
    # initially pointed at that fix even though most of the batch had already
    # rendered with the previous commit's code, still loaded in this process).
    git_commit = git_commit_hash()

    deduped = catalogue.read_votable(config.paths.deduped_catalogue)
    optical_chain = build_optical_chain(config)
    continuum_chain = build_continuum_chain(config)
    cache = CutoutCache(config.cutouts.cache_dir) if config.cutouts.cache_dir else None

    config.paths.dry_run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = config.paths.dry_run_dir / "manifest.json"

    already_done = _load_resumable_sources(manifest_path, config)
    if already_done:
        logger.info(
            "Resuming: %d/%d sources already completed in a previous run of this batch",
            len(already_done),
            len(deduped),
        )

    sources: list[dict] = []
    interrupted = False
    try:
        for row in deduped:
            name = str(row["name"])
            source_name = name.replace(" ", "_")

            existing = already_done.get(name)
            if existing is not None:
                sources.append(existing)
                logger.debug("%s: already done, skipping", source_name)
                continue

            entry: dict = {"name": name, "ra": float(row["ra"]), "dec": float(row["dec"])}
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
            # Written after every source, not just once at the end -- this is what
            # makes a re-run after Ctrl-C actually resume instead of starting over
            # (previously manifest.json was only written once the whole loop had
            # finished, so an interrupt anywhere in the batch lost all progress made
            # so far, not just the source that was in flight).
            _write_manifest(manifest_path, sources, git_commit, config)
    except KeyboardInterrupt:
        interrupted = True
        logger.warning(
            "Interrupted after %d/%d sources -- progress saved to %s. Re-run the same "
            "command to continue from here.",
            len(sources),
            len(deduped),
            manifest_path,
        )

    manifest = _write_manifest(manifest_path, sources, git_commit, config)

    n_ok = sum(1 for s in sources if s["status"] == "ok")
    if interrupted:
        logger.info("Dry-run interrupted: %d/%d sources completed so far.", n_ok, len(deduped))
    else:
        logger.info(
            "Dry-run complete: %d/%d sources OK. Manifest: %s", n_ok, len(sources), manifest_path
        )
    return manifest


def _process_one_source(row, source_name, config, optical_chain, continuum_chain, cache) -> dict:
    position = SkyCoord(ra=row["ra"], dec=row["dec"], unit="deg")
    cubelets = plotting.load_source_cubelets(config.paths.renamed_cubelets_dir, source_name)
    # The same reference field of view build_validation_figure pins every sky panel
    # to -- computed from mom0's own real WCS pixel scale, not an assumed constant
    # (see plotting.reference_field_of_view_arcsec's docstring for why that matters).
    size_arcsec = plotting.reference_field_of_view_arcsec(cubelets)

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
