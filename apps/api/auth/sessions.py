"""Helpers for building server-side user session rows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from audit.request_id import generate_request_id_v7
from auth.models import UserSession


def new_session_id() -> uuid.UUID:
    """UUIDv7 session identifier (stdlib lacks uuid7 on Python 3.12)."""
    return generate_request_id_v7()


def build_user_session(
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_agent: str | None,
    ip_addr: str | None,
    session_id: uuid.UUID | None = None,
) -> UserSession:
    now = datetime.now(UTC)
    sid = session_id if session_id is not None else new_session_id()
    return UserSession(
        id=sid,
        user_id=user_id,
        organization_id=organization_id,
        created_at=now,
        last_seen_at=now,
        revoked_at=None,
        user_agent=user_agent,
        ip_addr=ip_addr,
    )
