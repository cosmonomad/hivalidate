"""Shared reproducibility-metadata helpers, used by both the dry-run manifest and
the QA output catalogue (PLAN.md section 5, "Reproducibility metadata").
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git_commit_hash() -> str:
    """Best-effort: "unknown" if this isn't a git checkout (e.g. installed from a
    wheel on HPC) or git isn't on PATH, rather than failing the whole run over a
    provenance nicety.
    """
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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
