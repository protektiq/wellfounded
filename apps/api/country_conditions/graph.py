"""LangGraph state machine for country conditions memo generation."""

from __future__ import annotations

import json
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from audit.writer import AuditWriter
from country_conditions.prompts import (
    CC_DRAFT_PROMPT,
    CC_PLAN_PROMPT,
    CC_SYNTHESIZE_PROMPT,
    CC_VERIFY_PROMPT,
)
from country_conditions.schemas import (
    CC_SECTION_IDS,
    CountryConditionsInputs,
    FinalMemoStructured,
    MemoSectionStructured,
    PlanOutput,
    SectionDraftOutput,
    SynthesizeSectionsOut,
    VerifySectionOutput,
    assert_citations_subset,
    build_bibliography,
    timeframe_start_date,
)
from llm.client import LLMClient
from llm.prompts import DEFAULT_CLAUDE_MODEL, with_variables
from retrieval.passage_search import search
from retrieval.schemas import RetrievedPassage


class CountryConditionsState(TypedDict, total=False):
    organization_id: uuid.UUID
    case_id: uuid.UUID
    memo_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    inputs: dict[str, Any]
    outline: str
    section_queries: dict[str, str]
    section_titles: dict[str, str]
    retrieval_by_section: dict[str, list[dict[str, Any]]]
    section_drafts: dict[str, str]
    verified_sections: dict[str, str]
    final_memo: dict[str, Any]
    model_versions: dict[str, str]
    errors: list[str]


def _passage_to_dict(p: RetrievedPassage) -> dict[str, Any]:
    return {
        "passage_id": str(p.passage_id),
        "document_id": str(p.document_id),
        "source_family": p.source_family,
        "document_title": p.document_title,
        "publication_date": p.publication_date.isoformat(),
        "url": p.url,
        "section_anchor": p.section_anchor,
        "text": p.text,
        "similarity_score": p.similarity_score,
    }


def _allowed_passage_ids(rows: list[dict[str, Any]]) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for row in rows:
        raw = row.get("passage_id")
        if isinstance(raw, str):
            out.add(uuid.UUID(raw))
        else:
            raise TypeError("passage_id must be str in serialized passage")
    return out


def _flatten_passage_meta(
    retrieval: dict[str, list[dict[str, Any]]],
) -> dict[uuid.UUID, dict[str, str]]:
    meta: dict[uuid.UUID, dict[str, str]] = {}
    for rows in retrieval.values():
        for row in rows:
            pid = uuid.UUID(str(row["passage_id"]))
            meta[pid] = {
                "document_title": str(row["document_title"]),
                "publication_date": str(row["publication_date"]),
                "url": str(row["url"]),
                "section_anchor": str(row["section_anchor"]),
            }
    return meta


