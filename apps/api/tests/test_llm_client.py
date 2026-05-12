"""Tests for ``LLMClient`` (mocked HTTP, no external network)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llm.client import LLMClient
from llm.hashing import completion_input_hash, embedding_input_hash, text_sha256
from llm.models import LLMCallRecord
from llm.prompts import EMBEDDING_PROMPT_ID, EXAMPLE_PING_PROMPT, Prompt
from orgs.models import UserRole, UserStatus
from orgs.repository import OrgRepository


class _Answer(BaseModel):
    answer: str
    confidence: float


def _slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _anthropic_message_json(
    *,
    text: str | None = None,
    tool_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tool_input is not None:
        content = [
            {
                "type": "tool_use",
                "id": "toolu_test",
                "name": "structured_output",
                "input": tool_input,
            },
        ]
        stop_reason = "tool_use"
    else:
        content = [{"type": "text", "text": text or ""}]
        stop_reason = "end_turn"
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-4-7",
        "content": content,
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _openai_chat_json(
    *,
    content: str | None = None,
    parsed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "assistant"}
    if parsed is not None:
        msg["content"] = json.dumps(parsed)
    else:
        msg["content"] = content or ""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


def _openai_embeddings_json(batch_len: int) -> dict[str, Any]:
    def vec(i: int) -> list[float]:
        row = [0.0] * 3072
        row[i % 3072] = 1.0
        return row

    return {
        "object": "list",
        "data": [
            {"object": "embedding", "embedding": vec(i), "index": i}
            for i in range(batch_len)
        ],
        "model": "text-embedding-3-large",
        "usage": {"prompt_tokens": batch_len * 2, "total_tokens": batch_len * 2},
    }


def _make_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio(loop_scope="session")
async def test_anthropic_complete_persists(db_session: AsyncSession) -> None:
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="LLM Org", slug=_slug("llm-org"))
    user = await org_repo.create_user(
        organization_id=org.id,
        email="llm@example.com",
        display_name="LLM User",
        role=UserRole.attorney,
        status=UserStatus.active,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/messages")
        return httpx.Response(200, json=_anthropic_message_json(text="Hello world"))

    http = httpx.AsyncClient(transport=_make_transport(handler))
    anthropic = AsyncAnthropic(
        api_key="sk-test-anthropic",
        http_client=http,
        max_retries=0,
    )
    client = LLMClient(
        db_session,
        org.id,
        user.id,
        anthropic_client=anthropic,
        http_client=http,
    )

    resp = await client.complete(EXAMPLE_PING_PROMPT)
    assert "Hello world" in resp.text
    await db_session.commit()

    n = await db_session.scalar(select(func.count()).select_from(LLMCallRecord))
    assert n == 1
    row = (await db_session.execute(select(LLMCallRecord))).scalar_one()
    assert row.success is True
    assert row.organization_id == org.id
    assert row.user_id == user.id
    assert row.prompt_id == EXAMPLE_PING_PROMPT.id
    sys, usr = EXAMPLE_PING_PROMPT.rendered()
    expected_hash = completion_input_hash(
        prompt_id=EXAMPLE_PING_PROMPT.id,
        system=sys,
        user=usr,
        model_id=EXAMPLE_PING_PROMPT.model_id,
        provider="anthropic",
    )
    assert row.input_sha256 == expected_hash
    await http.aclose()


@pytest.mark.asyncio(loop_scope="session")
async def test_openai_structured_persists(db_session: AsyncSession) -> None:
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="LLM Org B", slug=_slug("llm-org-b"))
    user = await org_repo.create_user(
        organization_id=org.id,
        email="llm-b@example.com",
        display_name="LLM User B",
        role=UserRole.attorney,
        status=UserStatus.active,
    )

    prompt = Prompt(
        id="test.openai.structured",
        system="You extract answers.",
        user_template="Extract: {q}",
        variables=(("q", "Is ice cold?"),),
        provider="openai",
        model_id="gpt-4o-mini",
        default_max_tokens=128,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/chat/completions")
        return httpx.Response(
            200,
            json=_openai_chat_json(parsed={"answer": "yes", "confidence": 0.9}),
        )

    http = httpx.AsyncClient(transport=_make_transport(handler))
    oai = AsyncOpenAI(api_key="sk-test-openai", http_client=http, max_retries=0)
    client = LLMClient(
        db_session,
        org.id,
        user.id,
        openai_client=oai,
        http_client=http,
    )

    out = await client.complete_structured(prompt, _Answer)
    assert out.answer == "yes"
    assert out.confidence == 0.9
    await db_session.commit()

    row = (await db_session.execute(select(LLMCallRecord))).scalar_one()
    assert row.success is True
    sys, usr = prompt.rendered()
    expected_hash = completion_input_hash(
        prompt_id=prompt.id,
        system=sys,
        user=usr,
        model_id=prompt.model_id,
        provider="openai",
        schema_name="_Answer",
    )
    assert row.input_sha256 == expected_hash
    await http.aclose()


@pytest.mark.asyncio(loop_scope="session")
async def test_anthropic_complete_retry_429(db_session: AsyncSession) -> None:
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="LLM Org C", slug=_slug("llm-org-c"))
    user = await org_repo.create_user(
        organization_id=org.id,
        email="llm-c@example.com",
        display_name="LLM User C",
        role=UserRole.attorney,
        status=UserStatus.active,
    )

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/messages")
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429,
                json={
                    "type": "error",
                    "error": {"type": "rate_limit_error", "message": "slow down"},
                },
            )
        return httpx.Response(200, json=_anthropic_message_json(text="recovered"))

    http = httpx.AsyncClient(transport=_make_transport(handler))
    anthropic = AsyncAnthropic(
        api_key="sk-test-anthropic",
        http_client=http,
        max_retries=0,
    )
    client = LLMClient(
        db_session,
        org.id,
        user.id,
        anthropic_client=anthropic,
        http_client=http,
    )

    resp = await client.complete(EXAMPLE_PING_PROMPT)
    assert "recovered" in resp.text
    await db_session.commit()

    assert calls["n"] == 2
    n = await db_session.scalar(select(func.count()).select_from(LLMCallRecord))
    assert n == 1
    await http.aclose()


@pytest.mark.asyncio(loop_scope="session")
async def test_embed_batches_two_http(db_session: AsyncSession) -> None:
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="LLM Org D", slug=_slug("llm-org-d"))
    user = await org_repo.create_user(
        organization_id=org.id,
        email="llm-d@example.com",
        display_name="LLM User D",
        role=UserRole.attorney,
        status=UserStatus.active,
    )

    http_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/embeddings")
        http_calls["n"] += 1
        body = json.loads(request.content.decode("utf-8"))
        batch = body["input"]
        assert isinstance(batch, list)
        return httpx.Response(200, json=_openai_embeddings_json(len(batch)))

    http = httpx.AsyncClient(transport=_make_transport(handler))
    oai = AsyncOpenAI(api_key="sk-test-openai", http_client=http, max_retries=0)
    client = LLMClient(
        db_session,
        org.id,
        user.id,
        openai_client=oai,
        http_client=http,
    )

    texts = [f"chunk-{i}" for i in range(65)]
    out = await client.embed(texts)
    assert len(out) == 65
    await db_session.commit()

    assert http_calls["n"] == 2
    n = await db_session.scalar(select(func.count()).select_from(LLMCallRecord))
    assert n == 2

    rows = (await db_session.execute(select(LLMCallRecord))).scalars().all()
    assert {r.prompt_id for r in rows} == {EMBEDDING_PROMPT_ID}
    digests = [text_sha256(t) for t in texts]
    h_first = embedding_input_hash(
        model_id="text-embedding-3-large",
        text_digests=digests[0:64],
    )
    h_second = embedding_input_hash(
        model_id="text-embedding-3-large",
        text_digests=digests[64:65],
    )
    stored = {r.input_sha256 for r in rows}
    assert stored == {h_first, h_second}
    await http.aclose()
