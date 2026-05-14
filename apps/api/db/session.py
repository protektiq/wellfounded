from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_settings

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


async def dispose_async_engine() -> None:
    """Close all pooled connections and drop cached factory (tests, Alembic churn)."""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_maker = None


def get_async_session_maker() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory, creating the engine on first use."""
    global _engine, _session_maker
    if _session_maker is not None:
        return _session_maker
    settings = get_settings()
    _engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )
    _session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return _session_maker


def get_engine() -> AsyncEngine:
    """Return the shared async engine, creating it on first use."""
    get_async_session_maker()
    assert _engine is not None
    return _engine


async def get_db_session() -> AsyncIterator[AsyncSession]:
    factory = get_async_session_maker()
    async with factory() as session:
        yield session
