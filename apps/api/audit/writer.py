"""Append-only audit log writer bound to a request correlation id."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditLogEntry
from audit.repository import AuditRepository

_MAX_ACTION_LEN = 128
_MAX_RESOURCE_TYPE_LEN = 64
_MAX_METADATA_JSON_BYTES = 16_384


class AuditWriter:
    def __init__(self, session: AsyncSession, request_id: uuid.UUID) -> None:
        self._session = session
        self._request_id = request_id
        self._repo = AuditRepository(session)

    async def record(
        self,
        action: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID | None,
        resource_type: str,
        resource_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if (
            not isinstance(action, str)
            or len(action) == 0
            or len(action) > _MAX_ACTION_LEN
        ):
            raise ValueError("action must be a non-empty string up to 128 characters")
        if (
            not isinstance(resource_type, str)
            or len(resource_type) == 0
            or len(resource_type) > _MAX_RESOURCE_TYPE_LEN
        ):
            raise ValueError(
                "resource_type must be a non-empty string up to 64 characters",
            )
        if not isinstance(resource_id, uuid.UUID):
            raise TypeError("resource_id must be a UUID")
        if not isinstance(organization_id, uuid.UUID):
            raise TypeError("organization_id must be a UUID")
        if user_id is not None and not isinstance(user_id, uuid.UUID):
            raise TypeError("user_id must be a UUID or None")
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError("metadata must be a dict or None")

        merged: dict[str, Any] = dict(metadata) if metadata else {}
        merged["request_id"] = str(self._request_id)
        payload = json.dumps(merged, separators=(",", ":"), default=str)
        if len(payload.encode("utf-8")) > _MAX_METADATA_JSON_BYTES:
            raise ValueError("metadata JSON exceeds maximum allowed size")

        entry = AuditLogEntry(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_=merged,
        )
        await self._repo.append(entry)
