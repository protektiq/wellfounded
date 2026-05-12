"""Pytest fixtures: database URL, Alembic migrations, async session."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_API_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _preserve_event_loop() -> Iterator[None]:
    """Prevent sync tests that call asyncio.run() from clearing the session loop.

    asyncio.run() calls asyncio.set_event_loop(None) on exit, which wipes the
    loop that pytest-asyncio set up for the session. Saving and restoring it
    here ensures async tests that follow any sync test continue to work.
    """
    try:
        saved = asyncio.get_event_loop()
    except RuntimeError:
        saved = None
    yield
    if saved is not None and not saved.is_closed():
        asyncio.set_event_loop(saved)


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
        await session.execute(text("TRUNCATE TABLE source_documents CASCADE"))
        await session.execute(text("TRUNCATE TABLE organizations CASCADE"))
        await session.commit()
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def api_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """HTTP client against the ASGI app with DB session override for one test."""
    from config import Settings, get_settings
    from db.session import get_db_session
    from main import app

    async def _db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def _settings_override() -> Settings:
        get_settings.cache_clear()
        return Settings().model_copy(
            update={
                "public_app_url": "http://test/web",
                "api_public_url": "http://test",
            },
        )

    app.dependency_overrides[get_db_session] = _db_override
    app.dependency_overrides[get_settings] = _settings_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def api_client_webauthn(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """HTTP client with WebAuthn RP/origin aligned to py_webauthn test vectors."""
    from config import Settings, get_settings
    from db.session import get_db_session
    from main import app

    async def _db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def _settings_override() -> Settings:
        get_settings.cache_clear()
        return Settings().model_copy(
            update={
                "public_app_url": "http://localhost:5000",
                "api_public_url": "http://localhost:5000",
            },
        )

    app.dependency_overrides[get_db_session] = _db_override
    app.dependency_overrides[get_settings] = _settings_override

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://localhost:5000",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
