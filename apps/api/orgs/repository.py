"""Async persistence for organizations and users."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orgs.models import Organization, User, UserRole, UserStatus


class OrgRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_org_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(
            Organization.slug == slug,
            Organization.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_organization_by_id(
        self,
        organization_id: uuid.UUID,
    ) -> Organization | None:
        stmt = select(Organization).where(
            Organization.id == organization_id,
            Organization.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_org(
        self,
        *,
        name: str,
        slug: str,
        kms_data_key_arn: str | None = None,
    ) -> Organization:
        org = Organization(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            kms_data_key_arn=kms_data_key_arn,
        )
        self._session.add(org)
        await self._session.flush()
        return org

    async def get_user_by_email(
        self,
        email: str,
        organization_id: uuid.UUID,
    ) -> User | None:
        stmt = select(User).where(
            User.email == email,
            User.organization_id == organization_id,
            User.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(
        self,
        *,
        organization_id: uuid.UUID,
        email: str,
        display_name: str,
        role: UserRole,
        status: UserStatus,
    ) -> User:
        user = User(
            id=uuid.uuid4(),
            organization_id=organization_id,
            email=email,
            display_name=display_name,
            role=role,
            status=status,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def list_users_in_org(self, organization_id: uuid.UUID) -> list[User]:
        stmt = (
            select(User)
            .where(
                User.organization_id == organization_id,
                User.deleted_at.is_(None),
            )
            .order_by(User.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete_user(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> bool:
        stmt = select(User).where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return False
        user.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return True
