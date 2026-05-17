"""Live declaration quality scorer: LangGraph draft + rubric LLM judge."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, cast

from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession

from audit.writer import AuditWriter
from cases.models import ClaimBasis
from declarations.graph import build_declaration_graph
from declarations.schemas import CaseMetadata
from evals.declaration_criteria import (
    DECLARATION_CRITERION_KEYS,
    DEFAULT_FAITHFULNESS_MIN,
    DEFAULT_MIN_SCORE,
)
from evals.declaration_format import format_draft_for_judge
from evals.eval_audit import EvalAuditWriter
from evals.fixtures import Fixture, ScoreResult
from evals.scorers.base import ScorerContext, register
from evals.scorers.rubric_llm_judge import (
    RubricScore,
    _read_rubric,
    _resolve_rubric_path,
)
from llm.prompts import Prompt, with_variables

_EVAL_ORG_ID = uuid.UUID("00000000-0000-4000-8000-00000000e001")
_EVAL_USER_ID = uuid.UUID("00000000-0000-4000-8000-00000000e002")

_MAX_PRIORS = 8

_SYSTEM_PROMPT = (
    "You evaluate a generated asylum declaration draft against a practitioner rubric. "
    "You are given the source transcript, any prior statements, the draft text, and "
    "flags raised by the drafting system. Be exacting and conservative. Score on a "
    "1-5 integer scale per the rubric. Use criterion keys exactly as specified in the "
    "rubric. If a criterion cannot be assessed, mark it 0 in the criteria map and "
    "explain why. Do not invent facts not in the source materials."
)

_USER_TEMPLATE = (
    "Rubric (markdown):\n"
    "---\n"
    "{rubric}\n"
    "---\n\n"
    "Evaluation package (source material, draft, and flags):\n"
    "---\n"
    "{evaluation_package}\n"
    "---\n\n"
    "Return a single structured judgement that conforms to the schema."
)

DECLARATION_JUDGE_PROMPT = Prompt(
    id="evals.declaration_judge.v1",
    system=_SYSTEM_PROMPT,
    user_template=_USER_TEMPLATE,
    variables=(("rubric", ""), ("evaluation_package", "")),
    default_max_tokens=2048,
    default_temperature=0.0,
)


def _parse_case_metadata(raw: Any) -> CaseMetadata:
    if not isinstance(raw, dict):
        raise TypeError("input.case_metadata must be an object")
    basis_raw = raw.get("basis")
    if isinstance(basis_raw, str):
        basis = ClaimBasis(basis_raw)
    elif isinstance(basis_raw, ClaimBasis):
        basis = basis_raw
    else:
        raise ValueError("input.case_metadata.basis must be a valid claim basis")
    return CaseMetadata(
        pseudonym=str(raw.get("pseudonym", "")),
        country_code=str(raw.get("country_code", "")).upper(),
        basis=basis,
        group_description=str(raw.get("group_description", "")),
    )


def _parse_transcript(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("input.transcript must be an object")
    segments = raw.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("input.transcript.segments must be a non-empty list")
    return dict(raw)


def _parse_prior_statements(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError("input.prior_statements must be a list")
    if len(raw) > _MAX_PRIORS:
        raise ValueError(f"prior_statements exceeds maximum of {_MAX_PRIORS}")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise TypeError(f"prior_statements[{i}] must be an object")
        prior_id = item.get("id")
        if prior_id is not None and not isinstance(prior_id, str):
            raise TypeError(f"prior_statements[{i}].id must be a string")
        out.append(dict(item))
    return out


def _parse_min_criteria(expected: dict[str, Any]) -> dict[str, float]:
    raw = expected.get("min_criteria")
    if raw is None:
        return {"faithfulness_to_source": DEFAULT_FAITHFULNESS_MIN}
    if not isinstance(raw, dict):
        raise ValueError("expected.min_criteria must be an object")
    out: dict[str, float] = {}
    for key, val in raw.items():
        if not isinstance(key, str) or key not in DECLARATION_CRITERION_KEYS:
            raise ValueError(f"unknown min_criteria key: {key!r}")
        try:
            out[key] = float(val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"min_criteria[{key!r}] must be numeric") from exc
    return out


def _check_pass(
    judgement: RubricScore,
    *,
    min_score: int,
    min_criteria: dict[str, float],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if judgement.score < min_score:
        failures.append(f"overall: {judgement.score} < {min_score}")
    for key, threshold in min_criteria.items():
        val = judgement.criteria.get(key)
        if val is None or val == 0:
            failures.append(f"{key}: not scored")
        elif float(val) < threshold:
            failures.append(f"{key}: {val} < {threshold}")
    for key in DECLARATION_CRITERION_KEYS:
        if key in min_criteria:
            continue
        val = judgement.criteria.get(key)
        if val is not None and val != 0 and float(val) < min_score:
            failures.append(f"{key}: {val} < {min_score}")
    return len(failures) == 0, failures


class DeclarationQualityLiveScorer:
    name: str = "declaration_quality_live"
    requires_llm: bool = True

    async def score(
        self,
        fixture: Fixture,
        *,
        ctx: ScorerContext,
    ) -> ScoreResult:
        if ctx.llm is None:
            return ScoreResult(error="declaration_quality_live requires an LLMClient")
        if ctx.rubrics_root is None:
            return ScoreResult(error="declaration_quality_live requires a rubrics_root")
        if ctx.session is None:
            return ScoreResult(
                error="declaration_quality_live requires a database session",
            )

        session: AsyncSession = ctx.session

        try:
            transcript = _parse_transcript(fixture.input.get("transcript"))
            case_metadata = _parse_case_metadata(fixture.input.get("case_metadata"))
            prior_statements = _parse_prior_statements(
                fixture.input.get("prior_statements"),
            )
            rubric_rel = fixture.expected.get("rubric_path")
            if not isinstance(rubric_rel, str):
                raise ValueError("expected.rubric_path must be a string")
            rubric_path = _resolve_rubric_path(rubric_rel, ctx.rubrics_root)
            rubric = _read_rubric(rubric_path)
            min_score_raw = fixture.expected.get("min_score", DEFAULT_MIN_SCORE)
            min_score = int(min_score_raw)
            min_criteria = _parse_min_criteria(fixture.expected)
        except (TypeError, ValueError, FileNotFoundError) as exc:
            return ScoreResult(error=str(exc))

        draft_id = uuid.uuid4()
        case_id = uuid.uuid4()
        checkpointer = MemorySaver()
        audit = cast(AuditWriter, EvalAuditWriter())
        graph = build_declaration_graph(
            checkpointer=checkpointer,
            session=session,
            organization_id=_EVAL_ORG_ID,
            user_id=_EVAL_USER_ID,
            draft_id=draft_id,
            audit=audit,
        )

        init: dict[str, Any] = {
            "organization_id": _EVAL_ORG_ID,
            "case_id": case_id,
            "draft_id": draft_id,
            "requested_by_user_id": _EVAL_USER_ID,
            "case_metadata": case_metadata.model_dump(mode="json"),
            "transcript": transcript,
            "prior_statements": prior_statements,
            "model_versions": {},
        }

        try:
            final_state = await graph.ainvoke(
                init,
                {"configurable": {"thread_id": str(draft_id)}},
            )
        except Exception as exc:  # noqa: BLE001
            return ScoreResult(error=f"declaration graph failed: {exc}")

        draft_raw = final_state.get("draft")
        flags_raw = final_state.get("flags", [])
        if not isinstance(draft_raw, dict):
            return ScoreResult(error="graph finished without draft")

        flags_list = flags_raw if isinstance(flags_raw, list) else []
        evaluation_package = format_draft_for_judge(
            draft=draft_raw,
            flags=[f for f in flags_list if isinstance(f, dict)],
            transcript=transcript,
            prior_statements=prior_statements,
        )
        digest = hashlib.sha256(evaluation_package.encode("utf-8")).hexdigest()
        package_hash = digest[:16]

        prompt = with_variables(
            DECLARATION_JUDGE_PROMPT,
            {"rubric": rubric, "evaluation_package": evaluation_package},
        )

        try:
            judgement = await ctx.llm.complete_structured(prompt, RubricScore)
        except Exception as exc:  # noqa: BLE001
            return ScoreResult(error=f"judge call failed: {exc}")

        passed, failures = _check_pass(
            judgement,
            min_score=min_score,
            min_criteria=min_criteria,
        )

        return ScoreResult(
            score=float(judgement.score),
            passed=passed,
            details={
                "judge_score": judgement.score,
                "criteria": judgement.criteria,
                "reasoning": judgement.reasoning,
                "rubric_path": rubric_rel,
                "threshold": min_score,
                "min_criteria": min_criteria,
                "failures": failures,
                "evaluation_package_hash": package_hash,
                "flag_count": len(flags_list),
                "model_versions": final_state.get("model_versions", {}),
            },
        )


register(DeclarationQualityLiveScorer())
