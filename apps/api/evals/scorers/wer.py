"""Word Error Rate scorer for transcription fixtures.

Implements word-level Levenshtein distance in the standard library so we avoid
adding ``jiwer`` (or similar) as a dependency for a single arithmetic routine.
The score returned is ``1 - WER`` (clamped to ``[0, 1]``) so that higher is
better, matching every other scorer's orientation.

Reads two strings from ``fixture.input``:

* ``reference``: ground-truth transcription provided by the practitioner.
* ``hypothesis``: text emitted by the transcription pipeline under test.
"""

from __future__ import annotations

import re
from typing import Any

from evals.fixtures import Fixture, ScoreResult
from evals.scorers.base import ScorerContext, register

_MAX_TEXT_CHARS = 100_000
_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


def _validate_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if len(value) > _MAX_TEXT_CHARS:
        raise ValueError(f"{field} exceeds {_MAX_TEXT_CHARS} characters")
    return value


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def _levenshtein(ref: list[str], hyp: list[str]) -> int:
    """Standard two-row dynamic-programming word-level edit distance."""
    r, h = len(ref), len(hyp)
    if r == 0:
        return h
    if h == 0:
        return r
    prev = list(range(h + 1))
    curr = [0] * (h + 1)
    for i in range(1, r + 1):
        curr[0] = i
        for j in range(1, h + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + cost,
            )
        prev, curr = curr, prev
    return prev[h]


def compute_wer(reference: str, hypothesis: str) -> float:
    """Public for tests: word-level WER, ``inf``-safe on empty references."""
    ref_tokens = _tokenize(reference)
    hyp_tokens = _tokenize(hypothesis)
    if not ref_tokens:
        return 0.0 if not hyp_tokens else 1.0
    distance = _levenshtein(ref_tokens, hyp_tokens)
    return distance / len(ref_tokens)


class WerScorer:
    name: str = "wer"
    requires_llm: bool = False

    async def score(
        self,
        fixture: Fixture,
        *,
        ctx: ScorerContext,
    ) -> ScoreResult:
        del ctx  # deterministic scorer; no runtime context needed
        try:
            reference = _validate_text(
                fixture.input.get("reference"),
                "input.reference",
            )
            hypothesis = _validate_text(
                fixture.input.get("hypothesis"),
                "input.hypothesis",
            )
        except (TypeError, ValueError) as exc:
            return ScoreResult(error=str(exc))

        wer = compute_wer(reference, hypothesis)
        wer_clamped = max(0.0, min(1.0, wer))
        score = 1.0 - wer_clamped

        threshold = fixture.expected.get("max_wer")
        passed: bool | None = None
        if isinstance(threshold, int | float):
            passed = wer_clamped <= float(threshold)

        return ScoreResult(
            score=score,
            passed=passed,
            details={
                "wer": wer_clamped,
                "reference_word_count": len(_tokenize(reference)),
                "hypothesis_word_count": len(_tokenize(hypothesis)),
            },
        )


register(WerScorer())
