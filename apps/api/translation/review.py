"""LLM review pass for NMT segment translations."""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from llm.client import LLMClient
from llm.prompts import DEFAULT_CLAUDE_MODEL, TRANSLATION_REVIEW_PROMPT, with_variables


async def review_translations(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    source_language: str,
    segments_json: str,
) -> tuple[list[str], str]:
    """Return reviewed English strings aligned with input segments."""
    llm = LLMClient(session, organization_id, user_id)
    prompt = with_variables(
        TRANSLATION_REVIEW_PROMPT,
        {
            "source_language": source_language,
            "segments_json": segments_json,
        },
    )
    raw = await llm.complete(prompt)
    try:
        data = json.loads(raw.text)
    except json.JSONDecodeError as exc:
        raise ValueError("translation review returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("translation review payload must be an object")
    english = data.get("english_segments")
    if not isinstance(english, list) or not all(isinstance(x, str) for x in english):
        raise ValueError("english_segments must be a list of strings")
    return list(english), f"translation-review@{DEFAULT_CLAUDE_MODEL}"
