"""FastAPI dependencies for audit logging."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from audit.writer import AuditWriter
from db.session import get_db_session


async def get_audit_writer(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> AsyncIterator[AuditWriter]:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request context was not initialized (missing request_id).",
        )
    yield AuditWriter(db, request_id)
