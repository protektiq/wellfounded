"""Filesystem path resolution for eval fixtures, rubrics, and results.

The harness code lives under ``apps/api/evals/`` but the human-curated data
lives at repo root under ``evals/``. This module finds the repo root by walking
up from this file to the first ancestor containing a ``.git`` directory, with
explicit overrides supported for tests.
"""

from __future__ import annotations

from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
_MAX_ANCESTOR_DEPTH = 8


def repo_root() -> Path:
    """Return the path to the repository root.

    Walks up from this file looking for ``.git``. Bounded to avoid pathological
    filesystems. Raises ``RuntimeError`` if no marker is found.
    """
    current = _THIS_FILE.parent
    for _ in range(_MAX_ANCESTOR_DEPTH):
        if (current / ".git").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise RuntimeError(
        "could not locate repository root (no .git directory in ancestors)",
    )


def default_fixtures_root() -> Path:
    return repo_root() / "evals" / "fixtures"


def default_results_root() -> Path:
    return repo_root() / "evals" / "results"


def default_rubrics_root() -> Path:
    return repo_root() / "evals" / "rubrics"
