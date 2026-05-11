"""Pytest fixtures: database URL, Alembic migrations, async session."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_API_ROOT = Path(__file__).resolve().parents[1]


def pytest_configure() -> None:
    _default = (
        "postgresql+asyncpg://wellfounded:wellfounded@127.0.0.1:15432/wellfounded"
    )
    os.environ.setdefault(
        "DATABASE_URL",
        os.environ.get("TEST_DATABASE_URL", _default),
    )
    from config import get_settings

    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _alembic_upgrade_head() -> Iterator[None]:
    cfg = Config(str(_API_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def db_session(_alembic_upgrade_head: None) -> AsyncIterator[AsyncSession]:
    from db.session import get_async_session_maker

    factory = get_async_session_maker()
    async with factory() as session:
        await session.execute(
            text("TRUNCATE TABLE audit_log_entries, organizations CASCADE"),
        )
        await session.commit()
        try:
            yield session
        finally:
            await session.rollback()
