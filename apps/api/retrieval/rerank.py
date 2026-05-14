"""Rerank retrieval candidates (LLM default, optional cross-encoder)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings, get_settings
from llm.client import LLMClient
from llm.prompts import RETRIEVAL_RERANK_PROMPT, with_variables
from retrieval.schemas import RetrievedPassage

_RERANK_TEXT_SNIPPET_CHARS = 800


class RerankOutput(BaseModel):
    """Structured LLM response: passage ids in relevance order (full permutation)."""

    ordered_passage_ids: list[uuid.UUID] = Field(
        ...,
        description="Every candidate passage id exactly once, most relevant first",
    )


def _snippet(text: str) -> str:
    t = text.strip()
    if len(t) <= _RERANK_TEXT_SNIPPET_CHARS:
        return t
    return t[:_RERANK_TEXT_SNIPPET_CHARS] + "..."


def _passages_json_for_prompt(passages: list[RetrievedPassage]) -> str:
    rows = [
        {
            "passage_id": str(p.passage_id),
            "text_snippet": _snippet(p.text),
        }
        for p in passages
    ]
    return json.dumps(rows, ensure_ascii=False)


def _apply_order(
    passages: list[RetrievedPassage],
    ordered_ids: list[uuid.UUID],
) -> list[RetrievedPassage]:
    by_id = {p.passage_id: p for p in passages}
    seen: set[uuid.UUID] = set()
    ordered: list[RetrievedPassage] = []
    for pid in ordered_ids:
        row = by_id.get(pid)
        if row is not None:
            ordered.append(row)
            seen.add(pid)
    for p in passages:
        if p.passage_id not in seen:
            ordered.append(p)
    n = len(ordered)
    scores = [1.0 - (i / max(1, n - 1)) * 0.5 for i in range(n)] if n else []
    return [
        RetrievedPassage(
            passage_id=p.passage_id,
            document_id=p.document_id,
            source_family=p.source_family,
            document_title=p.document_title,
            publication_date=p.publication_date,
            url=p.url,
            section_anchor=p.section_anchor,
            text=p.text,
            similarity_score=float(scores[i]) if n else 0.0,
        )
        for i, p in enumerate(ordered)
    ]


async def _rerank_llm(
    query: str,
    passages: list[RetrievedPassage],
    session: AsyncSession,
    organization_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> list[RetrievedPassage]:
    if not passages:
        return []
    client = LLMClient(session, organization_id, user_id)
    prompt = with_variables(
        RETRIEVAL_RERANK_PROMPT,
        {
            "query": query,
            "passages_json": _passages_json_for_prompt(passages),
        },
    )
    out = await client.complete_structured(
        prompt,
        RerankOutput,
        max_tokens=4096,
        temperature=0.0,
    )
    return _apply_order(passages, out.ordered_passage_ids)


def _rerank_cross_encoder_sync(
    query: str,
    passages: list[RetrievedPassage],
    model_id: str,
) -> list[RetrievedPassage]:
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError(
            "retrieval_rerank_backend is cross_encoder but sentence-transformers "
            "is not installed. Install it and its PyTorch dependency, or set "
            "RETRIEVAL_RERANK_BACKEND=llm in the environment.",
        ) from exc
    try:
        model = CrossEncoder(model_id)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load cross-encoder model {model_id!r}. "
            "Fix the model path or use RETRIEVAL_RERANK_BACKEND=llm.",
        ) from exc
    pairs = [(query, _snippet(p.text)) for p in passages]
    raw_scores = model.predict(pairs)
    scored = list(zip(passages, (float(s) for s in raw_scores), strict=True))
    scored.sort(key=lambda x: x[1], reverse=True)
    n = len(scored)
    return [
        RetrievedPassage(
            passage_id=p.passage_id,
            document_id=p.document_id,
            source_family=p.source_family,
            document_title=p.document_title,
            publication_date=p.publication_date,
            url=p.url,
            section_anchor=p.section_anchor,
            text=p.text,
            similarity_score=1.0 - (i / max(1, n - 1)) * 0.5,
        )
        for i, (p, _) in enumerate(scored)
    ]


async def rerank_passages(
    query: str,
    passages: list[RetrievedPassage],
    session: AsyncSession,
    *,
    organization_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    backend: Literal["llm", "cross_encoder"] | None = None,
    settings: Settings | None = None,
) -> list[RetrievedPassage]:
    """Reorder passages by relevance; updates ``similarity_score`` to rerank scores."""
    s = settings if settings is not None else get_settings()
    resolved: Literal["llm", "cross_encoder"] = (
        backend if backend is not None else s.retrieval_rerank_backend
    )
    if not passages:
        return []
    if resolved == "llm":
        return await _rerank_llm(query, passages, session, organization_id, user_id)
    return await asyncio.to_thread(
        _rerank_cross_encoder_sync,
        query,
        passages,
        s.retrieval_cross_encoder_model,
    )
