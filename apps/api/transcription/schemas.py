"""Pydantic schemas for interview upload and transcription status."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from declarations.models import SourceLanguage, TranscriptionStatus, TranscriptStatus


class InterviewUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_audio_id: uuid.UUID
    transcript_id: uuid.UUID
    status: TranscriptionStatus


class InterviewAudioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    source_filename: str
    source_language: SourceLanguage
    duration_seconds: float
    transcription_status: TranscriptionStatus
    error_message: str | None
    uploaded_at: datetime
    transcript_id: uuid.UUID | None = None


class InterviewAudioSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    source_filename: str
    source_language: SourceLanguage
    duration_seconds: float
    transcription_status: TranscriptionStatus
    uploaded_at: datetime
    transcript_id: uuid.UUID | None = None


class TranscriptStatusEnum(str, Enum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class TranscriptDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    interview_audio_id: uuid.UUID | None
    status: TranscriptStatus
    source_language: SourceLanguage
    segments: list[dict[str, object]] | None
    full_source_text: str | None
    full_english_text: str | None
    model_version: str | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
