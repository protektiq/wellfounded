"""Batch embeddings for retrieval (delegates to ``LLMClient``)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from llm.client import LLMClient


async def embed_texts(
    texts: Sequence[str],
    session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> list[list[float]]:
    """Return one embedding vector per input string, preserving order."""
    client = LLMClient(
        session,
        organization_id,
        user_id,
    )
    return await client.embed(list(texts))
