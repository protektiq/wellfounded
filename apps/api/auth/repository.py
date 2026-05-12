"""Async persistence for magic-link tokens and sessions (tenant-scoped reads)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import (
    MagicLinkToken,
    UserSession,
    WebAuthnChallenge,
    WebAuthnChallengePurpose,
    WebAuthnCredential,
)


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

    async def set_session_mfa_verified_at(
        self,
        session_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        verified_at: datetime,
    ) -> bool:
        stmt = (
            update(UserSession)
            .where(
                UserSession.id == session_id,
                UserSession.organization_id == organization_id,
                UserSession.revoked_at.is_(None),
            )
            .values(mfa_verified_at=verified_at)
            .returning(UserSession.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def replace_webauthn_challenge(
        self,
        *,
        organization_id: uuid.UUID,
        session_id: uuid.UUID,
        purpose: WebAuthnChallengePurpose,
        challenge: bytes,
        expires_at: datetime,
        row_id: uuid.UUID,
    ) -> WebAuthnChallenge:
        await self._session.execute(
            delete(WebAuthnChallenge).where(
                WebAuthnChallenge.organization_id == organization_id,
                WebAuthnChallenge.session_id == session_id,
                WebAuthnChallenge.purpose == purpose,
            ),
        )
        row = WebAuthnChallenge(
            id=row_id,
            organization_id=organization_id,
            session_id=session_id,
            purpose=purpose,
            challenge=challenge,
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_webauthn_challenge(
        self,
        organization_id: uuid.UUID,
        session_id: uuid.UUID,
        purpose: WebAuthnChallengePurpose,
    ) -> WebAuthnChallenge | None:
        stmt = select(WebAuthnChallenge).where(
            WebAuthnChallenge.organization_id == organization_id,
            WebAuthnChallenge.session_id == session_id,
            WebAuthnChallenge.purpose == purpose,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_webauthn_challenge(
        self,
        challenge_row_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> bool:
        stmt = (
            delete(WebAuthnChallenge)
            .where(
                WebAuthnChallenge.id == challenge_row_id,
                WebAuthnChallenge.organization_id == organization_id,
            )
            .returning(WebAuthnChallenge.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def insert_webauthn_credential(
        self,
        row: WebAuthnCredential,
    ) -> WebAuthnCredential:
        self._session.add(row)
        await self._session.flush()
        return row

    async def count_webauthn_credentials(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(WebAuthnCredential)
            .where(
                WebAuthnCredential.organization_id == organization_id,
                WebAuthnCredential.user_id == user_id,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_webauthn_credentials_for_user(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[WebAuthnCredential]:
        stmt = (
            select(WebAuthnCredential)
            .where(
                WebAuthnCredential.organization_id == organization_id,
                WebAuthnCredential.user_id == user_id,
            )
            .order_by(WebAuthnCredential.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_webauthn_credential_by_credential_id(
        self,
        organization_id: uuid.UUID,
        credential_id: bytes,
    ) -> WebAuthnCredential | None:
        stmt = select(WebAuthnCredential).where(
            WebAuthnCredential.organization_id == organization_id,
            WebAuthnCredential.credential_id == credential_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_webauthn_credential_sign_count(
        self,
        organization_id: uuid.UUID,
        credential_pk: uuid.UUID,
        *,
        sign_count: int,
        last_used_at: datetime,
    ) -> bool:
        stmt = (
            update(WebAuthnCredential)
            .where(
                WebAuthnCredential.id == credential_pk,
                WebAuthnCredential.organization_id == organization_id,
            )
            .values(sign_count=sign_count, last_used_at=last_used_at)
            .returning(WebAuthnCredential.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
