"""Async SQLAlchemy engine, session factory and declarative base."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str) -> AsyncEngine:
    """Create (or replace) the global engine. Called at startup and by tests."""
    global _engine, _session_factory
    connect_args: dict[str, object] = {}
    if database_url.startswith("postgresql+asyncpg"):
        # Supabase's transaction pooler does not support prepared statements.
        connect_args["statement_cache_size"] = 0
    if database_url.startswith("sqlite"):
        # Tests: no pooling, so connections never cross event loops.
        _engine = create_async_engine(database_url, poolclass=NullPool)
    else:
        _engine = create_async_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def is_initialized() -> bool:
    return _session_factory is not None


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database engine not initialised; call init_engine() first")
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request."""
    async with session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
