"""Live scorer: call the country-conditions draft node with fixture passages.

Fixture ``input`` schema::

    {
      "section_id": "<one of CC_SECTION_IDS>",
      "section_query": "<natural-language query used for retrieval>",
      "passage_items": [
        {
          "passage_id": "<stable UUID>",
          "text": "<passage body>",
          "source_family": "<SourceFamily value>",
          "document_title": "<title>",
          "publication_date": "<YYYY-MM-DD>",
          "url": "<source URL>",
          "section_anchor": "<heading>",
          "similarity_score": 0.0
        },
        ...
      ]
    }

The scorer calls ``LLMClient.complete_structured`` with ``CC_DRAFT_PROMPT``
and ``SectionDraftOutput``, then checks that every ``<cite passage_id="..."/>``
token in the model output references a passage_id from ``passage_items``.
Any citation not in that set is an "orphan" (hallucinated reference).

Score = (cited_count - orphan_count) / cited_count, or 1.0 if cited_count=0.
Passed = no orphans.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from country_conditions.prompts import CC_DRAFT_PROMPT
from country_conditions.schemas import (
    CC_SECTION_IDS,
    SectionDraftOutput,
    passage_ids_in_prose,
)
from evals.fixtures import Fixture, ScoreResult
from evals.scorers.base import ScorerContext, register
from llm.prompts import with_variables

_MAX_PASSAGE_ITEMS = 64
_MAX_TEXT_CHARS = 32_000


def _coerce_passage_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise TypeError("passage_items must be a list")
    if len(value) > _MAX_PASSAGE_ITEMS:
        raise ValueError(f"passage_items exceeds maximum of {_MAX_PASSAGE_ITEMS}")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            raise TypeError(f"passage_items[{i}] must be an object")
        pid = item.get("passage_id")
        if not isinstance(pid, str) or not pid:
            raise ValueError(f"passage_items[{i}].passage_id must be a non-empty string")
        try:
            uuid.UUID(pid)
        except ValueError as exc:
            raise ValueError(f"passage_items[{i}].passage_id is not a valid UUID") from exc
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"passage_items[{i}].text must be a non-empty string")
        if len(text) > _MAX_TEXT_CHARS:
            raise ValueError(f"passage_items[{i}].text exceeds {_MAX_TEXT_CHARS} chars")
        out.append(dict(item))
    return out


class CountryConditionsDraftScorer:
    name: str = "country_conditions_draft"
    requires_llm: bool = True

    async def score(
        self,
        fixture: Fixture,
        *,
        ctx: ScorerContext,
    ) -> ScoreResult:
        if ctx.llm is None:
            return ScoreResult(error="country_conditions_draft scorer requires LLM client")

        section_id = fixture.input.get("section_id")
        section_query = fixture.input.get("section_query")
        raw_items = fixture.input.get("passage_items")

        if not isinstance(section_id, str) or section_id not in CC_SECTION_IDS:
            return ScoreResult(
                error=f"input.section_id must be one of {list(CC_SECTION_IDS)}"
            )
        if not isinstance(section_query, str) or not section_query.strip():
            return ScoreResult(error="input.section_query must be a non-empty string")

        try:
            passage_items = _coerce_passage_items(raw_items)
        except (TypeError, ValueError) as exc:
            return ScoreResult(error=f"input.passage_items invalid: {exc}")

        allowed_ids: set[str] = {item["passage_id"] for item in passage_items}

        prompt = with_variables(
            CC_DRAFT_PROMPT,
            {
                "section_id": section_id,
                "section_query": section_query,
                "outline": "(standalone section draft for eval — no prior outline context)",
                "passages_json": json.dumps(passage_items, default=str),
            },
        )

        try:
            draft = await ctx.llm.complete_structured(prompt, SectionDraftOutput)
        except Exception as exc:  # noqa: BLE001
            return ScoreResult(error=f"LLM call failed: {exc}")

        if draft.section_id != section_id:
            return ScoreResult(
                error=f"model returned section_id {draft.section_id!r}, expected {section_id!r}",
                details={"section_id_mismatch": True},
            )

        cited_ids = [str(pid) for pid in passage_ids_in_prose(draft.prose)]
        orphans = sorted({cid for cid in cited_ids if cid not in allowed_ids})
        total_cited = len(cited_ids)
        citation_score = (
            1.0 if total_cited == 0 else (total_cited - len(orphans)) / total_cited
        )

        return ScoreResult(
            score=citation_score,
            passed=len(orphans) == 0,
            details={
                "section_id": section_id,
                "passage_count": len(passage_items),
                "cited_count": total_cited,
                "orphan_count": len(orphans),
                "orphans": orphans,
            },
        )


register(CountryConditionsDraftScorer())
