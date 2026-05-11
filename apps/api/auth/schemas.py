"""Pydantic schemas for auth HTTP payloads."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

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
    mfa_verified: bool
    webauthn_credential_count: int


_MAX_WEBAUTHN_CREDENTIAL_JSON_BYTES = 256 * 1024


class WebAuthnRegisterFinishRequest(BaseModel):
    friendly_name: str = Field(min_length=1, max_length=64)
    credential: dict[str, Any]

    @field_validator("credential")
    @classmethod
    def credential_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(value, separators=(",", ":"), default=str)
        if len(payload.encode("utf-8")) > _MAX_WEBAUTHN_CREDENTIAL_JSON_BYTES:
            raise ValueError("credential JSON exceeds maximum allowed size")
        return value


class WebAuthnAuthenticateFinishRequest(BaseModel):
    credential: dict[str, Any]

    @field_validator("credential")
    @classmethod
    def credential_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(value, separators=(",", ":"), default=str)
        if len(payload.encode("utf-8")) > _MAX_WEBAUTHN_CREDENTIAL_JSON_BYTES:
            raise ValueError("credential JSON exceeds maximum allowed size")
        return value
