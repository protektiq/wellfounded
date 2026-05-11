"""Integration tests for org repository tenancy and soft delete."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from orgs.models import UserRole, UserStatus
from orgs.repository import OrgRepository

_API_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio(loop_scope="session")
async def test_get_user_by_email_scoped_to_org(db_session: AsyncSession) -> None:
    repo = OrgRepository(db_session)
    org_a = await repo.create_org(name="Org A", slug=f"org-a-{uuid.uuid4().hex[:8]}")
    org_b = await repo.create_org(name="Org B", slug=f"org-b-{uuid.uuid4().hex[:8]}")
    email = "alice@x.com"
    user_a = await repo.create_user(
        organization_id=org_a.id,
        email=email,
        display_name="Alice A",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    user_b = await repo.create_user(
        organization_id=org_b.id,
        email=email,
        display_name="Alice B",
        role=UserRole.paralegal,
        status=UserStatus.active,
    )
    found_a = await repo.get_user_by_email(email, org_a.id)
    found_b = await repo.get_user_by_email(email, org_b.id)
    assert found_a is not None
    assert found_b is not None
    assert found_a.id == user_a.id
    assert found_b.id == user_b.id
    assert found_a.id != found_b.id
    assert found_a.organization_id == org_a.id
    assert found_b.organization_id == org_b.id


@pytest.mark.asyncio(loop_scope="session")
async def test_soft_delete_excludes_from_list_and_lookup(
    db_session: AsyncSession,
) -> None:
    repo = OrgRepository(db_session)
    org = await repo.create_org(name="Org", slug=f"org-del-{uuid.uuid4().hex[:8]}")
    user = await repo.create_user(
        organization_id=org.id,
        email="bob@x.com",
        display_name="Bob",
        role=UserRole.student,
        status=UserStatus.invited,
    )
    before = await repo.list_users_in_org(org.id)
    assert len(before) == 1
    assert before[0].id == user.id

    deleted = await repo.soft_delete_user(user.id, org.id)
    assert deleted is True

    after_list = await repo.list_users_in_org(org.id)
    assert after_list == []

    found = await repo.get_user_by_email("bob@x.com", org.id)
    assert found is None


@pytest.mark.asyncio(loop_scope="session")
async def test_soft_delete_wrong_org_returns_false(db_session: AsyncSession) -> None:
    repo = OrgRepository(db_session)
    org_a = await repo.create_org(name="A", slug=f"org-w-{uuid.uuid4().hex[:8]}")
    org_b = await repo.create_org(name="B", slug=f"org-x-{uuid.uuid4().hex[:8]}")
    user = await repo.create_user(
        organization_id=org_a.id,
        email="c@x.com",
        display_name="C",
        role=UserRole.admin,
        status=UserStatus.active,
    )
    assert await repo.soft_delete_user(user.id, org_b.id) is False
    still = await repo.get_user_by_email("c@x.com", org_a.id)
    assert still is not None


def test_alembic_downgrade_removes_org_tables() -> None:
    cfg = Config(str(_API_ROOT / "alembic.ini"))

    from sqlalchemy.ext.asyncio import create_async_engine

    from config import get_settings

    async def has_organizations_table(url: str) -> bool:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).has_table("organizations"),
                )
        finally:
            await engine.dispose()

    url = get_settings().database_url

    async def has_org() -> bool:
        return await has_organizations_table(url)

    before = asyncio.run(has_org())
    command.downgrade(cfg, "cc18cd30d200")
    after_down = asyncio.run(has_org())
    command.upgrade(cfg, "head")
    after_up = asyncio.run(has_org())
    assert before is True
    assert after_down is False
    assert after_up is True
