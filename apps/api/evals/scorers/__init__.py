"""Scorer submodules self-register at import time.

Importing this package populates ``SCORER_REGISTRY``. Adding a new scorer is
exactly: drop a new file alongside the existing ones, expose a class with a
``name``, ``requires_llm`` attribute, and an async ``score`` method, then add
its import below.
"""

from __future__ import annotations

from evals.scorers import (  # noqa: F401 - registration side effects
    country_conditions_draft,
    exact_citation_match,
    rubric_llm_judge,
    wer,
)
from evals.scorers.base import SCORER_REGISTRY, Scorer, ScorerContext, register

__all__ = [
    "SCORER_REGISTRY",
    "Scorer",
    "ScorerContext",
    "register",
]
