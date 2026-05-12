"""Integration tests for case file API: tenancy, RBAC, audit."""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditLogEntry
from cases.models import ClaimBasis
from orgs.models import UserRole, UserStatus
from orgs.repository import OrgRepository


async def _magic_link_login(
    *,
    api_client: AsyncClient,
    db_session: AsyncSession,
    slug: str,
    email: str,
    role: UserRole,
    capsys: pytest.CaptureFixture[str],
) -> None:
    org_repo = OrgRepository(db_session)
    org = await org_repo.get_org_by_slug(slug)
    if org is None:
        org = await org_repo.create_org(name="Cases Org", slug=slug)
    existing = await org_repo.get_user_by_email(email, org.id)
    if existing is None:
        await org_repo.create_user(
            organization_id=org.id,
            email=email,
            display_name="Cases User",
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


def _case_create_payload(*, lead_user_id: uuid.UUID) -> dict[str, object]:
    return {
        "pseudonym": "M.A. — Eritrea",
        "country_code": "er",
        "basis": ClaimBasis.political_opinion.value,
        "group_description": "Particular social group description",
        "filing_deadline": None,
        "asylum_office": None,
        "intake_notes": "Intake",
        "assignments": [
            {"user_id": str(lead_user_id), "role_on_case": "lead_attorney"},
        ],
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_cases_cross_org_isolation(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug_a = f"ca-{uuid.uuid4().hex[:10]}"
    slug_b = f"cb-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug_a,
        email="a1@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    org_a = await org_repo.get_org_by_slug(slug_a)
    assert org_a is not None
    user_a = await org_repo.get_user_by_email("a1@example.com", org_a.id)
    assert user_a is not None

    r_create = await api_client.post(
        "/cases",
        json=_case_create_payload(lead_user_id=user_a.id),
    )
    assert r_create.status_code == 201
    case_id = uuid.UUID(r_create.json()["id"])

    org_b = await org_repo.create_org(name="B", slug=slug_b)
    await org_repo.create_user(
        organization_id=org_b.id,
        email="b1@example.com",
        display_name="B",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug_b,
        email="b1@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    r_get = await api_client.get(f"/cases/{case_id}")
    assert r_get.status_code == 404
    r_list = await api_client.get("/cases")
    assert r_list.status_code == 200
    ids = {item["id"] for item in r_list.json()}
    assert str(case_id) not in ids


@pytest.mark.asyncio(loop_scope="session")
async def test_student_cannot_create_case(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"cs-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="S", slug=slug)
    stu = await org_repo.create_user(
        organization_id=org.id,
        email="stu@example.com",
        display_name="Stu",
        role=UserRole.student,
        status=UserStatus.active,
    )
    await db_session.commit()

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="stu@example.com",
        role=UserRole.student,
        capsys=capsys,
    )
    r = await api_client.post(
        "/cases",
        json=_case_create_payload(lead_user_id=stu.id),
    )
    assert r.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
async def test_paralegal_cannot_archive(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"cp-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="P", slug=slug)
    att = await org_repo.create_user(
        organization_id=org.id,
        email="att@example.com",
        display_name="Att",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    par = await org_repo.create_user(
        organization_id=org.id,
        email="par@example.com",
        display_name="Par",
        role=UserRole.paralegal,
        status=UserStatus.active,
    )
    await db_session.commit()

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="att@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    r_create = await api_client.post(
        "/cases",
        json={
            **_case_create_payload(lead_user_id=att.id),
            "assignments": [
                {"user_id": str(att.id), "role_on_case": "lead_attorney"},
                {"user_id": str(par.id), "role_on_case": "paralegal"},
            ],
        },
    )
    assert r_create.status_code == 201
    case_id = r_create.json()["id"]

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="par@example.com",
        role=UserRole.paralegal,
        capsys=capsys,
    )
    r_arch = await api_client.post(f"/cases/{case_id}/archive")
    assert r_arch.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
async def test_create_requires_lead_attorney(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"cl-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="L", slug=slug)
    att = await org_repo.create_user(
        organization_id=org.id,
        email="la@example.com",
        display_name="LA",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="la@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    body = _case_create_payload(lead_user_id=att.id)
    body["assignments"] = [
        {"user_id": str(att.id), "role_on_case": "supporting_attorney"},
    ]
    r = await api_client.post("/cases", json=body)
    assert r.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_assignment_based_listing(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"cl2-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="L2", slug=slug)
    att_view = await org_repo.create_user(
        organization_id=org.id,
        email="viewer@example.com",
        display_name="Viewer",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    att_peer = await org_repo.create_user(
        organization_id=org.id,
        email="peer@example.com",
        display_name="Peer",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    par = await org_repo.create_user(
        organization_id=org.id,
        email="par2@example.com",
        display_name="Par2",
        role=UserRole.paralegal,
        status=UserStatus.active,
    )
    await db_session.commit()

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="viewer@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    r1 = await api_client.post(
        "/cases",
        json=_case_create_payload(lead_user_id=att_peer.id),
    )
    assert r1.status_code == 201
    r2 = await api_client.post(
        "/cases",
        json={
            **_case_create_payload(lead_user_id=att_view.id),
            "pseudonym": "Other",
            "assignments": [
                {"user_id": str(att_view.id), "role_on_case": "lead_attorney"},
                {"user_id": str(par.id), "role_on_case": "paralegal"},
            ],
        },
    )
    assert r2.status_code == 201

    r_list_att = await api_client.get("/cases")
    assert r_list_att.status_code == 200
    items = r_list_att.json()
    assert len(items) == 2
    access_by_id = {item["id"]: item["access"] for item in items}
    assert access_by_id[r1.json()["id"]] == "read_only"
    assert access_by_id[r2.json()["id"]] == "full"

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="par2@example.com",
        role=UserRole.paralegal,
        capsys=capsys,
    )
    r_list_par = await api_client.get("/cases")
    assert r_list_par.status_code == 200
    assert len(r_list_par.json()) == 1
    assert r_list_par.json()[0]["id"] == r2.json()["id"]


@pytest.mark.asyncio(loop_scope="session")
async def test_soft_delete_hidden_then_restore(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"sd-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="SD", slug=slug)
    await org_repo.create_user(
        organization_id=org.id,
        email="adm@example.com",
        display_name="Adm",
        role=UserRole.admin,
        status=UserStatus.active,
    )
    att = await org_repo.create_user(
        organization_id=org.id,
        email="atd@example.com",
        display_name="Atd",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="atd@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    r_create = await api_client.post(
        "/cases",
        json=_case_create_payload(lead_user_id=att.id),
    )
    assert r_create.status_code == 201
    case_id = r_create.json()["id"]

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="adm@example.com",
        role=UserRole.admin,
        capsys=capsys,
    )
    r_del = await api_client.post(f"/cases/{case_id}/soft-delete")
    assert r_del.status_code == 204

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="atd@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    r_list = await api_client.get("/cases")
    assert r_list.status_code == 200
    assert r_list.json() == []

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="adm@example.com",
        role=UserRole.admin,
        capsys=capsys,
    )
    r_restore = await api_client.post(f"/cases/{case_id}/restore")
    assert r_restore.status_code == 204


@pytest.mark.asyncio(loop_scope="session")
async def test_case_mutations_write_expected_audit_actions(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"au-{uuid.uuid4().hex[:10]}"
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="AU", slug=slug)
    att = await org_repo.create_user(
        organization_id=org.id,
        email="aud@example.com",
        display_name="Aud",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    sup = await org_repo.create_user(
        organization_id=org.id,
        email="sup@example.com",
        display_name="Sup",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    await _magic_link_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="aud@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    r_create = await api_client.post(
        "/cases",
        json=_case_create_payload(lead_user_id=att.id),
    )
    assert r_create.status_code == 201
    case_id = uuid.UUID(r_create.json()["id"])

    r_patch = await api_client.patch(
        f"/cases/{case_id}",
        json={"intake_notes": "Updated intake"},
    )
    assert r_patch.status_code == 200

    r_arch = await api_client.post(f"/cases/{case_id}/archive")
    assert r_arch.status_code == 200

    r_asg = await api_client.post(
        f"/cases/{case_id}/assignments",
        json={
            "add": [{"user_id": str(sup.id), "role_on_case": "supporting_attorney"}],
            "remove": [],
        },
    )
    assert r_asg.status_code == 200

    stmt = select(AuditLogEntry).where(
        AuditLogEntry.organization_id == org.id,
        AuditLogEntry.resource_id == case_id,
    )
    result = await db_session.execute(stmt)
    rows = list(result.scalars().all())
    actions = sorted({e.action for e in rows})
    assert "cases.archive" in actions
    assert "cases.assignments.add" in actions
    assert "cases.create" in actions
    assert "cases.update" in actions
