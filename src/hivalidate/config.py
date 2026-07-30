"""Per-field/SB configuration.

Every hivalidate CLI stage takes ``--config path/to/field.yaml`` instead of reading
hardcoded paths -- this is the fix for the fragility documented in PLAN.md section 3
(issue #2, #9), where the legacy scripts each hardcoded a different field/SB's paths
as module-level constants.

Functions in the rest of the package take plain arguments (paths, numbers, arrays),
not a `Config` object -- only the CLI layer (`hivalidate.cli.*`) reads a `Config` and
threads its fields through as individual arguments. This keeps the science/IO modules
independently unit-testable without needing a YAML file on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class DedupSettings:
    """Positional/velocity cross-match tolerance for deduplicating sources that were
    independently detected in more than one per-run SoFiA catalogue (adjacent
    sub-cube runs can both catch a source near their shared boundary -- see PLAN.md
    issue #5). Velocity tolerance follows the same functional form already used for
    GAMA cross-matching in the legacy script: ``vel_tol = wm50_factor * wm50 + base_km_s``.
    """

    sep_arcsec: float = 30.0
    vel_tol_base_km_s: float = 30.0
    vel_tol_wm50_factor: float = 0.6


@dataclass
class CosmologySettings:
    """Not tied to a specific paper -- H0=70, flat LCDM, Om0=0.3 is the legacy
    script's round-number default. Override per-field if a project standardises on a
    different cosmology.
    """

    h0: float = 70.0
    om0: float = 0.3
    tcmb0: float = 2.725


@dataclass
class CutoutSettings:
    """Phase 2 settings: fallback-chain order and where things get cached. Backend
    names are resolved against `hivalidate.cutouts` registries, not imported here, so
    this module has no dependency on astroquery/MontagePy.
    """

    optical_priority: list[str] = field(default_factory=lambda: ["skyview", "legacy_survey"])
    continuum_priority: list[str] = field(default_factory=lambda: ["local", "racs_casda"])
    cutout_size_pix: int = 256
    cache_dir: Path | None = None
    casda_username_env: str = "CASDA_USERNAME"
    casda_password_env: str = "CASDA_PASSWORD"


@dataclass
class Paths:
    raw_sofia_dir: Path
    work_dir: Path
    continuum_local_dir: Path | None = None
    gama_catalogue: Path | None = None
    #: Full-field moment-0 mosaic (SoFiA's own output, e.g. `run_sofia/mom0.fits`),
    #: used only by Phase 5 postprocess to place true-flagged detections in context.
    #: Optional -- the mosaic step is skipped (not an error) if unset.
    field_mosaic: Path | None = None

    @property
    def combined_catalogue(self) -> Path:
        return self.work_dir / "combined_cat.xml"

    @property
    def deduped_catalogue(self) -> Path:
        return self.work_dir / "deduped_cat.xml"

    @property
    def renamed_cubelets_dir(self) -> Path:
        return self.work_dir / "cubelets"

    @property
    def dry_run_dir(self) -> Path:
        return self.work_dir / "dry_run"

    @property
    def qa_dir(self) -> Path:
        return self.work_dir / "qa"

    @property
    def postprocess_dir(self) -> Path:
        return self.work_dir / "postprocess"


@dataclass
class Config:
    field_name: str
    paths: Paths
    dedup: DedupSettings = field(default_factory=DedupSettings)
    cosmology: CosmologySettings = field(default_factory=CosmologySettings)
    cutouts: CutoutSettings = field(default_factory=CutoutSettings)

    @classmethod
    def from_yaml(cls, config_path: str | Path) -> "Config":
        config_path = Path(config_path)
        with open(config_path) as fh:
            raw = yaml.safe_load(fh)
        return cls.from_dict(raw, base_dir=config_path.parent)

    @classmethod
    def from_dict(cls, raw: dict, base_dir: Path | None = None) -> "Config":
        base_dir = base_dir or Path(".")

        def resolve(p: str | None) -> Path | None:
            if p is None:
                return None
            p = Path(p)
            return p if p.is_absolute() else (base_dir / p).resolve()

        try:
            field_name = raw["field_name"]
            raw_paths = raw["paths"]
        except KeyError as exc:
            raise ValueError(f"Config is missing required top-level key: {exc}") from exc

        try:
            paths = Paths(
                raw_sofia_dir=resolve(raw_paths["raw_sofia_dir"]),
                work_dir=resolve(raw_paths["work_dir"]),
                continuum_local_dir=resolve(raw_paths.get("continuum_local_dir")),
                gama_catalogue=resolve(raw_paths.get("gama_catalogue")),
                field_mosaic=resolve(raw_paths.get("field_mosaic")),
            )
        except KeyError as exc:
            raise ValueError(f"Config 'paths' section is missing required key: {exc}") from exc

        dedup = DedupSettings(**raw.get("dedup", {}))
        cosmology = CosmologySettings(**raw.get("cosmology", {}))

        cutouts_raw = dict(raw.get("cutouts", {}))
        if "cache_dir" in cutouts_raw:
            cutouts_raw["cache_dir"] = resolve(cutouts_raw["cache_dir"])
        cutouts = CutoutSettings(**cutouts_raw)

        config = cls(
            field_name=field_name, paths=paths, dedup=dedup, cosmology=cosmology, cutouts=cutouts
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Fail loudly and early on obviously-broken config, rather than partway
        through a batch job. Does not check network-dependent things (CASDA
        credentials, survey reachability) -- that's the preflight check's job
        (Phase 2), which needs to run at pipeline-start time, not config-load time.
        """
        if not self.paths.raw_sofia_dir.is_dir():
            raise ValueError(f"paths.raw_sofia_dir does not exist or is not a directory: "
                              f"{self.paths.raw_sofia_dir}")
        continuum_dir = self.paths.continuum_local_dir
        if continuum_dir is not None and not continuum_dir.is_dir():
            raise ValueError(
                f"paths.continuum_local_dir does not exist or is not a directory: {continuum_dir}"
            )
        if self.paths.gama_catalogue is not None and not self.paths.gama_catalogue.is_file():
            raise ValueError(f"paths.gama_catalogue does not exist: {self.paths.gama_catalogue}")
        if self.paths.field_mosaic is not None and not self.paths.field_mosaic.is_file():
            raise ValueError(f"paths.field_mosaic does not exist: {self.paths.field_mosaic}")
