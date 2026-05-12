"""Pydantic schemas for case file HTTP API."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cases.models import (
    AsylumOffice,
    CaseAssignmentRole,
    ClaimBasis,
)

_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_MAX_GROUP = 16_384
_MAX_INTAKE = 16_384
_MAX_ASSIGNMENT_OPS = 64


class AssignmentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    role_on_case: CaseAssignmentRole


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pseudonym: Annotated[str, Field(min_length=1, max_length=512)]
    country_code: Annotated[str, Field(min_length=2, max_length=2)]
    basis: ClaimBasis
    group_description: Annotated[str, Field(min_length=0, max_length=_MAX_GROUP)]
    filing_deadline: date | None = None
    asylum_office: AsylumOffice | None = None
    intake_notes: Annotated[str, Field(min_length=0, max_length=_MAX_INTAKE)]
    assignments: Annotated[list[AssignmentEntry], Field(min_length=1, max_length=50)]

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError("country_code must be a string")
        s = v.strip().upper()
        if not _COUNTRY_RE.match(s):
            raise ValueError("country_code must be ISO 3166-1 alpha-2")
        return s


class CaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pseudonym: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    country_code: Annotated[str, Field(min_length=2, max_length=2)] | None = None
    basis: ClaimBasis | None = None
    group_description: (
        Annotated[str, Field(min_length=0, max_length=_MAX_GROUP)] | None
    ) = None
    filing_deadline: date | None = None
    asylum_office: AsylumOffice | None = None
    intake_notes: Annotated[str, Field(min_length=0, max_length=_MAX_INTAKE)] | None = (
        None
    )

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_optional(cls, v: object) -> object:
        if v is None:
            return None
        if not isinstance(v, str):
            raise TypeError("country_code must be a string")
        s = v.strip().upper()
        if not _COUNTRY_RE.match(s):
            raise ValueError("country_code must be ISO 3166-1 alpha-2")
        return s


class AssignmentChangeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    role_on_case: CaseAssignmentRole


class CaseAssignmentsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    add: list[AssignmentChangeEntry] = Field(
        default_factory=list,
        max_length=_MAX_ASSIGNMENT_OPS,
    )
    remove: list[AssignmentChangeEntry] = Field(
        default_factory=list,
        max_length=_MAX_ASSIGNMENT_OPS,
    )


class CaseAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    role_on_case: CaseAssignmentRole
    created_at: datetime


class CaseListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    pseudonym: str
    country_code: str
    basis: ClaimBasis
    filing_deadline: date | None
    archived_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    access: Literal["full", "read_only"]
    assignments: list[CaseAssignmentOut]


class CaseDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    pseudonym: str
    country_code: str
    basis: ClaimBasis
    group_description: str
    filing_deadline: date | None
    asylum_office: AsylumOffice | None
    intake_notes: str
    created_by_user_id: uuid.UUID
    created_at: datetime
    archived_at: datetime | None
    deleted_at: datetime | None
    assignments: list[CaseAssignmentOut]
    can_edit: bool
