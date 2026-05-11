"""HTTP routes for magic-link sign-in and session management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.deps import get_audit_writer
from audit.writer import AuditWriter
from auth.deps import RequestAuth, get_email_sender, get_request_auth
from auth.email import EmailSender
from auth.models import MagicLinkToken
from auth.repository import AuthRepository
from auth.schemas import MagicLinkRequest, MeResponse, OrganizationSummary, UserSummary
from auth.sessions import build_user_session
from auth.tokens import generate_raw_token, hash_token
from config import Settings, get_settings
from db.session import get_db_session
from orgs.models import User, UserStatus
from orgs.repository import OrgRepository

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE_NAME = "wf_session"
_MAX_RAW_TOKEN_LEN = 512


def _session_cookie_secure(settings: Settings) -> bool:
    return settings.environment.strip().lower() != "local"


_SESSION_MAX_AGE_SECONDS = 30 * 24 * 3600


def _redirect_with_error(settings: Settings, error_code: str) -> RedirectResponse:
    base = settings.public_app_url
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}error={error_code}"
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.post("/magic-link", status_code=status.HTTP_204_NO_CONTENT)
async def request_magic_link(
    body: MagicLinkRequest,
    db: AsyncSession = Depends(get_db_session),
    audit: AuditWriter = Depends(get_audit_writer),
    sender: EmailSender = Depends(get_email_sender),
    settings: Settings = Depends(get_settings),
) -> Response:
    org_repo = OrgRepository(db)
    auth_repo = AuthRepository(db)
    email_norm = str(body.email).strip().lower()

    org = await org_repo.get_org_by_slug(body.organization_slug)
    if org is None:
        log.warning(
            "magic_link_unknown_organization",
            organization_slug=body.organization_slug,
        )
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    user = await org_repo.get_user_by_email(email_norm, org.id)
    audit_resource_id = uuid.uuid4()
    await audit.record(
        "auth.magic_link.request",
        org.id,
        user.id if user is not None else None,
        "auth_magic_link",
        audit_resource_id,
        metadata={
            "organization_slug": body.organization_slug,
            "user_found": user is not None,
            "user_active": user is not None and user.status is UserStatus.active,
        },
    )

    if user is not None and user.status is UserStatus.active:
        raw = generate_raw_token()
        digest = hash_token(raw)
        ttl = settings.magic_link_ttl_seconds
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
        token_row = MagicLinkToken(
            id=uuid.uuid4(),
            user_id=user.id,
            organization_id=org.id,
            token_hash=digest,
            expires_at=expires_at,
            consumed_at=None,
        )
        await auth_repo.insert_magic_link_token(token_row)
        callback = f"{settings.api_public_url}/auth/callback?token={raw}"
        await sender.send_magic_link(
            to_email=user.email,
            magic_link_url=callback,
            organization_name=org.name,
        )

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/callback", status_code=status.HTTP_302_FOUND)
async def magic_link_callback(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db_session),
    audit: AuditWriter = Depends(get_audit_writer),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if len(token) > _MAX_RAW_TOKEN_LEN:
        return _redirect_with_error(settings, "invalid_token")

    digest = hash_token(token)
    auth_repo = AuthRepository(db)
    org_repo = OrgRepository(db)
    now = datetime.now(UTC)

    row = await auth_repo.get_magic_link_by_hash_any_org(digest)
    if row is None:
        await db.commit()
        return _redirect_with_error(settings, "invalid_token")

    if row.consumed_at is not None or row.expires_at <= now:
        await db.commit()
        return _redirect_with_error(settings, "invalid_token")

    uresult = await db.execute(
        select(User).where(
            User.id == row.user_id,
            User.organization_id == row.organization_id,
            User.deleted_at.is_(None),
        ),
    )
    user = uresult.scalar_one_or_none()
    if user is None or user.status is not UserStatus.active:
        await db.commit()
        return _redirect_with_error(settings, "invalid_token")

    org = await org_repo.get_organization_by_id(row.organization_id)
    if org is None:
        await db.commit()
        return _redirect_with_error(settings, "invalid_token")

    consumed = await auth_repo.consume_magic_link_if_valid(row.id, now=now)
    if not consumed:
        await db.commit()
        return _redirect_with_error(settings, "invalid_token")

    ua = request.headers.get("user-agent")
    if ua is not None and len(ua) > 512:
        ua = ua[:512]
    client = request.client
    ip_raw = client.host if client is not None else None
    ip_addr: str | None
    if ip_raw is None:
        ip_addr = None
    elif len(ip_raw) <= 45:
        ip_addr = ip_raw
    else:
        ip_addr = ip_raw[:45]

    session_row = build_user_session(
        user_id=user.id,
        organization_id=user.organization_id,
        user_agent=ua,
        ip_addr=ip_addr,
    )
    await auth_repo.insert_user_session(session_row)

    user.last_login_at = now

    await audit.record(
        "auth.magic_link.consume",
        user.organization_id,
        user.id,
        "session",
        session_row.id,
        metadata={"magic_link_token_id": str(row.id)},
    )
    await db.commit()

    resp = RedirectResponse(
        url=settings.public_app_url,
        status_code=status.HTTP_302_FOUND,
    )
    resp.set_cookie(
        SESSION_COOKIE_NAME,
        str(session_row.id),
        httponly=True,
        samesite="lax",
        secure=_session_cookie_secure(settings),
        max_age=_SESSION_MAX_AGE_SECONDS,
        path="/",
    )
    return resp


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    auth_ctx: Annotated[RequestAuth, Depends(get_request_auth)],
    db: AsyncSession = Depends(get_db_session),
    audit: AuditWriter = Depends(get_audit_writer),
    settings: Settings = Depends(get_settings),
) -> Response:
    auth_repo = AuthRepository(db)
    await auth_repo.revoke_user_session(
        auth_ctx.session.id,
        auth_ctx.session.organization_id,
    )
    await audit.record(
        "auth.logout",
        auth_ctx.user.organization_id,
        auth_ctx.user.id,
        "session",
        auth_ctx.session.id,
        metadata={},
    )
    await db.commit()
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    out.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
        httponly=True,
        secure=_session_cookie_secure(settings),
    )
    return out


@router.get("/me", response_model=MeResponse)
async def me(
    auth_ctx: Annotated[RequestAuth, Depends(get_request_auth)],
    db: AsyncSession = Depends(get_db_session),
) -> MeResponse:
    u = auth_ctx.user
    o = auth_ctx.organization
    await db.commit()
    return MeResponse(
        user=UserSummary(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=u.role,
        ),
        organization=OrganizationSummary(
            id=o.id,
            name=o.name,
            slug=o.slug,
        ),
    )