def build_country_conditions_graph(
    *,
    checkpointer: Any,
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    memo_id: uuid.UUID,
    audit: AuditWriter,
    interrupt_after: list[str] | None = None,
) -> Any:
    """Compile the memo generation graph with injected persistence and audit."""

    async def plan_node(state: CountryConditionsState) -> dict[str, Any]:
        llm = LLMClient(session, organization_id, user_id)
        inputs = CountryConditionsInputs.model_validate(state["inputs"])
        prompt = with_variables(
            CC_PLAN_PROMPT,
            {"inputs_json": inputs.model_dump_json()},
        )
        plan_out = await llm.complete_structured(prompt, PlanOutput)
        mv = dict(state.get("model_versions", {}))
        mv["plan"] = DEFAULT_CLAUDE_MODEL
        await audit.record(
            "country_conditions.plan.complete",
            organization_id,
            user_id,
            "country_conditions_memo",
            memo_id,
            metadata={"sections": list(CC_SECTION_IDS)},
        )
        await session.flush()
        return {
            "outline": plan_out.outline,
            "section_queries": plan_out.section_queries,
            "section_titles": plan_out.section_titles,
            "model_versions": mv,
        }

    async def retrieve_node(state: CountryConditionsState) -> dict[str, Any]:
        inputs = CountryConditionsInputs.model_validate(state["inputs"])
        queries = state["section_queries"]
        by_section: dict[str, list[dict[str, Any]]] = {}
        for sid in CC_SECTION_IDS:
            q = queries.get(sid)
            if not q:
                raise ValueError(f"missing retrieval query for {sid}")
            rows = await search(
                session,
                q,
                organization_id=organization_id,
                user_id=user_id,
                country_codes=[inputs.country_code],
                date_after=timeframe_start_date(inputs.timeframe_start_year),
                top_k=16,
            )
            by_section[sid] = [_passage_to_dict(p) for p in rows]
        await audit.record(
            "country_conditions.retrieve.complete",
            organization_id,
            user_id,
            "country_conditions_memo",
            memo_id,
            metadata={"sections": list(CC_SECTION_IDS)},
        )
        await session.flush()
        return {"retrieval_by_section": by_section}

    async def draft_node(state: CountryConditionsState) -> dict[str, Any]:
        llm = LLMClient(session, organization_id, user_id)
        outline = state["outline"]
        queries = state["section_queries"]
        retrieval = state["retrieval_by_section"]
        drafts: dict[str, str] = {}
        mv = dict(state.get("model_versions", {}))
        mv["draft"] = DEFAULT_CLAUDE_MODEL
        for sid in CC_SECTION_IDS:
            passages = retrieval.get(sid, [])
            allowed = _allowed_passage_ids(passages)
            prompt = with_variables(
                CC_DRAFT_PROMPT,
                {
                    "section_id": sid,
                    "section_query": queries[sid],
                    "outline": outline,
                    "passages_json": json.dumps(passages, default=str),
                },
            )
            draft = await llm.complete_structured(prompt, SectionDraftOutput)
            if draft.section_id != sid:
                raise ValueError("draft section_id mismatch")
            assert_citations_subset(draft.prose, allowed)
            drafts[sid] = draft.prose
        await audit.record(
            "country_conditions.draft.complete",
            organization_id,
            user_id,
            "country_conditions_memo",
            memo_id,
            metadata={"sections": list(CC_SECTION_IDS)},
        )
        await session.flush()
        return {"section_drafts": drafts, "model_versions": mv}

    async def verify_node(state: CountryConditionsState) -> dict[str, Any]:
        llm = LLMClient(session, organization_id, user_id)
        retrieval = state["retrieval_by_section"]
        section_drafts = state["section_drafts"]
        verified: dict[str, str] = {}
        mv = dict(state.get("model_versions", {}))
        mv["verify"] = DEFAULT_CLAUDE_MODEL
        for sid in CC_SECTION_IDS:
            passages = retrieval.get(sid, [])
            allowed = _allowed_passage_ids(passages)
            draft_prose = section_drafts[sid]
            prompt = with_variables(
                CC_VERIFY_PROMPT,
                {
                    "section_id": sid,
                    "draft_prose": draft_prose,
                    "passages_json": json.dumps(passages, default=str),
                },
            )
            out = await llm.complete_structured(prompt, VerifySectionOutput)
            if out.section_id != sid:
                raise ValueError("verify section_id mismatch")
            assert_citations_subset(out.revised_prose, allowed)
            verified[sid] = out.revised_prose
        await audit.record(
            "country_conditions.verify.complete",
            organization_id,
            user_id,
            "country_conditions_memo",
            memo_id,
            metadata={"sections": list(CC_SECTION_IDS)},
        )
        await session.flush()
        return {"verified_sections": verified, "model_versions": mv}

    async def synthesize_node(state: CountryConditionsState) -> dict[str, Any]:
        llm = LLMClient(session, organization_id, user_id)
        verified = state["verified_sections"]
        titles = state.get("section_titles", {})
        retrieval = state["retrieval_by_section"]
        mv = dict(state.get("model_versions", {}))
        mv["synthesize"] = DEFAULT_CLAUDE_MODEL
        prompt = with_variables(
            CC_SYNTHESIZE_PROMPT,
            {
                "verified_json": json.dumps(verified, default=str),
                "titles_json": json.dumps(titles, default=str),
            },
        )
        syn = await llm.complete_structured(prompt, SynthesizeSectionsOut)
        by_id = {s.section_id: s for s in syn.sections}
        ordered_sections: list[MemoSectionStructured] = []
        for sid in CC_SECTION_IDS:
            sec = by_id.get(sid)
            if sec is None:
                raise ValueError(f"synthesize output missing section {sid}")
            ordered_sections.append(sec)
        passage_meta = _flatten_passage_meta(retrieval)
        bib = build_bibliography(ordered_sections, passage_meta)
        final = FinalMemoStructured(sections=ordered_sections, bibliography=bib)
        await audit.record(
            "country_conditions.synthesize.complete",
            organization_id,
            user_id,
            "country_conditions_memo",
            memo_id,
            metadata={"bibliography_entries": len(bib)},
        )
        await session.flush()
        return {
            "final_memo": final.model_dump(mode="json"),
            "model_versions": mv,
        }

    builder = StateGraph(CountryConditionsState)
    builder.add_node("plan", plan_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("draft", draft_node)
    builder.add_node("verify", verify_node)
    builder.add_node("synthesize", synthesize_node)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "retrieve")
    builder.add_edge("retrieve", "draft")
    builder.add_edge("draft", "verify")
    builder.add_edge("verify", "synthesize")
    builder.add_edge("synthesize", END)
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_after=interrupt_after,
    )
