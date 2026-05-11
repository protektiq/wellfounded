"""Pydantic schemas for auth HTTP payloads."""

from __future__ import annotations

import re
import uuid

# email-validator is listed in pyproject.toml; required by pydantic.EmailStr.
from pydantic import BaseModel, EmailStr, Field, field_validator

from orgs.models import UserRole

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class MagicLinkRequest(BaseModel):
    email: EmailStr
    organization_slug: str = Field(min_length=1, max_length=128)

    @field_validator("organization_slug")
    @classmethod
    def slug_format(cls, value: str) -> str:
        stripped = value.strip().lower()
        if len(stripped) > 128:
            raise ValueError("organization_slug is too long")
        if not _SLUG_RE.fullmatch(stripped):
            raise ValueError(
                "organization_slug must be a lowercase slug "
                "(letters, digits, hyphens)",
            )
        return stripped


class OrganizationSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole


class MeResponse(BaseModel):
    user: UserSummary
    organization: OrganizationSummary
