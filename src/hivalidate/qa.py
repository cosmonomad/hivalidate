"""Interactive QA review, decoupled from dry-run (PLAN.md Phase 4): reads only the
manifest and PNGs `hivalidate-dry-run` already produced -- never re-fetches a cutout
or regenerates a figure. This is what lets QA run on a normal machine with a display
(a laptop) while dry-run ran unattended on an HPC compute node with neither.

The review loop, catalogue merge, and flag numbering all live in this module (not the
CLI) so they're directly unit-testable; `display_fn`/`prompt_fn`/`close_fn` are
injected so tests never need a real display or real keyboard input --
`hivalidate.cli.qa` supplies the real (matplotlib window + terminal `input()`)
versions for actual use.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from hivalidate import __version__, catalogue
from hivalidate.config import Config
from hivalidate.provenance import git_commit_hash, now_iso

logger = logging.getLogger(__name__)

#: Matches the legacy script's qa convention (0: false, 1: true, 2: uncertain,
#: 3: duplicate) for continuity, though "duplicate" here means a human caught one
#: `deduplicate_positional` missed, not the same thing the legacy script meant by it.
FLAG_TO_NUMERIC = {"t": 1.0, "f": 0.0, "u": 2.0, "d": 3.0}
VALID_FLAGS = set(FLAG_TO_NUMERIC) | {"b", "q"}


def load_manifest(dry_run_dir: str | Path) -> dict:
    manifest_path = Path(dry_run_dir) / "manifest.json"
    with open(manifest_path) as fh:
        return json.load(fh)


def load_qa_results(qa_dir: str | Path) -> dict:
    results_path = Path(qa_dir) / "qa_results.json"
    if not results_path.exists():
        return {}
    with open(results_path) as fh:
        return json.load(fh)


def save_qa_results(qa_dir: str | Path, results: dict) -> None:
    qa_dir = Path(qa_dir)
    qa_dir.mkdir(parents=True, exist_ok=True)
    with open(qa_dir / "qa_results.json", "w") as fh:
        json.dump(results, fh, indent=2)


def run_qa_session(config: Config, prompt_fn, display_fn, close_fn) -> dict:
    """Runs the review loop and returns the final `qa_results` dict (also persisted
    incrementally to disk after every review, and re-exported to
    `validated_cat.xml` at the end -- see `merge_qa_into_catalogue`).

    `prompt_fn(source: dict, position: int, total: int) -> (flag: str, comment: str)`
    `display_fn(png_path: Path) -> handle` (opaque, passed straight to `close_fn`)
    `close_fn(handle) -> None`
    """
    manifest = load_manifest(config.paths.dry_run_dir)
    ok_sources = [s for s in manifest["sources"] if s["status"] == "ok"]
    results = load_qa_results(config.paths.qa_dir)
    already_done_at_start = set(results.keys())

    position = 0
    while position < len(ok_sources):
        source = ok_sources[position]
        name = source["name"]

        if name in already_done_at_start:
            position += 1
            continue

        handle = display_fn(Path(source["png_path"]))
        flag, comment = prompt_fn(source, position, len(ok_sources))
        close_fn(handle)

        if flag == "q":
            logger.info("Stopping session at %d/%d reviewed", len(results), len(ok_sources))
            break
        if flag == "b":
            if position > 0:
                position -= 1
                prev_name = ok_sources[position]["name"]
                results.pop(prev_name, None)
                already_done_at_start.discard(prev_name)
                save_qa_results(config.paths.qa_dir, results)
            continue

        results[name] = {
            "qa_flag": flag,
            "qa_numeric": FLAG_TO_NUMERIC[flag],
            "comment": comment,
            "reviewed_at": now_iso(),
        }
        save_qa_results(config.paths.qa_dir, results)
        position += 1

    merge_qa_into_catalogue(config, manifest, results)
    return results


def merge_qa_into_catalogue(config: Config, manifest: dict, results: dict):
    """Writes `validated_cat.xml` and `validated_cat.csv` (identical content, VOTable
    and plain CSV -- the CSV is for anyone/anything downstream that would rather not
    deal with VOTable XML): the deduped catalogue plus `qa`/`qa_comment` (NaN/empty
    for anything not yet reviewed -- safe to run after a partial session) and the
    optical/continuum provenance and dry-run status from the manifest, so the final
    catalogue records not just the verdict but what was actually looked at to reach
    it. Also writes `run_info.json` alongside it (PLAN.md section 5, "Reproducibility
    metadata").
    """
    deduped = catalogue.read_votable(config.paths.deduped_catalogue)
    manifest_by_name = {s["name"]: s for s in manifest["sources"]}

    qa, qa_comment, optical_provenance, continuum_provenance, dry_run_status = [], [], [], [], []
    for name in deduped["name"]:
        name = str(name)
        m = manifest_by_name.get(name, {})
        r = results.get(name)
        qa.append(r["qa_numeric"] if r else np.nan)
        qa_comment.append(r["comment"] if r else "")
        optical_provenance.append(m.get("optical_provenance") or "")
        continuum_provenance.append(m.get("continuum_provenance") or "")
        dry_run_status.append(m.get("status", "missing"))

    deduped["qa"] = qa
    deduped["qa_comment"] = qa_comment
    deduped["optical_provenance"] = optical_provenance
    deduped["continuum_provenance"] = continuum_provenance
    deduped["dry_run_status"] = dry_run_status

    config.paths.qa_dir.mkdir(parents=True, exist_ok=True)
    catalogue.write_votable(deduped, config.paths.qa_dir / "validated_cat.xml")
    catalogue.write_csv(deduped, config.paths.qa_dir / "validated_cat.csv")

    run_info = {
        "hivalidate_version": __version__,
        "hivalidate_git_commit": git_commit_hash(),
        "config_field_name": config.field_name,
        "generated_at": now_iso(),
        "n_reviewed": len(results),
        "n_total": len(deduped),
    }
    with open(config.paths.qa_dir / "run_info.json", "w") as fh:
        json.dump(run_info, fh, indent=2)

    logger.info(
        "Wrote %s and .csv (%d/%d reviewed)",
        config.paths.qa_dir / "validated_cat.xml",
        len(results),
        len(deduped),
    )
    return deduped


# --- real (non-injected) implementations, used by hivalidate.cli.qa -------------


def default_display(png_path: Path):
    """Opens the PNG in a real matplotlib window. Deliberately does not call
    `matplotlib.use(...)` -- unlike `hivalidate.cli.dry_run`, this is meant to run
    somewhere with an actual display, and forcing a backend here would fight
    whatever the environment already picked (or break dry-run if the two are ever
    imported in the same process, since a backend can't be switched after pyplot
    has already been used).
    """
    import matplotlib.pyplot as plt

    image = plt.imread(png_path)
    fig, ax = plt.subplots(figsize=(15, 9))
    ax.imshow(image)
    ax.axis("off")
    fig.suptitle(png_path.stem)
    plt.show(block=False)
    plt.pause(0.1)
    return fig


def default_close(handle) -> None:
    import matplotlib.pyplot as plt

    plt.close(handle)


def default_prompt(source: dict, position: int, total: int) -> tuple[str, str]:
    print(f"\n[{position + 1}/{total}] {source['name']}")
    while True:
        flag = input("  Flag (t=true, f=false, u=uncertain, d=duplicate, b=back, q=save & quit): ")
        flag = flag.strip().lower()
        if flag in VALID_FLAGS:
            break
        print(f"  Invalid input {flag!r} -- enter one of: {sorted(VALID_FLAGS)}")

    comment = ""
    if flag in FLAG_TO_NUMERIC:
        comment = input("  Comment (optional, Enter to skip): ").strip()
    return flag, comment
