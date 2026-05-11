"""Pydantic schemas for organization and user API payloads."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class UserRoleSchema(str, enum.Enum):
    admin = "admin"
    attorney = "attorney"
    paralegal = "paralegal"
    student = "student"


class UserStatusSchema(str, enum.Enum):
    invited = "invited"
    active = "active"
    suspended = "suspended"


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=128, pattern=_SLUG_PATTERN)


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    deleted_at: datetime | None
    kms_data_key_arn: str | None


class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    display_name: str = Field(min_length=1, max_length=255)
    role: UserRoleSchema
    status: UserStatusSchema


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    display_name: str
    role: UserRoleSchema
    status: UserStatusSchema
    created_at: datetime
    last_login_at: datetime | None
    deleted_at: datetime | None


class UserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    display_name: str
    role: UserRoleSchema
    status: UserStatusSchema
    created_at: datetime
