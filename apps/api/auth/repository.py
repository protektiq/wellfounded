"""Async persistence for magic-link tokens and sessions (tenant-scoped reads)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import MagicLinkToken, UserSession


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_magic_link_token(self, row: MagicLinkToken) -> MagicLinkToken:
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_magic_link_by_hash_any_org(
        self,
        token_hash: bytes,
    ) -> MagicLinkToken | None:
        """Lookup by hash alone (callback only has token in URL, not org slug)."""
        stmt = select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def consume_magic_link_if_valid(
        self,
        token_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Set consumed_at when unused and not expired. True if one row updated."""
        ts = now if now is not None else datetime.now(UTC)
        stmt = (
            update(MagicLinkToken)
            .where(
                MagicLinkToken.id == token_id,
                MagicLinkToken.consumed_at.is_(None),
                MagicLinkToken.expires_at > ts,
            )
            .values(consumed_at=ts)
            .returning(MagicLinkToken.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def insert_user_session(self, row: UserSession) -> UserSession:
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_user_session_for_org(
        self,
        session_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> UserSession | None:
        stmt = select(UserSession).where(
            UserSession.id == session_id,
            UserSession.organization_id == organization_id,
            UserSession.revoked_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_session_by_id(self, session_id: uuid.UUID) -> UserSession | None:
        stmt = select(UserSession).where(
            UserSession.id == session_id,
            UserSession.revoked_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_user_session(
        self,
        session_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> bool:
        ts = datetime.now(UTC)
        stmt = (
            update(UserSession)
            .where(
                UserSession.id == session_id,
                UserSession.organization_id == organization_id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=ts)
            .returning(UserSession.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def touch_user_session_seen(
        self,
        session_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        ts = datetime.now(UTC)
        await self._session.execute(
            update(UserSession)
            .where(
                UserSession.id == session_id,
                UserSession.organization_id == organization_id,
                UserSession.revoked_at.is_(None),
            )
            .values(last_seen_at=ts),
        )
