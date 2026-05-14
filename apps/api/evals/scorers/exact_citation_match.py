"""Deterministic scorer: every cited source id appears in the retrieval context.

Reads two arrays from ``fixture.input``:

* ``retrieval_context_ids``: source identifiers returned by retrieval and given
  to the model.
* ``cited_source_ids``: source identifiers actually cited in the model output.

Passes iff ``cited_source_ids`` is a subset of ``retrieval_context_ids``. Any
citation not present in retrieval is an "orphan" and the scorer surfaces all
orphans in ``details["orphans"]`` so reviewers can see exactly what hallucinated.

Optional verification (when ``expected.verification_claims`` is a non-empty list):

* ``expected.verification_claims`` and ``input.verification_claims`` are lists of
  objects shaped like ``ClaimVerificationEntry`` (``claim_text``, ``support``).
* Claims are compared in order by index; lengths must match. Each pair must
  have identical ``claim_text`` and ``support`` (values aligned with
  ``country_conditions.schemas.ClaimSupport``).
* ``score`` is ``citation_score * verification_score`` where ``verification_score``
  is the fraction of claims that match. ``passed`` requires no orphans and a
  verification score of 1.0.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError

from country_conditions.schemas import ClaimVerificationEntry
from evals.fixtures import Fixture, ScoreResult
from evals.scorers.base import ScorerContext, register

_MAX_ID_LEN = 256
_MAX_IDS = 1024
_MAX_VERIFICATION_CLAIMS = 256

_claim_list_adapter = TypeAdapter(list[ClaimVerificationEntry])


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


def _parse_claim_list(value: Any, field: str) -> list[ClaimVerificationEntry] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise TypeError(f"{field} must be a list or null")
    if len(value) > _MAX_VERIFICATION_CLAIMS:
        lim = _MAX_VERIFICATION_CLAIMS
        raise ValueError(f"{field} exceeds maximum length of {lim}")
    if not value:
        return []
    try:
        return _claim_list_adapter.validate_python(value)
    except ValidationError as exc:
        raise ValueError(f"{field} invalid claim entries: {exc}") from exc


def _verification_score(
    expected: list[ClaimVerificationEntry],
    actual: list[ClaimVerificationEntry],
) -> tuple[float, bool, list[dict[str, Any]]]:
    mismatches: list[dict[str, Any]] = []
    if len(expected) != len(actual):
        mismatches.append(
            {
                "index": None,
                "reason": "length_mismatch",
                "expected_len": len(expected),
                "actual_len": len(actual),
            },
        )
        return 0.0, False, mismatches
    matches = 0
    for i, (exp_row, act_row) in enumerate(zip(expected, actual, strict=True)):
        text_ok = exp_row.claim_text == act_row.claim_text
        sup_ok = exp_row.support == act_row.support
        ok = text_ok and sup_ok
        if ok:
            matches += 1
        else:
            mismatches.append(
                {
                    "index": i,
                    "expected_claim_text": exp_row.claim_text,
                    "actual_claim_text": act_row.claim_text,
                    "expected_support": exp_row.support,
                    "actual_support": act_row.support,
                },
            )
    n = len(expected)
    score = 1.0 if n == 0 else matches / n
    return score, len(mismatches) == 0, mismatches


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
        citation_passed = not orphans
        citation_score = 1.0 if not cited else (len(cited) - len(orphans)) / len(cited)

        expected_raw = fixture.expected.get("verification_claims")
        try:
            expected_claims = _parse_claim_list(
                expected_raw,
                "expected.verification_claims",
            )
        except (TypeError, ValueError) as exc:
            return ScoreResult(
                error=str(exc),
                details={
                    "citation_score": citation_score,
                    "context_count": len(context_set),
                    "cited_count": len(cited),
                    "orphans": orphans,
                },
            )

        if expected_claims is None or not expected_claims:
            return ScoreResult(
                score=citation_score,
                passed=citation_passed,
                details={
                    "citation_score": citation_score,
                    "context_count": len(context_set),
                    "cited_count": len(cited),
                    "orphans": orphans,
                },
            )

        try:
            actual_raw = fixture.input.get("verification_claims")
            if actual_raw is None:
                raise TypeError(
                    "input.verification_claims is required when "
                    "expected.verification_claims is set",
                )
            actual_claims = _parse_claim_list(
                actual_raw,
                "input.verification_claims",
            )
        except (TypeError, ValueError) as exc:
            return ScoreResult(
                error=str(exc),
                details={
                    "citation_score": citation_score,
                    "context_count": len(context_set),
                    "cited_count": len(cited),
                    "orphans": orphans,
                },
            )

        assert actual_claims is not None  # for mypy; None only when actual_raw is None
        ver_score, ver_passed, mismatches = _verification_score(
            expected_claims,
            actual_claims,
        )
        combined_score = citation_score * ver_score
        combined_passed = citation_passed and ver_passed

        return ScoreResult(
            score=combined_score,
            passed=combined_passed,
            details={
                "citation_score": citation_score,
                "verification_score": ver_score,
                "context_count": len(context_set),
                "cited_count": len(cited),
                "orphans": orphans,
                "verification_mismatches": mismatches,
            },
        )


register(ExactCitationMatchScorer())
