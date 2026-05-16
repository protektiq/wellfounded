"""Organization HTTP routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from audit.deps import get_audit_writer
from audit.writer import AuditWriter
from auth.deps import RequestAuth, get_request_auth, require_mfa, require_role
from db.session import get_db_session
from orgs.models import User, UserRole
from orgs.repository import OrgRepository

router = APIRouter(prefix="/orgs", tags=["orgs"])


@router.get("/admin/users")
async def list_org_users_stub(
    _mfa: Annotated[RequestAuth, Depends(require_mfa)],
    _admin: Annotated[User, Depends(require_role(UserRole.admin))],
) -> dict[str, list[dict[str, str]]]:
    return {"users": []}


@router.post("/admin/revoke-data-key", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_org_data_key(
    request: Request,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    _mfa: Annotated[RequestAuth, Depends(require_mfa)],
    _admin: Annotated[User, Depends(require_role(UserRole.admin))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> Response:
    org_id = auth.organization.id
    repo = OrgRepository(db)
    ok = await repo.revoke_data_key(org_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    rid = getattr(request.state, "request_id", None)
    metadata: dict[str, str] = {}
    if isinstance(rid, uuid.UUID):
        metadata["request_id"] = str(rid)
    await audit.record(
        "org.data_key.revoke",
        org_id,
        auth.user.id,
        "organization",
        org_id,
        metadata=metadata,
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
