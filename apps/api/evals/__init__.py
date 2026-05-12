"""Eval harness: discoverable JSON fixtures, pluggable scorers, versioned results.

Harness code lives here, in ``apps/api/evals/``. Fixture inputs, rubrics, and
result manifests live at repo root under ``evals/`` so practitioners can review
them outside the API package. See ``DATA_FLOW.md`` for the full diagram.
"""

from __future__ import annotations

from evals.fixtures import (
    CATEGORIES,
    Category,
    Fixture,
    FixtureRun,
    RunManifest,
    ScoreResult,
)
from evals.scorers.base import SCORER_REGISTRY, Scorer, register

__all__ = [
    "CATEGORIES",
    "Category",
    "Fixture",
    "FixtureRun",
    "RunManifest",
    "SCORER_REGISTRY",
    "ScoreResult",
    "Scorer",
    "register",
]
