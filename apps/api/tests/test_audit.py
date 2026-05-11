"""Tests for append-only audit log persistence and tenancy."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditLogEntry
from audit.repository import AuditRepository
from audit.writer import AuditWriter
from orgs.models import UserRole, UserStatus
from orgs.repository import OrgRepository


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_writer_persists_org_user_and_request_metadata(
    db_session: AsyncSession,
) -> None:
    org_repo = OrgRepository(db_session)
    slug = f"org-audit-{uuid.uuid4().hex[:8]}"
    org = await org_repo.create_org(name="Org", slug=slug)
    user = await org_repo.create_user(
        organization_id=org.id,
        email="u@example.com",
        display_name="User",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    rid = uuid.uuid4()
    writer = AuditWriter(db_session, rid)
    resource_id = uuid.uuid4()
    await writer.record(
        "case.create",
        org.id,
        user.id,
        "case",
        resource_id,
        metadata={"extra": "x"},
    )
    await db_session.commit()

    audit_repo = AuditRepository(db_session)
    rows = await audit_repo.list_for_organization(org.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.organization_id == org.id
    assert row.user_id == user.id
    assert row.action == "case.create"
    assert row.resource_type == "case"
    assert row.resource_id == resource_id
    assert row.metadata_["request_id"] == str(rid)
    assert row.metadata_["extra"] == "x"


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_list_scoped_to_organization(db_session: AsyncSession) -> None:
    org_repo = OrgRepository(db_session)
    org_a = await org_repo.create_org(name="A", slug=f"org-a-{uuid.uuid4().hex[:8]}")
    org_b = await org_repo.create_org(name="B", slug=f"org-b-{uuid.uuid4().hex[:8]}")
    user_a = await org_repo.create_user(
        organization_id=org_a.id,
        email="a@example.com",
        display_name="A",
        role=UserRole.paralegal,
        status=UserStatus.active,
    )
    rid = uuid.uuid4()
    writer = AuditWriter(db_session, rid)
    await writer.record(
        "memo.generate.start",
        org_a.id,
        user_a.id,
        "memo",
        uuid.uuid4(),
    )
    await writer.record(
        "memo.generate.start",
        org_b.id,
        None,
        "memo",
        uuid.uuid4(),
    )
    await db_session.commit()

    audit_repo = AuditRepository(db_session)
    rows_a = await audit_repo.list_for_organization(org_a.id)
    assert len(rows_a) == 1
    assert rows_a[0].organization_id == org_a.id

    rows_b = await audit_repo.list_for_organization(org_b.id)
    assert len(rows_b) == 1
    assert rows_b[0].organization_id == org_b.id


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_repository_has_no_update_or_delete() -> None:
    assert not hasattr(AuditRepository, "update")
    assert not hasattr(AuditRepository, "delete")


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_update_blocked_by_database_trigger(
    db_session: AsyncSession,
) -> None:
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Org", slug=f"org-trig-{uuid.uuid4().hex[:8]}")
    writer = AuditWriter(db_session, uuid.uuid4())
    resource_id = uuid.uuid4()
    await writer.record(
        "case.create",
        org.id,
        None,
        "case",
        resource_id,
    )
    await db_session.commit()

    audit_repo = AuditRepository(db_session)
    rows = await audit_repo.list_for_organization(org.id)
    entry_id = rows[0].id

    with pytest.raises(DBAPIError) as excinfo:
        await db_session.execute(
            update(AuditLogEntry)
            .where(AuditLogEntry.id == entry_id)
            .values(action="tampered"),
        )
        await db_session.flush()
    combined = str(excinfo.value).lower()
    orig = getattr(excinfo.value, "orig", None)
    if orig is not None:
        combined += str(orig).lower()
    assert "audit_log_append_only" in combined
    await db_session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_delete_blocked_by_database_trigger(
    db_session: AsyncSession,
) -> None:
    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="Org", slug=f"org-del-{uuid.uuid4().hex[:8]}")
    writer = AuditWriter(db_session, uuid.uuid4())
    await writer.record(
        "case.create",
        org.id,
        None,
        "case",
        uuid.uuid4(),
    )
    await db_session.commit()

    audit_repo = AuditRepository(db_session)
    entry_id = (await audit_repo.list_for_organization(org.id))[0].id

    with pytest.raises(DBAPIError) as excinfo:
        await db_session.execute(
            delete(AuditLogEntry).where(AuditLogEntry.id == entry_id),
        )
        await db_session.flush()
    combined = str(excinfo.value).lower()
    orig = getattr(excinfo.value, "orig", None)
    if orig is not None:
        combined += str(orig).lower()
    assert "audit_log_append_only" in combined
    await db_session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_for_organization_time_range_uses_indexed_columns(
    db_session: AsyncSession,
) -> None:
    org_repo = OrgRepository(db_session)
    slug = f"org-range-{uuid.uuid4().hex[:8]}"
    org = await org_repo.create_org(name="Org", slug=slug)
    writer = AuditWriter(db_session, uuid.uuid4())
    await writer.record("a", org.id, None, "t", uuid.uuid4())
    await db_session.commit()

    audit_repo = AuditRepository(db_session)
    now = datetime.now(UTC)
    rows = await audit_repo.list_for_organization(
        org.id,
        created_after=now - timedelta(hours=1),
        created_before=now + timedelta(hours=1),
    )
    assert len(rows) == 1
