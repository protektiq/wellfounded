"""Mocked-LLM tests for the rubric-driven LLM-as-judge scorer.

These tests do not contact Anthropic; they use ``httpx.MockTransport`` to
stand in for the real HTTP backend, exactly as ``tests/test_llm_client.py``
does for the gateway itself. The point of these tests is to verify that the
scorer renders the prompt, routes through ``LLMClient``, persists an
``LLMCallRecord`` row, and refuses unsafe rubric paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from anthropic import AsyncAnthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from evals.fixtures import Fixture
from evals.scorers import SCORER_REGISTRY
from evals.scorers.base import ScorerContext
from llm.client import LLMClient
from llm.models import LLMCallRecord


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
async def test_rubric_judge_calls_llm_and_persists(
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    rubrics_root = tmp_path / "rubrics"
    rubrics_root.mkdir()
    (rubrics_root / "declaration_v1.md").write_text(
        "# Declaration rubric v1\n- Faithfulness: 1-5\n- Completeness: 1-5\n",
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/messages")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json=_anthropic_tool_use(
                {
                    "score": 4,
                    "reasoning": "Covers all rubric criteria with one minor omission.",
                    "criteria": {"faithfulness": 4, "completeness": 4},
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
            "id": "decl-001",
            "category": "declaration_quality",
            "scorer": "rubric_llm_judge",
            "input": {
                "text": (
                    "I fled my country because of persecution. I lived in "
                    "hiding for three months before crossing the border."
                ),
            },
            "expected": {
                "rubric_path": "declaration_v1.md",
                "min_score": 4,
            },
        },
    )

    scorer = SCORER_REGISTRY["rubric_llm_judge"]
    ctx = ScorerContext(llm=llm, rubrics_root=rubrics_root)
    result = await scorer.score(fixture, ctx=ctx)
    await db_session.commit()

    assert result.error is None
    assert result.score == 4.0
    assert result.passed is True
    assert result.details["criteria"] == {"faithfulness": 4, "completeness": 4}
    assert result.details["rubric_path"] == "declaration_v1.md"
    assert result.details["threshold"] == 4

    user_message = captured["body"]["messages"][0]["content"]
    assert "Declaration rubric v1" in user_message
    assert "fled my country" in user_message

    count = await db_session.scalar(select(func.count()).select_from(LLMCallRecord))
    assert count == 1
    row = (await db_session.execute(select(LLMCallRecord))).scalar_one()
    assert row.success is True
    assert row.prompt_id == "evals.rubric_judge.v1"
    assert row.organization_id is None
    assert row.user_id is None

    await http.aclose()


@pytest.mark.asyncio(loop_scope="session")
async def test_rubric_judge_returns_error_without_llm(tmp_path: Path) -> None:
    rubrics_root = tmp_path / "rubrics"
    rubrics_root.mkdir()
    fixture = Fixture.model_validate(
        {
            "id": "no-llm",
            "category": "declaration_quality",
            "scorer": "rubric_llm_judge",
            "input": {"text": "anything"},
            "expected": {"rubric_path": "missing.md"},
        },
    )
    ctx = ScorerContext(llm=None, rubrics_root=rubrics_root)
    scorer = SCORER_REGISTRY["rubric_llm_judge"]
    result = await scorer.score(fixture, ctx=ctx)
    assert result.score is None
    assert result.error is not None
    assert "LLMClient" in result.error


@pytest.mark.asyncio(loop_scope="session")
async def test_rubric_judge_rejects_path_traversal(
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    rubrics_root = tmp_path / "rubrics"
    rubrics_root.mkdir()
    (tmp_path / "secret.md").write_text("not for the judge", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("LLM must not be called when path validation fails")

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
            "id": "traversal",
            "category": "declaration_quality",
            "scorer": "rubric_llm_judge",
            "input": {"text": "ok"},
            "expected": {"rubric_path": "../secret.md"},
        },
    )
    scorer = SCORER_REGISTRY["rubric_llm_judge"]
    ctx = ScorerContext(llm=llm, rubrics_root=rubrics_root)
    result = await scorer.score(fixture, ctx=ctx)

    assert result.score is None
    assert result.error is not None
    assert "escapes rubrics root" in result.error
    await http.aclose()


@pytest.mark.asyncio(loop_scope="session")
async def test_rubric_judge_reports_missing_rubric(
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    rubrics_root = tmp_path / "rubrics"
    rubrics_root.mkdir()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("LLM must not be called when rubric file is missing")

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
            "id": "missing-rubric",
            "category": "declaration_quality",
            "scorer": "rubric_llm_judge",
            "input": {"text": "ok"},
            "expected": {"rubric_path": "does_not_exist.md"},
        },
    )
    scorer = SCORER_REGISTRY["rubric_llm_judge"]
    ctx = ScorerContext(llm=llm, rubrics_root=rubrics_root)
    result = await scorer.score(fixture, ctx=ctx)

    assert result.score is None
    assert result.error is not None
    assert "not found" in result.error
    await http.aclose()
