"""Organization-scoped persistence for interview audio and pipeline transcripts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cases.models import Case, CaseArtifact, CaseArtifactType
from declarations.models import (
    SourceLanguage,
    Transcript,
    TranscriptionStatus,
    TranscriptStatus,
)
from transcription.models import InterviewAudio


class TranscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _lock_case(self, organization_id: uuid.UUID, case_id: uuid.UUID) -> None:
        stmt = (
            select(Case.id)
            .where(
                Case.organization_id == organization_id,
                Case.id == case_id,
                Case.deleted_at.is_(None),
            )
            .with_for_update()
        )
        result = await self._session.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise ValueError("Case not found")

    async def create_interview_with_transcript(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        *,
        audio_id: uuid.UUID,
        source_filename: str,
        source_language: SourceLanguage,
        duration_seconds: float,
        storage_key: str,
        encryption_key_id: str,
        content_hash: str,
        uploaded_by_user_id: uuid.UUID,
        correlation_request_id: uuid.UUID | None,
    ) -> tuple[InterviewAudio, Transcript]:
        await self._lock_case(organization_id, case_id)
        audio_artifact = CaseArtifact(
            id=uuid.uuid4(),
            case_id=case_id,
            artifact_type=CaseArtifactType.interview_audio,
        )
        self._session.add(audio_artifact)
        await self._session.flush()

        audio = InterviewAudio(
            id=audio_id,
            organization_id=organization_id,
            case_id=case_id,
            case_artifact_id=audio_artifact.id,
            source_filename=source_filename,
            source_language=source_language,
            duration_seconds=duration_seconds,
            storage_key=storage_key,
            encryption_key_id=encryption_key_id,
            content_hash=content_hash,
            uploaded_by_user_id=uploaded_by_user_id,
            transcription_status=TranscriptionStatus.pending,
            error_message=None,
            correlation_request_id=correlation_request_id,
        )
        self._session.add(audio)
        await self._session.flush()

        tx_artifact = CaseArtifact(
            id=uuid.uuid4(),
            case_id=case_id,
            artifact_type=CaseArtifactType.transcript,
        )
        self._session.add(tx_artifact)
        await self._session.flush()

        transcript = Transcript(
            id=uuid.uuid4(),
            organization_id=organization_id,
            case_id=case_id,
            case_artifact_id=tx_artifact.id,
            interview_audio_id=audio.id,
            status=TranscriptStatus.pending,
            source_language=source_language,
            segments=None,
            full_source_text=None,
            full_english_text=None,
            model_version=None,
            completed_at=None,
            error_message=None,
            created_by_user_id=uploaded_by_user_id,
        )
        self._session.add(transcript)
        await self._session.flush()
        return audio, transcript

    async def get_interview_audio(
        self,
        organization_id: uuid.UUID,
        audio_id: uuid.UUID,
    ) -> InterviewAudio | None:
        stmt = select(InterviewAudio).where(
            InterviewAudio.organization_id == organization_id,
            InterviewAudio.id == audio_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_interview_audio_for_case(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> list[InterviewAudio]:
        stmt = (
            select(InterviewAudio)
            .where(
                InterviewAudio.organization_id == organization_id,
                InterviewAudio.case_id == case_id,
            )
            .order_by(InterviewAudio.uploaded_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_interview_audio_for_case(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        audio_id: uuid.UUID,
    ) -> InterviewAudio | None:
        stmt = select(InterviewAudio).where(
            InterviewAudio.organization_id == organization_id,
            InterviewAudio.case_id == case_id,
            InterviewAudio.id == audio_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_transcript_for_audio(
        self,
        organization_id: uuid.UUID,
        interview_audio_id: uuid.UUID,
    ) -> Transcript | None:
        stmt = select(Transcript).where(
            Transcript.organization_id == organization_id,
            Transcript.interview_audio_id == interview_audio_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

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

    async def set_pipeline_processing(
        self,
        organization_id: uuid.UUID,
        audio_id: uuid.UUID,
        transcript_id: uuid.UUID,
    ) -> None:
        await self._session.execute(
            update(InterviewAudio)
            .where(
                InterviewAudio.organization_id == organization_id,
                InterviewAudio.id == audio_id,
            )
            .values(transcription_status=TranscriptionStatus.processing),
        )
        await self._session.execute(
            update(Transcript)
            .where(
                Transcript.organization_id == organization_id,
                Transcript.id == transcript_id,
            )
            .values(status=TranscriptStatus.processing),
        )

    async def complete_pipeline(
        self,
        organization_id: uuid.UUID,
        audio_id: uuid.UUID,
        transcript_id: uuid.UUID,
        *,
        segments: list[dict[str, Any]],
        full_source_text: str,
        full_english_text: str,
        model_version: str,
        completed_at: datetime,
    ) -> None:
        await self._session.execute(
            update(InterviewAudio)
            .where(
                InterviewAudio.organization_id == organization_id,
                InterviewAudio.id == audio_id,
            )
            .values(
                transcription_status=TranscriptionStatus.complete,
                error_message=None,
            ),
        )
        await self._session.execute(
            update(Transcript)
            .where(
                Transcript.organization_id == organization_id,
                Transcript.id == transcript_id,
            )
            .values(
                status=TranscriptStatus.complete,
                segments=segments,
                full_source_text=full_source_text,
                full_english_text=full_english_text,
                model_version=model_version,
                completed_at=completed_at,
                error_message=None,
            ),
        )

    async def fail_pipeline(
        self,
        organization_id: uuid.UUID,
        audio_id: uuid.UUID,
        transcript_id: uuid.UUID,
        *,
        error_message: str,
    ) -> None:
        await self._session.execute(
            update(InterviewAudio)
            .where(
                InterviewAudio.organization_id == organization_id,
                InterviewAudio.id == audio_id,
            )
            .values(
                transcription_status=TranscriptionStatus.failed,
                error_message=error_message[:16_384],
            ),
        )
        await self._session.execute(
            update(Transcript)
            .where(
                Transcript.organization_id == organization_id,
                Transcript.id == transcript_id,
            )
            .values(
                status=TranscriptStatus.failed,
                error_message=error_message[:16_384],
            ),
        )
