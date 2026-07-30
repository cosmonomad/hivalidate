"""Builds the configured optical/continuum fallback chains from a `Config`.

Kept separate from `base.py` (no config dependency there, so it stays independently
testable) and from the individual backend modules (so adding a backend only means
registering it here, not touching every caller). Used by both
`hivalidate-check-connectivity` and `hivalidate-dry-run` -- they must build the exact
same chains, or a connectivity check that passed wouldn't mean anything for the batch
run that follows it.
"""

from __future__ import annotations

from hivalidate.config import Config
from hivalidate.cutouts.base import CutoutBackend
from hivalidate.cutouts.continuum import LocalContinuumBackend, RacsCasdaBackend
from hivalidate.cutouts.optical import LegacySurveyBackend, SkyViewBackend

_OPTICAL_BACKENDS = {
    "skyview": lambda config: SkyViewBackend(),
    "legacy_survey": lambda config: LegacySurveyBackend(),
}

_CONTINUUM_BACKENDS = {
    "local": lambda config: LocalContinuumBackend(config.paths.continuum_local_dir),
    "racs_casda": lambda config: RacsCasdaBackend(
        username_env=config.cutouts.casda_username_env,
        password_env=config.cutouts.casda_password_env,
    ),
}


def build_optical_chain(config: Config) -> list[CutoutBackend]:
    return [_OPTICAL_BACKENDS[name](config) for name in config.cutouts.optical_priority]


def build_continuum_chain(config: Config) -> list[CutoutBackend]:
    chain = []
    for name in config.cutouts.continuum_priority:
        if name == "local" and config.paths.continuum_local_dir is None:
            continue  # no local continuum configured for this field -- skip, don't error
        chain.append(_CONTINUUM_BACKENDS[name](config))
    return chain
