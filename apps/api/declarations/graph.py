"""LangGraph state machine for declaration drafting."""

from __future__ import annotations

import json
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from audit.writer import AuditWriter
from declarations.prompts import (
    DECL_DRAFT_PROMPT,
    DECL_EXTRACT_PROMPT,
    DECL_INCONSISTENCY_PROMPT,
)
from declarations.schemas import (
    CaseMetadata,
    DeclarationFlag,
    DeclarationFlagStatus,
    DeclarationFlagType,
    DraftFlagOut,
    DraftOutput,
    ExtractOutput,
    FlagSpan,
    InconsistencyCheckOutput,
)
from declarations.validators import gap_flags_from_ir
from llm.client import LLMClient
from llm.prompts import DEFAULT_CLAUDE_MODEL, with_variables


class DeclarationState(TypedDict, total=False):
    organization_id: uuid.UUID
    case_id: uuid.UUID
    draft_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    transcript: dict[str, Any]
    prior_statements: list[dict[str, Any]]
    case_metadata: dict[str, Any]
    extracted_facts: dict[str, Any]
    gap_analysis: list[dict[str, Any]]
    inconsistency_report: list[dict[str, Any]]
    draft: dict[str, Any]
    flags: list[dict[str, Any]]
    model_versions: dict[str, str]
    errors: list[str]


def _draft_flags_to_declaration(
    items: list[DraftFlagOut],
    *,
    default_status: DeclarationFlagStatus = DeclarationFlagStatus.open,
) -> list[DeclarationFlag]:
    out: list[DeclarationFlag] = []
    for item in items:
        out.append(
            DeclarationFlag(
                id=uuid.uuid4(),
                type=item.type,
                paragraph_id=item.paragraph_id,
                span=item.span,
                description=item.description,
                suggested_resolution=item.suggested_resolution,
                status=default_status,
                element_key=item.element_key,
                prior_statement_id=item.prior_statement_id,
                transcript_quote=item.transcript_quote,
                prior_quote=item.prior_quote,
            ),
        )
    return out


def _inconsistency_to_flags(report: InconsistencyCheckOutput) -> list[DeclarationFlag]:
    flags: list[DeclarationFlag] = []
    for item in report.inconsistencies:
        flags.append(
            DeclarationFlag(
                id=uuid.uuid4(),
                type=DeclarationFlagType.INCONSISTENCY,
                paragraph_id=item.paragraph_id,
                span=FlagSpan(start=0, end=0),
                description=item.description,
                suggested_resolution=item.suggested_resolution,
                prior_statement_id=item.prior_statement_id,
                transcript_quote=item.transcript_quote,
                prior_quote=item.prior_quote,
            ),
        )
    return flags


def build_declaration_graph(
    *,
    checkpointer: Any,
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    draft_id: uuid.UUID,
    audit: AuditWriter,
) -> Any:
    """Compile the declaration drafting graph."""

    async def extract_node(state: DeclarationState) -> dict[str, Any]:
        llm = LLMClient(session, organization_id, user_id)
        meta = CaseMetadata.model_validate(state["case_metadata"])
        prompt = with_variables(
            DECL_EXTRACT_PROMPT,
            {
                "case_metadata_json": meta.model_dump_json(),
                "transcript_json": json.dumps(state["transcript"], default=str),
            },
        )
        out = await llm.complete_structured(prompt, ExtractOutput)
        mv = dict(state.get("model_versions", {}))
        mv["extract"] = DEFAULT_CLAUDE_MODEL
        ir_dict = out.claim_ir.model_dump(mode="json")
        await audit.record(
            "declaration.extract.complete",
            organization_id,
            user_id,
            "declaration_draft",
            draft_id,
        )
        await session.flush()
        return {"extracted_facts": ir_dict, "model_versions": mv}

    async def gap_check_node(state: DeclarationState) -> dict[str, Any]:
        ir = state.get("extracted_facts", {})
        gap_flags = gap_flags_from_ir(ir if isinstance(ir, dict) else {})
        gap_list = [f.model_dump(mode="json") for f in gap_flags]
        await audit.record(
            "declaration.gap_check.complete",
            organization_id,
            user_id,
            "declaration_draft",
            draft_id,
            metadata={"gap_count": len(gap_list)},
        )
        await session.flush()
        return {"gap_analysis": gap_list}

    async def inconsistency_check_node(state: DeclarationState) -> dict[str, Any]:
        priors = state.get("prior_statements", [])
        if not priors:
            await audit.record(
                "declaration.inconsistency_check.skipped",
                organization_id,
                user_id,
                "declaration_draft",
                draft_id,
            )
            await session.flush()
            return {"inconsistency_report": []}

        llm = LLMClient(session, organization_id, user_id)
        ir = state.get("extracted_facts", {})
        prompt = with_variables(
            DECL_INCONSISTENCY_PROMPT,
            {
                "claim_ir_json": json.dumps(ir, default=str),
                "prior_statements_json": json.dumps(priors, default=str),
            },
        )
        out = await llm.complete_structured(prompt, InconsistencyCheckOutput)
        flags = _inconsistency_to_flags(out)
        report = [f.model_dump(mode="json") for f in flags]
        mv = dict(state.get("model_versions", {}))
        mv["inconsistency_check"] = DEFAULT_CLAUDE_MODEL
        await audit.record(
            "declaration.inconsistency_check.complete",
            organization_id,
            user_id,
            "declaration_draft",
            draft_id,
            metadata={"inconsistency_count": len(report)},
        )
        await session.flush()
        return {"inconsistency_report": report, "model_versions": mv}

    async def compose_draft_node(state: DeclarationState) -> dict[str, Any]:
        llm = LLMClient(session, organization_id, user_id)
        meta = CaseMetadata.model_validate(state["case_metadata"])
        ir = state.get("extracted_facts", {})
        existing = list(state.get("gap_analysis", [])) + list(
            state.get("inconsistency_report", []),
        )
        prompt = with_variables(
            DECL_DRAFT_PROMPT,
            {
                "case_metadata_json": meta.model_dump_json(),
                "claim_ir_json": json.dumps(ir, default=str),
                "transcript_json": json.dumps(state["transcript"], default=str),
                "existing_flags_json": json.dumps(existing, default=str),
            },
        )
        out = await llm.complete_structured(prompt, DraftOutput)
        draft_dict = out.draft.model_dump(mode="json")
        llm_flags = _draft_flags_to_declaration(out.flags)
        merged: list[DeclarationFlag] = []
        for raw in existing:
            merged.append(DeclarationFlag.model_validate(raw))
        merged.extend(llm_flags)
        flags_list = [f.model_dump(mode="json") for f in merged]
        mv = dict(state.get("model_versions", {}))
        mv["draft"] = DEFAULT_CLAUDE_MODEL
        await audit.record(
            "declaration.draft.complete",
            organization_id,
            user_id,
            "declaration_draft",
            draft_id,
            metadata={"flag_count": len(flags_list)},
        )
        await session.flush()
        return {
            "draft": draft_dict,
            "flags": flags_list,
            "model_versions": mv,
        }

    builder = StateGraph(DeclarationState)
    builder.add_node("extract", extract_node)
    builder.add_node("gap_check", gap_check_node)
    builder.add_node("inconsistency_check", inconsistency_check_node)
    builder.add_node("compose_draft", compose_draft_node)
    builder.add_edge(START, "extract")
    builder.add_edge("extract", "gap_check")
    builder.add_edge("gap_check", "inconsistency_check")
    builder.add_edge("inconsistency_check", "compose_draft")
    builder.add_edge("compose_draft", END)
    return builder.compile(checkpointer=checkpointer)
