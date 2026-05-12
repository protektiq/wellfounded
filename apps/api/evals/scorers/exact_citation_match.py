"""Deterministic scorer: every cited source id appears in the retrieval context.

Reads two arrays from ``fixture.input``:

* ``retrieval_context_ids``: source identifiers returned by retrieval and given
  to the model.
* ``cited_source_ids``: source identifiers actually cited in the model output.

Passes iff ``cited_source_ids`` is a subset of ``retrieval_context_ids``. Any
citation not present in retrieval is an "orphan" and the scorer surfaces all
orphans in ``details["orphans"]`` so reviewers can see exactly what hallucinated.
"""

from __future__ import annotations

from typing import Any

from evals.fixtures import Fixture, ScoreResult
from evals.scorers.base import ScorerContext, register

_MAX_ID_LEN = 256
_MAX_IDS = 1024


def _coerce_ids(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"{field} must be a list of strings")
    if len(value) > _MAX_IDS:
        raise ValueError(f"{field} exceeds maximum length of {_MAX_IDS}")
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"{field}[{i}] must be a string")
        if not 1 <= len(item) <= _MAX_ID_LEN:
            raise ValueError(f"{field}[{i}] length out of range (1..{_MAX_ID_LEN})")
        out.append(item)
    return out


class ExactCitationMatchScorer:
    name: str = "exact_citation_match"
    requires_llm: bool = False

    async def score(
        self,
        fixture: Fixture,
        *,
        ctx: ScorerContext,
    ) -> ScoreResult:
        del ctx  # deterministic scorer; no runtime context needed
        try:
            context = _coerce_ids(
                fixture.input.get("retrieval_context_ids"),
                "input.retrieval_context_ids",
            )
            cited = _coerce_ids(
                fixture.input.get("cited_source_ids"),
                "input.cited_source_ids",
            )
        except (TypeError, ValueError) as exc:
            return ScoreResult(error=str(exc))

        context_set = set(context)
        orphans = sorted({c for c in cited if c not in context_set})
        passed = not orphans
        # Score is the share of citations that resolved to a retrieved source.
        score = 1.0 if not cited else (len(cited) - len(orphans)) / len(cited)
        return ScoreResult(
            score=score,
            passed=passed,
            details={
                "context_count": len(context_set),
                "cited_count": len(cited),
                "orphans": orphans,
            },
        )


register(ExactCitationMatchScorer())
