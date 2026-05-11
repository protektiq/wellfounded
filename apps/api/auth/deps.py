"""FastAPI dependencies for session-backed authentication."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from auth.email import ConsoleEmailSender, EmailSender, SesEmailSenderStub
from auth.models import UserSession
from auth.repository import AuthRepository
from config import Settings, get_settings
from db.session import get_db_session
from orgs.models import Organization, User, UserRole, UserStatus


@dataclass(frozen=True)
class RequestAuth:
    user: User
    session: UserSession
    organization: Organization


def get_email_sender(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmailSender:
    if settings.email_backend == "console":
        return ConsoleEmailSender()
    return SesEmailSenderStub()


async def get_request_auth(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> RequestAuth:
    raw_session_id = request.cookies.get("wf_session")
    if raw_session_id is None or not raw_session_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        session_id = uuid.UUID(raw_session_id.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        ) from None

    auth_repo = AuthRepository(db)
    sess = await auth_repo.get_user_session_by_id(session_id)
    if sess is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    stmt = (
        select(User)
        .options(joinedload(User.organization))
        .where(
            User.id == sess.user_id,
            User.organization_id == sess.organization_id,
            User.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    user = result.unique().scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    if user.status is not UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    org = user.organization
    await auth_repo.touch_user_session_seen(sess.id, sess.organization_id)
    await db.flush()

    return RequestAuth(user=user, session=sess, organization=org)


async def get_current_user(
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
) -> User:
    return auth.user


def require_role(
    *allowed: UserRole,
) -> Callable[..., Coroutine[Any, Any, User]]:
    """Dependency factory: allow only users whose role is in ``allowed``."""
    allowed_set = frozenset(allowed)

    async def _require(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _require


async def require_mfa(
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
) -> RequestAuth:
    """Admin sessions must pass WebAuthn before calling admin-gated routes."""
    if auth.user.role is UserRole.admin and auth.session.mfa_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="WebAuthn verification required for this action",
        )
    return auth
