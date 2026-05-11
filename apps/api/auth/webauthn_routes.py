"""WebAuthn (passkey) registration and authentication for admin MFA."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
)

from audit.deps import get_audit_writer
from audit.writer import AuditWriter
from auth.deps import RequestAuth, get_request_auth
from auth.models import WebAuthnChallengePurpose, WebAuthnCredential
from auth.repository import AuthRepository
from auth.schemas import (
    WebAuthnAuthenticateFinishRequest,
    WebAuthnRegisterFinishRequest,
)
from config import Settings, get_settings
from db.session import get_db_session
from orgs.models import UserRole

log = structlog.get_logger()

router = APIRouter(prefix="/webauthn", tags=["webauthn"])

_CHALLENGE_TTL_SECONDS = 300
_MAX_CREDENTIAL_JSON_BYTES = 256 * 1024


def _require_admin(auth: RequestAuth) -> None:
    if auth.user.role is not UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="WebAuthn enrollment is limited to admin users",
        )


def _descriptor_transports(
    transports: list[str],
) -> list[AuthenticatorTransport] | None:
    out: list[AuthenticatorTransport] = []
    for raw in transports:
        if not isinstance(raw, str) or len(raw) > 32:
            continue
        try:
            out.append(AuthenticatorTransport(raw))
        except ValueError:
            continue
    return out or None


def _transports_for_storage(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and 0 < len(item) <= 32:
            out.append(item)
        if len(out) >= 16:
            break
    return out


@router.post("/register/begin")
async def webauthn_register_begin(
    auth_ctx: Annotated[RequestAuth, Depends(get_request_auth)],
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    _require_admin(auth_ctx)
    auth_repo = AuthRepository(db)
    rp_id = settings.resolved_webauthn_rp_id()
    existing = await auth_repo.list_webauthn_credentials_for_user(
        auth_ctx.user.organization_id,
        auth_ctx.user.id,
    )
    exclude: list[PublicKeyCredentialDescriptor] = []
    for cred in existing:
        exclude.append(
            PublicKeyCredentialDescriptor(
                id=cred.credential_id,
                transports=_descriptor_transports(cred.transports),
            ),
        )
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=settings.webauthn_rp_name,
        user_name=str(auth_ctx.user.id),
        user_id=auth_ctx.user.id.bytes,
        user_display_name=auth_ctx.user.display_name[:64],
        exclude_credentials=exclude or None,
    )
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=_CHALLENGE_TTL_SECONDS)
    await auth_repo.replace_webauthn_challenge(
        organization_id=auth_ctx.user.organization_id,
        session_id=auth_ctx.session.id,
        purpose=WebAuthnChallengePurpose.registration,
        challenge=options.challenge,
        expires_at=expires,
        row_id=uuid.uuid4(),
    )
    await db.commit()
    return Response(
        content=options_to_json(options),
        media_type="application/json",
    )


@router.post("/register/finish")
async def webauthn_register_finish(
    auth_ctx: Annotated[RequestAuth, Depends(get_request_auth)],
    body: WebAuthnRegisterFinishRequest,
    db: AsyncSession = Depends(get_db_session),
    audit: AuditWriter = Depends(get_audit_writer),
    settings: Settings = Depends(get_settings),
) -> Response:
    _require_admin(auth_ctx)
    auth_repo = AuthRepository(db)
    row = await auth_repo.get_webauthn_challenge(
        auth_ctx.user.organization_id,
        auth_ctx.session.id,
        WebAuthnChallengePurpose.registration,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active WebAuthn registration challenge",
        )
    now = datetime.now(UTC)
    if row.expires_at <= now:
        await auth_repo.delete_webauthn_challenge(row.id, auth_ctx.user.organization_id)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WebAuthn registration challenge expired",
        )
    rp_id = settings.resolved_webauthn_rp_id()
    origins = settings.resolved_webauthn_expected_origins()
    try:
        verified = verify_registration_response(
            credential=body.credential,
            expected_challenge=row.challenge,
            expected_rp_id=rp_id,
            expected_origin=origins,
        )
    except InvalidRegistrationResponse as exc:
        log.warning("webauthn_register_verify_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid WebAuthn registration payload",
        ) from exc

    transports = _transports_for_storage(body.credential.get("transports"))
    cred_row = WebAuthnCredential(
        id=uuid.uuid4(),
        organization_id=auth_ctx.user.organization_id,
        user_id=auth_ctx.user.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=transports,
        friendly_name=body.friendly_name,
        created_at=now,
        last_used_at=None,
    )
    await auth_repo.insert_webauthn_credential(cred_row)
    await auth_repo.delete_webauthn_challenge(row.id, auth_ctx.user.organization_id)
    await auth_repo.set_session_mfa_verified_at(
        auth_ctx.session.id,
        auth_ctx.user.organization_id,
        verified_at=now,
    )
    await audit.record(
        "auth.webauthn.register_finish",
        auth_ctx.user.organization_id,
        auth_ctx.user.id,
        "webauthn_credential",
        cred_row.id,
        metadata={"friendly_name": body.friendly_name},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/authenticate/begin")
async def webauthn_authenticate_begin(
    auth_ctx: Annotated[RequestAuth, Depends(get_request_auth)],
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    _require_admin(auth_ctx)
    auth_repo = AuthRepository(db)
    n = await auth_repo.count_webauthn_credentials(
        auth_ctx.user.organization_id,
        auth_ctx.user.id,
    )
    if n < 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Register a passkey before WebAuthn authentication",
        )
    creds = await auth_repo.list_webauthn_credentials_for_user(
        auth_ctx.user.organization_id,
        auth_ctx.user.id,
    )
    allow: list[PublicKeyCredentialDescriptor] = []
    for cred in creds:
        allow.append(
            PublicKeyCredentialDescriptor(
                id=cred.credential_id,
                transports=_descriptor_transports(cred.transports),
            ),
        )
    rp_id = settings.resolved_webauthn_rp_id()
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow,
    )
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=_CHALLENGE_TTL_SECONDS)
    await auth_repo.replace_webauthn_challenge(
        organization_id=auth_ctx.user.organization_id,
        session_id=auth_ctx.session.id,
        purpose=WebAuthnChallengePurpose.authentication,
        challenge=options.challenge,
        expires_at=expires,
        row_id=uuid.uuid4(),
    )
    await db.commit()
    return Response(
        content=options_to_json(options),
        media_type="application/json",
    )


@router.post("/authenticate/finish")
async def webauthn_authenticate_finish(
    auth_ctx: Annotated[RequestAuth, Depends(get_request_auth)],
    body: WebAuthnAuthenticateFinishRequest,
    db: AsyncSession = Depends(get_db_session),
    audit: AuditWriter = Depends(get_audit_writer),
    settings: Settings = Depends(get_settings),
) -> Response:
    _require_admin(auth_ctx)
    auth_repo = AuthRepository(db)
    n = await auth_repo.count_webauthn_credentials(
        auth_ctx.user.organization_id,
        auth_ctx.user.id,
    )
    if n < 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Register a passkey before WebAuthn authentication",
        )
    row = await auth_repo.get_webauthn_challenge(
        auth_ctx.user.organization_id,
        auth_ctx.session.id,
        WebAuthnChallengePurpose.authentication,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active WebAuthn authentication challenge",
        )
    now = datetime.now(UTC)
    if row.expires_at <= now:
        await auth_repo.delete_webauthn_challenge(row.id, auth_ctx.user.organization_id)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WebAuthn authentication challenge expired",
        )

    raw_id_b: bytes | None = None
    rid = body.credential.get("rawId")
    if isinstance(rid, str):
        try:
            raw_id_b = base64url_to_bytes(rid)
        except Exception:
            raw_id_b = None
    if raw_id_b is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid credential rawId",
        )

    stored = await auth_repo.get_webauthn_credential_by_credential_id(
        auth_ctx.user.organization_id,
        raw_id_b,
    )
    if stored is None or stored.user_id != auth_ctx.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown WebAuthn credential",
        )

    rp_id = settings.resolved_webauthn_rp_id()
    origins = settings.resolved_webauthn_expected_origins()
    try:
        verified = verify_authentication_response(
            credential=body.credential,
            expected_challenge=row.challenge,
            expected_rp_id=rp_id,
            expected_origin=origins,
            credential_public_key=stored.public_key,
            credential_current_sign_count=stored.sign_count,
        )
    except InvalidAuthenticationResponse as exc:
        log.warning("webauthn_authenticate_verify_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid WebAuthn authentication payload",
        ) from exc

    await auth_repo.update_webauthn_credential_sign_count(
        auth_ctx.user.organization_id,
        stored.id,
        sign_count=verified.new_sign_count,
        last_used_at=now,
    )
    await auth_repo.delete_webauthn_challenge(row.id, auth_ctx.user.organization_id)
    await auth_repo.set_session_mfa_verified_at(
        auth_ctx.session.id,
        auth_ctx.user.organization_id,
        verified_at=now,
    )
    await audit.record(
        "auth.webauthn.authenticate_finish",
        auth_ctx.user.organization_id,
        auth_ctx.user.id,
        "webauthn_credential",
        stored.id,
        metadata={},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
