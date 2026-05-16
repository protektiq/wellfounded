"""Orchestration for declaration drafting."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from audit.writer import AuditWriter
from cases.models import Case
from cases.repository import CaseRepository
from config import get_settings
from db.session import get_async_session_maker
from declarations.flags import (
    flags_from_dicts,
    flags_to_dicts,
    merge_flags_on_revise,
    status_after_flags,
    validate_flags,
)
from declarations.graph import build_declaration_graph
from declarations.models import DeclarationDraftStatus
from declarations.prompts import DECL_REVISE_PROMPT
from declarations.repository import DeclarationsRepository
from declarations.schemas import (
    CaseMetadata,
    ClaimIntermediateRepresentation,
    DeclarationDraftContent,
    DeclarationDraftDetail,
    DeclarationFlag,
    DeclarationFlagStatus,
    DeclarationReviseScope,
    ReviseOutput,
)
from declarations.validators import validate_declaration_output
from llm.client import LLMClient
from llm.prompts import DEFAULT_CLAUDE_MODEL, with_variables

log = structlog.get_logger()


class DeclarationsService:
    """Schedules declaration LangGraph runs and scoped revisions."""

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_maker = session_maker

    def _maker(self) -> async_sessionmaker[AsyncSession]:
        if self._session_maker is not None:
            return self._session_maker
        return get_async_session_maker()

    @staticmethod
    def _case_metadata(case: Case) -> CaseMetadata:
        return CaseMetadata(
            pseudonym=case.pseudonym,
            country_code=case.country_code.upper(),
            basis=case.basis,
            group_description=case.group_description,
        )

    @staticmethod
    def _transcript_payload(transcript: Any) -> dict[str, Any]:
        segments = transcript.segments
        return {
            "source_language": transcript.source_language.value,
            "segments": segments,
            "full_english_text": transcript.full_english_text,
            "full_source_text": transcript.full_source_text,
        }

    @staticmethod
    def _prior_payload(row: Any) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "statement_type": row.statement_type.value,
            "english_text": row.english_text,
            "source_text": row.source_text,
        }

    async def generate(
        self,
        *,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        transcript_id: uuid.UUID,
        prior_statement_ids: list[uuid.UUID],
        requested_by_user_id: uuid.UUID,
        correlation_request_id: uuid.UUID,
        session: AsyncSession,
        audit: AuditWriter,
    ) -> tuple[uuid.UUID, int]:
        case_repo = CaseRepository(session)
        case = await case_repo.get_case_for_org(organization_id, case_id)
        if case is None:
            raise ValueError("Case not found")

        decl_repo = DeclarationsRepository(session)
        transcript = await decl_repo.get_transcript(organization_id, transcript_id)
        if transcript is None or transcript.case_id != case_id:
            raise ValueError("Transcript not found")
        from declarations.models import TranscriptStatus

        if transcript.status is not TranscriptStatus.complete:
            raise ValueError("Transcript is not ready")
        if transcript.segments is None or transcript.full_english_text is None:
            raise ValueError("Transcript is not ready")

        priors = await decl_repo.list_prior_statements_for_case(
            organization_id,
            case_id,
            prior_statement_ids,
        )
        if len(priors) != len(prior_statement_ids):
            raise ValueError("One or more prior statements not found for case")

        draft = await decl_repo.create_draft_with_artifact(
            organization_id,
            case_id,
            transcript_id=transcript_id,
            interview_audio_id=transcript.interview_audio_id,
            prior_statement_ids=prior_statement_ids,
            created_by_user_id=requested_by_user_id,
            correlation_request_id=correlation_request_id,
        )
        await audit.record(
            "declaration.generate.start",
            organization_id,
            requested_by_user_id,
            "declaration_draft",
            draft.id,
            metadata={"case_id": str(case_id), "version": draft.version},
        )
        await session.flush()

        draft_id = draft.id
        version = draft.version
        meta = self._case_metadata(case)
        transcript_payload = self._transcript_payload(transcript)
        prior_payloads = [self._prior_payload(p) for p in priors]
        await session.commit()

        asyncio.create_task(
            self._run_graph_background(
                organization_id=organization_id,
                case_id=case_id,
                draft_id=draft_id,
                user_id=requested_by_user_id,
                correlation_request_id=correlation_request_id,
                case_metadata=meta.model_dump(mode="json"),
                transcript=transcript_payload,
                prior_statements=prior_payloads,
            ),
        )
        log.info(
            "declaration_generation_scheduled",
            draft_id=str(draft_id),
            case_id=str(case_id),
        )
        return draft_id, version

    async def revise(
        self,
        *,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        parent_draft_id: uuid.UUID,
        instruction: str,
        scope: DeclarationReviseScope,
        requested_by_user_id: uuid.UUID,
        correlation_request_id: uuid.UUID,
        session: AsyncSession,
        audit: AuditWriter,
    ) -> tuple[uuid.UUID, int, DeclarationDraftStatus]:
        decl_repo = DeclarationsRepository(session)
        parent = await decl_repo.get_draft(organization_id, parent_draft_id)
        if parent is None or parent.case_id != case_id:
            raise ValueError("Draft not found")
        if parent.draft is None or parent.claim_ir is None:
            raise ValueError("Parent draft is not complete")

        new_row = await decl_repo.create_draft_with_artifact(
            organization_id,
            case_id,
            transcript_id=parent.transcript_id,
            interview_audio_id=parent.interview_audio_id,
            prior_statement_ids=list(parent.prior_statement_ids),
            created_by_user_id=requested_by_user_id,
            correlation_request_id=correlation_request_id,
        )
        await decl_repo.update_draft_status(
            organization_id,
            new_row.id,
            DeclarationDraftStatus.generating,
        )

        parent_flags = flags_from_dicts(list(parent.flags))
        claim_ir = ClaimIntermediateRepresentation.model_validate(parent.claim_ir)

        llm = LLMClient(session, organization_id, requested_by_user_id)
        prompt = with_variables(
            DECL_REVISE_PROMPT,
            {
                "instruction": instruction,
                "paragraph_id": scope.paragraph_id or "",
                "section_id": scope.section_id or "",
                "draft_json": json.dumps(parent.draft, default=str),
                "claim_ir_json": claim_ir.model_dump_json(),
                "flags_json": json.dumps(
                    [f.model_dump(mode="json") for f in parent_flags],
                    default=str,
                ),
            },
        )
        revise_out = await llm.complete_structured(prompt, ReviseOutput)
        new_llm_flags = [
            DeclarationFlag(
                id=uuid.uuid4(),
                type=f.type,
                paragraph_id=f.paragraph_id,
                span=f.span,
                description=f.description,
                suggested_resolution=f.suggested_resolution,
                element_key=f.element_key,
                prior_statement_id=f.prior_statement_id,
                transcript_quote=f.transcript_quote,
                prior_quote=f.prior_quote,
            )
            for f in revise_out.new_flags
        ]
        merged_flags = merge_flags_on_revise(parent_flags, new_llm_flags, scope)
        final_draft = revise_out.draft
        validate_declaration_output(final_draft, merged_flags)
        validate_flags(merged_flags)
        st = DeclarationDraftStatus(status_after_flags(merged_flags))

        await decl_repo.update_draft_complete(
            organization_id,
            new_row.id,
            draft=final_draft.model_dump(mode="json"),
            flags=flags_to_dicts(merged_flags),
            claim_ir=claim_ir.model_dump(mode="json"),
            status=st,
            model_versions={"revise": DEFAULT_CLAUDE_MODEL},
        )
        await audit.record(
            "declaration.revise",
            organization_id,
            requested_by_user_id,
            "declaration_draft",
            new_row.id,
            metadata={
                "parent_draft_id": str(parent_draft_id),
                "version": new_row.version,
            },
        )
        await session.flush()
        return new_row.id, new_row.version, st

    async def resolve_flag(
        self,
        *,
        organization_id: uuid.UUID,
        draft_id: uuid.UUID,
        flag_id: uuid.UUID,
        status: DeclarationFlagStatus,
        resolution_note: str | None,
        user_id: uuid.UUID,
        session: AsyncSession,
        audit: AuditWriter,
    ) -> DeclarationDraftStatus:
        from datetime import UTC, datetime

        decl_repo = DeclarationsRepository(session)
        draft = await decl_repo.get_draft(organization_id, draft_id)
        if draft is None:
            raise ValueError("Draft not found")

        flags = flags_from_dicts(list(draft.flags))
        found = False
        now = datetime.now(UTC)
        for f in flags:
            if f.id != flag_id:
                continue
            found = True
            f.status = status
            f.resolved_by_user_id = user_id
            f.resolved_at = now
            f.resolution_note = resolution_note
        if not found:
            raise ValueError("Flag not found")

        st = DeclarationDraftStatus(status_after_flags(flags))
        await decl_repo.update_draft_flags(
            organization_id,
            draft_id,
            flags=flags_to_dicts(flags),
            status=st,
        )
        await audit.record(
            "declaration.flag.resolve",
            organization_id,
            user_id,
            "declaration_draft",
            draft_id,
            metadata={"flag_id": str(flag_id), "status": status.value},
        )
        await session.flush()
        return st

    @staticmethod
    def draft_to_detail(row: Any) -> DeclarationDraftDetail:
        draft_content: DeclarationDraftContent | None = None
        if row.draft is not None:
            draft_content = DeclarationDraftContent.model_validate(row.draft)
        claim_ir: ClaimIntermediateRepresentation | None = None
        if row.claim_ir is not None:
            claim_ir = ClaimIntermediateRepresentation.model_validate(row.claim_ir)
        return DeclarationDraftDetail(
            id=row.id,
            case_id=row.case_id,
            version=row.version,
            status=row.status,
            transcript_id=row.transcript_id,
            interview_audio_id=row.interview_audio_id,
            prior_statement_ids=list(row.prior_statement_ids),
            draft=draft_content,
            flags=flags_from_dicts(list(row.flags)),
            claim_ir=claim_ir,
            created_at=row.created_at,
            finalized_at=row.finalized_at,
            error_message=row.error_message,
        )

    async def _run_graph_background(
        self,
        *,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        draft_id: uuid.UUID,
        user_id: uuid.UUID,
        correlation_request_id: uuid.UUID,
        case_metadata: dict[str, Any],
        transcript: dict[str, Any],
        prior_statements: list[dict[str, Any]],
    ) -> None:
        settings = get_settings()
        uri = settings.resolved_checkpoint_database_url()
        maker = self._maker()
        stub_local = (
            settings.declaration_e2e_stub
            and settings.environment.strip().lower() == "local"
        )
        structlog.contextvars.bind_contextvars(
            organization_id=str(organization_id),
            user_id=str(user_id),
        )
        try:
            async with maker() as session:
                audit = AuditWriter(session, correlation_request_id)
                repo = DeclarationsRepository(session)
                try:
                    await repo.update_draft_status(
                        organization_id,
                        draft_id,
                        DeclarationDraftStatus.generating,
                    )
                    await session.flush()

                    if stub_local:
                        from declarations.e2e_stub import e2e_stub_declaration_payload

                        payload = e2e_stub_declaration_payload()
                        flags = flags_from_dicts(payload["flags"])
                        st = DeclarationDraftStatus(status_after_flags(flags))
                        await repo.update_draft_complete(
                            organization_id,
                            draft_id,
                            draft=payload["draft"],
                            flags=payload["flags"],
                            claim_ir=payload["claim_ir"],
                            status=st,
                            model_versions=payload["model_versions"],
                        )
                        await audit.record(
                            "declaration.generate.complete",
                            organization_id,
                            user_id,
                            "declaration_draft",
                            draft_id,
                            metadata={"case_id": str(case_id), "e2e_stub": True},
                        )
                        await session.commit()
                        return

                    async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
                        await checkpointer.setup()
                        graph = build_declaration_graph(
                            checkpointer=checkpointer,
                            session=session,
                            organization_id=organization_id,
                            user_id=user_id,
                            draft_id=draft_id,
                            audit=audit,
                        )
                        init: dict[str, Any] = {
                            "organization_id": organization_id,
                            "case_id": case_id,
                            "draft_id": draft_id,
                            "requested_by_user_id": user_id,
                            "case_metadata": case_metadata,
                            "transcript": transcript,
                            "prior_statements": prior_statements,
                            "model_versions": {},
                        }
                        final_state = await graph.ainvoke(
                            init,
                            {"configurable": {"thread_id": str(draft_id)}},
                        )

                    draft_raw = final_state.get("draft")
                    flags_raw = final_state.get("flags", [])
                    ir_raw = final_state.get("extracted_facts")
                    model_versions = final_state.get("model_versions", {})
                    if not isinstance(draft_raw, dict) or not isinstance(ir_raw, dict):
                        raise RuntimeError("graph finished without draft or IR")

                    draft_content = DeclarationDraftContent.model_validate(draft_raw)
                    flags = flags_from_dicts(
                        flags_raw if isinstance(flags_raw, list) else [],
                    )
                    validate_declaration_output(draft_content, flags)
                    validate_flags(flags)
                    st = DeclarationDraftStatus(status_after_flags(flags))

                    await repo.update_draft_complete(
                        organization_id,
                        draft_id,
                        draft=draft_content.model_dump(mode="json"),
                        flags=flags_to_dicts(flags),
                        claim_ir=ir_raw,
                        status=st,
                        model_versions=model_versions,
                    )
                    await audit.record(
                        "declaration.generate.complete",
                        organization_id,
                        user_id,
                        "declaration_draft",
                        draft_id,
                        metadata={"case_id": str(case_id), "flag_count": len(flags)},
                    )
                    await session.commit()
                except Exception as exc:
                    await session.rollback()
                    async with maker() as err_session:
                        err_repo = DeclarationsRepository(err_session)
                        err_audit = AuditWriter(err_session, correlation_request_id)
                        await err_repo.update_draft_failed(
                            organization_id,
                            draft_id,
                            error_message=str(exc),
                        )
                        await err_audit.record(
                            "declaration.generate.failed",
                            organization_id,
                            user_id,
                            "declaration_draft",
                            draft_id,
                            metadata={"error": str(exc)[:500]},
                        )
                        await err_session.commit()
                    log.exception("declaration_generation_failed", draft_id=str(draft_id))
        finally:
            structlog.contextvars.unbind_contextvars("organization_id", "user_id")


_service: DeclarationsService | None = None


def get_declarations_service() -> DeclarationsService:
    global _service
    if _service is None:
        _service = DeclarationsService()
    return _service
