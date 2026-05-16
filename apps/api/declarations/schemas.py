"""Pydantic models for declaration API and LangGraph structured steps."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cases.models import ClaimBasis
from declarations.models import (
    DeclarationDraftStatus,
    PriorStatementType,
    SourceLanguage,
    TranscriptStatus,
)

DECLARATION_SECTION_IDS: tuple[str, ...] = (
    "identity_background",
    "past_persecution",
    "perpetrator_motivation",
    "well_founded_fear_future",
    "internal_relocation",
    "filing_bar_facts",
)

_MAX_TEXT = 500_000
_MAX_SEGMENT = 16_384
_MAX_INSTRUCTION = 8_192


class DeclarationFlagType(str, Enum):
    GAP = "GAP"
    INFERENCE = "INFERENCE"
    INCONSISTENCY = "INCONSISTENCY"
    AMBIGUITY = "AMBIGUITY"
    TRANSLATION_UNCERTAINTY = "TRANSLATION_UNCERTAINTY"


class DeclarationFlagStatus(str, Enum):
    open = "open"
    resolved = "resolved"
    deferred = "deferred"


class FlagSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]

    @field_validator("end")
    @classmethod
    def end_gte_start(cls, v: int, info: Any) -> int:
        start = info.data.get("start")
        if isinstance(start, int) and v < start:
            raise ValueError("span end must be >= start")
        return v


class DeclarationFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: DeclarationFlagType
    paragraph_id: Annotated[str, Field(min_length=1, max_length=256)]
    span: FlagSpan
    description: Annotated[str, Field(min_length=1, max_length=16_384)]
    suggested_resolution: Annotated[str, Field(min_length=1, max_length=16_384)]
    status: DeclarationFlagStatus = DeclarationFlagStatus.open
    resolved_by_user_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    resolution_note: Annotated[str | None, Field(default=None, max_length=16_384)] = None
    element_key: Annotated[str | None, Field(default=None, max_length=128)] = None
    prior_statement_id: uuid.UUID | None = None
    transcript_quote: Annotated[str | None, Field(default=None, max_length=8_192)] = None
    prior_quote: Annotated[str | None, Field(default=None, max_length=8_192)] = None


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    speaker: Annotated[str, Field(min_length=1, max_length=64)]
    source_text: Annotated[str, Field(max_length=_MAX_SEGMENT)]
    english_text: Annotated[str, Field(max_length=_MAX_SEGMENT)]


class TranscriptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_audio_id: uuid.UUID | None = None
    source_language: SourceLanguage
    segments: Annotated[list[TranscriptSegment], Field(min_length=1, max_length=10_000)]
    full_source_text: Annotated[str, Field(min_length=1, max_length=_MAX_TEXT)]
    full_english_text: Annotated[str, Field(min_length=1, max_length=_MAX_TEXT)]
    model_version: Annotated[str, Field(min_length=1, max_length=128)]
    completed_at: datetime | None = None


class TranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    interview_audio_id: uuid.UUID | None
    status: TranscriptStatus
    source_language: SourceLanguage
    segments: list[dict[str, Any]] | None
    full_source_text: str | None
    full_english_text: str | None
    model_version: str | None
    completed_at: datetime | None
    error_message: str | None = None
    created_at: datetime


class PriorStatementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement_type: PriorStatementType
    source_text: Annotated[str, Field(min_length=1, max_length=_MAX_TEXT)]
    english_text: Annotated[str, Field(min_length=1, max_length=_MAX_TEXT)]
    source_language: SourceLanguage


class PriorStatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    statement_type: PriorStatementType
    source_text: str
    english_text: str
    source_language: SourceLanguage
    uploaded_at: datetime


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_date: Annotated[str | None, Field(default=None, max_length=128)] = None
    description: Annotated[str, Field(min_length=1, max_length=16_384)]
    segment_ids: list[str] = Field(default_factory=list)


class ClaimIntermediateRepresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    biographical_data: dict[str, str] = Field(default_factory=dict)
    timeline_events: list[TimelineEvent] = Field(default_factory=list)
    identified_persecutors: list[str] = Field(default_factory=list)
    articulated_harms: list[str] = Field(default_factory=list)
    protected_ground_evidence: Annotated[str | None, Field(default=None, max_length=16_384)] = (
        None
    )
    nexus_evidence: Annotated[str | None, Field(default=None, max_length=16_384)] = None
    well_founded_fear_evidence: Annotated[str | None, Field(default=None, max_length=16_384)] = (
        None
    )
    internal_relocation_evidence: Annotated[str | None, Field(default=None, max_length=16_384)] = (
        None
    )
    one_year_filing_bar_facts: Annotated[str | None, Field(default=None, max_length=16_384)] = None
    first_incident_date: Annotated[str | None, Field(default=None, max_length=128)] = None


class ExtractOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_ir: ClaimIntermediateRepresentation


class InconsistencyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, Field(min_length=1, max_length=16_384)]
    suggested_resolution: Annotated[str, Field(min_length=1, max_length=16_384)]
    prior_statement_id: uuid.UUID
    transcript_quote: Annotated[str, Field(min_length=1, max_length=8_192)]
    prior_quote: Annotated[str, Field(min_length=1, max_length=8_192)]
    paragraph_id: Annotated[str, Field(min_length=1, max_length=256)] = "past_persecution:p0"


class InconsistencyCheckOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inconsistencies: list[InconsistencyItem] = Field(default_factory=list)


class InferenceSpanOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]
    rationale: Annotated[str, Field(min_length=1, max_length=4_096)]


class DeclarationParagraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=256)]
    text: Annotated[str, Field(min_length=1, max_length=32_768)]
    source_segment_ids: list[str] = Field(default_factory=list)
    inference_spans: list[InferenceSpanOut] = Field(default_factory=list)


class DeclarationSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    paragraphs: list[DeclarationParagraph] = Field(default_factory=list)


class DeclarationDraftContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: dict[str, DeclarationSection]

    @field_validator("sections")
    @classmethod
    def required_sections(
        cls, v: dict[str, DeclarationSection]
    ) -> dict[str, DeclarationSection]:
        for sid in DECLARATION_SECTION_IDS:
            if sid not in v:
                raise ValueError(f"missing section {sid}")
        return v


class DraftFlagOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: DeclarationFlagType
    paragraph_id: Annotated[str, Field(min_length=1, max_length=256)]
    span: FlagSpan
    description: Annotated[str, Field(min_length=1, max_length=16_384)]
    suggested_resolution: Annotated[str, Field(min_length=1, max_length=16_384)]
    element_key: Annotated[str | None, Field(default=None, max_length=128)] = None
    prior_statement_id: uuid.UUID | None = None
    transcript_quote: Annotated[str | None, Field(default=None, max_length=8_192)] = None
    prior_quote: Annotated[str | None, Field(default=None, max_length=8_192)] = None


class DraftOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: DeclarationDraftContent
    flags: list[DraftFlagOut] = Field(default_factory=list)


class ReviseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: DeclarationDraftContent
    new_flags: list[DraftFlagOut] = Field(default_factory=list)


class CaseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pseudonym: Annotated[str, Field(min_length=1, max_length=512)]
    country_code: Annotated[str, Field(min_length=2, max_length=2)]
    basis: ClaimBasis
    group_description: Annotated[str, Field(min_length=1, max_length=16_384)]


class DeclarationGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript_id: uuid.UUID
    prior_statement_ids: list[uuid.UUID] = Field(default_factory=list, max_length=32)


class DeclarationGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    version: int
    status: DeclarationDraftStatus


class DeclarationDraftSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    version: int
    status: DeclarationDraftStatus
    created_at: datetime


class DeclarationDraftDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    case_id: uuid.UUID
    version: int
    status: DeclarationDraftStatus
    transcript_id: uuid.UUID
    interview_audio_id: uuid.UUID | None
    prior_statement_ids: list[uuid.UUID]
    draft: DeclarationDraftContent | None
    flags: list[DeclarationFlag]
    claim_ir: ClaimIntermediateRepresentation | None
    created_at: datetime
    finalized_at: datetime | None
    error_message: str | None = None


class DeclarationReviseScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paragraph_id: Annotated[str | None, Field(default=None, max_length=256)] = None
    section_id: Annotated[str | None, Field(default=None, max_length=256)] = None

    @field_validator("section_id")
    @classmethod
    def scope_present(cls, v: str | None, info: Any) -> str | None:
        para = info.data.get("paragraph_id")
        if not para and not v:
            raise ValueError("paragraph_id or section_id is required")
        return v


class DeclarationReviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: Annotated[str, Field(min_length=1, max_length=_MAX_INSTRUCTION)]
    scope: DeclarationReviseScope


class DeclarationReviseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    version: int
    status: DeclarationDraftStatus


class FlagResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["resolved", "deferred"]
    resolution_note: Annotated[str | None, Field(default=None, max_length=16_384)] = None


class CleanExportBlockedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str = "Clean export blocked: unresolved required flags"
    unresolved_flag_ids: list[uuid.UUID]


_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


def normalize_country_code(v: object) -> str:
    if not isinstance(v, str):
        raise TypeError("country_code must be a string")
    s = v.strip().upper()
    if not _COUNTRY_RE.match(s):
        raise ValueError("country_code must be ISO 3166-1 alpha-2")
    return s


def paragraph_text(draft: DeclarationDraftContent, paragraph_id: str) -> str | None:
    for sec in draft.sections.values():
        for para in sec.paragraphs:
            if para.id == paragraph_id:
                return para.text
    return None


def validate_inference_flags(
    draft: DeclarationDraftContent,
    flags: list[DeclarationFlag],
) -> None:
    for f in flags:
        if f.type != DeclarationFlagType.INFERENCE:
            continue
        text = paragraph_text(draft, f.paragraph_id)
        if text is None:
            raise ValueError(f"INFERENCE flag references unknown paragraph {f.paragraph_id}")
        if f.span.end > len(text):
            raise ValueError(f"INFERENCE span out of range for {f.paragraph_id}")
