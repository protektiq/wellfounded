"""ORM for transcripts, prior statements, and declaration drafts."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SourceLanguage(str, enum.Enum):
    es = "es"
    zh = "zh"
    fr = "fr"
    ht = "ht"
    ti = "ti"
    prs = "prs"


class PriorStatementType(str, enum.Enum):
    credible_fear_interview = "credible_fear_interview"
    airport_statement = "airport_statement"
    prior_filing = "prior_filing"


class DeclarationDraftStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    draft_ready = "draft_ready"
    flags_unresolved = "flags_unresolved"
    ready_for_review = "ready_for_review"
    finalized = "finalized"
    failed = "failed"


class TranscriptStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class TranscriptionStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class Transcript(Base):
    __tablename__ = "transcripts"
    __table_args__ = (
        Index("ix_transcripts_organization_id", "organization_id"),
        Index("ix_transcripts_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_artifact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    interview_audio_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("interview_audio.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[TranscriptStatus] = mapped_column(
        SAEnum(TranscriptStatus, name="transcriptstatus", native_enum=True),
        nullable=False,
        server_default=TranscriptStatus.complete.value,
    )
    source_language: Mapped[SourceLanguage] = mapped_column(
        SAEnum(SourceLanguage, name="sourcelanguage", native_enum=True),
        nullable=False,
    )
    segments: Mapped[list[object] | None] = mapped_column(JSONB, nullable=True)
    full_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_english_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PriorStatement(Base):
    __tablename__ = "prior_statements"
    __table_args__ = (
        Index("ix_prior_statements_organization_id", "organization_id"),
        Index("ix_prior_statements_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_artifact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    statement_type: Mapped[PriorStatementType] = mapped_column(
        SAEnum(PriorStatementType, name="priorstatementtype", native_enum=True),
        nullable=False,
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    english_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_language: Mapped[SourceLanguage] = mapped_column(
        SAEnum(SourceLanguage, name="sourcelanguage", native_enum=False),
        nullable=False,
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DeclarationDraft(Base):
    __tablename__ = "declaration_drafts"
    __table_args__ = (
        Index("ix_declaration_drafts_organization_id", "organization_id"),
        Index("ix_declaration_drafts_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_artifact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    interview_audio_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DeclarationDraftStatus] = mapped_column(
        SAEnum(
            DeclarationDraftStatus,
            name="declarationdraftstatus",
            native_enum=True,
        ),
        nullable=False,
    )
    draft: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    flags: Mapped[list[object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    prior_statement_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    )
    claim_ir: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    model_versions: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
