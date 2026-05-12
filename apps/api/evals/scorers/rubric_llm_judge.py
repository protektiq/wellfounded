"""LLM-as-judge scorer driven by a fixed practitioner-authored rubric.

The fixture supplies the artifact under review in ``input.text`` (for example a
generated declaration excerpt) and points to a rubric markdown file via
``expected.rubric_path``. The rubric path is resolved relative to the run's
``rubrics_root`` and must not escape it. We send the rubric and the text to
``LLMClient.complete_structured`` with a strict ``RubricScore`` schema so the
judge returns a 1-5 integer plus per-criterion scores and reasoning, never free
text.

All LLM calls go through ``LLMClient``, which persists an ``LLMCallRecord`` and
respects the ``.cursorrules`` requirement that no model SDK is imported outside
``apps/api/llm/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evals.fixtures import Fixture, ScoreResult
from evals.scorers.base import ScorerContext, register
from llm.prompts import Prompt, with_variables

_MAX_RUBRIC_BYTES = 50_000
_MAX_TEXT_CHARS = 50_000
_MAX_REASONING_CHARS = 4_000
_DEFAULT_THRESHOLD = 4

_SYSTEM_PROMPT = (
    "You evaluate a piece of immigration-practice writing against a rubric "
    "supplied by a senior practitioner. Be exacting and conservative. Score on a "
    "1-5 integer scale per the rubric. Cite the specific criteria you applied. "
    "If a criterion cannot be assessed from the supplied text, mark it with a "
    "score of 0 in the criteria map and explain why. Do not flatter the text. "
    "Do not invent facts."
)

_USER_TEMPLATE = (
    "Rubric (markdown):\n"
    "---\n"
    "{rubric}\n"
    "---\n\n"
    "Text to evaluate:\n"
    "---\n"
    "{text}\n"
    "---\n\n"
    "Return a single structured judgement that conforms to the schema."
)


# Module-level Prompt constant per .cursorrules: no ad-hoc Prompt() in feature code.
RUBRIC_JUDGE_PROMPT = Prompt(
    id="evals.rubric_judge.v1",
    system=_SYSTEM_PROMPT,
    user_template=_USER_TEMPLATE,
    variables=(("rubric", ""), ("text", "")),
    default_max_tokens=2048,
    default_temperature=0.0,
)


class RubricScore(BaseModel):
    """Structured judgement returned by ``LLMClient.complete_structured``."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=5)
    reasoning: str = Field(min_length=1, max_length=_MAX_REASONING_CHARS)
    criteria: dict[str, int] = Field(default_factory=dict)


def _resolve_rubric_path(rubric_path: str, rubrics_root: Path) -> Path:
    if not isinstance(rubric_path, str) or not rubric_path:
        raise ValueError("expected.rubric_path must be a non-empty string")
    if len(rubric_path) > 256:
        raise ValueError("expected.rubric_path is too long")
    candidate = (rubrics_root / rubric_path).resolve()
    root_resolved = rubrics_root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("rubric_path escapes rubrics root") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"rubric file not found: {rubric_path}")
    return candidate


def _read_rubric(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > _MAX_RUBRIC_BYTES:
        raise ValueError(
            f"rubric file exceeds {_MAX_RUBRIC_BYTES} bytes: {path.name}",
        )
    return raw.decode("utf-8")


def _validate_text(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("input.text must be a string")
    if not value.strip():
        raise ValueError("input.text is empty")
    if len(value) > _MAX_TEXT_CHARS:
        raise ValueError(f"input.text exceeds {_MAX_TEXT_CHARS} characters")
    return value


class RubricLLMJudgeScorer:
    name: str = "rubric_llm_judge"
    requires_llm: bool = True

    async def score(
        self,
        fixture: Fixture,
        *,
        ctx: ScorerContext,
    ) -> ScoreResult:
        if ctx.llm is None:
            return ScoreResult(error="rubric_llm_judge requires an LLMClient")
        if ctx.rubrics_root is None:
            return ScoreResult(error="rubric_llm_judge requires a rubrics_root")

        try:
            text = _validate_text(fixture.input.get("text"))
            rubric_rel = fixture.expected.get("rubric_path")
            if not isinstance(rubric_rel, str):
                raise ValueError("expected.rubric_path must be a string")
            rubric_path = _resolve_rubric_path(rubric_rel, ctx.rubrics_root)
            rubric = _read_rubric(rubric_path)
        except (TypeError, ValueError, FileNotFoundError) as exc:
            return ScoreResult(error=str(exc))

        prompt = with_variables(
            RUBRIC_JUDGE_PROMPT,
            {"rubric": rubric, "text": text},
        )

        try:
            judgement = await ctx.llm.complete_structured(prompt, RubricScore)
        except Exception as exc:  # noqa: BLE001 - persisted by LLMClient already
            return ScoreResult(error=f"judge call failed: {exc}")

        threshold_raw = fixture.expected.get("min_score", _DEFAULT_THRESHOLD)
        try:
            threshold = int(threshold_raw)
        except (TypeError, ValueError):
            threshold = _DEFAULT_THRESHOLD
        passed = judgement.score >= threshold

        return ScoreResult(
            score=float(judgement.score),
            passed=passed,
            details={
                "judge_score": judgement.score,
                "criteria": judgement.criteria,
                "reasoning": judgement.reasoning,
                "rubric_path": rubric_rel,
                "threshold": threshold,
            },
        )


register(RubricLLMJudgeScorer())
