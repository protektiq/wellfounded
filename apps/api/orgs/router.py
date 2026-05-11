"""Organization HTTP routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from auth.deps import RequestAuth, require_mfa, require_role
from orgs.models import User, UserRole

router = APIRouter(prefix="/orgs", tags=["orgs"])


@router.get("/admin/users")
async def list_org_users_stub(
    _mfa: Annotated[RequestAuth, Depends(require_mfa)],
    _admin: Annotated[User, Depends(require_role(UserRole.admin))],
) -> dict[str, list[dict[str, str]]]:
    return {"users": []}
