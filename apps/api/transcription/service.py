"""Interview upload orchestration and background transcription pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import structlog
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from audit.writer import AuditWriter
from config import get_settings
from db.session import get_async_session_maker
from declarations.models import SourceLanguage
from encryption.service import (
    DataKeyRevokedError,
    decrypt_audio_from_storage,
    encrypt_audio_for_storage,
    get_envelope_crypto,
)
from orgs.repository import OrgRepository
from storage import s3_client
from storage.keys import interview_audio_storage_key
from transcription.repository import TranscriptionRepository
from transcription.validators import validate_audio_file
from transcription.whisper import (
    WhisperResult,
    transcribe_audio_file,
)
from translation.pipeline import translate_whisper_segments

log = structlog.get_logger()

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


@lru_cache
def get_transcription_service() -> TranscriptionService:
    return TranscriptionService()


class TranscriptionService:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_maker = session_maker

    def _maker(self) -> async_sessionmaker[AsyncSession]:
        if self._session_maker is not None:
            return self._session_maker
        return get_async_session_maker()

    async def upload_interview(
        self,
        *,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        source_language: SourceLanguage,
        upload: UploadFile,
        uploaded_by_user_id: uuid.UUID,
        correlation_request_id: uuid.UUID,
        session: AsyncSession,
        audit: AuditWriter,
    ) -> tuple[uuid.UUID, uuid.UUID]:
        settings = get_settings()
        org_repo = OrgRepository(session)
        if await org_repo.is_data_key_revoked(organization_id):
            raise DataKeyRevokedError("Organization data encryption key was revoked")

        filename = upload.filename or "audio.wav"
        if len(filename) > 512:
            raise ValueError("filename too long")

        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp:
            tmp_path = Path(tmp.name)
            size = 0
            hasher = hashlib.sha256()
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 200 * 1024 * 1024:
                    tmp_path.unlink(missing_ok=True)
                    raise ValueError("Audio file exceeds maximum size")
                hasher.update(chunk)
                tmp.write(chunk)

        try:
            validated = validate_audio_file(
                tmp_path,
                filename=filename,
                size_bytes=size,
            )
            plaintext = tmp_path.read_bytes()
            content_hash = hasher.hexdigest()

            repo = TranscriptionRepository(session)
            audio_id = uuid.uuid4()
            storage_key = interview_audio_storage_key(
                organization_id,
                case_id,
                audio_id,
            )

            crypto = get_envelope_crypto()
            encrypted, key_id = encrypt_audio_for_storage(
                crypto,
                organization_id,
                plaintext,
            )

            audio, transcript = await repo.create_interview_with_transcript(
                organization_id,
                case_id,
                audio_id=audio_id,
                source_filename=filename,
                source_language=source_language,
                duration_seconds=validated.duration_seconds,
                storage_key=storage_key,
                encryption_key_id=key_id,
                content_hash=content_hash,
                uploaded_by_user_id=uploaded_by_user_id,
                correlation_request_id=correlation_request_id,
            )
            await session.flush()

            s3_client.put_object(key=storage_key, body=encrypted)

            await audit.record(
                "interview.upload",
                organization_id,
                uploaded_by_user_id,
                "interview_audio",
                audio.id,
                metadata={"case_id": str(case_id), "storage_key": storage_key},
            )
            await audit.record(
                "transcript.pipeline.start",
                organization_id,
                uploaded_by_user_id,
                "transcript",
                transcript.id,
                metadata={
                    "case_id": str(case_id),
                    "interview_audio_id": str(audio.id),
                },
            )
            await session.flush()

            audio_id_final = audio.id
            transcript_id = transcript.id
            await session.commit()

            run_stub = (
                settings.transcription_e2e_stub
                and settings.environment == "local"
            )
            pipeline_coro = self._run_pipeline_background(
                organization_id=organization_id,
                case_id=case_id,
                audio_id=audio_id_final,
                transcript_id=transcript_id,
                user_id=uploaded_by_user_id,
                source_language=source_language,
                storage_key=storage_key,
                correlation_request_id=correlation_request_id,
                use_stub=run_stub,
            )
            if run_stub:
                await pipeline_coro
            else:
                asyncio.create_task(pipeline_coro)
            return audio_id_final, transcript_id
        finally:
            tmp_path.unlink(missing_ok=True)

    async def _run_pipeline_background(
        self,
        *,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        audio_id: uuid.UUID,
        transcript_id: uuid.UUID,
        user_id: uuid.UUID,
        source_language: SourceLanguage,
        storage_key: str,
        correlation_request_id: uuid.UUID,
        use_stub: bool,
    ) -> None:
        maker = self._maker()
        async with maker() as session:
            audit = AuditWriter(session, correlation_request_id)
            repo = TranscriptionRepository(session)
            org_repo = OrgRepository(session)
            try:
                if await org_repo.is_data_key_revoked(organization_id):
                    raise DataKeyRevokedError(
                        "Organization data encryption key was revoked",
                    )
                await repo.set_pipeline_processing(
                    organization_id,
                    audio_id,
                    transcript_id,
                )
                await session.commit()

                if use_stub:
                    segments, model_version = _load_stub_segments(source_language)
                else:
                    encrypted = s3_client.get_object_bytes(key=storage_key)
                    crypto = get_envelope_crypto()
                    is_revoked = await org_repo.is_data_key_revoked(organization_id)
                    plaintext = decrypt_audio_from_storage(
                        crypto,
                        organization_id,
                        encrypted,
                        is_revoked=is_revoked,
                    )
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        tmp_path = Path(tmp.name)
                        tmp_path.write_bytes(plaintext)
                    try:
                        whisper_result = transcribe_audio_file(tmp_path)
                        segments, model_version = await _segments_from_whisper(
                            session,
                            organization_id,
                            user_id,
                            whisper_result=whisper_result,
                            source_language=source_language,
                        )
                    finally:
                        tmp_path.unlink(missing_ok=True)

                full_source = " ".join(
                    str(s.get("source_text", "")) for s in segments
                ).strip()
                full_english = " ".join(
                    str(s.get("english_text", "")) for s in segments
                ).strip()
                completed_at = datetime.now(UTC)

                await repo.complete_pipeline(
                    organization_id,
                    audio_id,
                    transcript_id,
                    segments=segments,
                    full_source_text=full_source,
                    full_english_text=full_english,
                    model_version=model_version,
                    completed_at=completed_at,
                )
                await audit.record(
                    "transcript.pipeline.complete",
                    organization_id,
                    user_id,
                    "transcript",
                    transcript_id,
                    metadata={"case_id": str(case_id)},
                )
                await session.commit()
                log.info(
                    "transcription_pipeline_complete",
                    transcript_id=str(transcript_id),
                )
            except Exception as exc:
                await session.rollback()
                async with maker() as fail_session:
                    fail_repo = TranscriptionRepository(fail_session)
                    fail_audit = AuditWriter(fail_session, correlation_request_id)
                    msg = str(exc)[:16_384]
                    await fail_repo.fail_pipeline(
                        organization_id,
                        audio_id,
                        transcript_id,
                        error_message=msg,
                    )
                    await fail_audit.record(
                        "transcript.pipeline.failed",
                        organization_id,
                        user_id,
                        "transcript",
                        transcript_id,
                        metadata={"error": msg[:500]},
                    )
                    await fail_session.commit()
                log.exception(
                    "transcription_pipeline_failed",
                    transcript_id=str(transcript_id),
                )


def _load_stub_segments(
    source_language: SourceLanguage,
) -> tuple[list[dict[str, object]], str]:
    path = _FIXTURES_DIR / f"transcription_stub_{source_language.value}.json"
    if not path.is_file():
        path = _FIXTURES_DIR / "transcription_stub_es.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = data.get("segments")
    if not isinstance(segments, list):
        raise ValueError("invalid stub fixture")
    model_version = str(data.get("model_version", "transcription-stub@1"))
    return segments, model_version


async def _segments_from_whisper(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    whisper_result: WhisperResult,
    source_language: SourceLanguage,
) -> tuple[list[dict[str, object]], str]:
    if not whisper_result.segments:
        return [], whisper_result.model_version
    segments, translation_version = await translate_whisper_segments(
        session,
        organization_id,
        user_id,
        whisper_segments=whisper_result.segments,
        source_language=source_language,
    )
    model_version = f"{whisper_result.model_version};{translation_version}"
    return segments, model_version
