"""Pydantic models for country conditions API and LangGraph structured steps."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cases.models import AsylumOffice, ClaimBasis
from country_conditions.models import CountryConditionsMemoStatus

CC_SECTION_IDS: tuple[str, ...] = (
    "general_conditions",
    "treatment_of_group",
    "state_actor_involvement",
    "internal_relocation",
    "recent_trends",
)

_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_MAX_GROUP = 16_384
_MAX_QUERY = 8_192
_MAX_OUTLINE = 32_768
_MAX_PROSE = 120_000
_CITE_TAG_RE = re.compile(
    r'<cite\s+passage_id="([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"\s*/>',
)


def passage_ids_in_prose(prose: str) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for m in _CITE_TAG_RE.finditer(prose):
        out.append(uuid.UUID(m.group(1)))
    return out


def assert_citations_subset(prose: str, allowed: set[uuid.UUID]) -> None:
    for pid in passage_ids_in_prose(prose):
        if pid not in allowed:
            raise ValueError(f"citation passage_id {pid} is not in retrieved passages")


class CountryConditionsInputs(BaseModel):
    """Normalized inputs stored on the memo row and passed through the graph."""

    model_config = ConfigDict(extra="forbid")

    country_code: Annotated[str, Field(min_length=2, max_length=2)]
    basis: ClaimBasis
    group_description: Annotated[str, Field(min_length=1, max_length=_MAX_GROUP)]
    timeframe_start_year: Annotated[int, Field(ge=1990, le=2100)]
    jurisdiction_asylum_office: AsylumOffice | None = None

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError("country_code must be a string")
        s = v.strip().upper()
        if not _COUNTRY_RE.match(s):
            raise ValueError("country_code must be ISO 3166-1 alpha-2")
        return s


class CountryConditionsGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country_code: Annotated[str, Field(min_length=2, max_length=2)]
    basis: ClaimBasis
    group_description: Annotated[str, Field(min_length=1, max_length=_MAX_GROUP)]
    timeframe_start_year: Annotated[int, Field(ge=1990, le=2100)]
    jurisdiction_asylum_office: AsylumOffice | None = None

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError("country_code must be a string")
        s = v.strip().upper()
        if not _COUNTRY_RE.match(s):
            raise ValueError("country_code must be ISO 3166-1 alpha-2")
        return s

    def to_inputs(self) -> CountryConditionsInputs:
        return CountryConditionsInputs(
            country_code=self.country_code,
            basis=self.basis,
            group_description=self.group_description,
            timeframe_start_year=self.timeframe_start_year,
            jurisdiction_asylum_office=self.jurisdiction_asylum_office,
        )


class CountryConditionsMemoSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    case_id: uuid.UUID
    version: int
    status: CountryConditionsMemoStatus
    generated_at: datetime | None = None


class CountryConditionsMemoDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    case_id: uuid.UUID
    version: int
    status: CountryConditionsMemoStatus
    inputs: CountryConditionsInputs
    output: dict[str, object] | None
    model_versions: dict[str, object]
    error_message: str | None
    generated_at: datetime | None = None


class CountryConditionsGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memo_id: uuid.UUID
    version: int
    status: CountryConditionsMemoStatus


class PlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outline: Annotated[str, Field(max_length=_MAX_OUTLINE)]
    section_queries: dict[
        str,
        Annotated[str, Field(min_length=1, max_length=_MAX_QUERY)],
    ]
    section_titles: dict[str, Annotated[str, Field(min_length=1, max_length=512)]]

    @field_validator("section_queries")
    @classmethod
    def keys_match_sections_queries(cls, v: dict[str, str]) -> dict[str, str]:
        keys = set(v.keys())
        required = set(CC_SECTION_IDS)
        if keys != required:
            raise ValueError(
                f"section_queries must contain exactly keys {sorted(required)}, "
                f"got {sorted(keys)}",
            )
        return v

    @field_validator("section_titles")
    @classmethod
    def keys_match_sections_titles(cls, v: dict[str, str]) -> dict[str, str]:
        keys = set(v.keys())
        required = set(CC_SECTION_IDS)
        if keys != required:
            raise ValueError(
                f"section_titles must contain exactly keys {sorted(required)}, "
                f"got {sorted(keys)}",
            )
        return v


class SectionDraftOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: Literal[
        "general_conditions",
        "treatment_of_group",
        "state_actor_involvement",
        "internal_relocation",
        "recent_trends",
    ]
    prose: Annotated[str, Field(min_length=1, max_length=_MAX_PROSE)]


ClaimSupport = Literal["supported", "partially_supported", "unsupported"]


class ClaimVerificationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_text: Annotated[str, Field(max_length=8_000)]
    support: ClaimSupport


class VerifySectionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: Literal[
        "general_conditions",
        "treatment_of_group",
        "state_actor_involvement",
        "internal_relocation",
        "recent_trends",
    ]
    revised_prose: Annotated[str, Field(min_length=1, max_length=_MAX_PROSE)]
    claims: list[ClaimVerificationEntry] = Field(default_factory=list)


class MemoSectionStructured(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: Annotated[str, Field(min_length=1, max_length=512)]
    body: Annotated[str, Field(min_length=1, max_length=_MAX_PROSE)]


class SynthesizeSectionsOut(BaseModel):
    """LLM output for the synthesize step (bibliography assembled in code)."""

    model_config = ConfigDict(extra="forbid")

    sections: list[MemoSectionStructured]


class BibliographyEntryStructured(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    passage_id: uuid.UUID
    source_title: str
    publication_date: str
    url: str
    section_anchor: str


class FinalMemoStructured(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[MemoSectionStructured]
    bibliography: list[BibliographyEntryStructured]


def timeframe_start_date(year: int) -> date:
    return date(year, 1, 1)


def build_bibliography(
    sections: list[MemoSectionStructured],
    passage_meta: dict[uuid.UUID, dict[str, str]],
) -> list[BibliographyEntryStructured]:
    """Dedupe passage ids by first appearance across bodies (stable order)."""
    ordered: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for sec in sections:
        for pid in passage_ids_in_prose(sec.body):
            if pid not in seen:
                seen.add(pid)
                ordered.append(pid)
    out: list[BibliographyEntryStructured] = []
    for i, pid in enumerate(ordered, start=1):
        meta = passage_meta.get(pid)
        if meta is None:
            raise ValueError(f"missing metadata for passage_id {pid}")
        out.append(
            BibliographyEntryStructured(
                index=i,
                passage_id=pid,
                source_title=meta["document_title"],
                publication_date=meta["publication_date"],
                url=meta["url"],
                section_anchor=meta["section_anchor"],
            ),
        )
    return out
