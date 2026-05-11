"""Integration tests for magic-link authentication and sessions."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditLogEntry
from audit.repository import AuditRepository
from auth.models import (
    MagicLinkToken,
    UserSession,
    WebAuthnChallengePurpose,
    WebAuthnCredential,
)
from auth.repository import AuthRepository
from auth.tokens import generate_raw_token, hash_token
from orgs.models import UserRole, UserStatus
from orgs.repository import OrgRepository

_WEBAUTHN_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "webauthn"


def _load_webauthn_json(name: str) -> dict[str, object]:
    path = _WEBAUTHN_FIXTURES / name
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("fixture root must be a JSON object")
    return cast(dict[str, object], data)


def _webauthn_challenge_registration() -> bytes:
    from webauthn.helpers import base64url_to_bytes

    return base64url_to_bytes(
        "TwN7n4WTyGKLc4ZY-qGsFqKnHM4nglqsyV0ICJlN2TO9XiRyFtrkaDwUvsql-gkLJXP6fnF1MlrZ53Mm4R7Cvw",
    )


def _webauthn_challenge_authentication() -> bytes:
    from webauthn.helpers import base64url_to_bytes

    return base64url_to_bytes(
        "xi30GPGAFYRxVDpY1sM10DaLzVQG66nv-_7RUazH0vI2YvG8LYgDEnvN5fZZNVuvEDuMi9te3VLqb42N0fkLGA",
    )


def _webauthn_ec2_credential_id() -> bytes:
    from webauthn.helpers import base64url_to_bytes

    return base64url_to_bytes(
        "EDx9FfAbp4obx6oll2oC4-CZuDidRVV4gZhxC529ytlnqHyqCStDUwfNdm1SNHAe3X5KvueWQdAX3x9R1a2b9Q",
    )


def _webauthn_ec2_public_key() -> bytes:
    from webauthn.helpers import base64url_to_bytes

    return base64url_to_bytes(
        "pQECAyYgASFYIIeDTe-gN8A-zQclHoRnGFWN8ehM1b7yAsa8I8KIvmplIlgg4nFGT5px8o6gpPZZhO01wdy9crDSA_Ngtkx0vGpvPHI",
    )


async def _webauthn_magic_link_login(
    *,
    api_client: AsyncClient,
    db_session: AsyncSession,
    slug: str,
    email: str,
    role: UserRole,
    capsys: pytest.CaptureFixture[str],
) -> None:
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="WebAuthn Org", slug=slug)
    await org_repo.create_user(
        organization_id=org.id,
        email=email,
        display_name="WA User",
        role=role,
        status=UserStatus.active,
    )
    await db_session.commit()

    await api_client.post(
        "/auth/magic-link",
        json={"email": email, "organization_slug": slug},
    )
    out = capsys.readouterr().out
    m = re.search(r"token=([^\s]+)", out)
    assert m is not None, out
    raw_token = m.group(1)
    r = await api_client.get(
        f"/auth/callback?token={raw_token}",
        follow_redirects=False,
    )
    assert r.status_code == 302


@pytest.mark.asyncio(loop_scope="session")
async def test_magic_link_happy_path_me_and_audit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"auth-happy-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Happy Org", slug=slug)
    await org_repo.create_user(
        organization_id=org.id,
        email="happy@example.com",
        display_name="Happy User",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    r = await api_client.post(
        "/auth/magic-link",
        json={"email": "happy@example.com", "organization_slug": slug},
    )
    assert r.status_code == 204

    out = capsys.readouterr().out
    m = re.search(r"token=([^\s]+)", out)
    assert m is not None, out
    raw_token = m.group(1)

    r2 = await api_client.get(
        f"/auth/callback?token={raw_token}",
        follow_redirects=False,
    )
    assert r2.status_code == 302
    assert "wf_session" in r2.headers.get("set-cookie", "").lower()

    r3 = await api_client.get("/auth/me")
    assert r3.status_code == 200
    body = r3.json()
    assert body["mfa_verified"] is False
    assert body["webauthn_credential_count"] == 0
    assert body["user"]["email"] == "happy@example.com"
    assert body["user"]["display_name"] == "Happy User"
    assert body["organization"]["slug"] == slug

    audit_repo = AuditRepository(db_session)
    rows = await audit_repo.list_for_organization(org.id)
    actions = {row.action for row in rows}
    assert "auth.magic_link.request" in actions
    assert "auth.magic_link.consume" in actions


@pytest.mark.asyncio(loop_scope="session")
async def test_expired_magic_link_rejected(
    db_session: AsyncSession,
    api_client: AsyncClient,
) -> None:
    slug = f"auth-exp-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Exp Org", slug=slug)
    user = await org_repo.create_user(
        organization_id=org.id,
        email="exp@example.com",
        display_name="Exp",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    raw = generate_raw_token()
    digest = hash_token(raw)
    past = datetime.now(UTC) - timedelta(hours=1)
    db_session.add(
        MagicLinkToken(
            id=uuid.uuid4(),
            user_id=user.id,
            organization_id=org.id,
            token_hash=digest,
            expires_at=past,
            consumed_at=None,
        ),
    )
    await db_session.commit()

    r = await api_client.get(f"/auth/callback?token={raw}", follow_redirects=False)
    assert r.status_code == 302
    assert "error=invalid_token" in (r.headers.get("location") or "")


@pytest.mark.asyncio(loop_scope="session")
async def test_consumed_magic_link_cannot_reuse(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"auth-reuse-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Reuse Org", slug=slug)
    await org_repo.create_user(
        organization_id=org.id,
        email="reuse@example.com",
        display_name="Reuse",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    await api_client.post(
        "/auth/magic-link",
        json={"email": "reuse@example.com", "organization_slug": slug},
    )
    out = capsys.readouterr().out
    m = re.search(r"token=([^\s]+)", out)
    assert m is not None
    raw_token = m.group(1)

    r1 = await api_client.get(
        f"/auth/callback?token={raw_token}",
        follow_redirects=False,
    )
    assert r1.status_code == 302
    assert "error=" not in (r1.headers.get("location") or "")

    r2 = await api_client.get(
        f"/auth/callback?token={raw_token}",
        follow_redirects=False,
    )
    assert r2.status_code == 302
    assert "error=invalid_token" in (r2.headers.get("location") or "")


@pytest.mark.asyncio(loop_scope="session")
async def test_logout_invalidates_session(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"auth-out-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Out Org", slug=slug)
    await org_repo.create_user(
        organization_id=org.id,
        email="out@example.com",
        display_name="Out",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    await api_client.post(
        "/auth/magic-link",
        json={"email": "out@example.com", "organization_slug": slug},
    )
    out = capsys.readouterr().out
    m = re.search(r"token=([^\s]+)", out)
    assert m is not None
    raw_token = m.group(1)
    await api_client.get(f"/auth/callback?token={raw_token}", follow_redirects=False)

    lo = await api_client.post("/auth/logout")
    assert lo.status_code == 204

    me = await api_client.get("/auth/me")
    assert me.status_code == 401

    audit_repo = AuditRepository(db_session)
    rows = await audit_repo.list_for_organization(org.id)
    assert any(row.action == "auth.logout" for row in rows)


@pytest.mark.asyncio(loop_scope="session")
async def test_magic_link_unknown_email_returns_204_no_token(
    db_session: AsyncSession,
    api_client: AsyncClient,
) -> None:
    slug = f"auth-miss-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Miss Org", slug=slug)
    await org_repo.create_user(
        organization_id=org.id,
        email="known@example.com",
        display_name="Known",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    r = await api_client.post(
        "/auth/magic-link",
        json={"email": "nobody@example.com", "organization_slug": slug},
    )
    assert r.status_code == 204

    cnt = await db_session.scalar(select(func.count()).select_from(MagicLinkToken))
    assert cnt == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_token_table_stores_hash_not_raw_secret(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"auth-hash-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Hash Org", slug=slug)
    await org_repo.create_user(
        organization_id=org.id,
        email="hash@example.com",
        display_name="Hash",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    await api_client.post(
        "/auth/magic-link",
        json={"email": "hash@example.com", "organization_slug": slug},
    )
    out = capsys.readouterr().out
    m = re.search(r"token=([^\s]+)", out)
    assert m is not None
    raw_token = m.group(1)

    row = (
        await db_session.execute(select(MagicLinkToken).limit(1))
    ).scalar_one()
    assert len(row.token_hash) == 32
    assert row.token_hash != raw_token.encode("utf-8")
    assert raw_token.encode("utf-8") not in (row.token_hash,)


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_magic_link_request_logged_for_unknown_email_in_org(
    db_session: AsyncSession,
    api_client: AsyncClient,
) -> None:
    slug = f"auth-audit-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Audit Org", slug=slug)
    await org_repo.create_user(
        organization_id=org.id,
        email="member@example.com",
        display_name="Member",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    await api_client.post(
        "/auth/magic-link",
        json={"email": "ghost@example.com", "organization_slug": slug},
    )

    audit_repo = AuditRepository(db_session)
    rows = await audit_repo.list_for_organization(org.id)
    req_rows = [x for x in rows if x.action == "auth.magic_link.request"]
    assert len(req_rows) >= 1
    meta = req_rows[-1].metadata_
    assert meta.get("user_found") is False


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_entries_include_request_actions(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"auth-audit2-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Audit2 Org", slug=slug)
    await org_repo.create_user(
        organization_id=org.id,
        email="audit2@example.com",
        display_name="A2",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    await api_client.post(
        "/auth/magic-link",
        json={"email": "audit2@example.com", "organization_slug": slug},
    )
    out = capsys.readouterr().out
    m = re.search(r"token=([^\s]+)", out)
    assert m is not None
    await api_client.get(f"/auth/callback?token={m.group(1)}", follow_redirects=False)
    await api_client.post("/auth/logout")

    result = await db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.organization_id == org.id),
    )
    rows = list(result.scalars().all())
    actions = {row.action for row in rows}
    assert "auth.magic_link.request" in actions
    assert "auth.magic_link.consume" in actions
    assert "auth.logout" in actions


# WebAuthn cases live here (not a separate test_webauthn module) so the `webauthn`
# package is not imported at collection time before pytest-asyncio initializes.


@pytest.mark.asyncio(loop_scope="session")
async def test_webauthn_attorney_register_begin_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"wa-att-{uuid.uuid4().hex[:10]}"
    await _webauthn_magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="att@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    r = await api_client.post("/auth/webauthn/register/begin")
    assert r.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
async def test_webauthn_admin_register_begin_ok(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"wa-adm-{uuid.uuid4().hex[:10]}"
    await _webauthn_magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="adm@example.com",
        role=UserRole.admin,
        capsys=capsys,
    )
    r = await api_client.post("/auth/webauthn/register/begin")
    assert r.status_code == 200
    body = r.json()
    assert "challenge" in body


@pytest.mark.asyncio(loop_scope="session")
async def test_webauthn_admin_users_stub_requires_mfa(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"wa-gate-{uuid.uuid4().hex[:10]}"
    await _webauthn_magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="gate@example.com",
        role=UserRole.admin,
        capsys=capsys,
    )
    r0 = await api_client.get("/orgs/admin/users")
    assert r0.status_code == 403

    raw = api_client.cookies.get("wf_session")
    assert raw is not None
    sid = uuid.UUID(raw)
    now = datetime.now(UTC)
    await db_session.execute(
        update(UserSession).where(UserSession.id == sid).values(mfa_verified_at=now),
    )
    await db_session.commit()

    r1 = await api_client.get("/orgs/admin/users")
    assert r1.status_code == 200
    assert r1.json() == {"users": []}


@pytest.mark.asyncio(loop_scope="session")
async def test_webauthn_registration_finish_sets_credential_and_mfa(
    db_session: AsyncSession,
    api_client_webauthn: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"wa-reg-{uuid.uuid4().hex[:10]}"
    await _webauthn_magic_link_login(
        api_client=api_client_webauthn,
        db_session=db_session,
        slug=slug,
        email="reg@example.com",
        role=UserRole.admin,
        capsys=capsys,
    )
    raw = api_client_webauthn.cookies.get("wf_session")
    assert raw is not None
    sid = uuid.UUID(raw)
    org_repo = OrgRepository(db_session)
    org = await org_repo.get_org_by_slug(slug)
    assert org is not None
    auth_repo = AuthRepository(db_session)
    assert await org_repo.get_user_by_email("reg@example.com", org.id) is not None
    expires = datetime.now(UTC) + timedelta(minutes=5)
    await auth_repo.replace_webauthn_challenge(
        organization_id=org.id,
        session_id=sid,
        purpose=WebAuthnChallengePurpose.registration,
        challenge=_webauthn_challenge_registration(),
        expires_at=expires,
        row_id=uuid.uuid4(),
    )
    await db_session.commit()

    cred = _load_webauthn_json("registration_none_attestation.json")
    fin = await api_client_webauthn.post(
        "/auth/webauthn/register/finish",
        json={"friendly_name": "primary", "credential": cred},
    )
    assert fin.status_code == 204

    me = await api_client_webauthn.get("/auth/me")
    assert me.status_code == 200
    mj = me.json()
    assert mj["webauthn_credential_count"] == 1
    assert mj["mfa_verified"] is True


@pytest.mark.asyncio(loop_scope="session")
async def test_webauthn_authentication_finish_updates_sign_count_and_mfa(
    db_session: AsyncSession,
    api_client_webauthn: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"wa-auth-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Auth Org", slug=slug)
    org_id = org.id
    user = await org_repo.create_user(
        organization_id=org_id,
        email="authfin@example.com",
        display_name="Auth Fin",
        role=UserRole.admin,
        status=UserStatus.active,
    )
    db_session.add(
        WebAuthnCredential(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=user.id,
            credential_id=_webauthn_ec2_credential_id(),
            public_key=_webauthn_ec2_public_key(),
            sign_count=77,
            transports=["usb"],
            friendly_name="fixture",
            created_at=datetime.now(UTC),
            last_used_at=None,
        ),
    )
    await db_session.commit()

    await api_client_webauthn.post(
        "/auth/magic-link",
        json={"email": "authfin@example.com", "organization_slug": slug},
    )
    out = capsys.readouterr().out
    m = re.search(r"token=([^\s]+)", out)
    assert m is not None
    raw_token = m.group(1)
    cb = await api_client_webauthn.get(
        f"/auth/callback?token={raw_token}",
        follow_redirects=False,
    )
    assert cb.status_code == 302
    raw = api_client_webauthn.cookies.get("wf_session")
    assert raw is not None
    sid = uuid.UUID(raw)

    auth_repo = AuthRepository(db_session)
    expires = datetime.now(UTC) + timedelta(minutes=5)
    await auth_repo.replace_webauthn_challenge(
        organization_id=org_id,
        session_id=sid,
        purpose=WebAuthnChallengePurpose.authentication,
        challenge=_webauthn_challenge_authentication(),
        expires_at=expires,
        row_id=uuid.uuid4(),
    )
    await db_session.commit()

    cred = _load_webauthn_json("authentication_ec2.json")
    fin = await api_client_webauthn.post(
        "/auth/webauthn/authenticate/finish",
        json={"credential": cred},
    )
    assert fin.status_code == 204

    await db_session.commit()
    db_session.expire_all()
    row = await auth_repo.get_webauthn_credential_by_credential_id(
        org_id,
        _webauthn_ec2_credential_id(),
    )
    assert row is not None
    assert row.sign_count == 78
    assert row.last_used_at is not None

    sess = await auth_repo.get_user_session_by_id(sid)
    assert sess is not None
    assert sess.mfa_verified_at is not None
