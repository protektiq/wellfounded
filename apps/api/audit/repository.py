"""Async persistence for audit log entries (append-only reads and inserts)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditLogEntry


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, entry: AuditLogEntry) -> None:
        self._session.add(entry)
        await self._session.flush()

    async def list_for_organization(
        self,
        organization_id: uuid.UUID,
        *,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[AuditLogEntry]:
        stmt = select(AuditLogEntry).where(
            AuditLogEntry.organization_id == organization_id,
        )
        if created_after is not None:
            stmt = stmt.where(AuditLogEntry.created_at >= created_after)
        if created_before is not None:
            stmt = stmt.where(AuditLogEntry.created_at <= created_before)
        stmt = stmt.order_by(AuditLogEntry.created_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
