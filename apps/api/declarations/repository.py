"""Organization-scoped persistence for declarations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cases.models import Case, CaseArtifact, CaseArtifactType
from declarations.models import (
    DeclarationDraft,
    DeclarationDraftStatus,
    PriorStatement,
    Transcript,
    TranscriptStatus,
)
from declarations.models import PriorStatementType as PriorStatementTypeOrm
from declarations.models import SourceLanguage as SourceLanguageOrm


class DeclarationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_transcript_with_artifact(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        *,
        interview_audio_id: uuid.UUID | None,
        source_language: SourceLanguageOrm,
        segments: list[dict[str, Any]],
        full_source_text: str,
        full_english_text: str,
        model_version: str,
        completed_at: datetime,
        created_by_user_id: uuid.UUID,
    ) -> Transcript:
        await self._lock_case(organization_id, case_id)
        artifact = CaseArtifact(
            id=uuid.uuid4(),
            case_id=case_id,
            artifact_type=CaseArtifactType.transcript,
        )
        self._session.add(artifact)
        await self._session.flush()
        row = Transcript(
            id=uuid.uuid4(),
            organization_id=organization_id,
            case_id=case_id,
            case_artifact_id=artifact.id,
            interview_audio_id=interview_audio_id,
            status=TranscriptStatus.complete,
            source_language=source_language,
            segments=segments,
            full_source_text=full_source_text,
            full_english_text=full_english_text,
            model_version=model_version,
            completed_at=completed_at,
            error_message=None,
            created_by_user_id=created_by_user_id,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_transcript(
        self,
        organization_id: uuid.UUID,
        transcript_id: uuid.UUID,
    ) -> Transcript | None:
        stmt = select(Transcript).where(
            Transcript.organization_id == organization_id,
            Transcript.id == transcript_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_prior_statement_with_artifact(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        *,
        statement_type: PriorStatementTypeOrm,
        source_text: str,
        english_text: str,
        source_language: SourceLanguageOrm,
        uploaded_by_user_id: uuid.UUID,
    ) -> PriorStatement:
        await self._lock_case(organization_id, case_id)
        artifact = CaseArtifact(
            id=uuid.uuid4(),
            case_id=case_id,
            artifact_type=CaseArtifactType.uploaded_file,
        )
        self._session.add(artifact)
        await self._session.flush()
        row = PriorStatement(
            id=uuid.uuid4(),
            organization_id=organization_id,
            case_id=case_id,
            case_artifact_id=artifact.id,
            statement_type=statement_type,
            source_text=source_text,
            english_text=english_text,
            source_language=source_language,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_prior_statement(
        self,
        organization_id: uuid.UUID,
        prior_id: uuid.UUID,
    ) -> PriorStatement | None:
        stmt = select(PriorStatement).where(
            PriorStatement.organization_id == organization_id,
            PriorStatement.id == prior_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all_prior_statements(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> list[PriorStatement]:
        stmt = (
            select(PriorStatement)
            .where(
                PriorStatement.organization_id == organization_id,
                PriorStatement.case_id == case_id,
            )
            .order_by(PriorStatement.uploaded_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_prior_statements_for_case(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        ids: list[uuid.UUID],
    ) -> list[PriorStatement]:
        if not ids:
            return []
        stmt = select(PriorStatement).where(
            PriorStatement.organization_id == organization_id,
            PriorStatement.case_id == case_id,
            PriorStatement.id.in_(ids),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_draft_with_artifact(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        *,
        transcript_id: uuid.UUID,
        interview_audio_id: uuid.UUID | None,
        prior_statement_ids: list[uuid.UUID],
        created_by_user_id: uuid.UUID,
        correlation_request_id: uuid.UUID | None,
    ) -> DeclarationDraft:
        await self._lock_case(organization_id, case_id)
        stmt = select(func.coalesce(func.max(DeclarationDraft.version), 0)).where(
            DeclarationDraft.organization_id == organization_id,
            DeclarationDraft.case_id == case_id,
        )
        result = await self._session.execute(stmt)
        next_version = int(result.scalar_one()) + 1

        artifact = CaseArtifact(
            id=uuid.uuid4(),
            case_id=case_id,
            artifact_type=CaseArtifactType.declaration_draft,
        )
        self._session.add(artifact)
        await self._session.flush()

        draft = DeclarationDraft(
            id=uuid.uuid4(),
            organization_id=organization_id,
            case_id=case_id,
            case_artifact_id=artifact.id,
            transcript_id=transcript_id,
            interview_audio_id=interview_audio_id,
            version=next_version,
            status=DeclarationDraftStatus.pending,
            draft=None,
            flags=[],
            prior_statement_ids=prior_statement_ids,
            claim_ir=None,
            created_by_user_id=created_by_user_id,
            finalized_at=None,
            model_versions={},
            error_message=None,
            correlation_request_id=correlation_request_id,
        )
        self._session.add(draft)
        await self._session.flush()
        return draft

    async def get_draft(
        self,
        organization_id: uuid.UUID,
        draft_id: uuid.UUID,
    ) -> DeclarationDraft | None:
        stmt = select(DeclarationDraft).where(
            DeclarationDraft.organization_id == organization_id,
            DeclarationDraft.id == draft_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_drafts_for_case(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> list[DeclarationDraft]:
        stmt = (
            select(DeclarationDraft)
            .where(
                DeclarationDraft.organization_id == organization_id,
                DeclarationDraft.case_id == case_id,
            )
            .order_by(DeclarationDraft.version.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_draft_status(
        self,
        organization_id: uuid.UUID,
        draft_id: uuid.UUID,
        status: DeclarationDraftStatus,
    ) -> None:
        stmt = (
            update(DeclarationDraft)
            .where(
                DeclarationDraft.organization_id == organization_id,
                DeclarationDraft.id == draft_id,
            )
            .values(status=status)
        )
        await self._session.execute(stmt)

    async def update_draft_complete(
        self,
        organization_id: uuid.UUID,
        draft_id: uuid.UUID,
        *,
        draft: dict[str, Any],
        flags: list[dict[str, Any]],
        claim_ir: dict[str, Any],
        status: DeclarationDraftStatus,
        model_versions: dict[str, Any],
    ) -> None:
        stmt = (
            update(DeclarationDraft)
            .where(
                DeclarationDraft.organization_id == organization_id,
                DeclarationDraft.id == draft_id,
            )
            .values(
                status=status,
                draft=draft,
                flags=flags,
                claim_ir=claim_ir,
                model_versions=model_versions,
                error_message=None,
            )
        )
        await self._session.execute(stmt)

    async def update_draft_failed(
        self,
        organization_id: uuid.UUID,
        draft_id: uuid.UUID,
        *,
        error_message: str,
    ) -> None:
        stmt = (
            update(DeclarationDraft)
            .where(
                DeclarationDraft.organization_id == organization_id,
                DeclarationDraft.id == draft_id,
            )
            .values(
                status=DeclarationDraftStatus.failed,
                error_message=error_message[:8000],
            )
        )
        await self._session.execute(stmt)

    async def update_draft_flags(
        self,
        organization_id: uuid.UUID,
        draft_id: uuid.UUID,
        *,
        flags: list[dict[str, Any]],
        status: DeclarationDraftStatus,
    ) -> None:
        stmt = (
            update(DeclarationDraft)
            .where(
                DeclarationDraft.organization_id == organization_id,
                DeclarationDraft.id == draft_id,
            )
            .values(flags=flags, status=status)
        )
        await self._session.execute(stmt)

    async def _lock_case(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> None:
        case_stmt = (
            select(Case)
            .where(
                Case.id == case_id,
                Case.organization_id == organization_id,
                Case.deleted_at.is_(None),
            )
            .with_for_update()
        )
        locked = await self._session.execute(case_stmt)
        if locked.scalar_one_or_none() is None:
            raise ValueError("case not found for organization")
