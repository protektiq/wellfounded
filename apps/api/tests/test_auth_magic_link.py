"""Integration tests for magic-link authentication and sessions."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditLogEntry
from audit.repository import AuditRepository
from auth.models import MagicLinkToken
from auth.tokens import generate_raw_token, hash_token
from orgs.models import UserRole, UserStatus
from orgs.repository import OrgRepository


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
