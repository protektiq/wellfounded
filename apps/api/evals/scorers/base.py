"""Scorer protocol, dispatch context, and global registry.

Scorers self-register on module import; the runner imports ``evals.scorers``
once to populate ``SCORER_REGISTRY`` and then dispatches by fixture's ``scorer``
field. ``requires_llm`` tells the runner whether to open a DB session and
instantiate ``LLMClient`` for the run. ``ScorerContext`` carries dependencies
that scorers cannot construct themselves (LLM client, rubrics root path) so the
``Scorer`` protocol stays uniform across deterministic and LLM-backed scorers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from evals.fixtures import Fixture, ScoreResult
from llm.client import LLMClient


@dataclass(frozen=True)
class ScorerContext:
    """Per-run dependencies handed to every scorer call."""

    llm: LLMClient | None = None
    rubrics_root: Path | None = None


@runtime_checkable
class Scorer(Protocol):
    """Async scorer contract. Instances live in ``SCORER_REGISTRY``."""

    name: str
    requires_llm: bool

    async def score(
        self,
        fixture: Fixture,
        *,
        ctx: ScorerContext,
    ) -> ScoreResult: ...


SCORER_REGISTRY: dict[str, Scorer] = {}


def register(scorer: Scorer) -> Scorer:
    """Add ``scorer`` to the registry; refuse duplicate names."""
    name = scorer.name
    if not isinstance(name, str) or not name:
        raise ValueError("scorer.name must be a non-empty string")
    if name in SCORER_REGISTRY:
        raise ValueError(f"scorer already registered: {name!r}")
    SCORER_REGISTRY[name] = scorer
    return scorer
