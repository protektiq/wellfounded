"""Mocked tests for declaration_quality_live scorer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

import orgs.models  # noqa: F401 — registers Organization in SQLAlchemy metadata for llm_call_records FK

from declarations.schemas import (
    DECLARATION_SECTION_IDS,
    DeclarationDraftContent,
    DeclarationParagraph,
    DeclarationSection,
)
from evals.fixtures import Fixture
from evals.scorers import SCORER_REGISTRY
from evals.scorers.base import ScorerContext
from llm.client import LLMClient


def _minimal_draft() -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for sid in DECLARATION_SECTION_IDS:
        sections[sid] = DeclarationSection(
            section_id=sid,
            paragraphs=[
                DeclarationParagraph(
                    id=f"{sid}:p0",
                    text=f"Substantive text for {sid}.",
                    source_segment_ids=["seg-0"],
                ),
            ],
        ).model_dump(mode="json")
    return DeclarationDraftContent.model_validate({"sections": sections}).model_dump(
        mode="json",
    )


def _anthropic_tool_use(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-4-7",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_test",
                "name": "structured_output",
                "input": payload,
            },
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 12, "output_tokens": 5},
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_declaration_quality_live_scores_and_passes(
    tmp_path: Path,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rubrics_root = tmp_path / "rubrics"
    rubrics_root.mkdir()
    (rubrics_root / "declaration_v1.md").write_text(
        "# Rubric\nfaithfulness_to_source 1-5\n",
        encoding="utf-8",
    )

    class _MockGraph:
        async def ainvoke(
            self,
            init: dict[str, Any],
            config: dict[str, Any],
        ) -> dict[str, Any]:
            _ = (init, config)
            return {
                "draft": _minimal_draft(),
                "flags": [
                    {
                        "type": "GAP",
                        "paragraph_id": "past_persecution:p0",
                        "span": {"start": 0, "end": 0},
                        "description": "Missing date",
                        "suggested_resolution": "Ask client",
                        "status": "open",
                    },
                ],
                "model_versions": {"draft": "claude-opus-4-7"},
            }

    monkeypatch.setattr(
        "evals.scorers.declaration_quality_live.build_declaration_graph",
        lambda **kwargs: _MockGraph(),
    )

    judge_payload = {
        "score": 4,
        "reasoning": "Solid draft with minor gaps.",
        "criteria": {
            "faithfulness_to_source": 5,
            "structural_completeness": 4,
            "voice_authenticity": 4,
            "flag_accuracy": 4,
            "legal_element_coverage": 4,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        user_msg = body["messages"][0]["content"]
        assert "Evaluation package" in user_msg
        return httpx.Response(200, json=_anthropic_tool_use(judge_payload))

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    anthropic = AsyncAnthropic(api_key="sk-test", http_client=http, max_retries=0)
    llm = LLMClient(
        db_session,
        organization_id=None,
        user_id=None,
        anthropic_client=anthropic,
        http_client=http,
    )

    fixture = Fixture.model_validate(
        {
            "id": "ti-er-journalist-01",
            "category": "declaration_quality",
            "scorer": "declaration_quality_live",
            "tags": ["ti", "calibration"],
            "input": {
                "transcript": {
                    "source_language": "ti",
                    "segments": [
                        {
                            "start": 0.0,
                            "end": 10.0,
                            "speaker": "client",
                            "source_text": "test",
                            "english_text": "My name is M.A.",
                        },
                    ],
                    "full_source_text": "test",
                    "full_english_text": "My name is M.A.",
                },
                "prior_statements": [],
                "case_metadata": {
                    "pseudonym": "M.A. — Eritrea",
                    "country_code": "ER",
                    "basis": "political_opinion",
                    "group_description": "journalists",
                },
            },
            "expected": {
                "rubric_path": "declaration_v1.md",
                "min_score": 4,
                "min_criteria": {"faithfulness_to_source": 4.5},
            },
        },
    )

    scorer = SCORER_REGISTRY["declaration_quality_live"]
    ctx = ScorerContext(
        llm=llm,
        rubrics_root=rubrics_root,
        session=db_session,
    )
    result = await scorer.score(fixture, ctx=ctx)
    await db_session.commit()

    assert result.error is None
    assert result.passed is True
    assert result.score == 4.0
    assert result.details["criteria"]["faithfulness_to_source"] == 5
    await http.aclose()


@pytest.mark.asyncio(loop_scope="session")
async def test_declaration_quality_live_fails_faithfulness_threshold(
    tmp_path: Path,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rubrics_root = tmp_path / "rubrics"
    rubrics_root.mkdir()
    (rubrics_root / "declaration_v1.md").write_text("# Rubric\n", encoding="utf-8")

    class _MockGraph:
        async def ainvoke(
            self,
            init: dict[str, Any],
            config: dict[str, Any],
        ) -> dict[str, Any]:
            _ = (init, config)
            return {"draft": _minimal_draft(), "flags": [], "model_versions": {}}

    monkeypatch.setattr(
        "evals.scorers.declaration_quality_live.build_declaration_graph",
        lambda **kwargs: _MockGraph(),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_anthropic_tool_use(
                {
                    "score": 3,
                    "reasoning": "Weak faithfulness.",
                    "criteria": {
                        "faithfulness_to_source": 3,
                        "structural_completeness": 4,
                        "voice_authenticity": 4,
                        "flag_accuracy": 4,
                        "legal_element_coverage": 4,
                    },
                },
            ),
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    anthropic = AsyncAnthropic(api_key="sk-test", http_client=http, max_retries=0)
    llm = LLMClient(
        db_session,
        organization_id=None,
        user_id=None,
        anthropic_client=anthropic,
        http_client=http,
    )

    fixture = Fixture.model_validate(
        {
            "id": "fail-faith",
            "category": "declaration_quality",
            "scorer": "declaration_quality_live",
            "input": {
                "transcript": {
                    "source_language": "es",
                    "segments": [
                        {
                            "start": 0.0,
                            "end": 5.0,
                            "speaker": "client",
                            "source_text": "hola",
                            "english_text": "hello",
                        },
                    ],
                    "full_source_text": "hola",
                    "full_english_text": "hello",
                },
                "case_metadata": {
                    "pseudonym": "X — Mexico",
                    "country_code": "MX",
                    "basis": "political_opinion",
                    "group_description": "group",
                },
            },
            "expected": {
                "rubric_path": "declaration_v1.md",
                "min_criteria": {"faithfulness_to_source": 4.5},
            },
        },
    )

    scorer = SCORER_REGISTRY["declaration_quality_live"]
    ctx = ScorerContext(llm=llm, rubrics_root=rubrics_root, session=db_session)
    result = await scorer.score(fixture, ctx=ctx)

    assert result.error is None
    assert result.passed is False
    assert "faithfulness_to_source" in str(result.details.get("failures"))
    await http.aclose()
